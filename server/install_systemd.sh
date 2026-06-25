#!/usr/bin/env bash
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="esp-remote-build-flash.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"
RUN_USER="${SUDO_USER:-$USER}"

sudo tee "$SERVICE_PATH" >/dev/null <<EOF
[Unit]
Description=ESP Remote Build Flash Server
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${SERVER_DIR}
Environment=ESP_SERVER_BASE_DIR=${SERVER_DIR}
ExecStart=${SERVER_DIR}/start_server.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager
