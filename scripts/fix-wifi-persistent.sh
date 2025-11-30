#!/bin/bash

###############################################################################
# Fix WiFi - Save Connection Directly in NetworkManager
# 
# Problem: Netplan creates the connection dynamically, but it's not persistent
# Solution: Save WiFi credentials directly in NetworkManager (bypassing netplan)
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Fix WiFi Connection (Save to NetworkManager)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}ERROR: Please run as root (sudo)${NC}"
    exit 1
fi

echo -e "${YELLOW}The Problem:${NC}"
echo "  • Your WiFi is managed by netplan (dynamic)"
echo "  • Connection isn't saved in NetworkManager properly"
echo "  • After reboot, the connection may not reconnect"
echo ""
echo -e "${YELLOW}The Solution:${NC}"
echo "  • Remove netplan WiFi config"
echo "  • Save WiFi directly to NetworkManager"
echo "  • NetworkManager will handle reconnection"
echo ""
read -p "Fix this now? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi
echo ""

# ============================================================================
# Step 1: Get WiFi info from current connection
# ============================================================================
echo -e "${BLUE}[1/4] Getting current WiFi information...${NC}"

CURRENT_SSID=$(nmcli -t -f active,ssid dev wifi | grep '^yes' | cut -d':' -f2)

if [ -z "$CURRENT_SSID" ]; then
    echo -e "${RED}Error: Not connected to WiFi${NC}"
    exit 1
fi

echo -e "  Current SSID: ${GREEN}$CURRENT_SSID${NC}"

# Get password from user
echo ""
read -p "Enter WiFi password for '$CURRENT_SSID': " WIFI_PASSWORD
echo ""

# ============================================================================
# Step 2: Remove netplan WiFi config
# ============================================================================
echo -e "${BLUE}[2/4] Removing netplan WiFi configuration...${NC}"

# Backup netplan files
if [ -d /etc/netplan ]; then
    mkdir -p /etc/netplan.backup
    cp /etc/netplan/*.yaml /etc/netplan.backup/ 2>/dev/null || true
    echo -e "  ${GREEN}✓${NC} Backed up netplan configs"
fi

# Remove netplan WiFi configs
rm -f /etc/netplan/*NM*.yaml 2>/dev/null
rm -f /etc/netplan/*wlan*.yaml 2>/dev/null
echo -e "  ${GREEN}✓${NC} Removed netplan WiFi configs"
echo ""

# ============================================================================
# Step 3: Delete old NetworkManager connection
# ============================================================================
echo -e "${BLUE}[3/4] Removing old connection...${NC}"

# Delete the netplan-created connection
nmcli connection delete "netplan-wlan0-$CURRENT_SSID" 2>/dev/null || true
nmcli connection delete "$CURRENT_SSID" 2>/dev/null || true

echo -e "  ${GREEN}✓${NC} Old connection removed"
echo ""

# ============================================================================
# Step 4: Create new persistent NetworkManager connection
# ============================================================================
echo -e "${BLUE}[4/4] Creating persistent NetworkManager connection...${NC}"

# Connect to WiFi (this saves it to NetworkManager)
nmcli device wifi connect "$CURRENT_SSID" password "$WIFI_PASSWORD"

if [ $? -eq 0 ]; then
    echo -e "  ${GREEN}✓${NC} Connected and saved to NetworkManager"
else
    echo -e "  ${RED}✗${NC} Failed to connect"
    exit 1
fi

# Make sure autoconnect is enabled
nmcli connection modify "$CURRENT_SSID" connection.autoconnect yes

echo -e "  ${GREEN}✓${NC} Autoconnect enabled"
echo ""

# ============================================================================
# Verify
# ============================================================================
echo -e "${BLUE}Verifying...${NC}"
echo ""

echo -e "${YELLOW}NetworkManager connections:${NC}"
nmcli connection show
echo ""

echo -e "${YELLOW}Saved connection files:${NC}"
ls -la /etc/NetworkManager/system-connections/
echo ""

if [ -f "/etc/NetworkManager/system-connections/$CURRENT_SSID.nmconnection" ]; then
    echo -e "${GREEN}✓ Connection saved to: /etc/NetworkManager/system-connections/$CURRENT_SSID.nmconnection${NC}"
else
    echo -e "${YELLOW}Connection might be saved with a different filename${NC}"
fi
echo ""

# ============================================================================
# Done
# ============================================================================
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}WiFi Fixed!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}What changed:${NC}"
echo "  • Removed netplan WiFi config"
echo "  • Saved WiFi directly to NetworkManager"
echo "  • Connection is now persistent"
echo ""
echo -e "${YELLOW}Test it:${NC}"
echo "  1. Check you're still connected:"
echo "     ${BLUE}nmcli device status${NC}"
echo ""
echo "  2. REBOOT to test persistence:"
echo "     ${BLUE}sudo reboot${NC}"
echo ""
echo "  3. After reboot, check WiFi:"
echo "     ${BLUE}nmcli device status${NC}"
echo "     ${BLUE}ping -c 5 google.com${NC}"
echo ""
echo -e "${GREEN}Your WiFi should now stay connected after reboot!${NC}"
echo ""
