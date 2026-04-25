"""Networks page — discovered WiFi APs.

Server-side sort + search + filter via query params; HTMX swaps the
table partial in place. Whitelist toggle is a single-row HTMX swap so
the rest of the table doesn't repaint.
"""

import re
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request

from webui.auth import require_login

router = APIRouter()

# Allowed sort fields → SQLite column. Whitelist guards against query
# injection in the ORDER BY clause (parameterized binding doesn't work
# for column names in standard SQLite).
_SORT_COLUMNS = {
    "ssid": "ssid",
    "bssid": "bssid",
    "channel": "channel",
    "encryption": "encryption",
    "signal": "signal_strength",
    "last_seen": "last_seen",
    "whitelisted": "is_whitelisted",
}
_DEFAULT_SORT = "last_seen"

_BSSID_RE = re.compile(r"^[0-9a-fA-F:]{17}$")


def _sorted_filtered_networks(db, q: str, sort: str, order: str, only: str):
    """Hit the DB then apply text filter / sort in Python.

    Networks are O(hundreds) at most for our scope; in-memory filtering
    is fine and lets us keep the DB layer simple.
    """
    networks = db.get_networks(
        whitelisted=True if only == "white" else False if only == "open" else None,
    )
    if q:
        ql = q.lower()
        networks = [
            n for n in networks
            if ql in (n.get("ssid") or "").lower()
            or ql in (n.get("bssid") or "").lower()
            or ql in (n.get("encryption") or "").lower()
        ]
    col = _SORT_COLUMNS.get(sort, _SORT_COLUMNS[_DEFAULT_SORT])
    reverse = (order or "desc").lower() != "asc"
    networks.sort(key=lambda n: (n.get(col) is None, n.get(col)), reverse=reverse)
    return networks


@router.get("/networks")
def networks_page(
    request: Request,
    username: str = Depends(require_login),
    q: str = "",
    sort: str = _DEFAULT_SORT,
    order: str = "desc",
    only: str = "all",
):
    db = request.app.state.db
    networks = _sorted_filtered_networks(db, q, sort, order, only)
    return request.app.state.templates.TemplateResponse(
        "networks.html",
        {
            "request": request,
            "username": username,
            "active_nav": "networks",
            "networks": networks,
            "q": q,
            "sort": sort if sort in _SORT_COLUMNS else _DEFAULT_SORT,
            "order": order if order in ("asc", "desc") else "desc",
            "only": only if only in ("all", "white", "open") else "all",
        },
    )


@router.get("/partials/networks")
def networks_partial(
    request: Request,
    username: str = Depends(require_login),
    q: str = "",
    sort: str = _DEFAULT_SORT,
    order: str = "desc",
    only: str = "all",
):
    """Just the table body. Used by HTMX for refresh + filter/sort changes."""
    db = request.app.state.db
    networks = _sorted_filtered_networks(db, q, sort, order, only)
    return request.app.state.templates.TemplateResponse(
        "partials/networks_table.html",
        {
            "request": request,
            "networks": networks,
            "sort": sort if sort in _SORT_COLUMNS else _DEFAULT_SORT,
            "order": order if order in ("asc", "desc") else "desc",
            "q": q, "only": only,
        },
    )


@router.post("/partials/networks/{bssid}/whitelist")
def toggle_whitelist(
    request: Request,
    bssid: str,
    whitelisted: str = Form(""),
    username: str = Depends(require_login),
):
    """Flip the whitelist flag on a network. Returns just the updated row."""
    if not _BSSID_RE.match(bssid):
        raise HTTPException(status_code=400, detail="invalid BSSID")
    db = request.app.state.db
    target = whitelisted.lower() in ("1", "true", "on", "yes")
    db.set_whitelist(bssid, target)
    network = db.get_network_by_bssid(bssid)
    if not network:
        raise HTTPException(status_code=404, detail="network not found")
    return request.app.state.templates.TemplateResponse(
        "partials/networks_row.html",
        {"request": request, "n": network},
    )
