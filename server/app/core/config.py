from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(frozen=True, slots=True)
class Settings:
    base_dir: Path
    data_dir: Path
    upload_dir: Path
    workspace_dir: Path
    artifact_dir: Path
    ota_release_dir: Path
    lvgl_preview_dir: Path
    log_dir: Path
    static_dir: Path
    config_dir: Path
    database_path: Path
    worker_lock_path: Path
    build_script: Path
    package_script: Path
    lvgl_build_script: Path

    default_project_name: str
    default_idf_image: str
    default_target: str
    allowed_idf_images: tuple[str, ...]
    allow_custom_idf_image: bool
    max_upload_size: int
    max_build_records: int
    max_archive_entries: int
    max_archive_uncompressed_size: int
    max_archive_file_size: int

    ota_app_partition_size: int
    ota_public_base_url: str
    lvgl_default_width: int
    lvgl_default_height: int
    lvgl_default_version: str
    lvgl_emsdk_image: str
    lvgl_git_repo: str
    lvgl_git_ref: str
    lvgl_source_dir: str
    lvgl_sdl2_port_dir: str
    lvgl_emsdk_cache_dir: str
    lvgl_max_upload_size: int

    esp_build_timeout_seconds: int
    lvgl_build_timeout_seconds: int
    worker_poll_seconds: float

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    @property
    def workspaces_config(self) -> Path:
        return self.config_dir / "workspaces.json"

    @property
    def home_tools_config(self) -> Path:
        return self.config_dir / "home_tools.json"

    def ensure_directories(self) -> None:
        for directory in (
            self.data_dir,
            self.upload_dir,
            self.workspace_dir,
            self.artifact_dir,
            self.ota_release_dir,
            self.lvgl_preview_dir,
            self.log_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    base_dir = Path(os.getenv("ESP_SERVER_BASE_DIR", SERVER_DIR)).expanduser().resolve()
    data_dir = base_dir / "data"
    allowed_images = tuple(
        image.strip()
        for image in os.getenv(
            "ESP_ALLOWED_IDF_IMAGES",
            "espressif/idf:v4.4.8,espressif/idf:v5.0.8,espressif/idf:v5.1.6,"
            "espressif/idf:v5.2.5,espressif/idf:v5.3.4,espressif/idf:v5.4.2,"
            "espressif/idf:v5.5.1,espressif/idf:v6.0.1,espressif/idf:v6.0.2",
        ).split(",")
        if image.strip()
    )
    max_upload_mb = _env_int("ESP_MAX_UPLOAD_SIZE_MB", 200)
    lvgl_max_upload_mb = _env_int("LVGL_MAX_UPLOAD_SIZE_MB", max_upload_mb)

    return Settings(
        base_dir=base_dir,
        data_dir=data_dir,
        upload_dir=data_dir / "uploads",
        workspace_dir=data_dir / "workspaces",
        artifact_dir=data_dir / "artifacts",
        ota_release_dir=data_dir / "ota" / "releases",
        lvgl_preview_dir=data_dir / "lvgl" / "previews",
        log_dir=data_dir / "logs",
        static_dir=base_dir / "app" / "static",
        config_dir=base_dir / "config",
        database_path=data_dir / "server.db",
        worker_lock_path=data_dir / "worker.lock",
        build_script=base_dir / "scripts" / "build_uploaded_project.sh",
        package_script=base_dir / "scripts" / "package_firmware.sh",
        lvgl_build_script=base_dir / "scripts" / "build_lvgl_wasm_project.sh",
        default_project_name=os.getenv("ESP_DEFAULT_PROJECT_NAME", "ESP32_S3_wifi_ble_hub"),
        default_idf_image=os.getenv("ESP_DEFAULT_IDF_IMAGE", "espressif/idf:v6.0.1"),
        default_target=os.getenv("ESP_DEFAULT_TARGET", "esp32s3"),
        allowed_idf_images=allowed_images,
        allow_custom_idf_image=_env_bool("ESP_ALLOW_CUSTOM_IDF_IMAGE", False),
        max_upload_size=max_upload_mb * 1024 * 1024,
        max_build_records=_env_int("ESP_MAX_BUILD_RECORDS", 100),
        max_archive_entries=_env_int("ESP_MAX_ARCHIVE_ENTRIES", 20_000),
        max_archive_uncompressed_size=_env_int("ESP_MAX_ARCHIVE_UNCOMPRESSED_MB", 1024) * 1024 * 1024,
        max_archive_file_size=_env_int("ESP_MAX_ARCHIVE_FILE_MB", 256) * 1024 * 1024,
        ota_app_partition_size=_env_int("ESP_OTA_APP_PARTITION_SIZE", 6 * 1024 * 1024),
        ota_public_base_url=os.getenv("ESP_OTA_PUBLIC_BASE_URL", "").strip().rstrip("/"),
        lvgl_default_width=_env_int("LVGL_DEFAULT_WIDTH", 128),
        lvgl_default_height=_env_int("LVGL_DEFAULT_HEIGHT", 296),
        lvgl_default_version=os.getenv("LVGL_DEFAULT_VERSION", "9.x"),
        lvgl_emsdk_image=os.getenv("LVGL_EMSDK_IMAGE", "emscripten/emsdk:latest"),
        lvgl_git_repo=os.getenv("LVGL_GIT_REPO", "https://github.com/lvgl/lvgl.git"),
        lvgl_git_ref=os.getenv("LVGL_GIT_REF", "v9.3.0"),
        lvgl_source_dir=os.getenv("LVGL_SOURCE_DIR", "").strip(),
        lvgl_sdl2_port_dir=os.getenv("LVGL_SDL2_PORT_DIR", "").strip(),
        lvgl_emsdk_cache_dir=os.getenv("LVGL_EMSDK_CACHE_DIR", "").strip(),
        lvgl_max_upload_size=lvgl_max_upload_mb * 1024 * 1024,
        esp_build_timeout_seconds=_env_int("ESP_BUILD_TIMEOUT_SECONDS", 3600),
        lvgl_build_timeout_seconds=_env_int("LVGL_BUILD_TIMEOUT_SECONDS", 1800),
        worker_poll_seconds=float(os.getenv("ESP_WORKER_POLL_SECONDS", "1")),
    )
