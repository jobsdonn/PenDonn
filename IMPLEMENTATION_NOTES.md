# wlan2 Enumeration Implementation

## Problem
When the enumerator connected to cracked networks using wlan0 (management interface), it killed the SSH connection to the Raspberry Pi.

## Solution
Implemented a coordination system to use wlan2 (attack interface) for enumeration instead of wlan0:

### Architecture

**WiFi Adapters:**
- **wlan0** (dc:a6:32:9e:ea:ba): Management + SSH - NEVER disconnect
- **wlan1**: Monitor mode for passive scanning
- **wlan2**: Attack interface - temporarily borrowed for enumeration

**Coordination System:**
1. Enumerator requests to borrow wlan2 via `wifi_scanner.pause_for_enumeration()`
2. WiFiScanner stops all active captures and sets `enumeration_active` flag
3. Enumerator switches wlan2: monitor → managed
4. Enumerator connects to target network, performs enumeration
5. Enumerator disconnects and restores wlan2: managed → monitor
6. Enumerator notifies via `wifi_scanner.resume_from_enumeration()`
7. WiFiScanner resumes normal operations

### Safety Features

**Threading Lock:**
- `wifi_scanner.enumeration_lock` prevents race conditions
- Both pause/resume operations are locked

**Monitor Mode Restoration:**
- `_disconnect_from_network()` uses try/finally block
- Monitor mode restoration happens in finally block (always executes)
- Emergency fallback with ifconfig/iwconfig if ip/iw fails
- Critical logging if restore fails

**Network Safety:**
- Checks if target network is currently connected via wlan0
- Refuses to enumerate if it would kill SSH
- Logs helpful error messages

**Capture Prevention:**
- `_start_handshake_capture()` checks `enumeration_active` flag
- No new captures start while enumeration borrows wlan2

### Modified Files

**core/wifi_scanner.py:**
- Added `enumeration_active` flag
- Added `enumeration_lock` for thread safety
- Added `pause_for_enumeration()` - stops captures, sets flag
- Added `resume_from_enumeration()` - restores monitor, clears flag
- Modified `_start_handshake_capture()` - skips if enumeration active

**core/enumerator.py:**
- Added `wifi_scanner` parameter to `__init__`
- Set `enumeration_interface = wlan2` (attack interface)
- Added safety check in `_perform_enumeration()` - prevents SSH kill
- Rewrote `_connect_to_network()` - mode switch, proper interface, pause/resume
- Rewrote `_disconnect_from_network()` - try/finally safety, monitor restore
- Updated `_discover_hosts()` - uses enumeration_interface not management

**main.py:**
- Updated enumerator initialization to pass `wifi_scanner` instance

### Testing Checklist

Before production deployment:

- [ ] Crack a test network (not current SSH network)
- [ ] Verify enumeration connects via wlan2
- [ ] Verify SSH stays alive during enumeration
- [ ] Check logs show: pause → mode switch → connect → scan → disconnect → restore → resume
- [ ] Verify wlan2 returns to monitor mode after enumeration
- [ ] Verify attacks resume after enumeration completes
- [ ] Test error cases:
  - [ ] Connection timeout
  - [ ] Invalid password (should not happen, but test safety)
  - [ ] DHCP failure
  - [ ] nmap crash
- [ ] Verify monitor mode ALWAYS restored (check finally block works)

### Logs to Watch

**Normal Flow:**
```
[enumerator] Pausing attacks to use wlan2 for enumeration
[wifi_scanner] Pausing for enumeration, stopping active captures
[enumerator] Switching wlan2 from monitor to managed mode
[enumerator] Starting wpa_supplicant on wlan2
[enumerator] Requesting IP address on wlan2
[enumerator] Successfully connected to TestNetwork on wlan2
[enumerator] Scanning network: 192.168.1.0/24 on wlan2
[enumerator] Disconnecting from network on wlan2
[enumerator] Restoring wlan2 to monitor mode
[enumerator] Resuming attacks
[wifi_scanner] Resuming from enumeration
[enumerator] Successfully restored wlan2 to monitor mode
```

**Error Flow (Mode Restore Failure - CRITICAL):**
```
[enumerator] FAILED to restore wlan2 to monitor mode: [error]
[enumerator] Manual intervention required: iw wlan2 set monitor control
[enumerator] Emergency restore attempted with ifconfig/iwconfig
```

If you see the CRITICAL message, manually restore:
```bash
sudo ip link set wlan2 down
sudo iw wlan2 set monitor control
sudo ip link set wlan2 up
```

### Future Improvements

1. **4th Adapter:** If SSH kills still happen, add a dedicated enumeration adapter
2. **Connection Verification:** More robust checks after mode switching
3. **Timeout Tuning:** Adjust DHCP/connection timeouts based on real-world testing
4. **Parallel Operations:** Allow multiple scans if another adapter available

## Configuration

No config changes needed. System automatically uses:
- `config['wifi']['management_interface']` (wlan0) for SSH/management
- `config['wifi']['attack_interface']` (wlan2) for enumeration

## Rollback Plan

If issues occur, revert to wlan0 enumeration by changing line in enumerator.py:
```python
# Temporary rollback (will kill SSH):
self.enumeration_interface = config['wifi']['management_interface']
```

Better solution: Disable auto-scan in config.json:
```json
"enumeration": {
    "auto_scan_on_crack": false
}
```
