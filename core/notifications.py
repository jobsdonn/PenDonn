"""
PenDonn notifications.

Push notifications for:
  - Handshake captured
  - PSK cracked
  - Vulnerability found
  - Scan completed

Two transports are supported, each opt-in via config:

  1. **ntfy.sh** (or self-hosted ntfy server) — sends a phone-friendly
     push via the public ntfy.sh service or a private instance.
     Headers: Title / Priority / Tags. Plain-text body.
  2. **Webhook** — POST a JSON payload to any URL, optional custom
     headers. Use for Slack/Teams/Discord/n8n/your-own-server.

Both backends share semantics: same event types, same priority tiers
(low/normal/high/urgent), same per-event opt-out. They run in parallel
when both are enabled.

Design notes:
  - Fire-and-forget over a daemon thread per backend — never block
    the main pipeline even if a remote endpoint is slow or unreachable.
  - Bounded queues drop oldest on overflow; auditing is more
    valuable than guaranteed delivery for ops alerting.
  - Disabled by default. Operator turns on individual transports
    via config.json.local.
"""

import abc
import json
import logging
import threading
import time
from queue import Queue, Empty
from typing import Dict, List, Optional

import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


# Semantic priority -> numeric ntfy priority. Webhook backends get the
# semantic name as a string field instead, since Slack/Teams/etc don't
# care about ntfy's 1-5 scale.
_NTFY_PRIORITY = {
    'low': '2',
    'normal': '3',
    'high': '4',
    'urgent': '5',
}


# ---------------------------------------------------------------------------
# Backend interface
# ---------------------------------------------------------------------------


class _Backend(abc.ABC):
    """Each backend owns a thread + queue + delivery loop. Subclasses
    implement `_deliver(event)` for whatever HTTP shape they need."""

    name = "abstract"

    def __init__(self, queue_size: int = 200):
        self._queue: Queue = Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None

    def start(self):
        self._worker = threading.Thread(
            target=self._run, name=f"notify-{self.name}", daemon=True,
        )
        self._worker.start()
        logger.info(f"Notification backend started: {self.name}")

    def stop(self):
        self._stop.set()

    def enqueue(self, event: Dict):
        try:
            self._queue.put_nowait(event)
        except Exception:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(event)
            except Exception as e:
                logger.warning(f"{self.name} queue full, dropping event: {e}")

    @abc.abstractmethod
    def _deliver(self, event: Dict) -> None:
        """Send one event over the wire. Should raise on failure so the
        worker can log it; the worker swallows the exception."""

    # Retry delays (seconds) for transient network errors (DNS, ECONNREFUSED).
    # Injection on adjacent radios can briefly disrupt the management WiFi;
    # 30s is usually enough for connectivity to recover between bursts.
    _RETRY_DELAYS = (10, 30)

    def _run(self):
        while not self._stop.is_set():
            try:
                event = self._queue.get(timeout=1.0)
            except Empty:
                continue
            last_err = None
            for attempt, delay in enumerate(
                [0] + list(self._RETRY_DELAYS), start=1
            ):
                if delay:
                    time.sleep(delay)
                try:
                    self._deliver(event)
                    last_err = None
                    break
                except urllib.error.URLError as e:
                    last_err = e
                    if attempt <= len(self._RETRY_DELAYS):
                        logger.debug(
                            f"{self.name} delivery attempt {attempt} failed "
                            f"({e}); retrying in {self._RETRY_DELAYS[attempt-1]}s"
                        )
                except Exception as e:
                    logger.warning(f"{self.name} unexpected error: {e}")
                    break
            if last_err is not None:
                logger.warning(
                    f"{self.name} delivery failed after "
                    f"{len(self._RETRY_DELAYS)+1} attempts: {last_err}"
                )


# ---------------------------------------------------------------------------
# ntfy backend
# ---------------------------------------------------------------------------


class NtfyBackend(_Backend):
    name = "ntfy"

    def __init__(self, server: str, topic: str, token: str = ""):
        super().__init__()
        self.server = server.rstrip("/")
        self.topic = topic
        self.token = token

    def _deliver(self, event: Dict) -> None:
        url = f"{self.server}/{self.topic}"
        req = urllib.request.Request(
            url,
            data=event["body"].encode("utf-8"),
            method="POST",
        )
        req.add_header("Title", event["title"])
        req.add_header("Priority", _NTFY_PRIORITY.get(event["priority"], "3"))
        if event.get("tags"):
            req.add_header("Tags", event["tags"])
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 400:
                logger.warning(f"ntfy returned {resp.status} for {event['title']}")


# ---------------------------------------------------------------------------
# Generic webhook backend
# ---------------------------------------------------------------------------


def _autodetect_webhook_format(url: str) -> str:
    """Best-effort guess at the destination's expected payload shape
    based on the URL host. Used when config doesn't pin `format`
    explicitly. Falls back to generic JSON."""
    u = (url or "").lower()
    if "discord.com/api/webhooks" in u or "discordapp.com/api/webhooks" in u:
        return "discord"
    if "hooks.slack.com" in u:
        return "slack"
    if "office.com/webhook" in u or "outlook.office.com/webhook" in u or "webhook.office.com" in u:
        return "teams"
    return "json"


# Priority -> color (0xRRGGBB) for rich-format outputs.
_PRIORITY_COLOR = {
    "low":     0x94A3B8,  # slate
    "normal":  0x0EA5E9,  # sky
    "high":    0xF59E0B,  # amber
    "urgent":  0xEF4444,  # red
}


class WebhookBackend(_Backend):
    """POSTs to a configured URL. Several output formats are supported
    so common destinations work without an external relay.

    Formats:
      - "json" (default): generic
            {event, priority, title, body, tags, data}
      - "discord": Discord incoming-webhook
            {username, content, embeds:[{title, description, color}]}
      - "slack":   Slack incoming-webhook
            {text, blocks}
      - "teams":   Microsoft Teams legacy connector
            {"@type": "MessageCard", title, text, themeColor}

    Custom headers can be set per backend (for bearer auth on private
    endpoints; Slack/Discord/Teams hooks encode their auth in the URL
    so headers are usually unnecessary for those).
    """
    name = "webhook"

    SUPPORTED_FORMATS = ("json", "discord", "slack", "teams")

    def __init__(self, url: str, headers: Optional[Dict[str, str]] = None,
                 fmt: str = "json"):
        super().__init__()
        self.url = url
        self.headers = headers or {}
        if fmt not in self.SUPPORTED_FORMATS:
            logger.warning(
                f"Unknown webhook format {fmt!r}; falling back to 'json'"
            )
            fmt = "json"
        self.fmt = fmt

    # ---- format translators ----

    @staticmethod
    def _payload_json(event: Dict) -> bytes:
        return json.dumps({
            "event": event.get("event"),
            "priority": event.get("priority"),
            "title": event.get("title"),
            "body": event.get("body"),
            "tags": (event.get("tags") or "").split(",") if event.get("tags") else [],
            "data": event.get("data") or {},
        }).encode("utf-8")

    @staticmethod
    def _payload_discord(event: Dict) -> bytes:
        title = event.get("title") or "PenDonn"
        body = event.get("body") or ""
        priority = event.get("priority", "normal")
        color = _PRIORITY_COLOR.get(priority, _PRIORITY_COLOR["normal"])
        return json.dumps({
            "username": "PenDonn",
            # `content` covers clients that ignore embeds. Embed gives
            # the colored sidebar that makes severity scannable.
            "content": f"**{title}**",
            "embeds": [{
                "title": title,
                "description": body[:4000] if body else " ",
                "color": color,
            }],
        }).encode("utf-8")

    @staticmethod
    def _payload_slack(event: Dict) -> bytes:
        title = event.get("title") or "PenDonn"
        body = event.get("body") or ""
        priority = event.get("priority", "normal")
        # Slack uses string-named "color" on attachments — but for incoming
        # webhooks we send `text` as the primary content and a colored
        # attachment for severity.
        slack_color = {
            "low":     "#94A3B8",
            "normal":  "#0EA5E9",
            "high":    "#F59E0B",
            "urgent":  "#EF4444",
        }.get(priority, "#0EA5E9")
        return json.dumps({
            "text": title,
            "attachments": [{
                "color": slack_color,
                "text": body or " ",
            }],
        }).encode("utf-8")

    @staticmethod
    def _payload_teams(event: Dict) -> bytes:
        title = event.get("title") or "PenDonn"
        body = event.get("body") or ""
        priority = event.get("priority", "normal")
        # Teams legacy MessageCard themeColor is hex without `#`.
        theme_color = "{:06X}".format(
            _PRIORITY_COLOR.get(priority, _PRIORITY_COLOR["normal"])
        )
        return json.dumps({
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": title,
            "themeColor": theme_color,
            "title": title,
            "text": body or " ",
        }).encode("utf-8")

    def _deliver(self, event: Dict) -> None:
        if self.fmt == "discord":
            payload = self._payload_discord(event)
        elif self.fmt == "slack":
            payload = self._payload_slack(event)
        elif self.fmt == "teams":
            payload = self._payload_teams(event)
        else:
            payload = self._payload_json(event)

        req = urllib.request.Request(self.url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "PenDonn/1.0")
        for k, v in self.headers.items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 400:
                logger.warning(f"webhook returned {resp.status} for {event.get('title')}")


# ---------------------------------------------------------------------------
# Notifier — public surface
# ---------------------------------------------------------------------------


class Notifier:
    """Multi-backend dispatcher. Disabled by default; backends are added
    based on `notifications.<name>.enabled` flags in config."""

    def __init__(self, config: Dict):
        notif_cfg = config.get("notifications", {}) or {}
        self.backends: List[_Backend] = []
        self.notify_on: Dict[str, bool] = {}

        # Pull a unified per-event opt-out. Either backend's notify_on
        # works; if both set, ntfy wins (first-loaded; in practice they
        # should match because the operator usually only changes one UI).
        ntfy_cfg = notif_cfg.get("ntfy", {}) or {}
        webhook_cfg = notif_cfg.get("webhook", {}) or {}

        if ntfy_cfg.get("enabled") and ntfy_cfg.get("topic"):
            backend = NtfyBackend(
                server=ntfy_cfg.get("server", "https://ntfy.sh"),
                topic=ntfy_cfg.get("topic", "").strip(),
                token=ntfy_cfg.get("token", "").strip(),
            )
            backend.start()
            self.backends.append(backend)
            self.notify_on = ntfy_cfg.get("notify_on", {}) or {}
        elif ntfy_cfg.get("enabled"):
            logger.warning(
                "notifications.ntfy.enabled=true but no topic set — "
                "ntfy backend disabled"
            )

        if webhook_cfg.get("enabled") and webhook_cfg.get("url"):
            url = webhook_cfg.get("url", "").strip()
            fmt = webhook_cfg.get("format") or _autodetect_webhook_format(url)
            backend = WebhookBackend(
                url=url,
                headers=webhook_cfg.get("headers", {}) or {},
                fmt=fmt,
            )
            backend.start()
            self.backends.append(backend)
            # Webhook notify_on overrides only if ntfy didn't set it.
            if not self.notify_on:
                self.notify_on = webhook_cfg.get("notify_on", {}) or {}
        elif webhook_cfg.get("enabled"):
            logger.warning(
                "notifications.webhook.enabled=true but no url set — "
                "webhook backend disabled"
            )

        if not self.backends:
            logger.info(
                "Notifications disabled (no enabled+configured backends). "
                "Configure in WebUI Settings → Notifications, or in "
                "config.json.local."
            )

    @property
    def enabled(self) -> bool:
        return bool(self.backends)

    def stop(self):
        for b in self.backends:
            b.stop()

    # ---------- semantic event helpers ----------

    def handshake_captured(self, ssid: str, bssid: str):
        if not self._allowed("handshake"):
            return
        self._fanout({
            "event": "handshake",
            "title": f"Handshake captured: {ssid}",
            "body": f"BSSID {bssid}",
            "priority": "low",
            "tags": "lock",
            "data": {"ssid": ssid, "bssid": bssid},
        })

    def password_cracked(self, ssid: str, bssid: str, engine: str, seconds: int):
        if not self._allowed("crack"):
            return
        self._fanout({
            "event": "crack",
            "title": f"PSK cracked: {ssid}",
            "body": f"BSSID {bssid} — {engine} in {seconds}s",
            "priority": "high",
            "tags": "key,fire",
            "data": {"ssid": ssid, "bssid": bssid, "engine": engine,
                     "seconds": seconds},
        })

    def vulnerability_found(self, ssid: str, host: str, severity: str,
                            vuln_type: str, description: str = ""):
        if not self._allowed("vulnerability"):
            return
        sev = (severity or "").lower()
        prio = "urgent" if sev == "critical" else (
            "high" if sev == "high" else "normal"
        )
        body = f"{host} — {vuln_type}"
        if description:
            body += f"\n{description[:200]}"
        self._fanout({
            "event": "vulnerability",
            "title": f"[{sev or 'vuln'}] {ssid}",
            "body": body,
            "priority": prio,
            "tags": "warning" if sev in ("critical", "high") else "mag",
            "data": {"ssid": ssid, "host": host, "severity": sev,
                     "vuln_type": vuln_type, "description": description},
        })

    def scan_completed(self, ssid: str, hosts: int, vulns: int):
        if not self._allowed("scan"):
            return
        self._fanout({
            "event": "scan",
            "title": f"Scan complete: {ssid}",
            "body": f"{hosts} host{'s' if hosts != 1 else ''}, "
                    f"{vulns} vuln{'s' if vulns != 1 else ''}",
            "priority": "normal",
            "tags": "white_check_mark",
            "data": {"ssid": ssid, "hosts": hosts, "vulnerabilities": vulns},
        })

    def send_test(self, source: str = "manual") -> bool:
        """Fire a one-shot test event through every enabled backend.
        Returns True if at least one backend was active to receive it.
        Bypasses notify_on so the test always goes through."""
        if not self.backends:
            return False
        self._fanout_unfiltered({
            "event": "test",
            "title": "PenDonn notification test",
            "body": f"Test fired from {source}. If you see this, the channel works.",
            "priority": "normal",
            "tags": "test_tube",
            "data": {"source": source},
        })
        return True

    # ---------- internals ----------

    def _allowed(self, kind: str) -> bool:
        if not self.backends:
            return False
        return self.notify_on.get(kind, True) is not False

    def _fanout(self, event: Dict):
        for b in self.backends:
            b.enqueue(event)

    def _fanout_unfiltered(self, event: Dict):
        # Skip notify_on filter — used by test button so the operator
        # can verify a backend even if a specific event type is muted.
        for b in self.backends:
            b.enqueue(event)
