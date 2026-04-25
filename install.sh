#!/bin/bash

###############################################################################
# PenDonn - Automated Penetration Testing Tool Installer
# For Raspberry Pi 4/5 with Raspberry Pi OS Trixie
# 
# LEGAL NOTICE: This tool is for authorized penetration testing only.
# Unauthorized access to computer networks is illegal.
###############################################################################

set -e

# CRITICAL: Determine project root FIRST, before any directory changes
INITIAL_PWD="$PWD"
if [ -n "${BASH_SOURCE[0]}" ] && [[ "${BASH_SOURCE[0]}" == */* ]]; then
    # Script has path in it
    SCRIPT_LOCATION="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    SCRIPT_DIR="$SCRIPT_LOCATION"
elif [ -f "$PWD/install.sh" ]; then
    # Running from project root
    SCRIPT_DIR="$PWD"
elif [ -f "$PWD/../install.sh" ]; then
    # Running from subdirectory
    SCRIPT_DIR="$(dirname "$PWD")"
else
    # Search up directory tree
    SEARCH_DIR="$PWD"
    while [ "$SEARCH_DIR" != "/" ]; do
        if [ -f "$SEARCH_DIR/requirements.txt" ] && [ -d "$SEARCH_DIR/core" ]; then
            SCRIPT_DIR="$SEARCH_DIR"
            break
        fi
        SEARCH_DIR="$(dirname "$SEARCH_DIR")"
    done
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

INSTALL_DIR="/opt/pendonn"
SERVICE_NAME="pendonn"
WEB_SERVICE_NAME="pendonn-web"
WEBUI_SERVICE_NAME="pendonn-webui"

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
echo "  9) RTL8852BU      - Realtek 8852BU chipset (Wi-Fi 6)"
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
            echo -e "${BLUE}[1/9] Installing RTL8188EU driver...${NC}"
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
            echo -e "${GREEN}[1/9] RTL8188EU driver already present${NC}"
        fi
    fi

    # Realtek RTL8812AU/RTL8821AU (Alfa AWUS036ACH, AWUS036AC, many dual-band adapters)
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 2 ]]; then
        if ! lsmod | grep -q 8812au; then
            echo -e "${BLUE}[2/9] Installing RTL8812AU driver...${NC}"
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
            echo -e "${GREEN}[2/9] RTL8812AU driver already present${NC}"
        fi
    fi

    # Realtek RTL8814AU (Alfa AWUS1900, high-power adapters)
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 3 ]]; then
        if ! lsmod | grep -q 8814au; then
            echo -e "${BLUE}[3/9] Installing RTL8814AU driver...${NC}"
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
            echo -e "${GREEN}[3/9] RTL8814AU driver already present${NC}"
        fi
    fi

    # Realtek RTL8822BU
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 4 ]]; then
        if ! lsmod | grep -q 8822bu; then
            echo -e "${BLUE}[4/9] Installing RTL8822BU driver...${NC}"
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
            echo -e "${GREEN}[4/9] RTL8822BU driver already present${NC}"
        fi
    fi

    # Realtek RTL8821CU
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 5 ]]; then
        if ! lsmod | grep -q 8821cu; then
            echo -e "${BLUE}[5/9] Installing RTL8821CU driver...${NC}"
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
            echo -e "${GREEN}[5/9] RTL8821CU driver already present${NC}"
        fi
    fi

    # MediaTek MT7612U (Alfa AWUS036ACM, Panda PAU0D)
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 6 ]]; then
        if ! lsmod | grep -q mt76x2u; then
            echo -e "${BLUE}[6/9] Installing MT7612U driver...${NC}"
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
            echo -e "${GREEN}[6/9] MT7612U driver already present${NC}"
        fi
    fi

    # Ralink RT5370 (Built into many adapters, usually works but may need update)
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 7 ]]; then
        if ! lsmod | grep -q rt2800usb; then
            echo -e "${BLUE}[7/9] Loading RT5370 driver...${NC}"
            modprobe rt2800usb
            print_success "RT5370 driver loaded"
        else
            echo -e "${GREEN}[7/9] RT5370 driver already present${NC}"
        fi
    fi

    # Atheros AR9271 (TP-Link TL-WN722N v1)
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 8 ]]; then
        if ! lsmod | grep -q ath9k_htc; then
            echo -e "${BLUE}[8/9] Loading AR9271 driver...${NC}"
            modprobe ath9k_htc
            print_success "AR9271 driver loaded"
        else
            echo -e "${GREEN}[8/9] AR9271 driver already present${NC}"
        fi
    fi

    # Realtek RTL8852AU (Wi-Fi 6)
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 9 ]]; then
        if ! lsmod | grep -q 8852au; then
            echo -e "${BLUE}[9/9] Installing RTL8852AU driver...${NC}"
            cd /tmp
            rm -rf rtl8852au 2>/dev/null
            if git clone --depth 1 https://github.com/lwfinger/rtl8852au.git; then
                cd rtl8852au
                # Create required directory for systemd-sleep scripts
                mkdir -p /usr/lib/systemd/system-sleep
                # Detect architecture and set build parameters
                ARCH=$(uname -m)
                echo -e "${BLUE}Building for architecture: $ARCH${NC}"
                if [[ "$ARCH" == "aarch64" ]] || [[ "$ARCH" == "arm64" ]]; then
                    # ARM64 architecture (Raspberry Pi 4/5)
                    make ARCH=arm64 -j$(nproc) && make ARCH=arm64 install
                else
                    # x86_64 or other architectures
                    make -j$(nproc) && make install
                fi
                if [ $? -eq 0 ]; then
                    print_success "RTL8852AU driver installed"
                else
                    print_warning "RTL8852AU driver compilation failed (non-critical)"
                fi
                cd /tmp && rm -rf rtl8852au
            else
                print_warning "Failed to download RTL8852AU driver"
            fi
        else
            echo -e "${GREEN}[9/9] RTL8852AU driver already present${NC}"
        fi
    fi

    print_success "WiFi adapter driver installation complete"
fi

# Prepare installation directory
print_status "Preparing installation directory..."

# Verify we found the project root
if [ -z "$SCRIPT_DIR" ] || [ ! -f "$SCRIPT_DIR/requirements.txt" ]; then
    print_error "Could not find project root!"
    print_error "Looking for requirements.txt in: ${SCRIPT_DIR:-'(not set)'}"
    print_error "Please run this script from the project directory"
    exit 1
fi

echo -e "${BLUE}Source directory: $SCRIPT_DIR${NC}"
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
ls -la "$SCRIPT_DIR" | head -10

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
pip install --upgrade pip setuptools wheel
echo -e "${YELLOW}Installing packages from requirements.txt...${NC}"
pip install -r requirements.txt
print_success "Python dependencies installed"

# Install Waveshare E-Paper display library
print_status "Installing Waveshare E-Paper display library..."
cd /tmp
if [ -d "e-Paper" ]; then
    rm -rf e-Paper
fi

if git clone --depth 1 https://github.com/waveshare/e-Paper.git 2>&1 | grep -v "^Cloning"; then
    if [ -d "e-Paper/RaspberryPi_JetsonNano/python" ]; then
        cd e-Paper/RaspberryPi_JetsonNano/python
        
        # Copy library to system location for both venv and system Python
        print_status "Copying Waveshare library to /usr/local/lib..."
        mkdir -p /usr/local/lib/python3/dist-packages
        if [ -d "lib/waveshare_epd" ]; then
            # Show what we're about to copy
            echo -e "${BLUE}Files in source lib/waveshare_epd:${NC}"
            ls -la lib/waveshare_epd/ | grep epd7 | head -n 5
            
            # Copy the entire waveshare_epd package directory
            cp -r lib/waveshare_epd /usr/local/lib/python3/dist-packages/
            
            # Also create symbolic link for backward compatibility
            mkdir -p /usr/local/lib/waveshare_epd
            cp -r lib/waveshare_epd/* /usr/local/lib/waveshare_epd/
            
            # Verify __init__.py exists
            if [ -f "/usr/local/lib/python3/dist-packages/waveshare_epd/__init__.py" ]; then
                print_success "Waveshare library files copied with package structure"
            else
                print_warning "Waveshare __init__.py not found - import may fail"
            fi
        else
            print_error "Waveshare library source not found at lib/waveshare_epd"
        fi
        
        # Install into virtual environment's site-packages
        print_status "Installing Waveshare library into virtual environment..."
        source "$INSTALL_DIR/venv/bin/activate"
        
        # Get venv site-packages directory
        VENV_SITE_PACKAGES=$(python3 -c "import site; print(site.getsitepackages()[0])")
        print_status "Target directory: $VENV_SITE_PACKAGES"
        
        if [ -d "lib/waveshare_epd" ]; then
            # Copy the entire package directory (don't pipe to head - it kills the copy!)
            print_status "Copying waveshare_epd package..."
            cp -r lib/waveshare_epd "$VENV_SITE_PACKAGES/" 2>&1 | tail -n 3
            
            # Verify files were copied
            if [ -f "$VENV_SITE_PACKAGES/waveshare_epd/__init__.py" ]; then
                # Check if __init__.py is empty (common issue)
                if [ ! -s "$VENV_SITE_PACKAGES/waveshare_epd/__init__.py" ]; then
                    print_status "Creating minimal __init__.py..."
                    echo '# Waveshare EPD Library' > "$VENV_SITE_PACKAGES/waveshare_epd/__init__.py"
                fi
                print_success "Waveshare library copied to venv site-packages"
                
                # Verify epd7in3e.py was copied
                if [ -f "$VENV_SITE_PACKAGES/waveshare_epd/epd7in3e.py" ]; then
                    print_success "✓ epd7in3e.py found!"
                    print_success "✓ Waveshare display library installed"
                    print_status "Note: Display requires GPIO access and will initialize when service runs"
                else
                    print_error "✗ epd7in3e.py NOT copied! Check disk space and permissions"
                    print_warning "Display will use simulation mode"
                fi
            else
                print_error "Failed to copy Waveshare files to $VENV_SITE_PACKAGES"
            fi
        else
            print_error "Waveshare library source not found at lib/waveshare_epd"
            print_error "Current directory: $(pwd)"
            ls -la lib/ 2>&1 | head -n 10
        fi
        
        deactivate
        
        cd /tmp
        rm -rf e-Paper
    else
        print_warning "Waveshare library structure unexpected, skipping"
    fi
else
    print_warning "Could not download Waveshare library (display will use simulation mode)"
fi

cd "$INSTALL_DIR"

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
# stdout/stderr → journald. The Python app ALSO writes a copy to
# logs/pendonn.log via FileHandler for offline tail; using
# StandardOutput=append: as well would double every line in the file
# (incident debugged 2026-04-25). Journal is the single source of truth
# for live streaming via the new UI's /api/logs/stream endpoint.
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pendonn

[Install]
WantedBy=multi-user.target
EOF

# Set up systemd service for legacy Flask web interface (port 8080)
cat > /etc/systemd/system/${WEB_SERVICE_NAME}.service << EOF
[Unit]
Description=PenDonn Web Interface (legacy Flask, port 8080)
After=network.target pendonn.service
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/web/app.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pendonn-web

[Install]
WantedBy=multi-user.target
EOF

# Set up systemd service for the new FastAPI/HTMX UI (port 8081)
cat > /etc/systemd/system/${WEBUI_SERVICE_NAME}.service << EOF
[Unit]
Description=PenDonn Web UI (modern FastAPI+HTMX, port 8081)
After=network.target pendonn.service
Wants=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PYTHONPATH=$INSTALL_DIR"
ExecStart=$INSTALL_DIR/venv/bin/python3 -m uvicorn webui.app:app --host 0.0.0.0 --port 8081 --no-access-log
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pendonn-webui

[Install]
WantedBy=multi-user.target
EOF

print_success "Systemd service files created"

# Check disk space before initializing database
print_status "Checking available disk space..."
AVAILABLE_KB=$(df "$INSTALL_DIR" | awk 'NR==2 {print $4}')
AVAILABLE_MB=$((AVAILABLE_KB / 1024))
if [ "$AVAILABLE_MB" -lt 100 ]; then
    print_error "Insufficient disk space: ${AVAILABLE_MB}MB available (need 100MB minimum)"
    print_error "Free up space on your SD card and try again"
    exit 1
fi
print_success "Disk space OK: ${AVAILABLE_MB}MB available"

# Ensure data directory exists and has proper permissions
mkdir -p "$INSTALL_DIR/data"
chmod 755 "$INSTALL_DIR/data"

# Initialize database
print_status "Initializing database..."
if $INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/core/database.py --init 2>&1 | tee /tmp/db_init.log; then
    print_success "Database initialized"
else
    print_error "Database initialization failed!"
    echo -e "${RED}Error details:${NC}"
    cat /tmp/db_init.log
    print_error "This could be due to:"
    print_error "  - SD card corruption (run: sudo fsck)"
    print_error "  - Insufficient disk space"
    print_error "  - Filesystem mounted read-only"
    exit 1
fi

# Set permissions
print_status "Setting permissions..."
chmod +x "$INSTALL_DIR/main.py"
chmod +x "$INSTALL_DIR/web/app.py"
chmod 600 "$INSTALL_DIR/config/config.json"
# config.json.local (if generated by web/app.py first run) holds the
# Flask secret_key and basic_auth password_hash. Lock it down too.
[ -f "$INSTALL_DIR/config/config.json.local" ] && \
    chmod 600 "$INSTALL_DIR/config/config.json.local"

# Ensure data directory exists and is writable
mkdir -p "$INSTALL_DIR/data"
chmod 755 "$INSTALL_DIR/data"
chown root:root "$INSTALL_DIR/data"

# Ensure logs directory exists and is writable
mkdir -p "$INSTALL_DIR/logs"
chmod 755 "$INSTALL_DIR/logs"
chown root:root "$INSTALL_DIR/logs"

# SECURITY: lock down the plugins/ directory.
#
# core/plugin_manager.py runs `exec_module()` on every .py inside this
# tree, which means any file dropped here runs as the service user (root).
# The earlier `chmod -R 755` made the whole install group/world-readable
# and left the directory writable by root only — but a leftover plugin
# dropped by an admin via `cp` (without `-p`) would inherit the umask of
# whoever did the copy.
#
# 0700 root:root closes the gap: no other UID can drop a file here, and
# the loader-side ownership check in plugin_manager refuses to exec
# anything not owned by root or our euid. Together they make the common
# accident impossible.
mkdir -p "$INSTALL_DIR/plugins"
chown -R root:root "$INSTALL_DIR/plugins"
chmod 700 "$INSTALL_DIR/plugins"
find "$INSTALL_DIR/plugins" -type d -exec chmod 700 {} \;
find "$INSTALL_DIR/plugins" -type f -exec chmod 600 {} \;

print_success "Permissions set"

# Enable services
print_status "Enabling services..."
systemctl daemon-reload
# Phase 2A: do NOT auto-`enable` the services. The first-boot of a real
# Pi (2026-04-25) showed that systemd would launch the daemon immediately
# after install with whatever default config existed — including an empty
# allowlist that triggered indiscriminate scanning of neighbor APs. The
# operator must now explicitly:
#   1. Configure interfaces + allowlist (web UI > Settings, or edit
#      /opt/pendonn/config/config.json.local)
#   2. Run preflight: `sudo /opt/pendonn/venv/bin/python3 /opt/pendonn/main.py --preflight`
#   3. Then `sudo systemctl enable --now pendonn pendonn-web`
# Service unit files ARE installed and `start`/`stop`/`restart` work.
print_success "Service unit files installed (NOT enabled — see post-install instructions)"

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
            IFACE="${INTERFACES[$i]}"
            MAC=$(cat /sys/class/net/$IFACE/address 2>/dev/null || echo "unknown")
            # Check if this is likely the onboard WiFi (dc:a6:32:* for Pi)
            if [[ $MAC == dc:a6:32:* ]]; then
                echo "  $((i+1)). $IFACE ($MAC) [ONBOARD - recommended for MANAGEMENT]"
            else
                echo "  $((i+1)). $IFACE ($MAC) [USB adapter]"
            fi
        done
        echo ""
        
        # Try to auto-detect the onboard WiFi for management
        ONBOARD_IDX=""
        for i in "${!INTERFACES[@]}"; do
            IFACE="${INTERFACES[$i]}"
            MAC=$(cat /sys/class/net/$IFACE/address 2>/dev/null || echo "unknown")
            if [[ $MAC == dc:a6:32:* ]]; then
                ONBOARD_IDX=$((i+1))
                break
            fi
        done
        
        # Management interface (default to onboard if found, otherwise last interface)
        if [ -n "$ONBOARD_IDX" ]; then
            read -p "Select MANAGEMENT interface (1-$INTERFACE_COUNT) [$ONBOARD_IDX (onboard WiFi - keeps SSH)]: " MGMT_CHOICE
            MGMT_CHOICE=${MGMT_CHOICE:-$ONBOARD_IDX}
        else
            read -p "Select MANAGEMENT interface (1-$INTERFACE_COUNT) [$INTERFACE_COUNT (last interface)]: " MGMT_CHOICE
            MGMT_CHOICE=${MGMT_CHOICE:-$INTERFACE_COUNT}
        fi
        MGMT_IFACE=${INTERFACES[$((MGMT_CHOICE-1))]}
        
        # Monitor interface (default to first USB adapter)
        read -p "Select MONITOR interface (1-$INTERFACE_COUNT) [1 (scanning)]: " MON_CHOICE
        MON_CHOICE=${MON_CHOICE:-1}
        MON_IFACE=${INTERFACES[$((MON_CHOICE-1))]}
        
        # Attack interface (default to second USB adapter)
        read -p "Select ATTACK interface (1-$INTERFACE_COUNT) [2 (handshakes)]: " ATK_CHOICE
        ATK_CHOICE=${ATK_CHOICE:-2}
        ATK_IFACE=${INTERFACES[$((ATK_CHOICE-1))]}
        
        # Validate that all three interfaces are different
        if [ "$MGMT_IFACE" = "$MON_IFACE" ] || [ "$MGMT_IFACE" = "$ATK_IFACE" ] || [ "$MON_IFACE" = "$ATK_IFACE" ]; then
            print_error "ERROR: You must select three DIFFERENT interfaces!"
            echo "  Management: $MGMT_IFACE"
            echo "  Monitor:    $MON_IFACE"
            echo "  Attack:     $ATK_IFACE"
            echo ""
            echo "Please run the installer again and select different interfaces."
            exit 1
        fi
        
        echo ""
        echo -e "${GREEN}Selected interfaces:${NC}"
        echo "  Management: $MGMT_IFACE (keeps SSH working)"
        echo "  Monitor:    $MON_IFACE (scans networks)"
        echo "  Attack:     $ATK_IFACE (captures handshakes)"
        
        # Get MAC addresses for persistent identification
        MGMT_MAC=$(cat /sys/class/net/$MGMT_IFACE/address 2>/dev/null || echo "unknown")
        MON_MAC=$(cat /sys/class/net/$MON_IFACE/address 2>/dev/null || echo "unknown")
        ATK_MAC=$(cat /sys/class/net/$ATK_IFACE/address 2>/dev/null || echo "unknown")
        
        echo ""
        echo -e "${GREEN}MAC addresses (for persistent identification):${NC}"
        echo "  Management: $MGMT_MAC"
        echo "  Monitor:    $MON_MAC"
        echo "  Attack:     $ATK_MAC"
        
        # Update config file with Python (more reliable than sed)
        $INSTALL_DIR/venv/bin/python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
config['wifi']['management_interface'] = '$MGMT_IFACE'
config['wifi']['monitor_interface'] = '$MON_IFACE'
config['wifi']['attack_interface'] = '$ATK_IFACE'
config['wifi']['management_mac'] = '$MGMT_MAC'
config['wifi']['monitor_mac'] = '$MON_MAC'
config['wifi']['attack_mac'] = '$ATK_MAC'
with open('$CONFIG_FILE', 'w') as f:
    json.dump(config, f, indent=2)
print('Config updated: WiFi interfaces and MAC addresses configured')
"
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
        # Update config with Python (proper JSON handling)
        $INSTALL_DIR/venv/bin/python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
ssids = [$WHITELIST_SSIDS]
config['whitelist']['ssids'] = ssids
with open('$CONFIG_FILE', 'w') as f:
    json.dump(config, f, indent=2)
print(f'Config updated: {len(ssids)} SSID(s) whitelisted')
"
        echo -e "${GREEN}Whitelist configured${NC}"
    else
        echo -e "${YELLOW}No SSIDs whitelisted - will scan ALL networks${NC}"
    fi
    
    echo ""
    
    # Web Interface Configuration
    echo -e "${BLUE}[3/5] Web Interface Configuration${NC}"
    read -p "Enter web interface port [8080]: " WEB_PORT
    WEB_PORT=${WEB_PORT:-8080}
    
    # Generate random secret key
    SECRET_KEY=$(openssl rand -hex 32)
    
    # Update config with Python
    $INSTALL_DIR/venv/bin/python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
config['web']['port'] = $WEB_PORT
config['web']['secret_key'] = '$SECRET_KEY'
with open('$CONFIG_FILE', 'w') as f:
    json.dump(config, f, indent=2)
print('Config updated: web.port = $WEB_PORT, secret_key generated')
"
    
    echo -e "${GREEN}Web interface configured on port $WEB_PORT${NC}"
    echo -e "${GREEN}Random secret key generated${NC}"
    
    echo ""
    
    # Cracking Configuration
    echo -e "${BLUE}[4/5] Password Cracking Configuration${NC}"
    read -p "Enable auto-cracking after handshake capture? (yes/no) [yes]: " AUTO_CRACK
    AUTO_CRACK=${AUTO_CRACK:-yes}
    
    # Use Python to update JSON reliably
    AUTO_CRACK_VALUE="True"
    if [ "$AUTO_CRACK" = "no" ]; then
        AUTO_CRACK_VALUE="False"
        echo -e "${YELLOW}Auto-cracking disabled${NC}"
    else
        echo -e "${GREEN}Auto-cracking enabled${NC}"
    fi
    
    # Update config with Python (more reliable than sed for JSON)
    $INSTALL_DIR/venv/bin/python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
config['cracking']['auto_start_cracking'] = $AUTO_CRACK_VALUE
with open('$CONFIG_FILE', 'w') as f:
    json.dump(config, f, indent=2)
print('Config updated: auto_start_cracking = ' + str($AUTO_CRACK_VALUE))
"
    
    echo ""
    
    # Display Configuration
    echo -e "${BLUE}[5/5] Display Configuration${NC}"
    read -p "Do you have a Waveshare display connected? (yes/no) [no]: " HAS_DISPLAY
    HAS_DISPLAY=${HAS_DISPLAY:-no}
    
    # Use Python to update JSON reliably
    DISPLAY_ENABLED="False"
    if [ "$HAS_DISPLAY" = "yes" ]; then
        DISPLAY_ENABLED="True"
        echo -e "${GREEN}Display enabled${NC}"
    else
        echo -e "${YELLOW}Display disabled (headless mode)${NC}"
    fi
    
    # Update config with Python
    $INSTALL_DIR/venv/bin/python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
config['display']['enabled'] = $DISPLAY_ENABLED
with open('$CONFIG_FILE', 'w') as f:
    json.dump(config, f, indent=2)
print('Config updated: display.enabled = ' + str($DISPLAY_ENABLED))
"
    
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║          Configuration completed successfully!                ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    # Verify configuration was saved
    print_status "Verifying configuration..."
    if [ -f "$CONFIG_FILE" ]; then
        CONFIG_SIZE=$(stat -f%z "$CONFIG_FILE" 2>/dev/null || stat -c%s "$CONFIG_FILE" 2>/dev/null)
        if [ "$CONFIG_SIZE" -gt 100 ]; then
            print_success "Configuration file saved successfully ($CONFIG_SIZE bytes)"
        else
            print_warning "Configuration file seems too small, may not have saved correctly"
        fi
    else
        print_error "Configuration file not found at $CONFIG_FILE"
    fi
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
    
    # Show actual saved config values for verification
    echo -e "${BLUE}Saved Configuration Values:${NC}"
    $INSTALL_DIR/venv/bin/python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
print(f\"  auto_start_cracking: {config['cracking']['auto_start_cracking']}\")
print(f\"  display.enabled: {config['display']['enabled']}\")
print(f\"  web.port: {config['web']['port']}\")
print(f\"  whitelist.ssids: {len(config['whitelist']['ssids'])} SSID(s)\")
if 'wifi' in config and 'monitor_interface' in config['wifi']:
    print(f\"  monitor_interface: {config['wifi']['monitor_interface']}\")
"
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
echo -e "${YELLOW}Phase 2A: services are installed but NOT enabled.${NC}"
echo -e "${YELLOW}First, populate the allowlist (SSIDs you have permission to attack):${NC}"
echo -e "   ${BLUE}sudo nano /opt/pendonn/config/config.json.local${NC}"
echo -e "   add: ${BLUE}{ \"allowlist\": { \"strict\": true, \"ssids\": [\"YourTarget1\"] } }${NC}"
echo ""
echo -e "${YELLOW}Then start (one-shot or persistent):${NC}"
echo -e "Run once:        ${BLUE}sudo systemctl start $SERVICE_NAME $WEB_SERVICE_NAME${NC}"
echo -e "Auto-start boot: ${BLUE}sudo systemctl enable --now $SERVICE_NAME $WEB_SERVICE_NAME${NC}"
echo -e "Stop services:   ${BLUE}sudo systemctl stop $SERVICE_NAME $WEB_SERVICE_NAME${NC}"
echo -e "View logs:       ${BLUE}sudo journalctl -u $SERVICE_NAME -f${NC}"
echo -e "Web interface:   ${BLUE}http://<raspberry-pi-ip>:8080${NC}"
echo ""
echo -e "${YELLOW}⚠️  IMPORTANT: Services are NOT started automatically${NC}"
echo -e "${YELLOW}   This prevents disconnecting your SSH session during install.${NC}"
echo -e "${YELLOW}   When ready, start services manually:${NC}"
echo -e "   ${BLUE}sudo systemctl start $SERVICE_NAME $WEB_SERVICE_NAME${NC}"
echo ""

# Configure system to prevent WiFi driver conflicts
print_status "Configuring WiFi driver management..."

# Get wlan0 MAC address for persistent naming
if [ -e /sys/class/net/wlan0/address ]; then
    WLAN0_MAC=$(cat /sys/class/net/wlan0/address)
    
    echo -e "${BLUE}Creating udev rules for persistent interface naming...${NC}"
    cat > /etc/udev/rules.d/70-persistent-wifi.rules << EOF
# Ensure built-in WiFi is always wlan0 (management interface)
SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="$WLAN0_MAC", NAME="wlan0"

# External USB WiFi adapters become wlan1 and wlan2
# These will be used for pentesting (monitor/attack interfaces)
EOF
    print_success "udev rules created"
else
    print_warning "wlan0 not found - skipping udev rules"
fi

# Configure NetworkManager to not manage external interfaces
if systemctl is-active --quiet NetworkManager; then
    echo -e "${BLUE}Configuring NetworkManager to ignore wlan1/wlan2...${NC}"
    
    if [ -f /etc/NetworkManager/NetworkManager.conf ]; then
        cp /etc/NetworkManager/NetworkManager.conf /etc/NetworkManager/NetworkManager.conf.backup
        
        if grep -q "^\[keyfile\]" /etc/NetworkManager/NetworkManager.conf; then
            # Add unmanaged-devices to existing [keyfile] section
            if ! grep -q "unmanaged-devices" /etc/NetworkManager/NetworkManager.conf; then
                sed -i '/^\[keyfile\]/a unmanaged-devices=interface-name:wlan1;interface-name:wlan2' /etc/NetworkManager/NetworkManager.conf
            fi
        else
            # Add new [keyfile] section
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
echo -e "${GREEN}WiFi Driver Protection Configured${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Configuration applied:${NC}"
echo -e "  ✓ wlan0 locked to built-in WiFi (by MAC address)"
echo -e "  ✓ wlan1/wlan2 reserved for external adapters"
echo -e "  ✓ Network manager configured to ignore wlan1/wlan2"
echo ""
echo -e "${BLUE}After reboot:${NC}"
echo -e "  • wlan0 = Your management WiFi (stays connected)"
echo -e "  • wlan1 = Monitor interface (scans networks)"
echo -e "  • wlan2 = Attack interface (captures handshakes)"
echo ""
echo -e "${GREEN}Installation complete! Configure before starting services.${NC}"
echo ""
echo -e "${BLUE}Checking service status...${NC}"
sleep 2
systemctl status pendonn --no-pager -n 10 || true
echo ""
echo -e "${YELLOW}Recent logs (if service started):${NC}"
journalctl -u pendonn -n 30 --no-pager 2>/dev/null || echo "  (No logs yet - service may not have started)"
echo ""
echo -e "${YELLOW}Useful commands:${NC}"
echo "  • Check status:     sudo systemctl status pendonn"
echo "  • View live logs:   sudo journalctl -u pendonn -f"
echo "  • Check errors:     sudo journalctl -u pendonn -p err"
echo "  • Restart service:  sudo systemctl restart pendonn"
echo "  • Web UI:           http://$(hostname -I | awk '{print $1}'):8080"
echo "  • Health check:     cd $INSTALL_DIR && sudo ./check_health.py"
echo "  • Display test:     cd $INSTALL_DIR && sudo ./diagnose_display.py"
echo ""
echo -e "${RED}REMINDER: Only use on networks you own or have permission to test!${NC}"
echo ""
