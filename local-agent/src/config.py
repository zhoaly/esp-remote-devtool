from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_REMOTE_BUILD_URL = "http://127.0.0.1:8000/api/build/upload"


@dataclass(slots=True)
class AgentSettings:
    remote_build_url: str
    default_project_name: str
    default_idf_image: str
    default_target: str
    host: str
    port: int
    allowed_origins: list[str] = field(default_factory=list)
    exclude_dir_names: set[str] = field(default_factory=set)
    exclude_file_suffixes: set[str] = field(default_factory=set)
    config_path: Path | None = None


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _pick(config: dict[str, object], key: str, env_names: tuple[str, ...], default: str) -> str:
    for env_name in env_names:
        value = os.getenv(env_name)
        if value:
            return value
    config_value = config.get(key)
    if isinstance(config_value, str) and config_value:
        return config_value
    return default


def _derive_allowed_origins(remote_build_url: str) -> list[str]:
    parsed = urlparse(remote_build_url)
    origins = {
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    }
    if parsed.scheme and parsed.netloc:
        origins.add(f"{parsed.scheme}://{parsed.netloc}")
    return sorted(origins)


def load_settings() -> AgentSettings:
    config_path = Path(__file__).resolve().parents[1] / "config.json"
    config = _load_json(config_path)

    remote_build_url = _pick(
        config,
        "remote_build_url",
        ("ESP_REMOTE_BUILD_URL", "REMOTE_BUILD_URL"),
        DEFAULT_REMOTE_BUILD_URL,
    )
    default_project_name = _pick(
        config,
        "default_project_name",
        ("ESP_DEFAULT_PROJECT_NAME", "DEFAULT_PROJECT_NAME"),
        "ESP32_S3_wifi_ble_hub",
    )
    default_idf_image = _pick(
        config,
        "default_idf_image",
        ("ESP_DEFAULT_IDF_IMAGE", "DEFAULT_IDF_IMAGE"),
        "espressif/idf:v6.0.1",
    )
    default_target = _pick(
        config,
        "default_target",
        ("ESP_DEFAULT_TARGET", "DEFAULT_TARGET"),
        "esp32s3",
    )
    host = _pick(
        config,
        "host",
        ("ESP_LOCAL_AGENT_HOST",),
        "127.0.0.1",
    )
    port = int(_pick(config, "port", ("ESP_LOCAL_AGENT_PORT",), "8765"))

    allowed_origins = config.get("allowed_origins")
    if not isinstance(allowed_origins, list) or not allowed_origins:
        allowed_origins = _derive_allowed_origins(remote_build_url)

    return AgentSettings(
        remote_build_url=remote_build_url,
        default_project_name=default_project_name,
        default_idf_image=default_idf_image,
        default_target=default_target,
        host=host,
        port=port,
        allowed_origins=[str(item) for item in allowed_origins],
        exclude_dir_names={
            "build",
            ".git",
            ".vscode",
            "managed_components",
            "__pycache__",
        },
        exclude_file_suffixes={".pyc", ".pyo", ".log"},
        config_path=config_path if config_path.exists() else None,
    )
