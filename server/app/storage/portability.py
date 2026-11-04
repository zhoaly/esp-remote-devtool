from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath

from filelock import FileLock
from sqlalchemy import select

from app.core.config import Settings
from app.domain.jobs import JobStatus
from app.storage.database import create_database_engine, create_session_factory
from app.storage.models import ArtifactRecord, JobRecord


def portable_value(value: str, old_roots: list[str]) -> str:
    for root in old_roots:
        path_type = PureWindowsPath if PureWindowsPath(root).drive else PurePosixPath
        path, previous = path_type(value), path_type(root)
        if not previous.is_absolute():
            raise ValueError("--old-root must be an absolute data directory")
        try:
            relative = path.relative_to(previous)
        except ValueError:
            continue
        if ".." in relative.parts:
            raise ValueError("Legacy path escapes its data root")
        return relative.as_posix()
    return value


def relocate_data(settings: Settings, old_roots: list[str], *, apply: bool = False) -> dict:
    if not settings.database_path.is_file():
        raise RuntimeError(
            "Database does not exist; copy the stopped server's data directory first"
        )
    # Validate even an empty database's arguments.
    portable_value("", old_roots)
    with (
        FileLock(settings.data_dir / "server.lock", timeout=0),
        FileLock(settings.worker_lock_path, timeout=0),
    ):
        engine = create_database_engine(settings)
        changes = 0
        backup = None
        try:
            factory = create_session_factory(engine)
            with factory() as session:
                if session.scalar(
                    select(JobRecord.id).where(JobRecord.status == JobStatus.RUNNING.value).limit(1)
                ):
                    raise RuntimeError(
                        "Running job records remain; stop the old server cleanly before relocation"
                    )
                for job in session.scalars(select(JobRecord)):
                    for field in ("upload_path", "workspace_path", "log_path"):
                        value = getattr(job, field)
                        converted = portable_value(value, old_roots) if value else value
                        if converted != value:
                            setattr(job, field, converted)
                            changes += 1
                    for field, key in (
                        ("request_json", "workspace_path"),
                        ("result_json", "_ota_app_path"),
                    ):
                        payload = getattr(job, field) or {}
                        value = payload.get(key)
                        if value:
                            converted = portable_value(value, old_roots)
                            if converted != value:
                                setattr(job, field, {**payload, key: converted})
                                changes += 1
                for artifact in session.scalars(select(ArtifactRecord)):
                    converted = portable_value(artifact.path, old_roots)
                    if converted != artifact.path:
                        artifact.path = converted
                        changes += 1
                if apply and changes:
                    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                    backup = settings.database_path.with_name(
                        f"server.db.before-relocate-{stamp}.bak"
                    )
                    with (
                        sqlite3.connect(settings.database_path) as source,
                        sqlite3.connect(backup) as destination,
                    ):
                        source.backup(destination)
                    session.commit()
                else:
                    session.rollback()
        finally:
            engine.dispose()
    return {"changed_paths": changes, "applied": apply, "backup": str(backup) if backup else None}
