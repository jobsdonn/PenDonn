"""Dashboard route + KPI partials.

The dashboard page is a thin shell that hosts HTMX partials that
self-refresh every few seconds. Each partial is a tiny route returning
just the fragment so the rest of the page doesn't repaint.
"""

from fastapi import APIRouter, Depends, Request

from webui.auth import require_login

router = APIRouter()


@router.get("/")
def dashboard(request: Request, username: str = Depends(require_login)):
    """Main landing page. Renders the shell; partials are loaded via HTMX."""
    db = request.app.state.db
    stats = db.get_statistics()
    cfg = request.app.state.config
    allowlist = list((cfg.get("allowlist", {}) or {}).get("ssids") or [])
    confirmed, missing = db.is_scope_confirmed_for(allowlist)
    return request.app.state.templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "username": username,
            "active_nav": "dashboard",
            "stats": stats,
            "scope_confirmed": confirmed,
            "scope_missing_ssids": missing,
            "scope_has_targets": bool(allowlist),
        },
    )


@router.get("/partials/stats")
def stats_partial(request: Request, username: str = Depends(require_login)):
    """KPI tiles, polled by the dashboard every 5 seconds via HTMX."""
    db = request.app.state.db
    stats = db.get_statistics()
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/stats.html",
        {"request": request, "stats": stats,},
    )
