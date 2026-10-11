from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse

from app.api.dependencies import get_ota_service
from app.domain.schemas import OtaPublishRequest, OtaReleaseResponse
from app.services.ota import OtaService

router = APIRouter(prefix="/ota", tags=["ota"])


def _origin(request: Request) -> str:
    return str(request.base_url).rstrip("/")


@router.post("/releases", response_model=OtaReleaseResponse, status_code=status.HTTP_201_CREATED)
def publish_release(
    payload: OtaPublishRequest,
    request: Request,
    service: OtaService = Depends(get_ota_service),
) -> OtaReleaseResponse:
    return service.publish(payload, _origin(request))


@router.get("/releases")
def list_releases(
    request: Request,
    project: str | None = None,
    chip: str | None = None,
    channel: str | None = None,
    service: OtaService = Depends(get_ota_service),
) -> dict[str, list[OtaReleaseResponse]]:
    return {
        "releases": service.list(
            _origin(request), project=project, chip=chip, channel=channel
        )
    }


@router.delete("/releases/{release_id}")
def delete_release(
    release_id: str,
    request: Request,
    service: OtaService = Depends(get_ota_service),
) -> dict[str, object]:
    return service.delete(release_id, _origin(request))


@router.get("/latest")
def latest_manifest(
    project: str,
    chip: str,
    request: Request,
    channel: str = "stable",
    service: OtaService = Depends(get_ota_service),
) -> dict[str, object]:
    return service.latest_manifest(project, chip, channel, _origin(request))


@router.get("/manifests/{release_id}")
def release_manifest(
    release_id: str,
    request: Request,
    service: OtaService = Depends(get_ota_service),
) -> dict[str, object]:
    return service.release_manifest(release_id, _origin(request))


@router.get("/firmware/{release_id}")
def release_firmware(
    release_id: str,
    service: OtaService = Depends(get_ota_service),
) -> FileResponse:
    download = service.firmware_download(release_id)
    return FileResponse(download.path, media_type=download.media_type, filename=download.filename)
