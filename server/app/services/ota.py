from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlencode

from app.builders.files import is_managed_path, remove_managed_path, sha256_file
from app.core.config import Settings
from app.core.errors import AppError, ConflictError
from app.domain.jobs import JobKind, JobStatus
from app.domain.schemas import OtaPublishRequest, OtaReleaseResponse
from app.services.files import FileDownload
from app.storage.models import OtaReleaseRecord
from app.storage.repositories import ArtifactRepository, JobRepository, OtaRepository


def _semver(value: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in value.split("."))  # type: ignore[return-value]


class OtaService:
    def __init__(
        self,
        settings: Settings,
        jobs: JobRepository,
        artifacts: ArtifactRepository,
        releases: OtaRepository,
    ) -> None:
        self.settings = settings
        self.jobs = jobs
        self.artifacts = artifacts
        self.releases = releases

    def publish(self, payload: OtaPublishRequest, request_origin: str) -> OtaReleaseResponse:
        job = self.jobs.get(payload.job_id)
        if job.kind != JobKind.ESP.value or job.status != JobStatus.SUCCEEDED.value:
            raise ConflictError("job_not_publishable", "Only successful ESP jobs can be published")
        result = job.result_json or {}
        if not result.get("ota_publishable"):
            raise ConflictError("job_not_publishable", "Build output is not OTA publishable")

        project = job.project_name
        chip = str(job.request_json["target"])
        latest = self.releases.latest(project, chip, payload.channel)
        if latest and not payload.force and _semver(payload.version) <= _semver(latest.version):
            raise ConflictError(
                "ota_version_not_increasing",
                "Version must be greater than the current channel version unless force=true",
            )

        app_path = Path(str(result.get("_ota_app_path", ""))).resolve()
        if not app_path.is_file() or not is_managed_path(
            app_path, (self.settings.workspace_dir, Path(str(job.request_json.get("workspace_path", "/__none__"))).resolve())
        ):
            raise AppError("ota_binary_missing", "Application binary is unavailable", status_code=404)
        size = app_path.stat().st_size
        if size > self.settings.ota_app_partition_size:
            raise ConflictError("ota_binary_too_large", "Application binary exceeds OTA partition size")
        digest = sha256_file(app_path)
        if result.get("ota_app_sha256") and digest != result["ota_app_sha256"]:
            raise ConflictError("ota_binary_changed", "Application binary changed after the build")

        release_id = uuid.uuid4().hex
        release_dir = self.settings.ota_release_dir / release_id
        release_dir.mkdir(parents=True, exist_ok=False)
        firmware_path = release_dir / "app.bin"
        shutil.copy2(app_path, firmware_path)
        artifact = self.artifacts.create(
            job_id=job.id,
            kind="ota_firmware",
            filename="app.bin",
            path=str(firmware_path),
            media_type="application/octet-stream",
            size=size,
            sha256=digest,
        )
        base = self.settings.ota_public_base_url or request_origin.rstrip("/")
        firmware_url = f"{base}/api/v2/ota/firmware/{release_id}"
        latest_url = (
            f"{base}/api/v2/ota/latest?"
            + urlencode({"project": project, "chip": chip, "channel": payload.channel})
        )
        manifest = {
            "project": project,
            "chip": chip,
            "version": payload.version,
            "min_version": payload.min_version,
            "force": payload.force,
            "url": firmware_url,
            "size": size,
            "sha256": digest,
        }
        (release_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        record = self.releases.create(
            id=release_id,
            job_id=job.id,
            artifact_id=artifact.id,
            project=project,
            chip=chip,
            channel=payload.channel,
            version=payload.version,
            min_version=payload.min_version,
            force=payload.force,
            release_notes=payload.release_notes,
            size=size,
            sha256=digest,
            manifest_json=manifest,
        )
        self.jobs.merge_result(
            job,
            {
                "ota_release_id": release_id,
                "ota_manifest_url": latest_url,
                "ota_firmware_url": firmware_url,
            },
        )
        return self.to_response(record, request_origin)

    def list(
        self,
        request_origin: str,
        *,
        project: str | None = None,
        chip: str | None = None,
        channel: str | None = None,
    ) -> list[OtaReleaseResponse]:
        return [
            self.to_response(record, request_origin)
            for record in self.releases.list(project=project, chip=chip, channel=channel)
        ]

    def latest_manifest(
        self, project: str, chip: str, channel: str, request_origin: str
    ) -> dict[str, object]:
        record = self.releases.latest(project, chip, channel)
        if record is None:
            raise AppError("ota_release_not_found", "OTA release not found", status_code=404)
        return self.manifest(record, request_origin)

    def manifest(self, record: OtaReleaseRecord, request_origin: str) -> dict[str, object]:
        value = dict(record.manifest_json)
        base = self.settings.ota_public_base_url or request_origin.rstrip("/")
        value["url"] = f"{base}/api/v2/ota/firmware/{record.id}"
        return value

    def release_manifest(self, release_id: str, request_origin: str) -> dict[str, object]:
        return self.manifest(self.releases.get(release_id), request_origin)

    def firmware_download(self, release_id: str) -> FileDownload:
        release = self.releases.get(release_id)
        artifact = self.artifacts.get(release.artifact_id)
        path = Path(artifact.path)
        if not path.is_file():
            raise AppError("ota_firmware_not_found", "OTA firmware not found", status_code=404)
        return FileDownload(path, "application/octet-stream", "app.bin")

    def delete(self, release_id: str, request_origin: str) -> dict[str, object]:
        record = self.releases.get(release_id)
        artifact = self.artifacts.get(record.artifact_id)
        job = self.jobs.get(record.job_id)
        release_dir = self.settings.ota_release_dir / release_id
        self.releases.delete(record)
        self.artifacts.delete(artifact)
        if release_dir.exists():
            remove_managed_path(release_dir, (self.settings.ota_release_dir,))

        remaining = self.releases.list(project=record.project, chip=record.chip, channel=record.channel)
        job_releases = [item for item in self.releases.list() if item.job_id == job.id]
        latest_for_job = job_releases[0] if job_releases else None
        self.jobs.merge_result(
            job,
            {
                "ota_release_id": latest_for_job.id if latest_for_job else None,
                "ota_manifest_url": (
                    self.to_response(latest_for_job, request_origin).manifest_url if latest_for_job else None
                ),
                "ota_firmware_url": (
                    self.to_response(latest_for_job, request_origin).firmware_url if latest_for_job else None
                ),
            },
        )
        return {
            "deleted_release_id": release_id,
            "latest_release_id": remaining[0].id if remaining else None,
        }

    def to_response(self, record: OtaReleaseRecord, request_origin: str) -> OtaReleaseResponse:
        base = self.settings.ota_public_base_url or request_origin.rstrip("/")
        latest_url = (
            f"{base}/api/v2/ota/latest?"
            + urlencode({"project": record.project, "chip": record.chip, "channel": record.channel})
        )
        return OtaReleaseResponse(
            id=record.id,
            job_id=record.job_id,
            project=record.project,
            chip=record.chip,
            channel=record.channel,
            version=record.version,
            min_version=record.min_version,
            force=record.force,
            release_notes=record.release_notes,
            size=record.size,
            sha256=record.sha256,
            manifest_url=latest_url,
            manifest_direct_url=f"{base}/api/v2/ota/manifests/{record.id}",
            firmware_url=f"{base}/api/v2/ota/firmware/{record.id}",
            created_at=record.created_at,
        )
