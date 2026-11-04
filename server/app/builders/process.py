from __future__ import annotations

import queue
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from app.builders.docker import docker_environment, docker_executable
from app.core.processes import own_process_tree, popen_options, release_process_tree, terminate_tree


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

        with log_path.open("a", encoding="utf-8", newline="\n") as log:
            log.write("\n========== RUN COMMAND ==========\n")
            # Proxy environment arguments may contain credentials.
            display = ["<proxy>" if "proxy=" in item.lower() else item for item in command]
            log.write(" ".join(display) + "\n")
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
                stdin=subprocess.DEVNULL,
                env=docker_environment() if container_name else None,
                **popen_options(),
            )
            own_process_tree(process)
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

                    if cancel_requested():
                        self._terminate(process, container_name)
                        raise BuildCanceled("Build canceled")
                    if time.monotonic() - started > timeout_seconds:
                        self._terminate(process, container_name)
                        raise BuildTimedOut(f"Build timed out after {timeout_seconds} seconds")

                return_code = process.wait()
                if return_code != 0:
                    raise RuntimeError(f"Command failed with exit code {return_code}")
            finally:
                if process.poll() is None:
                    self._terminate(process, container_name)
                if container_name:
                    self.cleanup_container(container_name)
                release_process_tree(process)
                reader.join(timeout=2)
                process.stdout.close()

    @staticmethod
    def _terminate(process: subprocess.Popen[str], container_name: str | None) -> None:
        if container_name:
            ProcessRunner.cleanup_container(container_name)
        terminate_tree(process)

    @staticmethod
    def cleanup_container(container_name: str) -> None:
        try:
            subprocess.run(
                [docker_executable(), "rm", "-f", container_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
                env=docker_environment(),
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
