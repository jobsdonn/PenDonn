"""Scans + vulnerabilities pages."""

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from webui.auth import require_login

router = APIRouter()


def _decode_results(scan: Dict[str, Any]) -> Dict[str, Any]:
    """Parse the JSON-encoded `results` blob into a Python object for templates."""
    out = dict(scan)
    raw = scan.get("results")
    if isinstance(raw, str) and raw:
        try:
            out["results_parsed"] = json.loads(raw)
        except json.JSONDecodeError:
            out["results_parsed"] = None
    else:
        out["results_parsed"] = raw
    return out


@router.get("/scans")
def scans_page(request: Request, username: str = Depends(require_login)):
    db = request.app.state.db
    scans = [_decode_results(s) for s in db.get_scans()]
    return request.app.state.templates.TemplateResponse(
        request,
        "scans.html",
        {
                       "username": username,
            "active_nav": "scans",
            "scans": scans,},
    )


@router.get("/partials/scans")
def scans_partial(request: Request, username: str = Depends(require_login)):
    db = request.app.state.db
    scans = [_decode_results(s) for s in db.get_scans()]
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/scans_table.html",
        {"request": request, "scans": scans,},
    )


@router.get("/scans/{scan_id}")
def scan_detail_partial(
    request: Request,
    scan_id: int,
    username: str = Depends(require_login),
):
    """Expandable details row for a single scan — hosts, ports, vulns."""
    db = request.app.state.db
    scans = [s for s in db.get_scans() if s.get("id") == scan_id]
    if not scans:
        raise HTTPException(status_code=404, detail="scan not found")
    scan = _decode_results(scans[0])
    vulns = db.get_vulnerabilities(scan_id=scan_id)
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/scan_detail.html",
        {"request": request, "scan": scan, "vulns": vulns,},
    )


@router.get("/vulnerabilities")
def vulns_page(
    request: Request,
    username: str = Depends(require_login),
    severity: str = "all",
):
    db = request.app.state.db
    sev_filter = None if severity == "all" else severity
    vulns = db.get_vulnerabilities(severity=sev_filter)
    grouped = _group_by_severity(db.get_vulnerabilities())
    return request.app.state.templates.TemplateResponse(
        request,
        "vulnerabilities.html",
        {
                       "username": username,
            "active_nav": "vulns",
            "vulns": vulns,
            "grouped": grouped,
            "severity": severity,},
    )


@router.get("/partials/vulnerabilities")
def vulns_partial(
    request: Request,
    username: str = Depends(require_login),
    severity: str = "all",
):
    db = request.app.state.db
    sev_filter = None if severity == "all" else severity
    vulns = db.get_vulnerabilities(severity=sev_filter)
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/vulns_table.html",
        {"request": request, "vulns": vulns, "severity": severity,},
    )


_SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")


def _group_by_severity(vulns):
    """Return {severity: count} ordered by severity_order."""
    counts = {s: 0 for s in _SEVERITY_ORDER}
    for v in vulns:
        sev = (v.get("severity") or "info").lower()
        if sev not in counts:
            counts[sev] = 0
        counts[sev] += 1
    return counts
