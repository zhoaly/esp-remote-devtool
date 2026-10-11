from __future__ import annotations

from pathlib import Path

from app.builders.base import ArtifactSpec, BuildOutput
from app.builders.process import BuildCanceled
from app.domain.jobs import JobKind, JobStatus, SourceMode
from app.main import create_app
from app.services.worker import BuildWorker
from app.storage.repositories import ArtifactRepository, JobRepository
from fastapi.testclient import TestClient


class FakeBuilder:
    def __init__(self, artifact_path: Path) -> None:
        self.artifact_path = artifact_path

    def run(self, context) -> BuildOutput:
        self.artifact_path.write_bytes(b"artifact")
        return BuildOutput(
            result={"fake": True},
            artifacts=[ArtifactSpec("firmware", self.artifact_path, "application/zip")],
        )


class StoppingBuilder:
    def __init__(self, worker: BuildWorker) -> None:
        self.worker = worker

    def run(self, context) -> BuildOutput:
        self.worker.request_stop()
        if context.cancel_requested():
            raise BuildCanceled("stopping")
        raise AssertionError("stop request was not propagated")


def test_worker_completes_queued_job(settings, database) -> None:
    _, factory = database
    with factory.begin() as session:
        record = JobRepository(session).create(
            kind=JobKind.ESP,
            source_mode=SourceMode.WORKSPACE.value,
            project_name="demo",
            request_json={
                "kind": "esp",
                "project_name": "demo",
                "target": "esp32s3",
                "idf_image": settings.default_idf_image,
                "workspace_path": str(settings.workspace_dir),
            },
            log_path=str(settings.log_dir / "fake.log"),
        )
        job_id = record.id

    worker = BuildWorker(settings, factory)
    worker.builders[JobKind.ESP] = FakeBuilder(settings.artifact_dir / "fake.zip")
    assert worker.run_once() is True

    with factory() as session:
        jobs = JobRepository(session)
        assert jobs.get(job_id).status == JobStatus.SUCCEEDED.value
        artifact = ArtifactRepository(session).list_for_job(job_id)[0]
        assert artifact.filename == "fake.zip"
        artifact_id = artifact.id

    with TestClient(create_app(settings, database[0])) as client:
        downloaded = client.get(f"/api/v2/artifacts/{artifact_id}")
        assert downloaded.status_code == 200
        assert downloaded.content == b"artifact"


def test_worker_stop_interrupts_running_job(settings, database) -> None:
    _, factory = database
    with factory.begin() as session:
        record = JobRepository(session).create(
            kind=JobKind.ESP,
            source_mode=SourceMode.WORKSPACE.value,
            project_name="stop-demo",
            request_json={
                "kind": "esp",
                "project_name": "stop-demo",
                "target": "esp32s3",
                "idf_image": settings.default_idf_image,
                "workspace_path": str(settings.workspace_dir),
            },
            log_path=str(settings.log_dir / "stop-demo.log"),
        )
        job_id = record.id

    worker = BuildWorker(settings, factory)
    worker.builders[JobKind.ESP] = StoppingBuilder(worker)
    assert worker.run_once() is True

    with factory() as session:
        record = JobRepository(session).get(job_id)
        assert record.status == JobStatus.INTERRUPTED.value
        assert record.error_code == "worker_stopped"
