"""Settings page + whitelist editor.

Read-most-write-some: shows every config section, but only the SSID
whitelist is editable from the UI (the rest are either secrets that
belong in config.json.local managed via CLI, or operational knobs you
shouldn't be hot-reloading from a web button on a Pi).

Whitelist edits are written to config.json.local — never to the tracked
config.json — so per-deployment SSIDs don't accumulate in git.
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
    return request.app.state.templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "username": username,
            "active_nav": "settings",
            "config_redacted": _redact(cfg),
            "config_json": json.dumps(_redact(cfg), indent=2, sort_keys=True),
            "whitelist": list((cfg.get("whitelist", {}) or {}).get("ssids", []) or []),
            "safety": _safety_status(cfg),
            "config_path": request.app.state.config_path,
            "overlay_path": local_overlay_path(request.app.state.config_path),
            "overlay_exists": os.path.isfile(local_overlay_path(request.app.state.config_path)),
        },
    )


@router.get("/partials/whitelist")
def whitelist_partial(request: Request, username: str = Depends(require_login)):
    cfg = request.app.state.config
    return request.app.state.templates.TemplateResponse(
        "partials/whitelist.html",
        {
            "request": request,
            "whitelist": list((cfg.get("whitelist", {}) or {}).get("ssids", []) or []),
        },
    )


# Conservative SSID validator: match what hostapd / iwconfig accept and
# what wifi_scanner.whitelist actually compares against. Up to 32 bytes,
# no NUL/CR/LF, allow any other UTF-8 byte.
_SSID_RE = re.compile(r"^[^\x00\r\n]{1,32}$")


def _normalize_ssid(raw: str) -> str:
    s = (raw or "").strip()
    if not _SSID_RE.match(s):
        raise HTTPException(status_code=400, detail="SSID must be 1-32 chars, no newlines or NULs")
    return s


def _persist_whitelist(request: Request, ssids: list) -> None:
    """Write the SSID list to config.json.local without clobbering other overlay keys."""
    overlay_path = local_overlay_path(request.app.state.config_path)
    overlay: Dict[str, Any] = {}
    if os.path.isfile(overlay_path):
        try:
            with open(overlay_path, "r", encoding="utf-8") as f:
                overlay = json.load(f)
        except (OSError, json.JSONDecodeError):
            overlay = {}
    overlay.setdefault("whitelist", {})["ssids"] = ssids
    _atomic_write_local(overlay_path, overlay)
    # Reflect in the live in-memory config so the next page render sees it.
    cfg = request.app.state.config
    cfg.setdefault("whitelist", {})["ssids"] = ssids


@router.post("/partials/whitelist/add")
def whitelist_add(
    request: Request,
    ssid: str = Form(""),
    username: str = Depends(require_login),
):
    s = _normalize_ssid(ssid)
    cfg = request.app.state.config
    current = list((cfg.get("whitelist", {}) or {}).get("ssids", []) or [])
    if s not in current:
        current.append(s)
        _persist_whitelist(request, current)
    return request.app.state.templates.TemplateResponse(
        "partials/whitelist.html",
        {"request": request, "whitelist": current},
    )


@router.post("/partials/whitelist/remove")
def whitelist_remove(
    request: Request,
    ssid: str = Form(""),
    username: str = Depends(require_login),
):
    s = (ssid or "").strip()
    if not s:
        raise HTTPException(status_code=400, detail="ssid required")
    cfg = request.app.state.config
    current = list((cfg.get("whitelist", {}) or {}).get("ssids", []) or [])
    if s in current:
        current.remove(s)
        _persist_whitelist(request, current)
    return request.app.state.templates.TemplateResponse(
        "partials/whitelist.html",
        {"request": request, "whitelist": current},
    )
