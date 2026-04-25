"""PenDonn modern web UI — FastAPI app.

Run locally:
    PYTHONPATH=. uvicorn webui.app:app --port 8081 --reload

Auth, port, and bind host are read from config.json (+ .local overlay)
via core.config_loader. The legacy Flask UI on 8080 is unaffected.
"""

import logging
import os
import sys
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# Make `core.*` importable when running uvicorn from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_loader import ensure_persistent_secret, load_config
from core.database import Database

from webui import auth as auth_mod
from webui.routes import dashboard as dashboard_routes
from webui.routes import handshakes as handshakes_routes
from webui.routes import networks as networks_routes

logger = logging.getLogger("pendonn.webui")

# ---------------------------------------------------------------------------
# Config + app construction
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(REPO_ROOT, "config", "config.json")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

config = load_config(CONFIG_PATH)
secret_key = ensure_persistent_secret(config, CONFIG_PATH)

app = FastAPI(
    title="PenDonn",
    description="Authorized-pentest WiFi automation — modern UI",
    version=config.get("system", {}).get("version", "0.0.0"),
    docs_url="/api/docs",
    redoc_url=None,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=secret_key,
    session_cookie="pendonn_session",
    https_only=False,    # operator may run over plain HTTP on the LAN
    same_site="lax",
    max_age=60 * 60 * 12,  # 12h — matches typical pentest session length
)

app.state.config = config
app.state.config_path = CONFIG_PATH
app.state.auth = auth_mod.AuthSettings(config.get("web", {}) or {})
app.state.db = Database(config["database"]["path"])

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["app_version"] = app.version
templates.env.globals["auth_enabled"] = app.state.auth.enabled
app.state.templates = templates

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ---------------------------------------------------------------------------
# Health & login
# ---------------------------------------------------------------------------

@app.get("/health", include_in_schema=False)
def health() -> Dict[str, str]:
    """Liveness probe. Anonymous so monitoring can hit it."""
    return {"status": "ok", "version": app.version}


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request, next: str = "/", error: Optional[str] = None):
    if auth_mod.is_logged_in(request):
        return RedirectResponse(next or "/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "next": next, "error": error,
         "auth_enabled": app.state.auth.enabled},
    )


@app.post("/login", include_in_schema=False)
def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
):
    if not app.state.auth.verify_credentials(username, password):
        # Don't leak whether the username or password was wrong.
        return RedirectResponse(
            f"/login?next={next}&error=invalid",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    auth_mod.login_session(request, username)
    return RedirectResponse(next or "/", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/logout", include_in_schema=False)
def logout(request: Request):
    auth_mod.logout_session(request)
    return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(dashboard_routes.router)
app.include_router(networks_routes.router)
app.include_router(handshakes_routes.router)
