#!/bin/bash
# Write (or overwrite) all PenDonn systemd unit files.
# Safe to run on every code deploy — idempotent.
# Usage: sudo bash scripts/write-units.sh [install_dir]
#
# Separated from install.sh so that quick rsync deploys can pick up unit
# changes without running the full installer.

set -euo pipefail

INSTALL_DIR="${1:-/opt/pendonn}"
UNIT_DIR="/etc/systemd/system"

cat > "${UNIT_DIR}/pendonn.service" << EOF
[Unit]
Description=PenDonn Automated Penetration Testing Daemon
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pendonn

[Install]
WantedBy=multi-user.target
EOF

cat > "${UNIT_DIR}/pendonn-webui.service" << EOF
[Unit]
Description=PenDonn WebUI (FastAPI/HTMX)
After=network.target pendonn.service

[Service]
Type=simple
User=root
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/uvicorn webui.app:app --host 0.0.0.0 --port 8081
Restart=always
RestartSec=5
TimeoutStopSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pendonn-webui

[Install]
WantedBy=multi-user.target
EOF

cat > "${UNIT_DIR}/pendonn-watchdog.service" << EOF
[Unit]
Description=PenDonn Recovery Watchdog (SSH lockout last-resort)
After=network.target

[Service]
Type=simple
User=root
ExecStart=/bin/bash ${INSTALL_DIR}/scripts/recovery-watchdog.sh
Restart=always
RestartSec=15
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pendonn-watchdog

[Install]
WantedBy=multi-user.target
EOF

cat > "${UNIT_DIR}/pendonn-uvmon.service" << EOF
[Unit]
Description=PenDonn undervoltage / throttle monitor
After=sysinit.target

[Service]
Type=simple
User=root
ExecStart=/bin/bash ${INSTALL_DIR}/scripts/undervoltage-monitor.sh
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pendonn-uvmon

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable pendonn pendonn-webui pendonn-watchdog pendonn-uvmon
echo "Units written and enabled."
