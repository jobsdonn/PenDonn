# PenDonn - Quick File Reference

## 🎯 Where to Find Things

### 🔧 Want to Run Tests?
```bash
cd tests/
python validate_all.py          # Run all validations
python test_mock_system.py      # Test mock system
```

### 📖 Want Documentation?
```bash
cd docs/
cat VALIDATION_SUMMARY.md       # Test results
cat STRUCTURE.md                # Project organization
cat WIFI_MANAGEMENT.md          # WiFi setup guide
```

### ⚙️ Want to Configure?
```bash
cd config/
nano config.yaml                # Main config
nano whitelist.yaml             # Network whitelist
```

### 🚀 Want to Run the App?
```bash
python main.py                  # Start application
```

### 🔍 Want to Develop?
```bash
cd core/
# Edit modules here:
# - cracker.py (password cracking)
# - database.py (database ops)
# - wifi_monitor.py (WiFi monitoring)
# - display.py (display control)
```

## 📂 Directory Quick Reference

| Directory | Purpose | Key Files |
|-----------|---------|-----------|
| `core/` | Production code | All main modules |
| `tests/` | All test files | validate_*.py, test_*.py |
| `docs/` | Documentation | *.md files |
| `config/` | Configuration | *.yaml files |
| `scripts/` | Setup scripts | *.sh files |
| `handshakes/` | Captured files | *.cap files |
| `test_data/` | Test data | wordlists |
| `logs/` | Application logs | *.log files |
| `data/` | Database | pendonn.db |

## 🎯 Common Tasks

### Run All Validations
```bash
python tests/validate_all.py
```

### Run Single Validation
```bash
python tests/validate_cracker.py
python tests/validate_database.py
python tests/validate_wifi_monitor.py
python tests/validate_display.py
```

### Run Integration Test
```bash
python tests/test_mock_system.py
```

### View Documentation
```bash
# Structure and organization
cat docs/STRUCTURE.md

# Validation results
cat docs/VALIDATION_SUMMARY.md

# WiFi management
cat docs/WIFI_MANAGEMENT.md
```

### Configure System
```bash
# Edit main config
nano config/config.yaml

# Edit whitelist
nano config/whitelist.yaml
```

## ✅ Current Status

**All validations passing:**
- ✅ Database Operations
- ✅ WiFi Monitor  
- ✅ Password Cracker
- ✅ Display System

**Project organized:**
- ✅ Tests in `tests/`
- ✅ Docs in `docs/`
- ✅ Code in `core/`
- ✅ Config in `config/`
