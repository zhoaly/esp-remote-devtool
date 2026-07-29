from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
import shutil

import requests


def download_artifact_zip(artifact_url: str) -> tuple[Path, Path]:
    work_dir = Path(tempfile.mkdtemp(prefix="esp_flash_"))
    zip_path = work_dir / "firmware.zip"

    try:
        response = requests.get(artifact_url, timeout=120)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Failed to download artifact: {response.status_code} {response.text}"
            )

        zip_path.write_bytes(response.content)
        return work_dir, zip_path
    except BaseException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


def extract_artifact(zip_path: Path, work_dir: Path) -> Path:
    with zipfile.ZipFile(zip_path, "r") as archive:
        root = work_dir.resolve()
        for member in archive.infolist():
            destination = (work_dir / member.filename).resolve()
            if not destination.is_relative_to(root):
                raise RuntimeError(
                    f"Unsafe path in firmware archive: {member.filename}"
                )
        archive.extractall(work_dir)

    firmware_path = work_dir / "firmware_merged.bin"
    if not firmware_path.exists():
        raise RuntimeError("firmware_merged.bin not found in artifact zip")

    return firmware_path
