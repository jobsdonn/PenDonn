#!/bin/bash

###############################################################################
# PenDonn Configuration Wizard
# Interactive configuration tool for PenDonn settings
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

INSTALL_DIR="/opt/pendonn"
CONFIG_FILE="$INSTALL_DIR/config/config.json"

echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║              PenDonn Configuration Wizard                      ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}[ERROR]${NC} Please run as root (use sudo)"
    exit 1
fi

# Check if config exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}[ERROR]${NC} Configuration file not found: $CONFIG_FILE"
    echo "Please run installation first: sudo ./install.sh"
    exit 1
fi

# Backup existing config
cp "$CONFIG_FILE" "$CONFIG_FILE.backup.$(date +%Y%m%d_%H%M%S)"
echo -e "${GREEN}[✓]${NC} Backed up existing configuration"
echo ""

# Detect WiFi interfaces
echo -e "${YELLOW}Detecting WiFi interfaces...${NC}"
INTERFACES=($(iw dev 2>/dev/null | grep Interface | awk '{print $2}'))
INTERFACE_COUNT=${#INTERFACES[@]}

echo -e "${BLUE}Found $INTERFACE_COUNT interface(s):${NC}"
for i in "${!INTERFACES[@]}"; do
    DRIVER=""
    if [ -d "/sys/class/net/${INTERFACES[$i]}/device/driver" ]; then
        DRIVER=$(readlink "/sys/class/net/${INTERFACES[$i]}/device/driver" | xargs basename)
    fi
    echo "  $((i+1)). ${INTERFACES[$i]} ${DRIVER:+($DRIVER)}"
done
echo ""

if [ "$INTERFACE_COUNT" -lt 3 ]; then
    echo -e "${YELLOW}[!]${NC} Warning: Only $INTERFACE_COUNT interface(s) detected"
    echo "    Recommended: 1 onboard + 2 external WiFi adapters"
    echo ""
    read -p "Continue anyway? (yes/no): " CONTINUE
    if [ "$CONTINUE" != "yes" ]; then
        echo "Configuration cancelled"
        exit 0
    fi
fi

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# 1. WiFi Interface Configuration
echo -e "${BLUE}[1/6] WiFi Interface Configuration${NC}"
echo ""
echo -e "${YELLOW}You need to assign 3 interfaces:${NC}"
echo "  1. ${GREEN}Management${NC} - Keeps SSH/network working (usually wlan0)"
echo "  2. ${GREEN}Monitor${NC} - Scans for networks (external adapter)"
echo "  3. ${GREEN}Attack${NC} - Captures handshakes (external adapter)"
echo ""

# Get current settings
CURRENT_MGMT=$(grep -A 5 '"wifi"' "$CONFIG_FILE" | grep '"management_interface"' | cut -d'"' -f4)
CURRENT_MON=$(grep -A 5 '"wifi"' "$CONFIG_FILE" | grep '"monitor_interface"' | cut -d'"' -f4)
CURRENT_ATK=$(grep -A 5 '"wifi"' "$CONFIG_FILE" | grep '"attack_interface"' | cut -d'"' -f4)

echo -e "${YELLOW}Current configuration:${NC}"
echo "  Management: $CURRENT_MGMT"
echo "  Monitor:    $CURRENT_MON"
echo "  Attack:     $CURRENT_ATK"
echo ""

read -p "Update WiFi interfaces? (yes/no) [yes]: " UPDATE_WIFI
UPDATE_WIFI=${UPDATE_WIFI:-yes}

if [ "$UPDATE_WIFI" = "yes" ]; then
    # Management interface
    echo ""
    echo -e "${GREEN}Select MANAGEMENT interface (keeps SSH working):${NC}"
    for i in "${!INTERFACES[@]}"; do
        echo "  $((i+1)). ${INTERFACES[$i]}"
    done
    read -p "Choice (1-$INTERFACE_COUNT) [$CURRENT_MGMT]: " MGMT_CHOICE
    if [ -n "$MGMT_CHOICE" ]; then
        MGMT_IFACE=${INTERFACES[$((MGMT_CHOICE-1))]}
    else
        MGMT_IFACE=$CURRENT_MGMT
    fi
    
    # Monitor interface
    echo ""
    echo -e "${GREEN}Select MONITOR interface (scans networks):${NC}"
    for i in "${!INTERFACES[@]}"; do
        if [ "${INTERFACES[$i]}" != "$MGMT_IFACE" ]; then
            echo "  $((i+1)). ${INTERFACES[$i]}"
        fi
    done
    read -p "Choice (1-$INTERFACE_COUNT) [$CURRENT_MON]: " MON_CHOICE
    if [ -n "$MON_CHOICE" ]; then
        MON_IFACE=${INTERFACES[$((MON_CHOICE-1))]}
    else
        MON_IFACE=$CURRENT_MON
    fi
    
    # Attack interface
    echo ""
    echo -e "${GREEN}Select ATTACK interface (captures handshakes):${NC}"
    for i in "${!INTERFACES[@]}"; do
        if [ "${INTERFACES[$i]}" != "$MGMT_IFACE" ] && [ "${INTERFACES[$i]}" != "$MON_IFACE" ]; then
            echo "  $((i+1)). ${INTERFACES[$i]}"
        fi
    done
    read -p "Choice (1-$INTERFACE_COUNT) [$CURRENT_ATK]: " ATK_CHOICE
    if [ -n "$ATK_CHOICE" ]; then
        ATK_IFACE=${INTERFACES[$((ATK_CHOICE-1))]}
    else
        ATK_IFACE=$CURRENT_ATK
    fi
    
    # Validate no duplicates
    if [ "$MGMT_IFACE" = "$MON_IFACE" ] || [ "$MGMT_IFACE" = "$ATK_IFACE" ] || [ "$MON_IFACE" = "$ATK_IFACE" ]; then
        echo -e "${RED}[ERROR]${NC} Each interface must be unique!"
        exit 1
    fi
    
    echo ""
    echo -e "${GREEN}✓ WiFi interfaces configured:${NC}"
    echo "  Management: $MGMT_IFACE"
    echo "  Monitor:    $MON_IFACE"
    echo "  Attack:     $ATK_IFACE"
    
    # Update config
    sed -i "s/\"management_interface\": \".*\"/\"management_interface\": \"$MGMT_IFACE\"/g" "$CONFIG_FILE"
    sed -i "s/\"monitor_interface\": \".*\"/\"monitor_interface\": \"$MON_IFACE\"/g" "$CONFIG_FILE"
    sed -i "s/\"attack_interface\": \".*\"/\"attack_interface\": \"$ATK_IFACE\"/g" "$CONFIG_FILE"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# 2. Whitelist Configuration
echo -e "${BLUE}[2/6] Whitelist Configuration${NC}"
echo ""
echo -e "${YELLOW}Add your home/work network SSIDs to avoid scanning them${NC}"
echo ""

CURRENT_WHITELIST=$(grep -A 2 '"whitelist"' "$CONFIG_FILE" | grep '"ssids"' | cut -d'[' -f2 | cut -d']' -f1)
echo -e "${YELLOW}Current whitelist:${NC} $CURRENT_WHITELIST"
echo ""

read -p "Update whitelist? (yes/no) [yes]: " UPDATE_WHITELIST
UPDATE_WHITELIST=${UPDATE_WHITELIST:-yes}

if [ "$UPDATE_WHITELIST" = "yes" ]; then
    echo ""
    echo "Enter SSIDs to whitelist (one per line, empty line to finish):"
    WHITELIST_SSIDS=""
    while true; do
        read -p "  SSID: " SSID
        if [ -z "$SSID" ]; then
            break
        fi
        if [ -z "$WHITELIST_SSIDS" ]; then
            WHITELIST_SSIDS="\"$SSID\""
        else
            WHITELIST_SSIDS="$WHITELIST_SSIDS, \"$SSID\""
        fi
        echo -e "    ${GREEN}✓ Added: $SSID${NC}"
    done
    
    sed -i "s/\"ssids\": \[.*\]/\"ssids\": [$WHITELIST_SSIDS]/g" "$CONFIG_FILE"
    
    if [ -n "$WHITELIST_SSIDS" ]; then
        echo -e "${GREEN}✓ Whitelist updated${NC}"
    else
        echo -e "${YELLOW}! No SSIDs in whitelist - will scan ALL networks${NC}"
    fi
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# 3. Web Interface Configuration
echo -e "${BLUE}[3/6] Web Interface Configuration${NC}"
echo ""

CURRENT_PORT=$(grep -A 3 '"web"' "$CONFIG_FILE" | grep '"port"' | grep -oP '\d+')
echo -e "${YELLOW}Current web port:${NC} $CURRENT_PORT"

read -p "Change web interface port? (yes/no) [no]: " CHANGE_PORT
if [ "$CHANGE_PORT" = "yes" ]; then
    read -p "Enter new port [8080]: " NEW_PORT
    NEW_PORT=${NEW_PORT:-8080}
    sed -i "s/\"port\": $CURRENT_PORT/\"port\": $NEW_PORT/g" "$CONFIG_FILE"
    echo -e "${GREEN}✓ Web port set to $NEW_PORT${NC}"
fi

echo ""
read -p "Generate new secret key? (yes/no) [no]: " NEW_KEY
if [ "$NEW_KEY" = "yes" ]; then
    SECRET_KEY=$(openssl rand -hex 32)
    sed -i "s/\"secret_key\": \".*\"/\"secret_key\": \"$SECRET_KEY\"/g" "$CONFIG_FILE"
    echo -e "${GREEN}✓ New secret key generated${NC}"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# 4. Cracking Configuration
echo -e "${BLUE}[4/6] Password Cracking Configuration${NC}"
echo ""

CURRENT_AUTO_CRACK=$(grep -A 5 '"cracking"' "$CONFIG_FILE" | grep '"auto_start_cracking"' | grep -o 'true\|false')
echo -e "${YELLOW}Auto-start cracking:${NC} $CURRENT_AUTO_CRACK"

read -p "Enable auto-cracking after handshake capture? (yes/no) [$CURRENT_AUTO_CRACK]: " AUTO_CRACK
AUTO_CRACK=${AUTO_CRACK:-$CURRENT_AUTO_CRACK}

if [ "$AUTO_CRACK" = "yes" ] || [ "$AUTO_CRACK" = "true" ]; then
    sed -i 's/"auto_start_cracking": false/"auto_start_cracking": true/g' "$CONFIG_FILE"
    echo -e "${GREEN}✓ Auto-cracking enabled${NC}"
else
    sed -i 's/"auto_start_cracking": true/"auto_start_cracking": false/g' "$CONFIG_FILE"
    echo -e "${YELLOW}! Auto-cracking disabled${NC}"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# 5. Network Enumeration Configuration
echo -e "${BLUE}[5/6] Network Enumeration Configuration${NC}"
echo ""

CURRENT_AUTO_SCAN=$(grep -A 3 '"enumeration"' "$CONFIG_FILE" | grep '"auto_scan_on_crack"' | grep -o 'true\|false')
echo -e "${YELLOW}Auto-scan after password crack:${NC} $CURRENT_AUTO_SCAN"

read -p "Enable auto-scan after successful crack? (yes/no) [$CURRENT_AUTO_SCAN]: " AUTO_SCAN
AUTO_SCAN=${AUTO_SCAN:-$CURRENT_AUTO_SCAN}

if [ "$AUTO_SCAN" = "yes" ] || [ "$AUTO_SCAN" = "true" ]; then
    sed -i 's/"auto_scan_on_crack": false/"auto_scan_on_crack": true/g' "$CONFIG_FILE"
    echo -e "${GREEN}✓ Auto-scan enabled${NC}"
else
    sed -i 's/"auto_scan_on_crack": true/"auto_scan_on_crack": false/g' "$CONFIG_FILE"
    echo -e "${YELLOW}! Auto-scan disabled${NC}"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# 6. Display Configuration
echo -e "${BLUE}[6/6] Display Configuration${NC}"
echo ""

CURRENT_DISPLAY=$(grep -A 4 '"display"' "$CONFIG_FILE" | grep '"enabled"' | grep -o 'true\|false' | head -1)
echo -e "${YELLOW}Hardware display:${NC} $CURRENT_DISPLAY"

read -p "Do you have a Waveshare display? (yes/no) [$CURRENT_DISPLAY]: " HAS_DISPLAY
HAS_DISPLAY=${HAS_DISPLAY:-$CURRENT_DISPLAY}

if [ "$HAS_DISPLAY" = "yes" ] || [ "$HAS_DISPLAY" = "true" ]; then
    # Find and replace only the display enabled setting
    sed -i '/"display"/,/}/s/"enabled": false/"enabled": true/' "$CONFIG_FILE"
    echo -e "${GREEN}✓ Display enabled${NC}"
else
    sed -i '/"display"/,/}/s/"enabled": true/"enabled": false/' "$CONFIG_FILE"
    echo -e "${YELLOW}! Display disabled (headless mode)${NC}"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

# Configuration Summary
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║          Configuration completed successfully!                ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BLUE}Configuration Summary:${NC}"
echo ""
if [ -n "$MGMT_IFACE" ]; then
    echo "  WiFi Interfaces:"
    echo "    Management: $MGMT_IFACE (keeps SSH working)"
    echo "    Monitor:    $MON_IFACE (scans networks)"
    echo "    Attack:     $ATK_IFACE (captures handshakes)"
fi
echo ""
echo "  Web Interface: http://$(hostname -I | awk '{print $1}'):${NEW_PORT:-$CURRENT_PORT}"
echo "  Auto-cracking: ${AUTO_CRACK:-$CURRENT_AUTO_CRACK}"
echo "  Auto-scanning: ${AUTO_SCAN:-$CURRENT_AUTO_SCAN}"
echo "  Display: ${HAS_DISPLAY:-$CURRENT_DISPLAY}"
echo ""

echo -e "${YELLOW}Config file:${NC} $CONFIG_FILE"
echo -e "${YELLOW}Backup saved:${NC} $CONFIG_FILE.backup.*"
echo ""

echo -e "${BLUE}Next Steps:${NC}"
echo "1. Review configuration: ${BLUE}sudo nano $CONFIG_FILE${NC}"
echo "2. Run safety check: ${BLUE}sudo ./pre-start-check.sh${NC}"
echo "3. Start services: ${BLUE}sudo systemctl start pendonn pendonn-web${NC}"
echo "4. Check status: ${BLUE}sudo systemctl status pendonn${NC}"
echo "5. View logs: ${BLUE}sudo journalctl -u pendonn -f${NC}"
echo ""
