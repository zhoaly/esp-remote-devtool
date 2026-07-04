#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -f "$SERVER_DIR/.env" ]; then
    set -a
    . "$SERVER_DIR/.env"
    set +a
fi

ESP_SERVER_BASE_DIR="${ESP_SERVER_BASE_DIR:-$SERVER_DIR}"
ESP_SERVER_PORT="${ESP_SERVER_PORT:-8000}"
ESP_SERVER_IPV6_PROXY_HOST="${ESP_SERVER_IPV6_PROXY_HOST:-::}"
ESP_SERVER_IPV6_PROXY_TARGET_HOST="${ESP_SERVER_IPV6_PROXY_TARGET_HOST:-127.0.0.1}"
ESP_SERVER_IPV6_PROXY_TARGET_PORT="${ESP_SERVER_IPV6_PROXY_TARGET_PORT:-$ESP_SERVER_PORT}"
ESP_SERVER_IPV6_PROXY_PIDFILE="${ESP_SERVER_IPV6_PROXY_PIDFILE:-$ESP_SERVER_BASE_DIR/data/esp_remote_ipv6_proxy.pid}"
ESP_SERVER_IPV6_PROXY_LOG="${ESP_SERVER_IPV6_PROXY_LOG:-$ESP_SERVER_BASE_DIR/data/logs/esp_remote_ipv6_proxy.log}"

PYTHON_BIN="$SERVER_DIR/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

is_running() {
    [ -f "$ESP_SERVER_IPV6_PROXY_PIDFILE" ] || return 1
    local pid
    pid="$(cat "$ESP_SERVER_IPV6_PROXY_PIDFILE" 2>/dev/null || true)"
    [ -n "$pid" ] || return 1
    kill -0 "$pid" 2>/dev/null
}

start_proxy() {
    mkdir -p "$(dirname "$ESP_SERVER_IPV6_PROXY_PIDFILE")" "$(dirname "$ESP_SERVER_IPV6_PROXY_LOG")"

    if is_running; then
        echo "IPv6 proxy already running with pid $(cat "$ESP_SERVER_IPV6_PROXY_PIDFILE")"
        return 0
    fi

    rm -f "$ESP_SERVER_IPV6_PROXY_PIDFILE"
    nohup "$PYTHON_BIN" "$SCRIPT_DIR/ipv6_proxy.py" \
        --listen-host "$ESP_SERVER_IPV6_PROXY_HOST" \
        --listen-port "$ESP_SERVER_PORT" \
        --target-host "$ESP_SERVER_IPV6_PROXY_TARGET_HOST" \
        --target-port "$ESP_SERVER_IPV6_PROXY_TARGET_PORT" \
        >>"$ESP_SERVER_IPV6_PROXY_LOG" 2>&1 &

    local pid=$!
    echo "$pid" >"$ESP_SERVER_IPV6_PROXY_PIDFILE"
    sleep 0.5

    if ! kill -0 "$pid" 2>/dev/null; then
        echo "IPv6 proxy failed to start; see $ESP_SERVER_IPV6_PROXY_LOG" >&2
        exit 1
    fi

    echo "IPv6 proxy started with pid $pid"
}

stop_proxy() {
    if ! is_running; then
        rm -f "$ESP_SERVER_IPV6_PROXY_PIDFILE"
        return 0
    fi

    local pid
    pid="$(cat "$ESP_SERVER_IPV6_PROXY_PIDFILE")"
    kill "$pid" 2>/dev/null || true

    for _ in $(seq 1 20); do
        if ! kill -0 "$pid" 2>/dev/null; then
            rm -f "$ESP_SERVER_IPV6_PROXY_PIDFILE"
            return 0
        fi
        sleep 0.2
    done

    kill -9 "$pid" 2>/dev/null || true
    rm -f "$ESP_SERVER_IPV6_PROXY_PIDFILE"
}

case "${1:-start}" in
    start)
        start_proxy
        ;;
    stop)
        stop_proxy
        ;;
    restart)
        stop_proxy
        start_proxy
        ;;
    status)
        if is_running; then
            echo "IPv6 proxy running with pid $(cat "$ESP_SERVER_IPV6_PROXY_PIDFILE")"
        else
            echo "IPv6 proxy not running"
            exit 3
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}" >&2
        exit 2
        ;;
esac
