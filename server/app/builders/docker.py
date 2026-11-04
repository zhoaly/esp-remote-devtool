from __future__ import annotations

import csv
import io
import os
import shutil
import sys
from pathlib import Path


def docker_executable() -> str:
    configured = os.getenv("ESP_DOCKER_EXECUTABLE")
    if configured:
        return configured
    found = shutil.which("docker")
    if found:
        return found
    candidates = [
        Path.home() / ".docker/bin/docker",
        Path.home() / ".local/bin/docker",
        Path("/Applications/Docker.app/Contents/Resources/bin/docker"),
        Path(os.getenv("ProgramFiles", "C:/Program Files"))
        / "Docker/Docker/resources/bin/docker.exe",
    ]
    return str(next((p for p in candidates if p.is_file()), Path("docker")))


def bind_mount(source: Path, target: str, *, readonly: bool = False) -> list[str]:
    source = source.expanduser().resolve(strict=True)
    output = io.StringIO(newline="")
    fields = ["type=bind", f"source={source}", f"target={target}"]
    if readonly:
        fields.append("readonly")
    csv.writer(output, lineterminator="").writerow(fields)
    return ["--mount", output.getvalue()]


def docker_environment() -> dict[str, str]:
    """Docker also locates credential helpers through PATH in background sessions."""
    environment = os.environ.copy()
    executable = Path(docker_executable()).expanduser()
    candidates = [
        executable.resolve().parent,
        Path("/Applications/Docker.app/Contents/Resources/bin"),
        Path(os.getenv("ProgramFiles", "C:/Program Files")) / "Docker/Docker/resources/bin",
    ]
    paths = environment.get("PATH", "").split(os.pathsep)
    for directory in candidates:
        if directory.is_dir() and str(directory) not in paths:
            paths.append(str(directory))
    environment["PATH"] = os.pathsep.join(paths)
    return environment


def run_command(name: str, project: Path) -> list[str]:
    args = [docker_executable(), "run", "--rm", "--name", name]
    platform = os.getenv("ESP_DOCKER_PLATFORM", "").strip()
    if platform:
        if platform not in {"linux/amd64", "linux/arm64"}:
            raise ValueError("ESP_DOCKER_PLATFORM must be linux/amd64 or linux/arm64")
        args += ["--platform", platform]
    user = os.getenv("ESP_DOCKER_USER")
    if user is None and sys.platform.startswith("linux"):
        user = f"{os.getuid()}:{os.getgid()}"
    if user:
        args += ["--user", user]
    args += ["-e", "HOME=/tmp", *bind_mount(project, "/project"), "-w", "/project"]
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        value = os.getenv(f"ESP_BUILD_{key}")
        if value:
            args += ["-e", f"{key}={value}", "-e", f"{key.lower()}={value}"]
    return args
