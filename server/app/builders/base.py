from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.builders.process import ProcessRunner
from app.core.config import Settings
from app.domain.jobs import JobStage
from app.storage.models import JobRecord


@dataclass(frozen=True, slots=True)
class ArtifactSpec:
    kind: str
    path: Path
    media_type: str


@dataclass(frozen=True, slots=True)
class BuildOutput:
    result: dict[str, Any]
    artifacts: list[ArtifactSpec]


@dataclass(slots=True)
class BuildContext:
    settings: Settings
    job: JobRecord
    runner: ProcessRunner
    update_stage: Callable[[JobStage, str], None]
    cancel_requested: Callable[[], bool]
