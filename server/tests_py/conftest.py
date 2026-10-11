from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from app.core.config import get_settings
from app.storage.database import create_database_engine, create_session_factory
from app.storage.models import Base


@pytest.fixture()
def settings(tmp_path: Path):
    base = get_settings()
    data = tmp_path / "data"
    value = replace(
        base,
        base_dir=tmp_path,
        data_dir=data,
        upload_dir=data / "uploads",
        workspace_dir=data / "workspaces",
        artifact_dir=data / "artifacts",
        ota_release_dir=data / "ota" / "releases",
        lvgl_preview_dir=data / "lvgl" / "previews",
        log_dir=data / "logs",
        config_dir=tmp_path / "config",
        database_path=data / "server.db",
        worker_lock_path=data / "worker.lock",
    )
    value.ensure_directories()
    value.config_dir.mkdir(parents=True, exist_ok=True)
    return value


@pytest.fixture()
def database(settings):
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    try:
        yield engine, create_session_factory(engine)
    finally:
        engine.dispose()
