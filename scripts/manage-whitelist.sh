#!/bin/bash

###############################################################################
# PenDonn Whitelist Manager
# Add/remove SSIDs from the attack whitelist
###############################################################################

CONFIG_FILE="/opt/pendonn/config/config.json"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

show_usage() {
    echo -e "${BLUE}PenDonn Whitelist Manager${NC}"
    echo ""
    echo "Usage: $0 [command] [ssid]"
    echo ""
    echo "Commands:"
    echo "  list              - Show current whitelist"
    echo "  add <ssid>        - Add SSID to whitelist"
    echo "  remove <ssid>     - Remove SSID from whitelist"
    echo "  clear             - Clear entire whitelist (attack ALL networks)"
    echo "  scan              - Show nearby networks you can add"
    echo ""
    echo "Examples:"
    echo "  $0 list"
    echo "  $0 add \"TestNetwork\""
    echo "  $0 remove \"TestNetwork\""
    echo "  $0 scan"
}

list_whitelist() {
    echo -e "${BLUE}Current Whitelist:${NC}"
    python3 -c "
import json
with open('$CONFIG_FILE') as f:
    config = json.load(f)
    ssids = config['whitelist']['ssids']
    if ssids:
        for ssid in ssids:
            print(f'  ✓ {ssid}')
    else:
        print('  ${YELLOW}(empty - will attack ALL networks!)${NC}')
"
}

add_ssid() {
    local ssid="$1"
    if [ -z "$ssid" ]; then
        echo -e "${RED}Error: SSID required${NC}"
        echo "Usage: $0 add \"NetworkName\""
        exit 1
    fi
    
    python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)

if '$ssid' in config['whitelist']['ssids']:
    print('${YELLOW}$ssid is already in whitelist${NC}')
else:
    config['whitelist']['ssids'].append('$ssid')
    with open('$CONFIG_FILE', 'w') as f:
        json.dump(config, f, indent=2)
    print('${GREEN}✓ Added $ssid to whitelist${NC}')
"
}

remove_ssid() {
    local ssid="$1"
    if [ -z "$ssid" ]; then
        echo -e "${RED}Error: SSID required${NC}"
        echo "Usage: $0 remove \"NetworkName\""
        exit 1
    fi
    
    python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)

if '$ssid' in config['whitelist']['ssids']:
    config['whitelist']['ssids'].remove('$ssid')
    with open('$CONFIG_FILE', 'w') as f:
        json.dump(config, f, indent=2)
    print('${GREEN}✓ Removed $ssid from whitelist${NC}')
else:
    print('${YELLOW}$ssid is not in whitelist${NC}')
"
}

clear_whitelist() {
    echo -e "${YELLOW}WARNING: This will clear the whitelist - PenDonn will attack ALL networks!${NC}"
    read -p "Are you sure? (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
        python3 -c "
import json
with open('$CONFIG_FILE', 'r') as f:
    config = json.load(f)
config['whitelist']['ssids'] = []
with open('$CONFIG_FILE', 'w') as f:
    json.dump(config, f, indent=2)
print('${GREEN}✓ Whitelist cleared${NC}')
"
    else
        echo "Cancelled"
    fi
}

scan_networks() {
    echo -e "${BLUE}Scanning for nearby networks...${NC}"
    echo ""
    sudo nmcli dev wifi list | head -20
    echo ""
    echo -e "${YELLOW}Tip: Copy SSID and add with: $0 add \"NetworkName\"${NC}"
}

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}Error: Config file not found: $CONFIG_FILE${NC}"
    exit 1
fi

# Parse command
case "$1" in
    list)
        list_whitelist
        ;;
    add)
        add_ssid "$2"
        list_whitelist
        ;;
    remove)
        remove_ssid "$2"
        list_whitelist
        ;;
    clear)
        clear_whitelist
        ;;
    scan)
        scan_networks
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
