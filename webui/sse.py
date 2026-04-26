"""Server-Sent Events bus for live UI updates.

The WebUI used to poll partial endpoints from the browser every 5-10s.
That worked but had two failure modes:

  1. State reset — every poll discarded any in-progress UI state (open
     accordions, expanded rows). The Phase-3 fix used a `data-expanded`
     attribute to pause polling, but only on the scans page.
  2. Wasted work when nothing changed — the daemon emits at most a
     few events per minute under normal conditions, but the browser
     polled every page on every interval regardless.

This module replaces those polls with a single SSE stream. The server
polls the database internally (cheap, in-process), computes a digest
per logical view (stats, scans, handshakes, networks, passwords,
vulnerabilities, scope), and only emits an event when the digest
changes. Browsers subscribe via EventSource; HTMX listens for the
named event and re-fetches the corresponding partial only when it
actually has new content.

The daemon and the WebUI are separate processes that share a SQLite
file. We don't need IPC — we just notice the changes when we look.
"""

import asyncio
import hashlib
import json
import logging
from typing import AsyncGenerator, Callable, Dict

logger = logging.getLogger("pendonn.webui.sse")

# How often to re-snapshot the DB. 1.5s feels live without hammering
# SQLite. The daemon writes maybe a handful of rows per minute under
# load, so most ticks emit nothing.
_POLL_INTERVAL = 1.5

# Heartbeat interval. EventSource auto-reconnects, but some proxies kill
# idle connections after ~30s; a comment line every 15s keeps it warm.
_HEARTBEAT = 15.0


def _digest(payload) -> str:
    """Stable hash for arbitrary JSON-able payloads. We use it to detect
    "anything changed in this view since last tick"; the actual content
    is then re-fetched by HTMX from the partial endpoint."""
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.blake2b(blob, digest_size=16).hexdigest()


def _stats_digest(db) -> str:
    return _digest(db.get_statistics())


def _scans_digest(db) -> str:
    rows = db.get_scans()
    # Only the fields the UI actually shows. Avoids re-emitting on every
    # nmap progress write to results JSON.
    return _digest([
        (r.get("id"), r.get("status"), r.get("vulnerabilities_found"),
         r.get("ssid"), r.get("scan_type"), r.get("end_time"))
        for r in rows
    ])


def _handshakes_digest(db) -> str:
    rows = db.get_all_handshakes() if hasattr(db, "get_all_handshakes") else []
    return _digest([
        (r.get("id"), r.get("status"), r.get("bssid"), r.get("ssid"),
         r.get("quality"))
        for r in rows
    ])


def _networks_digest(db) -> str:
    rows = db.get_networks() if hasattr(db, "get_networks") else []
    return _digest([
        (r.get("id"), r.get("bssid"), r.get("ssid"), r.get("encryption"),
         r.get("signal_strength"), r.get("is_whitelisted"))
        for r in rows
    ])


def _passwords_digest(db) -> str:
    rows = db.get_cracked_passwords()
    return _digest([(r.get("id"), r.get("ssid"), r.get("bssid")) for r in rows])


def _vulns_digest(db) -> str:
    rows = db.get_vulnerabilities()
    return _digest([
        (r.get("id"), r.get("severity"), r.get("host"), r.get("port"))
        for r in rows
    ])


def _scope_digest(db) -> str:
    active = db.get_active_scope()
    if not active:
        return "none"
    return _digest((active.get("id"), active.get("ssids"), active.get("revoked")))


# Ordered map: event name -> digest function. Order is mostly for log
# readability; the bus emits whichever changes.
_EVENT_SOURCES: Dict[str, Callable] = {
    "stats": _stats_digest,
    "scans": _scans_digest,
    "handshakes": _handshakes_digest,
    "networks": _networks_digest,
    "passwords": _passwords_digest,
    "vulns": _vulns_digest,
    "scope": _scope_digest,
}


async def event_stream(request, db) -> AsyncGenerator[str, None]:
    """Yield SSE-framed events as DB state changes.

    Caller is responsible for wrapping in StreamingResponse with
    media_type='text/event-stream' and the usual no-cache headers.
    """
    # Initial digest so we don't fire spurious events on connect.
    digests: Dict[str, str] = {}
    for name, fn in _EVENT_SOURCES.items():
        try:
            digests[name] = fn(db)
        except Exception as e:
            logger.debug(f"Initial {name} digest failed: {e}")
            digests[name] = ""

    # Tell the client we're connected. Useful for debugging in DevTools.
    yield "event: connected\ndata: ok\n\n"

    last_heartbeat = asyncio.get_event_loop().time()
    while True:
        if await request.is_disconnected():
            return

        await asyncio.sleep(_POLL_INTERVAL)

        for name, fn in _EVENT_SOURCES.items():
            try:
                new_digest = fn(db)
            except Exception as e:
                logger.debug(f"{name} digest error: {e}")
                continue
            if new_digest != digests.get(name):
                digests[name] = new_digest
                # Event payload is the digest itself — small, cacheable,
                # not actually rendered (HTMX just uses the trigger).
                yield f"event: {name}\ndata: {new_digest}\n\n"

        now = asyncio.get_event_loop().time()
        if now - last_heartbeat >= _HEARTBEAT:
            # SSE comment line — keeps proxies + browsers happy without
            # firing any client-side handler.
            yield ": heartbeat\n\n"
            last_heartbeat = now
