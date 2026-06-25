#!/usr/bin/env bash
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${ESP_SERVER_BASE_DIR:-$SERVER_DIR}/data"
KEEP_DAYS="${1:-7}"

find "$DATA_DIR/uploads" -type f -mtime "+$KEEP_DAYS" -delete
find "$DATA_DIR/artifacts" -type f -mtime "+$KEEP_DAYS" -delete
find "$DATA_DIR/logs" -type f -mtime "+$KEEP_DAYS" -delete
find "$DATA_DIR/jobs" -type f -mtime "+$KEEP_DAYS" -delete
find "$DATA_DIR/workspaces" -mindepth 1 -maxdepth 1 -type d -mtime "+$KEEP_DAYS" -exec rm -rf {} +
