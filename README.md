# PenDonn

Headless WiFi pentest tool for Raspberry Pi, designed for **authorized internal pentests** (employer-owned networks, lab environments, customer engagements with written scope). Discovers WPA-protected networks, captures handshakes, attempts cracking, and probes for credentials on the resulting LAN — all without operator intervention once started.

> **Legal:** Only use on networks you own or have written authorization to test. Unauthorized network probing is illegal in most jurisdictions.

## What it does

- **Continuous WiFi scan** (airodump-ng) across 2.4 GHz + 5 GHz, parsing APs by BSSID/ESSID/encryption/channel
- **Targeted handshake capture**: only attacks SSIDs in `allowlist.ssids`, with both classic 4-way handshake (deauth + reassociation) and active PMKID retrieval (hcxdumptool, no client required)
- **Cracking**: cowpatty (`.pcapng` native, ARM-friendly), aircrack-ng, and john the Ripper, in that priority. Extra wordlists (test/probable/SecLists top-N) are tried before `rockyou.txt`.
- **Post-crack enumeration**: connects to the cracked network and runs nmap + a plugin pipeline (HTTP, FTP, SSH, SMB, SNMP, mDNS, UPnP, …)
- **Web UI** (FastAPI + HTMX, port 8081) for status, settings, log streaming, and manual control
- **Push notifications** (optional, via [ntfy.sh](https://ntfy.sh)) — phone alerts when a handshake captures, a PSK cracks, or a critical vuln surfaces
- **SSH-lockout protection**: explicit allowlist for which iface can go into monitor mode, plus a recovery watchdog as last resort

## Hardware

- **Raspberry Pi 4 / 5** with Raspberry Pi OS Trixie (Debian 13)
- **Two external WiFi adapters** that support monitor mode + injection (verified: Mercusys MA20N / RTL8821AU)
- **Onboard WiFi or Ethernet** for management/SSH (must be different from the two attack adapters)
- *Optional*: Waveshare 7.3″ ePaper display ([wiring + setup](docs/DISPLAY_SETUP.md))

The single-radio "RPi Zero 2 W" config exists (`config/config.rpi_zero2w.json`) but requires `safety.armed_override: true` because the only WiFi radio is also the management iface — see [docs/SAFETY.md](docs/SAFETY.md).

## Install

```bash
git clone <this-repo> pendonn
cd pendonn
sudo ./install.sh
```

`install.sh` is the only operator-facing entry point. It:

1. Installs system dependencies (aircrack-ng suite, hcxdumptool, hcxtools, cowpatty, john, nmap, build tools)
2. Installs the RTL8812AU/RTL8821AU driver from source if not already present
3. Copies code to `/opt/pendonn/`, creates a venv, installs Python deps from `requirements.txt`
4. Downloads `rockyou.txt` to `/usr/share/wordlists/`
5. Creates three systemd units (`pendonn`, `pendonn-webui`, `pendonn-watchdog`) — installed but **not enabled**
6. Runs an interactive wizard for iface assignment + allowlist + web UI port + cracking + display

Re-running `install.sh` is safe: it preserves `data/`, `logs/`, `handshakes/`, and `config/config.json.local`.

## After install

```bash
# 1. Set the web UI password (writes a scrypt hash you paste into config.json.local)
sudo /opt/pendonn/venv/bin/python3 /opt/pendonn/scripts/hash-password.py

# 2. Edit local overlay config: set MAC addresses for each iface + paste the hash
sudo nano /opt/pendonn/config/config.json.local

# 3. Start everything (one-shot for testing, --enable for persistence)
sudo systemctl start  pendonn pendonn-webui pendonn-watchdog
sudo systemctl enable pendonn pendonn-webui pendonn-watchdog

# 4. Open the UI
xdg-open http://<pi-ip>:8081
```

Minimum `config.json.local` shape:

```json
{
  "wifi": {
    "monitor_mac":    "aa:bb:cc:dd:ee:01",
    "attack_mac":     "aa:bb:cc:dd:ee:02",
    "management_mac": "dc:a6:32:11:22:33"
  },
  "allowlist": {
    "strict": true,
    "ssids":  ["Customer-Authorized-AP-1"]
  },
  "web": {
    "host":       "0.0.0.0",
    "secret_key": "<openssl rand -hex 32>",
    "basic_auth": {
      "enabled":       true,
      "username":      "admin",
      "password_hash": "<output of hash-password.py>"
    }
  }
}
```

The full annotated default lives in [config/config.example.json](config/config.example.json). The base [config/config.json](config/config.json) is tracked in git; your overlay (`config.json.local`) is not, so secrets stay off the repo.

## Configuration reference

| Section | Key | Effect |
|---|---|---|
| `wifi` | `monitor_mac` / `attack_mac` / `management_mac` | Iface resolution by MAC. Survives USB reseats; falls back to `*_interface` names if MAC empty. |
| `allowlist` | `strict` (default `true`) | `true` = only attack SSIDs in `ssids[]`. `false` = attack everything (requires `safety.armed_override`). |
| `allowlist` | `ssids` | List of authorized SSIDs. Empty + strict = passive scan only, no attacks. |
| `safety` | `armed_override` (default `false`) | Bypass all SSH-lockout guards. Only set if you SSH'd over Ethernet or accept losing your shell. See [docs/SAFETY.md](docs/SAFETY.md). |
| `web.basic_auth` | `enabled` / `username` / `password_hash` | Login for the web UI. Always enable in production. |
| `cracking` | `engines` | Order to try: `["cowpatty", "aircrack-ng", "john"]`. Cowpatty reads `.pcapng` natively and is the most reliable engine on ARM. |
| `cracking` | `wordlist_path` | Default `/usr/share/wordlists/rockyou.txt`. Operator can swap. |
| `cracking` | `extra_wordlists` | List of additional wordlist paths to try **before** the main wordlist (e.g. test password, probable-WPA, SecLists top-N). Empty by default. |
| `notifications.ntfy` | `enabled` / `topic` | Push notifications via ntfy. Disabled by default. Pick a long random topic — anyone who knows it can read your alerts. See "Notifications" below. |
| `display` | `enabled` | Set `false` for headless Pi. |

## Operating

**The web UI** (port 8081) is the primary interface:

- **Dashboard** — KPI tiles (networks/handshakes/cracked/active scans)
- **Networks** — sortable/filterable AP table, inline allowlist toggle
- **Handshakes** — captured `.cap` files, verification status
- **Cracked** — recovered passwords (click to reveal, copy-on-click)
- **Scans** — per-network nmap + plugin output, expandable
- **Vulnerabilities** — grouped by severity
- **Logs** — live SSE stream from journald (`pendonn` or `pendonn-webui`)
- **Settings** — allowlist editor, strict toggle, safety status, redacted config viewer
- **Captive** — mobile-friendly portal page for evil-twin engagements

**CLI** (when you don't want the UI):

```bash
sudo journalctl -u pendonn -f                    # live daemon log
sudo journalctl -u pendonn -p err                # errors only
sudo systemctl status pendonn pendonn-webui pendonn-watchdog
sudo systemctl restart pendonn
```

Captured handshakes land in `/opt/pendonn/handshakes/` as `<BSSID>_<TIMESTAMP>-01.cap`. Cracked passwords go into `data/pendonn.db` and the web UI's "Cracked" page.

## Notifications

PenDonn can push alerts to your phone via [ntfy.sh](https://ntfy.sh) — no account, no app store hoops, just install the official ntfy app and subscribe to your topic. Disabled by default; opt in via `config.json.local`.

```json
{
  "notifications": {
    "ntfy": {
      "enabled": true,
      "server":  "https://ntfy.sh",
      "topic":   "pendonn-<long-random-string>",
      "token":   "",
      "notify_on": {
        "handshake":     true,
        "crack":         true,
        "vulnerability": true,
        "scan":          true
      }
    }
  }
}
```

Event → ntfy priority mapping:

| Event | Priority | Phone behaviour |
|---|---|---|
| Handshake captured | 2 (low) | Silent / banner |
| Scan complete | 3 (default) | Normal notification |
| PSK cracked | 4 (high) | Sound + vibrate |
| Critical/high vulnerability | 5 (urgent) | Bypasses Do Not Disturb on most phones |

**Topic security:** `ntfy.sh` topics are public by URL — anyone who guesses your topic name can read your notifications. Treat the topic string as a shared secret. Use `openssl rand -hex 16` for a unique unguessable name, and keep it in `config.json.local` (untracked) — never in committed defaults.

For sensitive engagements, run a self-hosted ntfy server with auth (`server: "https://ntfy.example.com"`, `token: "tk_..."`).

## Safety model

There are two principles:

### 1. Never lock yourself out of SSH

- Every iface mode change goes through `SSHGuard.assert_safe_to_modify()` — refuses to touch the management iface or the iface SSH currently rides
- A boot-time `Preflight` aborts daemon startup if config would lead to lockout (e.g. `strict=false` without `armed_override`)
- A `pendonn-watchdog` systemd unit runs `scripts/recovery-watchdog.sh` independently — flips management iface back from monitor → managed every 30s if anything escapes the first two layers

### 2. Never attack a network you haven't been authorized to test

- The `allowlist` defines *which* SSIDs are in scope (config-level)
- A separate **scope authorization** receipt sits between the allowlist and the daemon (operational-level): the daemon refuses to capture handshakes or deauth until a human has explicitly clicked "Confirm scope" in the web UI on **Settings → Scope authorization**, attesting they have written authorization
- The receipt is per-SSID-set: shrinking the allowlist stays confirmed; adding a new SSID requires re-confirmation
- A banner on the dashboard makes the unconfirmed state impossible to miss
- All confirmations are timestamped + tagged with the WebUI username for audit trail

This means: even with the allowlist populated, a fresh install / restored backup / new SSID is **passive-only** until a human says "yes, go".

Read [docs/SAFETY.md](docs/SAFETY.md) before changing the `safety:` config section.

## Project layout

```
pendonn/
├── core/             # daemon: scanner, cracker, enumerator, evil_twin, safety, plugin_manager
├── webui/            # FastAPI + HTMX UI (port 8081)
├── plugins/          # Per-service enumeration (HTTP, FTP, SSH, SMB, SNMP, mDNS, UPnP, …)
├── scripts/          # Internal helpers — operator only invokes hash-password.py directly
│   ├── hash-password.py            # generate basic_auth hash for config.json.local
│   ├── recovery-watchdog.sh        # SSH-lockout watchdog (called by systemd unit)
│   ├── install-wifi-drivers.sh     # called by install.sh
│   └── patch_waveshare.py          # called by install.sh
├── config/
│   ├── config.json                 # tracked defaults
│   ├── config.example.json         # annotated reference
│   └── config.rpi_zero2w.json      # single-radio variant
├── tests/            # 159 unit tests, run with: python -m unittest discover tests
├── docs/
│   ├── SAFETY.md                   # SSH lockout + plugin loader trust model
│   └── DISPLAY_SETUP.md            # Waveshare wiring + library install
├── install.sh        # ONE entry point — operator runs this and nothing else
├── main.py           # daemon entry
├── check_health.py   # post-deploy smoke test (optional)
└── diagnose_display.py  # display hardware test (optional)
```

## Development

```bash
python -m venv venv
. venv/bin/activate                 # or venv\Scripts\activate on Windows
pip install -r requirements.txt
python -m unittest discover tests   # 159 tests, ~7s on a laptop
```

POSIX-only tests (e.g. `/proc` walking) are skipped on Windows. The web UI runs locally:

```bash
PYTHONPATH=. uvicorn webui.app:app --host 127.0.0.1 --port 8081
```

## Known limitations

- **PMKID requires the AP to expose it.** Many enterprise APs (Aruba, Cisco, Meraki) disable PMKID; the daemon falls back to classic deauth+handshake on those.
- **No remote cracking offload.** Handshakes are cracked locally on the Pi (CPU only — slow). Backlog item: ship `.22000` to a remote GPU host running hashcat.
- **`install.sh` re-runs are idempotent for data, not for system-level state.** Re-installing won't lose your handshakes, but it will re-overwrite the systemd units and re-run the wizard.
- **Plugin loader executes any `.py` file in `plugins/`** as root. The `0700 root:root` permission lockdown + ownership check (see [docs/SAFETY.md](docs/SAFETY.md)) prevents the most common accidents but is not a sandbox.

## License

Operator-owned project; no public license. Pen-test use only on systems you own or have authorization for.
