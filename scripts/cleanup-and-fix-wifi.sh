#!/bin/bash

# PenDonn - Complete WiFi Management Cleanup & Redesign
# This script removes ALL old WiFi management code and implements a simple, working solution
# Based on proven Ragnar approach

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PenDonn WiFi Management Cleanup & Redesign${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}ERROR: Please run as root (sudo)${NC}"
    exit 1
fi

echo -e "${YELLOW}This script will:${NC}"
echo "1. Remove all old WiFi management services and scripts"
echo "2. Remove udev rules (they cause race conditions)"
echo "3. Configure NetworkManager properly (the Ragnar way)"
echo "4. Set up minimal, working WiFi management"
echo ""
echo -e "${RED}WARNING: This will restart NetworkManager${NC}"
echo ""
read -p "Press Enter to continue or Ctrl+C to cancel..."
echo ""

# ============================================================================
# STEP 1: Remove ALL old WiFi management code
# ============================================================================
echo -e "${BLUE}[1/5] Removing old WiFi management services and scripts...${NC}"

# Stop and disable old services
systemctl stop pendonn-wifi-keeper.service 2>/dev/null || true
systemctl disable pendonn-wifi-keeper.service 2>/dev/null || true
systemctl stop pendonn-wifi-autofix.service 2>/dev/null || true
systemctl disable pendonn-wifi-autofix.service 2>/dev/null || true

# Remove service files
rm -f /etc/systemd/system/pendonn-wifi-keeper.service
rm -f /etc/systemd/system/pendonn-wifi-autofix.service

# Remove scripts
rm -f /usr/local/bin/pendonn-wifi-keeper.sh
rm -f /usr/local/bin/pendonn-wifi-autofix.sh

# Remove udev rules (they cause race conditions!)
rm -f /etc/udev/rules.d/70-persistent-wifi.rules
rm -f /etc/udev/rules.d/72-usb-wifi.rules

# Reload systemd and udev
systemctl daemon-reload
udevadm control --reload-rules
udevadm trigger

echo -e "${GREEN}✓ Old WiFi management removed${NC}"
echo ""

# ============================================================================
# STEP 2: Stop and disable ModemManager (common problem)
# ============================================================================
echo -e "${BLUE}[2/5] Checking ModemManager...${NC}"

if systemctl is-active --quiet ModemManager; then
    echo -e "${YELLOW}ModemManager is running - this often causes WiFi issues${NC}"
    systemctl stop ModemManager
    systemctl disable ModemManager
    systemctl mask ModemManager
    echo -e "${GREEN}✓ ModemManager stopped and disabled${NC}"
else
    echo -e "${GREEN}✓ ModemManager not running${NC}"
fi
echo ""

# ============================================================================
# STEP 3: Configure NetworkManager properly (the Ragnar way)
# ============================================================================
echo -e "${BLUE}[3/5] Configuring NetworkManager...${NC}"

# Backup existing config
if [ -f /etc/NetworkManager/NetworkManager.conf ]; then
    cp /etc/NetworkManager/NetworkManager.conf /etc/NetworkManager/NetworkManager.conf.backup-$(date +%Y%m%d)
fi

# Create clean, working configuration
cat > /etc/NetworkManager/NetworkManager.conf << 'EOF'
[main]
plugins=ifupdown,keyfile
dhcp=dhclient
dns=default

[device]
# Don't randomize MAC during scans - this disrupts connections!
wifi.scan-rand-mac-address=no
# Use wpa_supplicant backend
wifi.backend=wpa_supplicant

[connection]
# Disable WiFi power save (can cause disconnects)
wifi.powersave=2
# Don't change MAC addresses
wifi.cloned-mac-address=preserve

[keyfile]
# Don't manage wlan1/wlan2 - those are for pentesting
unmanaged-devices=interface-name:wlan1;interface-name:wlan2
EOF

echo -e "${GREEN}✓ NetworkManager configured${NC}"
echo ""

# ============================================================================
# STEP 4: Ensure rfkill isn't blocking WiFi
# ============================================================================
echo -e "${BLUE}[4/5] Checking rfkill status...${NC}"

if command -v rfkill >/dev/null 2>&1; then
    rfkill unblock wifi
    echo -e "${GREEN}✓ WiFi unblocked${NC}"
    rfkill list wifi
else
    echo -e "${YELLOW}⚠ rfkill not available${NC}"
fi
echo ""

# ============================================================================
# STEP 5: Restart NetworkManager with new config
# ============================================================================
echo -e "${BLUE}[5/5] Restarting NetworkManager...${NC}"

systemctl restart NetworkManager

# Wait for NetworkManager to be ready
sleep 5

# Check status
if systemctl is-active --quiet NetworkManager; then
    echo -e "${GREEN}✓ NetworkManager restarted successfully${NC}"
else
    echo -e "${RED}✗ NetworkManager failed to start!${NC}"
    echo "Check logs: journalctl -u NetworkManager -n 50"
    exit 1
fi
echo ""

# ============================================================================
# Summary and next steps
# ============================================================================
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}WiFi Management Cleanup Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}What was done:${NC}"
echo "  ✓ Removed old WiFi keeper and auto-fix services"
echo "  ✓ Removed udev rules (they were causing race conditions)"
echo "  ✓ Configured NetworkManager properly:"
echo "    - Disabled MAC randomization during scans"
echo "    - Disabled WiFi power save"
echo "    - Told NM to ignore wlan1/wlan2 (pentesting interfaces)"
echo "  ✓ Stopped ModemManager (if it was running)"
echo "  ✓ Unblocked WiFi with rfkill"
echo ""
echo -e "${YELLOW}How WiFi works now:${NC}"
echo "  • NetworkManager manages wlan0 (built-in WiFi) automatically"
echo "  • wlan1/wlan2 (external adapters) are ignored by NetworkManager"
echo "  • No udev rules - let the system name interfaces naturally"
echo "  • No custom services fighting with NetworkManager"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo "1. Check current WiFi status:"
echo "   ${BLUE}nmcli device status${NC}"
echo ""
echo "2. If wlan0 is disconnected, connect to your WiFi:"
echo "   ${BLUE}nmcli device wifi list${NC}"
echo "   ${BLUE}nmcli device wifi connect 'YourSSID' password 'YourPassword'${NC}"
echo ""
echo "3. REBOOT to test if WiFi stays connected:"
echo "   ${BLUE}sudo reboot${NC}"
echo ""
echo "4. After reboot, check if WiFi is still connected:"
echo "   ${BLUE}nmcli device status${NC}"
echo "   ${BLUE}ping -c 5 8.8.8.8${NC}"
echo ""
echo -e "${GREEN}If WiFi stays connected after reboot → Problem solved!${NC}"
echo -e "${YELLOW}If WiFi still disconnects → Run diagnose-wifi-issue.sh${NC}"
echo ""
