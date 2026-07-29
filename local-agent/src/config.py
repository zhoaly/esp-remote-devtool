from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse, urlunparse


APP_DIR_NAME = "ESPRemoteBuildAgent"
DEFAULT_REMOTE_BUILD_URL = "http://127.0.0.1:8000/api/build/upload"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


@dataclass(slots=True)
class AgentSettings:
    remote_build_url: str
    default_project_name: str
    default_idf_image: str
    default_target: str
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    allowed_origins: list[str] = field(default_factory=list)
    exclude_dir_names: set[str] = field(default_factory=set)
    exclude_file_suffixes: set[str] = field(default_factory=set)
    config_path: Path | None = None
    data_dir: Path | None = None
    log_dir: Path | None = None


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_app_data_dir() -> Path:
    override = os.getenv("ESP_LOCAL_AGENT_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()

    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_DIR_NAME

    return Path.home() / "AppData" / "Local" / APP_DIR_NAME


def get_user_config_path() -> Path:
    override = os.getenv("ESP_LOCAL_AGENT_CONFIG_PATH")
    if override:
        return Path(override).expanduser().resolve()
    return get_app_data_dir() / "config.json"


def get_legacy_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config.json"


def get_log_dir() -> Path:
    return get_app_data_dir() / "logs"


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid agent configuration: {path}: {exc}") from exc

    if not isinstance(value, dict):
        raise ValueError(f"Agent configuration must contain a JSON object: {path}")
    return value


def _source_config_path() -> Path:
    user_path = get_user_config_path()
    if os.getenv("ESP_LOCAL_AGENT_CONFIG_PATH"):
        return user_path
    if user_path.exists():
        return user_path

    legacy_path = get_legacy_config_path()
    if not is_frozen() and legacy_path.exists():
        return legacy_path

    return user_path


def has_saved_configuration() -> bool:
    return _source_config_path().exists()


def _pick(
    config: dict[str, object],
    key: str,
    env_names: tuple[str, ...],
    default: str,
) -> str:
    for env_name in env_names:
        value = os.getenv(env_name)
        if value:
            return value

    config_value = config.get(key)
    if isinstance(config_value, str) and config_value.strip():
        return config_value.strip()
    return default


def validate_remote_build_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Remote build URL must be an absolute HTTP or HTTPS URL")
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, "")
    )


def derive_remote_origin(remote_build_url: str) -> str:
    parsed = urlparse(validate_remote_build_url(remote_build_url))
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


def derive_remote_ui_url(remote_build_url: str) -> str:
    return f"{derive_remote_origin(remote_build_url)}/tools/esp"


def derive_remote_info_url(remote_build_url: str) -> str:
    return f"{derive_remote_origin(remote_build_url)}/api/info"


def _derive_allowed_origins(remote_build_url: str) -> list[str]:
    origins = {
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        derive_remote_origin(remote_build_url),
    }
    return sorted(origins)


def load_settings() -> AgentSettings:
    source_path = _source_config_path()
    config = _load_json(source_path)

    remote_build_url = validate_remote_build_url(
        _pick(
            config,
            "remote_build_url",
            ("ESP_REMOTE_BUILD_URL", "REMOTE_BUILD_URL"),
            DEFAULT_REMOTE_BUILD_URL,
        )
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

    allowed_origins = config.get("allowed_origins")
    if not isinstance(allowed_origins, list) or not allowed_origins:
        allowed_origins = _derive_allowed_origins(remote_build_url)

    data_dir = get_app_data_dir()
    return AgentSettings(
        remote_build_url=remote_build_url,
        default_project_name=default_project_name,
        default_idf_image=default_idf_image,
        default_target=default_target,
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        allowed_origins=[str(item) for item in allowed_origins],
        exclude_dir_names={
            "build",
            ".git",
            ".vscode",
            "managed_components",
            "__pycache__",
        },
        exclude_file_suffixes={".pyc", ".pyo", ".log"},
        config_path=source_path if source_path.exists() else get_user_config_path(),
        data_dir=data_dir,
        log_dir=data_dir / "logs",
    )


def settings_to_user_dict(settings: AgentSettings) -> dict[str, str]:
    values = asdict(settings)
    return {
        "remote_build_url": str(values["remote_build_url"]),
        "default_project_name": str(values["default_project_name"]),
        "default_idf_image": str(values["default_idf_image"]),
        "default_target": str(values["default_target"]),
    }


def save_user_settings(values: dict[str, str]) -> Path:
    remote_build_url = validate_remote_build_url(values.get("remote_build_url", ""))
    required = {
        "default_project_name": values.get("default_project_name", "").strip(),
        "default_idf_image": values.get("default_idf_image", "").strip(),
        "default_target": values.get("default_target", "").strip(),
    }
    for key, value in required.items():
        if not value:
            raise ValueError(f"{key} must not be empty")

    payload = {
        "remote_build_url": remote_build_url,
        **required,
    }
    config_path = get_user_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = config_path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, config_path)
    return config_path
