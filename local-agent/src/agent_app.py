from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import load_settings
from flasher import flash_firmware
from project_zip import create_project_zip, validate_project_dir
from remote_upload import upload_project_zip
from serial_ports import list_serial_ports


settings = load_settings()


class BuildFromPathRequest(BaseModel):
    project_path: str = Field(..., description="Local ESP-IDF project path on Windows")
    project_name: str = Field(default=settings.default_project_name)
    idf_image: str = Field(default=settings.default_idf_image)
    target: str = Field(default=settings.default_target)


class FlashFromArtifactRequest(BaseModel):
    artifact_url: str
    com_port: str = "COM7"
    baud: int = 460800
    chip: str = "esp32s3"


app = FastAPI(title="ESP Local Upload Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_private_network=True,
)


@app.get("/")
def index() -> dict[str, str]:
    return {
        "name": "ESP Local Upload Agent",
        "status": "running",
        "remote_build_url": settings.remote_build_url,
    }


@app.get("/api/serial_ports")
def get_serial_ports() -> dict[str, object]:
    return list_serial_ports()


@app.post("/api/flash_from_artifact")
def flash_from_artifact(req: FlashFromArtifactRequest) -> dict[str, object]:
    try:
        return flash_firmware(req.artifact_url, req.com_port, req.baud, req.chip)
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
def build_from_path(req: BuildFromPathRequest) -> dict[str, Any]:
    project_dir = Path(req.project_path).expanduser().resolve()

    try:
        validate_project_dir(project_dir)
        zip_path = create_project_zip(
            project_dir,
            settings.exclude_dir_names,
            settings.exclude_file_suffixes,
        )
        return upload_project_zip(
            settings.remote_build_url,
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
