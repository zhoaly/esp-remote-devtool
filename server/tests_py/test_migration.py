from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from sqlalchemy import create_engine, inspect


def test_alembic_upgrades_empty_database(tmp_path: Path, monkeypatch) -> None:
    server_dir = Path(__file__).resolve().parents[1]
    base_dir = tmp_path / "server"
    base_dir.mkdir()
    monkeypatch.setenv("ESP_SERVER_BASE_DIR", str(base_dir))
    get_settings.cache_clear()
    try:
        config = Config(str(server_dir / "alembic.ini"))
        config.set_main_option("script_location", str(server_dir / "migrations"))
        command.upgrade(config, "head")
        tables = set(inspect(create_engine(f"sqlite:///{base_dir / 'data' / 'server.db'}")).get_table_names())
        assert {"alembic_version", "jobs", "job_events", "artifacts", "ota_releases"} <= tables
    finally:
        get_settings.cache_clear()
