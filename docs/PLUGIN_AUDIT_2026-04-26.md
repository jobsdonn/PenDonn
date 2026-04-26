# Plugin audit — 2026-04-26

Snapshot of the state of `plugins/` at branch `redesign/2026-overhaul`. This file is a **find-once-fix-over-time** record — track progress against the priorities below.

## TL;DR

The plugin system is **mostly non-functional today**. Three reasons:

1. **7 of 11 plugins fail to load** because their `plugin.json` manifests omit `module` and `class` keys, and the loader's defaults (`plugin.py` + `Plugin`) don't match the actual filenames/classnames.
2. **Most error paths crash on `AttributeError: 'PluginBase' object has no attribute 'log_debug'`** — `PluginBase` only provides `log_info/warning/error`, but seven plugins call `self.log_debug(...)`.
3. **Active-attack plugins (`ssh_scanner`, `router_scanner`, `web_scanner._check_default_credentials`, and—when fixed—`ftp_scanner`) brute-force credentials**, which directly violates the project's non-negotiable lockout-protection rule.

The "stealer" plugins (`smb_cred_stealer`, `vpn_cred_stealer`) are recon-only (filename pattern matching) — names oversell what they actually do.

## Per-plugin status

| Plugin | Status | Scope (ports/binaries/IO) | Key risks/issues | Quick wins |
|---|---|---|---|---|
| **bluetooth_scanner** | SUSPICIOUS | Local hci0; `hciconfig`,`hcitool`,`bluetoothctl`,`sdptool` (deprecated); writes vulns to DB | `super().__init__(config, db, "Bluetooth Scanner")` — name leaks into `extra_args`, harmless but wrong; flags every discovered device as a "vuln"; `sdptool` removed in BlueZ 5.51+; touches surrounding devices not in scope | Stop creating "Discoverable" vulns; replace sdptool with bluetoothctl SDP; gate on allowlist |
| **dns_scanner** | BROKEN | UDP/TCP 53; `dnspython` lib | Manifest missing `module/class` → won't load; `log_debug` doesn't exist; tests `example.com`/`*.local` AXFR which is meaningless on internal IP | Add manifest fields; remove log_debug; query reverse-PTR domains, not `example.com` |
| **ftp_scanner** | BROKEN | TCP 21,2121; stdlib `ftplib` | Manifest missing `module/class`; `log_debug` AttributeError; **6 weak creds tried in sequence → account-lockout risk** (violates non-negotiable lockout protection); no per-host throttle | Manifest fix; auth-only on `anonymous`, drop creds list or move behind explicit consent flag |
| **router_scanner** | BROKEN | TCP 80/443/8080/8443/8000/8888; `requests` (verify=False) | Manifest missing fields; `log_debug` missing; **30 cred attempts/host across web forms → guaranteed lockout** of routers/cameras/printers; POSTs to arbitrary `/login*` endpoints (active attack); duplicate creds in list | Manifest fix; cap to 1-2 attempts; honor lockout-protection config; respect Retry-After |
| **smb_cred_stealer** | BROKEN | TCP 139/445; shells out to `smbclient`; **uses literal `'\\n'` instead of `'\n'`** when splitting output → never parses anything | Manifest missing fields; `log_debug` missing; recursive `ls` on every share with 60s timeout; only does discovery (no actual file fetch) so name oversells; if it worked, scope creep beyond authorized share | Fix `\\n`→`\n`; manifest; share-allowlist; bound recurse depth; rename to `smb_share_locator` |
| **smb_scanner** | SUSPICIOUS | TCP 139/445; `nmap`, `smbclient` | **`_check_share_writable` runs `mkdir testdir` on every share** → writes to target FS, leaves artifact, may trip DLP/AV; no cleanup `rmdir`; nmap subprocess no rate-limit | Replace mkdir-probe with read-only ACL inspection or skip; add cleanup; manifest already OK |
| **snmp_scanner** | BROKEN | UDP 161; `pysnmp` | Manifest missing fields; `log_debug` missing; `pysnmp.hlapi` star-import is heavy and v7 deprecated old API; 12 community strings tried sequentially | Manifest fix; switch to `pysnmp.hlapi.v3arch`; parallelize or single-shot |
| **ssh_scanner** | SUSPICIOUS | TCP 22; `paramiko`, `nmap` | **6 weak creds attempted → lockout risk**, contradicts memory's non-negotiable rule; `version<7` flag is now wrong (OpenSSH 9.x current); `_check_root_login` parses nmap stdout fragility | Gate creds behind explicit consent; widen version threshold; add per-host backoff |
| **upnp_scanner** | BROKEN | UDP 1900 unicast; raw socket | Manifest missing fields; **SSDP packet uses literal `'\\r\\n'`** strings — server will reject malformed M-SEARCH; response parser also splits on `'\\r\\n'`; `log_debug` missing | Replace `'\\r\\n'`→`'\r\n'`; manifest; multicast not unicast |
| **vpn_cred_stealer** | BROKEN | TCP 139/445/443/8443; `smbclient`, `requests` | Manifest missing fields; same `'\\n'` bug as smb_cred_stealer; `log_debug` missing; "extract credentials" only matches filenames — name overstates capability; HTTPS portal probe with verify=False | Fix `\\n`; manifest; rename to "VPN Config Locator"; verify TLS |
| **web_scanner** | SUSPICIOUS | TCP 80/443/8080/8443; `requests`, **`nikto`** binary (300s/host) | Manifest OK; **`_check_default_credentials` POSTs creds to `/wp-login.php`, `/admin`, etc → active brute force, lockout**; no missing-host suppress for `requests` warnings before first call; nikto run unconditional, can take 5+min/host and stalls scan | Drop default-creds POST or gate; bound nikto via cap or make opt-in; check nikto presence |

## Priorities

### Priority 1 — One-shot loader fixes (low risk, no semantic change)
- Add `log_debug` to `core/plugin_manager.py:PluginBase`
- In the loader, infer `module`/`class` from manifest dir name when missing (e.g. `dns_scanner/` → `dns_scanner.py` → `DNSScanner`)
- Fix literal-escape bugs:
  - `plugins/smb_cred_stealer/smb_cred_stealer.py`: `'\\n'` → `'\n'`
  - `plugins/vpn_cred_stealer/vpn_cred_stealer.py`: `'\\n'` → `'\n'`
  - `plugins/upnp_scanner/upnp_scanner.py`: `'\\r\\n'` → `'\r\n'`

These fixes get 7 plugins loading and 3 plugins actually producing output, without changing any attack behaviour.

### Priority 2 — Lockout-policy compliance (needs operator decision)
- `ssh_scanner`: gate the 6-cred brute-force behind a config flag, or remove entirely
- `router_scanner`: cap attempts to 1-2, OR move behind explicit consent
- `web_scanner._check_default_credentials`: same — gate or remove
- `ftp_scanner`: keep `anonymous` only, drop weak-cred list

These are **operator policy decisions**, not bugs. Defer until reviewed.

### Priority 3 — Reduce target-side artifacts
- `smb_scanner._check_share_writable`: stop creating `testdir` on every share. Replace with ACL inspection or skip the writable-check entirely.
- `bluetooth_scanner`: stop flagging every discovered device as a vuln; rate-limit broadcast probes.

### Priority 4 — Naming honesty
- Rename `smb_cred_stealer` → `smb_share_locator`
- Rename `vpn_cred_stealer` → `vpn_config_locator`

These plugins do not steal credentials; they list filenames. The current names violate the project's "operator clarity" principle.

## Out of scope for this audit
- Performance / parallelism tuning
- New plugins (covered by separate todo)
- Plugin sandbox / privilege drop (already documented in docs/SAFETY.md)
