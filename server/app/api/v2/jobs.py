from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse, RedirectResponse

from app.api.dependencies import get_job_service
from app.domain.jobs import JobKind, JobStatus
from app.domain.schemas import JobResponse, LogChunkResponse
from app.services.jobs import JobService

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs(
    kind: JobKind | None = None,
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: JobService = Depends(get_job_service),
) -> list[JobResponse]:
    return service.list(kind=kind, status=status_filter, limit=limit, offset=offset)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, service: JobService = Depends(get_job_service)) -> JobResponse:
    return service.get(job_id)


@router.get("/jobs/{job_id}/logs", response_model=LogChunkResponse)
def get_job_logs(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=65536, ge=1, le=1024 * 1024),
    service: JobService = Depends(get_job_service),
) -> LogChunkResponse:
    return service.read_log(job_id, offset, limit)


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: str, service: JobService = Depends(get_job_service)) -> JobResponse:
    return service.cancel(job_id)


@router.post(
    "/jobs/{job_id}/retry",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_job(job_id: str, service: JobService = Depends(get_job_service)) -> JobResponse:
    return service.retry(job_id)


@router.get("/artifacts/{artifact_id}")
def download_artifact(
    artifact_id: str, service: JobService = Depends(get_job_service)
) -> FileResponse:
    download = service.artifact_download(artifact_id)
    return FileResponse(download.path, media_type=download.media_type, filename=download.filename)


@router.get("/jobs/{job_id}/preview")
def preview_index(job_id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/api/v2/jobs/{job_id}/preview/index.html")


@router.get("/jobs/{job_id}/preview/{asset_path:path}")
def preview_asset(
    job_id: str,
    asset_path: str,
    service: JobService = Depends(get_job_service),
) -> FileResponse:
    download = service.preview_asset(job_id, asset_path)
    return FileResponse(
        download.path,
        media_type=download.media_type,
        headers={"Cache-Control": download.cache_control or "no-store"},
    )
