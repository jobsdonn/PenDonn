#!/bin/bash

###############################################################################
# Fix NetworkManager Configuration
# 
# Problem: NetworkManager.conf has "managed=false" which tells NetworkManager
# to ignore ALL interfaces, including your WiFi!
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Fix NetworkManager Configuration${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}ERROR: Please run as root (sudo)${NC}"
    exit 1
fi

NMCONF="/etc/NetworkManager/NetworkManager.conf"

echo -e "${YELLOW}Current NetworkManager.conf:${NC}"
cat "$NMCONF"
echo ""

echo -e "${RED}Problem: managed=false tells NetworkManager to ignore ALL interfaces!${NC}"
echo -e "${GREEN}Solution: Change to managed=true so NetworkManager handles WiFi${NC}"
echo ""
read -p "Fix this now? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi
echo ""

# Backup
cp "$NMCONF" "${NMCONF}.backup-broken-$(date +%Y%m%d_%H%M%S)"
echo -e "${GREEN}✓ Backed up current config${NC}"

# Fix the config - change managed=false to managed=true
sed -i 's/managed=false/managed=true/g' "$NMCONF"

echo ""
echo -e "${YELLOW}New NetworkManager.conf:${NC}"
cat "$NMCONF"
echo ""

echo -e "${BLUE}Restarting NetworkManager...${NC}"
systemctl restart NetworkManager
sleep 3

if systemctl is-active --quiet NetworkManager; then
    echo -e "${GREEN}✓ NetworkManager restarted successfully${NC}"
else
    echo -e "${RED}✗ NetworkManager failed to start!${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}NetworkManager Fixed!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}What changed:${NC}"
echo "  • managed=false → managed=true"
echo "  • NetworkManager will now manage wlan0"
echo ""
echo -e "${YELLOW}Check WiFi status:${NC}"
nmcli device status
echo ""

WIFI_STATUS=$(nmcli -t -f DEVICE,STATE device status | grep "^wlan0:" | cut -d':' -f2)

if [ "$WIFI_STATUS" = "connected" ]; then
    echo -e "${GREEN}✓ wlan0 is connected!${NC}"
    echo ""
    echo -e "${YELLOW}Now reboot to test if it stays connected:${NC}"
    echo "  ${BLUE}sudo reboot${NC}"
else
    echo -e "${YELLOW}wlan0 is not connected yet${NC}"
    echo ""
    echo -e "${YELLOW}Connect to WiFi:${NC}"
    echo "  ${BLUE}nmcli device wifi list${NC}"
    echo "  ${BLUE}nmcli device wifi connect 'YourSSID' password 'YourPassword'${NC}"
    echo ""
    echo -e "${YELLOW}Then reboot to test:${NC}"
    echo "  ${BLUE}sudo reboot${NC}"
fi
echo ""
