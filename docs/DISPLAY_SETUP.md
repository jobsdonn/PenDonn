# Waveshare 7.3inch ACeP E-Paper Display Setup

## Hardware Information

**Model:** Waveshare 7.3inch ACeP 7-Color E-Paper Display  
**Resolution:** 800×480 pixels  
**Colors:** 7 colors (Black, White, Red, Green, Blue, Yellow, Orange)  
**Interface:** SPI  
**Refresh Time:** ~30 seconds (full refresh)

## Hardware Connection

Connect the display to Raspberry Pi GPIO pins:

| E-Paper Pin | RPi Pin | Description |
|-------------|---------|-------------|
| VCC | 3.3V | Power |
| GND | GND | Ground |
| DIN | GPIO 10 (MOSI) | SPI Data In |
| CLK | GPIO 11 (SCLK) | SPI Clock |
| CS | GPIO 8 (CE0) | Chip Select |
| DC | GPIO 25 | Data/Command |
| RST | GPIO 17 | Reset |
| BUSY | GPIO 24 | Busy Status |

## Software Installation

### 1. Enable SPI Interface

```bash
sudo raspi-config
# Navigate to: Interface Options → SPI → Enable
```

### 2. Install Required Packages

```bash
# System dependencies
sudo apt-get update
sudo apt-get install -y python3-pip python3-pil python3-numpy

# Python libraries
pip3 install pillow spidev RPi.GPIO
```

### 3. Install Waveshare E-Paper Library

```bash
# Clone Waveshare library
cd /tmp
git clone https://github.com/waveshare/e-Paper.git
cd e-Paper/RaspberryPi_JetsonNano/python

# Install library
sudo python3 setup.py install

# Or copy manually
sudo mkdir -p /usr/local/lib/waveshare_epd
sudo cp -r lib/waveshare_epd/* /usr/local/lib/waveshare_epd/
```

### 4. Test Display

```bash
# Test with Waveshare examples
cd /tmp/e-Paper/RaspberryPi_JetsonNano/python/examples
python3 epd_7in3e_test.py
```

### 5. Configure PenDonn

Edit `/opt/pendonn/config/config.json`:

```json
{
  "display": {
    "enabled": true,
    "type": "waveshare_v4",
    "refresh_interval": 30
  }
}
```

### 6. Test PenDonn Display

```bash
# Test display module
cd /opt/pendonn
sudo python3 -m core.display

# Or restart PenDonn service
sudo systemctl restart pendonn
```

## Display Features

The PenDonn display shows:

- **Header:** System name, version, IP address, timestamp
- **Statistics:** 
  - Networks discovered
  - Handshakes captured
  - Passwords cracked
  - Scans completed
  - Vulnerabilities found
  - Critical vulnerabilities (highlighted)
- **Status Bar:** Current system status and active processes
- **Color Coding:**
  - 🔵 Blue: Network statistics
  - 🟢 Green: Success metrics (handshakes, active status)
  - 🔴 Red: Security findings (passwords, critical issues)
  - 🟠 Orange: Enumeration scans
  - 🟡 Yellow: Vulnerabilities

## Troubleshooting

### Display Not Working

1. **Check SPI is enabled:**
   ```bash
   lsmod | grep spi
   # Should show: spi_bcm2835
   ```

2. **Verify connections:**
   ```bash
   # Test GPIO access
   sudo python3 -c "import RPi.GPIO as GPIO; GPIO.setmode(GPIO.BCM); print('GPIO OK')"
   ```

3. **Check library installation:**
   ```bash
   python3 -c "from waveshare_epd import epd7in3e; print('Waveshare library OK')"
   ```

4. **View PenDonn logs:**
   ```bash
   sudo journalctl -u pendonn -f
   ```

### Display Shows Random Pixels

- Perform a clear operation:
  ```bash
  cd /tmp/e-Paper/RaspberryPi_JetsonNano/python/examples
  python3 epd_7in3e_test.py
  ```

### Slow Refresh

- This is normal! E-Paper displays refresh slowly (~30 seconds)
- Adjust `refresh_interval` in config to reduce updates
- Consider 60-120 seconds for stable operation

### Image Saved to /tmp Instead

- This means the Waveshare library is not installed
- Display will save preview images to `/tmp/pendonn_display.png`
- Follow installation steps above

## Performance Tips

1. **Set appropriate refresh interval:**
   - Recommended: 30-60 seconds
   - E-Paper has limited refresh cycles (~100,000)

2. **Reduce wear:**
   - Don't refresh too frequently
   - Display sleeps when service stops

3. **Power consumption:**
   - E-Paper only uses power during refresh
   - ~100mA during update, 0mA when static

## Display API

### Show Custom Message

```python
from core.display import Display

# In your code
display.show_message("Scan Complete!", duration=5, message_type="success")

# Message types: 'info', 'success', 'warning', 'error'
```

### Manual Refresh

```python
display._render_display()
```

## References

- [Waveshare 7.3inch ACeP Datasheet](https://www.waveshare.com/wiki/7.3inch_e-Paper_HAT)
- [Waveshare Python Library](https://github.com/waveshare/e-Paper)
- [RPi.GPIO Documentation](https://sourceforge.net/p/raspberry-gpio-python/wiki/Home/)
