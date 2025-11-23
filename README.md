# PenDonn - Automated Penetration Testing System

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.9+-green)
![License](https://img.shields.io/badge/license-Educational-red)

**PenDonn** is an automated penetration testing tool designed for Raspberry Pi 4/5 with dual external WiFi adapters and Waveshare V4 display. It automates the process of WiFi network discovery, handshake capture, password cracking, and network enumeration with a dynamic plugin system for vulnerability scanning.

📁 **[Project Structure Documentation](PROJECT_STRUCTURE.md)** - Detailed explanation of directory organization

## ⚠️ LEGAL DISCLAIMER

**THIS TOOL IS FOR AUTHORIZED PENETRATION TESTING ONLY**

By downloading, installing, or using this software, you agree that:

1. ✅ You will **ONLY** use this tool on networks you **OWN** or have **EXPLICIT WRITTEN PERMISSION** to test
2. 🚫 Unauthorized access to computer networks is **ILLEGAL** in most jurisdictions
3. ⚖️ You take **FULL RESPONSIBILITY** for your actions with this tool
4. 🛡️ The developers assume **NO LIABILITY** for misuse of this software
5. 📜 You will comply with all applicable local, state, national, and international laws

**Use at your own risk. Unauthorized network penetration is a criminal offense.**

---

## 🎯 Features

### Core Functionality
- 📡 **WiFi Network Discovery** - Automatically discovers and monitors WiFi networks
- 🤝 **Handshake Capture** - Captures WPA/WPA2 handshakes using deauthentication
- 🔓 **Password Cracking** - Automated cracking with John the Ripper and Hashcat
- 🔍 **Network Enumeration** - Comprehensive network scanning with Nmap
- 🔌 **Plugin System** - Dynamic plugin architecture for custom vulnerability scanners
- 🌐 **Web Interface** - Full-featured web dashboard for monitoring and control
- 📊 **Display Output** - Real-time status on Waveshare V4 display
- 💾 **Data Export** - Export all results to JSON with database backup

### Advanced Features
- 📋 **Whitelist System** - Protect your own networks from scanning
- 🔄 **Auto-Start** - Runs on boot via systemd services
- 📈 **Statistics Tracking** - Comprehensive metrics and logging
- 🗃️ **SQLite Database** - Stores all networks, handshakes, passwords, and vulnerabilities
- 🔌 **3 Built-in Plugins** - SMB, Web, and SSH vulnerability scanners included

---

## 🛠️ Hardware Requirements

### Required Hardware
- **Raspberry Pi 4 or 5** (4GB+ RAM recommended)
- **2x External WiFi Adapters** (monitor mode capable)
  - Recommended: Alfa AWUS036ACH, TP-Link TL-WN722N v1
  - Must support monitor mode and packet injection
- **Waveshare V4 Display** (optional but recommended)
- **MicroSD Card** (32GB+ recommended)
- **Power Supply** (Official RPi power supply recommended)

### Recommended Accessories
- Cooling fan or heatsinks for Raspberry Pi
- Portable battery pack for mobile operations
- Case with ventilation

---

## 📦 Installation

### Prerequisites

1. **Install Raspberry Pi OS Trixie** (latest version)
   ```bash
   # Use Raspberry Pi Imager to flash the latest Raspberry Pi OS
   ```

2. **Enable SSH** (for headless operation)
   ```bash
   sudo systemctl enable ssh
   sudo systemctl start ssh
   ```

3. **Update System**
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

### Quick Install

#### For Raspberry Pi (Production):

1. **Clone the repository**
   ```bash
   cd ~
   git clone https://github.com/yourusername/pendonn.git
   cd pendonn
   ```

2. **Run the installer**
   ```bash
   chmod +x scripts/install.sh
   sudo scripts/install.sh
   ```

3. **The installer will:**
   - ✅ Install all system dependencies
   - ✅ Set up Python virtual environment
   - ✅ Download wordlists (rockyou.txt)
   - ✅ Configure systemd services
   - ✅ Initialize the database
   - ✅ Detect WiFi interfaces
   - ✅ Start services automatically

#### For Development/Testing (Windows/Linux/macOS):

**🐛 Debug Mode** - Test PenDonn without hardware requirements!

```bash
# Install dependencies
pip install -r requirements.txt

# Run in debug mode
python main.py --debug

# Or use the launcher (Windows)
.\start-debug.ps1
```

**Features of Debug Mode:**
- ✅ No root/sudo required
- ✅ No hardware dependencies
- ✅ Simulates WiFi scanning and handshake capture
- ✅ Mock password cracking with test data
- ✅ Full web interface functionality
- ✅ Works on any OS (Windows/Linux/macOS)

**📚 See [DEBUG_QUICKSTART.md](DEBUG_QUICKSTART.md) and [TESTING.md](TESTING.md) for complete testing guide**

### Post-Installation Configuration

1. **Configure WiFi Interfaces**
   ```bash
   sudo nano /opt/pendonn/config/config.json
   ```

   Update the interface names:
   ```json
   {
     "wifi": {
       "monitor_interface": "wlan1",    // External WiFi 1
       "attack_interface": "wlan2",      // External WiFi 2
       "management_interface": "wlan0"   // Onboard WiFi
     }
   }
   ```

2. **Add Your Networks to Whitelist**
   ```json
   {
     "whitelist": {
       "ssids": ["YourHomeNetwork", "YourWorkNetwork"]
     }
   }
   ```

3. **Change Web Interface Secret Key**
   ```json
   {
     "web": {
       "secret_key": "YOUR_RANDOM_SECRET_KEY_HERE"
     }
   }
   ```

4. **Restart Services**
   ```bash
   sudo systemctl restart pendonn pendonn-web
   ```

---

## 🚀 Usage

### Service Management

```bash
# Start services
sudo systemctl start pendonn pendonn-web

# Stop services
sudo systemctl stop pendonn pendonn-web

# Restart services
sudo systemctl restart pendonn pendonn-web

# Check status
sudo systemctl status pendonn
sudo systemctl status pendonn-web

# View logs
sudo journalctl -u pendonn -f
sudo journalctl -u pendonn-web -f
```

### Web Interface

1. **Access the dashboard**
   - On the RPi: `http://localhost:8080`
   - From another device: `http://<raspberry-pi-ip>:8080`

2. **Dashboard Features**
   - 📊 Real-time statistics
   - 📡 Discovered networks
   - 🤝 Captured handshakes
   - 🔓 Cracked passwords
   - 🔍 Network scans
   - 🔴 Vulnerabilities
   - ⚙️ Configuration management

### Command Line Operations

```bash
# Manual mode (not recommended, use services instead)
cd /opt/pendonn
sudo python3 main.py

# Export data
curl -X POST http://localhost:8080/api/export --output export.json

# Check statistics
curl http://localhost:8080/api/status | jq
```

---

## 🔌 Plugin Development

### Creating a Custom Plugin

1. **Create plugin directory**
   ```bash
   mkdir /opt/pendonn/plugins/my_scanner
   ```

2. **Create plugin.json**
   ```json
   {
     "name": "My Custom Scanner",
     "version": "1.0.0",
     "description": "Description of what it does",
     "author": "Your Name",
     "enabled": true,
     "module": "my_scanner.py",
     "class": "MyScanner"
   }
   ```

3. **Create plugin module (my_scanner.py)**
   ```python
   import sys
   import os
   sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
   from core.plugin_manager import PluginBase
   
   class MyScanner(PluginBase):
       """My custom vulnerability scanner"""
       
       def run(self, scan_id, hosts, scan_results):
           """
           Execute scanning logic
           
           Args:
               scan_id: Database scan ID
               hosts: List of IP addresses
               scan_results: Nmap results
           
           Returns:
               {'vulnerabilities': count, 'results': [...]}
           """
           self.log_info("Starting my scan")
           
           vulnerabilities_found = 0
           
           # Your scanning logic here
           for host in hosts:
               # Check for vulnerabilities
               if self.check_vulnerability(host):
                   # Add to database
                   self.db.add_vulnerability(
                       scan_id=scan_id,
                       host=host,
                       port=1234,
                       service='myservice',
                       vuln_type='My Vulnerability',
                       severity='high',
                       description='Vulnerability description',
                       plugin_name=self.name
                   )
                   vulnerabilities_found += 1
           
           return {
               'vulnerabilities': vulnerabilities_found,
               'results': []
           }
       
       def check_vulnerability(self, host):
           # Your checking logic
           return False
   ```

4. **Reload plugins**
   ```bash
   sudo systemctl restart pendonn
   ```

### Plugin API Reference

**Available Methods:**
- `self.log_info(message)` - Log info message
- `self.log_warning(message)` - Log warning
- `self.log_error(message)` - Log error
- `self.db` - Database instance for adding vulnerabilities

**Database Methods:**
- `self.db.add_vulnerability(scan_id, host, port, service, vuln_type, severity, description, plugin_name)`

**Severity Levels:** `critical`, `high`, `medium`, `low`

---

## 📁 Project Structure

```
pendonn/
├── config/
│   └── config.json              # Main configuration
├── core/
│   ├── database.py              # SQLite database handler
│   ├── wifi_monitor.py          # WiFi scanning & handshake capture
│   ├── cracker.py               # Password cracking engine
│   ├── enumerator.py            # Network enumeration
│   ├── plugin_manager.py        # Plugin system
│   └── display.py               # Waveshare display
├── web/
│   ├── app.py                   # Flask web server
│   └── templates/
│       └── index.html           # Web dashboard
├── plugins/
│   ├── smb_scanner/             # SMB vulnerability scanner
│   ├── web_scanner/             # Web vulnerability scanner
│   └── ssh_scanner/             # SSH security scanner
├── data/
│   └── pendonn.db               # SQLite database
├── logs/
│   ├── pendonn.log              # Main daemon log
│   └── web.log                  # Web interface log
├── handshakes/                  # Captured handshake files
├── main.py                      # Main daemon
├── requirements.txt             # Python dependencies
├── install.sh                   # Installation script
└── README.md                    # This file
```

---

## 🔧 Configuration Reference

### Complete config.json

```json
{
  "system": {
    "name": "PenDonn",
    "version": "1.0.0",
    "auto_start": true,
    "log_level": "INFO"
  },
  "wifi": {
    "monitor_interface": "wlan1",
    "attack_interface": "wlan2",
    "management_interface": "wlan0",
    "channel_hop_interval": 2,
    "handshake_timeout": 300
  },
  "whitelist": {
    "ssids": ["YourNetwork"]
  },
  "cracking": {
    "enabled": true,
    "engines": ["john", "hashcat"],
    "wordlist_path": "/usr/share/wordlists/rockyou.txt",
    "auto_start_cracking": true,
    "max_concurrent_cracks": 2,
    "john_format": "wpapsk",
    "hashcat_mode": 22000
  },
  "enumeration": {
    "enabled": true,
    "auto_scan_on_crack": true,
    "nmap_timing": "T4",
    "port_scan_range": "1-10000",
    "scan_timeout": 3600
  },
  "plugins": {
    "enabled": true,
    "directory": "./plugins",
    "auto_load": true
  },
  "database": {
    "path": "./data/pendonn.db",
    "backup_on_export": true
  },
  "web": {
    "host": "0.0.0.0",
    "port": 8080,
    "secret_key": "CHANGE_THIS"
  },
  "display": {
    "enabled": true,
    "type": "waveshare_v4",
    "refresh_interval": 2,
    "brightness": 80
  }
}
```

---

## 🐛 Troubleshooting

### WiFi Adapters Not Detected

```bash
# List WiFi interfaces
iw dev

# Check if monitor mode is supported
iw list | grep "Supported interface modes" -A 8

# Manually enable monitor mode
sudo ip link set wlan1 down
sudo iw wlan1 set monitor control
sudo ip link set wlan1 up
```

### Services Not Starting

```bash
# Check service status
sudo systemctl status pendonn

# View detailed logs
sudo journalctl -u pendonn -n 50

# Check permissions
ls -la /opt/pendonn

# Reinstall
cd /opt/pendonn
sudo ./install.sh
```

### No Handshakes Captured

1. Verify WiFi adapters support monitor mode and packet injection
2. Check if interfaces are in monitor mode: `iwconfig`
3. Ensure no other processes are using the interfaces
4. Try different channels manually
5. Check logs for errors: `sudo journalctl -u pendonn -f`

### Password Cracking Not Working

```bash
# Test John the Ripper
john --test

# Test Hashcat
hashcat -I

# Check wordlist exists
ls -lh /usr/share/wordlists/rockyou.txt

# Try manual cracking
aircrack-ng -w /usr/share/wordlists/rockyou.txt handshake.cap
```

### Web Interface Not Accessible

```bash
# Check if web service is running
sudo systemctl status pendonn-web

# Check firewall
sudo iptables -L

# Test locally
curl http://localhost:8080/api/status

# Check port binding
sudo netstat -tlnp | grep 8080
```

---

## 📊 Database Schema

The SQLite database stores:

- **Networks** - Discovered WiFi networks
- **Handshakes** - Captured WPA/WPA2 handshakes
- **Cracked Passwords** - Successfully cracked passwords
- **Scans** - Network enumeration scans
- **Vulnerabilities** - Discovered security issues
- **System Logs** - System activity logs

### Export Data

```bash
# Via web interface
curl -X POST http://localhost:8080/api/export > export.json

# Via Python
cd /opt/pendonn
sudo python3 -c "from core.database import Database; db = Database('./data/pendonn.db'); db.export_data('./export.json')"
```

---

## 🤝 Contributing

This is an educational project. Contributions are welcome!

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

---

## 📝 License

This project is for **educational purposes only**. 

**DO NOT USE FOR ILLEGAL ACTIVITIES.**

---

## 🙏 Acknowledgments

Inspired by:
- **Pwnagotchi** - WiFi handshake capture concepts
- **Bjorn** - Network enumeration techniques
- **Aircrack-ng** - WiFi security testing tools
- **John the Ripper** & **Hashcat** - Password cracking

---

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/yourusername/pendonn/issues)
- **Documentation:** This README
- **Logs:** `/opt/pendonn/logs/`

---

## 🔮 Future Enhancements

- [ ] Evil Twin attack support
- [ ] Bluetooth enumeration
- [ ] Advanced reporting with PDF export
- [ ] Mobile app for remote control
- [ ] Multi-language support
- [ ] Cloud backup integration
- [ ] Machine learning for password prediction

---

## ⚡ Quick Reference

```bash
# Start/Stop
sudo systemctl start pendonn pendonn-web
sudo systemctl stop pendonn pendonn-web

# Logs
sudo journalctl -u pendonn -f

# Web Interface
http://<rpi-ip>:8080

# Export Data
curl -X POST http://localhost:8080/api/export > export.json

# Add to Whitelist
curl -X POST http://localhost:8080/api/whitelist \
  -H "Content-Type: application/json" \
  -d '{"ssid":"MyNetwork"}'

# Configuration
sudo nano /opt/pendonn/config/config.json
```

---

**Remember: Always obtain proper authorization before testing any network. Stay legal, stay ethical! 🔒**
