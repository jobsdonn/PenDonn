# PenDonn Safety Model — SSH Lockout Protection

**TL;DR:** PenDonn touches WiFi interfaces. WiFi interfaces are how you SSH into the Pi. If the wrong iface goes into monitor mode at the wrong moment, you lose your shell and have to drive to the Pi. The safety module exists to make that not happen.

This document explains the safety contract, what it blocks, what it allows, and how to opt out when you genuinely need to.

---

## The threat model

A new operator unboxes a Pi, plugs in two USB WiFi adapters, runs the installer, and SSHes in. The installer auto-detects MACs, but the operator hasn't yet verified which adapter is which. They start `pendonn`. PenDonn picks an interface to put into monitor mode. If it picks the wrong one — the one carrying the SSH session — the shell freezes mid-keystroke.

There is no remote way out of this. You drive to the Pi.

The safety module defends against this in three layers:

1. **`SSHGuard` (process-internal)** — every wifi-interface modification in PenDonn must call `SSHGuard.assert_safe_to_modify(iface)` first. Refuses the operation if it would touch the management iface or the iface SSH is currently riding over.

2. **`Preflight` (boot-time)** — runs once before the main daemon starts. Refuses to start if config + live system state would lead to immediate lockout.

3. **`recovery-watchdog.sh` (independent process)** — runs as its own systemd unit. If management iface drifts into monitor mode or loses its IP for >60s, it restores managed mode and renews DHCP. Insurance for when something escapes the first two layers (driver bug, daemon crash mid-state-change, etc.).

---

## The `safety:` config section

```json
"safety": {
  "enabled": true,
  "block_monitor_on_ssh_iface": true,
  "block_monitor_on_management": true,
  "block_kill_management_supplicant": true,
  "armed_override": false,
  "explicit_safe_ifaces": []
}
```

| Field | Default | What it does |
|-------|---------|--------------|
| `enabled` | `true` | Master switch. `false` = no protection at all. **Don't.** |
| `block_monitor_on_ssh_iface` | `true` | Refuse to put any iface in monitor mode if SSH is currently riding over it. |
| `block_monitor_on_management` | `true` | Refuse to put the configured `management_interface` in monitor mode, ever. |
| `block_kill_management_supplicant` | `true` | Refuse to kill `wpa_supplicant` instances bound to the management iface. (Replaces the old `pgrep -f` pattern that could match the wrong process.) |
| `armed_override` | `false` | Big red button. Bypasses all four guards above. Use only when you genuinely accept SSH loss. |
| `explicit_safe_ifaces` | `[]` | Per-iface allowlist for advanced cases. Iface names listed here skip all guard checks. |

---

## When to set `armed_override: true`

There are two legitimate cases:

1. **RPi Zero 2 W single-interface mode.** The Zero 2W has one WiFi radio. To do anything useful, you have to put `wlan0` (which is also management) into monitor mode. That IS the lockout. The shipped `config/config.rpi_zero2w.json` already has `armed_override: true` for this reason — by using that config you've accepted SSH loss. You're expected to have HDMI+keyboard or auto-start-on-boot ready.

2. **You SSH'd in over Ethernet.** If you're connected via wired ethernet, no WiFi monitoring can lock you out. Setting `armed_override: true` skips the (technically correct but pointless) checks.

In every other case, leave it `false`.

---

## What happens when a guard fires

`SSHGuard.assert_safe_to_modify('wlan2')` raises `SafetyViolation` with a clear message:

```
SAFETY: refusing to monitor mode on wlan2 — wlan2 is the configured
management interface (safety.block_monitor_on_management=true). To proceed,
either change the config or set safety.armed_override=true.
```

PenDonn modules catch this where appropriate (e.g. `wifi_scanner.start()` should log it and decline to start, not crash the daemon). The `Preflight` check at boot raises it as a fatal error and refuses to start the daemon at all.

---

## What the watchdog does (and doesn't do)

The watchdog (`scripts/recovery-watchdog.sh`, deployed as `pendonn-watchdog.service`):

- Runs every 30s by default (`PENDONN_WATCHDOG_INTERVAL=30`)
- Reads `safety.armed_override` and `safety.enabled` every iteration — you can toggle them live
- If override is armed or safety is disabled, the watchdog stays out of the way
- Otherwise, if management iface is in non-managed mode for >60s, runs:
  ```
  ip link set <iface> down
  iw dev <iface> set type managed
  ip link set <iface> up
  dhclient <iface>      # or dhcpcd if dhclient absent
  ```
- If management iface has no IPv4 for >60s, just renews DHCP

It cannot:
- Recover from driver kernel-panics (no userspace tool can)
- Recover if `iw` itself was unloaded
- Restore an SSH session that was already torn down (only the IP path)

It is **not** a substitute for getting the SSH-iface choice right in the first place. It's the airbag, not the seatbelt.

---

## Testing the safety model

Unit tests live in `tests/test_safety.py` and run on Windows or Linux without any hardware:

```bash
python -m unittest tests.test_safety -v
```

Coverage:
- All `SSHGuard` predicates and the assert path
- Preflight with clean config, duplicate-iface config, and SSH-over-monitor-iface scenarios
- `armed_override` correctly bypasses everything
- Supplicant-PID filtering keeps management-iface PIDs out of the kill list

If you change `core/safety.py`, run these tests before committing.

---

## Plugin loader trust model

`core/plugin_manager.py` discovers `.py` files under `plugins/` and runs
them via `importlib.util.spec_from_file_location` + `exec_module`. PenDonn
typically runs as root, so a plugin file = root code execution.

Two layers of protection close the most common accidents:

**Layer 1 — installer**
`scripts/install.sh` (and the legacy top-level `install.sh`) runs:

```
chown -R root:root /opt/pendonn/plugins
chmod 700           /opt/pendonn/plugins
find ... -type d -exec chmod 700 {} \;
find ... -type f -exec chmod 600 {} \;
```

After installation, only root can read or write under `plugins/`. An
operator who SSHes in as a non-root user cannot drop a plugin without
sudo.

**Layer 2 — loader-side ownership/mode check**
`core/plugin_manager._check_plugin_file_safety()` runs before each
`exec_module` call and refuses if:

- The plugin file or directory is **world-writable** (`o+w`) — fatal.
- The plugin file is **owned by a UID that isn't root or our effective UID** — fatal.
- The plugin file is **group-writable** — warning only (groups vary
  per-deployment; warning lets you spot it but doesn't break a `pendonn`
  shared dev group setup).

If you need to bypass this for a known-good reason (e.g. you're
developing plugins as a non-root user inside a VM), set:

```json
"safety": {
  "plugin_loader": {
    "allow_insecure_files": true
  }
}
```

Logs a `WARNING` at every load. Not for production.

## Adopting the guard in existing modules (Phase 1 work)

Right now `core/safety.py` exists but no PenDonn module calls into it yet. That migration happens in Phase 1. The pattern is:

```python
# In wifi_scanner.start():
from core.safety import SSHGuard, SafetyConfig
guard = SSHGuard(SafetyConfig.from_dict(self.config.get('safety')), interfaces)
try:
    guard.assert_safe_to_modify(self.interface, operation='monitor mode')
except SafetyViolation as e:
    logger.error(str(e))
    return  # refuse to start
```

And in `enumerator.py`, replace the `pgrep -f wpa_supplicant.*<iface>` + `kill <pid>` block with:

```python
pids_by_iface = self._enumerate_supplicant_pids()  # parses /proc/<pid>/cmdline
safe_pids = guard.assert_safe_to_kill_supplicant(pids_by_iface)
for pid in safe_pids:
    os.kill(pid, signal.SIGTERM)
```

Both migrations are pure additions of a check before existing code paths — no behavior change unless the check fires.
