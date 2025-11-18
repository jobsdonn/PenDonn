#!/bin/bash

###############################################################################
# PenDonn Quick Start Script
# Run this after installation to configure and start the system
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║                    PenDonn Quick Start                         ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}[ERROR]${NC} Please run as root (use sudo)"
    exit 1
fi

# Check if installed
if [ ! -d "/opt/pendonn" ]; then
    echo -e "${RED}[ERROR]${NC} PenDonn is not installed. Run install.sh first."
    exit 1
fi

cd /opt/pendonn

echo -e "${GREEN}[INFO]${NC} Detecting WiFi interfaces..."
echo ""

# Detect WiFi interfaces
INTERFACES=$(iw dev | grep Interface | awk '{print $2}')
INTERFACE_ARRAY=($INTERFACES)
INTERFACE_COUNT=${#INTERFACE_ARRAY[@]}

echo -e "${BLUE}Found $INTERFACE_COUNT WiFi interfaces:${NC}"
for i in "${!INTERFACE_ARRAY[@]}"; do
    echo -e "  $((i+1)). ${INTERFACE_ARRAY[$i]}"
done
echo ""

if [ "$INTERFACE_COUNT" -lt 3 ]; then
    echo -e "${RED}[WARNING]${NC} You need at least 3 WiFi interfaces!"
    echo -e "  - 1 onboard WiFi (management)"
    echo -e "  - 2 external WiFi adapters (monitoring & attack)"
    echo ""
    read -p "Continue anyway? (yes/no): " continue_anyway
    if [ "$continue_anyway" != "yes" ]; then
        exit 1
    fi
fi

# Configure interfaces
echo -e "${YELLOW}[SETUP]${NC} Configure WiFi interfaces"
echo ""

echo "Which interface should be used for MANAGEMENT (onboard WiFi)?"
read -p "Enter interface name (default: wlan0): " MGMT_IFACE
MGMT_IFACE=${MGMT_IFACE:-wlan0}

echo "Which interface should be used for MONITORING?"
read -p "Enter interface name (default: wlan1): " MON_IFACE
MON_IFACE=${MON_IFACE:-wlan1}

echo "Which interface should be used for ATTACKS?"
read -p "Enter interface name (default: wlan2): " ATK_IFACE
ATK_IFACE=${ATK_IFACE:-wlan2}

# Update config
echo -e "${GREEN}[INFO]${NC} Updating configuration..."
python3 << EOF
import json
with open('config/config.json', 'r') as f:
    config = json.load(f)
config['wifi']['management_interface'] = '$MGMT_IFACE'
config['wifi']['monitor_interface'] = '$MON_IFACE'
config['wifi']['attack_interface'] = '$ATK_IFACE'
with open('config/config.json', 'w') as f:
    json.dump(config, f, indent=2)
EOF

# Add to whitelist
echo ""
echo -e "${YELLOW}[SETUP]${NC} Add networks to whitelist"
echo "Enter SSIDs to whitelist (one per line, empty line to finish):"
WHITELIST_SSIDS=()
while true; do
    read -p "SSID: " ssid
    if [ -z "$ssid" ]; then
        break
    fi
    WHITELIST_SSIDS+=("$ssid")
done

if [ ${#WHITELIST_SSIDS[@]} -gt 0 ]; then
    echo -e "${GREEN}[INFO]${NC} Adding to whitelist: ${WHITELIST_SSIDS[@]}"
    python3 << EOF
import json
with open('config/config.json', 'r') as f:
    config = json.load(f)
config['whitelist']['ssids'] = [$(printf '"%s",' "${WHITELIST_SSIDS[@]}" | sed 's/,$//')
]
with open('config/config.json', 'w') as f:
    json.dump(config, f, indent=2)
EOF
fi

# Generate secret key
echo -e "${GREEN}[INFO]${NC} Generating web interface secret key..."
SECRET_KEY=$(openssl rand -hex 32)
python3 << EOF
import json
with open('config/config.json', 'r') as f:
    config = json.load(f)
config['web']['secret_key'] = '$SECRET_KEY'
with open('config/config.json', 'w') as f:
    json.dump(config, f, indent=2)
EOF

# Enable and start services
echo -e "${GREEN}[INFO]${NC} Starting PenDonn services..."
systemctl daemon-reload
systemctl enable pendonn pendonn-web
systemctl restart pendonn pendonn-web

sleep 3

# Check status
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}              Setup Complete!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

if systemctl is-active --quiet pendonn; then
    echo -e "${GREEN}✓${NC} PenDonn daemon: ${GREEN}RUNNING${NC}"
else
    echo -e "${RED}✗${NC} PenDonn daemon: ${RED}STOPPED${NC}"
fi

if systemctl is-active --quiet pendonn-web; then
    echo -e "${GREEN}✓${NC} Web interface: ${GREEN}RUNNING${NC}"
else
    echo -e "${RED}✗${NC} Web interface: ${RED}STOPPED${NC}"
fi

echo ""
echo -e "${YELLOW}Web Interface:${NC}"
IP_ADDR=$(hostname -I | awk '{print $1}')
echo -e "  Local:  ${BLUE}http://localhost:8080${NC}"
echo -e "  Remote: ${BLUE}http://$IP_ADDR:8080${NC}"
echo ""
echo -e "${YELLOW}Useful Commands:${NC}"
echo -e "  View logs:      ${BLUE}sudo journalctl -u pendonn -f${NC}"
echo -e "  Restart:        ${BLUE}sudo systemctl restart pendonn${NC}"
echo -e "  Stop:           ${BLUE}sudo systemctl stop pendonn${NC}"
echo -e "  Configuration:  ${BLUE}sudo nano /opt/pendonn/config/config.json${NC}"
echo ""
echo -e "${GREEN}Happy (legal) hacking! 🔒${NC}"
