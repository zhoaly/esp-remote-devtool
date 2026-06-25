#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$1"
OUTPUT_DIR="$2"
PROJECT_NAME="${3:-ESP32_S3_wifi_ble_hub}"
JOB_ID="${4:-manual}"

cd "$PROJECT_DIR"

mkdir -p "$OUTPUT_DIR"

ZIP_NAME="${PROJECT_NAME}_${JOB_ID}_firmware.zip"
ZIP_PATH="${OUTPUT_DIR}/${ZIP_NAME}"

if [ ! -f "build/firmware_merged.bin" ]; then
    echo "ERROR: build/firmware_merged.bin not found"
    exit 1
fi

if [ ! -f "build/bootloader/bootloader.bin" ]; then
    echo "ERROR: bootloader.bin not found"
    exit 1
fi

if [ ! -f "build/partition_table/partition-table.bin" ]; then
    echo "ERROR: partition-table.bin not found"
    exit 1
fi

if [ ! -f "build/flasher_args.json" ]; then
    echo "ERROR: flasher_args.json not found"
    exit 1
fi

if [ ! -f "build/project_description.json" ]; then
    echo "ERROR: project_description.json not found"
    exit 1
fi

APP_BIN="$(find build -maxdepth 1 -name '*.bin' ! -name 'firmware_merged.bin' | head -n 1)"

if [ -z "$APP_BIN" ]; then
    echo "ERROR: app bin not found in build/"
    exit 1
fi

cat > build/flash_readme.txt <<EOF
ESP32-S3 Firmware Package

Project: ${PROJECT_NAME}
Job ID: ${JOB_ID}

Recommended flash command:

python -m esptool --chip esp32s3 -p COM5 -b 460800 --before default-reset --after hard-reset write_flash 0x0 firmware_merged.bin

Replace COM5 with your actual serial port.
EOF

sha256sum build/firmware_merged.bin > build/firmware_merged.sha256

zip -q -j "$ZIP_PATH" \
    build/firmware_merged.bin \
    build/firmware_merged.sha256 \
    build/bootloader/bootloader.bin \
    build/partition_table/partition-table.bin \
    "$APP_BIN" \
    build/flasher_args.json \
    build/project_description.json \
    build/flash_readme.txt

echo "$ZIP_PATH"