# WiFi Connectivity Issue - Deep Analysis

## Problem Statement

**Symptom**: After reboot, Raspberry Pi WiFi connects for approximately 5 pings (5-10 seconds), then completely disconnects and never reconnects.

**Environment**:
- Raspberry Pi OS Trixie (Debian 13) - Headless setup
- Built-in WiFi: brcmfmac driver (Broadcom)
- External WiFi: 2x RTL8812AU adapters
- Network management: NetworkManager + dhcpcd

## Root Cause Analysis

### Current Architecture (FLAWED)

```
Boot Sequence:
1. systemd starts
2. udev rules apply → WiFi interfaces named (wlan0 = built-in)
3. NetworkManager starts
4. WiFi connects successfully ✓
5. [~5 SECONDS LATER] ← CRITICAL TIMING
6. NetworkManager performs re-scan/reconfiguration
7. Driver reloads or interface state changes
8. Connection DROPS ✗
9. Never recovers (WiFi keeper service ineffective)
```

### Why Our Approach Fails

1. **Race Condition**: udev + NetworkManager + driver initialization creates unpredictable timing
2. **NetworkManager Interference**: Even with `unmanaged-devices`, NetworkManager still SCANS all interfaces during boot
3. **Driver Instability**: brcmfmac driver on Raspberry Pi is sensitive to configuration changes
4. **Service Timing**: Our WiFi keeper service runs AFTER NetworkManager has already disrupted the connection

### Evidence

From Pwnagotchi research (`builder/data/usr/bin/pwnlib`):
```bash
# Pwnagotchi checks interface state manually
is_interface_up() {
  if grep -qi 'up' /sys/class/net/$1/operstate; then
    return 0
  fi
  return 1
}

# They DON'T use NetworkManager for monitor interfaces
# They use ip commands directly:
ip -4 addr show wlan0 | grep inet >/dev/null 2>&1
```

From Pwnagotchi boot process:
- They create **mon0** (monitor interface) manually: `iw phy ... interface add mon0 type monitor`
- They use **bettercap** for WiFi management, NOT NetworkManager
- They have **conditional boot** based on interface state (AUTO vs MANU mode)

## Comparison: Proven Systems

### Pwnagotchi Architecture

```
Boot Flow:
1. systemd starts custom services
2. Check interface state BEFORE starting main services
3. Use bettercap (NOT NetworkManager) for WiFi
4. Manual interface management with ip/iw commands
5. Monitor mode: created dynamically, not renamed
```

**Key Differences**:
- No NetworkManager interference on wlan0
- Interface state checked BEFORE service start
- Manual control, no automatic scanning

### Kali Linux / Pentesting Distros

```
Common Pattern:
1. NetworkManager DISABLED for pentesting interfaces
2. systemd-networkd OR manual /etc/network/interfaces
3. rfkill management for WiFi state
4. Monitor mode managed by airmon-ng or manual iw commands
```

## Why 5-Second Disconnect Pattern?

The 5-second timing is **NOT random**. This matches typical systemd service startup delays:

```
Likely Culprits (check with `systemd-analyze blame`):
- NetworkManager.service (scans all interfaces ~3-5s after boot)
- wpa_supplicant.service (may restart/reconfigure)
- ModemManager.service (scans for modems, touches WiFi interfaces)
- systemd-networkd-wait-online.service (network state checks)
```

One of these services is touching wlan0 ~5 seconds after boot, causing the driver to reset.

## Proposed Solutions

### Option 1: Minimal Interference (Recommended)

**Concept**: Keep NetworkManager but prevent ANY scanning/reconfiguration during boot.

```bash
# Disable NetworkManager wake-on-lan and background scanning
[device]
wifi.scan-rand-mac-address=no
wifi.backend=wpa_supplicant

[connection]
wifi.powersave=2  # Disable powersave

# CRITICAL: Prevent NetworkManager from scanning during boot
[main]
dhcp=dhclient
no-auto-default=*

# Make wlan0 COMPLETELY unmanaged by NM during boot
[keyfile]
unmanaged-devices=mac:XX:XX:XX:XX:XX:XX  # Built-in WiFi MAC
```

**Additional Steps**:
1. Create systemd drop-in to delay NetworkManager start
2. Use `rfkill unblock wifi` BEFORE NetworkManager starts
3. Pre-configure wpa_supplicant with correct SSID

### Option 2: Hybrid Approach (Safer for Headless)

**Concept**: Use systemd-networkd for wlan0, NetworkManager for everything else.

```bash
# /etc/systemd/network/10-wlan0.network
[Match]
Name=wlan0

[Network]
DHCP=yes
MulticastDNS=yes

[DHCP]
RouteMetric=100
```

**Advantages**:
- systemd-networkd is MORE stable than NetworkManager
- Built-in to systemd, no extra services
- Less aggressive scanning behavior

**Configuration**:
```bash
# Disable NetworkManager for wlan0
nmcli device set wlan0 managed no

# Enable systemd-networkd
systemctl enable systemd-networkd
systemctl enable systemd-resolved

# Keep NetworkManager running for other features
systemctl enable NetworkManager
```

### Option 3: Pure Manual Control (Most Stable)

**Concept**: Completely disable automatic network management for wlan0.

```bash
# /etc/network/interfaces
auto wlan0
iface wlan0 inet dhcp
    wpa-ssid "YourSSID"
    wpa-psk "YourPassword"
    post-up rfkill unblock wifi
```

**Disable NetworkManager completely**:
```bash
systemctl disable NetworkManager
systemctl mask NetworkManager
```

**Use ifupdown** (Debian traditional):
```bash
apt-get install ifupdown
systemctl enable networking
```

## Debug Commands for User

To identify what's killing WiFi at the 5-second mark:

```bash
# 1. Check what happens around 5 seconds after boot
journalctl -b -u NetworkManager --since "5 seconds ago" --until "10 seconds ago"
journalctl -b -k --since "5 seconds ago" --until "10 seconds ago"  # Kernel messages

# 2. Check systemd service timing
systemd-analyze blame | head -20

# 3. Monitor interface state changes in real-time (during boot)
watch -n 0.1 'cat /sys/class/net/wlan0/operstate'

# 4. Check if NetworkManager is scanning
nmcli device | grep wlan0

# 5. Check for driver errors
dmesg | grep -i 'brcm\|wlan\|wifi'

# 6. Monitor NetworkManager logs during boot
journalctl -f -u NetworkManager &
# Then reboot and watch the logs
```

## Recommended Implementation Plan

**Phase 1: Immediate Diagnosis**
1. User runs debug commands to identify EXACT culprit
2. Confirm timing matches systemd service start
3. Identify which service touches wlan0 at 5-second mark

**Phase 2: Implement Hybrid Solution** (Safest for headless)
1. Switch wlan0 to systemd-networkd
2. Keep NetworkManager for user features (if needed)
3. Add systemd drop-in to prevent early scanning
4. Configure rfkill to unblock before network services

**Phase 3: Add Failsafe Recovery**
1. Create systemd service that monitors wlan0 state
2. If wlan0 goes down, trigger `systemctl restart systemd-networkd`
3. Log the event for debugging

## Example: Pwnagotchi Boot Script

From `builder/data/usr/bin/bettercap-launcher`:

```bash
# check if wifi driver is bugged
if ! check_brcm; then
  if ! reload_brcm; then
    echo "Could not reload wifi driver. Reboot"
    reboot
  fi
  sleep 10
fi

# start mon0 (monitor interface)
start_monitor_interface

# Start bettercap (NOT NetworkManager!)
if is_auto_mode_no_delete; then
  /usr/bin/bettercap -no-colors -caplet pwnagotchi-auto -iface mon0
else
  /usr/bin/bettercap -no-colors -caplet pwnagotchi-manual -iface mon0
fi
```

**Key Lesson**: They manage WiFi MANUALLY, not through automatic services.

## Critical Questions for User

1. **What is running at boot?**
   ```bash
   systemctl list-units --type=service --state=running
   ```

2. **Is ModemManager installed?** (Common culprit!)
   ```bash
   systemctl status ModemManager
   # If running: systemctl disable ModemManager
   ```

3. **What's in NetworkManager logs at 5-second mark?**
   ```bash
   journalctl -b -u NetworkManager | grep -A5 -B5 "wlan0"
   ```

4. **Is wpa_supplicant restarting?**
   ```bash
   journalctl -b -u wpa_supplicant
   ```

## Conclusion

Our current approach (udev + NetworkManager + auto-reconnect service) is **fundamentally flawed** because:

1. We're fighting AGAINST NetworkManager instead of working with it
2. We're trying to fix symptoms (reconnection) instead of root cause (interference)
3. Pentesting systems DON'T use NetworkManager for management interface

**The solution is NOT to add more services, but to REMOVE complexity:**
- Disable aggressive network scanning
- Use simpler network management (systemd-networkd or ifupdown)
- Prevent services from touching wlan0 during critical boot period
- Monitor driver state and reset if needed

The 5-second disconnect is **timing-based**, not configuration-based. We need to fix the TIMING, not add more configuration.
