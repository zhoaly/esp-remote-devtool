"""Cross-platform server entry point. Run `python manage.py --help`."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import venv
from pathlib import Path

SERVER = Path(__file__).resolve().parent


def venv_python() -> Path:
    return SERVER / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--env-file", type=Path, default=SERVER / ".env")
    result.add_argument("--base-dir", type=Path, help="Server assets and configuration directory")
    result.add_argument("--data-dir", type=Path, help="Persistent runtime data directory")
    result.add_argument(
        "--docker-executable", help="Absolute Docker CLI path for background services"
    )
    commands = result.add_subparsers(dest="command", required=True)
    install = commands.add_parser("install", help="Create a local venv and install dependencies")
    install.add_argument("--dev", action="store_true")
    commands.add_parser("doctor", help="Check dependencies, data access and Linux Docker readiness")
    commands.add_parser("migrate", help="Upgrade the database while the server is stopped")
    start = commands.add_parser("start", help="Run migrations, API and worker together")
    start.add_argument(
        "--skip-docker-check",
        action="store_true",
        help="Allow API use without a ready build engine",
    )
    start.add_argument(
        "--log-file", type=Path, help="Append supervisor and child logs to this file"
    )
    commands.add_parser("stop", help="Gracefully stop a manage.py start instance")
    commands.add_parser("api", help="Run only the API (schema must already be migrated)")
    commands.add_parser("worker", help="Run only the worker (schema must already be migrated)")
    commands.add_parser("ipv6-proxy", help="Run only the optional IPv6 forwarder")
    relocate = commands.add_parser(
        "relocate-data", help="Convert legacy stored paths after moving data"
    )
    relocate.add_argument(
        "--old-root",
        required=True,
        action="append",
        help="Previous data root, repeat for multiple roots",
    )
    relocate.add_argument(
        "--apply", action="store_true", help="Back up and commit; default is a dry run"
    )
    service = commands.add_parser(
        "service-config", help="Generate an OS startup configuration; does not install it"
    )
    service.add_argument("--target", choices=["systemd", "launchd", "windows"], required=True)
    service.add_argument("--output", type=Path, required=True)
    return result


def check_docker() -> dict:
    from app.builders.docker import docker_environment, docker_executable

    result = subprocess.run(
        [docker_executable(), "info", "--format", "{{json .}}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        env=docker_environment(),
    )
    if result.returncode:
        raise RuntimeError(
            "Docker engine unavailable; start Docker and verify its context and proxy settings"
        )
    info = json.loads(result.stdout)
    if info.get("OSType") != "linux":
        raise RuntimeError(
            "Linux containers are required; switch Docker Desktop to Linux containers"
        )
    return {
        key: info.get(key)
        for key in ("OSType", "Architecture", "NCPU", "MemTotal", "ServerVersion")
    }


def doctor(settings) -> int:
    import importlib.metadata
    import tempfile

    report = {
        "system": platform.system(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
    }
    report["data_dir"] = str(settings.data_dir)
    errors = []
    for dependency in (
        "fastapi",
        "sqlalchemy",
        "alembic",
        "filelock",
        "psutil",
        "python-dotenv",
        "uvicorn",
    ):
        try:
            report[dependency] = importlib.metadata.version(dependency)
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"Missing dependency: {dependency}")
    try:
        settings.ensure_directories()
        with tempfile.TemporaryFile(dir=settings.data_dir) as handle:
            handle.write(b"write-check")
        report["data_writable"] = True
    except OSError as exc:
        errors.append(f"Data directory is not writable: {exc}")
    try:
        report["docker"] = check_docker()
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        errors.append(str(exc))
    report["errors"] = errors
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return int(bool(errors))


def main() -> int:
    args = parser().parse_args()
    for name in ("env_file", "base_dir", "data_dir", "output", "log_file"):
        value = getattr(args, name, None)
        if value is not None:
            setattr(args, name, value.expanduser().resolve())
    if sys.version_info < (3, 10):  # noqa: UP036 - bootstrap must explain unsupported interpreters
        raise RuntimeError("Python 3.10 or newer is required")
    if args.command == "install":
        executable = venv_python()
        if not executable.is_file():
            if (SERVER / ".venv/pyvenv.cfg").exists():
                raise RuntimeError(
                    "Existing .venv belongs to another platform or is broken; move it aside and install a fresh environment"
                )
            venv.EnvBuilder(with_pip=True).create(SERVER / ".venv")
        requirement = "requirements-dev.txt" if args.dev else "requirements.txt"
        subprocess.run(
            [str(executable), "-m", "pip", "install", "-r", str(SERVER / requirement)], check=True
        )
        print(f"Installed. Next: {executable} {SERVER / 'manage.py'} doctor")
        return 0
    executable = venv_python()
    # POSIX venv interpreters are symlinks to the global binary: samefile() would
    # incorrectly skip activation. Prefix also handles Windows pythonw.exe.
    if executable.is_file() and Path(sys.prefix).resolve() != (SERVER / ".venv").resolve():
        return subprocess.call([str(executable), str(Path(__file__).resolve()), *sys.argv[1:]])
    from dotenv import load_dotenv

    load_dotenv(args.env_file.resolve(), override=False)
    if args.base_dir:
        os.environ["ESP_SERVER_BASE_DIR"] = str(args.base_dir.resolve())
    if args.data_dir:
        os.environ["ESP_SERVER_DATA_DIR"] = str(args.data_dir.resolve())
    if args.docker_executable:
        os.environ["ESP_DOCKER_EXECUTABLE"] = args.docker_executable
    os.chdir(SERVER)
    from app.core.config import get_settings

    settings = get_settings()
    if args.command == "doctor":
        return doctor(settings)
    if args.command == "start":
        if args.log_file:
            args.log_file.parent.mkdir(parents=True, exist_ok=True)
            handle = args.log_file.open("a", encoding="utf-8", buffering=1)
            sys.stdout = sys.stderr = handle
        if not args.skip_docker_check:
            check_docker()
        from app.runtime import start

        return start(settings)
    if args.command == "stop":
        from app.runtime import request_stop

        request_stop(settings)
    elif args.command == "migrate":
        from app.runtime import migrate
        from filelock import FileLock

        settings.ensure_directories()
        with (
            FileLock(settings.data_dir / "server.lock", timeout=0),
            FileLock(settings.worker_lock_path, timeout=0),
        ):
            migrate()
    elif args.command == "api":
        from app.runtime import serve_api

        serve_api()
    elif args.command == "worker":
        from app.worker import run

        run()
    elif args.command == "ipv6-proxy":
        import runpy

        port = os.getenv("ESP_SERVER_PORT", "8000")
        sys.argv = [
            "ipv6_proxy.py",
            "--listen-port",
            port,
            "--listen-host",
            os.getenv("ESP_SERVER_IPV6_PROXY_HOST", "::"),
            "--target-host",
            os.getenv("ESP_SERVER_IPV6_PROXY_TARGET_HOST", "127.0.0.1"),
            "--target-port",
            os.getenv("ESP_SERVER_IPV6_PROXY_TARGET_PORT", port),
        ]
        runpy.run_path(str(SERVER / "scripts/ipv6_proxy.py"), run_name="__main__")
    elif args.command == "relocate-data":
        from app.storage.portability import relocate_data

        print(json.dumps(relocate_data(settings, args.old_root, apply=args.apply), indent=2))
    elif args.command == "service-config":
        from app.service_config import write_config

        write_config(args.target, args.output.resolve(), args.env_file.resolve(), settings)
        print(f"Generated {args.output}; see docs/server_deploy.md for installation commands")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, ImportError) as exc:
        print(f"Server command failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
