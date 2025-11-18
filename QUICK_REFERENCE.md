# PenDonn Quick Reference Card

## 🚀 Quick Start

```bash
# Installation
sudo ./install.sh

# Configuration
sudo ./setup.sh

# Start/Stop
sudo systemctl start pendonn pendonn-web
sudo systemctl stop pendonn pendonn-web

# View Logs
sudo journalctl -u pendonn -f
```

## 📊 Web Interface

```
Local:  http://localhost:8080
Remote: http://<rpi-ip>:8080
```

## 🔧 Important Files

```
/opt/pendonn/config/config.json    # Configuration
/opt/pendonn/data/pendonn.db       # Database
/opt/pendonn/logs/pendonn.log      # Logs
/opt/pendonn/handshakes/           # Captures
/opt/pendonn/plugins/              # Plugins
```

## 🎛️ Service Commands

```bash
# Status
sudo systemctl status pendonn
sudo systemctl status pendonn-web

# Restart
sudo systemctl restart pendonn
sudo systemctl restart pendonn-web

# Enable auto-start
sudo systemctl enable pendonn pendonn-web

# Disable auto-start
sudo systemctl disable pendonn pendonn-web
```

## 🌐 API Endpoints

```bash
# Status
curl http://localhost:8080/api/status

# Networks
curl http://localhost:8080/api/networks

# Handshakes
curl http://localhost:8080/api/handshakes

# Passwords
curl http://localhost:8080/api/passwords

# Scans
curl http://localhost:8080/api/scans

# Vulnerabilities
curl http://localhost:8080/api/vulnerabilities

# Export Data
curl -X POST http://localhost:8080/api/export > export.json

# Add to Whitelist
curl -X POST http://localhost:8080/api/whitelist \
  -H "Content-Type: application/json" \
  -d '{"ssid":"MyNetwork"}'
```

## 🔍 Troubleshooting Commands

```bash
# Check WiFi interfaces
iw dev

# Check monitor mode support
iw list | grep "Supported interface modes" -A 8

# Test password cracking tools
john --test
hashcat -I

# Check wordlist
ls -lh /usr/share/wordlists/rockyou.txt

# Check database
sqlite3 /opt/pendonn/data/pendonn.db ".tables"

# View recent errors
sudo journalctl -u pendonn -p err -n 20

# Check port binding
sudo netstat -tlnp | grep 8080

# Check processes
ps aux | grep pendonn
```

## 📝 Configuration Snippets

### WiFi Interfaces
```json
{
  "wifi": {
    "monitor_interface": "wlan1",
    "attack_interface": "wlan2",
    "management_interface": "wlan0"
  }
}
```

### Whitelist
```json
{
  "whitelist": {
    "ssids": ["HomeNetwork", "WorkWiFi", "MySSID"]
  }
}
```

### Cracking
```json
{
  "cracking": {
    "enabled": true,
    "engines": ["john", "hashcat"],
    "max_concurrent_cracks": 2
  }
}
```

## 🔌 Plugin Template

```python
from core.plugin_manager import PluginBase

class MyScanner(PluginBase):
    def run(self, scan_id, hosts, scan_results):
        self.log_info("Starting scan")
        
        for host in hosts:
            # Your logic here
            pass
        
        return {'vulnerabilities': 0, 'results': []}
```

## 📊 Database Queries

```bash
# Connect to database
sqlite3 /opt/pendonn/data/pendonn.db

# View networks
SELECT ssid, bssid, encryption FROM networks;

# View cracked passwords
SELECT ssid, password, cracking_engine FROM cracked_passwords;

# View vulnerabilities
SELECT host, vulnerability_type, severity FROM vulnerabilities;

# Statistics
SELECT COUNT(*) FROM networks;
SELECT COUNT(*) FROM handshakes WHERE status='cracked';

# Exit
.exit
```

## 🛠️ Manual Operations

```bash
# Enable monitor mode manually
sudo ip link set wlan1 down
sudo iw wlan1 set monitor control
sudo ip link set wlan1 up

# Capture handshake manually
sudo airodump-ng --bssid AA:BB:CC:DD:EE:FF -c 6 -w capture wlan1

# Crack handshake manually
aircrack-ng -w /usr/share/wordlists/rockyou.txt capture.cap

# Scan network manually
sudo nmap -sV -p 1-1000 192.168.1.0/24
```

## 📦 Backup & Export

```bash
# Export data
curl -X POST http://localhost:8080/api/export > export_$(date +%Y%m%d).json

# Backup database
sudo cp /opt/pendonn/data/pendonn.db ~/pendonn_backup_$(date +%Y%m%d).db

# Backup configuration
sudo cp /opt/pendonn/config/config.json ~/config_backup.json

# Full system backup
sudo tar -czf ~/pendonn_full_backup.tar.gz /opt/pendonn/
```

## 🔄 Update & Reinstall

```bash
# Update code
cd ~/pendonn
git pull

# Reinstall
sudo ./install.sh

# Restart services
sudo systemctl restart pendonn pendonn-web
```

## 🚨 Emergency Commands

```bash
# Stop everything
sudo systemctl stop pendonn pendonn-web
sudo killall python3

# Reset database (CAUTION!)
sudo rm /opt/pendonn/data/pendonn.db
sudo /opt/pendonn/venv/bin/python3 /opt/pendonn/core/database.py --init

# Restore managed mode
sudo systemctl stop pendonn
sudo ip link set wlan1 down
sudo iw wlan1 set type managed
sudo ip link set wlan1 up
```

## 📞 Support

- **Logs:** `/opt/pendonn/logs/`
- **Issues:** GitHub Issues
- **Docs:** README.md, ARCHITECTURE.md

## ⚠️ Legal Reminder

**ONLY USE ON AUTHORIZED NETWORKS!**

```
✅ Your own networks
✅ Written permission obtained
✅ Legal penetration testing

❌ Unauthorized networks
❌ Without permission
❌ Illegal activities
```

---

**Remember: Stay legal, stay ethical! 🔒**
