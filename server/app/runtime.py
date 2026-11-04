from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import psutil
from filelock import FileLock, Timeout

from app.core.config import SERVER_DIR, Settings
from app.core.processes import popen_options, terminate_tree


def stop_event(callback: Callable[[], None] | None = None) -> threading.Event:
    event = threading.Event()
    marker = os.getenv("ESP_SERVER_STOP_FILE")
    parent_pid = os.getenv("ESP_SERVER_SUPERVISOR_PID")
    if marker:

        def watch() -> None:
            while not event.wait(0.2):
                if Path(marker).exists() or (parent_pid and not psutil.pid_exists(int(parent_pid))):
                    event.set()
                    if callback:
                        callback()

        threading.Thread(target=watch, name="shutdown-watch", daemon=True).start()
    return event


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(SERVER_DIR / "alembic.ini"))
    command.upgrade(config, "head")


def serve_api() -> None:
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(
            "app.main:app",
            host=os.getenv("ESP_SERVER_HOST", "0.0.0.0"),
            port=int(os.getenv("ESP_SERVER_PORT", "8000")),
        )
    )
    stop_event(lambda: setattr(server, "should_exit", True))
    server.run()


def request_stop(settings: Settings, *, timeout: float = 45) -> None:
    lock = FileLock(settings.data_dir / "server.lock", timeout=0)
    try:
        with lock:
            raise RuntimeError("Server is not running through manage.py start")
    except Timeout:
        pass
    (settings.data_dir / "server.stop").touch()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with lock.acquire(timeout=0):
                return
        except Timeout:
            time.sleep(0.2)
    raise RuntimeError("Server did not stop within the deadline")


def start(settings: Settings) -> int:
    settings.ensure_directories()
    marker = settings.data_dir / "server.stop"
    children: list[subprocess.Popen] = []
    with FileLock(settings.data_dir / "server.lock", timeout=0):
        marker.unlink(missing_ok=True)
        stopping = threading.Event()

        def stop(_signum, _frame) -> None:
            stopping.set()

        previous = {}
        for sig in (signal.SIGINT, signal.SIGTERM, getattr(signal, "SIGBREAK", None)):
            if sig is not None:
                previous[sig] = signal.signal(sig, stop)
        try:
            # Keep the worker lock across migrations, so a standalone worker cannot
            # claim jobs while the schema is changing.
            with FileLock(settings.worker_lock_path, timeout=0):
                migrate()
            env = os.environ.copy()
            env["ESP_SERVER_STOP_FILE"] = str(marker)
            env["ESP_SERVER_SUPERVISOR_PID"] = str(os.getpid())
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONUTF8"] = "1"
            executable = sys.executable
            if Path(executable).name.lower() == "pythonw.exe":
                executable = str(Path(executable).with_name("python.exe"))
            commands = [
                [executable, str(SERVER_DIR / "manage.py"), "api"],
                [executable, str(SERVER_DIR / "manage.py"), "worker"],
            ]
            if os.getenv("ESP_SERVER_IPV6_PROXY", "0").lower() in {"1", "true", "yes"}:
                commands.append(
                    [
                        executable,
                        str(SERVER_DIR / "manage.py"),
                        "ipv6-proxy",
                    ]
                )
            for command in commands:
                children.append(
                    subprocess.Popen(
                        command,
                        cwd=SERVER_DIR,
                        env=env,
                        stdout=sys.stdout,
                        stderr=sys.stderr,
                        **popen_options(),
                    )
                )
            print("API and worker started; use manage.py stop or Ctrl+C to stop.", flush=True)
            while not stopping.wait(0.2) and not marker.exists():
                for child in children:
                    if child.poll() is not None:
                        return child.returncode or 1
            return 0
        finally:
            marker.touch()
            deadline = time.monotonic() + 35
            for child in children:
                try:
                    child.wait(timeout=max(0.1, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    terminate_tree(child)
            for sig, handler in previous.items():
                signal.signal(sig, handler)


if __name__ == "__main__":
    serve_api()
