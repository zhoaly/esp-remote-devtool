#!/usr/bin/env bash
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="${SUDO_USER:-$USER}"
MIGRATE_SERVICE="esp-remote-migrate.service"
API_SERVICE="esp-remote-api.service"
WORKER_SERVICE="esp-remote-worker.service"

sudo systemctl disable --now esp-remote-build-flash.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/esp-remote-build-flash.service

sudo tee "/etc/systemd/system/${MIGRATE_SERVICE}" >/dev/null <<EOF
[Unit]
Description=ESP Remote database migration
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=${RUN_USER}
WorkingDirectory=${SERVER_DIR}
Environment=ESP_SERVER_BASE_DIR=${SERVER_DIR}
EnvironmentFile=-${SERVER_DIR}/.env
ExecStart=${SERVER_DIR}/.venv/bin/python -m alembic -c ${SERVER_DIR}/alembic.ini upgrade head
EOF

sudo tee "/etc/systemd/system/${API_SERVICE}" >/dev/null <<EOF
[Unit]
Description=ESP Remote API
After=network.target ${MIGRATE_SERVICE}
Requires=${MIGRATE_SERVICE}

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${SERVER_DIR}
Environment=ESP_SERVER_BASE_DIR=${SERVER_DIR}
Environment=ESP_SERVER_HOST=0.0.0.0
Environment=ESP_SERVER_PORT=8000
EnvironmentFile=-${SERVER_DIR}/.env
ExecStart=${SERVER_DIR}/.venv/bin/python -m uvicorn app.main:app --host \$ESP_SERVER_HOST --port \$ESP_SERVER_PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee "/etc/systemd/system/${WORKER_SERVICE}" >/dev/null <<EOF
[Unit]
Description=ESP Remote persistent build worker
After=network.target docker.service ${MIGRATE_SERVICE}
Requires=docker.service ${MIGRATE_SERVICE}

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${SERVER_DIR}
Environment=ESP_SERVER_BASE_DIR=${SERVER_DIR}
EnvironmentFile=-${SERVER_DIR}/.env
ExecStart=${SERVER_DIR}/.venv/bin/python -m app.worker
Restart=always
RestartSec=5
KillMode=mixed
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl restart "$MIGRATE_SERVICE"
sudo systemctl enable --now "$API_SERVICE" "$WORKER_SERVICE"
sudo systemctl status "$API_SERVICE" "$WORKER_SERVICE" --no-pager
