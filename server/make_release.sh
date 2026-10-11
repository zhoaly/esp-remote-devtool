#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '\r\n' < "$REPO_ROOT/VERSION")"
OUTPUT_DIR="$REPO_ROOT/release"
ARCHIVE_NAME="esp-remote-build-flash_${VERSION}.tar.gz"

mkdir -p "$OUTPUT_DIR"

tar \
    --exclude=".git" \
    --exclude=".pytest_cache" \
    --exclude="*/__pycache__" \
    --exclude="*.pyc" \
    --exclude="server/.venv" \
    --exclude="server/.env" \
    --exclude="server/data" \
    --exclude="local-agent/.venv" \
    --exclude="local-agent/build" \
    --exclude="local-agent/dist" \
    --exclude="local-agent/release" \
    --exclude="release/*.tar.gz" \
    -czf "$OUTPUT_DIR/$ARCHIVE_NAME" \
    -C "$REPO_ROOT" .

echo "$OUTPUT_DIR/$ARCHIVE_NAME"
