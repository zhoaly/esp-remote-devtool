from __future__ import annotations

import subprocess
import sys

from flash_helper import download_artifact_zip, extract_artifact


def flash_firmware(artifact_url: str, com_port: str, baud: int, chip: str) -> dict[str, object]:
    if not com_port.upper().startswith("COM"):
        raise ValueError("Invalid COM port")

    work_dir, zip_path = download_artifact_zip(artifact_url)
    firmware_path = extract_artifact(zip_path, work_dir)

    command = [
        sys.executable,
        "-m",
        "esptool",
        "--chip",
        chip,
        "-p",
        com_port,
        "-b",
        str(baud),
        "--before",
        "default-reset",
        "--after",
        "hard-reset",
        "write_flash",
        "0x0",
        str(firmware_path),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=180,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stdout)

    return {
        "status": "success",
        "message": "Flash success",
        "com_port": com_port,
        "baud": baud,
        "log": result.stdout,
    }
