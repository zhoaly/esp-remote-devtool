from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.domain.jobs import TERMINAL_STATUSES, JobKind, JobStage, JobStatus, can_transition
from app.storage.models import ArtifactRecord, JobEventRecord, JobRecord, OtaReleaseRecord


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        kind: JobKind,
        source_mode: str,
        project_name: str,
        request_json: dict[str, Any],
        log_path: str,
        upload_path: str | None = None,
        workspace_path: str | None = None,
        retry_of_job_id: str | None = None,
        job_id: str | None = None,
    ) -> JobRecord:
        record = JobRecord(
            id=job_id or uuid.uuid4().hex,
            kind=kind.value,
            source_mode=source_mode,
            status=JobStatus.QUEUED.value,
            stage=JobStage.QUEUED.value,
            message="Build queued",
            project_name=project_name,
            request_json=request_json,
            retry_of_job_id=retry_of_job_id,
            upload_path=upload_path,
            workspace_path=workspace_path,
            log_path=log_path,
        )
        self.session.add(record)
        self._add_event(record, "Build queued")
        self.session.flush()
        return record

    def get(self, job_id: str) -> JobRecord:
        record = self.session.get(JobRecord, job_id)
        if record is None:
            raise NotFoundError("job_not_found", "Job not found")
        return record

    def list(
        self,
        *,
        kind: JobKind | None = None,
        status: JobStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[JobRecord]:
        statement = select(JobRecord)
        if kind:
            statement = statement.where(JobRecord.kind == kind.value)
        if status:
            statement = statement.where(JobRecord.status == status.value)
        statement = statement.order_by(JobRecord.created_at.desc()).limit(limit).offset(offset)
        return list(self.session.scalars(statement))

    def claim_next(self) -> JobRecord | None:
        candidate_id = self.session.scalar(
            select(JobRecord.id)
            .where(JobRecord.status == JobStatus.QUEUED.value)
            .order_by(JobRecord.created_at.asc(), JobRecord.id.asc())
            .limit(1)
        )
        if candidate_id is None:
            return None

        now = utcnow()
        claimed = self.session.execute(
            update(JobRecord)
            .where(
                JobRecord.id == candidate_id,
                JobRecord.status == JobStatus.QUEUED.value,
            )
            .values(
                status=JobStatus.RUNNING.value,
                message="Build worker started",
                started_at=now,
                heartbeat_at=now,
            )
        )
        if claimed.rowcount != 1:
            self.session.rollback()
            return None

        record = self.get(candidate_id)
        self._add_event(record, record.message)
        self.session.flush()
        return record

    def transition(
        self,
        record: JobRecord,
        status: JobStatus,
        message: str,
        *,
        stage: JobStage | None = None,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> JobRecord:
        current = JobStatus(record.status)
        if not can_transition(current, status):
            raise ConflictError(
                "invalid_job_transition",
                f"Cannot transition job from {current.value} to {status.value}",
            )
        record.status = status.value
        record.message = message
        if stage is not None:
            record.stage = stage.value
        if result is not None:
            record.result_json = result
        record.error_code = error_code
        record.error_message = error_message
        if status in TERMINAL_STATUSES:
            record.finished_at = utcnow()
            record.stage = JobStage.COMPLETED.value
        record.heartbeat_at = utcnow()
        self._add_event(record, message)
        self.session.flush()
        return record

    def update_stage(self, record: JobRecord, stage: JobStage, message: str) -> None:
        if record.status != JobStatus.RUNNING.value:
            raise ConflictError("invalid_job_stage", "Only running jobs can change stage")
        record.stage = stage.value
        record.message = message
        record.heartbeat_at = utcnow()
        self._add_event(record, message)
        self.session.flush()

    def heartbeat(self, record: JobRecord) -> None:
        record.heartbeat_at = utcnow()
        self.session.flush()

    def merge_result(self, record: JobRecord, values: dict[str, Any]) -> None:
        result = dict(record.result_json or {})
        result.update(values)
        record.result_json = result
        self.session.flush()

    def request_cancel(self, record: JobRecord) -> JobRecord:
        status = JobStatus(record.status)
        if status == JobStatus.QUEUED:
            return self.transition(record, JobStatus.CANCELED, "Build canceled before execution")
        if status == JobStatus.RUNNING:
            record.cancel_requested = True
            record.message = "Cancellation requested"
            self._add_event(record, record.message)
            self.session.flush()
            return record
        raise ConflictError("invalid_job_transition", "Only queued or running jobs can be canceled")

    def is_cancel_requested(self, job_id: str) -> bool:
        return bool(
            self.session.scalar(select(JobRecord.cancel_requested).where(JobRecord.id == job_id))
        )

    def running_jobs(self) -> list[JobRecord]:
        return list(
            self.session.scalars(
                select(JobRecord).where(JobRecord.status == JobStatus.RUNNING.value)
            )
        )

    def interrupt_running(self) -> int:
        running = self.running_jobs()
        for record in running:
            self.transition(
                record,
                JobStatus.INTERRUPTED,
                "Build interrupted by worker restart",
                error_code="worker_restarted",
                error_message="The worker stopped before the build completed",
            )
        return len(running)

    def terminal_jobs_beyond_limit(self, kind: JobKind, keep: int) -> list[JobRecord]:
        statement = (
            select(JobRecord)
            .where(
                JobRecord.kind == kind.value,
                JobRecord.status.in_([item.value for item in TERMINAL_STATUSES]),
                JobRecord.id.not_in(select(OtaReleaseRecord.job_id)),
            )
            .order_by(JobRecord.created_at.desc())
            .offset(max(keep, 0))
        )
        return list(self.session.scalars(statement))

    def delete(self, record: JobRecord) -> None:
        self.session.delete(record)
        self.session.flush()

    def _add_event(self, record: JobRecord, message: str) -> None:
        self.session.add(
            JobEventRecord(
                job=record,
                status=record.status,
                stage=record.stage,
                message=message,
            )
        )


class ArtifactRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        job_id: str,
        kind: str,
        filename: str,
        path: str,
        media_type: str,
        size: int,
        sha256: str,
    ) -> ArtifactRecord:
        record = ArtifactRecord(
            id=uuid.uuid4().hex,
            job_id=job_id,
            kind=kind,
            filename=filename,
            path=path,
            media_type=media_type,
            size=size,
            sha256=sha256,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def get(self, artifact_id: str) -> ArtifactRecord:
        record = self.session.get(ArtifactRecord, artifact_id)
        if record is None:
            raise NotFoundError("artifact_not_found", "Artifact not found")
        return record

    def list_for_job(self, job_id: str) -> list[ArtifactRecord]:
        return list(
            self.session.scalars(
                select(ArtifactRecord)
                .where(ArtifactRecord.job_id == job_id)
                .order_by(ArtifactRecord.created_at.asc())
            )
        )

    def delete(self, record: ArtifactRecord) -> None:
        self.session.delete(record)
        self.session.flush()


class OtaRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, **values: Any) -> OtaReleaseRecord:
        record = OtaReleaseRecord(**values)
        self.session.add(record)
        self.session.flush()
        return record

    def get(self, release_id: str) -> OtaReleaseRecord:
        record = self.session.get(OtaReleaseRecord, release_id)
        if record is None:
            raise NotFoundError("ota_release_not_found", "OTA release not found")
        return record

    def list(
        self,
        *,
        project: str | None = None,
        chip: str | None = None,
        channel: str | None = None,
    ) -> list[OtaReleaseRecord]:
        statement = select(OtaReleaseRecord)
        if project:
            statement = statement.where(OtaReleaseRecord.project == project)
        if chip:
            statement = statement.where(OtaReleaseRecord.chip == chip)
        if channel:
            statement = statement.where(OtaReleaseRecord.channel == channel)
        statement = statement.order_by(OtaReleaseRecord.created_at.desc())
        return list(self.session.scalars(statement))

    def latest(self, project: str, chip: str, channel: str) -> OtaReleaseRecord | None:
        return self.session.scalar(
            select(OtaReleaseRecord)
            .where(
                OtaReleaseRecord.project == project,
                OtaReleaseRecord.chip == chip,
                OtaReleaseRecord.channel == channel,
            )
            .order_by(OtaReleaseRecord.created_at.desc())
            .limit(1)
        )

    def delete(self, record: OtaReleaseRecord) -> None:
        self.session.execute(delete(OtaReleaseRecord).where(OtaReleaseRecord.id == record.id))
        self.session.flush()
