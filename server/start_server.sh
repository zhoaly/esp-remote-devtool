#!/usr/bin/env bash
set -euo pipefail
SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$SERVER_DIR/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then PYTHON_BIN="python3"; fi
exec "$PYTHON_BIN" "$SERVER_DIR/manage.py" start "$@"
