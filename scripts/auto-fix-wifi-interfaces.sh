#!/bin/bash

###############################################################################
# PenDonn - Auto WiFi Interface Fixer
# Runs on boot to ensure correct interface naming
# Only fixes if needed (idempotent)
###############################################################################

LOG_FILE="/var/log/pendonn-wifi-autofix.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== PenDonn Auto WiFi Interface Fix Started ==="

# Wait for network interfaces to be fully initialized
log "Waiting 10 seconds for interfaces to stabilize..."
sleep 10

# Check if built-in WiFi (brcmfmac) is NOT on wlan0
BUILTIN_ON_WLAN0=false

if [ -e /sys/class/net/wlan0/device/driver ]; then
    WLAN0_DRIVER=$(readlink /sys/class/net/wlan0/device/driver 2>/dev/null | xargs basename 2>/dev/null)
    if [[ "$WLAN0_DRIVER" == "brcmfmac" ]] || [[ "$WLAN0_DRIVER" == "brcmutil" ]]; then
        BUILTIN_ON_WLAN0=true
        log "Built-in WiFi is already on wlan0 - no fix needed"
        exit 0
    fi
fi

log "Built-in WiFi is NOT on wlan0 - searching for it..."

# Find the built-in WiFi interface
BUILTIN_MAC=""
BUILTIN_IFACE=""

for iface in /sys/class/net/wlan*; do
    if [ -e "$iface" ]; then
        IFACE_NAME=$(basename "$iface")
        DRIVER=$(readlink "$iface/device/driver" 2>/dev/null | xargs basename 2>/dev/null || echo "unknown")
        MAC=$(cat "$iface/address" 2>/dev/null)
        
        log "Checking $IFACE_NAME: driver=$DRIVER, MAC=$MAC"
        
        if [[ "$DRIVER" == "brcmfmac" ]] || [[ "$DRIVER" == "brcmutil" ]]; then
            BUILTIN_MAC="$MAC"
            BUILTIN_IFACE="$IFACE_NAME"
            log "Found built-in WiFi on $IFACE_NAME (MAC: $MAC)"
            break
        fi
    fi
done

if [ -z "$BUILTIN_MAC" ]; then
    log "No built-in WiFi detected - nothing to fix"
    exit 0
fi

log "Applying fix: Locking MAC $BUILTIN_MAC to wlan0..."

# Backup existing rules
if [ -f /etc/udev/rules.d/70-persistent-wifi.rules ]; then
    cp /etc/udev/rules.d/70-persistent-wifi.rules /etc/udev/rules.d/70-persistent-wifi.rules.backup.$(date +%Y%m%d_%H%M%S)
    log "Backed up existing udev rules"
fi

# Create corrected udev rules
cat > /etc/udev/rules.d/70-persistent-wifi.rules << EOF
# PenDonn - Persistent WiFi Interface Naming (Auto-fixed on $(date))
# Built-in WiFi MUST be wlan0 for management/SSH connection

# Built-in Broadcom WiFi is ALWAYS wlan0 (management interface)
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="$BUILTIN_MAC", NAME="wlan0"

# External USB WiFi adapters become wlan1 and wlan2 (pentesting)
EOF

log "Created udev rules locking $BUILTIN_MAC to wlan0"

# Update NetworkManager configuration
if systemctl is-active --quiet NetworkManager 2>/dev/null; then
    if [ -f /etc/NetworkManager/NetworkManager.conf ]; then
        cp /etc/NetworkManager/NetworkManager.conf /etc/NetworkManager/NetworkManager.conf.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null
        
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
        log "Updated NetworkManager configuration"
    fi
fi

# Update dhcpcd configuration
if [ -f /etc/dhcpcd.conf ]; then
    if ! grep -q "denyinterfaces wlan1 wlan2" /etc/dhcpcd.conf; then
        cp /etc/dhcpcd.conf /etc/dhcpcd.conf.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null
        echo "" >> /etc/dhcpcd.conf
        echo "# PenDonn: Don't manage pentesting interfaces (auto-fixed $(date))" >> /etc/dhcpcd.conf
        echo "denyinterfaces wlan1 wlan2" >> /etc/dhcpcd.conf
        log "Updated dhcpcd configuration"
    fi
fi

# Reload udev rules
udevadm control --reload-rules
udevadm trigger --subsystem-match=net
log "Reloaded udev rules"

# IMMEDIATE FIX: Rename interfaces NOW (don't wait for reboot)
log "=== Applying immediate interface rename ==="

# First, identify which interface currently has the connection
CONNECTED_IFACE=""
if command -v nmcli >/dev/null 2>&1; then
    CONNECTED_IFACE=$(nmcli -t -f DEVICE,STATE dev | grep ':connected$' | cut -d':' -f1 | grep '^wlan' | head -1)
fi

if [ -z "$CONNECTED_IFACE" ]; then
    # Fallback: check which interface has IP address
    CONNECTED_IFACE=$(ip -4 addr show | grep -oP '(?<=^[0-9]: )wlan[0-9]+' | head -1)
fi

log "Currently connected interface: ${CONNECTED_IFACE:-none}"

# Strategy: Rename interfaces in order, avoiding the connected one until last
# We need to rename: builtin to wlan0, and shuffle others

if [ "$BUILTIN_IFACE" != "wlan0" ]; then
    log "Built-in WiFi is on $BUILTIN_IFACE, needs to be wlan0"
    
    # Step 1: Move wlan0 out of the way (if it exists and is not builtin)
    if [ -e /sys/class/net/wlan0 ] && [ "$CONNECTED_IFACE" != "wlan0" ]; then
        log "Moving existing wlan0 to temp name..."
        ip link set wlan0 down 2>/dev/null
        ip link set wlan0 name wlan_temp 2>/dev/null && log "Renamed wlan0 -> wlan_temp" || log "Failed to rename wlan0"
    fi
    
    # Step 2: Rename builtin to wlan0 (carefully if it's connected)
    if [ "$CONNECTED_IFACE" == "$BUILTIN_IFACE" ]; then
        log "WARNING: Built-in WiFi is currently connected - attempting careful rename..."
        # Keep it up during rename to maintain connection
        ip link set "$BUILTIN_IFACE" name wlan0 2>/dev/null && log "Renamed $BUILTIN_IFACE -> wlan0 (kept connection)" || log "Failed to rename $BUILTIN_IFACE"
    else
        log "Renaming built-in WiFi $BUILTIN_IFACE -> wlan0..."
        ip link set "$BUILTIN_IFACE" down 2>/dev/null
        ip link set "$BUILTIN_IFACE" name wlan0 2>/dev/null && log "Renamed $BUILTIN_IFACE -> wlan0" || log "Failed to rename $BUILTIN_IFACE"
        ip link set wlan0 up 2>/dev/null
    fi
    
    # Step 3: Rename temp back to available slot
    if [ -e /sys/class/net/wlan_temp ]; then
        log "Moving wlan_temp to next available slot..."
        ip link set wlan_temp name wlan1 2>/dev/null && log "Renamed wlan_temp -> wlan1" || log "Failed to rename wlan_temp"
        ip link set wlan1 up 2>/dev/null
    fi
    
    log "Immediate interface renaming completed"
else
    log "Built-in WiFi already on wlan0 - no immediate rename needed"
fi

log "=== WiFi interface auto-fix completed ==="
log "Interfaces should now be correctly named (wlan0=builtin)"
log "Udev rules ensure names persist after reboot"

# Create flag file
echo "WiFi interfaces were auto-fixed on $(date). wlan0 is now the built-in WiFi." > /tmp/pendonn-wifi-fixed

exit 0
