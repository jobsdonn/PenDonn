"""Cookie-session authentication for the new web UI.

Reuses the same `web.basic_auth.password_hash` from config.json.local that
Phase 1E set up for the Flask UI — no new credential store, no separate
operator workflow. Login form posts username/password; on success we set
a signed session cookie via Starlette's SessionMiddleware.

Routes can require auth via the `current_user` dependency; routes that
don't request it stay anonymous (the captive-portal endpoints in
particular MUST stay anonymous so evil-twin victims can hit them).
"""

import logging
import secrets
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request, status
from werkzeug.security import check_password_hash

logger = logging.getLogger(__name__)

# Session keys
_SK_USERNAME = "u"
_SK_LOGGED_IN = "l"


class AuthSettings:
    """Resolved auth settings derived once at app start from the config dict."""

    def __init__(self, web_config: Dict[str, Any]):
        ba = (web_config.get("basic_auth") or {})
        self.enabled: bool = bool(ba.get("enabled", False))
        self.username: str = ba.get("username") or ""
        self.password_hash: str = ba.get("password_hash") or ""
        self.password_plaintext: str = ba.get("password") or ""

        if self.enabled and not (self.password_hash or self.password_plaintext):
            logger.warning(
                "web.basic_auth.enabled=true but no password_hash or password "
                "is set — login will reject every attempt. Generate a hash via "
                "'python web/app.py --hash-password' and put it in "
                "config.json.local under web.basic_auth.password_hash."
            )

    def verify_credentials(self, username: str, password: str) -> bool:
        """Constant-time-ish credential check. Returns True iff valid."""
        if not self.enabled:
            return True  # auth disabled = everyone is "logged in"
        if not username or username != self.username:
            return False
        if self.password_hash:
            try:
                return check_password_hash(self.password_hash, password)
            except (ValueError, TypeError) as e:
                logger.error("bad password_hash format: %s", e)
                return False
        if self.password_plaintext:
            return secrets.compare_digest(password, self.password_plaintext)
        return False


def is_logged_in(request: Request) -> bool:
    """True iff there is a valid session for this request."""
    auth: AuthSettings = request.app.state.auth
    if not auth.enabled:
        return True
    return bool(request.session.get(_SK_LOGGED_IN))


def current_username(request: Request) -> Optional[str]:
    """Return the logged-in username, or None."""
    if not is_logged_in(request):
        return None
    auth: AuthSettings = request.app.state.auth
    return request.session.get(_SK_USERNAME) if auth.enabled else "anonymous"


def login_session(request: Request, username: str) -> None:
    request.session[_SK_LOGGED_IN] = True
    request.session[_SK_USERNAME] = username


def logout_session(request: Request) -> None:
    request.session.clear()


def require_login(request: Request) -> str:
    """FastAPI dependency: redirects to /login on miss, returns username on hit.

    Use as `username: str = Depends(require_login)` on any route that
    should be auth-gated. The HTTPException carries a 303 redirect that
    HTMX understands (HX-Redirect header set in the global handler).
    """
    if is_logged_in(request):
        return current_username(request) or "anonymous"
    # Detect HTMX request and signal a client-side redirect so partials
    # don't get replaced with a login form fragment.
    if request.headers.get("HX-Request") == "true":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="login required",
            headers={"HX-Redirect": "/login"},
        )
    raise HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        detail="login required",
        headers={"Location": f"/login?next={request.url.path}"},
    )
