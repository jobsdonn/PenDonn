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
    echo -e "${BLUE}You can install them later with: ${GREEN}sudo ./install-wifi-drivers.sh${NC}"
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
            git clone https://github.com/aircrack-ng/rtl8188eus.git 2>&1 | grep -v "^Cloning"
            cd rtl8188eus
            make -j$(nproc) > /dev/null 2>&1 && make install
            cd /tmp && rm -rf rtl8188eus
            print_success "RTL8188EU driver installed"
        else
            echo -e "${GREEN}[1/8] RTL8188EU driver already present${NC}"
        fi
    fi

    # Realtek RTL8812AU/RTL8821AU (Alfa AWUS036ACH, AWUS036AC, many dual-band adapters)
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 2 ]]; then
        if ! lsmod | grep -q 8812au; then
            echo -e "${BLUE}[2/8] Installing RTL8812AU driver...${NC}"
            cd /tmp
            git clone https://github.com/aircrack-ng/rtl8812au.git 2>&1 | grep -v "^Cloning"
            cd rtl8812au
            make -j$(nproc) > /dev/null 2>&1 && make install
            cd /tmp && rm -rf rtl8812au
            print_success "RTL8812AU driver installed"
        else
            echo -e "${GREEN}[2/8] RTL8812AU driver already present${NC}"
        fi
    fi

    # Realtek RTL8814AU (Alfa AWUS1900, high-power adapters)
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 3 ]]; then
        if ! lsmod | grep -q 8814au; then
            echo -e "${BLUE}[3/8] Installing RTL8814AU driver...${NC}"
            cd /tmp
            git clone https://github.com/aircrack-ng/rtl8814au.git 2>&1 | grep -v "^Cloning"
            cd rtl8814au
            make -j$(nproc) > /dev/null 2>&1 && make install
            cd /tmp && rm -rf rtl8814au
            print_success "RTL8814AU driver installed"
        else
            echo -e "${GREEN}[3/8] RTL8814AU driver already present${NC}"
        fi
    fi

    # Realtek RTL8822BU
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 4 ]]; then
        if ! lsmod | grep -q 8822bu; then
            echo -e "${BLUE}[4/8] Installing RTL8822BU driver...${NC}"
            cd /tmp
            git clone https://github.com/morrownr/88x2bu-20210702.git 2>&1 | grep -v "^Cloning"
            cd 88x2bu-20210702
            make -j$(nproc) > /dev/null 2>&1 && make install
            cd /tmp && rm -rf 88x2bu-20210702
            print_success "RTL8822BU driver installed"
        else
            echo -e "${GREEN}[4/8] RTL8822BU driver already present${NC}"
        fi
    fi

    # Realtek RTL8821CU
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 5 ]]; then
        if ! lsmod | grep -q 8821cu; then
            echo -e "${BLUE}[5/8] Installing RTL8821CU driver...${NC}"
            cd /tmp
            git clone https://github.com/morrownr/8821cu-20210118.git 2>&1 | grep -v "^Cloning"
            cd 8821cu-20210118
            make -j$(nproc) > /dev/null 2>&1 && make install
            cd /tmp && rm -rf 8821cu-20210118
            print_success "RTL8821CU driver installed"
        else
            echo -e "${GREEN}[5/8] RTL8821CU driver already present${NC}"
        fi
    fi

    # MediaTek MT7612U (Alfa AWUS036ACM, Panda PAU0D)
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 6 ]]; then
        if ! lsmod | grep -q mt76x2u; then
            echo -e "${BLUE}[6/8] Installing MT7612U driver...${NC}"
            cd /tmp
            git clone https://github.com/aircrack-ng/rtl8812au.git 2>&1 | grep -v "^Cloning"
            cd rtl8812au
            make -j$(nproc) > /dev/null 2>&1 && make install
            cd /tmp && rm -rf rtl8812au
            print_success "MT7612U driver installed"
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
fi

# Create installation directory
print_status "Creating installation directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$INSTALL_DIR/plugins"
mkdir -p "$INSTALL_DIR/handshakes"
mkdir -p "$INSTALL_DIR/config"
print_success "Directory structure created"

# Copy files to installation directory
print_status "Copying application files..."
# Get the script's directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Copy files excluding .venv, .git, and __pycache__
echo -e "${BLUE}Source directory: $SCRIPT_DIR${NC}"
echo -e "${BLUE}Target directory: $INSTALL_DIR${NC}"

if command -v rsync &> /dev/null; then
    rsync -av --exclude='.venv' --exclude='venv' --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' ./ "$INSTALL_DIR/"
else
    # Fallback to cp if rsync not available
    print_warning "rsync not found, using cp (this is less reliable)"
    find . -type f -not -path './.venv/*' -not -path './venv/*' -not -path './.git/*' -not -path '*/__pycache__/*' -not -name '*.pyc' -exec cp --parents {} "$INSTALL_DIR/" \;
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
echo -e "${GREEN}Installation complete! Configure before starting services.${NC}"
echo ""
