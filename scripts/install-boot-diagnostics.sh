#!/bin/bash

###############################################################################
# Auto Boot Diagnostics - Captures info automatically at boot
# Run this ONCE to install, it will capture diagnostics on every boot
###############################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Installing Auto Boot Diagnostics...${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}ERROR: Please run as root (sudo)${NC}"
    exit 1
fi

# Create the diagnostic script
cat > /usr/local/bin/pendonn-boot-diagnostics.sh << 'EOFDIAG'
#!/bin/bash

# Auto-run at boot to capture diagnostics
LOGFILE="/var/log/pendonn-boot-diagnostics.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

{
    echo "=========================================="
    echo "Boot Diagnostics: $DATE"
    echo "=========================================="
    echo ""
    
    # Check PenDonn services
    echo "[1] PenDonn Services Status:"
    systemctl is-enabled pendonn.service 2>&1 || echo "pendonn: not found"
    systemctl is-active pendonn.service 2>&1 || echo "pendonn: inactive"
    systemctl is-enabled pendonn-web.service 2>&1 || echo "pendonn-web: not found"
    systemctl is-active pendonn-web.service 2>&1 || echo "pendonn-web: inactive"
    echo ""
    
    # Check if airmon-ng ran
    echo "[2] Did airmon-ng run?"
    journalctl -b | grep -i "airmon-ng" && echo "YES - FOUND" || echo "NO"
    echo ""
    
    # Check NetworkManager
    echo "[3] NetworkManager Status:"
    systemctl is-active NetworkManager
    echo ""
    
    # Check wlan0 mode
    echo "[4] wlan0 Interface Mode:"
    iw dev wlan0 info 2>&1 | grep "type" || echo "wlan0 not found"
    echo ""
    
    # Check wlan0 status
    echo "[5] wlan0 in NetworkManager:"
    nmcli device status | grep wlan0 || echo "wlan0 not in NM"
    echo ""
    
    # Power management
    echo "[6] WiFi Power Management:"
    iw dev wlan0 get power_save 2>&1 || echo "Can't check"
    iwconfig wlan0 2>&1 | grep "Power Management" || echo "Can't check"
    echo ""
    
    # Recent NetworkManager logs
    echo "[7] NetworkManager Errors:"
    journalctl -b -u NetworkManager --no-pager -p err | tail -10
    echo ""
    
    echo "=========================================="
    echo ""
    
} >> "$LOGFILE"

# Keep only last 10 boots
tail -500 "$LOGFILE" > "$LOGFILE.tmp" && mv "$LOGFILE.tmp" "$LOGFILE"
EOFDIAG

chmod +x /usr/local/bin/pendonn-boot-diagnostics.sh

# Create systemd service to run at boot
cat > /etc/systemd/system/pendonn-boot-diagnostics.service << 'EOFSERVICE'
[Unit]
Description=PenDonn Boot Diagnostics
After=network.target NetworkManager.service
Before=pendonn.service pendonn-web.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/pendonn-boot-diagnostics.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOFSERVICE

# Enable and start
systemctl daemon-reload
systemctl enable pendonn-boot-diagnostics.service
systemctl start pendonn-boot-diagnostics.service

echo -e "${GREEN}✓ Boot diagnostics installed!${NC}"
echo ""
echo -e "${YELLOW}What happens now:${NC}"
echo "  • Every boot, diagnostics are captured automatically"
echo "  • Logs saved to: ${BLUE}/var/log/pendonn-boot-diagnostics.log${NC}"
echo ""
echo -e "${YELLOW}To view diagnostics after WiFi dies:${NC}"
echo "  1. Get physical access (ethernet, monitor+keyboard, or SD card)"
echo "  2. Read the log:"
echo "     ${BLUE}cat /var/log/pendonn-boot-diagnostics.log${NC}"
echo ""
echo -e "${YELLOW}OR copy log to USB:${NC}"
echo "  ${BLUE}sudo cp /var/log/pendonn-boot-diagnostics.log /media/usb/boot-log.txt${NC}"
echo ""
echo -e "${GREEN}Now reboot and let WiFi fail, then check the log!${NC}"
echo ""
