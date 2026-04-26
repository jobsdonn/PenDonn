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
