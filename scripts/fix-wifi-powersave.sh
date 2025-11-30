#!/bin/bash

###############################################################################
# Fix WiFi Power Management (Broadcom brcmfmac)
# 
# Problem: WiFi connects, then goes to sleep after ~5 seconds and never wakes
# Solution: Disable power management on WiFi interface
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Fix WiFi Power Management (Disable Sleep)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}ERROR: Please run as root (sudo)${NC}"
    exit 1
fi

echo -e "${YELLOW}The Problem:${NC}"
echo "  • WiFi connects after boot"
echo "  • After ~5 seconds, it goes to sleep (power save)"
echo "  • It never wakes up - you lose connection"
echo ""
echo -e "${YELLOW}The Solution:${NC}"
echo "  • Disable WiFi power management completely"
echo "  • Create systemd service to keep it disabled"
echo ""
read -p "Apply fix? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi
echo ""

# ============================================================================
# Method 1: Disable via NetworkManager
# ============================================================================
echo -e "${BLUE}[1/3] Configuring NetworkManager to disable power save...${NC}"

NMCONF="/etc/NetworkManager/NetworkManager.conf"

# Backup
cp "$NMCONF" "${NMCONF}.backup-$(date +%Y%m%d_%H%M%S)"

# Check if [connection] section exists
if grep -q "^\[connection\]" "$NMCONF"; then
    # Add wifi.powersave=2 to existing section if not present
    if ! grep -q "wifi.powersave" "$NMCONF"; then
        sed -i '/^\[connection\]/a wifi.powersave=2' "$NMCONF"
    else
        # Update existing setting
        sed -i 's/^wifi.powersave=.*/wifi.powersave=2/' "$NMCONF"
    fi
else
    # Create [connection] section
    echo "" >> "$NMCONF"
    echo "[connection]" >> "$NMCONF"
    echo "wifi.powersave=2" >> "$NMCONF"
fi

echo -e "${GREEN}✓ NetworkManager configured${NC}"
echo ""

# ============================================================================
# Method 2: Create systemd service to force power management off
# ============================================================================
echo -e "${BLUE}[2/3] Creating WiFi power management service...${NC}"

cat > /etc/systemd/system/wifi-powersave-off.service << 'EOF'
[Unit]
Description=Disable WiFi Power Management
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/iw dev wlan0 set power_save off
ExecStartPost=/bin/sleep 2
ExecStartPost=/usr/sbin/iw dev wlan0 set power_save off

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable wifi-powersave-off.service
systemctl start wifi-powersave-off.service

echo -e "${GREEN}✓ Service created and enabled${NC}"
echo ""

# ============================================================================
# Method 3: Disable power management NOW
# ============================================================================
echo -e "${BLUE}[3/3] Disabling power management on wlan0 NOW...${NC}"

# Disable via iw
iw dev wlan0 set power_save off 2>/dev/null && echo -e "${GREEN}✓ Power save disabled via iw${NC}" || echo -e "${YELLOW}! iw command failed (might not be connected yet)${NC}"

# Disable via iwconfig
iwconfig wlan0 power off 2>/dev/null && echo -e "${GREEN}✓ Power management disabled via iwconfig${NC}" || echo -e "${YELLOW}! iwconfig command failed${NC}"

echo ""

# ============================================================================
# Restart NetworkManager
# ============================================================================
echo -e "${BLUE}Restarting NetworkManager with new config...${NC}"
systemctl restart NetworkManager
sleep 5

echo -e "${GREEN}✓ NetworkManager restarted${NC}"
echo ""

# ============================================================================
# Verify
# ============================================================================
echo -e "${BLUE}Checking current power management status...${NC}"
echo ""

echo -e "${YELLOW}Via iw:${NC}"
iw dev wlan0 get power_save 2>/dev/null || echo "  wlan0 not available yet"

echo ""
echo -e "${YELLOW}Via iwconfig:${NC}"
iwconfig wlan0 2>/dev/null | grep "Power Management" || echo "  wlan0 not available yet"

echo ""

# ============================================================================
# Done
# ============================================================================
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}WiFi Power Management Fix Applied${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}What was done:${NC}"
echo "  1. NetworkManager configured: wifi.powersave=2 (disabled)"
echo "  2. Systemd service created: wifi-powersave-off.service"
echo "  3. Power management disabled on wlan0"
echo ""
echo -e "${YELLOW}Next step - CRITICAL TEST:${NC}"
echo "  ${BLUE}sudo reboot${NC}"
echo ""
echo "After reboot:"
echo "  • WiFi should connect"
echo "  • It should STAY connected (not sleep after 5 seconds)"
echo "  • You should keep SSH access"
echo ""
echo -e "${GREEN}The WiFi power save bug should now be fixed!${NC}"
echo ""
