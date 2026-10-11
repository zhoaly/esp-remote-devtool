from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import StrEnum

import uvicorn
from agent_app import create_app
from config import AgentSettings, load_settings

LOGGER = logging.getLogger(__name__)


class ServerStatus(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ServerSnapshot:
    status: ServerStatus
    settings: AgentSettings | None
    error: str | None = None


class AgentServerController:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._settings: AgentSettings | None = None
        self._status = ServerStatus.STOPPED
        self._error: str | None = None

    def snapshot(self) -> ServerSnapshot:
        with self._lock:
            server = self._server
            thread = self._thread
            status = self._status

            if status == ServerStatus.STARTING and server and server.started:
                self._status = ServerStatus.RUNNING
                status = ServerStatus.RUNNING
            elif (
                status in {ServerStatus.STARTING, ServerStatus.RUNNING}
                and thread
                and not thread.is_alive()
            ):
                self._status = (
                    ServerStatus.ERROR if self._error else ServerStatus.STOPPED
                )
                status = self._status

            return ServerSnapshot(status, self._settings, self._error)

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return

            self._settings = load_settings()
            app = create_app(self._settings)
            config = uvicorn.Config(
                app,
                host=self._settings.host,
                port=self._settings.port,
                reload=False,
                access_log=False,
                log_config=None,
            )
            self._server = uvicorn.Server(config)
            self._status = ServerStatus.STARTING
            self._error = None
            self._thread = threading.Thread(
                target=self._run_server,
                name="ESPAgentServer",
                daemon=True,
            )
            self._thread.start()

    def _run_server(self) -> None:
        try:
            server = self._server
            if server is None:
                return
            settings = self._settings
            if settings:
                LOGGER.info(
                    "Starting local agent at %s:%s",
                    settings.host,
                    settings.port,
                )
            server.run()
        except SystemExit as exc:
            with self._lock:
                if self._status != ServerStatus.STOPPING:
                    self._error = f"Agent server failed to start (exit code {exc.code})"
                    self._status = ServerStatus.ERROR
            LOGGER.exception("Local agent server exited")
        except BaseException as exc:
            with self._lock:
                if self._status != ServerStatus.STOPPING:
                    self._error = f"{type(exc).__name__}: {exc}"
                    self._status = ServerStatus.ERROR
            LOGGER.exception("Local agent server failed")
        finally:
            with self._lock:
                if self._status == ServerStatus.STOPPING:
                    self._status = ServerStatus.STOPPED
                elif self._status not in {ServerStatus.ERROR, ServerStatus.STOPPED}:
                    self._status = ServerStatus.ERROR
                    self._error = self._error or "Agent server stopped unexpectedly"

    def wait_until_ready(self, timeout: float = 5.0) -> ServerSnapshot:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            snapshot = self.snapshot()
            if snapshot.status in {
                ServerStatus.RUNNING,
                ServerStatus.ERROR,
                ServerStatus.STOPPED,
            }:
                return snapshot
            time.sleep(0.05)
        return self.snapshot()

    def stop(self, timeout: float = 10.0) -> None:
        with self._lock:
            server = self._server
            thread = self._thread
            if not thread or not thread.is_alive():
                self._status = ServerStatus.STOPPED
                return
            self._status = ServerStatus.STOPPING
            if server:
                server.should_exit = True

        thread.join(timeout)
        if thread.is_alive() and server:
            server.force_exit = True
            thread.join(2)

        with self._lock:
            if not thread.is_alive():
                self._status = ServerStatus.STOPPED
                self._server = None
                self._thread = None

    def restart(self) -> None:
        self.stop()
        self.start()
