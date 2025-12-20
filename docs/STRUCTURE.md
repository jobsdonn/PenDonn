# PenDonn Project Structure

## 📁 Directory Organization

```
PenDonn/
│
├── 📂 core/                      # Core System Modules
│   ├── __init__.py
│   ├── cracker.py               # Password cracking (John/Hashcat)
│   ├── database.py              # SQLite database operations
│   ├── display.py               # Waveshare display handler
│   ├── mock_cracker.py          # Mock cracker for testing
│   ├── mock_wifi_monitor.py     # Mock WiFi monitor for testing
│   ├── network_scanner.py       # Network vulnerability scanner
│   └── wifi_monitor.py          # WiFi monitoring & handshake capture
│
├── 📂 tests/                     # Test & Validation Scripts
│   ├── test_mock_system.py      # Mock system integration test
│   ├── test_real_cracker.py     # Real cracker validation test
│   ├── validate_all.py          # Master validation script (runs all)
│   ├── validate_cracker.py      # Cracker code validation
│   ├── validate_database.py     # Database operations validation
│   ├── validate_display.py      # Display system validation
│   └── validate_wifi_monitor.py # WiFi monitor validation
│
├── 📂 docs/                      # Documentation
│   ├── PROJECT_STRUCTURE.md     # This file - project organization
│   ├── VALIDATION_SUMMARY.md    # Validation test results & summary
│   └── WIFI_MANAGEMENT.md       # WiFi adapter setup & management
│
├── 📂 config/                    # Configuration Files
│   ├── config.yaml              # Main system configuration
│   └── whitelist.yaml           # Network whitelist
│
├── 📂 scripts/                   # Utility Scripts
│   ├── setup_interface.sh       # WiFi interface setup script
│   └── install_tools.sh         # Dependency installation
│
├── 📂 test_data/                 # Test Data Files
│   └── mini_wordlist.txt        # Test password wordlist
│
├── 📂 handshakes/               # Captured Handshake Files
│   └── *.cap                    # WPA2 handshake captures
│
├── 📂 data/                      # Runtime Data
│   └── pendonn.db              # Main SQLite database
│
├── 📂 logs/                      # Log Files
│   ├── pendonn.log             # Application logs
│   └── *.log                   # Component-specific logs
│
├── 📂 debug/                     # Debug Output
│   └── *.txt                   # Debug information files
│
├── 📂 plugins/                   # Plugin System
│   ├── __init__.py
│   ├── smb_scanner.py          # SMB vulnerability scanner
│   ├── web_scanner.py          # Web application scanner
│   └── ssh_scanner.py          # SSH vulnerability scanner
│
├── 📂 web/                       # Web Interface (Future)
│   └── ...                     # Web dashboard files
│
├── 📄 main.py                   # Main application entry point
├── 📄 requirements.txt          # Python dependencies
├── 📄 install.sh               # Installation script
├── 📄 README.md                # Project documentation
├── 📄 LICENSE                  # Project license
└── 📄 .gitignore              # Git ignore rules
```

## 📦 Module Descriptions

### Core Modules (`core/`)

#### Production Code
- **wifi_monitor.py** - Real WiFi monitoring using Scapy
  - Network discovery and signal tracking
  - Handshake capture with deauthentication
  - Channel hopping and packet analysis
  
- **cracker.py** - Password cracking engine
  - John the Ripper integration (with hcx2john)
  - Hashcat integration (with hcxpcapngtool)
  - Multi-threaded cracking with progress tracking
  
- **database.py** - SQLite database manager
  - Network storage and retrieval
  - Handshake tracking
  - Cracked password storage
  - Vulnerability data management
  
- **display.py** - Waveshare display controller
  - Real-time status updates
  - Network information display
  - Progress visualization
  
- **network_scanner.py** - Network vulnerability scanner
  - Nmap integration
  - Port scanning
  - Service enumeration
  - Plugin system integration

#### Development/Testing Code
- **mock_wifi_monitor.py** - Simulated WiFi monitoring
  - 12 realistic test networks
  - Simulated handshake captures
  - Realistic timing and behavior
  
- **mock_cracker.py** - Simulated password cracking
  - SSID-to-password mappings
  - Tool simulation (John/Hashcat)
  - Progress tracking

### Test Suite (`tests/`)

#### Validation Scripts
All validation scripts test code structure and logic without requiring hardware:

- **validate_all.py** - Master script
  - Runs all validation tests
  - Provides comprehensive summary
  - Exit codes for CI/CD integration

- **validate_database.py** - Database validation
  - CRUD operations
  - Query methods
  - Statistics functions
  - Data integrity

- **validate_wifi_monitor.py** - WiFi monitor validation
  - Network discovery
  - Signal tracking
  - Handshake capture logic
  - Stop/cleanup

- **validate_cracker.py** - Cracker validation
  - Method availability
  - File handling (>1KB checks)
  - Database integration
  - Tool availability checks

- **validate_display.py** - Display validation
  - Initialization
  - Method signatures
  - Data retrieval
  - Code structure

#### Integration Tests
- **test_mock_system.py** - Full system test
  - 60-second integration test
  - Tests complete workflow
  - Progress tracking
  - Statistics verification

- **test_real_cracker.py** - Real cracker test
  - Tests with actual .cap files
  - Tool execution validation
  - Error handling verification

### Configuration (`config/`)

- **config.yaml** - Main configuration
  ```yaml
  interface: wlan1mon
  deauth_packets: 5
  wordlist: /path/to/wordlist.txt
  display:
    enabled: true
    refresh_interval: 1
  ```

- **whitelist.yaml** - Protected networks
  ```yaml
  ssids:
    - "MyHomeNetwork"
    - "MyOfficeWiFi"
  ```

### Scripts (`scripts/`)

- **setup_interface.sh** - WiFi adapter setup
  - Puts adapter in monitor mode
  - Verifies packet injection
  - Configures settings

- **install_tools.sh** - Dependency installer
  - Installs John the Ripper
  - Installs Hashcat
  - Installs hcxtools
  - Installs system dependencies

## 🚀 Usage Guide

### Running Tests

```bash
# Navigate to project root
cd /path/to/PenDonn

# Run all validations
python tests/validate_all.py

# Run specific validation
python tests/validate_cracker.py
python tests/validate_database.py
python tests/validate_wifi_monitor.py
python tests/validate_display.py

# Run mock system test (60 seconds)
python tests/test_mock_system.py
```

### Development Workflow

1. **Make code changes** in `core/` modules
2. **Run validations** to ensure nothing broke:
   ```bash
   python tests/validate_all.py
   ```
3. **Test with mock system** for integration:
   ```bash
   python tests/test_mock_system.py
   ```
4. **Deploy to Raspberry Pi** and test with real hardware

### File Management

#### Test Data
- Place wordlists in `test_data/`
- Captured handshakes stored in `handshakes/`
- Database created in `data/pendonn.db`

#### Logs
- Application logs in `logs/pendonn.log`
- Debug output in `debug/` directory
- Check logs for troubleshooting

## ✅ Validation Status

**All components validated and working:**

```
Database Operations............................... [SUCCESS] PASS
WiFi Monitor...................................... [SUCCESS] PASS
Password Cracker.................................. [SUCCESS] PASS
Display System.................................... [SUCCESS] PASS

Total: 4 | Passed: 4 | Failed: 0 | Skipped: 0
```

See `docs/VALIDATION_SUMMARY.md` for detailed results.

## 📝 Notes

- **Mock system** allows development without hardware
- **Real system** requires WiFi adapter, tools, and optionally display
- **Tests** validate code structure and logic
- **Integration** verified with mock and real components
- **Documentation** kept in `docs/` for easy reference

## 🔧 Maintenance

### Adding New Tests
1. Create new test file in `tests/`
2. Follow naming: `validate_<component>.py` or `test_<feature>.py`
3. Add to `validate_all.py` if it's a validation test

### Adding Documentation
1. Create markdown file in `docs/`
2. Link from main `README.md`
3. Keep structure documentation up to date

### Code Organization
- Keep production code in `core/`
- Keep tests in `tests/`
- Keep documentation in `docs/`
- Keep configuration in `config/`
