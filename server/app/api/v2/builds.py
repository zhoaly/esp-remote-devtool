from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from pydantic import ValidationError

from app.api.dependencies import get_build_service, get_job_service, get_settings
from app.core.config import Settings
from app.core.errors import AppError
from app.domain.jobs import JobKind, SourceMode
from app.domain.schemas import (
    EspBuildConfiguration,
    JobResponse,
    LvglBuildConfiguration,
    WorkspaceBuildRequest,
)
from app.services.builds import BuildSubmissionService
from app.services.jobs import JobService

router = APIRouter(prefix="/builds", tags=["builds"])


def _validation_error(exc: ValidationError) -> AppError:
    return AppError(
        "validation_error",
        "Request validation failed",
        status_code=422,
        details={"errors": exc.errors()},
    )


@router.post("/esp/workspace", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_esp_workspace(
    payload: WorkspaceBuildRequest,
    builds: BuildSubmissionService = Depends(get_build_service),
    jobs: JobService = Depends(get_job_service),
) -> JobResponse:
    return jobs.to_response(builds.submit_workspace(JobKind.ESP, payload))


@router.post("/esp/upload", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_esp_upload(
    file: Annotated[UploadFile, File()],
    project_name: Annotated[str | None, Form()] = None,
    idf_image: Annotated[str | None, Form()] = None,
    target: Annotated[str | None, Form()] = None,
    settings: Settings = Depends(get_settings),
    builds: BuildSubmissionService = Depends(get_build_service),
    jobs: JobService = Depends(get_job_service),
) -> JobResponse:
    try:
        config = EspBuildConfiguration(
            project_name=(
                settings.default_project_name if project_name is None else project_name
            ),
            target=settings.default_target if target is None else target,
            idf_image=settings.default_idf_image if idf_image is None else idf_image,
        )
    except ValidationError as exc:
        raise _validation_error(exc) from exc
    record = await builds.submit_upload(
        kind=JobKind.ESP,
        source_mode=SourceMode.UPLOAD,
        upload=file,
        configuration=config,
    )
    return jobs.to_response(record)


@router.post("/lvgl/workspace", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_lvgl_workspace(
    payload: WorkspaceBuildRequest,
    builds: BuildSubmissionService = Depends(get_build_service),
    jobs: JobService = Depends(get_job_service),
) -> JobResponse:
    return jobs.to_response(builds.submit_workspace(JobKind.LVGL, payload))


async def _submit_lvgl_upload(
    file: UploadFile,
    project_name: str,
    width: int | None,
    height: int | None,
    source_mode: SourceMode,
    settings: Settings,
    builds: BuildSubmissionService,
    jobs: JobService,
) -> JobResponse:
    try:
        config = LvglBuildConfiguration(
            project_name=project_name,
            width=settings.lvgl_default_width if width is None else width,
            height=settings.lvgl_default_height if height is None else height,
            lvgl_version=settings.lvgl_default_version,
        )
    except ValidationError as exc:
        raise _validation_error(exc) from exc
    record = await builds.submit_upload(
        kind=JobKind.LVGL,
        source_mode=source_mode,
        upload=file,
        configuration=config,
    )
    return jobs.to_response(record)


@router.post("/lvgl/upload", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_lvgl_upload(
    file: Annotated[UploadFile, File()],
    project_name: Annotated[str, Form()] = "lvgl_project",
    width: Annotated[int | None, Form()] = None,
    height: Annotated[int | None, Form()] = None,
    settings: Settings = Depends(get_settings),
    builds: BuildSubmissionService = Depends(get_build_service),
    jobs: JobService = Depends(get_job_service),
) -> JobResponse:
    return await _submit_lvgl_upload(
        file, project_name, width, height, SourceMode.UPLOAD, settings, builds, jobs
    )


@router.post("/lvgl/ui-upload", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_lvgl_ui_upload(
    file: Annotated[UploadFile, File()],
    project_name: Annotated[str, Form()] = "lvgl_ui",
    width: Annotated[int | None, Form()] = None,
    height: Annotated[int | None, Form()] = None,
    settings: Settings = Depends(get_settings),
    builds: BuildSubmissionService = Depends(get_build_service),
    jobs: JobService = Depends(get_job_service),
) -> JobResponse:
    return await _submit_lvgl_upload(
        file, project_name, width, height, SourceMode.UI_UPLOAD, settings, builds, jobs
    )
