from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.builds import BuildSubmissionService
from app.services.jobs import JobService
from app.services.ota import OtaService
from app.services.registry import RegistryService
from app.services.workspaces import WorkspaceService
from app.storage.repositories import ArtifactRepository, JobRepository, OtaRepository


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_workspace_service(settings: Settings = Depends(get_settings)) -> WorkspaceService:
    return WorkspaceService(settings)


def get_job_service(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> JobService:
    return JobService(settings, JobRepository(session), ArtifactRepository(session))


def get_build_service(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
    workspaces: WorkspaceService = Depends(get_workspace_service),
) -> BuildSubmissionService:
    return BuildSubmissionService(settings, JobRepository(session), workspaces)


def get_ota_service(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> OtaService:
    return OtaService(
        settings,
        JobRepository(session),
        ArtifactRepository(session),
        OtaRepository(session),
    )


def get_registry_service(settings: Settings = Depends(get_settings)) -> RegistryService:
    return RegistryService(settings)
