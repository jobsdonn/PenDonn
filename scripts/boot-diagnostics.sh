#!/bin/bash

###############################################################################
# Boot Diagnostics - Check what's killing WiFi
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Boot Diagnostics - What's Killing WiFi?${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check if PenDonn services exist and their status
echo -e "${YELLOW}[1] Checking PenDonn services...${NC}"
echo ""

for service in pendonn.service pendonn-web.service; do
    echo -e "${BLUE}$service:${NC}"
    
    if systemctl list-unit-files | grep -q "$service"; then
        echo "  Exists: YES"
        
        IS_ENABLED=$(systemctl is-enabled $service 2>/dev/null || echo "disabled")
        echo "  Enabled: $IS_ENABLED"
        
        IS_ACTIVE=$(systemctl is-active $service 2>/dev/null || echo "inactive")
        echo "  Active: $IS_ACTIVE"
        
        if [ "$IS_ENABLED" = "enabled" ]; then
            echo -e "  ${RED}PROBLEM: Service is ENABLED (will start at boot)${NC}"
        fi
        
        if [ "$IS_ACTIVE" = "active" ]; then
            echo -e "  ${RED}PROBLEM: Service is RUNNING NOW${NC}"
        fi
    else
        echo "  Exists: NO"
    fi
    echo ""
done

# Check if airmon-ng has been run
echo -e "${YELLOW}[2] Checking if airmon-ng killed NetworkManager...${NC}"
journalctl -b | grep -i "airmon-ng" && echo -e "${RED}FOUND: airmon-ng was executed${NC}" || echo -e "${GREEN}No airmon-ng in logs${NC}"
echo ""

# Check NetworkManager status
echo -e "${YELLOW}[3] NetworkManager status...${NC}"
systemctl status NetworkManager --no-pager | head -15
echo ""

# Check for anything that killed NetworkManager
echo -e "${YELLOW}[4] What killed NetworkManager?${NC}"
journalctl -b -u NetworkManager | grep -i "killed\|terminated\|stopped" && echo "" || echo -e "${GREEN}NetworkManager not killed${NC}"
echo ""

# Check boot log for WiFi issues
echo -e "${YELLOW}[5] Boot logs about WiFi...${NC}"
journalctl -b | grep -i "wlan0\|wifi\|brcmfmac" | tail -20
echo ""

# Check current WiFi status
echo -e "${YELLOW}[6] Current WiFi status...${NC}"
nmcli device status | grep wlan
echo ""
iw dev wlan0 info 2>/dev/null && echo "" || echo -e "${RED}wlan0 not in managed mode${NC}"
echo ""

# Check if wlan0 is in monitor mode
echo -e "${YELLOW}[7] Is wlan0 in monitor mode?${NC}"
iw dev wlan0 info 2>/dev/null | grep "type monitor" && echo -e "${RED}YES - wlan0 is in MONITOR MODE (this is the problem!)${NC}" || echo -e "${GREEN}No - wlan0 is in managed mode${NC}"
echo ""

# Check what processes are using wlan0
echo -e "${YELLOW}[8] What's using wlan0?${NC}"
lsof 2>/dev/null | grep wlan0 || echo "Nothing found with lsof"
echo ""

# Final summary
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Diagnostics Complete${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}If you see:${NC}"
echo "  • ${RED}Service is ENABLED${NC} → Run: sudo systemctl disable pendonn pendonn-web"
echo "  • ${RED}Service is RUNNING${NC} → Run: sudo systemctl stop pendonn pendonn-web"
echo "  • ${RED}airmon-ng was executed${NC} → Something started the PenDonn service"
echo "  • ${RED}wlan0 is in MONITOR MODE${NC} → Run: sudo systemctl stop pendonn; sudo systemctl restart NetworkManager"
echo ""
