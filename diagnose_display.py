#!/opt/pendonn/venv/bin/python3
"""
PenDonn Display Diagnostic Tool
Tests display hardware and identifies issues
"""

import os
import sys
import time

# Add venv site-packages to path
venv_site = '/opt/pendonn/venv/lib/python3.13/site-packages'
if os.path.exists(venv_site) and venv_site not in sys.path:
    sys.path.insert(0, venv_site)

# Color codes for output
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header(text):
    print(f"\n{BLUE}{'=' * 60}{RESET}")
    print(f"{BLUE}{text:^60}{RESET}")
    print(f"{BLUE}{'=' * 60}{RESET}\n")

def print_success(text):
    print(f"{GREEN}✓ {text}{RESET}")

def print_warning(text):
    print(f"{YELLOW}⚠ {text}{RESET}")

def print_error(text):
    print(f"{RED}✗ {text}{RESET}")

def print_info(text):
    print(f"  {text}")

def test_imports():
    """Test if required libraries are available"""
    print_header("Testing Python Libraries")
    
    issues = []
    
    # Test PIL
    try:
        from PIL import Image, ImageDraw, ImageFont
        print_success("PIL (Pillow) installed")
    except ImportError as e:
        print_error(f"PIL not installed: {e}")
        issues.append("Install Pillow: pip3 install pillow")
    
    # Test RPi.GPIO
    try:
        import RPi.GPIO as GPIO
        print_success("RPi.GPIO installed")
    except ImportError as e:
        print_warning(f"RPi.GPIO not installed (normal on non-RPi): {e}")
        issues.append("If on Raspberry Pi, install: pip3 install RPi.GPIO")
    
    # Test spidev
    try:
        import spidev
        print_success("spidev installed")
    except ImportError as e:
        print_warning(f"spidev not installed (normal on non-RPi): {e}")
        issues.append("If on Raspberry Pi, install: pip3 install spidev")
    
    # Test waveshare library
    try:
        import waveshare_epd.epd2in13_V4 as epd_driver
        print_success("Waveshare epd2in13_V4 library installed (2.13 inch 3-color)")
    except ImportError as e:
        print_error(f"Waveshare library not installed: {e}")
        issues.append("Install Waveshare library - see docs/DISPLAY_SETUP.md")
    
    return issues

def test_spi_interface():
    """Test if SPI is enabled"""
    print_header("Testing SPI Interface")
    
    issues = []
    
    # Check if /dev/spidev0.0 exists
    if os.path.exists('/dev/spidev0.0'):
        print_success("SPI device /dev/spidev0.0 exists")
    else:
        print_error("SPI device not found")
        issues.append("Enable SPI: sudo raspi-config → Interface Options → SPI")
    
    # Check if SPI module is loaded
    try:
        with open('/proc/modules', 'r') as f:
            modules = f.read()
            if 'spi_bcm' in modules:
                print_success("SPI kernel module loaded")
            else:
                print_warning("SPI kernel module not loaded")
    except Exception as e:
        print_warning(f"Could not check kernel modules: {e}")
    
    return issues

def test_gpio_permissions():
    """Test GPIO permissions"""
    print_header("Testing GPIO Permissions")
    
    issues = []
    
    # Check if running as root
    if os.geteuid() == 0:
        print_success("Running as root (required for GPIO)")
    else:
        print_warning("Not running as root")
        print_info("GPIO access requires root. Run with: sudo python3 diagnose_display.py")
        issues.append("Run as root for GPIO access")
    
    # Check GPIO group membership
    try:
        import grp
        gpio_group = grp.getgrnam('gpio')
        if os.getegid() in [gpio_group.gr_gid]:
            print_success("User is in gpio group")
        else:
            print_warning("User not in gpio group")
            print_info("Add user to gpio group: sudo usermod -a -G gpio $USER")
    except Exception as e:
        print_warning(f"Could not check gpio group: {e}")
    
    return issues

def test_display_initialization():
    """Try to initialize the display"""
    print_header("Testing Display Initialization")
    
    issues = []
    
    try:
        # Try importing and initializing (2.13 inch V4)
        import waveshare_epd.epd2in13_V4 as epd_driver
        
        print_info("Attempting to initialize display...")
        print_info("(This may take a few seconds)")
        
        epd = epd_driver.EPD()
        epd.init()
        
        print_success("Display initialized successfully!")
        
        # Try a simple clear
        print_info("Testing display clear...")
        epd.Clear()
        
        print_success("Display clear successful!")
        
        # Put to sleep
        epd.sleep()
        print_success("Display put to sleep successfully!")
        
    except ImportError as e:
        print_error(f"Cannot import display library: {e}")
        issues.append("Install Waveshare library")
    except Exception as e:
        print_error(f"Display initialization failed: {e}")
        print_info(f"Error type: {type(e).__name__}")
        import traceback
        print_info("Full error trace:")
        traceback.print_exc()
        issues.append(f"Hardware error: {e}")
    
    return issues

def test_fonts():
    """Test font availability"""
    print_header("Testing Fonts")
    
    issues = []
    
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            print_success(f"Font found: {os.path.basename(font_path)}")
        else:
            print_warning(f"Font not found: {font_path}")
            issues.append("Install fonts: sudo apt-get install fonts-dejavu")
    
    return issues

def test_pendonn_config():
    """Test PenDonn configuration"""
    print_header("Testing PenDonn Configuration")
    
    issues = []
    
    config_path = "./config/config.json"
    if os.path.exists(config_path):
        print_success(f"Config file found: {config_path}")
        
        import json
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            display_config = config.get('display', {})
            
            if display_config.get('enabled'):
                print_success("Display is enabled in config")
            else:
                print_warning("Display is disabled in config")
                print_info("Enable in config.json: display.enabled = true")
            
            refresh = display_config.get('refresh_interval', 0)
            if refresh >= 30:
                print_success(f"Refresh interval: {refresh}s (optimal for e-paper)")
            else:
                print_warning(f"Refresh interval: {refresh}s (too fast for e-paper)")
                print_info("Set to 30+ seconds for e-paper displays")
                issues.append("Increase display.refresh_interval to 30+ in config.json")
        
        except Exception as e:
            print_error(f"Error reading config: {e}")
            issues.append("Fix config.json syntax")
    else:
        print_error(f"Config file not found: {config_path}")
        issues.append("Create config file or run from correct directory")
    
    return issues

def main():
    """Main diagnostic routine"""
    print(f"\n{BLUE}╔{'═' * 58}╗{RESET}")
    print(f"{BLUE}║{' ' * 10}PenDonn Display Diagnostic Tool{' ' * 17}║{RESET}")
    print(f"{BLUE}╚{'═' * 58}╝{RESET}")
    
    all_issues = []
    
    # Run all tests
    all_issues.extend(test_imports())
    all_issues.extend(test_spi_interface())
    all_issues.extend(test_gpio_permissions())
    all_issues.extend(test_fonts())
    all_issues.extend(test_pendonn_config())
    all_issues.extend(test_display_initialization())
    
    # Summary
    print_header("Diagnostic Summary")
    
    if not all_issues:
        print_success("All tests passed! Display should work correctly.")
        print_info("\nYou can now run PenDonn:")
        print_info("  sudo python3 main.py")
    else:
        print_error(f"Found {len(all_issues)} issue(s):\n")
        for i, issue in enumerate(all_issues, 1):
            print(f"  {i}. {issue}")
        
        print(f"\n{YELLOW}Fix these issues and run diagnostic again.{RESET}")
    
    print()

if __name__ == "__main__":
    main()
