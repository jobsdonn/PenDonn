#!/usr/bin/env python3
"""
PenDonn Debug Mode - System Verification
Checks if all components are ready for debug mode testing
"""

import os
import sys
import json

def check_file(path, description):
    """Check if a file exists"""
    if os.path.exists(path):
        print(f"  ✓ {description}")
        return True
    else:
        print(f"  ✗ {description} - MISSING: {path}")
        return False

def check_directory(path, description):
    """Check if a directory exists"""
    if os.path.isdir(path):
        print(f"  ✓ {description}")
        return True
    else:
        print(f"  ✗ {description} - MISSING: {path}")
        return False

def main():
    print("\n" + "="*60)
    print("  PenDonn Debug Mode - System Verification")
    print("="*60 + "\n")
    
    all_ok = True
    
    # Check core files
    print("📁 Core System Files:")
    all_ok &= check_file("main.py", "Main daemon")
    all_ok &= check_file("requirements.txt", "Python dependencies")
    all_ok &= check_file("README.md", "Documentation")
    print()
    
    # Check config files
    print("⚙️  Configuration Files:")
    all_ok &= check_file("config/config.json", "Production config")
    all_ok &= check_file("config/config.debug.json", "Debug config")
    
    # Verify debug config has debug section
    try:
        with open("config/config.debug.json", 'r') as f:
            config = json.load(f)
            if config.get('debug', {}).get('enabled') == True:
                print("  ✓ Debug mode properly configured")
            else:
                print("  ⚠ Debug mode not enabled in config")
                all_ok = False
    except Exception as e:
        print(f"  ✗ Error reading debug config: {e}")
        all_ok = False
    print()
    
    # Check core modules
    print("🔧 Core Modules:")
    all_ok &= check_file("core/database.py", "Database module")
    all_ok &= check_file("core/wifi_monitor.py", "WiFi monitor")
    all_ok &= check_file("core/cracker.py", "Password cracker")
    all_ok &= check_file("core/enumerator.py", "Network enumerator")
    all_ok &= check_file("core/plugin_manager.py", "Plugin manager")
    all_ok &= check_file("core/display.py", "Display module")
    print()
    
    # Check mock modules
    print("🐛 Mock Modules (Debug Mode):")
    all_ok &= check_file("core/mock_wifi_monitor.py", "Mock WiFi monitor")
    all_ok &= check_file("core/mock_display.py", "Mock display")
    all_ok &= check_file("core/mock_cracker.py", "Mock cracker")
    all_ok &= check_file("core/test_data_generator.py", "Test data generator")
    print()
    
    # Check test utilities
    print("🧪 Test Utilities:")
    all_ok &= check_file("test_debug_mode.py", "Test data script")
    all_ok &= check_file("test_data/mini_wordlist.txt", "Test wordlist")
    if os.name == 'nt':
        all_ok &= check_file("start-debug.ps1", "Windows launcher")
    print()
    
    # Check web interface
    print("🌐 Web Interface:")
    all_ok &= check_file("web/app.py", "Flask application")
    all_ok &= check_file("web/templates/index.html", "Web dashboard")
    print()
    
    # Check plugins
    print("🔌 Plugins:")
    all_ok &= check_directory("plugins/smb_scanner", "SMB scanner plugin")
    all_ok &= check_directory("plugins/web_scanner", "Web scanner plugin")
    all_ok &= check_directory("plugins/ssh_scanner", "SSH scanner plugin")
    print()
    
    # Check documentation
    print("📚 Documentation:")
    all_ok &= check_file("TESTING.md", "Testing guide")
    all_ok &= check_file("DEBUG_QUICKSTART.md", "Debug quickstart")
    all_ok &= check_file("DEBUG_MODE_SUMMARY.md", "Debug summary")
    print()
    
    # Check directories (create if missing)
    print("📂 Required Directories:")
    dirs_to_check = ["data", "logs", "handshakes", "test_data"]
    for dir_name in dirs_to_check:
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
            print(f"  ✓ Created: {dir_name}")
        else:
            print(f"  ✓ {dir_name}")
    print()
    
    # Check Python version
    print("🐍 Python Environment:")
    version = sys.version_info
    if version.major >= 3 and version.minor >= 9:
        print(f"  ✓ Python {version.major}.{version.minor}.{version.micro}")
    else:
        print(f"  ✗ Python {version.major}.{version.minor}.{version.micro} - Need 3.9+")
        all_ok = False
    print()
    
    # Final verdict
    print("="*60)
    if all_ok:
        print("✅ ALL CHECKS PASSED - System ready for debug mode!")
        print("\n🚀 To start testing:")
        if os.name == 'nt':
            print("   .\\start-debug.ps1")
            print("   OR")
        print("   python main.py --debug")
        print("\n🌐 Web interface will be at: http://localhost:8080")
    else:
        print("⚠️  SOME CHECKS FAILED - Please review errors above")
        print("\n💡 Try:")
        print("   pip install -r requirements.txt")
        print("   python test_debug_mode.py")
    print("="*60 + "\n")
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n❌ Error during verification: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
