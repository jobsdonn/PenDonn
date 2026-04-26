#!/bin/bash
# Logs vcgencmd get_throttled every 30 seconds.
# Bit flags in the hex result:
#   0: Under-voltage detected
#   1: Arm frequency capped
#   2: Currently throttled
#   3: Soft temp limit active
#   16: Under-voltage has occurred
#   17: Arm frequency capping has occurred
#   18: Throttling has occurred
#   19: Soft temp limit has occurred
#
# Run: sudo ./undervoltage-monitor.sh >> /var/log/pendonn-throttle.log 2>&1
# Or via systemd: install scripts/pendonn-undervoltage.service

LOG_INTERVAL=30
FLAGFILE=/tmp/undervoltage_monitor_running

if [ -f "$FLAGFILE" ]; then
    echo "Monitor already running (PID $(cat $FLAGFILE))" >&2
    exit 1
fi
echo $$ > "$FLAGFILE"
trap 'rm -f $FLAGFILE' EXIT

while true; do
    THROTTLED=$(vcgencmd get_throttled 2>/dev/null)
    HEX=$(echo "$THROTTLED" | grep -oP '0x[0-9a-fA-F]+')
    if [ -z "$HEX" ]; then
        echo "$(date -Iseconds) WARN vcgencmd unavailable"
    else
        VAL=$((16#${HEX#0x}))
        BITS=""
        [ $((VAL & 0x1))  -ne 0 ] && BITS="${BITS}UNDERVOLTAGE "
        [ $((VAL & 0x2))  -ne 0 ] && BITS="${BITS}FREQ_CAPPED "
        [ $((VAL & 0x4))  -ne 0 ] && BITS="${BITS}THROTTLED "
        [ $((VAL & 0x8))  -ne 0 ] && BITS="${BITS}TEMP_SOFT_LIMIT "
        [ $((VAL & 0x10000)) -ne 0 ] && BITS="${BITS}UNDERVOLTAGE_OCCURRED "
        [ $((VAL & 0x20000)) -ne 0 ] && BITS="${BITS}FREQ_CAPPED_OCCURRED "
        [ $((VAL & 0x40000)) -ne 0 ] && BITS="${BITS}THROTTLED_OCCURRED "
        [ $((VAL & 0x80000)) -ne 0 ] && BITS="${BITS}TEMP_OCCURRED "
        if [ -n "$BITS" ]; then
            echo "$(date -Iseconds) WARN $THROTTLED [$BITS]"
        else
            echo "$(date -Iseconds) OK $THROTTLED"
        fi
    fi
    sleep "$LOG_INTERVAL"
done
