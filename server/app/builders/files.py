from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path


def is_managed_path(path: Path, roots: tuple[Path, ...]) -> bool:
    resolved = path.expanduser().resolve()
    return any(resolved == root.resolve() or root.resolve() in resolved.parents for root in roots)


def remove_managed_path(path: Path, roots: tuple[Path, ...]) -> None:
    if not is_managed_path(path, roots):
        raise RuntimeError(f"Refusing to remove unmanaged path: {path}")
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slug_name(value: str, fallback: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "").strip("._-")
    return slug or fallback


def find_esp_project_root(workspace: Path) -> Path:
    candidates: list[tuple[int, Path]] = []
    for cmake in workspace.rglob("CMakeLists.txt"):
        project_dir = cmake.parent
        if (project_dir / "main").is_dir() or (project_dir / "components").is_dir():
            candidates.append((len(project_dir.relative_to(workspace).parts), project_dir))
    if not candidates:
        raise RuntimeError("ESP-IDF project root not found")
    return min(candidates, key=lambda item: item[0])[1]


def find_lvgl_project_root(workspace: Path) -> Path:
    if (workspace / "CMakeLists.txt").is_file():
        return workspace
    ignored = {"build", "build_web", ".git", ".pio", "managed_components"}
    candidates: list[tuple[int, Path]] = []
    for cmake in workspace.rglob("CMakeLists.txt"):
        project_dir = cmake.parent
        relative = project_dir.relative_to(workspace)
        if any(part in ignored for part in relative.parts):
            continue
        candidates.append((len(relative.parts), project_dir))
    if not candidates:
        raise RuntimeError("LVGL CMake project root not found")
    return min(candidates, key=lambda item: item[0])[1]
