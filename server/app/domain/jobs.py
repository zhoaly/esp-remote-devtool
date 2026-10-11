from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType


class StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class JobKind(StringEnum):
    ESP = "esp"
    LVGL = "lvgl"


class SourceMode(StringEnum):
    WORKSPACE = "workspace"
    UPLOAD = "upload"
    UI_UPLOAD = "ui_upload"


class JobStatus(StringEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    INTERRUPTED = "interrupted"


class JobStage(StringEnum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    GENERATING = "generating"
    CHECKING = "checking"
    BUILDING = "building"
    PACKAGING = "packaging"
    COMPLETED = "completed"


TERMINAL_STATUSES = frozenset({
    JobStatus.SUCCEEDED,
    JobStatus.FAILED,
    JobStatus.CANCELED,
    JobStatus.INTERRUPTED,
})

ALLOWED_TRANSITIONS: Mapping[JobStatus, frozenset[JobStatus]] = MappingProxyType({
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELED}),
    JobStatus.RUNNING: frozenset({
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELED,
        JobStatus.INTERRUPTED,
    }),
})


def can_transition(current: JobStatus, target: JobStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())
