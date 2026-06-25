#!/usr/bin/env bash
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SERVER_DIR/.env" ]; then
    set -a
    . "$SERVER_DIR/.env"
    set +a
fi

export ESP_SERVER_BASE_DIR="${ESP_SERVER_BASE_DIR:-$SERVER_DIR}"
export ESP_SERVER_HOST="${ESP_SERVER_HOST:-0.0.0.0}"
export ESP_SERVER_PORT="${ESP_SERVER_PORT:-8000}"

PYTHON_BIN="$SERVER_DIR/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

exec "$PYTHON_BIN" -m uvicorn app.app:app \
    --app-dir "$SERVER_DIR" \
    --host "$ESP_SERVER_HOST" \
    --port "$ESP_SERVER_PORT"
