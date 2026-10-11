from __future__ import annotations

import shutil
import stat
import zipfile
from pathlib import Path

from app.core.config import Settings


class ArchiveValidationError(RuntimeError):
    pass


def safe_extract_zip(zip_path: Path, destination: Path, settings: Settings) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()

    try:
        archive = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile as exc:
        raise ArchiveValidationError("Uploaded file is not a valid zip archive") from exc

    with archive:
        members = archive.infolist()
        if len(members) > settings.max_archive_entries:
            raise ArchiveValidationError("Archive contains too many entries")

        total_size = 0
        validated: list[tuple[zipfile.ZipInfo, Path]] = []
        for member in members:
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ArchiveValidationError(f"Archive links are not allowed: {member.filename}")
            if member.file_size > settings.max_archive_file_size:
                raise ArchiveValidationError(f"Archive entry is too large: {member.filename}")
            total_size += member.file_size
            if total_size > settings.max_archive_uncompressed_size:
                raise ArchiveValidationError("Archive uncompressed size exceeds the configured limit")

            target = (root / member.filename).resolve()
            if target != root and root not in target.parents:
                raise ArchiveValidationError(f"Unsafe archive path: {member.filename}")
            validated.append((member, target))

        for member, target in validated:
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
