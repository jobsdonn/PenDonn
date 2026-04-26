"""Settings page + allowlist editor.

Read-most-write-some: shows every config section, but only the targeting
allowlist + the strict-mode flag are editable from the UI (the rest are
either secrets that belong in config.json.local managed via CLI, or
operational knobs you shouldn't be hot-reloading from a web button on a Pi).

Allowlist edits are written to config.json.local — never to the tracked
config.json — so per-deployment SSIDs don't accumulate in git.

URLs: the new spelling is /partials/allowlist/{add,remove}; the old
/partials/whitelist/{add,remove} are kept as aliases so a Pi running an
older version of the UI doesn't break for an in-flight htmx request mid-deploy.
"""

import copy
import json
import os
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from core.config_loader import (
    PLACEHOLDER_SECRETS,
    _atomic_write_local,
    local_overlay_path,
)
from webui.auth import require_login

router = APIRouter()


# Keys that should be redacted in the config viewer. Match by full dotted
# key (e.g. "web.secret_key") OR by the leaf name (e.g. "password_hash").
_REDACT_LEAFS = {"secret_key", "password", "password_hash"}


def _redact(d: Any, key_path: str = "") -> Any:
    """Return a deep copy of `d` with any sensitive leaf values replaced."""
    if isinstance(d, dict):
        out = {}
        for k, v in d.items():
            new_path = f"{key_path}.{k}" if key_path else k
            if k in _REDACT_LEAFS:
                if v and v not in PLACEHOLDER_SECRETS:
                    out[k] = "<redacted>"
                else:
                    out[k] = ""
            else:
                out[k] = _redact(v, new_path)
        return out
    if isinstance(d, list):
        return [_redact(v, key_path) for v in d]
    return d


def _safety_status(config: Dict[str, Any]) -> Dict[str, Any]:
    """Plain summary of the safety section for the template to render."""
    s = config.get("safety", {}) or {}
    auth = (config.get("web", {}) or {}).get("basic_auth", {}) or {}
    web_host = (config.get("web", {}) or {}).get("host", "")
    return {
        "ssh_guard_enabled": bool(s.get("enabled", True)),
        "armed_override": bool(s.get("armed_override", False)),
        "block_management_monitor": bool(s.get("block_monitor_on_management", True)),
        "block_ssh_iface_monitor": bool(s.get("block_monitor_on_ssh_iface", True)),
        "block_management_supplicant_kill": bool(s.get("block_kill_management_supplicant", True)),
        "auth_enabled": bool(auth.get("enabled", False)),
        "loopback_only": web_host in ("127.0.0.1", "localhost", "::1"),
    }


@router.get("/settings")
def settings_page(request: Request, username: str = Depends(require_login)):
    cfg = request.app.state.config
    al = cfg.get("allowlist", {}) or {}
    ctx = {
        "username": username,
        "active_nav": "settings",
        "config_redacted": _redact(cfg),
        "config_json": json.dumps(_redact(cfg), indent=2, sort_keys=True),
        "allowlist": list(al.get("ssids") or []),
        "allowlist_strict": bool(al.get("strict", True)),
        "safety": _safety_status(cfg),
        "config_path": request.app.state.config_path,
        "overlay_path": local_overlay_path(request.app.state.config_path),
        "overlay_exists": os.path.isfile(local_overlay_path(request.app.state.config_path)),
    }
    # Scope partial needs its own context keys (active, confirmed, missing_ssids, ...)
    ctx.update(_scope_status(request))
    # Notifications partial expects ntfy/webhook dicts.
    ctx.update(_notifications_status(request))
    return request.app.state.templates.TemplateResponse(
        request, "settings.html", ctx,
    )


@router.get("/partials/allowlist")
@router.get("/partials/whitelist")  # legacy alias
def allowlist_partial(request: Request, username: str = Depends(require_login)):
    cfg = request.app.state.config
    al = cfg.get("allowlist", {}) or {}
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/allowlist.html",
        {
                       "allowlist": list(al.get("ssids") or []),
            "allowlist_strict": bool(al.get("strict", True)),},
    )


# Conservative SSID validator: match what hostapd / iwconfig accept and
# what wifi_scanner targeting actually compares against. Up to 32 bytes,
# no NUL/CR/LF, allow any other UTF-8 byte.
_SSID_RE = re.compile(r"^[^\x00\r\n]{1,32}$")


def _normalize_ssid(raw: str) -> str:
    s = (raw or "").strip()
    if not _SSID_RE.match(s):
        raise HTTPException(status_code=400, detail="SSID must be 1-32 chars, no newlines or NULs")
    return s


def _persist_allowlist(
    request: Request,
    ssids: list,
    strict: Optional[bool] = None,
) -> None:
    """Write allowlist to config.json.local without clobbering other overlay keys.

    Always writes under the modern `allowlist` key. The legacy `whitelist`
    key is removed from the overlay if present (config_loader's normalizer
    handles back-compat for any deployed config.json files).
    """
    overlay_path = local_overlay_path(request.app.state.config_path)
    overlay: Dict[str, Any] = {}
    if os.path.isfile(overlay_path):
        try:
            with open(overlay_path, "r", encoding="utf-8") as f:
                overlay = json.load(f)
        except (OSError, json.JSONDecodeError):
            overlay = {}
    al_overlay = overlay.setdefault("allowlist", {})
    al_overlay["ssids"] = ssids
    if strict is not None:
        al_overlay["strict"] = bool(strict)
    overlay.pop("whitelist", None)
    _atomic_write_local(overlay_path, overlay)

    # Reflect in the live in-memory config so the next page render sees it.
    cfg = request.app.state.config
    al = cfg.setdefault("allowlist", {})
    al["ssids"] = ssids
    if strict is not None:
        al["strict"] = bool(strict)
    # Mirror to legacy `whitelist.ssids` per the normalizer's contract.
    cfg.setdefault("whitelist", {})["ssids"] = list(ssids)


def _current_allowlist(cfg: Dict[str, Any]) -> list:
    return list((cfg.get("allowlist", {}) or {}).get("ssids") or [])


@router.post("/partials/allowlist/add")
@router.post("/partials/whitelist/add")  # legacy alias
def allowlist_add(
    request: Request,
    ssid: str = Form(""),
    username: str = Depends(require_login),
):
    s = _normalize_ssid(ssid)
    cfg = request.app.state.config
    current = _current_allowlist(cfg)
    if s not in current:
        current.append(s)
        _persist_allowlist(request, current)
        request.app.state.db.add_audit_log(
            action="allowlist.add",
            actor=username,
            target=s,
            source_ip=_client_ip(request),
        )
    al = cfg.get("allowlist", {}) or {}
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/allowlist.html",
        {"request": request, "allowlist": current,
         "allowlist_strict": bool(al.get("strict", True)),},
    )


@router.post("/partials/allowlist/remove")
@router.post("/partials/whitelist/remove")  # legacy alias
def allowlist_remove(
    request: Request,
    ssid: str = Form(""),
    username: str = Depends(require_login),
):
    s = (ssid or "").strip()
    if not s:
        raise HTTPException(status_code=400, detail="ssid required")
    cfg = request.app.state.config
    current = _current_allowlist(cfg)
    if s in current:
        current.remove(s)
        _persist_allowlist(request, current)
        request.app.state.db.add_audit_log(
            action="allowlist.remove",
            actor=username,
            target=s,
            source_ip=_client_ip(request),
        )
    al = cfg.get("allowlist", {}) or {}
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/allowlist.html",
        {"request": request, "allowlist": current,
         "allowlist_strict": bool(al.get("strict", True)),},
    )


@router.post("/partials/allowlist/strict")
def allowlist_strict_toggle(
    request: Request,
    strict: str = Form(""),
    username: str = Depends(require_login),
):
    """Flip the strict flag.

    strict=true  → only attack listed SSIDs (safe default).
    strict=false → attack every visible SSID (DANGEROUS — refuses to start
                   without safety.armed_override; we still allow flipping the
                   bit here so operators can stage a config that preflight
                   will then validate).
    """
    new_strict = strict.lower() in ("1", "true", "on", "yes")
    cfg = request.app.state.config
    current = _current_allowlist(cfg)
    old_strict = bool((cfg.get("allowlist", {}) or {}).get("strict", True))
    _persist_allowlist(request, current, strict=new_strict)
    if old_strict != new_strict:
        request.app.state.db.add_audit_log(
            action="allowlist.strict_toggle",
            actor=username,
            target=("on" if new_strict else "off"),
            details={"old": old_strict, "new": new_strict},
            source_ip=_client_ip(request),
        )
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/allowlist.html",
        {"request": request, "allowlist": current, "allowlist_strict": new_strict,},
    )


# ---------------------------------------------------------------------------
# Pre-flight scope authorization
#
# A confirmed scope is a human-stamped receipt: "I, the operator, have
# written authorization to attack these SSIDs." It sits between the
# allowlist (which says *what* would be attacked) and the daemon (which
# refuses to attack until the scope is confirmed).
#
# Re-confirm whenever the allowlist gains a new SSID; shrinking the
# allowlist does NOT invalidate existing confirmation.
# ---------------------------------------------------------------------------


def _scope_status(request: Request) -> Dict[str, Any]:
    """Build the partial's view of the current scope-confirmation state."""
    db = request.app.state.db
    cfg = request.app.state.config
    allowlist = _current_allowlist(cfg)
    active = db.get_active_scope()
    confirmed, missing = db.is_scope_confirmed_for(allowlist)
    return {
        "allowlist": allowlist,
        "allowlist_empty": not allowlist,
        "active": active,
        "confirmed": confirmed,
        "missing_ssids": missing,
    }


@router.get("/partials/scope")
def scope_partial(request: Request, username: str = Depends(require_login)):
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/scope.html",
        _scope_status(request),
    )


def _client_ip(request: Request) -> Optional[str]:
    """WebUI client IP for audit log. None if not available (test contexts)."""
    return request.client.host if request.client else None


@router.post("/partials/scope/confirm")
def scope_confirm(
    request: Request,
    note: str = Form(""),
    username: str = Depends(require_login),
):
    cfg = request.app.state.config
    allowlist = _current_allowlist(cfg)
    if not allowlist:
        # Nothing to confirm — but don't 4xx; just re-render with empty state.
        return request.app.state.templates.TemplateResponse(
            request, "partials/scope.html", _scope_status(request),
        )
    db = request.app.state.db
    db.confirm_scope(
        ssids=allowlist,
        confirmed_by=username,
        note=(note or None),
    )
    db.add_audit_log(
        action="scope.confirm",
        actor=username,
        target=",".join(allowlist),
        details={"ssids": allowlist, "note": note or None},
        source_ip=_client_ip(request),
    )
    return request.app.state.templates.TemplateResponse(
        request, "partials/scope.html", _scope_status(request),
    )


@router.post("/partials/scope/revoke")
def scope_revoke(request: Request, username: str = Depends(require_login)):
    db = request.app.state.db
    revoked = db.revoke_scope(revoked_by=username)
    if revoked:
        db.add_audit_log(
            action="scope.revoke",
            actor=username,
            source_ip=_client_ip(request),
        )
    return request.app.state.templates.TemplateResponse(
        request, "partials/scope.html", _scope_status(request),
    )


# ---------------------------------------------------------------------------
# Notifications config (ntfy + webhook)
# ---------------------------------------------------------------------------


def _notifications_status(request: Request) -> Dict[str, Any]:
    """Pull current notifications config for the partial. Reads from the
    live merged config (config.json + config.json.local overlay)."""
    cfg = request.app.state.config
    notif = (cfg.get("notifications") or {})
    ntfy = notif.get("ntfy", {}) or {}
    webhook = notif.get("webhook", {}) or {}
    return {
        "ntfy": {
            "enabled": bool(ntfy.get("enabled", False)),
            "server": ntfy.get("server", "https://ntfy.sh"),
            "topic": ntfy.get("topic", ""),
            "token_set": bool(ntfy.get("token")),
            "notify_on": ntfy.get("notify_on", {}) or {},
        },
        "webhook": {
            "enabled": bool(webhook.get("enabled", False)),
            "url": webhook.get("url", ""),
            "format": webhook.get("format", "json"),
            "headers_count": len((webhook.get("headers") or {})),
            "notify_on": webhook.get("notify_on", {}) or {},
        },
    }


def _persist_notifications(request: Request, ntfy: Dict, webhook: Dict) -> None:
    """Write notifications.{ntfy,webhook} to config.json.local without
    clobbering other overlay keys. Mirrors to live in-memory config."""
    overlay_path = local_overlay_path(request.app.state.config_path)
    overlay: Dict[str, Any] = {}
    if os.path.isfile(overlay_path):
        try:
            with open(overlay_path, "r", encoding="utf-8") as f:
                overlay = json.load(f)
        except (OSError, json.JSONDecodeError):
            overlay = {}
    notif = overlay.setdefault("notifications", {})
    notif["ntfy"] = ntfy
    notif["webhook"] = webhook
    _atomic_write_local(overlay_path, overlay)

    cfg = request.app.state.config
    live_notif = cfg.setdefault("notifications", {})
    live_notif["ntfy"] = ntfy
    live_notif["webhook"] = webhook


_NTFY_TOPIC_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
_HTTPS_URL_RE = re.compile(r"^https?://[^\s]+$")


@router.get("/partials/notifications")
def notifications_partial(request: Request, username: str = Depends(require_login)):
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/notifications.html",
        _notifications_status(request),
    )


@router.post("/partials/notifications/save")
def notifications_save(
    request: Request,
    # ntfy fields
    ntfy_enabled: str = Form(""),
    ntfy_server: str = Form("https://ntfy.sh"),
    ntfy_topic: str = Form(""),
    ntfy_token: str = Form(""),
    ntfy_on_handshake: str = Form(""),
    ntfy_on_crack: str = Form(""),
    ntfy_on_vulnerability: str = Form(""),
    ntfy_on_scan: str = Form(""),
    # webhook fields
    wh_enabled: str = Form(""),
    wh_url: str = Form(""),
    wh_format: str = Form("json"),
    wh_headers: str = Form(""),  # JSON string {"Header": "value"}
    wh_on_handshake: str = Form(""),
    wh_on_crack: str = Form(""),
    wh_on_vulnerability: str = Form(""),
    wh_on_scan: str = Form(""),
    username: str = Depends(require_login),
):
    """Save notifications config from the settings UI. Validates topic
    and URL formats; refuses to enable a backend that's misconfigured."""
    cfg = request.app.state.config
    cur = cfg.get("notifications") or {}

    def _on(v: str) -> bool:
        return v.lower() in ("1", "true", "on", "yes")

    # ----- ntfy -----
    ntfy_topic = ntfy_topic.strip()
    ntfy_server = (ntfy_server or "").strip() or "https://ntfy.sh"
    ntfy_token_new = ntfy_token.strip()
    if ntfy_topic and not _NTFY_TOPIC_RE.match(ntfy_topic):
        raise HTTPException(
            status_code=400,
            detail="ntfy topic must be 6-64 chars, alphanumeric + - / _",
        )
    if not _HTTPS_URL_RE.match(ntfy_server):
        raise HTTPException(status_code=400, detail="ntfy server must be http(s):// URL")
    # Empty token form value means "keep existing" (so the operator
    # doesn't have to re-enter it on every save).
    keep_token = (cur.get("ntfy", {}) or {}).get("token", "")
    ntfy_block = {
        "enabled": _on(ntfy_enabled),
        "server": ntfy_server,
        "topic": ntfy_topic,
        "token": ntfy_token_new if ntfy_token_new else keep_token,
        "notify_on": {
            "handshake": _on(ntfy_on_handshake),
            "crack": _on(ntfy_on_crack),
            "vulnerability": _on(ntfy_on_vulnerability),
            "scan": _on(ntfy_on_scan),
        },
    }
    if ntfy_block["enabled"] and not ntfy_block["topic"]:
        raise HTTPException(status_code=400, detail="ntfy enabled but topic empty")

    # ----- webhook -----
    wh_url_clean = (wh_url or "").strip()
    if wh_url_clean and not _HTTPS_URL_RE.match(wh_url_clean):
        raise HTTPException(status_code=400, detail="webhook URL must be http(s)://")
    wh_headers_obj: Dict[str, str] = {}
    if wh_headers and wh_headers.strip():
        try:
            parsed = json.loads(wh_headers)
            if not isinstance(parsed, dict):
                raise ValueError("not a dict")
            wh_headers_obj = {str(k): str(v) for k, v in parsed.items()}
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"webhook headers must be a JSON object: {e}",
            )
    valid_formats = ("json", "discord", "slack", "teams")
    wh_format_clean = (wh_format or "json").lower()
    if wh_format_clean not in valid_formats:
        raise HTTPException(
            status_code=400,
            detail=f"webhook format must be one of {valid_formats}",
        )
    wh_block = {
        "enabled": _on(wh_enabled),
        "url": wh_url_clean,
        "format": wh_format_clean,
        "headers": wh_headers_obj,
        "notify_on": {
            "handshake": _on(wh_on_handshake),
            "crack": _on(wh_on_crack),
            "vulnerability": _on(wh_on_vulnerability),
            "scan": _on(wh_on_scan),
        },
    }
    if wh_block["enabled"] and not wh_block["url"]:
        raise HTTPException(status_code=400, detail="webhook enabled but url empty")

    _persist_notifications(request, ntfy_block, wh_block)

    request.app.state.db.add_audit_log(
        action="notifications.update",
        actor=username,
        details={
            "ntfy_enabled": ntfy_block["enabled"],
            "webhook_enabled": wh_block["enabled"],
        },
        source_ip=_client_ip(request),
    )

    return request.app.state.templates.TemplateResponse(
        request,
        "partials/notifications.html",
        _notifications_status(request),
    )


@router.post("/partials/notifications/test")
def notifications_test(request: Request, username: str = Depends(require_login)):
    """Fire a one-shot test event through every enabled backend.

    Builds a fresh Notifier from the live (saved) config so the operator
    sees the effect of their last save without restarting the daemon —
    the daemon's long-lived Notifier won't pick up changes until restart,
    but for the test we instantiate a temporary one.
    """
    from core.notifications import Notifier  # local import keeps webui import light

    cfg = request.app.state.config
    n = Notifier(cfg)
    sent = n.send_test(source=f"webui:{username}")
    n.stop()

    request.app.state.db.add_audit_log(
        action="notifications.test",
        actor=username,
        details={"any_backend_active": sent},
        source_ip=_client_ip(request),
    )

    msg = "Test fired" if sent else "No backend enabled — nothing sent"
    ctx = _notifications_status(request)
    ctx["test_message"] = msg
    return request.app.state.templates.TemplateResponse(
        request, "partials/notifications.html", ctx,
    )
