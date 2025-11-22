# PenDonn Debug Mode - Quick Reference

## 🚀 Quick Start Commands

### Windows:
```powershell
# Easy way (recommended)
.\start-debug.ps1

# Manual way
python main.py --debug
```

### Linux/macOS:
```bash
# Direct run
python3 main.py --debug

# With test data generation first
python3 test_debug_mode.py
python3 main.py --debug
```

## 🎯 Key URLs

| Resource | URL |
|----------|-----|
| Web Dashboard | http://localhost:8080 |
| API Status | http://localhost:8080/api/status |
| Networks | http://localhost:8080/api/networks |
| Handshakes | http://localhost:8080/api/handshakes |
| Passwords | http://localhost:8080/api/passwords |
| Export Data | http://localhost:8080/api/export |

## 📁 Important Files

| File | Purpose |
|------|---------|
| `config/config.debug.json` | Debug mode configuration |
| `config/config.json` | Production configuration |
| `logs/pendonn.log` | System logs |
| `data/pendonn_debug.db` | Debug mode database |
| `TESTING.md` | Comprehensive testing guide |

## 🛠️ Common Tasks

### Generate Test Data
```bash
python test_debug_mode.py
```

### Clear Debug Database
```bash
# Windows
Remove-Item .\data\pendonn_debug.db

# Linux/macOS
rm ./data/pendonn_debug.db
```

### View Logs in Real-Time
```powershell
# Windows PowerShell
Get-Content .\logs\pendonn.log -Wait -Tail 50

# Linux/macOS
tail -f ./logs/pendonn.log
```

### Test API Endpoint
```bash
curl http://localhost:8080/api/status
```

## 🐛 Mock Modules Overview

| Module | Mock Version | What It Simulates |
|--------|--------------|-------------------|
| WiFi Monitor | `mock_wifi_monitor.py` | Network discovery, handshake capture |
| Display | `mock_display.py` | Console output instead of hardware display |
| Cracker | `mock_cracker.py` | Password cracking with test passwords |

## 🧪 Test Data Includes

- **12 Networks**: Various SSIDs, channels, encryption types
- **8 Handshakes**: Captured .cap files
- **4 Cracked Passwords**: admin123, password123, etc.
- **4 Network Scans**: With host discovery
- **10 Vulnerabilities**: Various severity levels

## ⚡ Debug Mode Features

✅ **No root/sudo required**  
✅ **Runs on Windows/Linux/macOS**  
✅ **No hardware dependencies**  
✅ **Simulates realistic behavior**  
✅ **Generates test data automatically**  
✅ **Full web UI functionality**  
✅ **Real database operations**  
✅ **Plugin system works normally**

## 🔍 What's Different in Debug Mode?

| Feature | Production | Debug Mode |
|---------|-----------|------------|
| WiFi Scanning | Real adapters | Simulated networks |
| Handshake Capture | aircrack-ng | Mock .cap files |
| Password Cracking | John/Hashcat | Simulated with test passwords |
| Display Output | Waveshare V4 | Console logging |
| Root Required | Yes (Linux) | No |
| Hardware Required | Raspberry Pi + adapters | Any computer |

## 📊 Expected Behavior

### Timeline After Start:
- **T+0s**: System initializes
- **T+2-5s**: First mock network discovered
- **T+10-20s**: First handshake captured
- **T+20-40s**: First password cracked
- **T+continuous**: Networks, signals update

### Success Rates:
- **Network Discovery**: 100% (6 mock networks)
- **Handshake Capture**: ~60% success rate
- **Password Cracking**: ~70% success rate

## 🎓 Learning Path

1. **Start**: `python main.py --debug`
2. **Observe**: Watch logs for mock activity
3. **Explore**: Open web UI at localhost:8080
4. **Test**: Generate test data, try API endpoints
5. **Develop**: Modify code, see immediate results
6. **Deploy**: When ready, test on real Raspberry Pi

## 🚨 Troubleshooting Quick Fixes

| Problem | Solution |
|---------|----------|
| Port 8080 in use | Change port in config.debug.json |
| Missing modules | `pip install -r requirements.txt` |
| No data appearing | Run `test_debug_mode.py` first |
| Database locked | Kill all Python processes |
| Import errors | Check Python version (need 3.9+) |

## 💡 Pro Tips

1. **Use test data generator** for instant populated database
2. **Set `simulate_delays: false`** in config for faster testing
3. **Enable `verbose_logging`** when debugging issues
4. **Use `--debug` flag** to skip root checks
5. **Check logs** before asking for help

## 📞 Need More Help?

See **TESTING.md** for:
- Detailed testing scenarios
- Step-by-step guides
- Advanced debugging
- Integration testing
- Performance testing

---

**Happy Testing! 🎉**
