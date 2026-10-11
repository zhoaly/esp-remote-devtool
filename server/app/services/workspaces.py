from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.errors import AppError, NotFoundError


class WorkspaceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _load(self) -> dict[str, dict[str, Any]]:
        path = self.settings.workspaces_config
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AppError("invalid_workspace_config", f"Invalid workspace config: {exc}", status_code=500) from exc
        workspaces = data.get("workspaces", data)
        if not isinstance(workspaces, dict):
            raise AppError("invalid_workspace_config", "workspaces.json must contain an object", status_code=500)
        return {str(key): value for key, value in workspaces.items() if isinstance(value, dict)}

    def get(self, workspace_id: str, kind: str) -> dict[str, Any]:
        config = self._load().get(workspace_id)
        if config is None:
            raise NotFoundError("workspace_not_found", "Workspace not found")
        project_type = str(config.get("project_type", "esp_idf"))
        if kind == "esp" and project_type not in {"esp_idf", "esp"}:
            raise NotFoundError("workspace_not_found", "ESP workspace not found")
        if kind == "lvgl" and project_type not in {"lvgl", "lvgl_web", "lvgl_simulator"}:
            raise NotFoundError("workspace_not_found", "LVGL workspace not found")
        return config

    def list(self, kind: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for workspace_id, config in self._load().items():
            project_type = str(config.get("project_type", "esp_idf"))
            is_match = (
                kind == "esp" and project_type in {"esp_idf", "esp"}
            ) or (
                kind == "lvgl" and project_type in {"lvgl", "lvgl_web", "lvgl_simulator"}
            )
            if not is_match:
                continue
            item = {
                "workspace_id": workspace_id,
                "display_name": config.get("display_name", workspace_id),
                "project_type": project_type,
                "project_name": config.get("project_name"),
            }
            if kind == "esp":
                item.update(
                    target=config.get("target", self.settings.default_target),
                    idf_image=config.get("idf_image", self.settings.default_idf_image),
                    idf_images=self.idf_images(config),
                )
            else:
                item.update(
                    width=config.get("width", self.settings.lvgl_default_width),
                    height=config.get("height", self.settings.lvgl_default_height),
                    lvgl_version=config.get("lvgl_version", self.settings.lvgl_default_version),
                )
            items.append(item)
        return items

    def idf_images(self, config: dict[str, Any] | None = None) -> list[str]:
        values: list[Any] = [self.settings.default_idf_image, *self.settings.allowed_idf_images]
        if config:
            values.extend(config.get("idf_images", []))
            values.append(config.get("idf_image"))
        result: list[str] = []
        for value in values:
            if isinstance(value, str) and value.strip() and value.strip() not in result:
                result.append(value.strip())
        return result

    @staticmethod
    def resolved_path(config: dict[str, Any]) -> str:
        value = config.get("path")
        if not isinstance(value, str) or not value.strip():
            raise AppError("invalid_workspace_config", "Workspace path is missing", status_code=500)
        path = Path(value).expanduser().resolve()
        if not path.is_dir():
            raise AppError("workspace_unavailable", "Configured workspace is unavailable", status_code=503)
        return str(path)
