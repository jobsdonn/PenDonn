#!/bin/bash
# PenDonn Recovery Watchdog
#
# Independent safety net: if the management WiFi interface drifts into
# monitor mode or loses its IP for too long, restore it. Runs as its own
# systemd unit so even if the main pendonn daemon hangs/crashes, recovery
# still happens.
#
# This is the "drive to the Pi to recover" insurance. It cannot prevent
# every lockout (e.g. driver crash) but it covers the common case of
# pendonn putting the wrong iface in monitor mode and dying.
#
# Reads management iface from /opt/pendonn/config/config.json. Honors the
# safety.armed_override flag — if operator explicitly armed override, the
# watchdog refuses to interfere (they accepted the risk).
#
# Exit codes:
#   0  normal exit (e.g. SIGTERM)
#   2  config missing/unreadable
#   3  required tools missing (jq, ip, iw, dhclient)

set -u

CONFIG_PATH="${PENDONN_CONFIG:-/opt/pendonn/config/config.json}"
CHECK_INTERVAL_SEC="${PENDONN_WATCHDOG_INTERVAL:-30}"
DRIFT_TOLERANCE_SEC="${PENDONN_WATCHDOG_TOLERANCE:-60}"
LOG_TAG="pendonn-watchdog"

log() {
    # journald via logger when running under systemd; stderr otherwise
    if [ -t 2 ] || ! command -v logger >/dev/null 2>&1; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >&2
    else
        logger -t "$LOG_TAG" -- "$*"
    fi
}

require_tool() {
    if ! command -v "$1" >/dev/null 2>&1; then
        log "FATAL: required tool '$1' not found in PATH"
        exit 3
    fi
}

require_tool jq
require_tool ip
require_tool iw

if [ ! -r "$CONFIG_PATH" ]; then
    log "FATAL: cannot read config at $CONFIG_PATH (set PENDONN_CONFIG to override)"
    exit 2
fi

# Operator settings (MACs, allowlist, secret_key) live in config.json.local
# alongside the base config. Read BOTH every iteration and merge — same
# semantics as core/config_loader.py (recursive object merge, local wins).
# Without this the watchdog would target whatever the unpopulated base
# config says (default: wlan0) and could try to "restore" the actual
# monitor iface, killing the daemon's capture.
LOCAL_PATH="${CONFIG_PATH%.json}.json.local"

get_merged_config() {
    if [ -r "$LOCAL_PATH" ]; then
        jq -s '.[0] * .[1]' "$CONFIG_PATH" "$LOCAL_PATH" 2>/dev/null
    else
        cat "$CONFIG_PATH" 2>/dev/null
    fi
}

# Re-read every iteration so config edits take effect without restart.
read_config() {
    local key="$1" default="$2"
    get_merged_config | jq -r --arg d "$default" ".${key} // \$d" 2>/dev/null
}

resolve_management_iface() {
    # Prefer MAC-based resolution; fall back to interface name.
    local cfg mac iface_by_name
    cfg=$(get_merged_config)
    mac=$(echo "$cfg" | jq -r '.wifi.management_mac // ""' 2>/dev/null)
    iface_by_name=$(echo "$cfg" | jq -r '.wifi.management_interface // "wlan0"' 2>/dev/null)

    if [ -n "$mac" ] && [ "$mac" != "null" ]; then
        # Look up iface owning this MAC
        local resolved
        resolved=$(ip -o link show \
                   | awk -v m="${mac,,}" 'tolower($0) ~ m {print $2}' \
                   | tr -d ':' | head -n1)
        if [ -n "$resolved" ]; then
            echo "$resolved"
            return 0
        fi
    fi
    echo "$iface_by_name"
}

iface_mode() {
    iw dev "$1" info 2>/dev/null | awk '/^\ttype/ {print $2; exit}'
}

iface_has_ipv4() {
    ip -4 addr show dev "$1" 2>/dev/null | grep -q 'inet '
}

# Track how long the management iface has been in a bad state. We only
# act after DRIFT_TOLERANCE_SEC of sustained breakage to avoid fighting
# legitimate transient state changes (e.g. dhclient renewing).
no_ip_since=0
wrong_mode_since=0

restore_managed_mode() {
    local iface="$1"
    log "RECOVERY: $iface in wrong mode for >${DRIFT_TOLERANCE_SEC}s; restoring to managed"
    ip link set "$iface" down >/dev/null 2>&1 || true
    iw dev "$iface" set type managed >/dev/null 2>&1 || true
    ip link set "$iface" up >/dev/null 2>&1 || true
    # Trigger DHCP renewal — try common clients in order
    if command -v dhclient >/dev/null 2>&1; then
        dhclient -r "$iface" >/dev/null 2>&1 || true
        dhclient "$iface" >/dev/null 2>&1 &
    elif command -v dhcpcd >/dev/null 2>&1; then
        dhcpcd -n "$iface" >/dev/null 2>&1 || true
    fi
}

renew_dhcp() {
    local iface="$1"
    log "RECOVERY: $iface has no IPv4 for >${DRIFT_TOLERANCE_SEC}s; renewing DHCP"
    if command -v dhclient >/dev/null 2>&1; then
        dhclient -r "$iface" >/dev/null 2>&1 || true
        dhclient "$iface" >/dev/null 2>&1 &
    elif command -v dhcpcd >/dev/null 2>&1; then
        dhcpcd -n "$iface" >/dev/null 2>&1 || true
    fi
}

# Graceful shutdown
trap 'log "watchdog stopping"; exit 0' TERM INT

log "PenDonn recovery watchdog starting (config=$CONFIG_PATH, interval=${CHECK_INTERVAL_SEC}s, tolerance=${DRIFT_TOLERANCE_SEC}s)"

while true; do
    # Re-read armed_override every loop — operator may toggle it
    armed=$(jq -r '.safety.armed_override // false' "$CONFIG_PATH" 2>/dev/null)
    safety_enabled=$(jq -r '.safety.enabled // true' "$CONFIG_PATH" 2>/dev/null)

    if [ "$safety_enabled" = "false" ] || [ "$armed" = "true" ]; then
        # Operator explicitly opted out — sit quietly
        no_ip_since=0
        wrong_mode_since=0
        sleep "$CHECK_INTERVAL_SEC"
        continue
    fi

    iface=$(resolve_management_iface)
    if [ -z "$iface" ]; then
        log "warning: could not resolve management iface from config"
        sleep "$CHECK_INTERVAL_SEC"
        continue
    fi

    # Check 1: iface mode
    mode=$(iface_mode "$iface")
    now=$(date +%s)
    if [ -n "$mode" ] && [ "$mode" != "managed" ]; then
        if [ "$wrong_mode_since" -eq 0 ]; then
            wrong_mode_since=$now
            log "warning: $iface in mode '$mode' (expected 'managed') — watching"
        elif [ $((now - wrong_mode_since)) -ge "$DRIFT_TOLERANCE_SEC" ]; then
            restore_managed_mode "$iface"
            wrong_mode_since=0
        fi
    else
        wrong_mode_since=0
    fi

    # Check 2: iface has IPv4
    if ! iface_has_ipv4 "$iface"; then
        if [ "$no_ip_since" -eq 0 ]; then
            no_ip_since=$now
            log "warning: $iface has no IPv4 — watching"
        elif [ $((now - no_ip_since)) -ge "$DRIFT_TOLERANCE_SEC" ]; then
            renew_dhcp "$iface"
            no_ip_since=0
        fi
    else
        no_ip_since=0
    fi

    sleep "$CHECK_INTERVAL_SEC"
done
