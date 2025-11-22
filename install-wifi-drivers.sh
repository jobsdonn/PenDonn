#!/bin/bash

###############################################################################
# PenDonn WiFi Adapter Driver Installer
# Installs drivers for popular pentesting WiFi adapters
###############################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║              WiFi Adapter Driver Installer                     ║
║            For Popular Pentesting Adapters                     ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}[ERROR]${NC} Please run as root (use sudo)"
    exit 1
fi

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

# Show detected USB devices
print_status "Detecting USB WiFi adapters..."
echo ""
lsusb | grep -i "wireless\|wifi\|802.11\|wlan\|realtek\|ralink\|atheros\|mediatek" || echo "No obvious WiFi adapters detected via lsusb"
echo ""

# Show current network interfaces
print_status "Current network interfaces:"
iw dev 2>/dev/null || ip link show | grep -i "wlan\|wl"
echo ""

# Install build dependencies
print_status "Installing build dependencies..."
apt-get update -qq

# Detect correct kernel headers package
KERNEL_HEADERS="linux-headers-$(uname -r)"
if apt-cache show raspberrypi-kernel-headers > /dev/null 2>&1; then
    KERNEL_HEADERS="raspberrypi-kernel-headers"
fi

apt-get install -y build-essential dkms $KERNEL_HEADERS bc git 2>&1 | grep -v "^Selecting\|^Preparing\|^Unpacking\|^Setting up\|^Processing"
print_success "Build dependencies installed"

echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}Installing drivers for popular adapters...${NC}"
echo -e "${YELLOW}This may take 10-20 minutes depending on your Pi's speed${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
echo ""

DRIVERS_INSTALLED=0

# 1. Realtek RTL8188EU/RTL8188EUS
# Used in: TP-Link TL-WN722N v2/v3, many budget adapters
print_status "Checking RTL8188EU (TP-Link TL-WN722N v2/v3)..."
if lsusb | grep -iq "0bda:8179"; then
    echo -e "${GREEN}   Device detected: TP-Link TL-WN722N v2/v3 or similar${NC}"
fi
if ! lsmod | grep -q 8188eu; then
    print_status "Installing RTL8188EU driver..."
    cd /tmp
    rm -rf rtl8188eus
    git clone --depth 1 https://github.com/aircrack-ng/rtl8188eus.git
    cd rtl8188eus
    if make -j$(nproc) && make install; then
        print_success "RTL8188EU driver installed"
        ((DRIVERS_INSTALLED++))
    else
        print_error "RTL8188EU driver failed to install"
    fi
    cd /tmp && rm -rf rtl8188eus
else
    print_success "RTL8188EU driver already loaded"
fi
echo ""

# 2. Realtek RTL8812AU/RTL8821AU (most popular for pentesting)
# Used in: Alfa AWUS036ACH, AWUS036AC, Panda PAU09, many dual-band adapters
print_status "Checking RTL8812AU (Alfa AWUS036ACH, dual-band adapters)..."
if lsusb | grep -iq "0bda:8812\|0bda:881a\|0bda:a811"; then
    echo -e "${GREEN}   Device detected: Alfa AWUS036ACH or similar${NC}"
fi
if ! lsmod | grep -q 8812au; then
    print_status "Installing RTL8812AU driver..."
    cd /tmp
    rm -rf rtl8812au
    git clone --depth 1 https://github.com/aircrack-ng/rtl8812au.git
    cd rtl8812au
    if make -j$(nproc) && make install; then
        print_success "RTL8812AU driver installed"
        ((DRIVERS_INSTALLED++))
    else
        print_error "RTL8812AU driver failed to install"
    fi
    cd /tmp && rm -rf rtl8812au
else
    print_success "RTL8812AU driver already loaded"
fi
echo ""

# 3. Realtek RTL8814AU
# Used in: Alfa AWUS1900, high-power long-range adapters
print_status "Checking RTL8814AU (Alfa AWUS1900)..."
if lsusb | grep -iq "0bda:8813"; then
    echo -e "${GREEN}   Device detected: Alfa AWUS1900 or similar${NC}"
fi
if ! lsmod | grep -q 8814au; then
    print_status "Installing RTL8814AU driver..."
    cd /tmp
    rm -rf rtl8814au
    git clone --depth 1 https://github.com/aircrack-ng/rtl8814au.git
    cd rtl8814au
    if make -j$(nproc) && make install; then
        print_success "RTL8814AU driver installed"
        ((DRIVERS_INSTALLED++))
    else
        print_error "RTL8814AU driver failed to install"
    fi
    cd /tmp && rm -rf rtl8814au
else
    print_success "RTL8814AU driver already loaded"
fi
echo ""

# 4. Realtek RTL8822BU
# Used in: Newer dual-band adapters, some TP-Link models
print_status "Checking RTL8822BU (newer dual-band adapters)..."
if lsusb | grep -iq "0bda:b82c"; then
    echo -e "${GREEN}   Device detected: RTL8822BU adapter${NC}"
fi
if ! lsmod | grep -q 88x2bu; then
    print_status "Installing RTL8822BU driver..."
    cd /tmp
    rm -rf rtl88x2bu
    git clone --depth 1 https://github.com/cilynx/rtl88x2bu.git
    cd rtl88x2bu
    if make -j$(nproc) && make install; then
        print_success "RTL8822BU driver installed"
        ((DRIVERS_INSTALLED++))
    else
        print_error "RTL8822BU driver failed to install"
    fi
    cd /tmp && rm -rf rtl88x2bu
else
    print_success "RTL8822BU driver already loaded"
fi
echo ""

# 5. Realtek RTL8811CU/RTL8821CU
# Used in: Many budget dual-band adapters
print_status "Checking RTL8811CU/RTL8821CU (budget dual-band)..."
if lsusb | grep -iq "0bda:c811\|0bda:8811"; then
    echo -e "${GREEN}   Device detected: RTL8811CU adapter${NC}"
fi
if ! lsmod | grep -q 8821cu; then
    print_status "Installing RTL8821CU driver..."
    cd /tmp
    rm -rf rtl8821cu
    git clone --depth 1 https://github.com/morrownr/8821cu-20210916.git rtl8821cu
    cd rtl8821cu
    if ./install-driver.sh; then
        print_success "RTL8821CU driver installed"
        ((DRIVERS_INSTALLED++))
    else
        print_error "RTL8821CU driver failed to install"
    fi
    cd /tmp && rm -rf rtl8821cu
else
    print_success "RTL8821CU driver already loaded"
fi
echo ""

# 6. MediaTek MT7612U
# Used in: Alfa AWUS036ACM, Panda PAU0D
print_status "Checking MT7612U (Alfa AWUS036ACM)..."
if lsusb | grep -iq "0e8d:7612"; then
    echo -e "${GREEN}   Device detected: Alfa AWUS036ACM or similar${NC}"
fi
if ! lsmod | grep -q mt76x2u; then
    print_status "Installing MT7612U driver..."
    # Usually built into kernel, try loading
    if modprobe mt76x2u 2>/dev/null; then
        print_success "MT7612U driver loaded"
        ((DRIVERS_INSTALLED++))
    else
        print_warning "MT7612U driver may need kernel update"
    fi
else
    print_success "MT7612U driver already loaded"
fi
echo ""

# 7. Ralink RT5370
# Used in: TP-Link TL-WN722N v1 (the good old one), many older adapters
print_status "Checking RT5370 (TP-Link TL-WN722N v1)..."
if lsusb | grep -iq "148f:5370"; then
    echo -e "${GREEN}   Device detected: TP-Link TL-WN722N v1 or similar${NC}"
fi
if ! lsmod | grep -q rt2800usb; then
    print_status "Installing RT5370 driver..."
    if modprobe rt2800usb 2>/dev/null; then
        print_success "RT5370 driver loaded"
        ((DRIVERS_INSTALLED++))
    else
        print_warning "RT5370 driver may need kernel update"
    fi
else
    print_success "RT5370 driver already loaded"
fi
echo ""

# 8. Atheros AR9271
# Used in: TP-Link TL-WN722N v1, Alfa AWUS036NHA, many reliable adapters
print_status "Checking AR9271 (Alfa AWUS036NHA)..."
if lsusb | grep -iq "0cf3:9271"; then
    echo -e "${GREEN}   Device detected: Alfa AWUS036NHA or similar${NC}"
fi
if ! lsmod | grep -q ath9k_htc; then
    print_status "Installing AR9271 driver..."
    if modprobe ath9k_htc 2>/dev/null; then
        print_success "AR9271 driver loaded"
        ((DRIVERS_INSTALLED++))
    else
        print_warning "AR9271 driver may need kernel update"
    fi
else
    print_success "AR9271 driver already loaded"
fi
echo ""

# Summary
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Driver installation complete!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

if [ $DRIVERS_INSTALLED -gt 0 ]; then
    print_success "Installed/loaded $DRIVERS_INSTALLED driver(s)"
    echo ""
    print_warning "Please reboot your Raspberry Pi for changes to take effect:"
    echo -e "   ${BLUE}sudo reboot${NC}"
else
    print_warning "No new drivers were installed"
    echo ""
    echo -e "${YELLOW}Possible reasons:${NC}"
    echo -e "1. Drivers already installed"
    echo -e "2. No supported adapters connected"
    echo -e "3. Adapters need different drivers"
fi

echo ""
print_status "After reboot, check interfaces with:"
echo -e "   ${BLUE}iw dev${NC}"
echo -e "   ${BLUE}iwconfig${NC}"
echo ""

print_status "Test monitor mode with:"
echo -e "   ${BLUE}sudo airmon-ng check kill${NC}"
echo -e "   ${BLUE}sudo airmon-ng start wlan1${NC}"
echo ""

print_status "Supported adapters include:"
echo "   ✓ Alfa AWUS036ACH (RTL8812AU) - Highly recommended"
echo "   ✓ Alfa AWUS036NHA (AR9271) - Very reliable"
echo "   ✓ Alfa AWUS036ACM (MT7612U) - Good for 5GHz"
echo "   ✓ Alfa AWUS1900 (RTL8814AU) - High power"
echo "   ✓ TP-Link TL-WN722N v1 (AR9271/RT5370) - Classic"
echo "   ✓ Panda PAU09 (RTL8812AU) - Budget option"
echo ""

echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
echo ""
