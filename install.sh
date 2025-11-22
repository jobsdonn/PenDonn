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
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    aircrack-ng \
    john \
    hashcat \
    nmap \
    tcpdump \
    wireless-tools \
    net-tools \
    iw \
    macchanger \
    hcxtools \
    hcxdumptool \
    git \
    sqlite3 \
    hostapd \
    dnsmasq \
    nginx
print_success "System dependencies installed"

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
cp -r "$(dirname "$0")"/* "$INSTALL_DIR/"
print_success "Files copied"

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

# Configure WiFi interfaces
print_status "Detecting WiFi interfaces..."
INTERFACES=$(iw dev | grep Interface | awk '{print $2}')
INTERFACE_COUNT=$(echo "$INTERFACES" | wc -l)

echo -e "${YELLOW}Detected WiFi interfaces:${NC}"
echo "$INTERFACES" | nl

if [ "$INTERFACE_COUNT" -lt 3 ]; then
    print_warning "Less than 3 WiFi interfaces detected!"
    print_warning "You need: 1 onboard WiFi + 2 external WiFi adapters"
    print_warning "Please configure interfaces manually in $INSTALL_DIR/config/config.json"
else
    print_success "Sufficient WiFi interfaces detected"
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
echo ""
echo -e "${YELLOW}Service Management:${NC}"
echo -e "Start services:  ${BLUE}sudo systemctl start $SERVICE_NAME $WEB_SERVICE_NAME${NC}"
echo -e "Stop services:   ${BLUE}sudo systemctl stop $SERVICE_NAME $WEB_SERVICE_NAME${NC}"
echo -e "View logs:       ${BLUE}sudo journalctl -u $SERVICE_NAME -f${NC}"
echo -e "Web interface:   ${BLUE}http://<raspberry-pi-ip>:8080${NC}"
echo ""
echo -e "${GREEN}Starting services now...${NC}"
systemctl start ${SERVICE_NAME}.service
systemctl start ${WEB_SERVICE_NAME}.service

sleep 2

if systemctl is-active --quiet ${SERVICE_NAME}.service; then
    print_success "PenDonn daemon is running"
else
    print_error "PenDonn daemon failed to start. Check logs: journalctl -u $SERVICE_NAME"
fi

if systemctl is-active --quiet ${WEB_SERVICE_NAME}.service; then
    print_success "Web interface is running"
else
    print_error "Web interface failed to start. Check logs: journalctl -u $WEB_SERVICE_NAME"
fi

echo ""
echo -e "${GREEN}Happy (legal) hacking! 🔒${NC}"
echo ""
