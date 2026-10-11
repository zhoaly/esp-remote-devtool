from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Protocol

from app.core.config import Settings
from app.core.errors import AppError
from app.domain.jobs import JobKind, SourceMode
from app.domain.schemas import EspBuildConfiguration, LvglBuildConfiguration, WorkspaceBuildRequest
from app.services.workspaces import WorkspaceService
from app.storage.models import JobRecord
from app.storage.repositories import JobRepository

IDF_IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$")


class AsyncUpload(Protocol):
    filename: str | None

    async def read(self, size: int = -1) -> bytes: ...


class BuildSubmissionService:
    def __init__(
        self,
        settings: Settings,
        jobs: JobRepository,
        workspaces: WorkspaceService,
    ) -> None:
        self.settings = settings
        self.jobs = jobs
        self.workspaces = workspaces

    def submit_workspace(self, kind: JobKind, payload: WorkspaceBuildRequest) -> JobRecord:
        workspace = self.workspaces.get(payload.workspace_id, kind.value)
        workspace_path = self.workspaces.resolved_path(workspace)
        if kind == JobKind.ESP:
            project_name = payload.project_name or str(workspace.get("project_name") or payload.workspace_id)
            idf_image = payload.idf_image or str(workspace.get("idf_image") or self.settings.default_idf_image)
            self._validate_idf_image(idf_image, self.workspaces.idf_images(workspace))
            config = EspBuildConfiguration(
                project_name=project_name,
                target=str(workspace.get("target") or self.settings.default_target),
                idf_image=idf_image,
                workspace_id=payload.workspace_id,
            )
        else:
            project_name = payload.project_name or str(workspace.get("project_name") or payload.workspace_id)
            config = LvglBuildConfiguration(
                project_name=project_name,
                width=payload.width or int(workspace.get("width") or self.settings.lvgl_default_width),
                height=payload.height or int(workspace.get("height") or self.settings.lvgl_default_height),
                lvgl_version=str(workspace.get("lvgl_version") or self.settings.lvgl_default_version),
                workspace_id=payload.workspace_id,
            )
        request_json = config.model_dump()
        request_json["workspace_path"] = workspace_path
        return self._create_job(kind, SourceMode.WORKSPACE, config.project_name, request_json)

    async def submit_upload(
        self,
        *,
        kind: JobKind,
        source_mode: SourceMode,
        upload: AsyncUpload,
        configuration: EspBuildConfiguration | LvglBuildConfiguration,
    ) -> JobRecord:
        if not upload.filename or not upload.filename.lower().endswith(".zip"):
            raise AppError("invalid_upload", "Only .zip files are supported")
        if kind == JobKind.ESP:
            assert isinstance(configuration, EspBuildConfiguration)
            self._validate_idf_image(configuration.idf_image)

        job_id = uuid.uuid4().hex
        suffix = "_lvgl.zip" if kind == JobKind.LVGL else ".zip"
        upload_path = self.settings.upload_dir / f"{job_id}{suffix}"
        workspace_path = self.settings.workspace_dir / (
            f"{job_id}_lvgl" if kind == JobKind.LVGL else job_id
        )
        max_size = self.settings.lvgl_max_upload_size if kind == JobKind.LVGL else self.settings.max_upload_size
        try:
            await self._save_upload(upload, upload_path, max_size)
            return self._create_job(
                kind,
                source_mode,
                configuration.project_name,
                configuration.model_dump(),
                job_id=job_id,
                upload_path=str(upload_path),
                workspace_path=str(workspace_path),
            )
        except Exception:
            upload_path.unlink(missing_ok=True)
            shutil.rmtree(workspace_path, ignore_errors=True)
            raise

    def _create_job(
        self,
        kind: JobKind,
        source_mode: SourceMode,
        project_name: str,
        request_json: dict[str, Any],
        *,
        job_id: str | None = None,
        upload_path: str | None = None,
        workspace_path: str | None = None,
        retry_of_job_id: str | None = None,
    ) -> JobRecord:
        actual_id = job_id or uuid.uuid4().hex
        return self.jobs.create(
            kind=kind,
            source_mode=source_mode.value,
            project_name=project_name,
            request_json=request_json,
            log_path=str(self.settings.log_dir / f"{actual_id}.log"),
            upload_path=upload_path,
            workspace_path=workspace_path,
            retry_of_job_id=retry_of_job_id,
            job_id=actual_id,
        )

    async def _save_upload(self, upload: AsyncUpload, path: Path, max_size: int) -> None:
        size = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_size:
                    raise AppError("upload_too_large", "Uploaded file is too large", status_code=413)
                output.write(chunk)

    def _validate_idf_image(self, image: str, allowed: list[str] | None = None) -> None:
        allowed_images = allowed or self.workspaces.idf_images()
        if image in allowed_images:
            return
        if not self.settings.allow_custom_idf_image:
            raise AppError("idf_image_not_allowed", f"IDF image is not allowed: {image}")
        if not IDF_IMAGE_RE.fullmatch(image):
            raise AppError("invalid_idf_image", "Invalid IDF Docker image")
