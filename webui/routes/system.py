"""Logs (SSE stream) + service control + dangerous ops (database reset).

Service-control and journalctl-streaming both require systemctl/journalctl
on the host, so they no-op gracefully on dev machines (Windows/macOS).
The endpoints return a clear "not available on this platform" response
rather than erroring — keeps the UI testable in a non-Pi environment.

The database-reset endpoint requires the operator to type the word RESET
into the form (a `confirm_phrase` field) — defends against accidental
clicks even after the main confirm modal.
"""

import asyncio
import io
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from webui.auth import require_login
from webui.sse import event_stream

router = APIRouter()


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

# Action prefixes the operator can filter by from the UI. The set is
# intentionally short — adding new actions in code doesn't require a
# UI change unless they need their own filter chip.
_AUDIT_FILTER_GROUPS = [
    ("all", "All", None),
    ("scope", "Scope", "scope."),
    ("allowlist", "Allowlist", "allowlist."),
    ("login", "Auth", "login."),
    ("attack.refused", "Refused attacks", "attack.refused"),
]


@router.get("/audit")
def audit_page(
    request: Request,
    filter: str = "all",
    username: str = Depends(require_login),
):
    db = request.app.state.db
    prefix = next((p for k, _, p in _AUDIT_FILTER_GROUPS if k == filter), None)
    entries = db.get_audit_log(action_prefix=prefix, limit=500)
    return request.app.state.templates.TemplateResponse(
        request,
        "audit.html",
        {
            "username": username,
            "active_nav": "audit",
            "entries": entries,
            "filter": filter,
            "filter_groups": _AUDIT_FILTER_GROUPS,
        },
    )


@router.get("/partials/audit")
def audit_partial(
    request: Request,
    filter: str = "all",
    username: str = Depends(require_login),
):
    db = request.app.state.db
    prefix = next((p for k, _, p in _AUDIT_FILTER_GROUPS if k == filter), None)
    entries = db.get_audit_log(action_prefix=prefix, limit=500)
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/audit_table.html",
        {"entries": entries, "filter": filter},
    )


@router.get("/api/events/stream")
async def state_event_stream(
    request: Request,
    username: str = Depends(require_login),
):
    """Single SSE stream that fires named events when DB state changes.

    Events emitted (one per logical view):
      - stats, scans, handshakes, networks, passwords, vulns, scope

    Each event's `data` is just a digest hash; the UI listens for the
    event name and re-fetches the corresponding partial. Replaces the
    per-page HTMX `every Xs` polling that used to reset interactive
    state (open accordions, expanded rows) on every tick.
    """
    db = request.app.state.db
    return StreamingResponse(
        event_stream(request, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Service control
# ---------------------------------------------------------------------------

_ALLOWED_SERVICES = {"pendonn", "pendonn-webui"}
_ALLOWED_ACTIONS = {"start", "stop", "restart", "status"}


def _have_systemctl() -> bool:
    return platform.system() == "Linux" and shutil.which("systemctl") is not None


def _service_status(name: str) -> str:
    """Return 'active' / 'inactive' / 'failed' / 'unknown' / 'unavailable'."""
    if not _have_systemctl():
        return "unavailable"
    try:
        r = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return (r.stdout or "").strip() or "unknown"
    except (subprocess.SubprocessError, OSError):
        return "unknown"


@router.get("/partials/services")
def services_partial(request: Request, username: str = Depends(require_login)):
    statuses = {svc: _service_status(svc) for svc in _ALLOWED_SERVICES}
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/services.html",
        {"request": request, "statuses": statuses, "have_systemctl": _have_systemctl(),},
    )


@router.post("/services/{service}/{action}")
def service_action(
    request: Request,
    service: str,
    action: str,
    username: str = Depends(require_login),
):
    if service not in _ALLOWED_SERVICES:
        raise HTTPException(status_code=400, detail=f"unknown service: {service}")
    if action not in _ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail=f"unknown action: {action}")
    if not _have_systemctl():
        # Return a partial that shows the platform-unavailable state
        return request.app.state.templates.TemplateResponse(
            request,
            "partials/services.html",
            {
                               "statuses": {svc: "unavailable" for svc in _ALLOWED_SERVICES},
                "have_systemctl": False,
                "last_action_message": f"systemctl not available on this host — '{action} {service}' was not executed",},
        )
    try:
        r = subprocess.run(
            ["systemctl", action, service],
            capture_output=True, text=True, timeout=15, check=False,
        )
        msg = f"{action} {service}: " + ("ok" if r.returncode == 0 else f"exit {r.returncode}")
        if r.stderr.strip():
            msg += f" — {r.stderr.strip()[:200]}"
    except subprocess.TimeoutExpired:
        msg = f"{action} {service}: timeout (15s)"
    except OSError as e:
        msg = f"{action} {service}: {e}"
    statuses = {svc: _service_status(svc) for svc in _ALLOWED_SERVICES}
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/services.html",
        {
                       "statuses": statuses,
            "have_systemctl": True,
            "last_action_message": msg,},
    )


# ---------------------------------------------------------------------------
# Logs page + SSE stream
# ---------------------------------------------------------------------------

@router.get("/logs")
def logs_page(request: Request, username: str = Depends(require_login)):
    return request.app.state.templates.TemplateResponse(
        request,
        "logs.html",
        {
                       "username": username,
            "active_nav": "logs",
            "have_systemctl": _have_systemctl(),},
    )


def _journalctl_lines(service: str, n: int = 50):
    """Yield recent journal lines. Empty iter on non-Linux."""
    if not _have_systemctl() or not shutil.which("journalctl"):
        return
    try:
        r = subprocess.run(
            ["journalctl", "-u", service, "-n", str(n), "--no-pager", "-o", "short-iso"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        for line in r.stdout.splitlines():
            yield line
    except (subprocess.SubprocessError, OSError):
        return


@router.get("/api/logs/recent")
def logs_recent(
    request: Request,
    service: str = "pendonn",
    n: int = 100,
    username: str = Depends(require_login),
):
    """Non-streaming snapshot for the initial page load."""
    if service not in _ALLOWED_SERVICES:
        raise HTTPException(status_code=400, detail="unknown service")
    n = max(10, min(n, 500))
    lines = list(_journalctl_lines(service, n))
    if not lines:
        # Fallback: read from db.system_logs (works on Windows dev too)
        db = request.app.state.db
        try:
            db_logs = db.get_logs(limit=n)
            lines = [
                f"{l.get('timestamp', '?')} [{l.get('level', '?')}] "
                f"{l.get('module', '?')}: {l.get('message', '')}"
                for l in db_logs
            ]
        except Exception:
            lines = ["(no logs available — daemon may not have run yet)"]
    return {"service": service, "lines": lines}


@router.get("/api/logs/stream")
async def logs_stream(
    request: Request,
    service: str = "pendonn",
    username: str = Depends(require_login),
):
    """Server-Sent Events stream of `journalctl -fu <service>`.

    On non-Linux hosts (or when journalctl is missing) we send a single
    "stream-unavailable" event then close — caller's EventSource will see
    the connection end and stop reconnecting.
    """
    if service not in _ALLOWED_SERVICES:
        raise HTTPException(status_code=400, detail="unknown service")

    async def gen():
        if not _have_systemctl() or not shutil.which("journalctl"):
            yield (
                "event: unavailable\n"
                "data: log streaming requires systemd; running on "
                f"{platform.system()}.\n\n"
            )
            return
        proc = await asyncio.create_subprocess_exec(
            "journalctl", "-fu", service, "--no-pager", "-o", "short-iso",
            "-n", "0",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            while True:
                if await request.is_disconnected():
                    break
                line = await proc.stdout.readline()
                if not line:
                    # journalctl exited; tell the client and stop
                    yield "event: closed\ndata: stream ended\n\n"
                    break
                # SSE framing: prefix every line with "data: "
                text = line.decode("utf-8", errors="replace").rstrip()
                yield f"data: {text}\n\n"
        finally:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=2)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
    })


# ---------------------------------------------------------------------------
# Database reset (heavily-confirmed destructive op)
# ---------------------------------------------------------------------------

# Tables that should survive a "reset" (currently none — every table is
# operator data). Listed explicitly so future schema additions don't get
# silently wiped without thought.
_TABLES_TO_TRUNCATE = (
    "vulnerabilities",   # FK → scans
    "scans",             # FK → networks
    "cracked_passwords", # FK → handshakes
    "handshakes",        # FK → networks
    "networks",
    "system_logs",
)


@router.get("/export/pdf")
def export_pdf(
    request: Request,
    username: str = Depends(require_login),
):
    """Generate a PDF pentest report and stream it to the browser."""
    try:
        from core.pdf_report import PDFReport
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="PDF generation unavailable — install reportlab: pip install reportlab",
        )

    config = request.app.state.config
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    try:
        # Open a fresh DB connection for the report — avoids cross-thread
        # sqlite3 issues with the shared app.state.db instance.
        from core.database import Database
        report_db = Database(config["database"]["path"])
        gen = PDFReport(report_db, output_path=tmp.name)
        gen.generate_report()
        with open(tmp.name, "rb") as f:
            pdf_bytes = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    filename = f"pendonn_report_{timestamp}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/danger/reset-database")
def reset_database(
    request: Request,
    confirm_phrase: str = Form(""),
    username: str = Depends(require_login),
):
    """Truncate every operator-data table. Two confirmations required:

      1. Operator must explicitly POST here (UI gates it behind a modal).
      2. confirm_phrase must equal "RESET" exactly.

    A copy of the SQLite file is written to <db>.bak.<unixts> before any
    deletes, so a misclick is recoverable from disk.

    We TRUNCATE rather than rm-and-recreate because background threads
    (FastAPI workers, the daemon if it's running) hold thread-local
    sqlite3 connections that would silently break across an unlink. The
    Database class doesn't have a "close everyone's handle" primitive
    yet (audit P1 item still pending) — DELETE FROM avoids the issue.
    """
    if confirm_phrase != "RESET":
        raise HTTPException(
            status_code=400,
            detail='confirm_phrase must equal "RESET" exactly',
        )

    db = request.app.state.db
    db_path = request.app.state.config["database"]["path"]

    # Best-effort backup. Use sqlite3's online backup API rather than
    # shutil.copy so we get a transactionally-consistent snapshot even
    # if other connections are mid-write.
    backup_path = f"{db_path}.bak.{int(time.time())}"
    try:
        if os.path.isfile(db_path):
            import sqlite3
            src = sqlite3.connect(db_path)
            try:
                dst = sqlite3.connect(backup_path)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
    except (OSError, sqlite3.Error) as e:
        raise HTTPException(status_code=500, detail=f"backup failed: {e}")

    # Stop the daemon so it releases all write locks, then truncate, then restart.
    # Without stopping, the daemon's thread-local connections hold open transactions
    # that block writes indefinitely even with WAL mode + busy_timeout.
    import subprocess as _sub
    import sqlite3 as _sqlite3

    # On Linux with systemd: stop daemon to release write locks, truncate, restart.
    # On other platforms (dev/Windows): fall back to busy_timeout only.
    have_systemctl = _have_systemctl()
    daemon_was_running = False
    if have_systemctl:
        try:
            r = _sub.run(["systemctl", "is-active", "pendonn"],
                         capture_output=True, text=True)
            daemon_was_running = r.returncode == 0
            if daemon_was_running:
                _sub.run(["systemctl", "stop", "pendonn"], timeout=40, check=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"could not stop daemon: {e}")

    try:
        reset_conn = _sqlite3.connect(db_path, timeout=30, isolation_level=None)
        reset_conn.execute("PRAGMA journal_mode=WAL")
        reset_conn.execute("PRAGMA busy_timeout=30000")
        reset_conn.execute("BEGIN EXCLUSIVE")
        for tbl in _TABLES_TO_TRUNCATE:
            reset_conn.execute(f"DELETE FROM {tbl}")  # nosec — tbl is a literal allowlist
            reset_conn.execute("DELETE FROM sqlite_sequence WHERE name = ?", (tbl,))
        reset_conn.execute("COMMIT")
        reset_conn.close()
    except Exception as e:
        if daemon_was_running:
            _sub.run(["systemctl", "start", "pendonn"], timeout=10)
        raise HTTPException(status_code=500, detail=f"truncate failed: {e}")

    if daemon_was_running:
        _sub.run(["systemctl", "start", "pendonn"], timeout=10)

    return {
        "ok": True,
        "backup": backup_path,
        "tables_truncated": list(_TABLES_TO_TRUNCATE),
        "ts": datetime.now(tz=timezone.utc).isoformat(),
    }
