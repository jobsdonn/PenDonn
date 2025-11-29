#!/bin/bash

# PenDonn - WiFi Disconnect Diagnosis Script
# This script helps identify what's causing WiFi to disconnect ~5 seconds after boot
# Run this AFTER a reboot where WiFi disconnected

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PenDonn WiFi Disconnect Diagnosis${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}ERROR: Please run as root (sudo)${NC}"
    exit 1
fi

OUTPUT_FILE="/tmp/pendonn-wifi-diagnosis-$(date +%Y%m%d-%H%M%S).txt"

echo -e "${GREEN}Collecting diagnostic information...${NC}"
echo "Output will be saved to: $OUTPUT_FILE"
echo ""

# Create output file with header
{
    echo "PenDonn WiFi Diagnosis Report"
    echo "Generated: $(date)"
    echo "System: $(uname -a)"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
} > "$OUTPUT_FILE"

# Function to add section to report
add_section() {
    local title="$1"
    local command="$2"
    
    echo -e "${BLUE}[Checking] $title${NC}"
    {
        echo ""
        echo "═══════════════════════════════════════════════════════════════"
        echo "$title"
        echo "═══════════════════════════════════════════════════════════════"
        echo ""
        eval "$command" 2>&1 || echo "Command failed: $command"
        echo ""
    } >> "$OUTPUT_FILE"
}

# 1. Current interface status
add_section "1. Current Interface Status" \
    "ip addr show; echo ''; ip link show; echo ''; iwconfig 2>&1"

# 2. WiFi driver information
add_section "2. WiFi Driver Information" \
    "for iface in /sys/class/net/wlan*; do
        if [ -e \"\$iface\" ]; then
            name=\$(basename \"\$iface\")
            driver=\$(readlink \"\$iface/device/driver\" 2>/dev/null | xargs basename 2>/dev/null || echo 'unknown')
            mac=\$(cat \"\$iface/address\" 2>/dev/null)
            state=\$(cat \"\$iface/operstate\" 2>/dev/null)
            echo \"Interface: \$name\"
            echo \"  Driver: \$driver\"
            echo \"  MAC: \$mac\"
            echo \"  State: \$state\"
            echo \"\"
        fi
    done"

# 3. udev rules
add_section "3. udev Rules (Persistent Naming)" \
    "cat /etc/udev/rules.d/70-persistent-wifi.rules 2>&1 || echo 'No udev rules found'"

# 4. NetworkManager status and configuration
add_section "4. NetworkManager Status" \
    "systemctl status NetworkManager --no-pager; echo ''; \
     nmcli device status; echo ''; \
     nmcli connection show"

add_section "5. NetworkManager Configuration" \
    "cat /etc/NetworkManager/NetworkManager.conf"

add_section "6. NetworkManager Managed Devices" \
    "nmcli device | grep wlan"

# 5. Boot timing analysis - CRITICAL!
add_section "7. Boot Service Timing (systemd-analyze)" \
    "systemd-analyze blame | head -30"

add_section "8. Critical Period Analysis (Shows what ran 0-15 seconds after boot)" \
    "systemd-analyze critical-chain | head -20"

# 6. NetworkManager logs around disconnect time
add_section "9. NetworkManager Logs (Last Boot - First 30 Seconds)" \
    "journalctl -b -u NetworkManager --since '0 seconds ago' --until '30 seconds ago' --no-pager"

add_section "10. NetworkManager Recent Activity" \
    "journalctl -b -u NetworkManager -n 100 --no-pager"

# 7. Kernel/driver messages
add_section "11. WiFi Driver Messages (dmesg)" \
    "dmesg | grep -i 'wlan\|wifi\|brcm\|80211' | tail -50"

add_section "12. Kernel Messages (Last Boot)" \
    "journalctl -b -k -n 100 --no-pager"

# 8. wpa_supplicant logs
add_section "13. wpa_supplicant Status and Logs" \
    "systemctl status wpa_supplicant --no-pager; echo ''; \
     journalctl -b -u wpa_supplicant -n 50 --no-pager"

# 9. Check for known culprits
add_section "14. ModemManager Status (Common Culprit!)" \
    "systemctl status ModemManager --no-pager 2>&1 || echo 'ModemManager not installed'"

add_section "15. dhcpcd Status" \
    "systemctl status dhcpcd --no-pager 2>&1 || echo 'dhcpcd not running'; echo ''; \
     cat /etc/dhcpcd.conf 2>&1 | grep -A5 -B5 'wlan' || echo 'No wlan config in dhcpcd.conf'"

# 10. systemd network configuration
add_section "16. systemd-networkd Status" \
    "systemctl status systemd-networkd --no-pager; echo ''; \
     ls -la /etc/systemd/network/ 2>&1 || echo 'No systemd-networkd config'"

# 11. rfkill status
add_section "17. rfkill Status (WiFi Block/Unblock)" \
    "rfkill list all"

# 12. Current WiFi connection details
add_section "18. Current WiFi Connection" \
    "iwgetid -r; echo ''; \
     iwconfig wlan0 2>&1; echo ''; \
     iw dev wlan0 link 2>&1"

# 13. Active services that might interfere
add_section "19. Running Network-Related Services" \
    "systemctl list-units --type=service --state=running | grep -E 'network|wpa|dhcp|modem'"

# 14. Network interface configuration files
add_section "20. /etc/network/interfaces Configuration" \
    "cat /etc/network/interfaces 2>&1 || echo 'File not found'"

# 15. wpa_supplicant configuration
add_section "21. wpa_supplicant Configuration" \
    "cat /etc/wpa_supplicant/wpa_supplicant.conf 2>&1 | grep -v 'psk=' || echo 'File not found or no config'"

# 16. Check our custom services
add_section "22. PenDonn WiFi Keeper Service" \
    "systemctl status pendonn-wifi-keeper --no-pager 2>&1 || echo 'Service not found'"

add_section "23. PenDonn Auto-Fix Service" \
    "systemctl status pendonn-wifi-autofix --no-pager 2>&1 || echo 'Service not found'"

# 17. Boot logs (very verbose, but might show the issue)
add_section "24. Full Boot Log (Last 200 Lines)" \
    "journalctl -b -n 200 --no-pager"

echo "" >> "$OUTPUT_FILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >> "$OUTPUT_FILE"
echo "End of Diagnosis Report" >> "$OUTPUT_FILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >> "$OUTPUT_FILE"

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Diagnosis Complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}Report saved to: $OUTPUT_FILE${NC}"
echo ""
echo -e "${BLUE}KEY AREAS TO CHECK IN THE REPORT:${NC}"
echo ""
echo "1. Section 7-8: Boot timing analysis"
echo "   → Look for services starting 3-10 seconds after boot"
echo ""
echo "2. Section 9-10: NetworkManager logs"
echo "   → Look for 'state changed', 'deactivating', 'scanning'"
echo ""
echo "3. Section 11-12: Kernel messages"
echo "   → Look for brcmfmac errors, firmware crashes, or resets"
echo ""
echo "4. Section 14: ModemManager"
echo "   → If ModemManager is running, it's likely the culprit!"
echo ""
echo -e "${YELLOW}To view the report:${NC}"
echo "  cat $OUTPUT_FILE | less"
echo ""
echo -e "${YELLOW}To share with developer:${NC}"
echo "  scp $OUTPUT_FILE user@yourcomputer:/path/to/save/"
echo ""
echo -e "${RED}CRITICAL: Look for these patterns in the logs:${NC}"
echo "  • 'wlan0: deauthenticating' or 'deactivating connection'"
echo "  • Services starting around the 5-second mark"
echo "  • brcmfmac firmware crash or reset messages"
echo "  • ModemManager probing wlan0"
echo "  • NetworkManager state changes from 'connected' to something else"
echo ""

# Quick analysis
echo -e "${BLUE}Quick Analysis:${NC}"
echo ""

# Check if ModemManager is the culprit
if systemctl is-active --quiet ModemManager; then
    echo -e "${RED}⚠ WARNING: ModemManager is running!${NC}"
    echo "  This is a VERY common cause of WiFi disconnects on Pi."
    echo "  ModemManager scans all network devices looking for modems,"
    echo "  which can disrupt WiFi connections."
    echo ""
    echo -e "  ${YELLOW}Recommended fix:${NC}"
    echo "    sudo systemctl disable ModemManager"
    echo "    sudo systemctl stop ModemManager"
    echo ""
fi

# Check if wlan0 is currently up
if [ -e /sys/class/net/wlan0/operstate ]; then
    STATE=$(cat /sys/class/net/wlan0/operstate)
    if [ "$STATE" != "up" ]; then
        echo -e "${RED}⚠ wlan0 is currently: $STATE${NC}"
        echo "  (Should be 'up' if connected)"
        echo ""
    else
        echo -e "${GREEN}✓ wlan0 is currently: $STATE${NC}"
        echo ""
    fi
fi

# Check for recent NetworkManager state changes
echo -e "${YELLOW}Recent NetworkManager activity:${NC}"
journalctl -b -u NetworkManager -n 10 --no-pager | grep -i 'wlan0\|state' | tail -5
echo ""

echo -e "${GREEN}Done! Review the report at: $OUTPUT_FILE${NC}"
