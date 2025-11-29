#!/bin/bash

###############################################################################
# PenDonn WiFi Cleanup & Fix (MAC Address Based)
# 
# This script:
# 1. Removes old WiFi management (services, udev rules, scripts)
# 2. Detects WiFi adapters by MAC address (stable!)
# 3. Configures NetworkManager using MACs
# 4. Onboard WiFi (Broadcom) = managed by NetworkManager (for SSH)
# 5. External WiFi = ignored by NetworkManager (for pentesting)
###############################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PenDonn WiFi Cleanup & Fix (MAC Address Based)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}ERROR: Please run as root (sudo)${NC}"
    exit 1
fi

echo -e "${YELLOW}This script will:${NC}"
echo "  1. Remove old WiFi services and scripts"
echo "  2. Remove udev rules"
echo "  3. Detect WiFi adapters by MAC address (stable!)"
echo "  4. Configure NetworkManager using MACs"
echo "  5. Onboard WiFi → managed (for SSH)"
echo "  6. External WiFi → ignored (for pentesting)"
echo ""
echo -e "${RED}WARNING: Will restart NetworkManager${NC}"
echo ""
read -p "Continue? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi
echo ""

# ============================================================================
# STEP 1: Remove old WiFi management
# ============================================================================
echo -e "${BLUE}[1/5] Removing old WiFi management...${NC}"

# Stop old services
systemctl stop pendonn-wifi-keeper.service 2>/dev/null || true
systemctl disable pendonn-wifi-keeper.service 2>/dev/null || true
systemctl stop pendonn-wifi-autofix.service 2>/dev/null || true
systemctl disable pendonn-wifi-autofix.service 2>/dev/null || true

# Remove files
rm -f /etc/systemd/system/pendonn-wifi-keeper.service
rm -f /etc/systemd/system/pendonn-wifi-autofix.service
rm -f /usr/local/bin/pendonn-wifi-keeper.sh
rm -f /usr/local/bin/pendonn-wifi-autofix.sh

# Remove udev rules
rm -f /etc/udev/rules.d/70-persistent-wifi.rules
rm -f /etc/udev/rules.d/72-usb-wifi.rules
rm -f /etc/udev/rules.d/72-wifi-powersave.rules

systemctl daemon-reload
udevadm control --reload-rules

echo -e "${GREEN}✓ Old WiFi management removed${NC}"
echo ""

# ============================================================================
# STEP 2: Detect WiFi adapters by MAC
# ============================================================================
echo -e "${BLUE}[2/5] Detecting WiFi adapters by MAC address...${NC}"

declare -A WIFI_MACS
declare -A WIFI_DRIVERS

while IFS= read -r iface; do
    if [ -n "$iface" ]; then
        MAC=$(cat "/sys/class/net/$iface/address" 2>/dev/null || echo "unknown")
        DRIVER=""
        if [ -d "/sys/class/net/$iface/device/driver" ]; then
            DRIVER=$(readlink "/sys/class/net/$iface/device/driver" 2>/dev/null | xargs basename)
        fi
        WIFI_MACS[$iface]=$MAC
        WIFI_DRIVERS[$iface]=$DRIVER
    fi
done < <(iw dev 2>/dev/null | grep Interface | awk '{print $2}')

ONBOARD_MAC=""
EXTERNAL_MACS=()

echo ""
for iface in "${!WIFI_MACS[@]}"; do
    MAC=${WIFI_MACS[$iface]}
    DRIVER=${WIFI_DRIVERS[$iface]}
    
    echo -e "  ${GREEN}$iface${NC}: $MAC ${DRIVER:+($DRIVER)}"
    
    # Onboard WiFi = Broadcom driver
    if [[ "$DRIVER" == "brcmfmac" ]] || [[ "$DRIVER" == *"bcm"* ]]; then
        ONBOARD_MAC=$MAC
        echo -e "    ${BLUE}→ Onboard WiFi (will manage connection)${NC}"
    else
        EXTERNAL_MACS+=("$MAC")
        echo -e "    ${YELLOW}→ External (for pentesting)${NC}"
    fi
done
echo ""

if [ -z "$ONBOARD_MAC" ]; then
    echo -e "${YELLOW}Warning: Could not identify onboard WiFi by driver${NC}"
    echo -e "${YELLOW}All adapters will be managed by NetworkManager${NC}"
fi

# ============================================================================
# STEP 3: Configure NetworkManager with MACs
# ============================================================================
echo -e "${BLUE}[3/5] Configuring NetworkManager (MAC based)...${NC}"

NMCONF="/etc/NetworkManager/NetworkManager.conf"

# Backup
if [ -f "$NMCONF" ]; then
    cp "$NMCONF" "${NMCONF}.backup-$(date +%Y%m%d_%H%M%S)"
fi

# Remove old interface-name based config
if [ -f "$NMCONF" ]; then
    sed -i '/unmanaged-devices=interface-name:wlan/d' "$NMCONF"
    sed -i '/unmanaged-devices=mac:/d' "$NMCONF"
fi

# Add MAC-based config for external adapters only
if [ ${#EXTERNAL_MACS[@]} -gt 0 ]; then
    # Build MAC list
    MAC_LIST=""
    for mac in "${EXTERNAL_MACS[@]}"; do
        if [ -z "$MAC_LIST" ]; then
            MAC_LIST="mac:$mac"
        else
            MAC_LIST="$MAC_LIST;mac:$mac"
        fi
    done
    
    # Add to NetworkManager
    if grep -q "^\[keyfile\]" "$NMCONF"; then
        sed -i "/^\[keyfile\]/a unmanaged-devices=$MAC_LIST" "$NMCONF"
    else
        echo "" >> "$NMCONF"
        echo "[keyfile]" >> "$NMCONF"
        echo "unmanaged-devices=$MAC_LIST" >> "$NMCONF"
    fi
    
    echo -e "${GREEN}✓ External adapters will be ignored by NetworkManager${NC}"
    echo -e "  ${BLUE}MACs: ${EXTERNAL_MACS[*]}${NC}"
else
    echo -e "${YELLOW}No external adapters detected${NC}"
fi

if [ -n "$ONBOARD_MAC" ]; then
    echo -e "${GREEN}✓ Onboard WiFi ($ONBOARD_MAC) will stay managed${NC}"
fi
echo ""

# ============================================================================
# STEP 4: Check rfkill
# ============================================================================
echo -e "${BLUE}[4/5] Checking rfkill...${NC}"

if command -v rfkill >/dev/null 2>&1; then
    rfkill unblock wifi
    echo -e "${GREEN}✓ WiFi unblocked${NC}"
else
    echo -e "${YELLOW}⚠ rfkill not available${NC}"
fi
echo ""

# ============================================================================
# STEP 5: Restart NetworkManager
# ============================================================================
echo -e "${BLUE}[5/5] Restarting NetworkManager...${NC}"

systemctl restart NetworkManager
sleep 5

if systemctl is-active --quiet NetworkManager; then
    echo -e "${GREEN}✓ NetworkManager restarted successfully${NC}"
else
    echo -e "${RED}✗ NetworkManager failed to start!${NC}"
    echo "Check logs: journalctl -u NetworkManager -n 50"
    exit 1
fi
echo ""

# ============================================================================
# Done
# ============================================================================
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}WiFi Cleanup Complete (MAC-Based Configuration)${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${BLUE}What changed:${NC}"
echo "  • Old services and scripts removed"
echo "  • udev rules removed"
echo "  • Using MAC addresses (stable, never change)"
if [ -n "$ONBOARD_MAC" ]; then
    echo "  • Onboard WiFi ($ONBOARD_MAC) managed by NetworkManager"
fi
if [ ${#EXTERNAL_MACS[@]} -gt 0 ]; then
    echo "  • External adapters (${EXTERNAL_MACS[*]}) ignored"
fi
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo "1. Check WiFi status:"
echo "   ${BLUE}nmcli device status${NC}"
echo ""
echo "2. If disconnected, reconnect:"
echo "   ${BLUE}nmcli device wifi connect 'YourSSID' password 'YourPassword'${NC}"
echo ""
echo "3. REBOOT to test:"
echo "   ${BLUE}sudo reboot${NC}"
echo ""
echo "4. After reboot, verify:"
echo "   ${BLUE}nmcli device status${NC}"
echo "   ${BLUE}ping -c 5 google.com${NC}"
echo ""
echo -e "${GREEN}MAC addresses = Stable and reliable!${NC}"
echo ""
