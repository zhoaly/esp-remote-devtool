from __future__ import annotations

import logging
import time
import traceback
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.builders.base import BuildContext
from app.builders.esp import EspBuilder
from app.builders.files import sha256_file
from app.builders.lvgl import LvglBuilder
from app.builders.process import BuildCanceled, BuildTimedOut, ProcessRunner
from app.core.config import Settings
from app.domain.jobs import JobKind, JobStage, JobStatus
from app.services.jobs import RetentionService
from app.storage.repositories import ArtifactRepository, JobRepository

LOGGER = logging.getLogger(__name__)


class BuildWorker:
    def __init__(self, settings: Settings, session_factory: sessionmaker[Session]) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.builders = {
            JobKind.ESP: EspBuilder(),
            JobKind.LVGL: LvglBuilder(),
        }
        self._stopping = False

    def request_stop(self) -> None:
        self._stopping = True

    def recover(self) -> int:
        with self.session_factory() as session:
            unfinished = [
                (record.id, record.kind) for record in JobRepository(session).running_jobs()
            ]
        for job_id, kind in unfinished:
            ProcessRunner.cleanup_container(f"{kind}-build-{job_id}")
        with self.session_factory.begin() as session:
            jobs = JobRepository(session)
            interrupted = jobs.interrupt_running()
            RetentionService(self.settings, jobs).prune()
            return interrupted

    def run_once(self) -> bool:
        with self.session_factory.begin() as session:
            record = JobRepository(session).claim_next()
            if record is None:
                return False
            job_id = record.id

        with self.session_factory() as session:
            job = JobRepository(session).get(job_id)
            builder = self.builders[JobKind(job.kind)]
            heartbeat_at = [0.0]
            context = BuildContext(
                settings=self.settings,
                job=job,
                runner=ProcessRunner(),
                update_stage=lambda stage, message: self._update_stage(job_id, stage, message),
                cancel_requested=lambda: self._poll_control(job_id, heartbeat_at),
            )

        try:
            output = builder.run(context)
            with self.session_factory.begin() as session:
                jobs = JobRepository(session)
                current = jobs.get(job_id)
                if current.cancel_requested:
                    jobs.transition(current, JobStatus.CANCELED, "Build canceled")
                else:
                    artifacts = ArtifactRepository(session)
                    for spec in output.artifacts:
                        artifacts.create(
                            job_id=job_id,
                            kind=spec.kind,
                            filename=spec.path.name,
                            path=str(spec.path.resolve()),
                            media_type=spec.media_type,
                            size=spec.path.stat().st_size,
                            sha256=sha256_file(spec.path),
                        )
                    jobs.transition(
                        current,
                        JobStatus.SUCCEEDED,
                        "Build completed successfully",
                        stage=JobStage.COMPLETED,
                        result=output.result,
                    )
                RetentionService(self.settings, jobs).prune()
        except BuildCanceled as exc:
            if self._stopping:
                self._fail(
                    job_id,
                    JobStatus.INTERRUPTED,
                    "worker_stopped",
                    "Build interrupted because the worker is stopping",
                )
            else:
                self._fail(job_id, JobStatus.CANCELED, "build_canceled", str(exc))
        except BuildTimedOut as exc:
            self._fail(job_id, JobStatus.FAILED, "build_timeout", str(exc))
        except Exception as exc:
            if self._stopping:
                self._fail(
                    job_id,
                    JobStatus.INTERRUPTED,
                    "worker_stopped",
                    "Build process stopped while the worker was shutting down",
                )
            else:
                LOGGER.exception("Build job %s failed", job_id)
                self._append_failure(job_id, exc)
                self._fail(job_id, JobStatus.FAILED, "build_failed", str(exc))
        return True

    def _update_stage(self, job_id: str, stage: JobStage, message: str) -> None:
        with self.session_factory.begin() as session:
            jobs = JobRepository(session)
            jobs.update_stage(jobs.get(job_id), stage, message)

    def _poll_control(self, job_id: str, heartbeat_at: list[float]) -> bool:
        now = time.monotonic()
        with self.session_factory() as session:
            jobs = JobRepository(session)
            record = jobs.get(job_id)
            canceled = record.cancel_requested or self._stopping
            if now - heartbeat_at[0] >= 10:
                jobs.heartbeat(record)
                session.commit()
                heartbeat_at[0] = now
            return canceled

    def _fail(self, job_id: str, status: JobStatus, code: str, message: str) -> None:
        with self.session_factory.begin() as session:
            jobs = JobRepository(session)
            record = jobs.get(job_id)
            if record.status == JobStatus.RUNNING.value:
                public_message = {
                    JobStatus.CANCELED: "Build canceled",
                    JobStatus.INTERRUPTED: "Build interrupted",
                    JobStatus.FAILED: "Build timed out" if code == "build_timeout" else "Build failed",
                }[status]
                jobs.transition(
                    record,
                    status,
                    public_message,
                    error_code=code,
                    error_message=message,
                )
                RetentionService(self.settings, jobs).prune()

    def _append_failure(self, job_id: str, exc: Exception) -> None:
        with self.session_factory() as session:
            record = JobRepository(session).get(job_id)
            path = Path(record.log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as log:
            log.write("\n========== BUILD FAILED ==========\n")
            log.write("".join(traceback.format_exception_only(type(exc), exc)))
            log.write("==================================\n")
