#!/bin/bash

###############################################################################
# PenDonn - WiFi Recovery Tool
# Fixes WiFi connectivity after driver installation reboot
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║              WiFi Connectivity Recovery Tool                   ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}[ERROR]${NC} Please run as root (use sudo)"
    exit 1
fi

echo -e "${YELLOW}This script fixes WiFi connectivity after driver installation${NC}"
echo -e "${YELLOW}It prevents external drivers from managing built-in WiFi${NC}"
echo ""

# Step 1: Identify interfaces
echo -e "${BLUE}[1/6] Identifying WiFi interfaces...${NC}"
INTERFACES=($(ip link show | grep -oP '(?<=: )[^:]+' | grep '^wlan'))
echo "Found interfaces: ${INTERFACES[@]}"

if [ ${#INTERFACES[@]} -eq 0 ]; then
    echo -e "${RED}No WiFi interfaces found! This is a bigger problem.${NC}"
    echo -e "${YELLOW}Possible causes:${NC}"
    echo "  1. Drivers not loaded (run: lsmod | grep 8812)"
    echo "  2. USB devices not detected (run: lsusb)"
    echo "  3. Hardware failure"
    echo ""
    echo -e "${BLUE}Try manual driver loading:${NC}"
    echo "  sudo modprobe 8812au"
    echo "  sudo modprobe brcmfmac  # Built-in WiFi driver"
    exit 1
fi

# Step 2: Bring up all interfaces
echo ""
echo -e "${BLUE}[2/6] Bringing up all interfaces...${NC}"
for iface in "${INTERFACES[@]}"; do
    echo "  Bringing up $iface..."
    ip link set "$iface" up 2>/dev/null || echo "    Warning: Could not bring up $iface"
done
sleep 2

# Step 3: Identify which interface is built-in
echo ""
echo -e "${BLUE}[3/6] Identifying built-in WiFi...${NC}"
BUILTIN_IFACE=""
BUILTIN_MAC=""

for iface in "${INTERFACES[@]}"; do
    # Check if interface is USB (external) or built-in
    IFACE_PATH=$(readlink -f "/sys/class/net/$iface/device")
    
    if echo "$IFACE_PATH" | grep -q "usb"; then
        echo "  $iface: External USB adapter"
    else
        echo "  $iface: Built-in WiFi (non-USB)"
        BUILTIN_IFACE="$iface"
        BUILTIN_MAC=$(cat "/sys/class/net/$iface/address" 2>/dev/null)
        echo "    MAC: $BUILTIN_MAC"
    fi
done

if [ -z "$BUILTIN_IFACE" ]; then
    echo -e "${YELLOW}Could not identify built-in WiFi interface${NC}"
    echo -e "${YELLOW}Assuming wlan0 is built-in...${NC}"
    BUILTIN_IFACE="wlan0"
    if [ -e "/sys/class/net/wlan0/address" ]; then
        BUILTIN_MAC=$(cat "/sys/class/net/wlan0/address")
    fi
fi

# Step 4: Create udev rules for persistent naming
echo ""
echo -e "${BLUE}[4/6] Creating udev rules...${NC}"
if [ -n "$BUILTIN_MAC" ]; then
    cat > /etc/udev/rules.d/70-persistent-wifi.rules << EOF
# PenDonn - Persistent WiFi Interface Naming
# Built-in WiFi is always wlan0 (management interface)
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="$BUILTIN_MAC", NAME="wlan0"

# External USB WiFi adapters become wlan1 and wlan2
# These will be used for pentesting (monitor/attack interfaces)
EOF
    echo -e "${GREEN}✓ udev rules created for $BUILTIN_IFACE ($BUILTIN_MAC)${NC}"
else
    echo -e "${YELLOW}⚠ Could not determine MAC address, skipping udev rules${NC}"
fi

# Step 5: Configure NetworkManager
echo ""
echo -e "${BLUE}[5/6] Configuring network management...${NC}"

if systemctl is-active --quiet NetworkManager; then
    echo "Using NetworkManager..."
    
    if [ -f /etc/NetworkManager/NetworkManager.conf ]; then
        cp /etc/NetworkManager/NetworkManager.conf /etc/NetworkManager/NetworkManager.conf.backup 2>/dev/null
        
        if grep -q "^\[keyfile\]" /etc/NetworkManager/NetworkManager.conf; then
            if ! grep -q "unmanaged-devices" /etc/NetworkManager/NetworkManager.conf; then
                sed -i '/^\[keyfile\]/a unmanaged-devices=interface-name:wlan1;interface-name:wlan2' /etc/NetworkManager/NetworkManager.conf
                echo -e "${GREEN}✓ NetworkManager configured to ignore wlan1/wlan2${NC}"
            else
                echo -e "${GREEN}✓ NetworkManager already configured${NC}"
            fi
        else
            echo "" >> /etc/NetworkManager/NetworkManager.conf
            echo "[keyfile]" >> /etc/NetworkManager/NetworkManager.conf
            echo "unmanaged-devices=interface-name:wlan1;interface-name:wlan2" >> /etc/NetworkManager/NetworkManager.conf
            echo -e "${GREEN}✓ NetworkManager configured to ignore wlan1/wlan2${NC}"
        fi
        
        systemctl restart NetworkManager
        echo "NetworkManager restarted"
    fi
    
elif [ -f /etc/dhcpcd.conf ]; then
    echo "Using dhcpcd..."
    
    if ! grep -q "denyinterfaces wlan1 wlan2" /etc/dhcpcd.conf; then
        cp /etc/dhcpcd.conf /etc/dhcpcd.conf.backup 2>/dev/null
        echo "" >> /etc/dhcpcd.conf
        echo "# PenDonn: Don't manage pentesting interfaces" >> /etc/dhcpcd.conf
        echo "denyinterfaces wlan1 wlan2" >> /etc/dhcpcd.conf
        echo -e "${GREEN}✓ dhcpcd configured to ignore wlan1/wlan2${NC}"
        
        systemctl restart dhcpcd 2>/dev/null || true
        echo "dhcpcd restarted"
    else
        echo -e "${GREEN}✓ dhcpcd already configured${NC}"
    fi
fi

# Step 6: Restart WiFi on built-in interface
echo ""
echo -e "${BLUE}[6/6] Reconnecting built-in WiFi...${NC}"

if command -v nmcli &> /dev/null; then
    echo "Using nmcli to reconnect..."
    nmcli device set "$BUILTIN_IFACE" managed yes
    nmcli radio wifi on
    sleep 3
    
    # Show available networks
    echo ""
    echo -e "${YELLOW}Available WiFi networks:${NC}"
    nmcli device wifi list | head -10
    
    echo ""
    echo -e "${BLUE}To connect to your network:${NC}"
    echo "  nmcli device wifi connect <SSID> password <PASSWORD>"
    
elif command -v wpa_supplicant &> /dev/null; then
    echo "Using wpa_supplicant..."
    echo ""
    echo -e "${BLUE}Manual connection required:${NC}"
    echo "  1. Edit: sudo nano /etc/wpa_supplicant/wpa_supplicant.conf"
    echo "  2. Add your network:"
    echo "     network={"
    echo "       ssid=\"YourNetworkName\""
    echo "       psk=\"YourPassword\""
    echo "     }"
    echo "  3. Restart: sudo systemctl restart wpa_supplicant"
else
    echo -e "${YELLOW}Using raspi-config for connection${NC}"
    echo "Run: sudo raspi-config"
    echo "Navigate to: System Options → Wireless LAN"
fi

# Summary
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}WiFi Recovery Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}Configuration applied:${NC}"
echo "  ✓ Built-in WiFi: $BUILTIN_IFACE (MAC: $BUILTIN_MAC)"
echo "  ✓ Network manager configured to ignore wlan1/wlan2"
echo "  ✓ udev rules created for persistent naming"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  1. Connect to your WiFi network (see command above)"
echo "  2. Verify connection: ping -c 3 8.8.8.8"
echo "  3. Check interfaces: ip addr show"
echo ""
echo -e "${YELLOW}After connecting, your setup will be:${NC}"
echo "  • $BUILTIN_IFACE (wlan0) = Management WiFi (stays connected)"
echo "  • wlan1 = Monitor interface (scans networks)"
echo "  • wlan2 = Attack interface (captures handshakes)"
echo ""
