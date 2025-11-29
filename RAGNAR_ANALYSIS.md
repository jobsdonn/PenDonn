# Ragnar Analysis - Key Learnings for PenDonn WiFi

## Overview

The Ragnar project (https://github.com/PierreGode/Ragnar) is a Raspberry Pi IoT security tool with **robust WiFi management** that successfully handles the exact same challenges we face:
- Built-in WiFi for management
- External adapters for pentesting
- Automatic reconnection on boot
- AP fallback mode

## Critical Insights

### 1. Work WITH NetworkManager, Not Against It

**Ragnar's Approach:**
```python
# They DON'T try to control interfaces manually
# They simply enable WiFi and let NetworkManager do its job
subprocess.run(['sudo', 'nmcli', 'radio', 'wifi', 'on'])
subprocess.run(['sudo', 'nmcli', 'dev', 'set', 'wlan0', 'managed', 'yes'])

# Then they WAIT for automatic connection (up to 60 seconds)
# NetworkManager handles the actual connection logic
```

**Our Current Problem:**
We're fighting NetworkManager with udev rules and custom services, creating race conditions.

**Solution:**
Let NetworkManager manage wlan0, just configure it properly to prevent interference.

### 2. Detect Fresh Boot vs Service Restart

**Ragnar's Method:**
```python
def _is_fresh_boot(self):
    # Check system uptime (< 5 minutes = fresh boot)
    with open('/proc/uptime', 'r') as f:
        uptime_seconds = float(f.read().split()[0])
    
    if uptime_seconds < 300:
        return True
    
    # Check when NetworkManager started
    result = subprocess.run(['systemctl', 'show', 'NetworkManager', 
                           '--property=ActiveEnterTimestamp'])
```

**Why This Matters:**
- Fresh boot: Wait longer for NetworkManager to stabilize
- Service restart: Can reconnect immediately
- Prevents our 5-second race condition!

### 3. Query Existing NetworkManager Profiles

**Ragnar's Approach:**
```python
def get_system_wifi_profiles(self):
    """Get existing WiFi profiles instead of creating new ones"""
    result = subprocess.run(['nmcli', '-t', '-f', 'NAME,TYPE', 'con', 'show'])
    
    # Parse existing profiles
    wifi_profiles = []
    for line in result.stdout.strip().split('\n'):
        if parts[1] == '802-11-wireless':
            wifi_profiles.append(parts[0])
    
    return wifi_profiles
```

**Our Current Problem:**
We create new connections each time, potentially conflicting with existing profiles.

**Solution:**
Check if profile exists first, use `nmcli con up <profile>` instead of creating new.

### 4. Critical NetworkManager Settings

**Ragnar's /etc/NetworkManager/NetworkManager.conf:**
```ini
[main]
plugins=ifupdown,keyfile
dhcp=dhclient

[device]
wifi.scan-rand-mac-address=no  # CRITICAL!
# Random MAC scanning can disrupt connections

[connection]
wifi.cloned-mac-address=preserve  # Don't change MAC
wifi.powersave=2  # Disable WiFi powersave (can cause disconnects)
```

**Settings We're Missing:**
- `wifi.scan-rand-mac-address=no` - Stops disruptive scanning
- `wifi.powersave=2` - Prevents power-saving disconnects

### 5. rfkill Management

**Ragnar Always Checks:**
```bash
# In install script
if command -v rfkill >/dev/null 2>&1; then
    rfkill unblock wifi
fi

# They verify WiFi isn't soft-blocked
```

**Our Gap:**
We never check if WiFi is rfkill-blocked, which could cause "mystery" disconnects.

### 6. Service Timing and Dependencies

**Ragnar's Service File:**
```ini
[Unit]
Description=Ragnar WiFi Management
After=network.target NetworkManager.service
Wants=network.target
Requires=NetworkManager.service

[Service]
Type=simple
Restart=always
RestartSec=5
ExecStartPre=/bin/sleep 10  # Wait for NetworkManager to stabilize!
```

**Key Differences:**
- `After=NetworkManager.service` - Waits for NM to start
- `ExecStartPre=/bin/sleep 10` - Gives NM time to settle
- `Restart=always` - Auto-recovers from failures

**Our Service:**
Starts too early, before NetworkManager is fully ready.

### 7. Connection Verification

**Ragnar's Multi-Method Check:**
```python
def check_wifi_connection(self):
    # Method 1: nmcli active connections
    result = subprocess.run(['nmcli', '-t', '-f', 'ACTIVE,TYPE', 'con', 'show'])
    if 'yes:802-11-wireless' in result.stdout:
        # Method 2: Verify device status
        dev_result = subprocess.run(['nmcli', '-t', '-f', 'DEVICE,STATE', 'dev', 'wifi'])
        if 'connected' in dev_result.stdout:
            return True
    
    # Method 3: Check iwconfig as fallback
    result = subprocess.run(['iwconfig', 'wlan0'])
    if 'ESSID:' in result.stdout and 'off/any' not in result.stdout:
        return True
    
    return False
```

**Multiple verification methods prevent false positives!**

### 8. AP Mode Interface Handling

**Ragnar's Clean Approach:**
```python
# Before starting AP:
1. Stop NetworkManager management
   subprocess.run(['sudo', 'nmcli', 'dev', 'set', 'wlan0', 'managed', 'no'])

2. Configure interface manually
   subprocess.run(['sudo', 'ip', 'addr', 'flush', 'dev', 'wlan0'])
   subprocess.run(['sudo', 'ip', 'addr', 'add', '192.168.4.1/24', 'dev', 'wlan0'])

3. Start hostapd/dnsmasq

# After stopping AP:
1. Stop services
2. Flush interface
3. Return to NetworkManager control
   subprocess.run(['sudo', 'nmcli', 'dev', 'set', 'wlan0', 'managed', 'yes'])
```

**Clean state transitions prevent interface conflicts.**

## Recommended Changes for PenDonn

### Priority 1: Fix NetworkManager Configuration

Add to `/etc/NetworkManager/NetworkManager.conf`:
```ini
[device]
wifi.scan-rand-mac-address=no
wifi.backend=wpa_supplicant

[connection]
wifi.powersave=2
wifi.cloned-mac-address=preserve
```

### Priority 2: Add Boot Detection

Add to WiFi keeper service:
```python
def is_fresh_boot():
    with open('/proc/uptime', 'r') as f:
        uptime = float(f.read().split()[0])
    return uptime < 300  # Less than 5 minutes

if is_fresh_boot():
    # Wait longer for NetworkManager to stabilize
    time.sleep(15)
else:
    # Quick reconnect
    time.sleep(5)
```

### Priority 3: Use Existing Profiles

Change connection logic:
```python
# Check if profile exists
result = subprocess.run(['nmcli', 'con', 'show', ssid])
if result.returncode == 0:
    # Use existing profile
    subprocess.run(['nmcli', 'con', 'up', ssid])
else:
    # Create new profile
    subprocess.run(['nmcli', 'dev', 'wifi', 'connect', ssid, 'password', password])
```

### Priority 4: Add rfkill Check

Add to startup:
```bash
# Ensure WiFi is not blocked
rfkill unblock wifi

# Verify
if rfkill list wifi | grep -q "Soft blocked: yes"; then
    echo "WARNING: WiFi still blocked!"
fi
```

### Priority 5: Fix Service Timing

Update systemd service:
```ini
[Unit]
After=network.target NetworkManager.service
Wants=network.target
Requires=NetworkManager.service

[Service]
ExecStartPre=/bin/sleep 10
Restart=always
RestartSec=10
```

## Why Ragnar Works and We Don't

| Aspect | PenDonn (Current) | Ragnar (Working) |
|--------|-------------------|------------------|
| **NetworkManager** | Fight against it with udev | Work with it, configure properly |
| **Boot Detection** | None - same logic always | Detect fresh boot, adjust timing |
| **Connection** | Create new profiles | Use existing profiles when available |
| **WiFi Scanning** | Random MAC enabled | Disabled (`wifi.scan-rand-mac-address=no`) |
| **Power Save** | System default | Explicitly disabled |
| **Service Timing** | Start immediately | Wait 10s for NM to stabilize |
| **rfkill** | Never checked | Always unblock WiFi |
| **Verification** | Single method | Multiple verification methods |

## The Root Cause

Your 5-second disconnect is likely:

1. **NetworkManager re-scanning** with random MAC addresses
   - This temporarily disrupts the connection
   - Ragnar disables this: `wifi.scan-rand-mac-address=no`

2. **Service timing race**
   - Your WiFi keeper starts before NetworkManager is stable
   - Ragnar waits 10 seconds: `ExecStartPre=/bin/sleep 10`

3. **WiFi power-save kicking in**
   - Default power-save can disconnect WiFi
   - Ragnar disables it: `wifi.powersave=2`

## Implementation Strategy

1. **Immediate (Test on Pi):**
   ```bash
   # Add to NetworkManager config
   sudo bash -c 'cat >> /etc/NetworkManager/NetworkManager.conf << EOF
   
   [device]
   wifi.scan-rand-mac-address=no
   
   [connection]
   wifi.powersave=2
   EOF'
   
   # Restart NetworkManager
   sudo systemctl restart NetworkManager
   
   # Reboot and test
   sudo reboot
   ```

2. **If that fixes it:**
   - Update installer to include these settings
   - Remove udev rules (not needed if NM is configured right)
   - Simplify WiFi keeper service

3. **If still issues:**
   - Implement boot detection
   - Add 10-second delay to service startup
   - Add rfkill check

## Conclusion

Ragnar proves that **NetworkManager CAN be stable** on Raspberry Pi for pentesting use cases. The key is:
- Configure it correctly (disable disruptive features)
- Work with it instead of against it
- Proper timing (wait for it to stabilize on boot)
- Check for system-level issues (rfkill, powersave)

Our current approach of fighting NetworkManager with udev rules and custom services is creating the race condition that causes the 5-second disconnect.

**Next Steps:**
1. Test NetworkManager config changes immediately
2. If successful, refactor installer to use Ragnar's approach
3. Simplify architecture by removing unnecessary complexity
