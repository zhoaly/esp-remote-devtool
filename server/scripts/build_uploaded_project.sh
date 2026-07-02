#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$1"
PROJECT_NAME="${2:-ESP32_S3_wifi_ble_hub}"
IDF_IMAGE="${3:-espressif/idf:v6.0.1}"
TARGET="${4:-esp32s3}"

if [ ! -d "$PROJECT_DIR" ]; then
    echo "ERROR: project dir not found: $PROJECT_DIR"
    exit 1
fi

if [ ! -f "$PROJECT_DIR/CMakeLists.txt" ]; then
    echo "ERROR: CMakeLists.txt not found in project root: $PROJECT_DIR"
    exit 1
fi

cd "$PROJECT_DIR"

echo "========== ESP Uploaded Project Build =========="
echo "Project dir : $PROJECT_DIR"
echo "Project name: $PROJECT_NAME"
echo "IDF image   : $IDF_IMAGE"
echo "Target      : $TARGET"
echo "================================================"

echo "[1/4] Clean old build directory"
rm -rf build

echo "[2/4] Build project"
docker run --rm -i \
    --user "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -e IDF_GIT_SAFE_DIR='*' \
    -v "$PROJECT_DIR:/project" \
    -w /project \
    "$IDF_IMAGE" \
    idf.py build

echo "[3/4] Merge firmware"
docker run --rm -i \
    --user "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -e IDF_GIT_SAFE_DIR='*' \
    -v "$PROJECT_DIR:/project" \
    -w /project \
    "$IDF_IMAGE" \
    idf.py merge-bin -o firmware_merged.bin -f raw

echo "[4/4] Check firmware"
ls -lh build/firmware_merged.bin

echo "========== Build Finished =========="
