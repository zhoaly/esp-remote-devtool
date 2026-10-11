from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_registry_service, get_settings, get_workspace_service
from app.core.config import Settings
from app.services.registry import RegistryService
from app.services.workspaces import WorkspaceService

router = APIRouter(tags=["configuration"])


@router.get("/info")
def info(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {
        "name": "ESP Remote Build Server",
        "version": "0.2.0",
        "api_version": "v2",
        "docs": "/docs",
    }


@router.get("/home/tools")
def home_tools(service: RegistryService = Depends(get_registry_service)) -> dict[str, object]:
    return service.home_tools()


@router.get("/config/esp")
def esp_config(
    settings: Settings = Depends(get_settings),
    workspaces: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, object]:
    return {
        "default_project_name": settings.default_project_name,
        "default_idf_image": settings.default_idf_image,
        "default_target": settings.default_target,
        "allowed_idf_images": workspaces.idf_images(),
        "allow_custom_idf_image": settings.allow_custom_idf_image,
        "allow_custom": settings.allow_custom_idf_image,
    }


@router.get("/workspaces")
def list_workspaces(
    kind: Literal["esp", "lvgl"] = Query(...),
    settings: Settings = Depends(get_settings),
    service: WorkspaceService = Depends(get_workspace_service),
) -> dict[str, object]:
    response: dict[str, object] = {"kind": kind, "workspaces": service.list(kind)}
    if kind == "lvgl":
        response.update(
            default_width=settings.lvgl_default_width,
            default_height=settings.lvgl_default_height,
            default_lvgl_version=settings.lvgl_default_version,
            emsdk_image=settings.lvgl_emsdk_image,
        )
    return response
