# Tests and Validation

This directory contains all test and validation scripts for the PenDonn system.

## Validation Scripts

Run these to validate code structure and logic without hardware:

### Master Validation
```bash
python validate_all.py
```
Runs all validation tests and provides a comprehensive summary.

### Individual Validations
```bash
python validate_database.py      # Test database operations
python validate_wifi_monitor.py  # Test WiFi monitoring
python validate_cracker.py       # Test password cracking
python validate_display.py       # Test display system
```

## Integration Tests

### Mock System Test
```bash
python test_mock_system.py
```
60-second integration test using mock components. Tests complete workflow from network discovery to password cracking.

### Real Cracker Test
```bash
python test_real_cracker.py
```
Tests real cracker code with actual .cap files (requires tools installed).

## Test Results

All validations currently pass:
- ✅ Database Operations
- ✅ WiFi Monitor
- ✅ Password Cracker
- ✅ Display System

See `../docs/VALIDATION_SUMMARY.md` for detailed results.

## Adding New Tests

1. Create test file: `test_<feature>.py` or `validate_<component>.py`
2. Follow existing patterns
3. Add to `validate_all.py` if it's a validation test
4. Document in this README
