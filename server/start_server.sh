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
export ESP_SERVER_IPV6_PROXY="${ESP_SERVER_IPV6_PROXY:-0}"

PYTHON_BIN="$SERVER_DIR/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

UVICORN_PID=""
IPV6_PROXY_STARTED=0

stop_children() {
    if [ -n "$UVICORN_PID" ] && kill -0 "$UVICORN_PID" 2>/dev/null; then
        kill "$UVICORN_PID" 2>/dev/null || true
        wait "$UVICORN_PID" 2>/dev/null || true
    fi

    if [ "$IPV6_PROXY_STARTED" = "1" ]; then
        "$SERVER_DIR/scripts/manage_ipv6_proxy.sh" stop >/dev/null 2>&1 || true
    fi
}

trap stop_children INT TERM

if [ "$ESP_SERVER_IPV6_PROXY" = "1" ]; then
    "$SERVER_DIR/scripts/manage_ipv6_proxy.sh" stop >/dev/null 2>&1 || true
    "$SERVER_DIR/scripts/manage_ipv6_proxy.sh" start
    IPV6_PROXY_STARTED=1
fi

"$PYTHON_BIN" -m uvicorn app.app:app \
    --app-dir "$SERVER_DIR" \
    --host "$ESP_SERVER_HOST" \
    --port "$ESP_SERVER_PORT" &

UVICORN_PID=$!
wait "$UVICORN_PID"
STATUS=$?

if [ "$IPV6_PROXY_STARTED" = "1" ]; then
    "$SERVER_DIR/scripts/manage_ipv6_proxy.sh" stop >/dev/null 2>&1 || true
fi

exit "$STATUS"
