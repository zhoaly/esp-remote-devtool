from __future__ import annotations

import sys
import time

import pytest
from app.builders.process import BuildCanceled, BuildTimedOut, ProcessRunner


def test_process_runner_cancels_process_group(tmp_path) -> None:
    started = time.monotonic()
    with pytest.raises(BuildCanceled):
        ProcessRunner().run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            tmp_path / "cancel.log",
            timeout_seconds=30,
            cancel_requested=lambda: True,
        )
    assert time.monotonic() - started < 5


def test_process_runner_times_out(tmp_path) -> None:
    started = time.monotonic()
    with pytest.raises(BuildTimedOut):
        ProcessRunner().run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            tmp_path / "timeout.log",
            timeout_seconds=0,
            cancel_requested=lambda: False,
        )
    assert time.monotonic() - started < 5
