from __future__ import annotations

import logging
import signal

from filelock import FileLock, Timeout

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.runtime import stop_event
from app.services.worker import BuildWorker
from app.storage.database import create_database_engine, create_session_factory

configure_logging()
LOGGER = logging.getLogger(__name__)


def run() -> None:
    settings = get_settings()
    settings.ensure_directories()
    engine = create_database_engine(settings)
    worker = BuildWorker(settings, create_session_factory(engine))
    stopping = stop_event(worker.request_stop)

    def stop(_signum: int, _frame: object) -> None:
        stopping.set()
        worker.request_stop()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, stop)
    lock_path = settings.worker_lock_path
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    lock = FileLock(lock_path, timeout=0)
    try:
        lock.acquire()
    except Timeout as exc:
        raise SystemExit("Another build worker is already running") from exc
    try:
        interrupted = worker.recover()
        if interrupted:
            LOGGER.warning("Marked %s unfinished job(s) as interrupted", interrupted)
        LOGGER.info("Persistent build worker started")
        while not stopping.is_set():
            if not worker.run_once():
                stopping.wait(settings.worker_poll_seconds)
        LOGGER.info("Persistent build worker stopped")
    finally:
        engine.dispose()
        lock.release()


if __name__ == "__main__":
    run()
