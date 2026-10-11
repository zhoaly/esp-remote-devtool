from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path


class BuildCanceled(RuntimeError):
    pass


class BuildTimedOut(RuntimeError):
    pass


class ProcessRunner:
    def run(
        self,
        command: Sequence[str],
        log_path: Path,
        *,
        timeout_seconds: int,
        cancel_requested: Callable[[], bool],
        container_name: str | None = None,
    ) -> None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        lines: queue.Queue[str | None] = queue.Queue()

        with log_path.open("a", encoding="utf-8") as log:
            log.write("\n========== RUN COMMAND ==========\n")
            log.write(" ".join(command) + "\n")
            log.write("=================================\n")
            log.flush()

            process = subprocess.Popen(
                list(command),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                start_new_session=True,
            )
            assert process.stdout is not None

            def read_output() -> None:
                try:
                    for line in process.stdout:
                        lines.put(line)
                finally:
                    lines.put(None)

            reader = threading.Thread(target=read_output, name="build-output-reader", daemon=True)
            reader.start()
            started = time.monotonic()
            output_done = False

            try:
                while process.poll() is None or not output_done:
                    try:
                        item = lines.get(timeout=0.5)
                        if item is None:
                            output_done = True
                        else:
                            log.write(item)
                            log.flush()
                    except queue.Empty:
                        pass

                    if process.poll() is None and cancel_requested():
                        self._terminate(process, container_name)
                        raise BuildCanceled("Build canceled")
                    if process.poll() is None and time.monotonic() - started > timeout_seconds:
                        self._terminate(process, container_name)
                        raise BuildTimedOut(f"Build timed out after {timeout_seconds} seconds")

                return_code = process.wait()
                if return_code != 0:
                    raise RuntimeError(f"Command failed with exit code {return_code}")
            finally:
                if process.poll() is None:
                    self._terminate(process, container_name)
                reader.join(timeout=2)

    @staticmethod
    def _terminate(process: subprocess.Popen[str], container_name: str | None) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        if container_name:
            ProcessRunner.cleanup_container(container_name)

    @staticmethod
    def cleanup_container(container_name: str) -> None:
        try:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
