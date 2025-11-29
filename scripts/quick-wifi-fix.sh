#!/bin/bash

# PenDonn - Quick WiFi Fix Test Script
# This script applies the most common fixes for WiFi disconnection issues
# Based on analysis of Ragnar and other working Raspberry Pi systems

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PenDonn WiFi Quick Fix - Common Issues${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}ERROR: Please run as root (sudo)${NC}"
    exit 1
fi

echo -e "${YELLOW}This script will check and fix common WiFi issues:${NC}"
echo "1. Check ModemManager (often causes WiFi disconnects)"
echo "2. Verify rfkill status"
echo "3. Check NetworkManager configuration"
echo "4. Check for known problematic services"
echo "5. Check wlan0 current status"
echo ""
read -p "Press Enter to continue or Ctrl+C to cancel..."
echo ""

# 1. Check ModemManager
echo -e "${BLUE}[1/5] Checking ModemManager...${NC}"
if systemctl is-active --quiet ModemManager; then
    echo -e "${RED}⚠ ModemManager is RUNNING - This is a common cause of WiFi issues!${NC}"
    echo "   ModemManager scans all interfaces looking for modems, which disrupts WiFi."
    echo ""
    read -p "   Disable ModemManager? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        systemctl stop ModemManager
        systemctl disable ModemManager
        systemctl mask ModemManager
        echo -e "   ${GREEN}✓ ModemManager stopped and disabled${NC}"
    fi
else
    echo -e "${GREEN}✓ ModemManager not running${NC}"
fi
echo ""

# 2. Check rfkill
echo -e "${BLUE}[2/5] Checking rfkill status...${NC}"
if command -v rfkill >/dev/null 2>&1; then
    BLOCKED=$(rfkill list wifi | grep -c "Soft blocked: yes" || echo "0")
    if [ "$BLOCKED" -gt 0 ]; then
        echo -e "${RED}⚠ WiFi is soft-blocked!${NC}"
        rfkill unblock wifi
        echo -e "${GREEN}✓ WiFi unblocked${NC}"
    else
        echo -e "${GREEN}✓ WiFi not blocked${NC}"
    fi
    rfkill list wifi
else
    echo -e "${YELLOW}⚠ rfkill not available${NC}"
fi
echo ""

# 3. Check NetworkManager configuration
echo -e "${BLUE}[3/5] Checking NetworkManager configuration...${NC}"
NM_CONF="/etc/NetworkManager/NetworkManager.conf"

if [ -f "$NM_CONF" ]; then
    echo "Current NetworkManager config:"
    cat "$NM_CONF"
    echo ""
    
    # Check for critical settings
    NEEDS_UPDATE=0
    
    if ! grep -q "wifi.scan-rand-mac-address=no" "$NM_CONF"; then
        echo -e "${YELLOW}⚠ Missing: wifi.scan-rand-mac-address=no${NC}"
        NEEDS_UPDATE=1
    fi
    
    if ! grep -q "wifi.powersave=2" "$NM_CONF"; then
        echo -e "${YELLOW}⚠ Missing: wifi.powersave=2${NC}"
        NEEDS_UPDATE=1
    fi
    
    if [ $NEEDS_UPDATE -eq 1 ]; then
        echo ""
        echo -e "${YELLOW}These settings should already be added by the installer.${NC}"
        echo -e "${YELLOW}If they're missing, there may be an installer issue.${NC}"
    else
        echo -e "${GREEN}✓ NetworkManager configuration looks correct${NC}"
    fi
else
    echo -e "${RED}⚠ NetworkManager.conf not found!${NC}"
fi
echo ""

# 4. Check for problematic services at boot
echo -e "${BLUE}[4/5] Checking boot timing (systemd-analyze)...${NC}"
if command -v systemd-analyze >/dev/null 2>&1; then
    echo "Services starting around WiFi connection time:"
    systemd-analyze blame | head -20
    echo ""
    echo "Critical chain:"
    systemd-analyze critical-chain | head -10
else
    echo -e "${YELLOW}systemd-analyze not available${NC}"
fi
echo ""

# 5. Current wlan0 status
echo -e "${BLUE}[5/5] Checking wlan0 current status...${NC}"
if [ -e /sys/class/net/wlan0/operstate ]; then
    STATE=$(cat /sys/class/net/wlan0/operstate)
    echo "wlan0 state: $STATE"
    
    if [ "$STATE" = "up" ]; then
        echo -e "${GREEN}✓ wlan0 is UP${NC}"
        echo ""
        echo "Current connection:"
        iwgetid -r 2>/dev/null || echo "Not connected to any network"
        echo ""
        echo "IP address:"
        ip addr show wlan0 | grep "inet " || echo "No IP address assigned"
    else
        echo -e "${RED}⚠ wlan0 is $STATE (should be 'up')${NC}"
    fi
else
    echo -e "${RED}⚠ wlan0 interface not found!${NC}"
fi
echo ""

# Summary and recommendations
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Quick Check Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo "1. If ModemManager was running and you disabled it → Reboot now"
echo "   ${BLUE}sudo reboot${NC}"
echo ""
echo "2. If WiFi still disconnects after reboot → Run full diagnostic"
echo "   ${BLUE}sudo bash diagnose-wifi-issue.sh${NC}"
echo ""
echo "3. Check recent NetworkManager logs for clues:"
echo "   ${BLUE}sudo journalctl -u NetworkManager -n 50 --no-pager${NC}"
echo ""
echo "4. Monitor WiFi state during boot (requires console/monitor access):"
echo "   ${BLUE}watch -n 0.5 'cat /sys/class/net/wlan0/operstate'${NC}"
echo ""
