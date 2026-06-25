#!/usr/bin/env bash
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

python3 -m venv "$SERVER_DIR/.venv"
"$SERVER_DIR/.venv/bin/python" -m pip install --upgrade pip
"$SERVER_DIR/.venv/bin/pip" install -r "$SERVER_DIR/requirements.txt"

mkdir -p \
    "$SERVER_DIR/data/uploads" \
    "$SERVER_DIR/data/workspaces" \
    "$SERVER_DIR/data/artifacts" \
    "$SERVER_DIR/data/logs" \
    "$SERVER_DIR/data/jobs"

chmod +x "$SERVER_DIR"/scripts/*.sh

echo "Server environment installed at $SERVER_DIR"
