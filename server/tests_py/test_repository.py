from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from app.core.errors import ConflictError
from app.domain.jobs import JobKind, JobStatus, SourceMode
from app.storage.repositories import JobRepository


def create_job(repository: JobRepository, settings, name: str):
    return repository.create(
        kind=JobKind.ESP,
        source_mode=SourceMode.WORKSPACE.value,
        project_name=name,
        request_json={
            "kind": "esp",
            "project_name": name,
            "target": "esp32s3",
            "idf_image": "espressif/idf:v6.0.1",
            "workspace_path": str(settings.workspace_dir),
        },
        log_path=str(settings.log_dir / f"{name}.log"),
    )


def test_fifo_claim_and_invalid_transition(database, settings) -> None:
    _, factory = database
    with factory.begin() as session:
        jobs = JobRepository(session)
        first = create_job(jobs, settings, "first")
        create_job(jobs, settings, "second")
        first_id = first.id

    with factory.begin() as session:
        claimed = JobRepository(session).claim_next()
        assert claimed is not None
        assert claimed.id == first_id
        assert claimed.status == JobStatus.RUNNING.value

    with factory.begin() as session:
        jobs = JobRepository(session)
        running = jobs.get(first_id)
        with pytest.raises(ConflictError):
            jobs.transition(running, JobStatus.QUEUED, "invalid")


def test_recovery_interrupts_only_running_jobs(database, settings) -> None:
    _, factory = database
    with factory.begin() as session:
        jobs = JobRepository(session)
        running = create_job(jobs, settings, "running")
        queued = create_job(jobs, settings, "queued")
        running_id, queued_id = running.id, queued.id
        jobs.claim_next()

    with factory.begin() as session:
        assert JobRepository(session).interrupt_running() == 1

    with factory() as session:
        jobs = JobRepository(session)
        assert jobs.get(running_id).status == JobStatus.INTERRUPTED.value
        assert jobs.get(queued_id).status == JobStatus.QUEUED.value


def test_concurrent_claim_never_returns_same_job_twice(database, settings) -> None:
    _, factory = database
    with factory.begin() as session:
        job_id = create_job(JobRepository(session), settings, "concurrent").id

    def claim() -> str | None:
        with factory.begin() as session:
            record = JobRepository(session).claim_next()
            return record.id if record else None

    with ThreadPoolExecutor(max_workers=2) as executor:
        claimed = list(executor.map(lambda _: claim(), range(2)))

    assert claimed.count(job_id) == 1
    assert len([value for value in claimed if value is not None]) == 1
