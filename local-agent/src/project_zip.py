from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path


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
