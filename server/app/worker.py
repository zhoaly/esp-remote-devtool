from __future__ import annotations

import fcntl
import logging
import signal
import time
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.worker import BuildWorker
from app.storage.database import create_database_engine, create_session_factory

configure_logging()
LOGGER = logging.getLogger(__name__)


def run() -> None:
    settings = get_settings()
    settings.ensure_directories()
    engine = create_database_engine(settings)
    worker = BuildWorker(settings, create_session_factory(engine))
    should_stop = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal should_stop
        should_stop = True
        worker.request_stop()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    lock_path = Path(settings.worker_lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit("Another build worker is already running") from exc

        interrupted = worker.recover()
        if interrupted:
            LOGGER.warning("Marked %s unfinished job(s) as interrupted", interrupted)
        LOGGER.info("Persistent build worker started")
        while not should_stop:
            if not worker.run_once():
                time.sleep(settings.worker_poll_seconds)
        LOGGER.info("Persistent build worker stopped")


if __name__ == "__main__":
    run()
