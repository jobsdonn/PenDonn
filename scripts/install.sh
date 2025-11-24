#!/bin/bash

###############################################################################
# PenDonn - Automated Penetration Testing Tool Installer
# For Raspberry Pi 4/5 with Raspberry Pi OS Trixie
# 
# LEGAL NOTICE: This tool is for authorized penetration testing only.
# Unauthorized access to computer networks is illegal.
###############################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

INSTALL_DIR="/opt/pendonn"
SERVICE_NAME="pendonn"
WEB_SERVICE_NAME="pendonn-web"

echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║                         PenDonn                                ║
║           Automated Penetration Testing System                 ║
║                      Installer v1.0.0                          ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}[ERROR]${NC} Please run as root (use sudo)"
    exit 1
fi

echo -e "${GREEN}[INFO]${NC} Starting installation process..."

# Function to print status
print_status() {
    echo -e "${BLUE}[*]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Legal warning
echo -e "${YELLOW}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║                      LEGAL WARNING                             ║
╚═══════════════════════════════════════════════════════════════╝

This tool is designed for AUTHORIZED penetration testing only.

By installing and using this software, you agree that:
1. You will only use it on networks you own or have explicit 
   written permission to test
2. Unauthorized network access is illegal in most jurisdictions
3. You take full responsibility for your actions
4. The developers assume no liability for misuse

EOF
echo -e "${NC}"

read -p "Do you understand and agree? (yes/no): " agreement
if [ "$agreement" != "yes" ]; then
    echo -e "${RED}Installation aborted.${NC}"
    exit 1
fi

# Update system
print_status "Updating system packages..."
apt-get update -qq
print_success "System packages updated"

# Install system dependencies
print_status "Installing system dependencies (this may take several minutes)..."
echo -e "${YELLOW}Note: You'll see the actual apt-get output below${NC}"

# Try to install kernel headers (package name varies by OS version)
KERNEL_HEADERS="linux-headers-$(uname -r)"
if ! apt-cache show raspberrypi-kernel-headers > /dev/null 2>&1; then
    echo -e "${YELLOW}Note: Using $KERNEL_HEADERS (raspberrypi-kernel-headers not available)${NC}"
else
    KERNEL_HEADERS="raspberrypi-kernel-headers"
fi

apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    rsync \
    aircrack-ng \
    john \
    hashcat \
    nmap \
    tcpdump \
    wireless-tools \
    net-tools \
    iw \
    macchanger \
    git \
    sqlite3 \
    hostapd \
    dnsmasq \
    nginx \
    build-essential \
    dkms \
    $KERNEL_HEADERS \
    bc || {
        # If some packages fail, try without optional ones
        echo -e "${YELLOW}Some packages unavailable, trying without hcxtools/hcxdumptool...${NC}"
        apt-get install -y \
            python3 \
            python3-pip \
            python3-venv \
            rsync \
            aircrack-ng \
            john \
            hashcat \
            nmap \
            tcpdump \
            wireless-tools \
            net-tools \
            iw \
            macchanger \
            git \
            sqlite3 \
            hostapd \
            dnsmasq \
            nginx \
            build-essential \
            dkms \
            $KERNEL_HEADERS \
            bc
    }

# Try to install hcxtools/hcxdumptool separately (may not be available in all repos)
if apt-cache show hcxtools > /dev/null 2>&1; then
    apt-get install -y hcxtools hcxdumptool || print_warning "hcxtools/hcxdumptool not available"
else
    print_warning "hcxtools/hcxdumptool not available in repositories (optional)"
fi

print_success "System dependencies installed"

# IMPORTANT: Configure WiFi protection BEFORE installing drivers
# This prevents external drivers from breaking built-in WiFi
print_status "Configuring WiFi protection (before driver installation)..."

# Detect built-in WiFi by driver (not by interface name!)
BUILTIN_MAC=""
BUILTIN_IFACE=""

echo -e "${BLUE}Detecting built-in WiFi adapter...${NC}"
for iface in /sys/class/net/wlan*; do
    if [ -e "$iface" ]; then
        IFACE_NAME=$(basename "$iface")
        DRIVER=$(readlink "$iface/device/driver" 2>/dev/null | xargs basename 2>/dev/null || echo "unknown")
        MAC=$(cat "$iface/address" 2>/dev/null)
        
        echo -e "  Checking $IFACE_NAME: driver=$DRIVER"
        
        # Raspberry Pi built-in WiFi uses brcmfmac driver
        if [[ "$DRIVER" == "brcmfmac" ]] || [[ "$DRIVER" == "brcmutil" ]]; then
            BUILTIN_MAC="$MAC"
            BUILTIN_IFACE="$IFACE_NAME"
            echo -e "${GREEN}  ✓ Found built-in WiFi: $IFACE_NAME (MAC: $MAC)${NC}"
            break
        fi
    fi
done

if [ -n "$BUILTIN_MAC" ]; then
    echo -e "${GREEN}Built-in WiFi detected: $BUILTIN_IFACE (MAC: $BUILTIN_MAC)${NC}"
    
    echo -e "${BLUE}Creating udev rules for persistent interface naming...${NC}"
    cat > /etc/udev/rules.d/70-persistent-wifi.rules << EOF
# PenDonn - Persistent WiFi Interface Naming
# Created BEFORE driver installation to prevent WiFi loss
# Built-in WiFi is always wlan0 (management interface)
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="$BUILTIN_MAC", NAME="wlan0"

# External USB WiFi adapters become wlan1 and wlan2
# These will be used for pentesting (monitor/attack interfaces)
EOF
    print_success "udev rules created (wlan0 locked to $BUILTIN_MAC)"
else
    print_warning "Built-in WiFi not detected - WiFi protection skipped"
    echo -e "${YELLOW}This is normal if you're using only external adapters${NC}"
fi

# Configure NetworkManager to not manage external interfaces
if systemctl is-active --quiet NetworkManager; then
    echo -e "${BLUE}Configuring NetworkManager to ignore wlan1/wlan2...${NC}"
    
    if [ -f /etc/NetworkManager/NetworkManager.conf ]; then
        cp /etc/NetworkManager/NetworkManager.conf /etc/NetworkManager/NetworkManager.conf.backup
        
        if grep -q "^\[keyfile\]" /etc/NetworkManager/NetworkManager.conf; then
            if ! grep -q "unmanaged-devices" /etc/NetworkManager/NetworkManager.conf; then
                sed -i '/^\[keyfile\]/a unmanaged-devices=interface-name:wlan1;interface-name:wlan2' /etc/NetworkManager/NetworkManager.conf
            fi
        else
            echo "" >> /etc/NetworkManager/NetworkManager.conf
            echo "[keyfile]" >> /etc/NetworkManager/NetworkManager.conf
            echo "unmanaged-devices=interface-name:wlan1;interface-name:wlan2" >> /etc/NetworkManager/NetworkManager.conf
        fi
        print_success "NetworkManager configured"
    fi
elif [ -f /etc/dhcpcd.conf ]; then
    echo -e "${BLUE}Configuring dhcpcd to ignore wlan1/wlan2...${NC}"
    
    if ! grep -q "denyinterfaces wlan1 wlan2" /etc/dhcpcd.conf; then
        cp /etc/dhcpcd.conf /etc/dhcpcd.conf.backup
        echo "" >> /etc/dhcpcd.conf
        echo "# PenDonn: Don't manage pentesting interfaces" >> /etc/dhcpcd.conf
        echo "denyinterfaces wlan1 wlan2" >> /etc/dhcpcd.conf
        print_success "dhcpcd configured"
    fi
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}WiFi Protection Configured${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
if [ -n "$BUILTIN_MAC" ]; then
    echo -e "${BLUE}Protection applied:${NC}"
    echo -e "  ✓ wlan0 locked to built-in WiFi (MAC: $BUILTIN_MAC)"
    echo -e "  ✓ wlan1/wlan2 reserved for external adapters"
    echo -e "  ✓ Network manager configured to ignore wlan1/wlan2"
    echo ""
    echo -e "${YELLOW}This ensures your built-in WiFi stays connected after reboot!${NC}"
else
    echo -e "${YELLOW}No built-in WiFi detected - using external adapters only${NC}"
fi
echo ""

# Configure automatic WiFi reconnection on boot
if [ -n "$BUILTIN_MAC" ]; then
    echo -e "${BLUE}Setting up automatic WiFi reconnection service...${NC}"

    # Get current WiFi connection details
    CURRENT_SSID=$(iwgetid -r 2>/dev/null || nmcli -t -f active,ssid dev wifi | grep '^yes' | cut -d':' -f2 2>/dev/null || echo "")

    if [ -n "$CURRENT_SSID" ]; then
        echo -e "${GREEN}Current WiFi: $CURRENT_SSID${NC}"
        read -p "Save this WiFi for automatic reconnection on boot? (yes/no) [yes]: " SAVE_WIFI
        SAVE_WIFI=${SAVE_WIFI:-yes}
        
        if [ "$SAVE_WIFI" = "yes" ]; then
        # Create WiFi reconnection script
        cat > /usr/local/bin/pendonn-wifi-keeper.sh << 'EOFWIFI'
#!/bin/bash
# PenDonn WiFi Keeper - Ensures wlan0 stays connected

INTERFACE="wlan0"
MAX_RETRIES=10
RETRY_DELAY=5

# Wait for interface to exist
for i in $(seq 1 $MAX_RETRIES); do
    if [ -e "/sys/class/net/$INTERFACE" ]; then
        echo "Interface $INTERFACE found"
        break
    fi
    echo "Waiting for $INTERFACE... ($i/$MAX_RETRIES)"
    sleep $RETRY_DELAY
done

# Check if we have NetworkManager
if systemctl is-active --quiet NetworkManager; then
    echo "Using NetworkManager for WiFi management"
    
    # Wait for NetworkManager to be ready
    sleep 5
    
    # Check if already connected
    if nmcli -t -f DEVICE,STATE dev | grep "^$INTERFACE:connected" > /dev/null; then
        echo "Already connected to WiFi"
        exit 0
    fi
    
    # Try to reconnect
    echo "Attempting WiFi reconnection..."
    nmcli device connect $INTERFACE
    
elif command -v wpa_supplicant > /dev/null; then
    echo "Using wpa_supplicant for WiFi management"
    
    # Check if wlan0 is up
    if ! ip link show $INTERFACE | grep -q "UP"; then
        ip link set $INTERFACE up
    fi
    
    # Wait for connection
    for i in $(seq 1 $MAX_RETRIES); do
        if iwgetid -r > /dev/null 2>&1; then
            echo "WiFi connected"
            exit 0
        fi
        echo "Waiting for WiFi connection... ($i/$MAX_RETRIES)"
        sleep $RETRY_DELAY
    done
fi

echo "WiFi keeper completed"
EOFWIFI

        chmod +x /usr/local/bin/pendonn-wifi-keeper.sh
        
        # Create systemd service for WiFi keeper
        cat > /etc/systemd/system/pendonn-wifi-keeper.service << EOFSERVICE
[Unit]
Description=PenDonn WiFi Keeper
After=network-pre.target
Before=network.target
Wants=network-pre.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/pendonn-wifi-keeper.sh
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOFSERVICE

        # Enable the service
        systemctl daemon-reload
        systemctl enable pendonn-wifi-keeper.service
        
        print_success "WiFi keeper service installed (will reconnect wlan0 on boot)"
        fi
    else
        print_warning "No active WiFi connection detected - WiFi keeper not configured"
        echo -e "${YELLOW}You can manually configure WiFi reconnection later if needed${NC}"
    fi
else
    echo -e "${YELLOW}Skipping WiFi keeper setup (no built-in WiFi detected)${NC}"
fi

echo ""

# Ask about WiFi driver installation
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}WiFi Driver Installation${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Select which WiFi adapter drivers to install:"
echo ""
echo "  1) RTL8188EU/EUS  - TP-Link TL-WN722N v2/v3, many cheap adapters"
echo "  2) RTL8812AU      - Alfa AWUS036ACH, AWUS036AC (dual-band, recommended)"
echo "  3) RTL8814AU      - Alfa AWUS1900 (high-power)"
echo "  4) RTL8822BU      - Realtek 8822BU chipset"
echo "  5) RTL8821CU      - Realtek 8821CU chipset"
echo "  6) MT7612U        - Alfa AWUS036ACM, Panda PAU0D"
echo "  7) RT5370         - Ralink RT5370 (built into many adapters)"
echo "  8) AR9271         - Atheros AR9271 (TP-Link TL-WN722N v1)"
echo "  a) Install ALL drivers (takes 10-15 minutes)"
echo "  s) Skip driver installation"
echo ""
echo "Enter your choices (e.g., '1 2 3' or 'a' for all, 's' to skip):"
read -p "> " DRIVER_CHOICE
echo

if [[ $DRIVER_CHOICE =~ [Ss] ]]; then
    echo -e "${YELLOW}Skipping WiFi driver installation${NC}"
    echo -e "${BLUE}You can install them later with: ${GREEN}sudo scripts/install-wifi-drivers.sh${NC}"
else
    INSTALL_ALL=false
    if [[ $DRIVER_CHOICE =~ [Aa] ]]; then
        INSTALL_ALL=true
        print_status "Installing ALL WiFi adapter drivers (this may take 10-15 minutes)..."
    else
        print_status "Installing selected WiFi adapter drivers..."
    fi
    
    # RTL8188EU/RTL8188EUS (TP-Link TL-WN722N v2/v3, many cheap adapters)
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 1 ]]; then
        if ! lsmod | grep -q 8188eu; then
            echo -e "${BLUE}[1/8] Installing RTL8188EU driver...${NC}"
            cd /tmp
            rm -rf rtl8188eus 2>/dev/null
            if git clone --depth 1 https://github.com/aircrack-ng/rtl8188eus.git; then
                cd rtl8188eus
                if make -j$(nproc) && make install; then
                    print_success "RTL8188EU driver installed"
                else
                    print_warning "RTL8188EU driver compilation failed (non-critical)"
                fi
                cd /tmp && rm -rf rtl8188eus
            else
                print_warning "Failed to download RTL8188EU driver"
            fi
        else
            echo -e "${GREEN}[1/8] RTL8188EU driver already present${NC}"
        fi
    fi

    # Realtek RTL8812AU/RTL8821AU (Alfa AWUS036ACH, AWUS036AC, many dual-band adapters)
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 2 ]]; then
        if ! lsmod | grep -q 8812au; then
            echo -e "${BLUE}[2/8] Installing RTL8812AU driver...${NC}"
            cd /tmp
            rm -rf rtl8812au 2>/dev/null
            if git clone --depth 1 https://github.com/aircrack-ng/rtl8812au.git; then
                cd rtl8812au
                if make -j$(nproc) && make install; then
                    print_success "RTL8812AU driver installed"
                else
                    print_warning "RTL8812AU driver compilation failed (non-critical)"
                fi
                cd /tmp && rm -rf rtl8812au
            else
                print_warning "Failed to download RTL8812AU driver"
            fi
        else
            echo -e "${GREEN}[2/8] RTL8812AU driver already present${NC}"
        fi
    fi

    # Realtek RTL8814AU (Alfa AWUS1900, high-power adapters)
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 3 ]]; then
        if ! lsmod | grep -q 8814au; then
            echo -e "${BLUE}[3/8] Installing RTL8814AU driver...${NC}"
            cd /tmp
            rm -rf rtl8814au 2>/dev/null
            if git clone --depth 1 https://github.com/aircrack-ng/rtl8814au.git; then
                cd rtl8814au
                if make -j$(nproc) && make install; then
                    print_success "RTL8814AU driver installed"
                else
                    print_warning "RTL8814AU driver compilation failed (non-critical)"
                fi
                cd /tmp && rm -rf rtl8814au
            else
                print_warning "Failed to download RTL8814AU driver"
            fi
        else
            echo -e "${GREEN}[3/8] RTL8814AU driver already present${NC}"
        fi
    fi

    # Realtek RTL8822BU
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 4 ]]; then
        if ! lsmod | grep -q 8822bu; then
            echo -e "${BLUE}[4/8] Installing RTL8822BU driver...${NC}"
            cd /tmp
            rm -rf 88x2bu-20210702 2>/dev/null
            if git clone --depth 1 https://github.com/morrownr/88x2bu-20210702.git; then
                cd 88x2bu-20210702
                if make -j$(nproc) && make install; then
                    print_success "RTL8822BU driver installed"
                else
                    print_warning "RTL8822BU driver compilation failed (non-critical)"
                fi
                cd /tmp && rm -rf 88x2bu-20210702
            else
                print_warning "Failed to download RTL8822BU driver"
            fi
        else
            echo -e "${GREEN}[4/8] RTL8822BU driver already present${NC}"
        fi
    fi

    # Realtek RTL8821CU
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 5 ]]; then
        if ! lsmod | grep -q 8821cu; then
            echo -e "${BLUE}[5/8] Installing RTL8821CU driver...${NC}"
            cd /tmp
            rm -rf 8821cu 2>/dev/null
            if git clone --depth 1 https://github.com/brektrou/rtl8821CU.git 8821cu; then
                cd 8821cu
                if make -j$(nproc) && make install; then
                    print_success "RTL8821CU driver installed"
                else
                    print_warning "RTL8821CU driver compilation failed (non-critical)"
                fi
                cd /tmp && rm -rf 8821cu
            else
                print_warning "Failed to download RTL8821CU driver"
            fi
        else
            echo -e "${GREEN}[5/8] RTL8821CU driver already present${NC}"
        fi
    fi

    # MediaTek MT7612U (Alfa AWUS036ACM, Panda PAU0D)
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 6 ]]; then
        if ! lsmod | grep -q mt76x2u; then
            echo -e "${BLUE}[6/8] Installing MT7612U driver...${NC}"
            cd /tmp
            rm -rf mt7612u 2>/dev/null
            if git clone --depth 1 https://github.com/aircrack-ng/rtl8812au.git mt7612u; then
                cd mt7612u
                if make -j$(nproc) && make install; then
                    print_success "MT7612U driver installed"
                else
                    print_warning "MT7612U driver compilation failed (non-critical)"
                fi
                cd /tmp && rm -rf mt7612u
            else
                print_warning "Failed to download MT7612U driver"
            fi
        else
            echo -e "${GREEN}[6/8] MT7612U driver already present${NC}"
        fi
    fi

    # Ralink RT5370 (Built into many adapters, usually works but may need update)
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 7 ]]; then
        if ! lsmod | grep -q rt2800usb; then
            echo -e "${BLUE}[7/8] Loading RT5370 driver...${NC}"
            modprobe rt2800usb
            print_success "RT5370 driver loaded"
        else
            echo -e "${GREEN}[7/8] RT5370 driver already present${NC}"
        fi
    fi

    # Atheros AR9271 (TP-Link TL-WN722N v1)
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 8 ]]; then
        if ! lsmod | grep -q ath9k_htc; then
            echo -e "${BLUE}[8/8] Loading AR9271 driver...${NC}"
            modprobe ath9k_htc
            print_success "AR9271 driver loaded"
        else
            echo -e "${GREEN}[8/8] AR9271 driver already present${NC}"
        fi
    fi

    print_success "WiFi adapter driver installation complete"
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}⚠️  IMPORTANT: WiFi Drivers Require Reboot${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}New WiFi drivers have been compiled and installed.${NC}"
    echo -e "${YELLOW}The drivers will NOT work until you reboot the system.${NC}"
    echo ""
    echo -e "${BLUE}Installation will continue, but plan to reboot after completion:${NC}"
    echo -e "  ${GREEN}sudo reboot${NC}"
    echo ""
    read -p "Press ENTER to continue installation..." 
fi

# Prepare installation directory
print_status "Preparing installation directory..."

# Get the project root directory (parent of scripts/)
# Multiple fallback methods to ensure we find it
if [ -n "${BASH_SOURCE[0]}" ] && [[ "${BASH_SOURCE[0]}" == */* ]]; then
    # Method 1: BASH_SOURCE with full path
    SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
    SCRIPT_DIR="$(dirname "$(dirname "$SCRIPT_PATH")")"
elif [ -f "$PWD/install.sh" ]; then
    # Method 2: Running from scripts/ directory
    SCRIPT_DIR="$(dirname "$PWD")"
elif [ -f "$PWD/scripts/install.sh" ]; then
    # Method 3: Running from project root
    SCRIPT_DIR="$PWD"
else
    # Method 4: Search for PenDonn directory structure
    SEARCH_DIR="$PWD"
    while [ "$SEARCH_DIR" != "/" ]; do
        if [ -f "$SEARCH_DIR/requirements.txt" ] && [ -d "$SEARCH_DIR/core" ]; then
            SCRIPT_DIR="$SEARCH_DIR"
            break
        fi
        SEARCH_DIR="$(dirname "$SEARCH_DIR")"
    done
fi

# Verify we found the project root
if [ -z "$SCRIPT_DIR" ] || [ ! -f "$SCRIPT_DIR/requirements.txt" ]; then
    echo -e "${RED}ERROR: Cannot locate project root directory!${NC}"
    echo -e "${YELLOW}Please run this script from the PenDonn directory:${NC}"
    echo -e "  ${GREEN}cd ~/PenDonn${NC}"
    echo -e "  ${GREEN}sudo bash scripts/install.sh${NC}"
    echo ""
    echo -e "${BLUE}Current directory: $PWD${NC}"
    echo -e "${BLUE}Script path: ${BASH_SOURCE[0]}${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Found project root: $SCRIPT_DIR${NC}"
echo -e "${BLUE}Target directory: $INSTALL_DIR${NC}"

# Backup existing data if installation exists
if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}Found existing installation, backing up data...${NC}"
    mkdir -p /tmp/pendonn_backup
    [ -d "$INSTALL_DIR/data" ] && cp -r "$INSTALL_DIR/data" /tmp/pendonn_backup/ 2>/dev/null || true
    [ -d "$INSTALL_DIR/logs" ] && cp -r "$INSTALL_DIR/logs" /tmp/pendonn_backup/ 2>/dev/null || true
    [ -d "$INSTALL_DIR/handshakes" ] && cp -r "$INSTALL_DIR/handshakes" /tmp/pendonn_backup/ 2>/dev/null || true
    
    # Completely remove old installation
    echo -e "${YELLOW}Removing old installation...${NC}"
    chmod -R 755 "$INSTALL_DIR" 2>/dev/null || true
    rm -rf "$INSTALL_DIR"
    echo -e "${GREEN}Old installation removed${NC}"
fi

# Create fresh installation directory
echo -e "${BLUE}Creating installation directory...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$INSTALL_DIR/plugins"
mkdir -p "$INSTALL_DIR/handshakes"
mkdir -p "$INSTALL_DIR/config"

# Restore backed up data
if [ -d "/tmp/pendonn_backup" ]; then
    echo -e "${BLUE}Restoring backed-up data...${NC}"
    [ -d "/tmp/pendonn_backup/data" ] && cp -r /tmp/pendonn_backup/data/* "$INSTALL_DIR/data/" 2>/dev/null || true
    [ -d "/tmp/pendonn_backup/logs" ] && cp -r /tmp/pendonn_backup/logs/* "$INSTALL_DIR/logs/" 2>/dev/null || true
    [ -d "/tmp/pendonn_backup/handshakes" ] && cp -r /tmp/pendonn_backup/handshakes/* "$INSTALL_DIR/handshakes/" 2>/dev/null || true
    rm -rf /tmp/pendonn_backup
    echo -e "${GREEN}Data restored${NC}"
fi

print_success "Directory structure created"

# Copy application files
print_status "Copying application files..."
cd "$SCRIPT_DIR"

echo -e "${BLUE}Copying from: $SCRIPT_DIR${NC}"
echo -e "${BLUE}Copying to:   $INSTALL_DIR${NC}"

# Show what we're about to copy
echo -e "${BLUE}Files in source directory:${NC}"
ls -la "$SCRIPT_DIR" | head -20
echo ""
echo -e "${BLUE}Looking for requirements.txt...${NC}"
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    echo -e "${GREEN}✓ requirements.txt found in source${NC}"
else
    echo -e "${RED}✗ requirements.txt NOT found in source!${NC}"
    echo -e "${RED}Current directory: $(pwd)${NC}"
    exit 1
fi
echo ""

if command -v rsync &> /dev/null; then
    echo -e "${BLUE}Using rsync for file copy...${NC}"
    rsync -rlptgoD --exclude='.venv' --exclude='venv' --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='data/' --exclude='logs/' --exclude='handshakes/' --exclude='scripts/' "$SCRIPT_DIR/" "$INSTALL_DIR/"
else
    # Fallback to tar for more reliable copying
    echo -e "${BLUE}Using tar for file copy...${NC}"
    tar --exclude='.venv' --exclude='venv' --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='data' --exclude='logs' --exclude='handshakes' --exclude='scripts' -cf - . | (cd "$INSTALL_DIR" && tar -xf -)
fi

print_success "Files copied"

# List what was copied (for debugging)
echo -e "${BLUE}Verifying copied files:${NC}"
ls -la "$INSTALL_DIR/" | head -20

# Verify requirements.txt exists
if [ ! -f "$INSTALL_DIR/requirements.txt" ]; then
    print_error "requirements.txt not found after copy!"
    print_error "Files in $INSTALL_DIR:"
    ls -la "$INSTALL_DIR/"
    exit 1
fi
print_success "requirements.txt found"

# Create Python virtual environment
print_status "Setting up Python virtual environment..."
cd "$INSTALL_DIR"
python3 -m venv venv
source venv/bin/activate
print_success "Virtual environment created"

# Install Python packages
print_status "Installing Python dependencies (this may take a few minutes)..."
pip install --upgrade pip
echo -e "${YELLOW}Installing packages from requirements.txt...${NC}"
pip install -r requirements.txt
print_success "Python dependencies installed"

# Download rockyou wordlist
print_status "Downloading rockyou.txt wordlist (140MB, may take a while)..."
mkdir -p /usr/share/wordlists
if [ ! -f /usr/share/wordlists/rockyou.txt ]; then
    wget --progress=bar:force https://github.com/brannondorsey/naive-hashcat/releases/download/data/rockyou.txt -O /usr/share/wordlists/rockyou.txt
    print_success "Rockyou wordlist downloaded"
else
    print_success "Rockyou wordlist already exists"
fi

# Set up systemd service for main daemon
print_status "Creating systemd service files..."
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=PenDonn Automated Penetration Testing Daemon
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/main.py
Restart=always
RestartSec=10
StandardOutput=append:$INSTALL_DIR/logs/pendonn.log
StandardError=append:$INSTALL_DIR/logs/pendonn_error.log

[Install]
WantedBy=multi-user.target
EOF

# Set up systemd service for web interface
cat > /etc/systemd/system/${WEB_SERVICE_NAME}.service << EOF
[Unit]
Description=PenDonn Web Interface
After=network.target
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/web/app.py
Restart=always
RestartSec=10
StandardOutput=append:$INSTALL_DIR/logs/web.log
StandardError=append:$INSTALL_DIR/logs/web_error.log

[Install]
WantedBy=multi-user.target
EOF

print_success "Systemd service files created"

# Initialize database
print_status "Initializing database..."
$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/core/database.py --init
print_success "Database initialized"

# Set permissions
print_status "Setting permissions..."
chmod +x "$INSTALL_DIR/main.py"
chmod +x "$INSTALL_DIR/web/app.py"
chmod 600 "$INSTALL_DIR/config/config.json"
print_success "Permissions set"

# Enable services
print_status "Enabling services..."
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}.service
systemctl enable ${WEB_SERVICE_NAME}.service
print_success "Services enabled"

# Interactive Configuration Wizard
echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              Configuration Wizard                              ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Detect WiFi interfaces
print_status "Detecting WiFi interfaces..."
INTERFACES=($(iw dev 2>/dev/null | grep Interface | awk '{print $2}'))
INTERFACE_COUNT=${#INTERFACES[@]}

echo -e "${YELLOW}Detected WiFi interfaces:${NC}"
for i in "${!INTERFACES[@]}"; do
    echo "  $((i+1)). ${INTERFACES[$i]}"
done
echo ""

if [ "$INTERFACE_COUNT" -lt 3 ]; then
    print_warning "Only $INTERFACE_COUNT interface(s) detected!"
    print_warning "Recommended: 1 onboard WiFi + 2 external WiFi adapters"
    echo ""
fi

# Ask if user wants to configure now
read -p "Would you like to configure PenDonn now? (yes/no): " CONFIGURE_NOW

if [ "$CONFIGURE_NOW" = "yes" ]; then
    echo ""
    echo -e "${GREEN}Starting configuration wizard...${NC}"
    echo ""
    
    CONFIG_FILE="$INSTALL_DIR/config/config.json"
    
    # WiFi Interface Configuration
    echo -e "${BLUE}[1/5] WiFi Interface Configuration${NC}"
    echo -e "${YELLOW}You need 3 WiFi interfaces:${NC}"
    echo "  1. Management interface (keeps network/SSH working)"
    echo "  2. Monitor interface (scans for networks)"
    echo "  3. Attack interface (captures handshakes)"
    echo ""
    
    if [ "$INTERFACE_COUNT" -ge 3 ]; then
        echo -e "${YELLOW}Available interfaces:${NC}"
        for i in "${!INTERFACES[@]}"; do
            echo "  $((i+1)). ${INTERFACES[$i]}"
        done
        echo ""
        
        # Management interface
        read -p "Select MANAGEMENT interface (1-$INTERFACE_COUNT) [1]: " MGMT_CHOICE
        MGMT_CHOICE=${MGMT_CHOICE:-1}
        MGMT_IFACE=${INTERFACES[$((MGMT_CHOICE-1))]}
        
        # Monitor interface
        read -p "Select MONITOR interface (1-$INTERFACE_COUNT) [2]: " MON_CHOICE
        MON_CHOICE=${MON_CHOICE:-2}
        MON_IFACE=${INTERFACES[$((MON_CHOICE-1))]}
        
        # Attack interface
        read -p "Select ATTACK interface (1-$INTERFACE_COUNT) [3]: " ATK_CHOICE
        ATK_CHOICE=${ATK_CHOICE:-3}
        ATK_IFACE=${INTERFACES[$((ATK_CHOICE-1))]}
        
        echo ""
        echo -e "${GREEN}Selected interfaces:${NC}"
        echo "  Management: $MGMT_IFACE (keeps SSH working)"
        echo "  Monitor:    $MON_IFACE (scans networks)"
        echo "  Attack:     $ATK_IFACE (captures handshakes)"
        
        # Update config file
        sed -i "s/\"management_interface\": \"wlan0\"/\"management_interface\": \"$MGMT_IFACE\"/g" "$CONFIG_FILE"
        sed -i "s/\"monitor_interface\": \"wlan1\"/\"monitor_interface\": \"$MON_IFACE\"/g" "$CONFIG_FILE"
        sed -i "s/\"attack_interface\": \"wlan2\"/\"attack_interface\": \"$ATK_IFACE\"/g" "$CONFIG_FILE"
    else
        print_warning "Not enough interfaces for auto-configuration"
        echo "You'll need to edit config manually later"
    fi
    
    echo ""
    
    # Whitelist Configuration
    echo -e "${BLUE}[2/5] Whitelist Configuration${NC}"
    echo -e "${YELLOW}Add SSIDs to avoid scanning (your home/work networks)${NC}"
    echo ""
    
    WHITELIST_SSIDS=""
    while true; do
        read -p "Enter SSID to whitelist (or press Enter to skip): " SSID
        if [ -z "$SSID" ]; then
            break
        fi
        if [ -z "$WHITELIST_SSIDS" ]; then
            WHITELIST_SSIDS="\"$SSID\""
        else
            WHITELIST_SSIDS="$WHITELIST_SSIDS, \"$SSID\""
        fi
        echo -e "${GREEN}Added: $SSID${NC}"
    done
    
    if [ -n "$WHITELIST_SSIDS" ]; then
        sed -i "s/\"ssids\": \[\]/\"ssids\": [$WHITELIST_SSIDS]/g" "$CONFIG_FILE"
        echo -e "${GREEN}Whitelist configured${NC}"
    else
        echo -e "${YELLOW}No SSIDs whitelisted - will scan ALL networks${NC}"
    fi
    
    echo ""
    
    # Web Interface Configuration
    echo -e "${BLUE}[3/5] Web Interface Configuration${NC}"
    read -p "Enter web interface port [8080]: " WEB_PORT
    WEB_PORT=${WEB_PORT:-8080}
    sed -i "s/\"port\": 8080/\"port\": $WEB_PORT/g" "$CONFIG_FILE"
    
    # Generate random secret key
    SECRET_KEY=$(openssl rand -hex 32)
    sed -i "s/\"secret_key\": \"CHANGE_THIS_SECRET_KEY_IN_PRODUCTION\"/\"secret_key\": \"$SECRET_KEY\"/g" "$CONFIG_FILE"
    echo -e "${GREEN}Web interface configured on port $WEB_PORT${NC}"
    echo -e "${GREEN}Random secret key generated${NC}"
    
    echo ""
    
    # Cracking Configuration
    echo -e "${BLUE}[4/5] Password Cracking Configuration${NC}"
    read -p "Enable auto-cracking after handshake capture? (yes/no) [yes]: " AUTO_CRACK
    AUTO_CRACK=${AUTO_CRACK:-yes}
    if [ "$AUTO_CRACK" = "no" ]; then
        sed -i "s/\"auto_start_cracking\": true/\"auto_start_cracking\": false/g" "$CONFIG_FILE"
        echo -e "${YELLOW}Auto-cracking disabled${NC}"
    else
        echo -e "${GREEN}Auto-cracking enabled${NC}"
    fi
    
    echo ""
    
    # Display Configuration
    echo -e "${BLUE}[5/5] Display Configuration${NC}"
    read -p "Do you have a Waveshare display connected? (yes/no) [no]: " HAS_DISPLAY
    HAS_DISPLAY=${HAS_DISPLAY:-no}
    if [ "$HAS_DISPLAY" = "no" ]; then
        sed -i "s/\"enabled\": true/\"enabled\": false/g" "$CONFIG_FILE"
        echo -e "${YELLOW}Display disabled (headless mode)${NC}"
    else
        echo -e "${GREEN}Display enabled${NC}"
    fi
    
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║          Configuration completed successfully!                ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    # Show configuration summary
    echo -e "${BLUE}Configuration Summary:${NC}"
    echo "  WiFi Interfaces:"
    if [ -n "$MGMT_IFACE" ]; then
        echo "    - Management: $MGMT_IFACE"
        echo "    - Monitor: $MON_IFACE"
        echo "    - Attack: $ATK_IFACE"
    else
        echo "    - Manual configuration needed"
    fi
    echo "  Web Interface: http://<raspberry-pi-ip>:$WEB_PORT"
    if [ -n "$WHITELIST_SSIDS" ]; then
        echo "  Whitelisted SSIDs: Yes"
    else
        echo "  Whitelisted SSIDs: None"
    fi
    echo "  Auto-cracking: $AUTO_CRACK"
    echo "  Display: $HAS_DISPLAY"
    echo ""
    
else
    echo ""
    print_warning "Skipping configuration wizard"
    echo -e "${YELLOW}You'll need to manually edit: $INSTALL_DIR/config/config.json${NC}"
    echo ""
fi

# Installation complete
echo ""
echo -e "${GREEN}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║              Installation Completed Successfully!              ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

echo -e "${BLUE}Installation Directory:${NC} $INSTALL_DIR"
echo -e "${BLUE}Configuration File:${NC} $INSTALL_DIR/config/config.json"
echo -e "${BLUE}Database Location:${NC} $INSTALL_DIR/data/pendonn.db"
echo ""
echo -e "${YELLOW}Important Next Steps:${NC}"
echo -e "1. Edit configuration: ${BLUE}sudo nano $INSTALL_DIR/config/config.json${NC}"
echo -e "2. Configure WiFi interfaces (wlan0, wlan1, wlan2)"
echo -e "3. Add whitelisted SSIDs to avoid scanning"
echo -e "4. Change the web interface secret key"
echo -e "5. ${RED}IMPORTANT:${NC} Starting services will put WiFi in monitor mode"
echo -e "   This will disconnect your SSH session!"
echo ""
echo -e "${YELLOW}Service Management:${NC}"
echo -e "Start services:  ${BLUE}sudo systemctl start $SERVICE_NAME $WEB_SERVICE_NAME${NC}"
echo -e "Stop services:   ${BLUE}sudo systemctl stop $SERVICE_NAME $WEB_SERVICE_NAME${NC}"
echo -e "View logs:       ${BLUE}sudo journalctl -u $SERVICE_NAME -f${NC}"
echo -e "Web interface:   ${BLUE}http://<raspberry-pi-ip>:8080${NC}"
echo ""
echo -e "${YELLOW}⚠️  IMPORTANT: Services are NOT started automatically${NC}"
echo -e "${YELLOW}   This prevents disconnecting your SSH session during install.${NC}"
echo -e "${YELLOW}   When ready, start services manually:${NC}"
echo -e "   ${BLUE}sudo systemctl start $SERVICE_NAME $WEB_SERVICE_NAME${NC}"
echo ""
echo -e "${GREEN}Installation complete! Your WiFi is protected and will work after reboot.${NC}"
echo ""
