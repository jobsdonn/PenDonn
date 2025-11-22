#!/bin/bash

###############################################################################
# PenDonn Pre-Start Safety Check
# Run this before starting PenDonn services to verify configuration
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

INSTALL_DIR="/opt/pendonn"
CONFIG_FILE="$INSTALL_DIR/config/config.json"

echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           PenDonn Pre-Start Safety Check                       ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}[ERROR]${NC} Please run as root (use sudo)"
    exit 1
fi

# Check if config exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}[✗]${NC} Configuration file not found: $CONFIG_FILE"
    exit 1
fi

echo -e "${YELLOW}[INFO]${NC} Checking WiFi interface configuration..."
echo ""

# Detect WiFi interfaces
INTERFACES=$(iw dev | grep Interface | awk '{print $2}')
INTERFACE_COUNT=$(echo "$INTERFACES" | wc -l)

echo -e "${BLUE}Detected WiFi interfaces:${NC}"
echo "$INTERFACES" | nl
echo ""

# Read config
MONITOR_IF=$(grep -A 5 '"wifi"' "$CONFIG_FILE" | grep '"monitor_interface"' | cut -d'"' -f4)
ATTACK_IF=$(grep -A 5 '"wifi"' | grep '"attack_interface"' "$CONFIG_FILE" | cut -d'"' -f4)
MGMT_IF=$(grep -A 5 '"wifi"' "$CONFIG_FILE" | grep '"management_interface"' | cut -d'"' -f4)

echo -e "${BLUE}Configured interfaces:${NC}"
echo "  Monitor:     $MONITOR_IF"
echo "  Attack:      $ATTACK_IF"
echo "  Management:  $MGMT_IF"
echo ""

# Check if SSH connection exists
SSH_CONNECTION=$(who am i | grep -oP '\d+\.\d+\.\d+\.\d+' || echo "")
CURRENT_CONNECTION_IF=""

if [ -n "$SSH_CONNECTION" ]; then
    echo -e "${YELLOW}[!]${NC} You are connected via SSH from: $SSH_CONNECTION"
    
    # Try to determine which interface SSH is using
    DEFAULT_ROUTE_IF=$(ip route | grep default | awk '{print $5}' | head -n1)
    echo -e "${YELLOW}[!]${NC} Your SSH connection is likely using: $DEFAULT_ROUTE_IF"
    echo ""
    
    CURRENT_CONNECTION_IF=$DEFAULT_ROUTE_IF
fi

# Warning checks
WARNINGS=0

echo -e "${BLUE}Safety Checks:${NC}"

# Check 1: Management interface not configured for monitor/attack
if [ "$MGMT_IF" = "$MONITOR_IF" ] || [ "$MGMT_IF" = "$ATTACK_IF" ]; then
    echo -e "${RED}[✗]${NC} Management interface ($MGMT_IF) is configured as monitor/attack interface!"
    echo -e "    ${YELLOW}This will break network connectivity.${NC}"
    ((WARNINGS++))
else
    echo -e "${GREEN}[✓]${NC} Management interface is separate from monitor/attack interfaces"
fi

# Check 2: SSH connection won't be affected
if [ -n "$CURRENT_CONNECTION_IF" ]; then
    if [ "$CURRENT_CONNECTION_IF" = "$MONITOR_IF" ] || [ "$CURRENT_CONNECTION_IF" = "$ATTACK_IF" ]; then
        echo -e "${RED}[✗]${NC} Your SSH connection uses $CURRENT_CONNECTION_IF which is configured for monitor mode!"
        echo -e "    ${YELLOW}Starting PenDonn will disconnect you!${NC}"
        ((WARNINGS++))
    else
        echo -e "${GREEN}[✓]${NC} SSH connection interface is safe"
    fi
fi

# Check 3: At least 3 interfaces total
if [ "$INTERFACE_COUNT" -lt 3 ]; then
    echo -e "${YELLOW}[!]${NC} Only $INTERFACE_COUNT WiFi interface(s) detected (need 3)"
    echo -e "    You need: 1 onboard + 2 external WiFi adapters"
    ((WARNINGS++))
else
    echo -e "${GREEN}[✓]${NC} Sufficient WiFi interfaces detected ($INTERFACE_COUNT)"
fi

# Check 4: Whitelist configured
WHITELIST_COUNT=$(grep -A 5 '"whitelist"' "$CONFIG_FILE" | grep -c '"ssids"')
if [ "$WHITELIST_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}[!]${NC} No SSIDs in whitelist - will scan ALL networks"
    echo -e "    ${YELLOW}Add your own networks to whitelist to avoid scanning them${NC}"
    ((WARNINGS++))
else
    echo -e "${GREEN}[✓]${NC} Whitelist is configured"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"

if [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ All safety checks passed!${NC}"
    echo ""
    echo -e "You can safely start PenDonn services:"
    echo -e "  ${BLUE}sudo systemctl start pendonn pendonn-web${NC}"
    echo ""
    echo -e "Monitor status with:"
    echo -e "  ${BLUE}sudo systemctl status pendonn${NC}"
    echo -e "  ${BLUE}sudo journalctl -u pendonn -f${NC}"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Found $WARNINGS warning(s) - please review configuration!${NC}"
    echo ""
    echo -e "Edit configuration file:"
    echo -e "  ${BLUE}sudo nano $CONFIG_FILE${NC}"
    echo ""
    echo -e "${YELLOW}Common fixes:${NC}"
    echo -e "1. Set management_interface to your onboard WiFi (usually wlan0)"
    echo -e "2. Set monitor_interface to first external adapter (wlan1)"
    echo -e "3. Set attack_interface to second external adapter (wlan2)"
    echo -e "4. Add your home/work networks to whitelist"
    echo ""
    echo -e "${YELLOW}If you're accessing via SSH:${NC}"
    echo -e "1. Make sure SSH uses the management interface"
    echo -e "2. Consider using ethernet connection instead"
    echo -e "3. Connect directly to RPi with keyboard/monitor"
    echo ""
    
    read -p "Do you want to start services anyway? (yes/no): " FORCE_START
    if [ "$FORCE_START" = "yes" ]; then
        echo ""
        echo -e "${YELLOW}Starting services despite warnings...${NC}"
        echo -e "${RED}Your SSH connection may disconnect!${NC}"
        sleep 3
        exit 0
    else
        echo ""
        echo -e "${GREEN}Wise choice. Fix configuration and run this check again.${NC}"
        echo ""
        exit 1
    fi
fi
