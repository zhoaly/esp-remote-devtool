from __future__ import annotations

import pytest
from app.domain.jobs import JobStatus, can_transition
from app.domain.schemas import EspBuildConfiguration, LvglBuildConfiguration
from pydantic import ValidationError


def test_job_state_machine_allows_only_declared_transitions() -> None:
    assert can_transition(JobStatus.QUEUED, JobStatus.RUNNING)
    assert can_transition(JobStatus.QUEUED, JobStatus.CANCELED)
    for terminal in (
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.CANCELED,
        JobStatus.INTERRUPTED,
    ):
        assert not can_transition(terminal, JobStatus.RUNNING)
    assert not can_transition(JobStatus.RUNNING, JobStatus.QUEUED)


def test_build_configuration_validators_reject_unsafe_values() -> None:
    with pytest.raises(ValidationError):
        EspBuildConfiguration(project_name="../demo", target="esp32s3", idf_image="idf")
    with pytest.raises(ValidationError):
        LvglBuildConfiguration(
            project_name="demo",
            width=0,
            height=240,
            lvgl_version="9.x",
        )
