#!/usr/bin/env bash
set -euo pipefail

SERVICES=(esp-remote-api.service esp-remote-worker.service esp-remote-migrate.service esp-remote-build-flash.service)

for service in "${SERVICES[@]}"; do
    sudo systemctl disable --now "$service" 2>/dev/null || true
    sudo rm -f "/etc/systemd/system/${service}"
done
sudo systemctl daemon-reload
echo "Removed ESP Remote systemd services"
