"""
PenDonn notifications.

Push notifications via ntfy.sh (or self-hosted ntfy server) for:
  - Handshake captured
  - PSK cracked
  - Vulnerability found
  - Scan completed

Design notes:
  - Fire-and-forget over a daemon thread — never block the main pipeline
    even if the ntfy server is slow or unreachable.
  - Config-gated: disabled by default. Enable in config.json.local by
    setting `notifications.ntfy.enabled = true` and `notifications.ntfy.topic`.
  - Topic security: ntfy topics are public-by-default. Use a long random
    topic name and treat it as a shared secret (keep it in config.json.local,
    never in committed defaults).
  - Severity tiers map to ntfy priorities so phones can be configured to
    only buzz on high-priority events.
"""

import logging
import threading
from queue import Queue, Empty
from typing import Dict, Optional

import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


# ntfy priority levels (1=min, 5=urgent). Mapped from semantic event types.
_PRIORITY = {
    'low': '2',
    'normal': '3',
    'high': '4',
    'urgent': '5',
}


class Notifier:
    """Background notification dispatcher.

    Drops events onto an in-process queue; a worker thread sends them out
    over HTTP. If the queue ever fills (server down for hours), oldest
    events are dropped — we'd rather lose a notification than back-pressure
    the capture/crack pipeline.
    """

    def __init__(self, config: Dict):
        ntfy_cfg = config.get('notifications', {}).get('ntfy', {})
        self.enabled = bool(ntfy_cfg.get('enabled', False))
        self.server = ntfy_cfg.get('server', 'https://ntfy.sh').rstrip('/')
        self.topic = ntfy_cfg.get('topic', '').strip()
        # Optional bearer token for self-hosted ntfy with auth.
        self.token = ntfy_cfg.get('token', '').strip()
        # Per-event opt-out: e.g. notify_on = {"handshake": false, ...}
        self.notify_on = ntfy_cfg.get('notify_on', {})

        self._queue: Queue = Queue(maxsize=200)
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None

        if self.enabled and not self.topic:
            logger.warning("notifications.ntfy.enabled=true but no topic set — disabling")
            self.enabled = False

        if self.enabled:
            self._worker = threading.Thread(
                target=self._run, name='ntfy-worker', daemon=True
            )
            self._worker.start()
            logger.info(f"Notifier started (server={self.server}, topic=***)")
        else:
            logger.info("Notifier disabled (set notifications.ntfy.enabled in config.json.local)")

    def stop(self):
        self._stop.set()
        # Worker is a daemon thread; no need to join.

    # ---------- semantic event helpers ----------

    def handshake_captured(self, ssid: str, bssid: str):
        if not self._allowed('handshake'):
            return
        self._enqueue(
            title=f"Handshake captured: {ssid}",
            body=f"BSSID {bssid}",
            priority='low',
            tags=['lock'],
        )

    def password_cracked(self, ssid: str, bssid: str, engine: str, seconds: int):
        if not self._allowed('crack'):
            return
        self._enqueue(
            title=f"PSK cracked: {ssid}",
            body=f"BSSID {bssid} — {engine} in {seconds}s",
            priority='high',
            tags=['key', 'fire'],
        )

    def vulnerability_found(self, ssid: str, host: str, severity: str,
                            vuln_type: str, description: str = ''):
        if not self._allowed('vulnerability'):
            return
        sev = (severity or '').lower()
        prio = 'urgent' if sev == 'critical' else ('high' if sev == 'high' else 'normal')
        body = f"{host} — {vuln_type}"
        if description:
            body += f"\n{description[:200]}"
        self._enqueue(
            title=f"[{sev or 'vuln'}] {ssid}",
            body=body,
            priority=prio,
            tags=['warning'] if sev in ('critical', 'high') else ['mag'],
        )

    def scan_completed(self, ssid: str, hosts: int, vulns: int):
        if not self._allowed('scan'):
            return
        self._enqueue(
            title=f"Scan complete: {ssid}",
            body=f"{hosts} host{'s' if hosts != 1 else ''}, {vulns} vuln{'s' if vulns != 1 else ''}",
            priority='normal',
            tags=['white_check_mark'],
        )

    # ---------- internals ----------

    def _allowed(self, kind: str) -> bool:
        if not self.enabled:
            return False
        # Default to True for unspecified kinds; explicit false opts out.
        return self.notify_on.get(kind, True) is not False

    def _enqueue(self, title: str, body: str, priority: str, tags):
        try:
            self._queue.put_nowait({
                'title': title,
                'body': body,
                'priority': _PRIORITY.get(priority, '3'),
                'tags': ','.join(tags) if tags else '',
            })
        except Exception:
            # Queue full — drop oldest, push new.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait({
                    'title': title, 'body': body,
                    'priority': _PRIORITY.get(priority, '3'),
                    'tags': ','.join(tags) if tags else '',
                })
            except Exception as e:
                logger.warning(f"Notifier queue full, dropping event: {e}")

    def _run(self):
        url = f"{self.server}/{self.topic}"
        while not self._stop.is_set():
            try:
                msg = self._queue.get(timeout=1.0)
            except Empty:
                continue

            try:
                req = urllib.request.Request(
                    url,
                    data=msg['body'].encode('utf-8'),
                    method='POST',
                )
                req.add_header('Title', msg['title'])
                req.add_header('Priority', msg['priority'])
                if msg['tags']:
                    req.add_header('Tags', msg['tags'])
                if self.token:
                    req.add_header('Authorization', f'Bearer {self.token}')
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status >= 400:
                        logger.warning(f"ntfy returned {resp.status} for {msg['title']}")
            except urllib.error.URLError as e:
                logger.warning(f"ntfy delivery failed: {e}")
            except Exception as e:
                logger.warning(f"ntfy unexpected error: {e}")
