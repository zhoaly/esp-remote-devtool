from __future__ import annotations

import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from app.builders.archive import ArchiveValidationError, safe_extract_zip


def test_safe_extract_rejects_sibling_prefix_escape(settings, tmp_path: Path) -> None:
    archive = tmp_path / "escape.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../job-escape/payload.txt", "bad")

    with pytest.raises(ArchiveValidationError, match="Unsafe archive path"):
        safe_extract_zip(archive, tmp_path / "job", settings)
    assert not (tmp_path / "job-escape" / "payload.txt").exists()


def test_safe_extract_enforces_uncompressed_limit(settings, tmp_path: Path) -> None:
    archive = tmp_path / "large.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("large.bin", b"x" * 32)

    limited = replace(settings, max_archive_uncompressed_size=16)
    with pytest.raises(ArchiveValidationError, match="uncompressed size"):
        safe_extract_zip(archive, tmp_path / "output", limited)


def test_safe_extract_writes_valid_archive(settings, tmp_path: Path) -> None:
    archive = tmp_path / "valid.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("project/main/source.c", "int main(void) { return 0; }")

    destination = tmp_path / "output"
    safe_extract_zip(archive, destination, settings)
    assert (destination / "project" / "main" / "source.c").is_file()
