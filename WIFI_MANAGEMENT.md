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

## Available Scripts

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

The installer now handles all WiFi configuration automatically. If you experience issues:

1. **Check services are disabled**:
```bash
systemctl status pendonn pendonn-web
# Should show "disabled" and "inactive (dead)"
```

2. **Verify NetworkManager is running**:
```bash
systemctl status NetworkManager
```

3. **Check diagnostic logs**:
```bash
cat /var/log/pendonn-boot-diagnostics.log
```

### WiFi dies when starting PenDonn

**Make sure external WiFi adapters are plugged in**:
```bash
ip link show | grep wlan
# Should show wlan0 (onboard), wlan1 and wlan2 (external)
```

**Check the logs**:
```bash
sudo journalctl -u pendonn -f
```

PenDonn will refuse to start if external adapters aren't detected, preventing your SSH connection from dying.

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

If you have an old PenDonn installation, run a fresh install:

```bash
cd ~/pendonn
sudo ./scripts/install.sh
```

The installer now includes all WiFi fixes and proper configuration.

