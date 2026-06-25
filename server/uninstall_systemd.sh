#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="esp-remote-build-flash.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

sudo systemctl disable --now "$SERVICE_NAME" || true
sudo rm -f "$SERVICE_PATH"
sudo systemctl daemon-reload
echo "Removed ${SERVICE_NAME}"
