"""Handshakes + cracked passwords pages."""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from webui.auth import require_login

router = APIRouter()


def _annotate_handshake(h: dict) -> dict:
    """Compute display-time fields the template wants without reaching into the DB."""
    out = dict(h)
    fp = h.get("file_path")
    if fp:
        try:
            out["file_size_bytes"] = os.path.getsize(fp)
            out["file_exists"] = True
        except OSError:
            out["file_size_bytes"] = 0
            out["file_exists"] = False
    else:
        out["file_size_bytes"] = 0
        out["file_exists"] = False
    return out


@router.get("/handshakes")
def handshakes_page(
    request: Request,
    username: str = Depends(require_login),
    status: str = "all",
):
    db = request.app.state.db
    only_status = None if status == "all" else status
    handshakes = [_annotate_handshake(h) for h in db.get_all_handshakes(only_status)]
    return request.app.state.templates.TemplateResponse(
        "handshakes.html",
        {
            "request": request,
            "username": username,
            "active_nav": "handshakes",
            "handshakes": handshakes,
            "status": status,
        },
    )


@router.get("/partials/handshakes")
def handshakes_partial(
    request: Request,
    username: str = Depends(require_login),
    status: str = "all",
):
    db = request.app.state.db
    only_status = None if status == "all" else status
    handshakes = [_annotate_handshake(h) for h in db.get_all_handshakes(only_status)]
    return request.app.state.templates.TemplateResponse(
        "partials/handshakes_table.html",
        {"request": request, "handshakes": handshakes, "status": status},
    )


@router.get("/passwords")
def passwords_page(request: Request, username: str = Depends(require_login)):
    db = request.app.state.db
    return request.app.state.templates.TemplateResponse(
        "passwords.html",
        {
            "request": request,
            "username": username,
            "active_nav": "passwords",
            "passwords": db.get_cracked_passwords(),
        },
    )


@router.get("/partials/passwords")
def passwords_partial(request: Request, username: str = Depends(require_login)):
    db = request.app.state.db
    return request.app.state.templates.TemplateResponse(
        "partials/passwords_table.html",
        {"request": request, "passwords": db.get_cracked_passwords()},
    )
