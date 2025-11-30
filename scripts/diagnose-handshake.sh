#!/bin/bash

###############################################################################
# Diagnose Handshake Capture Issues
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== PenDonn Handshake Capture Diagnostics ===${NC}\n"

echo -e "${YELLOW}1. Check if airodump-ng/aireplay-ng are running:${NC}"
ps aux | grep -E "airodump|aireplay" | grep -v grep

echo -e "\n${YELLOW}2. Check monitor interfaces:${NC}"
iw dev

echo -e "\n${YELLOW}3. Check handshake directory:${NC}"
if [ -d "/opt/pendonn/handshakes" ]; then
    ls -lh /opt/pendonn/handshakes/
    echo ""
    echo "Total files: $(ls /opt/pendonn/handshakes/ 2>/dev/null | wc -l)"
else
    echo -e "${RED}Handshake directory doesn't exist!${NC}"
fi

echo -e "\n${YELLOW}4. Check if PenDonn is actually running:${NC}"
systemctl status pendonn --no-pager
echo ""
ps aux | grep -E "python.*main.py|pendonn" | grep -v grep

echo -e "\n${YELLOW}5. Check database and recent networks:${NC}"
if [ -f "/opt/pendonn/data/pendonn.db" ]; then
    echo "Database exists"
    sqlite3 /opt/pendonn/data/pendonn.db "SELECT ssid, bssid, channel, encryption, signal, discovered_at FROM networks ORDER BY discovered_at DESC LIMIT 10;" 2>/dev/null || echo -e "${RED}Database query failed - check if database is corrupted${NC}"
else
    echo -e "${RED}Database doesn't exist!${NC}"
fi

echo -e "\n${YELLOW}6. Check application logs (most recent):${NC}"
if [ -f "/opt/pendonn/logs/pendonn.log" ]; then
    echo "Last 50 lines from pendonn.log:"
    tail -50 /opt/pendonn/logs/pendonn.log
else
    echo -e "${RED}Log file doesn't exist!${NC}"
fi

echo -e "\n${YELLOW}7. Check systemd service logs:${NC}"
journalctl -u pendonn -n 50 --no-pager

echo -e "\n${YELLOW}8. Test airodump-ng manually:${NC}"
echo "To test manually, run:"
echo "  sudo airodump-ng wlan1"
echo "  sudo aireplay-ng --test wlan2"

echo -e "\n${BLUE}=== Diagnostics Complete ===${NC}"
