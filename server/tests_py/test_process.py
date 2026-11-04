from __future__ import annotations

import sys
import time

import psutil
import pytest
from app.builders.process import BuildCanceled, BuildTimedOut, ProcessRunner


def assert_process_exited(pid: int) -> None:
    # Windows Job Object termination completes asynchronously. A process can
    # disappear between pid_exists() and status(), which is also a successful exit.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            process = psutil.Process(pid)
            if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                return
        except psutil.NoSuchProcess:
            return
        time.sleep(0.02)
    pytest.fail(f"Child process {pid} is still running after cancellation")


def test_process_runner_cancels_process_group(tmp_path) -> None:
    started = time.monotonic()
    with pytest.raises(BuildCanceled):
        ProcessRunner().run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            tmp_path / "cancel.log",
            timeout_seconds=30,
            cancel_requested=lambda: True,
        )
    assert time.monotonic() - started < 5


def test_process_runner_times_out(tmp_path) -> None:
    started = time.monotonic()
    with pytest.raises(BuildTimedOut):
        ProcessRunner().run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            tmp_path / "timeout.log",
            timeout_seconds=0,
            cancel_requested=lambda: False,
        )
    assert time.monotonic() - started < 5


def test_cancel_reaps_child_process_and_cleans_container(tmp_path, monkeypatch) -> None:
    pidfile = tmp_path / "child.pid"
    code = (
        "import subprocess,sys,time,pathlib; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); "
        f"pathlib.Path({str(pidfile)!r}).write_text(str(p.pid)); "
        "time.sleep(120)"
    )
    cleaned = []
    monkeypatch.setattr(ProcessRunner, "cleanup_container", staticmethod(cleaned.append))
    with pytest.raises(BuildCanceled):
        ProcessRunner().run(
            [sys.executable, "-c", code],
            tmp_path / "child.log",
            timeout_seconds=15,
            cancel_requested=pidfile.exists,
            container_name="esp-build-cancel",
        )
    pid = int(pidfile.read_text())
    assert_process_exited(pid)
    assert "esp-build-cancel" in cleaned


def test_failed_command_cleans_container_and_redacts_proxy(tmp_path, monkeypatch) -> None:
    cleaned = []
    monkeypatch.setattr(ProcessRunner, "cleanup_container", staticmethod(cleaned.append))
    with pytest.raises(RuntimeError, match="exit code 2"):
        ProcessRunner().run(
            [sys.executable, "-c", "raise SystemExit(2)", "HTTPS_PROXY=http://secret@proxy"],
            tmp_path / "failure.log",
            timeout_seconds=10,
            cancel_requested=lambda: False,
            container_name="esp-build-failed",
        )
    assert cleaned == ["esp-build-failed"]
    assert "secret" not in (tmp_path / "failure.log").read_text()


def test_timeout_reaps_descendant_after_parent_exits(tmp_path):
    pidfile = tmp_path / "orphan.pid"
    code = (
        "import subprocess,sys,pathlib; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(120)']); "
        f"pathlib.Path({str(pidfile)!r}).write_text(str(p.pid))"
    )
    with pytest.raises(BuildTimedOut):
        ProcessRunner().run(
            [sys.executable, "-c", code],
            tmp_path / "orphan.log",
            timeout_seconds=1,
            cancel_requested=lambda: False,
        )
    pid = int(pidfile.read_text())
    assert_process_exited(pid)
