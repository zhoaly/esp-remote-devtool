from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from app.builders.files import remove_managed_path
from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError
from app.domain.jobs import TERMINAL_STATUSES, JobKind, JobStatus, SourceMode
from app.domain.schemas import (
    ArtifactResponse,
    EspBuildConfiguration,
    JobLinks,
    JobResponse,
    LogChunkResponse,
    LvglBuildConfiguration,
)
from app.services.files import FileDownload
from app.storage.models import ArtifactRecord, JobRecord
from app.storage.repositories import ArtifactRepository, JobRepository


class JobService:
    def __init__(
        self,
        settings: Settings,
        jobs: JobRepository,
        artifacts: ArtifactRepository,
    ) -> None:
        self.settings = settings
        self.jobs = jobs
        self.artifacts = artifacts

    def get(self, job_id: str) -> JobResponse:
        return self.to_response(self.jobs.get(job_id))

    def list(
        self,
        *,
        kind: JobKind | None,
        status: JobStatus | None,
        limit: int,
        offset: int,
    ) -> list[JobResponse]:
        return [
            self.to_response(record)
            for record in self.jobs.list(kind=kind, status=status, limit=limit, offset=offset)
        ]

    def cancel(self, job_id: str) -> JobResponse:
        record = self.jobs.request_cancel(self.jobs.get(job_id))
        if record.status == JobStatus.CANCELED.value:
            RetentionService(self.settings, self.jobs).prune()
        return self.to_response(record)

    def retry(self, job_id: str) -> JobResponse:
        original = self.jobs.get(job_id)
        if JobStatus(original.status) not in {
            JobStatus.FAILED,
            JobStatus.CANCELED,
            JobStatus.INTERRUPTED,
        }:
            raise ConflictError("invalid_job_transition", "Only failed, canceled, or interrupted jobs can be retried")
        if original.upload_path and not Path(original.upload_path).is_file():
            raise ConflictError("retry_source_missing", "The original upload is no longer available")
        if original.source_mode == SourceMode.WORKSPACE.value:
            workspace = Path(str(original.request_json.get("workspace_path", ""))).expanduser()
            if not workspace.is_dir():
                raise ConflictError("retry_source_missing", "The configured workspace is no longer available")

        new_id = uuid.uuid4().hex
        workspace_path = None
        upload_path = original.upload_path
        if original.upload_path:
            suffix = "_lvgl" if original.kind == JobKind.LVGL.value else ""
            workspace_path = str(self.settings.workspace_dir / f"{new_id}{suffix}")
            upload_suffix = "_lvgl.zip" if original.kind == JobKind.LVGL.value else ".zip"
            copied_upload = self.settings.upload_dir / f"{new_id}{upload_suffix}"
            shutil.copy2(original.upload_path, copied_upload)
            upload_path = str(copied_upload)
        try:
            record = self.jobs.create(
                kind=JobKind(original.kind),
                source_mode=original.source_mode,
                project_name=original.project_name,
                request_json=dict(original.request_json),
                log_path=str(self.settings.log_dir / f"{new_id}.log"),
                upload_path=upload_path,
                workspace_path=workspace_path,
                retry_of_job_id=original.id,
                job_id=new_id,
            )
        except Exception:
            if upload_path and upload_path != original.upload_path:
                Path(upload_path).unlink(missing_ok=True)
            raise
        return self.to_response(record)

    def read_log(self, job_id: str, offset: int, limit: int) -> LogChunkResponse:
        record = self.jobs.get(job_id)
        path = Path(record.log_path)
        if not path.exists():
            return LogChunkResponse(
                content="",
                next_offset=0,
                complete=JobStatus(record.status) in TERMINAL_STATUSES,
            )
        size = path.stat().st_size
        start = min(offset, size)
        with path.open("rb") as handle:
            handle.seek(start)
            content = handle.read(limit)
        return LogChunkResponse(
            content=content.decode("utf-8", errors="replace"),
            next_offset=start + len(content),
            complete=(start + len(content) >= size and JobStatus(record.status) in TERMINAL_STATUSES),
        )

    def artifact_download(self, artifact_id: str) -> FileDownload:
        artifact = self.artifacts.get(artifact_id)
        path = Path(artifact.path)
        if not path.is_file():
            raise NotFoundError("artifact_not_found", "Artifact file not found")
        return FileDownload(path, artifact.media_type, artifact.filename)

    def preview_asset(self, job_id: str, asset_path: str) -> FileDownload:
        job = self.jobs.get(job_id)
        if job.kind != JobKind.LVGL.value or job.status != JobStatus.SUCCEEDED.value:
            raise NotFoundError("preview_not_found", "LVGL preview not found")
        root = (self.settings.lvgl_preview_dir / job_id).resolve()
        target = (root / (asset_path or "index.html")).resolve()
        if target.is_dir():
            target = (target / "index.html").resolve()
        if (target != root and root not in target.parents) or not target.is_file():
            raise NotFoundError("preview_not_found", "LVGL preview asset not found")
        media_type = {
            ".wasm": "application/wasm",
            ".js": "application/javascript",
            ".mjs": "application/javascript",
            ".html": "text/html",
            ".css": "text/css",
            ".json": "application/json",
            ".data": "application/octet-stream",
        }.get(target.suffix.lower(), "application/octet-stream")
        return FileDownload(target, media_type, cache_control="no-store")

    def to_response(self, record: JobRecord) -> JobResponse:
        request = record.request_json
        if record.kind == JobKind.ESP.value:
            config = EspBuildConfiguration.model_validate(
                {
                    "project_name": record.project_name,
                    "target": request["target"],
                    "idf_image": request["idf_image"],
                    "workspace_id": request.get("workspace_id"),
                }
            )
        else:
            config = LvglBuildConfiguration.model_validate(
                {
                    "project_name": record.project_name,
                    "width": request["width"],
                    "height": request["height"],
                    "lvgl_version": request.get("lvgl_version", self.settings.lvgl_default_version),
                    "workspace_id": request.get("workspace_id"),
                }
            )
        artifact_records = self.artifacts.list_for_job(record.id)
        artifact_values = [self._artifact_response(item) for item in artifact_records]
        primary = artifact_values[0] if artifact_values else None
        raw_result = record.result_json or {}
        public_result = {key: value for key, value in raw_result.items() if not key.startswith("_")}
        preview_url = raw_result.get("preview_url")
        log_url = f"/api/v2/jobs/{record.id}/logs"
        return JobResponse(
            id=record.id,
            kind=JobKind(record.kind),
            source_mode=SourceMode(record.source_mode),
            status=JobStatus(record.status),
            stage=record.stage,
            message=record.message,
            project_name=record.project_name,
            configuration=config,
            result=public_result or None,
            artifacts=artifact_values,
            links=JobLinks(
                self=f"/api/v2/jobs/{record.id}",
                logs=log_url,
                preview=preview_url,
            ),
            retry_of_job_id=record.retry_of_job_id,
            cancel_requested=record.cancel_requested,
            error_code=record.error_code,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            target=request.get("target"),
            idf_image=request.get("idf_image"),
            width=request.get("width"),
            height=request.get("height"),
            lvgl_version=request.get("lvgl_version"),
            download_url=primary.url if primary else None,
            artifact_url=primary.url if primary else None,
            artifact_name=primary.filename if primary else None,
            preview_url=preview_url,
            log_url=log_url,
            ota_publishable=bool(raw_result.get("ota_publishable")),
            ota_project_version=raw_result.get("ota_project_version"),
            ota_app_size=raw_result.get("ota_app_size"),
            ota_app_sha256=raw_result.get("ota_app_sha256"),
            ota_app_bin_name=raw_result.get("ota_app_bin_name"),
            ota_partition_limit=raw_result.get("ota_partition_limit"),
            ota_manifest_url=raw_result.get("ota_manifest_url"),
            ota_firmware_url=raw_result.get("ota_firmware_url"),
            ota_release_id=raw_result.get("ota_release_id"),
        )

    @staticmethod
    def _artifact_response(record: ArtifactRecord) -> ArtifactResponse:
        return ArtifactResponse(
            id=record.id,
            kind=record.kind,
            filename=record.filename,
            media_type=record.media_type,
            size=record.size,
            sha256=record.sha256,
            url=f"/api/v2/artifacts/{record.id}",
        )


class RetentionService:
    def __init__(self, settings: Settings, jobs: JobRepository) -> None:
        self.settings = settings
        self.jobs = jobs

    def prune(self) -> int:
        removed = 0
        for kind in JobKind:
            for record in self.jobs.terminal_jobs_beyond_limit(kind, self.settings.max_build_records):
                self._remove_files(record)
                self.jobs.delete(record)
                removed += 1
        return removed

    def _remove_files(self, record: JobRecord) -> None:
        roots = (
            self.settings.upload_dir,
            self.settings.workspace_dir,
            self.settings.artifact_dir,
            self.settings.lvgl_preview_dir,
            self.settings.log_dir,
        )
        paths = [record.upload_path, record.workspace_path, record.log_path]
        paths.extend(item.path for item in record.artifacts)
        if record.kind == JobKind.LVGL.value:
            paths.append(str(self.settings.lvgl_preview_dir / record.id))
        for value in paths:
            if not value:
                continue
            try:
                remove_managed_path(Path(value), roots)
            except RuntimeError:
                continue
