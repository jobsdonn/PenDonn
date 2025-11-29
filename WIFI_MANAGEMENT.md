# PenDonn WiFi Management

## Simple & Stable Approach

PenDonn now uses a **simple, proven approach** for WiFi management based on the Ragnar project. No complex udev rules, no custom services fighting with NetworkManager - just clean configuration that works.

## How It Works

### Built-in WiFi (wlan0)
- **Managed by NetworkManager** - The system handles reconnection automatically
- **No udev rules** - Let interfaces be named naturally by the kernel
- **No custom services** - NetworkManager does the job better than custom scripts

### External WiFi Adapters (wlan1, wlan2)
- **Ignored by NetworkManager** - Won't try to manage them
- **Available for pentesting** - Use with airmon-ng, bettercap, etc.
- **No interference** - NetworkManager leaves them alone

### Key Configuration

`/etc/NetworkManager/NetworkManager.conf`:
```ini
[device]
wifi.scan-rand-mac-address=no  # Don't disrupt connection with scan MAC randomization
wifi.backend=wpa_supplicant     # Use stable backend

[connection]
wifi.powersave=2                # Disable WiFi power save (prevents disconnects)

[keyfile]
unmanaged-devices=interface-name:wlan1;interface-name:wlan2  # Don't manage pentesting interfaces
```

##Human: Scripts Removed

The following complex WiFi scripts have been **removed** because they were causing more problems than they solved:

- ❌ `auto-fix-wifi-interfaces.sh` - Caused race conditions during boot
- ❌ `fix-wifi-interfaces.sh` - Not needed with proper NM config
- ❌ `recover-wifi.sh` - NetworkManager handles recovery
- ❌ `troubleshoot-wifi.sh` - Use `diagnose-wifi-issue.sh` instead
- ❌ `quick-wifi-fix.sh` - Replaced by `cleanup-and-fix-wifi.sh`
- ❌ WiFi keeper service - NetworkManager reconnects automatically
- ❌ udev rules - They were causing timing issues

## Available Scripts

### cleanup-and-fix-wifi.sh
**Purpose**: Clean up old WiFi management and apply the new, simple approach

**When to use**: 
- After upgrading from old PenDonn version
- If WiFi is broken and you want a fresh start
- To remove all old complex WiFi code

**What it does**:
1. Removes old services and scripts
2. Removes udev rules
3. Configures NetworkManager properly
4. Disables ModemManager (causes WiFi issues)
5. Unblocks WiFi with rfkill

### diagnose-wifi-issue.sh  
**Purpose**: Diagnose WiFi problems with comprehensive logging

**When to use**:
- WiFi disconnects after reboot
- Investigating connection issues
- Before asking for help (share the report)

**Output**: Detailed report in `/tmp/pendonn-wifi-diagnosis-*.txt`

### detect-wifi-adapters.sh
**Purpose**: List all WiFi adapters with drivers and capabilities

**When to use**:
- Check which adapters are detected
- Verify external adapters are working
- Before pentesting operations

### install-wifi-drivers.sh
**Purpose**: Install drivers for common WiFi adapters

**When to use**:
- After plugging in new USB WiFi adapter
- To add support for specific chipsets

## Troubleshooting

### WiFi disconnects after reboot

**Most likely cause**: ModemManager is running

**Fix**:
```bash
sudo systemctl stop ModemManager
sudo systemctl disable ModemManager
sudo systemctl mask ModemManager
sudo reboot
```

### WiFi won't reconnect automatically

**Check if NetworkManager is managing wlan0**:
```bash
nmcli device status
# Should show wlan0 as "connected" or "connecting"
```

**If wlan0 shows "unmanaged"**:
```bash
sudo nmcli device set wlan0 managed yes
sudo nmcli device wifi connect "YourSSID" password "YourPassword"
```

### Can't SSH over ethernet

**Check network interfaces**:
```bash
ip addr show
# Should see eth0 with IP address
```

**If eth0 has no IP**:
```bash
# Enable eth0 in NetworkManager
sudo nmcli device set eth0 managed yes
sudo nmcli connection up "Wired connection 1"
```

### External WiFi adapters not working

**Check if they're detected**:
```bash
sudo ./scripts/detect-wifi-adapters.sh
```

**If not detected, install drivers**:
```bash
sudo ./scripts/install-wifi-drivers.sh
```

**Put in monitor mode**:
```bash
sudo airmon-ng start wlan1
# Should create wlan1mon
```

## NetworkManager Commands

### Check WiFi status
```bash
nmcli device status
nmcli device wifi list
```

### Connect to WiFi
```bash
nmcli device wifi connect "SSID" password "password"
```

### Forget network
```bash
nmcli connection delete "SSID"
```

### Reconnect to saved network
```bash
nmcli connection up "SSID"
```

### Show saved connections
```bash
nmcli connection show
```

## Why This Approach Works

1. **No race conditions** - NetworkManager waits for hardware to be ready
2. **No timing issues** - We don't fight with system services
3. **Proven stability** - Based on Ragnar (working Raspberry Pi pentesting system)
4. **Simpler code** - Less code = fewer bugs
5. **Better compatibility** - Works with system updates

## What Changed from Old Version

| Old Approach | New Approach |
|--------------|--------------|
| udev rules to force wlan0 naming | Let kernel name interfaces naturally |
| Custom WiFi keeper service | NetworkManager handles reconnection |
| Auto-fix service at boot | Not needed with proper NM config |
| Complex interface detection | NetworkManager knows what's what |
| Fighting with NetworkManager | Working WITH NetworkManager |

## For Developers

If you need to modify WiFi behavior:

1. **DON'T** add udev rules - they cause race conditions
2. **DON'T** create custom services - NM does it better
3. **DO** configure NetworkManager properly
4. **DO** test with `sudo systemctl restart NetworkManager`
5. **DO** check logs: `journalctl -u NetworkManager -f`

## Migration from Old Version

If you have an old PenDonn installation:

```bash
cd /opt/pendonn
sudo ./scripts/cleanup-and-fix-wifi.sh
sudo reboot
```

This will remove all old WiFi management and set up the new approach.
