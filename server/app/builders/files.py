from __future__ import annotations

import hashlib
import os
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


_WEB_BUILD_NAMES = {
    "CMakeFiles",
    "_deps",
    ".git",
    "CMakeCache.txt",
    "Makefile",
    "compile_commands.json",
    "build.ninja",
    ".ninja_deps",
    ".ninja_log",
}
_WEB_BUILD_SUFFIXES = {".o", ".obj", ".a", ".lib", ".bc", ".cmake", ".log", ".pc"}


def _runtime_entry(path: Path) -> bool:
    return (
        not path.is_symlink()
        and path.name not in _WEB_BUILD_NAMES
        and path.suffix not in _WEB_BUILD_SUFFIXES
    )


def stage_web_preview(build_dir: Path, output: Path) -> None:
    """Copy the runnable preview, preserving assets but excluding compiler state."""
    if build_dir.is_symlink():
        raise RuntimeError("Refusing to stage a linked WebAssembly build directory")
    candidates = [build_dir, *(build_dir / name for name in ("bin", "dist", "src"))]
    root = next(
        (p for p in candidates if (p / "index.html").is_file() and not p.is_symlink()), None
    )
    if root is None:
        for directory, folders, files in os.walk(build_dir, followlinks=False):
            path = Path(directory)
            folders[:] = sorted(name for name in folders if _runtime_entry(path / name))
            if len(path.relative_to(build_dir).parts) >= 4:
                folders.clear()
            if "index.html" in files and not (path / "index.html").is_symlink():
                root = path
                break
    if root is None:
        raise RuntimeError("LVGL preview index.html not found")
    output.mkdir(parents=True, exist_ok=True)
    for directory, folders, files in os.walk(root, followlinks=False):
        path = Path(directory)
        folders[:] = [name for name in folders if _runtime_entry(path / name)]
        for name in files:
            source = path / name
            if not _runtime_entry(source):
                continue
            target = output / source.relative_to(root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    if not (output / "index.html").is_file():
        raise RuntimeError("LVGL preview index.html is not a regular file")
