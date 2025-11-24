#!/bin/bash

###############################################################################
# PenDonn - WiFi Interface Fixer
# Correctly maps built-in WiFi to wlan0 and external adapters to wlan1/wlan2
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║              WiFi Interface Fixer for PenDonn                 ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "${YELLOW}This will fix WiFi interface naming so:${NC}"
echo -e "  • wlan0 = Built-in WiFi (management)"
echo -e "  • wlan1 = External adapter 1 (monitor)"
echo -e "  • wlan2 = External adapter 2 (attack)"
echo ""

# Detect interfaces
echo -e "${BLUE}[1] Detecting current interfaces...${NC}"
echo ""

for iface in /sys/class/net/wlan*; do
    if [ -e "$iface" ]; then
        IFACE_NAME=$(basename "$iface")
        DRIVER=$(readlink "$iface/device/driver" 2>/dev/null | xargs basename 2>/dev/null || echo "unknown")
        MAC=$(cat "$iface/address" 2>/dev/null)
        
        echo -e "${GREEN}$IFACE_NAME${NC}"
        echo -e "  MAC: $MAC"
        echo -e "  Driver: $DRIVER"
        
        # Identify built-in vs external
        if [[ "$DRIVER" == "brcmfmac" ]] || [[ "$DRIVER" == "brcmutil" ]]; then
            echo -e "  Type: ${GREEN}Built-in WiFi (Broadcom)${NC}"
            BUILTIN_MAC="$MAC"
            BUILTIN_IFACE="$IFACE_NAME"
        elif [[ "$DRIVER" == "rtl88XXau" ]] || [[ "$DRIVER" =~ rtl.*au ]]; then
            echo -e "  Type: ${YELLOW}External USB (Realtek)${NC}"
            EXTERNAL_MACS+=("$MAC")
        else
            echo -e "  Type: ${YELLOW}Unknown${NC}"
        fi
        echo ""
    fi
done

# Check if we found the built-in WiFi
if [ -z "$BUILTIN_MAC" ]; then
    echo -e "${RED}ERROR: Could not identify built-in WiFi!${NC}"
    echo -e "${YELLOW}Looking for brcmfmac driver but none found.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Found built-in WiFi:${NC}"
echo -e "  Interface: $BUILTIN_IFACE"
echo -e "  MAC: $BUILTIN_MAC"
echo ""

# Backup existing udev rules
if [ -f /etc/udev/rules.d/70-persistent-wifi.rules ]; then
    echo -e "${BLUE}[2] Backing up old udev rules...${NC}"
    cp /etc/udev/rules.d/70-persistent-wifi.rules /etc/udev/rules.d/70-persistent-wifi.rules.backup
    echo -e "${GREEN}✓ Backup saved${NC}"
    echo ""
fi

# Create corrected udev rules
echo -e "${BLUE}[3] Creating corrected udev rules...${NC}"

cat > /etc/udev/rules.d/70-persistent-wifi.rules << EOF
# PenDonn - Persistent WiFi Interface Naming (CORRECTED)
# Built-in WiFi MUST be wlan0 for management/SSH connection

# Built-in Broadcom WiFi is ALWAYS wlan0 (management interface)
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="$BUILTIN_MAC", NAME="wlan0"

# External USB WiFi adapters become wlan1 and wlan2 (pentesting)
# They are numbered by USB port order
SUBSYSTEM=="net", ACTION=="add", DRIVERS=="rtl88*", ENV{ID_USB_INTERFACE_NUM}=="00", ATTR{address}!="$BUILTIN_MAC", NAME="wlan1"
SUBSYSTEM=="net", ACTION=="add", DRIVERS=="rtl88*", ENV{ID_USB_INTERFACE_NUM}=="00", ATTR{address}!="$BUILTIN_MAC", NAME="wlan2"
EOF

echo -e "${GREEN}✓ udev rules created${NC}"
echo ""

# Update NetworkManager configuration
echo -e "${BLUE}[4] Updating NetworkManager configuration...${NC}"

if systemctl is-active --quiet NetworkManager; then
    if [ -f /etc/NetworkManager/NetworkManager.conf ]; then
        cp /etc/NetworkManager/NetworkManager.conf /etc/NetworkManager/NetworkManager.conf.backup.$(date +%Y%m%d_%H%M%S)
        
        # Remove old unmanaged-devices lines
        sed -i '/unmanaged-devices/d' /etc/NetworkManager/NetworkManager.conf
        
        # Add correct configuration
        if grep -q "^\[keyfile\]" /etc/NetworkManager/NetworkManager.conf; then
            sed -i '/^\[keyfile\]/a unmanaged-devices=interface-name:wlan1;interface-name:wlan2' /etc/NetworkManager/NetworkManager.conf
        else
            echo "" >> /etc/NetworkManager/NetworkManager.conf
            echo "[keyfile]" >> /etc/NetworkManager/NetworkManager.conf
            echo "unmanaged-devices=interface-name:wlan1;interface-name:wlan2" >> /etc/NetworkManager/NetworkManager.conf
        fi
        echo -e "${GREEN}✓ NetworkManager configured to ignore wlan1/wlan2${NC}"
    fi
fi

if [ -f /etc/dhcpcd.conf ]; then
    if ! grep -q "denyinterfaces wlan1 wlan2" /etc/dhcpcd.conf; then
        cp /etc/dhcpcd.conf /etc/dhcpcd.conf.backup.$(date +%Y%m%d_%H%M%S)
        echo "" >> /etc/dhcpcd.conf
        echo "# PenDonn: Don't manage pentesting interfaces" >> /etc/dhcpcd.conf
        echo "denyinterfaces wlan1 wlan2" >> /etc/dhcpcd.conf
        echo -e "${GREEN}✓ dhcpcd configured to ignore wlan1/wlan2${NC}"
    fi
fi

echo ""

# Reload udev rules
echo -e "${BLUE}[5] Reloading udev rules...${NC}"
udevadm control --reload-rules
udevadm trigger --subsystem-match=net
echo -e "${GREEN}✓ udev rules reloaded${NC}"
echo ""

# Final instructions
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}WiFi Interface Fix Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}IMPORTANT: You must reboot for changes to take effect${NC}"
echo ""
echo -e "${BLUE}After reboot, interfaces will be:${NC}"
echo -e "  • ${GREEN}wlan0${NC} = Built-in WiFi (MAC: $BUILTIN_MAC) - stays connected"
echo -e "  • ${YELLOW}wlan1${NC} = External adapter 1 (monitor interface)"
echo -e "  • ${YELLOW}wlan2${NC} = External adapter 2 (attack interface)"
echo ""
echo -e "${RED}⚠️  REBOOT NOW:${NC}"
echo -e "  ${GREEN}sudo reboot${NC}"
echo ""
