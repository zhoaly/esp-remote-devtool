from __future__ import annotations

import os
import signal
import subprocess
import time

import psutil


def popen_options() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}


def _group_has_live_members(group: int) -> bool:
    for item in psutil.process_iter(["pid", "status"]):
        try:
            if os.getpgid(item.pid) == group and item.info["status"] != psutil.STATUS_ZOMBIE:
                return True
        except (ProcessLookupError, PermissionError, psutil.NoSuchProcess):
            continue
    return False


def _signal_group(group: int, sig: int) -> bool:
    try:
        os.killpg(group, sig)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Darwin may report EPERM for a group containing only reparented zombies.
        # Do not mask permission failures while live processes still exist.
        if _group_has_live_members(group):
            raise
        return False


def terminate_tree(process: subprocess.Popen, grace: float = 5) -> None:
    """Reap descendants too, including those still holding the output pipe open."""
    if os.name == "nt":
        job = getattr(process, "_esp_job", None)
        if job:
            job.terminate()
            process.wait(timeout=5)
            return
        try:
            parent = psutil.Process(process.pid)
            processes = [*parent.children(recursive=True), parent]
        except psutil.NoSuchProcess:
            processes = []
        for item in processes:
            try:
                item.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(processes, timeout=grace)
        for item in alive:
            try:
                item.kill()
            except psutil.NoSuchProcess:
                pass
        psutil.wait_procs(alive, timeout=5)
    else:
        _signal_group(process.pid, signal.SIGTERM)
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            process.poll()  # Reap the group leader so it does not keep the group alive.
            if not _signal_group(process.pid, 0):
                break
            if process.returncode is not None and not _group_has_live_members(process.pid):
                break
            time.sleep(0.05)
        _signal_group(process.pid, signal.SIGKILL)
    process.wait(timeout=5)


def own_process_tree(process: subprocess.Popen) -> None:
    if os.name == "nt":
        from app.core.windows_job import WindowsJob

        try:
            process._esp_job = WindowsJob(process)
        except OSError:
            terminate_tree(process)
            raise


def release_process_tree(process: subprocess.Popen) -> None:
    job = getattr(process, "_esp_job", None)
    if job:
        job.close()
        del process._esp_job
