from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.domain.jobs import JobKind, JobStage, JobStatus, SourceMode

SafeIdentifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$"),
]


class EspBuildConfiguration(BaseModel):
    kind: Literal["esp"] = "esp"
    project_name: SafeIdentifier
    target: SafeIdentifier
    idf_image: str = Field(min_length=1, max_length=255)
    workspace_id: str | None = None


class LvglBuildConfiguration(BaseModel):
    kind: Literal["lvgl"] = "lvgl"
    project_name: SafeIdentifier
    width: int = Field(ge=120, le=4096)
    height: int = Field(ge=120, le=4096)
    lvgl_version: str
    workspace_id: str | None = None


BuildConfiguration = Annotated[
    EspBuildConfiguration | LvglBuildConfiguration,
    Field(discriminator="kind"),
]


class ArtifactResponse(BaseModel):
    id: str
    kind: str
    filename: str
    media_type: str
    size: int
    sha256: str
    url: str


class JobLinks(BaseModel):
    self: str
    logs: str
    preview: str | None = None


class JobResponse(BaseModel):
    id: str
    kind: JobKind
    source_mode: SourceMode
    status: JobStatus
    stage: JobStage
    message: str
    project_name: str
    configuration: BuildConfiguration
    result: dict[str, Any] | None = None
    artifacts: list[ArtifactResponse] = Field(default_factory=list)
    links: JobLinks
    retry_of_job_id: str | None = None
    cancel_requested: bool = False
    error_code: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    # Convenience fields retained for the small vanilla-JS client.
    target: str | None = None
    idf_image: str | None = None
    width: int | None = None
    height: int | None = None
    lvgl_version: str | None = None
    download_url: str | None = None
    artifact_url: str | None = None
    artifact_name: str | None = None
    preview_url: str | None = None
    log_url: str
    ota_publishable: bool = False
    ota_project_version: str | None = None
    ota_app_size: int | None = None
    ota_app_sha256: str | None = None
    ota_app_bin_name: str | None = None
    ota_partition_limit: int | None = None
    ota_manifest_url: str | None = None
    ota_firmware_url: str | None = None
    ota_release_id: str | None = None


class LogChunkResponse(BaseModel):
    content: str
    next_offset: int
    complete: bool


class WorkspaceBuildRequest(BaseModel):
    workspace_id: SafeIdentifier
    project_name: SafeIdentifier | None = None
    idf_image: str | None = Field(default=None, max_length=255)
    width: int | None = Field(default=None, ge=120, le=4096)
    height: int | None = Field(default=None, ge=120, le=4096)


class OtaPublishRequest(BaseModel):
    job_id: str
    channel: SafeIdentifier = "test"
    version: str
    min_version: str = ""
    force: bool = False
    release_notes: str = Field(default="", max_length=20_000)

    @field_validator("version", "min_version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return value
        if re.fullmatch(r"\d+\.\d+", value):
            return f"{value}.0"
        if not re.fullmatch(r"\d+\.\d+\.\d+", value):
            raise ValueError("version must be x.y.z")
        return value


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody


class OtaReleaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    project: str
    chip: str
    channel: str
    version: str
    min_version: str
    force: bool
    release_notes: str
    size: int
    sha256: str
    manifest_url: str
    manifest_direct_url: str
    firmware_url: str
    created_at: datetime
