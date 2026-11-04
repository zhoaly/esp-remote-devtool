from __future__ import annotations

import json
import zipfile
from pathlib import Path

from app.builders.files import is_managed_path, sha256_file


def find_app_bin(project: Path) -> Path:
    build = project / "build"
    description = build / "project_description.json"
    if description.is_file():
        data = json.loads(description.read_text(encoding="utf-8"))
        name = data.get("app_bin") or data.get("project_name")
        if name:
            candidate = build / str(name)
            if candidate.suffix != ".bin":
                candidate = candidate.with_suffix(".bin")
            if candidate.is_file() and is_managed_path(candidate, (build,)):
                return candidate
    candidates = sorted(p for p in build.glob("*.bin") if p.name != "firmware_merged.bin")
    if not candidates:
        raise RuntimeError("Application binary not found")
    candidate = candidates[0]
    if not is_managed_path(candidate, (build,)):
        raise RuntimeError("Application binary escapes the build directory")
    return candidate


def package_firmware(project: Path, output: Path, name: str, job_id: str, target: str) -> Path:
    build = project / "build"
    app = find_app_bin(project)
    files = [
        build / "firmware_merged.bin",
        build / "bootloader/bootloader.bin",
        build / "partition_table/partition-table.bin",
        app,
        build / "flasher_args.json",
        build / "project_description.json",
    ]
    for path in files:
        if not path.is_file() or not is_managed_path(path, (build,)):
            raise RuntimeError(f"Firmware file missing or outside build directory: {path.name}")
    info = {
        "project": name,
        "chip": target,
        "app_bin": app.name,
        "size": app.stat().st_size,
        "sha256": sha256_file(app),
        "job_id": job_id,
    }
    (build / "ota_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    (build / "flash_readme.txt").write_text(
        f"{target} Firmware Package\nProject: {name}\nJob ID: {job_id}\n\n"
        f"python -m esptool --chip {target} -p <SERIAL_PORT> -b 460800 "
        "--before default-reset --after hard-reset write_flash 0x0 firmware_merged.bin\n\n"
        "Replace <SERIAL_PORT> with your device port.\n",
        encoding="utf-8",
    )
    for binary in (build / "firmware_merged.bin", app):
        checksum = build / (
            "firmware_merged.sha256"
            if binary.name == "firmware_merged.bin"
            else f"{binary.name}.sha256"
        )
        checksum.write_text(
            f"{sha256_file(binary)}  {binary.relative_to(project).as_posix()}\n", encoding="utf-8"
        )
        files.append(checksum)
    files += [build / "ota_info.json", build / "flash_readme.txt"]
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f"{name}_{job_id}_firmware.zip"
    temporary = archive.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for path in files:
                package.write(path, path.name)
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)
    return archive
