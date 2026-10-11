from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, RedirectResponse

from app.api.dependencies import get_settings
from app.core.config import Settings
from app.core.errors import NotFoundError

router = APIRouter(include_in_schema=False)


def _page(settings: Settings, relative_path: str) -> FileResponse:
    path = settings.static_dir / relative_path
    if not path.is_file():
        raise NotFoundError("ui_not_found", "UI page not found")
    return FileResponse(path)


@router.get("/")
def index() -> RedirectResponse:
    return RedirectResponse(url="/home")


@router.get("/home")
def home(settings: Settings = Depends(get_settings)) -> FileResponse:
    return _page(settings, "home.html")


@router.get("/tools/esp")
def esp_home(settings: Settings = Depends(get_settings)) -> FileResponse:
    return _page(settings, "index.html")


@router.get("/tools/esp/{page}")
def esp_page(page: str, settings: Settings = Depends(get_settings)) -> FileResponse:
    allowed = {"build", "flash", "ota", "jobs", "settings"}
    if page not in allowed:
        raise NotFoundError("ui_not_found", "UI page not found")
    return _page(settings, f"pages/{page}.html")


@router.get("/tools/lvgl")
def lvgl_home(settings: Settings = Depends(get_settings)) -> FileResponse:
    return _page(settings, "pages/lvgl.html")


@router.get("/tools/lvgl/{page}")
def lvgl_page(page: str, settings: Settings = Depends(get_settings)) -> FileResponse:
    allowed = {"build", "preview", "jobs", "settings"}
    if page not in allowed:
        raise NotFoundError("ui_not_found", "UI page not found")
    return _page(settings, f"pages/lvgl-{page}.html")


@router.get("/ui{path:path}")
def legacy_ui_redirect(path: str) -> RedirectResponse:
    mapping = {
        "": "/tools/esp",
        "/build": "/tools/esp/build",
        "/flash": "/tools/esp/flash",
        "/ota": "/tools/esp/ota",
        "/jobs": "/tools/esp/jobs",
        "/settings": "/tools/esp/settings",
    }
    return RedirectResponse(url=mapping.get(path, "/tools/esp"))
