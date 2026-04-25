# Web UI Migration (Phase 3)

PenDonn is mid-migration from the legacy Flask UI (`web/`) to a modern
FastAPI + HTMX + Tailwind UI (`webui/`). Both run side-by-side until the
new one is feature-complete.

## What's where

| | Legacy | New |
|---|---|---|
| **Path** | `web/` | `webui/` |
| **Framework** | Flask + Jinja2 | FastAPI + Jinja2 |
| **Frontend** | Vanilla CSS + JS, gradient/glassmorphism | Tailwind via CDN, HTMX, Alpine.js |
| **Port** | 8080 | 8081 |
| **Auth** | HTTP Basic (Phase 1E) | Cookie-session login form (same `password_hash`) |
| **Live updates** | 3-second `setInterval` polling all endpoints | HTMX `hx-trigger="every 5s"` per partial; SSE for log stream (TBD) |
| **Mobile** | No | Yes (Tailwind responsive) |
| **Dark mode** | No (always dark gradient) | Toggle, persisted in localStorage |
| **systemd unit** | `pendonn-web.service` | not yet |
| **Status** | Frozen — bug fixes only | Active development |

## Running locally during development

From the repo root, with `requirements.txt` installed:

```bash
PYTHONPATH=. python -m uvicorn webui.app:app --port 8081 --reload
```

Then browse to `http://127.0.0.1:8081/`. With auth disabled (default),
you land on the dashboard immediately. To exercise the auth flow:

1. Generate a hash: `python web/app.py --hash-password`
2. Drop into `config/config.json.local`:
   ```json
   {
     "web": {
       "basic_auth": {
         "enabled": true,
         "username": "yourname",
         "password_hash": "scrypt:..."
       }
     }
   }
   ```
3. Restart uvicorn — `/` now redirects to `/login`.

## Migration plan

| Batch | Scope |
|---|---|
| **3A** ✅ | FastAPI skeleton, cookie auth, base layout, dashboard + KPI partials |
| **3B** | Networks page (table, sort, search, whitelist toggle, HTMX refresh) |
| **3C** | Handshakes + cracked passwords tables |
| **3D** | Scans + vulnerabilities pages (severity grouping, expandable details) |
| **3E** | Logs page with SSE stream, service start/stop/restart, database reset |
| **3F** | Settings (whitelist editor, config viewer), captive portal for evil-twin victims |
| **3G** | Polish + docs + flip installer to deploy `webui/` as the systemd unit; retire `web/` |

Each batch is its own commit on `redesign/2026-overhaul`. Tests in
`tests/test_webui_smoke.py` cover wiring; visual review happens in a
real browser per batch.

## Auth model

Same `password_hash` as Phase 1E Basic Auth — operator generates once
via `python web/app.py --hash-password`, drops into
`config/config.json.local` under `web.basic_auth.password_hash`, and
both UIs accept the same credentials. Logout works for the new UI;
the legacy UI relies on closing the browser.

Session cookie is `pendonn_session`, signed with the same `secret_key`
that Phase 1E persisted to `config.json.local`. `HttpOnly`, `SameSite=Lax`,
12-hour expiry. Not `Secure` (operator may run plain HTTP on the LAN —
encrypt the LAN segment with a VPN if you need transport security).

When `web.basic_auth.enabled` is `false`, all routes are anonymous and
the `/login` page just redirects to `/`. Use this for local dev only.

## Why both UIs at once

The user explicitly asked us to never break the running system. Keeping
the legacy UI live during the migration means:

- The Pi stays usable at every point in the migration.
- We can flip the installer's systemd unit pointer at the end as a single
  reversible change.
- Operators trying out the new UI can fall back to 8080 if anything
  breaks.

Once 3G ships and is verified, `web/` will be deleted.
