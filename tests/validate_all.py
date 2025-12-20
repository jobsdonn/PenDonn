#!/usr/bin/env python3
"""
Complete System Validation
Runs all validation tests to verify the entire codebase is working correctly
"""

import logging
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_validation_script(script_name):
    """Run a validation script and return result"""
    logger.info(f"\n{'=' * 70}")
    logger.info(f"Running: {script_name}")
    logger.info('=' * 70)
    
    try:
        # Get the Python executable path
        python_exe = sys.executable
        script_path = Path(__file__).parent / script_name
        
        # Run the script
        result = subprocess.run(
            [python_exe, str(script_path)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Print output
        if result.stdout:
            print(result.stdout)
        
        if result.stderr and result.returncode != 0:
            print(result.stderr, file=sys.stderr)
        
        # Check result
        if result.returncode == 0:
            logger.info(f"[SUCCESS] {script_name} - PASSED")
            return True
        else:
            logger.error(f"[FAIL] {script_name} - FAILED (exit code: {result.returncode})")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"[FAIL] {script_name} - TIMEOUT")
        return False
    except Exception as e:
        logger.error(f"[FAIL] {script_name} - ERROR: {e}")
        return False

def main():
    """Run all validation tests"""
    
    print("\n" + "=" * 70)
    print("COMPLETE SYSTEM VALIDATION")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Define validation scripts
    validations = [
        ("validate_database.py", "Database Operations"),
        ("validate_wifi_monitor.py", "WiFi Monitor"),
        ("validate_cracker.py", "Password Cracker"),
        ("validate_display.py", "Display System")
    ]
    
    results = {}
    
    # Run each validation
    for script, name in validations:
        script_path = Path(__file__).parent / script
        if script_path.exists():
            success = run_validation_script(script)
            results[name] = success
        else:
            logger.warning(f"[WARNING] {script} not found - SKIPPED")
            results[name] = None
    
    # Summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v is None)
    total = len(results)
    
    for name, result in results.items():
        if result is True:
            status = "[SUCCESS] PASS"
        elif result is False:
            status = "[FAIL] FAIL"
        else:
            status = "[WARNING] SKIP"
        
        print(f"  {name:.<50} {status}")
    
    print("=" * 70)
    print(f"Total: {total} | Passed: {passed} | Failed: {failed} | Skipped: {skipped}")
    print("=" * 70)
    
    if failed == 0 and passed > 0:
        print("\n[SUCCESS] ALL VALIDATIONS PASSED!")
        print("The codebase is working correctly and ready to use.")
        print("\n[Note] Some features require hardware (WiFi adapter, display, tools)")
        print("[Note] Code structure and logic have been validated successfully")
        return 0
    elif failed > 0:
        print("\n[FAIL] SOME VALIDATIONS FAILED")
        print("Please check the errors above for details.")
        return 1
    else:
        print("\n[WARNING] NO VALIDATIONS RUN")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nValidation interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Validation failed with error: {e}", exc_info=True)
        sys.exit(1)
