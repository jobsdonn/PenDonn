# PenDonn Testing & Development Guide

## 🐛 Debug Mode Overview

PenDonn includes a comprehensive debug mode that allows you to test the entire system on Windows, Linux, or macOS without requiring Raspberry Pi hardware, WiFi adapters, or root privileges.

## Quick Start - Debug Mode

### On Windows (PowerShell):
```powershell
# Install Python dependencies
python -m pip install -r requirements.txt

# Run in debug mode
python main.py --debug
```

### On Linux/macOS:
```bash
# Install Python dependencies
pip3 install -r requirements.txt

# Run in debug mode
python3 main.py --debug
```

### Access Web Interface:
Open your browser to: `http://localhost:8080`

---

## 🎯 What Debug Mode Does

Debug mode automatically:
- ✅ **Skips root/sudo requirements**
- ✅ **Uses mock WiFi adapter** (simulates network discovery)
- ✅ **Uses mock display** (console output instead of hardware)
- ✅ **Uses mock password cracker** (simulates cracking with test passwords)
- ✅ **Generates realistic test data** (networks, handshakes, scans, vulnerabilities)
- ✅ **Runs on Windows/Linux/macOS**
- ✅ **No hardware dependencies**

---

## 📁 Configuration Files

### Production Config: `config/config.json`
- Used when running: `python main.py`
- Requires Raspberry Pi hardware
- Requires root privileges
- Real WiFi interfaces

### Debug Config: `config/config.debug.json`
- Used when running: `python main.py --debug`
- No hardware required
- No root privileges needed
- Mock modules enabled

---

## 🧪 Testing Scenarios

### Scenario 1: Basic System Test
**Goal:** Verify all modules start correctly

```bash
# Start in debug mode
python main.py --debug

# Expected output:
# - "DEBUG MODE ENABLED - Using mock hardware modules"
# - All modules initialize without errors
# - Mock networks start appearing in logs
# - Web interface accessible at http://localhost:8080
```

**Validation:**
- Check logs in `./logs/pendonn.log`
- Verify web interface loads
- Confirm mock networks appear in dashboard

---

### Scenario 2: Network Discovery Simulation
**Goal:** Test WiFi scanning and network database

```bash
# Run in debug mode
python main.py --debug

# Watch the logs for:
# - "Mock: Discovered network - SSID: ..."
# - Networks added to database
# - Signal strength variations

# Verify in web UI:
# - Navigate to "Networks" tab
# - Should see 5-6 discovered networks
# - Each with BSSID, channel, encryption, signal strength
```

**Expected Timeline:**
- T+0s: System starts
- T+2-5s: First network discovered
- T+5-15s: Additional networks appear
- T+15s: All mock networks discovered

---

### Scenario 3: Handshake Capture Test
**Goal:** Verify handshake capture and database storage

```bash
# Run debug mode for 30 seconds
python main.py --debug

# Monitor for:
# - "Mock: Captured handshake - SSID: ..."
# - Handshake files created in ./handshakes/

# Check web UI:
# - "Handshakes" tab should show captured handshakes
# - Status should be "pending" before cracking
```

**Expected Results:**
- 60% success rate for handshake captures
- Files created in `./handshakes/` directory
- Database entries visible in web UI

---

### Scenario 4: Password Cracking Simulation
**Goal:** Test cracking queue and password recovery

```bash
# Run with auto-cracking enabled
python main.py --debug

# Watch for:
# - "Mock Worker X: Starting crack for ..."
# - "Mock Worker X: ✓ Cracked ... - Password: ..."
# - Cracked passwords appear in database

# Verify in web UI:
# - "Passwords" tab shows cracked credentials
# - Crack time recorded
# - Passwords: admin123, password123, etc.
```

**Mock Passwords Used:**
- password123
- admin123
- welcome1
- qwerty123
- letmein

**Expected Behavior:**
- 70% crack success rate
- 10-30 second simulated crack time (or 2s in fast mode)
- Automatic queue processing

---

### Scenario 5: Test Data Generation
**Goal:** Populate database with comprehensive test data

Create a test script `generate_test_data.py`:
```python
#!/usr/bin/env python3
import sys
from core.database import Database
from core.test_data_generator import TestDataGenerator

# Initialize database
db = Database('./data/pendonn_debug.db')

# Generate test data
generator = TestDataGenerator(db)
generator.generate_all(
    num_networks=15,
    num_handshakes=10,
    num_scans=5,
    num_vulnerabilities=12
)

print("✓ Test data generated successfully!")
db.close()
```

Run it:
```bash
python generate_test_data.py
```

**Generated Data:**
- 15 networks (various SSIDs, channels, signal strengths)
- 10 handshakes
- 3 cracked passwords
- 5 network scans with host discovery
- 12 vulnerabilities (various severities)

---

### Scenario 6: Web API Testing
**Goal:** Test all REST API endpoints

```bash
# Start system in debug mode
python main.py --debug

# In another terminal, test API:
```

#### Get System Status:
```bash
curl http://localhost:8080/api/status
```

#### Get All Networks:
```bash
curl http://localhost:8080/api/networks
```

#### Get Handshakes:
```bash
curl http://localhost:8080/api/handshakes
```

#### Get Cracked Passwords:
```bash
curl http://localhost:8080/api/passwords
```

#### Export Database:
```bash
curl -X POST http://localhost:8080/api/export -o export.json
```

#### Add to Whitelist:
```bash
curl -X POST http://localhost:8080/api/whitelist \
  -H "Content-Type: application/json" \
  -d '{"ssid": "MyHomeWiFi"}'
```

#### Reset Database (with backup):
```bash
curl -X POST http://localhost:8080/api/database/reset
```

---

### Scenario 7: Plugin System Test
**Goal:** Verify plugins load and execute in debug mode

```bash
# Run with plugins enabled
python main.py --debug

# Check logs for:
# - "Loaded plugin: smb_scanner"
# - "Loaded plugin: web_scanner"
# - "Loaded plugin: ssh_scanner"

# Plugins will NOT execute unless:
# 1. Network is scanned after password crack
# 2. Or manually triggered via enumeration
```

**Note:** Plugins work normally in debug mode since they don't require special hardware, just network connectivity.

---

## 🔧 Development Workflows

### Workflow 1: Module Development
When developing a new module:

1. **Create mock version** in `core/mock_<module>.py`
2. **Add conditional import** in `main.py`
3. **Test with** `--debug` flag
4. **Implement real version** in `core/<module>.py`
5. **Test on Raspberry Pi**

### Workflow 2: Database Schema Changes
When modifying database:

1. Update `core/database.py`
2. Delete `./data/pendonn_debug.db`
3. Run `python main.py --debug`
4. Use test data generator to populate
5. Verify with web UI

### Workflow 3: Web UI Development
When updating web interface:

1. Start system: `python main.py --debug`
2. Edit `web/templates/index.html` or `web/app.py`
3. Refresh browser (Flask auto-reloads in debug)
4. Use browser DevTools for debugging
5. Test API endpoints with curl/Postman

---

## 🐞 Debugging Tips

### Enable Verbose Logging
Edit `config/config.debug.json`:
```json
{
  "debug": {
    "enabled": true,
    "verbose_logging": true
  }
}
```

This sets log level to DEBUG for detailed output.

### View Real-Time Logs
```bash
# PowerShell
Get-Content .\logs\pendonn.log -Wait -Tail 50

# Linux/macOS
tail -f ./logs/pendonn.log
```

### Check Database Contents
```bash
# Install sqlite3 if needed
# PowerShell: choco install sqlite
# Linux: apt install sqlite3
# macOS: brew install sqlite3

sqlite3 ./data/pendonn_debug.db

# Useful queries:
sqlite> .tables
sqlite> SELECT * FROM networks;
sqlite> SELECT * FROM handshakes;
sqlite> SELECT * FROM cracked_passwords;
sqlite> .quit
```

### Inspect Mock Handshake Files
```bash
ls ./handshakes/
# Files contain: MOCK_HANDSHAKE_DATA_<bssid>
```

---

## 🚨 Common Issues & Solutions

### Issue: "ModuleNotFoundError: No module named 'scapy'"
**Solution:** Install dependencies
```bash
pip install -r requirements.txt
```

### Issue: Port 8080 already in use
**Solution:** Change port in `config/config.debug.json`
```json
{
  "web": {
    "port": 8081
  }
}
```

### Issue: No networks appearing
**Solution:** Check if whitelist is blocking
```json
{
  "whitelist": {
    "ssids": []  // Make sure this is empty for testing
  }
}
```

### Issue: Database locked error
**Solution:** Close other connections
```bash
# Windows
taskkill /F /IM python.exe

# Linux/macOS
pkill python3
```

### Issue: Mock modules not loading
**Solution:** Verify debug config
```bash
# Ensure --debug flag is used
python main.py --debug

# OR check config file has:
{
  "debug": {
    "enabled": true,
    "mock_wifi": true
  }
}
```

---

## 📊 Performance Testing

### Memory Usage Test
```bash
# Windows PowerShell
while ($true) { 
  Get-Process python | Select-Object WorkingSet64 
  Start-Sleep 5 
}

# Linux
watch -n 5 'ps aux | grep python'
```

### Database Performance
```python
import time
from core.database import Database

db = Database('./data/test_perf.db')

start = time.time()
for i in range(1000):
    db.add_network(f"Network_{i}", f"AA:BB:CC:DD:EE:{i:02X}", 6, "WPA2", -50)
elapsed = time.time() - start

print(f"1000 inserts in {elapsed:.2f}s ({1000/elapsed:.0f} ops/sec)")
```

---

## 🎓 Learning & Exploration

### Understanding the Flow

1. **Discovery Phase** (Mock WiFi Monitor)
   - Generates random networks
   - Simulates signal variations
   - Adds to database

2. **Capture Phase** (Mock WiFi Monitor)
   - Random handshake captures (60% success)
   - Creates `.cap` files
   - Queues for cracking

3. **Cracking Phase** (Mock Cracker)
   - Workers process queue
   - Simulates John/Hashcat
   - 70% success rate with test passwords

4. **Enumeration Phase** (Real Enumerator)
   - Connects to network (if possible)
   - Runs nmap scans
   - Executes plugins

5. **Display Phase** (Mock Display)
   - Console output every 5 seconds
   - Shows statistics
   - Updates web dashboard

---

## 🔬 Advanced Testing

### Unit Testing Framework
Create `tests/test_database.py`:
```python
import unittest
from core.database import Database
import os

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.db = Database(':memory:')
    
    def test_add_network(self):
        self.db.add_network("TestSSID", "AA:BB:CC:DD:EE:FF", 6, "WPA2", -50)
        networks = self.db.get_networks()
        self.assertEqual(len(networks), 1)
        self.assertEqual(networks[0]['ssid'], "TestSSID")
    
    def tearDown(self):
        self.db.close()

if __name__ == '__main__':
    unittest.main()
```

Run tests:
```bash
python -m unittest discover tests/
```

### Integration Testing
Create `tests/integration_test.py`:
```python
#!/usr/bin/env python3
import time
import requests
from subprocess import Popen

# Start PenDonn in debug mode
proc = Popen(['python', 'main.py', '--debug'])
time.sleep(5)  # Wait for startup

try:
    # Test web interface
    response = requests.get('http://localhost:8080/api/status')
    assert response.status_code == 200
    print("✓ Web API responding")
    
    # Wait for some data
    time.sleep(20)
    
    # Check for networks
    response = requests.get('http://localhost:8080/api/networks')
    networks = response.json()
    assert len(networks) > 0
    print(f"✓ {len(networks)} networks discovered")
    
    print("✓ Integration test passed!")
    
finally:
    proc.terminate()
```

---

## 📝 Checklist: Before Production Deployment

- [ ] Tested in debug mode on development machine
- [ ] All modules start without errors
- [ ] Web interface accessible and functional
- [ ] Database operations working correctly
- [ ] Plugins load and execute
- [ ] API endpoints respond correctly
- [ ] Export/import functions tested
- [ ] Whitelist filtering works
- [ ] Ready to test on actual Raspberry Pi hardware

---

## 🆘 Getting Help

**Check Logs First:**
```bash
# View full log
cat ./logs/pendonn.log

# Search for errors
grep ERROR ./logs/pendonn.log

# Search for specific module
grep "WiFi Monitor" ./logs/pendonn.log
```

**Enable Maximum Verbosity:**
```json
{
  "system": {
    "log_level": "DEBUG"
  },
  "debug": {
    "verbose_logging": true
  }
}
```

**Generate Fresh Test Data:**
```bash
# Delete old database
rm ./data/pendonn_debug.db

# Restart system
python main.py --debug
```

---

## 🎉 Success Indicators

You'll know debug mode is working when you see:
- ✅ "DEBUG MODE ENABLED" message at startup
- ✅ "Mock WiFi Monitor initialized (DEBUG MODE)"
- ✅ "Mock Display initialized (DEBUG MODE)"
- ✅ Networks appearing in logs every few seconds
- ✅ Handshakes being captured
- ✅ Passwords being cracked
- ✅ Web UI showing statistics
- ✅ No error messages in logs

---

## 🚀 Next Steps

1. **Run debug mode:** `python main.py --debug`
2. **Open web UI:** http://localhost:8080
3. **Watch it work:** Monitor logs and dashboard
4. **Explore features:** Try all tabs and API endpoints
5. **Generate test data:** Use TestDataGenerator for more scenarios
6. **Develop features:** Add new modules or plugins
7. **Deploy to Pi:** When ready, test on real hardware

**Happy Testing! 🎯**
