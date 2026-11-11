from pathlib import Path
from typing import Annotated, Any

import requests
from config import AgentSettings, derive_remote_origin, load_settings
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from flasher import flash_firmware
from project_zip import (
    create_lvgl_ui_package_zip,
    create_project_zip,
    validate_lvgl_project_dir,
    validate_project_dir,
)
from pydantic import BaseModel, Field
from remote_upload import (
    upload_lvgl_project_zip,
    upload_lvgl_ui_package_zip,
    upload_project_zip,
)
from serial_ports import list_serial_ports


class FlashFromArtifactRequest(BaseModel):
    artifact_url: str
    com_port: str = "COM7"
    baud: int = 460800
    chip: str = "esp32s3"


class BuildLvglFromPathRequest(BaseModel):
    project_path: str = Field(
        ..., description="Local standalone LVGL CMake project path on Windows"
    )
    project_name: str = "lvgl_project"
    width: int = 480
    height: int = 480


class BuildLvglUiFromPathRequest(BaseModel):
    project_path: str = Field(..., description="Local LVGL project path on Windows")
    project_name: str = "lvgl_ui"
    width: int = 480
    height: int = 480
    ui_roots: list[str] = Field(default_factory=list)
    include_dirs: list[str] = Field(default_factory=list)
    entry_call: str = "ui_init"
    entry_header: str = "ui.h"


def create_app(settings: AgentSettings) -> FastAPI:
    class BuildFromPathRequest(BaseModel):
        project_path: str = Field(
            ..., description="Local ESP-IDF project path on Windows"
        )
        project_name: str = Field(default=settings.default_project_name)
        idf_image: str = Field(default=settings.default_idf_image)
        target: str = Field(default=settings.default_target)

    app = FastAPI(title="ESP Local Upload Agent", version="0.2.0")
    app.state.agent_settings = settings

    default_origin = derive_remote_origin(settings.remote_build_url)
    build_servers = settings.remote_build_servers
    allowed_origins = settings.allowed_origins
    if build_servers:
        allowed_origins = sorted({*allowed_origins, default_origin, *build_servers})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_private_network=True,
    )

    def resolve_build_url(origin: Annotated[str | None, Header()] = None) -> str:
        if origin is None or not build_servers:
            return settings.remote_build_url
        if origin in build_servers:
            return build_servers[origin]
        if origin == default_origin:
            return settings.remote_build_url
        raise HTTPException(status_code=403, detail="Build server is not configured for this origin")

    @app.get("/")
    def index(origin: Annotated[str | None, Header()] = None) -> dict[str, str]:
        return {
            "name": "ESP Local Upload Agent",
            "status": "running",
            "remote_build_url": resolve_build_url(origin),
        }

    @app.get("/api/serial_ports")
    def get_serial_ports() -> dict[str, object]:
        return list_serial_ports()

    @app.post("/api/flash_from_artifact")
    def flash_from_artifact(req: FlashFromArtifactRequest) -> dict[str, object]:
        try:
            return flash_firmware(
                req.artifact_url,
                req.com_port,
                req.baud,
                req.chip,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Flash failed",
                    "log": str(exc),
                },
            ) from exc

    @app.post("/api/build_from_path")
    def build_from_path(
        req: BuildFromPathRequest, remote_build_url: Annotated[str, Depends(resolve_build_url)]
    ) -> dict[str, Any]:
        project_dir = Path(req.project_path).expanduser().resolve()

        try:
            validate_project_dir(project_dir)
            zip_path = create_project_zip(
                project_dir,
                settings.exclude_dir_names,
                settings.exclude_file_suffixes,
            )
            return upload_project_zip(
                remote_build_url,
                str(zip_path),
                req.project_name,
                req.idf_image,
                req.target,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Failed to upload build package",
                    "error": str(exc),
                },
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Remote build server returned error",
                    "text": str(exc),
                },
            ) from exc

    @app.post("/api/lvgl/build_from_path")
    def build_lvgl_from_path(
        req: BuildLvglFromPathRequest, remote_build_url: Annotated[str, Depends(resolve_build_url)]
    ) -> dict[str, Any]:
        project_dir = Path(req.project_path).expanduser().resolve()

        try:
            validate_lvgl_project_dir(project_dir)
            zip_path = create_project_zip(
                project_dir,
                settings.exclude_dir_names,
                settings.exclude_file_suffixes,
            )
            return upload_lvgl_project_zip(
                remote_build_url,
                str(zip_path),
                req.project_name,
                req.width,
                req.height,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Failed to upload LVGL build package",
                    "error": str(exc),
                },
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Remote LVGL build server returned error",
                    "text": str(exc),
                },
            ) from exc

    @app.post("/api/lvgl/build_ui_from_path")
    def build_lvgl_ui_from_path(
        req: BuildLvglUiFromPathRequest,
        remote_build_url: Annotated[str, Depends(resolve_build_url)],
    ) -> dict[str, Any]:
        project_dir = Path(req.project_path).expanduser().resolve()

        try:
            zip_path = create_lvgl_ui_package_zip(
                project_dir,
                req.project_name,
                req.width,
                req.height,
                req.ui_roots,
                req.include_dirs,
                req.entry_call,
                req.entry_header,
                settings.exclude_dir_names,
                settings.exclude_file_suffixes,
            )
            return upload_lvgl_ui_package_zip(
                remote_build_url,
                str(zip_path),
                req.project_name,
                req.width,
                req.height,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except requests.RequestException as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Failed to upload LVGL UI package",
                    "error": str(exc),
                },
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Remote LVGL UI build server returned error",
                    "text": str(exc),
                },
            ) from exc

    return app


settings = load_settings()
app = create_app(settings)
