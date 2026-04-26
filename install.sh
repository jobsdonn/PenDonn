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
WEBUI_SERVICE_NAME="pendonn-webui"
WATCHDOG_SERVICE_NAME="pendonn-watchdog"

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
agreement=$(echo "$agreement" | tr '[:upper:]' '[:lower:]')
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
    smbclient \
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
    jq \
    isc-dhcp-client \
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
            smbclient \
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
                    modprobe 8188eu 2>/dev/null || true
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
                    modprobe 8812au 2>/dev/null || true
                    print_success "RTL8812AU/RTL8821AU driver installed"
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
                    modprobe 8814au 2>/dev/null || true
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
                    modprobe 88x2bu 2>/dev/null || true
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
                    modprobe 8821cu 2>/dev/null || true
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
    # MT7612U is in-tree since kernel 4.2 as mt76x2u. If the module is missing,
    # install mt76 from morrownr's repo (the canonical out-of-tree source).
    if [[ $INSTALL_ALL == true ]] || [[ $DRIVER_CHOICE =~ 6 ]]; then
        if ! lsmod | grep -q mt76x2u; then
            echo -e "${BLUE}[6/9] Installing MT7612U driver...${NC}"
            cd /tmp
            rm -rf mt76 2>/dev/null
            if git clone --depth 1 https://github.com/morrownr/mt76.git mt76; then
                cd mt76
                if make -j$(nproc) && make install && modprobe mt76x2u 2>/dev/null; then
                    print_success "MT7612U (mt76x2u) driver installed"
                else
                    print_warning "MT7612U driver compilation failed (non-critical)"
                fi
                cd /tmp && rm -rf mt76
            else
                print_warning "Failed to download MT7612U driver (non-critical)"
            fi
        else
            echo -e "${GREEN}[6/9] MT7612U driver already present (mt76x2u)${NC}"
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
                    modprobe 8852au 2>/dev/null || true
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
    # Trigger kernel to re-enumerate USB devices so newly loaded modules
    # can pick up adapters that were already plugged in before the driver existed.
    print_status "Re-enumerating USB devices..."
    udevadm trigger --action=add 2>/dev/null || true
    sleep 3
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

# Idempotent install: NEVER touch operator data on re-run.
#
# The earlier backup-to-/tmp + rm -rf + restore dance was fragile (any
# interruption between rm and restore = lost handshakes). New behavior:
#   - data/, logs/, handshakes/ are never deleted; rsync excludes them.
#   - Application code (core/, webui/, plugins/, scripts/, config/, *.py)
#     is rsynced into place, replacing whatever was there.
#   - config/config.json.local is preserved (excluded from rsync) so the
#     operator's secret_key + basic_auth + interface MACs survive re-runs.
echo -e "${BLUE}Source directory: $SCRIPT_DIR${NC}"
echo -e "${BLUE}Target directory: $INSTALL_DIR${NC}"

mkdir -p "$INSTALL_DIR" "$INSTALL_DIR/data" "$INSTALL_DIR/logs" \
         "$INSTALL_DIR/plugins" "$INSTALL_DIR/handshakes" "$INSTALL_DIR/config"

print_success "Directory structure ready"

# Copy application files
print_status "Copying application files..."
cd "$SCRIPT_DIR"

# Common exclusions: dev artefacts + operator state.
# scripts/ IS copied — recovery-watchdog.sh is referenced by the systemd unit.
RSYNC_EXCLUDES=(
    --exclude='.venv'
    --exclude='venv'
    --exclude='.git'
    --exclude='__pycache__'
    --exclude='*.pyc'
    --exclude='data/'
    --exclude='logs/'
    --exclude='handshakes/'
    --exclude='config/config.json.local'
)

if command -v rsync &> /dev/null; then
    echo -e "${BLUE}Using rsync for file copy...${NC}"
    rsync -rlptgoD "${RSYNC_EXCLUDES[@]}" "$SCRIPT_DIR/" "$INSTALL_DIR/"
else
    echo -e "${BLUE}Using tar for file copy...${NC}"
    tar --exclude='.venv' --exclude='venv' --exclude='.git' \
        --exclude='__pycache__' --exclude='*.pyc' --exclude='data' \
        --exclude='logs' --exclude='handshakes' \
        --exclude='config/config.json.local' \
        -cf - . | (cd "$INSTALL_DIR" && tar -xf -)
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

# Download rockyou wordlist
print_status "Downloading rockyou.txt wordlist (140MB, may take a while)..."
mkdir -p /usr/share/wordlists
if [ ! -f /usr/share/wordlists/rockyou.txt ]; then
    if wget --progress=bar:force https://github.com/brannondorsey/naive-hashcat/releases/download/data/rockyou.txt \
            -O /usr/share/wordlists/rockyou.txt 2>/dev/null; then
        print_success "Rockyou wordlist downloaded"
    else
        rm -f /usr/share/wordlists/rockyou.txt
        print_warning "Rockyou download failed (network issue or URL changed)."
        print_warning "Install manually later: wget <url> -O /usr/share/wordlists/rockyou.txt"
        print_warning "Cracking will work once rockyou.txt is in place."
    fi
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

# Set up systemd service for the FastAPI/HTMX web UI (port 8081)
cat > /etc/systemd/system/${WEBUI_SERVICE_NAME}.service << EOF
[Unit]
Description=PenDonn Web UI (FastAPI+HTMX, port 8081)
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

# Recovery watchdog: independent unit that flips the management iface
# back from monitor → managed every 30s if anything escapes SSHGuard.
# Last-resort lockout protection (see scripts/recovery-watchdog.sh).
cat > /etc/systemd/system/${WATCHDOG_SERVICE_NAME}.service << EOF
[Unit]
Description=PenDonn Recovery Watchdog (SSH lockout last-resort)
After=network.target

[Service]
Type=simple
User=root
ExecStart=/bin/bash $INSTALL_DIR/scripts/recovery-watchdog.sh
Restart=always
RestartSec=15
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pendonn-watchdog

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
chmod +x "$INSTALL_DIR/scripts/recovery-watchdog.sh"
chmod 600 "$INSTALL_DIR/config/config.json"
# config.json.local holds the web secret_key + basic_auth password_hash.
# Lock it down so nobody can tail it.
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
#   3. Then `sudo systemctl enable --now pendonn pendonn-webui pendonn-watchdog`
# Service unit files ARE installed and `start`/`stop`/`restart` work.
print_success "Service unit files installed (NOT enabled — see post-install instructions)"

# Interactive Configuration Wizard
echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              Configuration Wizard                              ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Detect WiFi interfaces — retry loop so user can plug in adapters without
# restarting the installer after driver installation.
print_status "Detecting WiFi interfaces..."
while true; do
    INTERFACES=($(iw dev 2>/dev/null | grep Interface | awk '{print $2}'))
    INTERFACE_COUNT=${#INTERFACES[@]}

    echo -e "${YELLOW}Detected WiFi interfaces ($INTERFACE_COUNT):${NC}"
    for i in "${!INTERFACES[@]}"; do
        IFACE="${INTERFACES[$i]}"
        MAC=$(cat /sys/class/net/$IFACE/address 2>/dev/null || echo "unknown")
        echo "  $((i+1)). $IFACE  ($MAC)"
    done
    echo ""

    if [ "$INTERFACE_COUNT" -ge 3 ]; then
        break
    fi

    echo -e "${YELLOW}Need at least 3 interfaces (1 onboard + 2 USB adapters).${NC}"
    echo ""
    echo "  [Enter]  Plug in your USB adapters now and press Enter to re-scan"
    echo "  [s]      Skip — configure interfaces later via the web UI"
    echo ""
    read -rp "> " _IFACE_WAIT
    if [[ "$_IFACE_WAIT" =~ ^[Ss] ]]; then
        print_warning "Interface configuration skipped — set via web UI after boot"
        break
    fi
    # Try to load common modules and re-enumerate USB before next scan
    for _mod in 8812au 8821au 8188eu 8814au 88x2bu 8821cu 8852au rt2800usb ath9k_htc mt76x2u; do
        modprobe "$_mod" 2>/dev/null || true
    done
    udevadm trigger --action=add 2>/dev/null || true
    sleep 3
    echo ""
done

# Ask if user wants to configure now
read -p "Would you like to configure PenDonn now? (yes/no): " CONFIGURE_NOW

if [ "$CONFIGURE_NOW" = "yes" ]; then
    echo ""
    echo -e "${GREEN}Starting configuration wizard...${NC}"
    echo ""
    
    CONFIG_FILE="$INSTALL_DIR/config/config.json"
    LOCAL_FILE="${CONFIG_FILE}.local"

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
        
        # Interface selection loop — re-prompts on duplicate choice
        while true; do
            if [ -n "$ONBOARD_IDX" ]; then
                read -p "Select MANAGEMENT interface (1-$INTERFACE_COUNT) [$ONBOARD_IDX (onboard WiFi - keeps SSH)]: " MGMT_CHOICE
                MGMT_CHOICE=${MGMT_CHOICE:-$ONBOARD_IDX}
            else
                read -p "Select MANAGEMENT interface (1-$INTERFACE_COUNT) [$INTERFACE_COUNT (last interface)]: " MGMT_CHOICE
                MGMT_CHOICE=${MGMT_CHOICE:-$INTERFACE_COUNT}
            fi
            MGMT_IFACE=${INTERFACES[$((MGMT_CHOICE-1))]}

            read -p "Select MONITOR interface   (1-$INTERFACE_COUNT) [1 (scanning)]: " MON_CHOICE
            MON_CHOICE=${MON_CHOICE:-1}
            MON_IFACE=${INTERFACES[$((MON_CHOICE-1))]}

            read -p "Select ATTACK interface    (1-$INTERFACE_COUNT) [2 (handshakes)]: " ATK_CHOICE
            ATK_CHOICE=${ATK_CHOICE:-2}
            ATK_IFACE=${INTERFACES[$((ATK_CHOICE-1))]}

            if [ "$MGMT_IFACE" = "$MON_IFACE" ] || [ "$MGMT_IFACE" = "$ATK_IFACE" ] || [ "$MON_IFACE" = "$ATK_IFACE" ]; then
                print_error "All three interfaces must be different. Please select again."
                echo "  Management: $MGMT_IFACE  Monitor: $MON_IFACE  Attack: $ATK_IFACE"
                echo ""
                continue
            fi
            break
        done
        
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
        
        # Write to .local so git updates never clobber operator settings
        $INSTALL_DIR/venv/bin/python3 -c "
import json, os
local = '$LOCAL_FILE'
overlay = json.load(open(local)) if os.path.isfile(local) else {}
overlay.setdefault('wifi', {})
overlay['wifi']['management_interface'] = '$MGMT_IFACE'
overlay['wifi']['monitor_interface'] = '$MON_IFACE'
overlay['wifi']['attack_interface'] = '$ATK_IFACE'
overlay['wifi']['management_mac'] = '$MGMT_MAC'
overlay['wifi']['monitor_mac'] = '$MON_MAC'
overlay['wifi']['attack_mac'] = '$ATK_MAC'
with open(local, 'w') as f:
    json.dump(overlay, f, indent=2)
os.chmod(local, 0o600)
print('Local config updated: WiFi interfaces and MAC addresses configured')
"
    else
        print_warning "Not enough interfaces for auto-configuration"
        echo "You'll need to edit config manually later"
    fi
    
    echo ""
    
    # Allowlist Configuration (Phase 2A: was "whitelist", inverted semantics)
    echo -e "${BLUE}[2/5] Allowlist Configuration${NC}"
    echo -e "${YELLOW}Add SSIDs you have permission to attack (strict mode by default).${NC}"
    echo -e "${YELLOW}If you leave this empty, the daemon does PASSIVE SCAN ONLY — no attacks.${NC}"
    echo ""

    ALLOWLIST_SSIDS=""
    while true; do
        read -p "Enter authorized SSID (or press Enter to finish): " SSID
        if [ -z "$SSID" ]; then
            break
        fi
        if [ -z "$ALLOWLIST_SSIDS" ]; then
            ALLOWLIST_SSIDS="\"$SSID\""
        else
            ALLOWLIST_SSIDS="$ALLOWLIST_SSIDS, \"$SSID\""
        fi
        echo -e "${GREEN}Added: $SSID${NC}"
    done

    # Always write allowlist (with strict=true) so the daemon has a defined
    # safe state. Empty list + strict=true = no attacks; the operator can
    # add SSIDs later via the web UI's Settings page.
    $INSTALL_DIR/venv/bin/python3 -c "
import json, os
local = '$LOCAL_FILE'
overlay = json.load(open(local)) if os.path.isfile(local) else {}
ssids = [$ALLOWLIST_SSIDS] if '$ALLOWLIST_SSIDS' else []
overlay['allowlist'] = {'strict': True, 'ssids': ssids}
with open(local, 'w') as f:
    json.dump(overlay, f, indent=2)
os.chmod(local, 0o600)
print(f'Allowlist: strict=true, {len(ssids)} SSID(s)')
"
    if [ -n "$ALLOWLIST_SSIDS" ]; then
        echo -e "${GREEN}Allowlist configured (strict mode)${NC}"
    else
        echo -e "${YELLOW}Empty allowlist + strict mode → daemon will only scan, never attack${NC}"
    fi

    echo ""

    # Web Interface Configuration + Auth
    echo -e "${BLUE}[3/5] Web Interface & Authentication${NC}"
    read -p "Enter web interface port [8081]: " WEB_PORT
    WEB_PORT=${WEB_PORT:-8081}

    echo ""
    echo -e "${YELLOW}Set login credentials for the web UI:${NC}"
    read -p "Username [admin]: " WEB_USER
    WEB_USER=${WEB_USER:-admin}

    while true; do
        read -s -p "Password (min 8 chars): " WEB_PASS
        echo ""
        read -s -p "Confirm password:        " WEB_PASS2
        echo ""
        if [ "$WEB_PASS" != "$WEB_PASS2" ]; then
            print_error "Passwords do not match — try again"
            continue
        fi
        if [ "${#WEB_PASS}" -lt 8 ]; then
            print_error "Password must be at least 8 characters"
            continue
        fi
        break
    done

    # Generate random secret key + hash password via env vars (safe against special chars)
    SECRET_KEY=$(openssl rand -hex 32)
    WEB_PASS="$WEB_PASS" WEB_USER="$WEB_USER" \
    $INSTALL_DIR/venv/bin/python3 -c "
import json, os
from werkzeug.security import generate_password_hash
pw   = os.environ['WEB_PASS']
user = os.environ['WEB_USER']
local = '$LOCAL_FILE'
overlay = json.load(open(local)) if os.path.isfile(local) else {}
overlay.setdefault('web', {})
overlay['web']['port'] = $WEB_PORT
overlay['web']['secret_key'] = '$SECRET_KEY'
overlay['web']['host'] = '0.0.0.0'
overlay['web'].setdefault('basic_auth', {})
overlay['web']['basic_auth']['enabled'] = True
overlay['web']['basic_auth']['username'] = user
overlay['web']['basic_auth']['password_hash'] = generate_password_hash(pw)
with open(local, 'w') as f:
    json.dump(overlay, f, indent=2)
os.chmod(local, 0o600)
print(f'Auth configured: user={user}, password hashed and stored')
"

    echo -e "${GREEN}Web UI configured on port $WEB_PORT with authentication enabled${NC}"
    
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
    
    # Write to .local; also set platform-aware engine order (ARM64 = aircrack-ng first)
    $INSTALL_DIR/venv/bin/python3 -c "
import json, os, platform
local = '$LOCAL_FILE'
overlay = json.load(open(local)) if os.path.isfile(local) else {}
overlay.setdefault('cracking', {})
overlay['cracking']['auto_start_cracking'] = $AUTO_CRACK_VALUE
# On ARM64 (RPi4), hashcat+PoCL segfaults — keep aircrack-ng first
machine = platform.machine().lower()
if machine in ('aarch64', 'armv7l', 'arm'):
    overlay['cracking']['engines'] = ['aircrack-ng', 'hashcat', 'john']
with open(local, 'w') as f:
    json.dump(overlay, f, indent=2)
os.chmod(local, 0o600)
print('Local config updated: auto_start_cracking = ' + str($AUTO_CRACK_VALUE) + ', arch=' + machine)
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
        echo -e "${GREEN}Display enabled — installing Waveshare e-Paper library...${NC}"

        # Install Waveshare e-Paper library (only when display is present)
        cd /tmp
        rm -rf e-Paper
        if git clone --depth 1 https://github.com/waveshare/e-Paper.git 2>&1 | grep -v "^Cloning"; then
            if [ -d "e-Paper/RaspberryPi_JetsonNano/python" ]; then
                cd e-Paper/RaspberryPi_JetsonNano/python
                mkdir -p /usr/local/lib/python3/dist-packages
                if [ -d "lib/waveshare_epd" ]; then
                    cp -r lib/waveshare_epd /usr/local/lib/python3/dist-packages/
                    mkdir -p /usr/local/lib/waveshare_epd
                    cp -r lib/waveshare_epd/* /usr/local/lib/waveshare_epd/
                    [ -f "/usr/local/lib/python3/dist-packages/waveshare_epd/__init__.py" ] \
                        && print_success "Waveshare library copied (system-wide)" \
                        || print_warning "Waveshare __init__.py not found — import may fail"
                fi
                VENV_SITE_PACKAGES=$("$INSTALL_DIR/venv/bin/python3" -c "import site; print(site.getsitepackages()[0])")
                if [ -d "lib/waveshare_epd" ]; then
                    cp -r lib/waveshare_epd "$VENV_SITE_PACKAGES/"
                    [ ! -s "$VENV_SITE_PACKAGES/waveshare_epd/__init__.py" ] \
                        && echo '# Waveshare EPD Library' > "$VENV_SITE_PACKAGES/waveshare_epd/__init__.py"
                    [ -f "$VENV_SITE_PACKAGES/waveshare_epd/epd7in3e.py" ] \
                        && print_success "Waveshare library installed into venv" \
                        || print_warning "epd7in3e.py not found — display will use simulation mode"
                fi
                cd /tmp && rm -rf e-Paper
            else
                print_warning "Unexpected Waveshare repo structure — skipping"
            fi
        else
            print_warning "Could not download Waveshare library — display will use simulation mode"
        fi
        cd "$INSTALL_DIR"
    else
        echo -e "${YELLOW}Display disabled (headless mode)${NC}"
    fi

    # Update .local with Python
    $INSTALL_DIR/venv/bin/python3 -c "
import json, os
local = '$LOCAL_FILE'
overlay = json.load(open(local)) if os.path.isfile(local) else {}
overlay.setdefault('display', {})
overlay['display']['enabled'] = $DISPLAY_ENABLED
with open(local, 'w') as f:
    json.dump(overlay, f, indent=2)
os.chmod(local, 0o600)
print('Local config updated: display.enabled = ' + str($DISPLAY_ENABLED))
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
    echo "  Web UI: http://<raspberry-pi-ip>:$WEB_PORT"
    if [ -n "$ALLOWLIST_SSIDS" ]; then
        echo "  Allowlisted SSIDs: Yes (strict mode)"
    else
        echo "  Allowlisted SSIDs: None (passive-scan only)"
    fi
    echo "  Auto-cracking: $AUTO_CRACK"
    echo "  Display: $HAS_DISPLAY"
    echo ""
    
    # Show actual saved config values for verification (read merged base+local)
    echo -e "${BLUE}Saved Configuration Values:${NC}"
    $INSTALL_DIR/venv/bin/python3 -c "
import json, copy, os
def deep_merge(base, overlay):
    out = copy.deepcopy(base)
    for k, v in overlay.items():
        if k.startswith('_'):
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out
with open('$CONFIG_FILE') as f:
    config = json.load(f)
local = '$LOCAL_FILE'
if os.path.isfile(local):
    with open(local) as f:
        config = deep_merge(config, json.load(f))
print(f\"  auto_start_cracking: {config['cracking']['auto_start_cracking']}\")
print(f\"  display.enabled: {config['display']['enabled']}\")
print(f\"  web.port: {config['web']['port']}\")
print(f\"  allowlist.ssids: {len(config['allowlist']['ssids'])} SSID(s) (strict={config['allowlist'].get('strict', True)})\")
if 'wifi' in config and 'monitor_interface' in config['wifi']:
    print(f\"  monitor_interface: {config['wifi']['monitor_interface']}\")
print(f\"  cracking.engines: {config['cracking'].get('engines', ['aircrack-ng'])}\")
print(f\"  local overlay: {local} ({'found' if os.path.isfile(local) else 'NOT FOUND — settings not saved!'})\")
"
    echo ""
    
else
    echo ""
    print_warning "Skipping configuration wizard"
    echo -e "${YELLOW}You'll need to manually edit: $INSTALL_DIR/config/config.json${NC}"
    echo ""
fi

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

# Configure NetworkManager to not manage monitor/attack interfaces
# Use MAC addresses rather than interface names — USB adapter names shuffle on reboot.
if systemctl is-active --quiet NetworkManager; then
    if [ -n "$MON_MAC" ] && [ -n "$ATK_MAC" ]; then
        NM_UNMANAGED="mac:$MON_MAC;mac:$ATK_MAC"
        echo -e "${BLUE}Configuring NetworkManager to ignore monitor/attack adapters (by MAC)...${NC}"
    else
        NM_UNMANAGED="interface-name:wlan1;interface-name:wlan2"
        echo -e "${BLUE}Configuring NetworkManager to ignore wlan1/wlan2...${NC}"
    fi

    if [ -f /etc/NetworkManager/NetworkManager.conf ]; then
        cp /etc/NetworkManager/NetworkManager.conf /etc/NetworkManager/NetworkManager.conf.backup

        if grep -q "^\[keyfile\]" /etc/NetworkManager/NetworkManager.conf; then
            if ! grep -q "unmanaged-devices" /etc/NetworkManager/NetworkManager.conf; then
                sed -i "/^\[keyfile\]/a unmanaged-devices=$NM_UNMANAGED" /etc/NetworkManager/NetworkManager.conf
            fi
        else
            {
                echo ""
                echo "[keyfile]"
                echo "unmanaged-devices=$NM_UNMANAGED"
            } >> /etc/NetworkManager/NetworkManager.conf
        fi
        print_success "NetworkManager configured (unmanaged: $NM_UNMANAGED)"
    fi
elif [ -f /etc/dhcpcd.conf ]; then
    if [ -n "$MON_MAC" ] && [ -n "$ATK_MAC" ]; then
        echo -e "${BLUE}Configuring dhcpcd to ignore monitor/attack adapters (by MAC)...${NC}"
        DENY_DIRECTIVE="denyinterfaces $MON_MAC $ATK_MAC"
    else
        echo -e "${BLUE}Configuring dhcpcd to ignore wlan1/wlan2...${NC}"
        DENY_DIRECTIVE="denyinterfaces wlan1 wlan2"
    fi
    if ! grep -q "$DENY_DIRECTIVE" /etc/dhcpcd.conf; then
        cp /etc/dhcpcd.conf /etc/dhcpcd.conf.backup
        echo "" >> /etc/dhcpcd.conf
        echo "# PenDonn: Don't manage pentesting interfaces" >> /etc/dhcpcd.conf
        echo "$DENY_DIRECTIVE" >> /etc/dhcpcd.conf
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
echo -e "${BLUE}Running post-install smoke test...${NC}"
SMOKE_PASS=0
SMOKE_FAIL=0

_smoke_ok()  { echo -e "  ${GREEN}✓${NC} $1"; SMOKE_PASS=$((SMOKE_PASS+1)); }
_smoke_err() { echo -e "  ${RED}✗${NC} $1"; SMOKE_FAIL=$((SMOKE_FAIL+1)); }

# Python venv
$INSTALL_DIR/venv/bin/python3 -c "import sys; assert sys.version_info >= (3,9)" 2>/dev/null \
    && _smoke_ok "Python 3.9+ venv OK" || _smoke_err "Python venv broken"

# Config loads without error
$INSTALL_DIR/venv/bin/python3 -c "
import sys; sys.path.insert(0, '$INSTALL_DIR')
from core.config_loader import load_config
c = load_config('$INSTALL_DIR/config/config.json')
assert c.get('system', {}).get('name') == 'PenDonn', 'name mismatch'
" 2>/dev/null && _smoke_ok "config_loader OK" || _smoke_err "config_loader failed — check config.json / config.json.local syntax"

# config.json.local is valid JSON (if it exists)
if [ -f "$INSTALL_DIR/config/config.json.local" ]; then
    $INSTALL_DIR/venv/bin/python3 -c "
import json
with open('$INSTALL_DIR/config/config.json.local') as f:
    json.load(f)
" 2>/dev/null && _smoke_ok "config.json.local is valid JSON" \
    || _smoke_err "config.json.local is INVALID JSON — wizard write may have failed"
else
    _smoke_err "config.json.local not found — wizard may not have run or write failed"
fi

# hcxdumptool
command -v hcxdumptool >/dev/null 2>&1 \
    && _smoke_ok "hcxdumptool $(hcxdumptool --version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')" \
    || _smoke_err "hcxdumptool not found — capture will fail"

# aircrack-ng
command -v aircrack-ng >/dev/null 2>&1 \
    && _smoke_ok "aircrack-ng $(aircrack-ng --version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+')" \
    || _smoke_err "aircrack-ng not found — cracking will fail"

# tcpdump (needed for pcapng→cap conversion)
command -v tcpdump >/dev/null 2>&1 \
    && _smoke_ok "tcpdump present" \
    || _smoke_err "tcpdump not found — pcapng conversion will fail"

# smbclient (needed by SMB vulnerability scanner plugin)
command -v smbclient >/dev/null 2>&1 \
    && _smoke_ok "smbclient present" \
    || _smoke_err "smbclient not found — SMB scanner plugin will fail silently"

echo ""
if [ "$SMOKE_FAIL" -eq 0 ]; then
    echo -e "${GREEN}Smoke test: all $SMOKE_PASS checks passed${NC}"
else
    echo -e "${RED}Smoke test: $SMOKE_FAIL check(s) FAILED, $SMOKE_PASS passed${NC}"
    echo -e "${YELLOW}Fix the issues above before starting services.${NC}"
fi
echo ""

# ── Installation complete ────────────────────────────────────────────────────
echo -e "${GREEN}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║              Installation Completed Successfully!              ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

PI_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo -e "${BLUE}Installation directory:${NC} $INSTALL_DIR"
echo -e "${BLUE}Local config (your settings):${NC} $INSTALL_DIR/config/config.json.local"
echo -e "${BLUE}Database:${NC} $INSTALL_DIR/data/pendonn.db"
echo ""

echo -e "${YELLOW}Next steps:${NC}"
echo -e "1. Verify the allowlist — SSIDs you have permission to attack:"
echo -e "   ${BLUE}sudo nano $INSTALL_DIR/config/config.json.local${NC}"
echo ""
echo -e "2. Start the services (one-shot to test, or enable to persist across reboots):"
echo -e "   One-shot:   ${BLUE}sudo systemctl start $SERVICE_NAME $WEBUI_SERVICE_NAME $WATCHDOG_SERVICE_NAME${NC}"
echo -e "   Persistent: ${BLUE}sudo systemctl enable --now $SERVICE_NAME $WEBUI_SERVICE_NAME $WATCHDOG_SERVICE_NAME${NC}"
echo ""
echo -e "3. Open the web UI in your browser:"
if [ -n "$PI_IP" ]; then
    echo -e "   ${BLUE}http://$PI_IP:${WEB_PORT:-8081}${NC}"
else
    echo -e "   ${BLUE}http://<raspberry-pi-ip>:${WEB_PORT:-8081}${NC}"
fi
echo ""
echo -e "${YELLOW}Useful commands:${NC}"
echo "  • Service status:   sudo systemctl status pendonn pendonn-webui pendonn-watchdog"
echo "  • Live logs:        sudo journalctl -u pendonn -f"
echo "  • Errors only:      sudo journalctl -u pendonn -p err"
echo "  • Restart daemon:   sudo systemctl restart pendonn"
echo ""
echo -e "${RED}IMPORTANT:${NC} The daemon puts the monitor interface into monitor mode."
echo -e "Verify your management interface is correct first — see docs/SAFETY.md."
echo ""
echo -e "${RED}REMINDER: Only use on networks you own or have written permission to test!${NC}"
echo ""
