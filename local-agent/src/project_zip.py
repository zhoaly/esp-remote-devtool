from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any


def should_exclude(
    path: Path,
    project_root: Path,
    exclude_dir_names: set[str],
    exclude_file_suffixes: set[str],
) -> bool:
    relative_parts = path.relative_to(project_root).parts

    for part in relative_parts:
        if part in exclude_dir_names:
            return True

    return path.is_file() and path.suffix.lower() in exclude_file_suffixes


def validate_project_dir(project_dir: Path) -> None:
    if not project_dir.exists():
        raise ValueError(f"Project path not found: {project_dir}")

    if not project_dir.is_dir():
        raise ValueError(f"Project path is not a directory: {project_dir}")

    if not (project_dir / "CMakeLists.txt").exists():
        raise ValueError("CMakeLists.txt not found in project root")

    has_main = (project_dir / "main").is_dir()
    has_components = (project_dir / "components").is_dir()
    if not has_main and not has_components:
        raise ValueError("main/ or components/ directory not found")


def validate_lvgl_project_dir(project_dir: Path) -> None:
    if not project_dir.exists():
        raise ValueError(f"Project path not found: {project_dir}")

    if not project_dir.is_dir():
        raise ValueError(f"Project path is not a directory: {project_dir}")

    if not (project_dir / "CMakeLists.txt").exists():
        raise ValueError("CMakeLists.txt not found in LVGL project root")


def create_project_zip(
    project_dir: Path,
    exclude_dir_names: set[str],
    exclude_file_suffixes: set[str],
) -> Path:
    temp_dir = Path(tempfile.gettempdir())
    zip_path = temp_dir / f"{project_dir.name}_source_upload.zip"

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in project_dir.rglob("*"):
            if should_exclude(path, project_dir, exclude_dir_names, exclude_file_suffixes):
                continue

            if path.is_file():
                archive.write(path, Path(project_dir.name) / path.relative_to(project_dir))

    return zip_path


def _normalize_relative_dir(value: str) -> Path:
    item = value.strip().replace("\\", "/").strip("/")
    if not item:
        raise ValueError("Empty relative directory")

    relative = Path(item)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Invalid relative directory: {value}")

    return relative


def _unique_relative_dirs(values: list[str]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()

    for value in values:
        if not value or not value.strip():
            continue
        relative = _normalize_relative_dir(value)
        key = relative.as_posix()
        if key not in seen:
            seen.add(key)
            result.append(relative)

    return result


def create_lvgl_ui_package_zip(
    project_dir: Path,
    project_name: str,
    width: int,
    height: int,
    ui_roots: list[str],
    include_dirs: list[str],
    entry_call: str,
    entry_header: str,
    exclude_dir_names: set[str],
    exclude_file_suffixes: set[str],
) -> Path:
    validate_lvgl_project_dir(project_dir)

    source_roots = _unique_relative_dirs(ui_roots)
    include_roots = _unique_relative_dirs(include_dirs)
    package_roots = _unique_relative_dirs([*(root.as_posix() for root in source_roots), *(root.as_posix() for root in include_roots)])

    for relative in package_roots:
        candidate = project_dir / relative
        if not candidate.exists():
            raise ValueError(f"LVGL UI path not found: {relative.as_posix()}")
        if not candidate.is_dir():
            raise ValueError(f"LVGL UI path is not a directory: {relative.as_posix()}")

    manifest: dict[str, Any] = {
        "source_type": "ui_package",
        "project_name": project_name or project_dir.name,
        "width": width,
        "height": height,
        "ui_roots": [item.as_posix() for item in source_roots],
        "include_dirs": [item.as_posix() for item in include_roots],
        "entry_call": entry_call,
        "entry_header": entry_header,
    }

    temp_dir = Path(tempfile.gettempdir())
    zip_path = temp_dir / f"{project_dir.name}_lvgl_ui_upload.zip"

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("lvgl_sim.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        for relative_root in package_roots:
            root = project_dir / relative_root
            for path in root.rglob("*"):
                if should_exclude(path, project_dir, exclude_dir_names, exclude_file_suffixes):
                    continue
                if path.is_file():
                    archive.write(path, path.relative_to(project_dir))

    return zip_path
