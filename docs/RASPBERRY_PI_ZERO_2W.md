# Raspberry Pi Zero 2 W Setup Guide

## Overview

This guide covers running PenDonn on **Raspberry Pi Zero 2 W** with **only the onboard WiFi adapter** (no external adapters).

## Hardware Specifications

- **CPU**: Quad-core ARM Cortex-A53 @ 1GHz
- **RAM**: 512MB
- **WiFi**: 2.4GHz 802.11b/g/n (Broadcom BCM43436)
- **Interface**: `wlan0` (onboard)

## ⚠️ Important Limitations

### Single WiFi Interface Challenge

The RPi Zero 2 W has **only one WiFi adapter** (wlan0), which creates a fundamental trade-off:

1. **Monitor Mode** = Cannot maintain SSH connection
2. **Managed Mode** = Cannot capture handshakes

### Operating Modes

#### Option 1: Headless Auto-Start (Recommended)
- Configure PenDonn to auto-start on boot
- System loses SSH but continues operating
- View results via OLED display
- Collect data by shutting down and accessing SD card

#### Option 2: Local Access
- Connect HDMI monitor + USB keyboard
- Start PenDonn manually from local terminal
- Monitor via display or screen output

#### Option 3: Hybrid Mode (Advanced)
- Use systemd timer to toggle between modes
- Monitor for X minutes, then switch to managed for SSH access
- Download data, then restart monitoring

## Configuration

### 1. Use RPi Zero 2 W Config

```bash
cd /home/pi/PenDonn
cp config/config.rpi_zero2w.json config/config.json
```

### 2. Key Configuration Options

```json
{
  "wifi": {
    "monitor_interface": "wlan0",
    "attack_interface": "wlan0",
    "single_interface_mode": true,
    "allow_management_wifi": true
  },
  "cracking": {
    "max_concurrent_cracks": 1,
    "brute_max_length": 6
  },
  "enumeration": {
    "enabled": false
  }
}
```

### 3. Performance Tuning

Due to limited CPU/RAM:
- **Max concurrent cracks**: 1 (vs 2 on RPi 4)
- **Brute force length**: 6 (vs 8 on RPi 4)
- **Enumeration**: Disabled by default
- **nmap timing**: T2 (slower) if enabled

## Installation

### 1. Base System Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y \
  python3-pip \
  python3-venv \
  aircrack-ng \
  john \
  hashcat \
  hcxtools \
  wireless-tools \
  net-tools \
  sqlite3

# Install Python packages
cd /home/pi/PenDonn
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. OLED Display Setup

```bash
# Enable I2C
sudo raspi-config
# Navigate to: Interface Options -> I2C -> Enable

# Install display libraries
pip install adafruit-circuitpython-ssd1306 pillow

# Test display
python3 tests/test_display.py
```

### 3. Auto-Start Configuration

Create systemd service:

```bash
sudo nano /etc/systemd/system/pendonn.service
```

```ini
[Unit]
Description=PenDonn WiFi Security Auditing Tool
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/pi/PenDonn
ExecStart=/home/pi/PenDonn/.venv/bin/python3 main.py
Restart=on-failure
RestartSec=10

# Environment
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable pendonn.service
sudo systemctl start pendonn.service
```

### 4. Check Status

```bash
sudo systemctl status pendonn.service
journalctl -u pendonn.service -f
```

## Usage Workflow

### Headless Operation

1. **Setup Phase** (with SSH):
   ```bash
   ssh pi@raspberrypi.local
   cd /home/pi/PenDonn
   
   # Configure whitelist (optional)
   nano config/config.json
   # Add your networks to whitelist.ssids
   
   # Enable auto-start
   sudo systemctl enable pendonn.service
   ```

2. **Deploy**:
   ```bash
   # Reboot to start PenDonn
   sudo reboot
   
   # SSH connection will be lost when monitoring starts!
   # Monitor via OLED display
   ```

3. **Collection Phase**:
   ```bash
   # Safely shutdown
   # Option A: Hold button if configured
   # Option B: Power off after sufficient time
   
   sudo shutdown -h now
   ```

4. **Data Retrieval**:
   ```bash
   # Remove SD card, mount on computer
   # Access: /home/pi/PenDonn/
   #   - pendonn.db (database)
   #   - handshakes/*.cap (captures)
   #   - logs/*.log (logs)
   ```

### Local Access Operation

1. **Connect Hardware**:
   - HDMI monitor
   - USB hub + keyboard
   - Power supply

2. **Start PenDonn**:
   ```bash
   cd /home/pi/PenDonn
   source .venv/bin/activate
   sudo python3 main.py
   ```

3. **Monitor Output**:
   - Terminal output
   - OLED display
   - Database: `sqlite3 pendonn.db`

4. **Stop**:
   ```bash
   # Press Ctrl+C
   # Or wait for completion
   ```

## Monitoring Progress

### Via OLED Display

The SSD1306 display shows:
```
PenDonn v1.0
Networks: 12
Captured: 5
Cracked: 3/5
Status: Scanning
```

### Via Logs (SD Card Access)

```bash
# Mount SD card on computer
cat /mnt/sdcard/home/pi/PenDonn/logs/pendonn.log
```

### Via Database

```bash
sqlite3 pendonn.db

-- Check networks
SELECT ssid, bssid, first_seen FROM networks;

-- Check handshakes
SELECT h.id, n.ssid, h.status, h.captured_at 
FROM handshakes h 
JOIN networks n ON h.network_id = n.id;

-- Check cracked passwords
SELECT n.ssid, c.password, c.cracked_at
FROM cracked_passwords c
JOIN networks n ON c.network_id = n.id;
```

## Performance Expectations

### Capture Performance
- **Channel hopping**: ~2 seconds per channel
- **Handshake capture**: 80% success rate
- **Deauth effectiveness**: Similar to external adapters

### Cracking Performance
- **Dictionary attack**: ~1000-5000 passwords/sec (hashcat)
- **Rule-based**: ~500-2000 passwords/sec
- **Brute force**: Not recommended (too slow)
- **Recommended**: Use dictionary + rules only

### Resource Usage
- **CPU**: 50-80% during cracking
- **RAM**: 200-300MB
- **Storage**: 10MB per hour (handshakes + logs)
- **Power**: ~2.5W (500mA @ 5V)

## Troubleshooting

### Issue: WiFi Not Entering Monitor Mode

```bash
# Check interface
iw dev

# Manual monitor mode
sudo ip link set wlan0 down
sudo iw wlan0 set monitor control
sudo ip link set wlan0 up

# Verify
iw wlan0 info
```

### Issue: No Handshakes Captured

```bash
# Check if interface is monitoring
sudo airodump-ng wlan0

# Check if deauth is working
sudo aireplay-ng --deauth 10 -a [BSSID] wlan0
```

### Issue: Cracking Too Slow

Edit `config/config.json`:
```json
{
  "cracking": {
    "engines": ["john"],
    "max_concurrent_cracks": 1,
    "brute_force": false
  }
}
```

### Issue: System Freezing

Reduce concurrent operations:
```json
{
  "performance": {
    "max_threads": 1,
    "low_memory_mode": true
  },
  "cracking": {
    "max_concurrent_cracks": 1
  }
}
```

## Security Notes

### Legal Considerations
- Only test networks you own or have permission
- Enable whitelist for authorized testing
- Check local laws regarding WiFi security testing

### SSH Access
When running in single_interface_mode:
1. SSH connection will be **lost** when monitoring starts
2. Cannot SSH while in monitor mode
3. Must reboot to regain SSH access

### Safe Shutdown
```bash
# ALWAYS use safe shutdown
sudo shutdown -h now

# Do NOT just pull power (can corrupt SD card)
```

## Optimization Tips

### 1. Wordlist Selection
```bash
# Use smaller, targeted wordlists
# Download common password lists
wget https://github.com/danielmiessler/SecLists/raw/master/Passwords/Common-Credentials/10-million-password-list-top-10000.txt
```

### 2. Rule Files
```bash
# Use lightweight rules
mkdir -p rules
cp /usr/share/hashcat/rules/best64.rule rules/
```

### 3. Storage Management
```bash
# Compress old logs
gzip logs/*.log

# Archive old handshakes
tar -czf handshakes_backup.tar.gz handshakes/
```

### 4. Power Management
```bash
# Disable HDMI to save power (headless)
/usr/bin/tvservice -o

# Disable Bluetooth
sudo systemctl disable hciuart
```

## Comparison: RPi Zero 2 W vs RPi 4

| Feature | RPi Zero 2 W | RPi 4 (2GB+) |
|---------|--------------|--------------|
| **WiFi Adapters** | 1 (onboard) | 1 onboard + 2 external |
| **Monitor Mode** | Yes (loses SSH) | Yes (external adapters) |
| **Cracking Speed** | 1K-5K pwd/sec | 10K-50K pwd/sec |
| **Concurrent Cracks** | 1 | 2-4 |
| **Enumeration** | Limited | Full |
| **Power** | 2.5W | 6-8W |
| **Portability** | Excellent | Good |
| **Cost** | $15 | $35-75 |

## Recommended Use Cases

### ✅ Good For
- Portable security auditing
- Personal network testing
- Educational demonstrations
- Battery-powered deployments
- Covert testing (small form factor)

### ❌ Not Ideal For
- Large-scale pentesting
- Complex password cracking
- Network enumeration
- Real-time monitoring (no SSH)
- Multi-network attacks

## Advanced: Hybrid Mode Script

Create `/home/pi/toggle_mode.sh`:

```bash
#!/bin/bash
# Toggle between monitor and managed mode

MODE=$1

if [ "$MODE" == "monitor" ]; then
    sudo systemctl start pendonn.service
    echo "Switched to MONITOR mode - SSH will disconnect!"
elif [ "$MODE" == "managed" ]; then
    sudo systemctl stop pendonn.service
    sudo ip link set wlan0 down
    sudo iw wlan0 set type managed
    sudo ip link set wlan0 up
    sudo dhclient wlan0
    echo "Switched to MANAGED mode - SSH available"
else
    echo "Usage: $0 [monitor|managed]"
fi
```

## Summary

The Raspberry Pi Zero 2 W can run PenDonn effectively with these considerations:

1. **Single interface limitation** - Must choose between SSH and monitoring
2. **Headless operation** - Best deployed with auto-start
3. **Performance tuning** - Adjust cracking parameters for limited resources
4. **Local access** - HDMI+keyboard for real-time interaction
5. **Data collection** - SD card access for results

For maximum effectiveness, consider:
- Using targeted wordlists
- Enabling auto-start for unattended operation
- Monitoring via OLED display
- Collecting data via SD card removal

For production pentesting with SSH access, consider upgrading to RPi 4 with external WiFi adapters.
