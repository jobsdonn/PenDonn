#!/bin/bash

###############################################################################
# WiFi Adapter Detection Script
# Identifies connected WiFi adapters and their capabilities
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║           WiFi Adapter Detection & Capability Test            ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# 1. List all USB WiFi devices
echo -e "${BLUE}[1] USB WiFi Adapters Detected:${NC}"
echo -e "${YELLOW}────────────────────────────────────────────────────────────────${NC}"
USB_WIFI=$(lsusb | grep -iE "wireless|wifi|802\.11|wlan|network|realtek|ralink|atheros|mediatek|broadcom|intel|qualcomm|tp-link|alfa")

if [ -z "$USB_WIFI" ]; then
    echo -e "${RED}No USB WiFi adapters detected${NC}"
else
    echo "$USB_WIFI" | while read line; do
        # Extract vendor and product IDs
        VID_PID=$(echo "$line" | grep -oP '(?<=ID )[0-9a-f]{4}:[0-9a-f]{4}')
        
        # Identify common adapters
        case "$VID_PID" in
            "0bda:8812"|"0bda:881a"|"0bda:a811")
                echo -e "${GREEN}✓ $line${NC}"
                echo -e "  ${BLUE}→ Alfa AWUS036ACH or similar (RTL8812AU) - EXCELLENT${NC}"
                ;;
            "0bda:8179")
                echo -e "${GREEN}✓ $line${NC}"
                echo -e "  ${BLUE}→ TP-Link TL-WN722N v2/v3 (RTL8188EUS) - GOOD${NC}"
                ;;
            "0bda:8813")
                echo -e "${GREEN}✓ $line${NC}"
                echo -e "  ${BLUE}→ Alfa AWUS1900 (RTL8814AU) - EXCELLENT${NC}"
                ;;
            "0bda:b82c")
                echo -e "${GREEN}✓ $line${NC}"
                echo -e "  ${BLUE}→ RTL8822BU adapter - GOOD${NC}"
                ;;
            "0bda:c811"|"0bda:8811")
                echo -e "${GREEN}✓ $line${NC}"
                echo -e "  ${BLUE}→ RTL8811CU/RTL8821CU adapter - GOOD${NC}"
                ;;
            "0e8d:7612")
                echo -e "${GREEN}✓ $line${NC}"
                echo -e "  ${BLUE}→ Alfa AWUS036ACM (MT7612U) - EXCELLENT${NC}"
                ;;
            "148f:5370")
                echo -e "${GREEN}✓ $line${NC}"
                echo -e "  ${BLUE}→ TP-Link TL-WN722N v1 or RT5370 - EXCELLENT${NC}"
                ;;
            "0cf3:9271")
                echo -e "${GREEN}✓ $line${NC}"
                echo -e "  ${BLUE}→ Alfa AWUS036NHA (AR9271) - EXCELLENT${NC}"
                ;;
            *)
                echo -e "${YELLOW}? $line${NC}"
                echo -e "  ${YELLOW}→ Unknown adapter - may need driver${NC}"
                ;;
        esac
        echo ""
    done
fi
echo ""

# 2. List all network interfaces
echo -e "${BLUE}[2] Network Interfaces:${NC}"
echo -e "${YELLOW}────────────────────────────────────────────────────────────────${NC}"
ip link show | grep -E "^[0-9]+: " | while read line; do
    IFACE=$(echo "$line" | awk -F': ' '{print $2}')
    if [[ $IFACE == wlan* ]] || [[ $IFACE == wl* ]]; then
        echo -e "${GREEN}✓ $IFACE${NC}"
        
        # Check if it's up
        if ip link show "$IFACE" | grep -q "state UP"; then
            echo -e "  Status: ${GREEN}UP${NC}"
        else
            echo -e "  Status: ${YELLOW}DOWN${NC}"
        fi
        
        # Get driver info
        if [ -d "/sys/class/net/$IFACE/device/driver" ]; then
            DRIVER=$(readlink "/sys/class/net/$IFACE/device/driver" | xargs basename)
            echo -e "  Driver: ${BLUE}$DRIVER${NC}"
        fi
        echo ""
    fi
done
echo ""

# 3. Check monitor mode capability
echo -e "${BLUE}[3] Monitor Mode Capability:${NC}"
echo -e "${YELLOW}────────────────────────────────────────────────────────────────${NC}"

MONITOR_CAPABLE=0
for IFACE in $(iw dev | grep Interface | awk '{print $2}'); do
    if iw "$IFACE" info | grep -q "type managed"; then
        # Try to check supported modes
        if iw phy "$(iw dev "$IFACE" info | grep wiphy | awk '{print $2}')" info 2>/dev/null | grep -q "monitor"; then
            echo -e "${GREEN}✓ $IFACE - Monitor mode supported${NC}"
            ((MONITOR_CAPABLE++))
        else
            echo -e "${YELLOW}? $IFACE - Monitor mode unknown${NC}"
        fi
    fi
done

if [ $MONITOR_CAPABLE -eq 0 ]; then
    echo -e "${RED}No interfaces confirmed to support monitor mode${NC}"
    echo -e "${YELLOW}This might mean:${NC}"
    echo -e "  1. Drivers not installed"
    echo -e "  2. Adapters don't support monitor mode"
    echo -e "  3. Need to run: ${BLUE}sudo scripts/install-wifi-drivers.sh${NC}"
fi
echo ""

# 4. Check loaded kernel modules
echo -e "${BLUE}[4] Loaded WiFi Drivers:${NC}"
echo -e "${YELLOW}────────────────────────────────────────────────────────────────${NC}"
lsmod | grep -E "8188eu|8812au|8814au|88x2bu|8821cu|rt2800usb|rt5370|ath9k|mt76" | awk '{print $1}' | while read module; do
    echo -e "${GREEN}✓ $module loaded${NC}"
done

if ! lsmod | grep -qE "8188eu|8812au|8814au|88x2bu|8821cu|rt2800usb|rt5370|ath9k|mt76"; then
    echo -e "${YELLOW}No common pentesting WiFi drivers loaded${NC}"
    echo -e "${YELLOW}Run: ${BLUE}sudo scripts/install-wifi-drivers.sh${NC}"
fi
echo ""

# 5. Recommendations
echo -e "${BLUE}[5] Recommendations:${NC}"
echo -e "${YELLOW}════════════════════════════════════════════════════════════════${NC}"

ADAPTER_COUNT=$(iw dev 2>/dev/null | grep -c "Interface wlan" || echo "0")

if [ "$ADAPTER_COUNT" -lt 3 ]; then
    echo -e "${RED}✗ Only $ADAPTER_COUNT WiFi adapter(s) detected${NC}"
    echo -e "${YELLOW}  You need 3 adapters for PenDonn:${NC}"
    echo -e "  1. Onboard WiFi (management - keeps SSH working)"
    echo -e "  2. External adapter #1 (monitor mode - scanning)"
    echo -e "  3. External adapter #2 (attack mode - deauth/injection)"
    echo ""
    echo -e "${YELLOW}  Recommended adapters to buy:${NC}"
    echo -e "  ${GREEN}Best:${NC} Alfa AWUS036ACH (2.4GHz + 5GHz, excellent range)"
    echo -e "  ${GREEN}Good:${NC} Alfa AWUS036NHA (2.4GHz only, very reliable)"
    echo -e "  ${GREEN}Budget:${NC} TP-Link TL-WN722N v1 (NOT v2/v3)"
else
    echo -e "${GREEN}✓ $ADAPTER_COUNT WiFi adapters detected - sufficient for PenDonn${NC}"
fi
echo ""

if [ $MONITOR_CAPABLE -lt 2 ]; then
    echo -e "${YELLOW}! Install drivers for your external adapters:${NC}"
    echo -e "  ${BLUE}sudo scripts/install-wifi-drivers.sh${NC}"
    echo -e "  ${BLUE}sudo reboot${NC}"
    echo ""
fi

echo -e "${BLUE}Next steps:${NC}"
echo "1. If drivers missing: ${BLUE}sudo scripts/install-wifi-drivers.sh${NC}"
echo "2. Reboot after installing drivers: ${BLUE}sudo reboot${NC}"
echo "3. Run this script again to verify"
echo "4. Test monitor mode: ${BLUE}sudo airmon-ng start wlan1${NC}"
echo "5. Configure PenDonn: ${BLUE}sudo nano /opt/pendonn/config/config.json${NC}"
echo ""
echo -e "${YELLOW}════════════════════════════════════════════════════════════════${NC}"
echo ""
