#!/bin/bash

###############################################################################
# PenDonn - WiFi Adapter Troubleshooting Tool
# Diagnoses why external WiFi adapters are not showing up
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║           WiFi Adapter Troubleshooting Tool                    ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}[ERROR]${NC} Please run as root (use sudo)"
    exit 1
fi

echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}1. Checking USB Devices${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}All USB devices:${NC}"
lsusb
echo ""

echo -e "${YELLOW}Looking for WiFi adapters by chipset:${NC}"
RTL8812_FOUND=$(lsusb | grep -i "Realtek.*8812\|0bda:8812\|0bda:881a\|0bda:881b\|0bda:881c")
RTL8811_FOUND=$(lsusb | grep -i "Realtek.*8811\|0bda:8811")
RTL8188_FOUND=$(lsusb | grep -i "Realtek.*8188\|0bda:8179")
RTL8814_FOUND=$(lsusb | grep -i "Realtek.*8814\|0bda:8813")
ATHEROS_FOUND=$(lsusb | grep -i "Atheros\|0cf3:9271")

if [ -n "$RTL8812_FOUND" ]; then
    echo -e "${GREEN}✓ RTL8812AU/RTL8811AU detected:${NC}"
    echo "$RTL8812_FOUND"
fi

if [ -n "$RTL8811_FOUND" ]; then
    echo -e "${GREEN}✓ RTL8811AU detected:${NC}"
    echo "$RTL8811_FOUND"
fi

if [ -n "$RTL8188_FOUND" ]; then
    echo -e "${GREEN}✓ RTL8188EUS detected:${NC}"
    echo "$RTL8188_FOUND"
fi

if [ -n "$RTL8814_FOUND" ]; then
    echo -e "${GREEN}✓ RTL8814AU detected:${NC}"
    echo "$RTL8814_FOUND"
fi

if [ -n "$ATHEROS_FOUND" ]; then
    echo -e "${GREEN}✓ Atheros AR9271 detected:${NC}"
    echo "$ATHEROS_FOUND"
fi

if [ -z "$RTL8812_FOUND" ] && [ -z "$RTL8811_FOUND" ] && [ -z "$RTL8188_FOUND" ] && [ -z "$RTL8814_FOUND" ] && [ -z "$ATHEROS_FOUND" ]; then
    echo -e "${RED}✗ No supported WiFi adapters detected in USB!${NC}"
    echo -e "${YELLOW}Please check:${NC}"
    echo "  1. Is the adapter plugged in?"
    echo "  2. Try a different USB port"
    echo "  3. Check if adapter has power LED (should be lit)"
fi

echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}2. Checking Network Interfaces${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}All network interfaces (ip link):${NC}"
ip link show
echo ""

echo -e "${YELLOW}WiFi interfaces (iw dev):${NC}"
if command -v iw &> /dev/null; then
    iw dev
else
    echo -e "${RED}iw command not found${NC}"
fi
echo ""

echo -e "${YELLOW}Wireless interfaces (iwconfig):${NC}"
if command -v iwconfig &> /dev/null; then
    iwconfig 2>&1 | grep -v "no wireless"
else
    echo -e "${RED}iwconfig command not found${NC}"
fi
echo ""

# Count WiFi interfaces
WLAN_COUNT=$(ip link show | grep -c "wlan")
echo -e "${BLUE}Total WiFi interfaces found: ${GREEN}$WLAN_COUNT${NC}"
if [ "$WLAN_COUNT" -lt 3 ]; then
    echo -e "${YELLOW}⚠️  Expected 3 interfaces (wlan0, wlan1, wlan2)${NC}"
    echo -e "${YELLOW}   You need 1 built-in + 2 external WiFi adapters${NC}"
fi
echo ""

echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}3. Checking Loaded Drivers${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}Loaded WiFi kernel modules:${NC}"
LOADED_MODULES=$(lsmod | grep -E "8188|8812|8814|8821|8822|mt76|rt2800|ath9k|cfg80211|mac80211")
if [ -n "$LOADED_MODULES" ]; then
    echo "$LOADED_MODULES"
else
    echo -e "${RED}No WiFi kernel modules loaded!${NC}"
fi
echo ""

# Check specific drivers
echo -e "${YELLOW}Driver status:${NC}"
if lsmod | grep -q 8812au; then
    echo -e "${GREEN}✓ RTL8812AU driver loaded${NC}"
else
    echo -e "${RED}✗ RTL8812AU driver NOT loaded${NC}"
fi

if lsmod | grep -q 88XXau; then
    echo -e "${GREEN}✓ 88XXau (alternative 8812) driver loaded${NC}"
else
    echo -e "${RED}✗ 88XXau driver NOT loaded${NC}"
fi

if lsmod | grep -q 8188eu; then
    echo -e "${GREEN}✓ RTL8188EU driver loaded${NC}"
else
    echo -e "${RED}✗ RTL8188EU driver NOT loaded${NC}"
fi
echo ""

echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}4. Checking Installed Drivers${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}Checking for compiled driver modules:${NC}"
if [ -d /lib/modules/$(uname -r)/kernel/drivers/net/wireless ]; then
    echo -e "${BLUE}Searching for Realtek drivers...${NC}"
    find /lib/modules/$(uname -r) -name "*8812*.ko" -o -name "*88XXau*.ko" | while read -r driver; do
        echo -e "${GREEN}Found: $driver${NC}"
    done
    
    if ! find /lib/modules/$(uname -r) -name "*8812*.ko" -o -name "*88XXau*.ko" | grep -q .; then
        echo -e "${RED}No RTL8812AU driver found in kernel modules!${NC}"
    fi
else
    echo -e "${RED}Wireless driver directory not found${NC}"
fi
echo ""

echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}5. Checking dmesg for USB/Driver Messages${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}Recent USB device messages (last 30 lines):${NC}"
dmesg | grep -i "usb\|realtek\|rtl8\|8812\|8811\|wifi\|wlan" | tail -30
echo ""

echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}6. Checking for Blacklisted Drivers${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}Checking blacklist files:${NC}"
if grep -r "8812\|88XXau" /etc/modprobe.d/ 2>/dev/null; then
    echo -e "${RED}Driver might be blacklisted!${NC}"
else
    echo -e "${GREEN}No blacklist entries found${NC}"
fi
echo ""

echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}Diagnosis Summary${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# Diagnosis
HAS_USB_DEVICE=false
HAS_DRIVER=false
HAS_INTERFACE=false

if [ -n "$RTL8812_FOUND" ] || [ -n "$RTL8811_FOUND" ] || [ -n "$RTL8188_FOUND" ] || [ -n "$RTL8814_FOUND" ]; then
    HAS_USB_DEVICE=true
fi

if lsmod | grep -q "8812au\|88XXau\|8188eu"; then
    HAS_DRIVER=true
fi

if [ "$WLAN_COUNT" -ge 2 ]; then
    HAS_INTERFACE=true
fi

echo -e "${YELLOW}Checklist:${NC}"
if [ "$HAS_USB_DEVICE" = true ]; then
    echo -e "${GREEN}✓ USB WiFi adapter detected${NC}"
else
    echo -e "${RED}✗ No USB WiFi adapter detected${NC}"
    echo -e "  ${BLUE}Action: Check physical connection${NC}"
fi

if [ "$HAS_DRIVER" = true ]; then
    echo -e "${GREEN}✓ Driver loaded${NC}"
else
    echo -e "${RED}✗ Driver not loaded${NC}"
    echo -e "  ${BLUE}Action: Install or load driver${NC}"
fi

if [ "$HAS_INTERFACE" = true ]; then
    echo -e "${GREEN}✓ WiFi interface(s) present${NC}"
else
    echo -e "${RED}✗ No WiFi interfaces${NC}"
    echo -e "  ${BLUE}Action: Fix driver loading${NC}"
fi

echo ""
echo -e "${YELLOW}═══ Recommended Actions ═══${NC}"
echo ""

if [ "$HAS_USB_DEVICE" = false ]; then
    echo -e "${BLUE}1. USB device not detected:${NC}"
    echo "   - Unplug and replug the adapter"
    echo "   - Try a different USB port (use USB 2.0 ports, not USB 3.0)"
    echo "   - Check if adapter works on another computer"
    echo "   - Look for a power LED on the adapter"
    echo ""
fi

if [ "$HAS_USB_DEVICE" = true ] && [ "$HAS_DRIVER" = false ]; then
    echo -e "${BLUE}2. Driver not loaded (but USB device detected):${NC}"
    echo "   - Install driver: ${GREEN}sudo scripts/install-wifi-drivers.sh${NC}"
    echo "   - After installation: ${GREEN}sudo reboot${NC}"
    echo "   - Check dmesg after reboot: ${GREEN}dmesg | grep -i rtl${NC}"
    echo ""
fi

if [ "$HAS_DRIVER" = true ] && [ "$HAS_INTERFACE" = false ]; then
    echo -e "${BLUE}3. Driver loaded but no interface:${NC}"
    echo "   - Unload driver: ${GREEN}sudo modprobe -r 8812au${NC}"
    echo "   - Reload driver: ${GREEN}sudo modprobe 8812au${NC}"
    echo "   - Check dmesg: ${GREEN}dmesg | tail -20${NC}"
    echo "   - Reboot if still not working: ${GREEN}sudo reboot${NC}"
    echo ""
fi

if [ "$WLAN_COUNT" -eq 1 ]; then
    echo -e "${BLUE}4. Only 1 WiFi interface (need 3 total):${NC}"
    echo "   - You need 2 external WiFi adapters"
    echo "   - Current: 1 built-in (wlan0) + 0 external"
    echo "   - Required: 1 built-in + 2 external (wlan1, wlan2)"
    echo ""
fi

echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}For manual driver loading, try:${NC}"
echo -e "  ${GREEN}sudo modprobe 8812au${NC}      # For RTL8812AU/RTL8811AU"
echo -e "  ${GREEN}sudo modprobe 88XXau${NC}      # Alternative name"
echo -e "  ${GREEN}sudo modprobe 8188eu${NC}      # For RTL8188EU"
echo -e "  ${GREEN}dmesg | tail -50${NC}          # Check for errors"
echo ""
echo -e "${YELLOW}To see detailed USB info:${NC}"
echo -e "  ${GREEN}lsusb -v${NC}"
echo ""
