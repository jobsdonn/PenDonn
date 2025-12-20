# PenDonn Project Structure

```
PenDonn/
├── README.md                    # Main project documentation
├── LICENSE                      # Project license
├── requirements.txt             # Python dependencies
├── main.py                      # Main application entry point
├── __init__.py                  # Package initialization
│
├── scripts/                     # Installation and utility scripts
│   ├── install.sh              # Main installer for Raspberry Pi
│   ├── install-wifi-drivers.sh # WiFi adapter driver installer
│   ├── configure.sh            # Interactive configuration wizard
│   ├── pre-start-check.sh      # Safety checks before starting services
│   ├── detect-wifi-adapters.sh # WiFi adapter detection utility
│   └── setup.sh                # Quick setup script
│
├── core/                        # Core application modules
│   ├── scanner.py              # WiFi scanning and monitoring
│   ├── cracker.py              # Password cracking engine
│   ├── enumerator.py           # Network enumeration
│   ├── plugin_manager.py       # Plugin system
│   └── database.py             # Database operations
│
├── web/                         # Web interface
│   ├── app.py                  # Flask application
│   ├── routes.py               # API endpoints
│   ├── static/                 # CSS, JS, images
│   └── templates/              # HTML templates
│
├── config/                      # Configuration files
│   ├── config.json             # Main configuration
│   └── config.debug.json       # Debug mode configuration
│
├── plugins/                     # Custom plugins directory
│   └── example_plugin.py       # Example plugin template
│
├── data/                        # Application data
│   └── pendonn.db              # SQLite database
│
├── logs/                        # Application logs
│   ├── pendonn.log            # Main application log
│   └── pendonn_error.log      # Error log
│
├── handshakes/                  # Captured WPA handshakes
│   └── *.cap / *.pcap         # Handshake files
│
├── docs/                        # Documentation
│   ├── ARCHITECTURE.md         # System architecture
│   ├── CHANGELOG.md            # Version history
│   ├── CONTRIBUTING.md         # Contribution guidelines
│   ├── QUICK_REFERENCE.md      # Quick command reference
│   ├── IMPLEMENTATION_COMPLETE.md  # Implementation details
│   └── TESTING.md              # Testing guide
│
├── debug/                       # Debug and development files
│   ├── START_HERE_DEBUG.md     # Debug mode introduction
│   ├── DEBUG_QUICKSTART.md     # Quick start for debug mode
│   ├── DEBUG_MODE_SUMMARY.md   # Complete debug mode documentation
│   ├── start-debug.ps1         # Windows PowerShell debug launcher
│   ├── test_debug_mode.py      # Debug mode tests
│   └── verify_debug_setup.py   # Setup verification script
│
└── test_data/                   # Mock data for testing
    └── *.json                  # Test datasets
```

## Directory Purposes

### `/scripts/` - Installation & Utilities
All bash scripts for system setup, configuration, and maintenance. Run these on the Raspberry Pi.

**Usage:**
```bash
sudo scripts/install.sh              # Install PenDonn
sudo scripts/configure.sh            # Configure after installation
sudo scripts/pre-start-check.sh      # Check config before starting
sudo scripts/detect-wifi-adapters.sh # Detect WiFi hardware
sudo scripts/install-wifi-drivers.sh # Install specific drivers
```

### `/core/` - Application Logic
Python modules containing the main functionality:
- **scanner.py**: WiFi network discovery, channel hopping, packet capture
- **cracker.py**: Password cracking with John/Hashcat
- **enumerator.py**: Network scanning with Nmap
- **plugin_manager.py**: Dynamic plugin loading
- **database.py**: SQLite operations for storing results

### `/web/` - User Interface
Flask-based web interface for monitoring and control:
- **Access**: http://raspberry-pi-ip:8080
- Real-time network discovery dashboard
- Captured handshakes viewer
- Cracking progress monitor
- Configuration management

### `/config/` - Configuration
JSON configuration files:
- **config.json**: Production configuration
- **config.debug.json**: Debug mode (Windows/Linux testing)

**Key settings:**
- WiFi interface assignments (wlan0, wlan1, wlan2)
- Cracking engine preferences
- Web interface settings
- Whitelist for protected networks

### `/plugins/` - Extensions
Custom plugins to extend functionality:
- Add custom scanning logic
- Implement new attack types
- Create custom reporting
- Integrate external tools

### `/docs/` - Documentation
Comprehensive project documentation:
- Architecture diagrams
- API references
- Development guides
- Testing procedures

### `/debug/` - Development Tools
Debug mode for testing without Raspberry Pi hardware:
- Mock WiFi adapters
- Simulated cracking
- Test on Windows/Linux
- Development workflows

## Installation Flow

1. Clone repository to Raspberry Pi
2. Run `sudo scripts/install.sh`
3. Installer creates `/opt/pendonn/` with full system
4. Services managed via systemd:
   - `pendonn.service` - Main daemon
   - `pendonn-web.service` - Web interface

## File Locations (After Installation)

```
/opt/pendonn/              # Production installation
├── All Python files       # Copied from repo
├── venv/                  # Python virtual environment
├── data/                  # Runtime database
├── logs/                  # Application logs
├── handshakes/            # Captured files
└── config/                # Active configuration

/etc/systemd/system/       # System services
├── pendonn.service
└── pendonn-web.service

/usr/share/wordlists/      # Password dictionaries
└── rockyou.txt

/etc/NetworkManager/       # Network configuration
└── NetworkManager.conf    # wlan1/wlan2 unmanaged

/etc/udev/rules.d/         # Hardware rules
└── 70-persistent-wifi.rules  # Interface naming
```

## Service Management

```bash
# Start services
sudo systemctl start pendonn pendonn-web

# Stop services
sudo systemctl stop pendonn pendonn-web

# Enable auto-start on boot
sudo systemctl enable pendonn pendonn-web

# View logs
sudo journalctl -u pendonn -f

# Check status
sudo systemctl status pendonn
```

## Development Workflow

1. **Edit code** in repository
2. **Test locally** with debug mode:
   ```bash
   python main.py --debug
   ```
3. **Push to Git** when ready
4. **On Raspberry Pi**: Pull and reinstall if needed

## Important Notes

- **scripts/** directory contains all installation tooling
- **Never edit files in /opt/pendonn/** directly (will be overwritten)
- **Edit files in your git repository**, then reinstall
- **Debug mode** runs on any platform without hardware
- **Production mode** requires Raspberry Pi + WiFi adapters
