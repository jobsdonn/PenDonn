#!/bin/bash

###############################################################################
# Deep Network Diagnostics
# Find out what's ACTUALLY managing (or killing) your WiFi
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Deep Network Diagnostics${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# ============================================================================
# 1. Check what's managing the network
# ============================================================================
echo -e "${YELLOW}[1] Checking network management systems...${NC}"
echo ""

echo -e "${BLUE}NetworkManager:${NC}"
systemctl is-active NetworkManager && echo "  Status: RUNNING" || echo "  Status: NOT RUNNING"
systemctl is-enabled NetworkManager && echo "  Enabled: YES" || echo "  Enabled: NO"
echo ""

echo -e "${BLUE}systemd-networkd:${NC}"
systemctl is-active systemd-networkd && echo "  Status: RUNNING" || echo "  Status: NOT RUNNING"
systemctl is-enabled systemd-networkd && echo "  Enabled: YES" || echo "  Enabled: NO"
echo ""

echo -e "${BLUE}dhcpcd:${NC}"
systemctl is-active dhcpcd && echo "  Status: RUNNING" || echo "  Status: NOT RUNNING"
systemctl is-enabled dhcpcd && echo "  Enabled: YES" || echo "  Enabled: NO"
echo ""

echo -e "${BLUE}wpa_supplicant:${NC}"
systemctl is-active wpa_supplicant && echo "  Status: RUNNING" || echo "  Status: NOT RUNNING"
systemctl is-enabled wpa_supplicant && echo "  Enabled: YES" || echo "  Enabled: NO"
echo ""

# ============================================================================
# 2. Check /etc/network/interfaces (old-style config)
# ============================================================================
echo -e "${YELLOW}[2] Checking /etc/network/interfaces...${NC}"
if [ -f /etc/network/interfaces ]; then
    echo -e "${BLUE}Content:${NC}"
    cat /etc/network/interfaces
else
    echo "  File not found"
fi
echo ""

# ============================================================================
# 3. Check netplan (newer system)
# ============================================================================
echo -e "${YELLOW}[3] Checking netplan configuration...${NC}"
if [ -d /etc/netplan ]; then
    echo -e "${BLUE}Netplan files:${NC}"
    ls -la /etc/netplan/
    echo ""
    for file in /etc/netplan/*.yaml; do
        if [ -f "$file" ]; then
            echo -e "${BLUE}Content of $file:${NC}"
            cat "$file"
            echo ""
        fi
    done
else
    echo "  No netplan directory"
fi
echo ""

# ============================================================================
# 4. Check NetworkManager connections
# ============================================================================
echo -e "${YELLOW}[4] NetworkManager connections...${NC}"
if [ -d /etc/NetworkManager/system-connections ]; then
    echo -e "${BLUE}Saved connections:${NC}"
    ls -la /etc/NetworkManager/system-connections/
    echo ""
    
    for conn in /etc/NetworkManager/system-connections/*; do
        if [ -f "$conn" ]; then
            echo -e "${BLUE}Connection: $(basename "$conn")${NC}"
            grep -E "^\[|^interface-name=|^autoconnect=" "$conn" 2>/dev/null || echo "  (no relevant settings)"
            echo ""
        fi
    done
fi
echo ""

# ============================================================================
# 5. Check current interface status
# ============================================================================
echo -e "${YELLOW}[5] Current interface status...${NC}"
echo ""

echo -e "${BLUE}wlan0 status:${NC}"
ip addr show wlan0 2>/dev/null || echo "  wlan0 not found!"
echo ""

echo -e "${BLUE}wlan0 in NetworkManager:${NC}"
nmcli device show wlan0 2>/dev/null || echo "  Not managed by NetworkManager"
echo ""

echo -e "${BLUE}All devices in NetworkManager:${NC}"
nmcli device status
echo ""

# ============================================================================
# 6. Check what's in kernel logs about WiFi
# ============================================================================
echo -e "${YELLOW}[6] Recent WiFi-related kernel messages...${NC}"
dmesg | grep -i -E "brcmfmac|wlan0|wifi" | tail -20
echo ""

# ============================================================================
# 7. Check for any PenDonn services that might interfere
# ============================================================================
echo -e "${YELLOW}[7] Checking PenDonn services...${NC}"
echo ""

systemctl list-units --all | grep pendonn | while read -r line; do
    echo "$line"
done
echo ""

# ============================================================================
# 8. Check NetworkManager logs
# ============================================================================
echo -e "${YELLOW}[8] Recent NetworkManager logs...${NC}"
journalctl -u NetworkManager --no-pager -n 30
echo ""

# ============================================================================
# Summary
# ============================================================================
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Diagnostics Complete${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}Save this output and share it:${NC}"
echo "  ${BLUE}sudo bash this_script.sh | tee network-diagnostics.log${NC}"
echo ""
