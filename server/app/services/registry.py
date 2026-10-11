from __future__ import annotations

import json
from typing import Any

from app.core.config import Settings


def _default_registry() -> dict[str, Any]:
    return {
        "title": "ZLYHUB开发工具集",
        "subtitle": "统一管理远端开发工具、设备发布流程和后续个人服务。",
        "sections": [],
        "tools": [],
    }


class RegistryService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def home_tools(self) -> dict[str, Any]:
        path = self.settings.home_tools_config
        if not path.exists():
            return _default_registry()
        try:
            registry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _default_registry()
        if not isinstance(registry, dict):
            return _default_registry()
        defaults = _default_registry()
        sections = self._ordered(registry.get("sections"))
        enabled_sections = {str(item.get("id")) for item in sections}
        tools = [
            item
            for item in self._ordered(registry.get("tools"))
            if str(item.get("section_id")) in enabled_sections
        ]
        return {
            "title": registry.get("title", defaults["title"]),
            "subtitle": registry.get("subtitle", defaults["subtitle"]),
            "sections": sections,
            "tools": tools,
        }

    @staticmethod
    def _ordered(items: Any) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []
        enabled = [item for item in items if isinstance(item, dict) and item.get("enabled", True)]
        return sorted(enabled, key=lambda item: (int(item.get("order", 0)), str(item.get("id", ""))))
