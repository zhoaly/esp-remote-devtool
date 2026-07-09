from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles


app = FastAPI(title="ESP Remote Build Server", version="0.1.0")

SERVER_DIR = Path(__file__).resolve().parents[1]
BASE_DIR = Path(os.getenv("ESP_SERVER_BASE_DIR", SERVER_DIR)).resolve()
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
WORKSPACE_DIR = DATA_DIR / "workspaces"
ARTIFACT_DIR = DATA_DIR / "artifacts"
OTA_DIR = DATA_DIR / "ota"
OTA_RELEASE_DIR = OTA_DIR / "releases"
OTA_CHANNEL_DIR = OTA_DIR / "channels"
LOG_DIR = DATA_DIR / "logs"
JOB_DIR = DATA_DIR / "jobs"
STATIC_DIR = BASE_DIR / "app" / "static"
CONFIG_DIR = BASE_DIR / "config"
WORKSPACES_CONFIG = CONFIG_DIR / "workspaces.json"
HOME_TOOLS_CONFIG = CONFIG_DIR / "home_tools.json"

BUILD_SCRIPT = BASE_DIR / "scripts" / "build_uploaded_project.sh"
PACKAGE_SCRIPT = BASE_DIR / "scripts" / "package_firmware.sh"

DEFAULT_PROJECT_NAME = os.getenv("ESP_DEFAULT_PROJECT_NAME", "ESP32_S3_wifi_ble_hub")
DEFAULT_IDF_IMAGE = os.getenv("ESP_DEFAULT_IDF_IMAGE", "espressif/idf:v6.0.1")
DEFAULT_TARGET = os.getenv("ESP_DEFAULT_TARGET", "esp32s3")
DEFAULT_ALLOWED_IDF_IMAGES = [
    image.strip()
    for image in os.getenv(
        "ESP_ALLOWED_IDF_IMAGES",
        "espressif/idf:v4.4.8,espressif/idf:v5.0.8,espressif/idf:v5.1.6,espressif/idf:v5.2.5,espressif/idf:v5.3.4,espressif/idf:v5.4.2,espressif/idf:v5.5.1,espressif/idf:v6.0.1,espressif/idf:v6.0.2",
    ).split(",")
    if image.strip()
]
ALLOW_CUSTOM_IDF_IMAGE = os.getenv("ESP_ALLOW_CUSTOM_IDF_IMAGE", "1").lower() in {"1", "true", "yes", "on"}
MAX_UPLOAD_SIZE = int(os.getenv("ESP_MAX_UPLOAD_SIZE_MB", "200")) * 1024 * 1024
MAX_BUILD_RECORDS = int(os.getenv("ESP_MAX_BUILD_RECORDS", "100"))
OTA_APP_PARTITION_SIZE = int(os.getenv("ESP_OTA_APP_PARTITION_SIZE", str(6 * 1024 * 1024)))
OTA_PUBLIC_BASE_URL = os.getenv("ESP_OTA_PUBLIC_BASE_URL", "").strip().rstrip("/")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
VERSION_SHORT_RE = re.compile(r"^\d+\.\d+$")
IDF_IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$")

BUILD_LOCK = threading.Lock()

DEFAULT_HOME_TOOL_REGISTRY: Dict[str, Any] = {
    "title": "ZLYHUB开发工具集",
    "subtitle": "统一管理远端开发工具、设备发布流程和后续个人服务。",
    "sections": [],
    "tools": [],
}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

for directory in (UPLOAD_DIR, WORKSPACE_DIR, ARTIFACT_DIR, OTA_RELEASE_DIR, OTA_CHANNEL_DIR, LOG_DIR, JOB_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def make_job_id() -> str:
    return time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]


def job_file(job_id: str) -> Path:
    return JOB_DIR / f"{job_id}.json"


def log_file(job_id: str) -> Path:
    return LOG_DIR / f"{job_id}.log"


def is_managed_path(path: Path, allowed_roots: Tuple[Path, ...]) -> bool:
    resolved_path = path.expanduser().resolve()

    return any(resolved_path == root or root in resolved_path.parents for root in allowed_roots)


def remove_path_if_managed(path: Path, allowed_roots: Tuple[Path, ...]) -> None:
    if not is_managed_path(path, allowed_roots):
        return

    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def cleanup_job_record(job_id: str, data: Dict[str, Any], job_path: Path) -> None:
    managed_file_roots = (UPLOAD_DIR, ARTIFACT_DIR, LOG_DIR)
    managed_workspace_roots = (WORKSPACE_DIR,)

    for field in ("upload_file", "artifact", "log"):
        value = data.get(field)
        if value:
            remove_path_if_managed(Path(str(value)), managed_file_roots)

    artifact_name = data.get("artifact_name")
    if artifact_name:
        remove_path_if_managed(ARTIFACT_DIR / str(artifact_name), managed_file_roots)

    workspace = data.get("workspace")
    if workspace:
        remove_path_if_managed(Path(str(workspace)), managed_workspace_roots)

    remove_path_if_managed(UPLOAD_DIR / f"{job_id}.zip", managed_file_roots)
    remove_path_if_managed(LOG_DIR / f"{job_id}.log", managed_file_roots)
    for artifact_path in ARTIFACT_DIR.glob(f"*_{job_id}_firmware.zip"):
        remove_path_if_managed(artifact_path, managed_file_roots)
    remove_path_if_managed(WORKSPACE_DIR / job_id, managed_workspace_roots)

    job_path.unlink(missing_ok=True)


def cleanup_old_build_records() -> None:
    if MAX_BUILD_RECORDS < 1:
        return

    jobs: List[Tuple[str, str, Path, Dict[str, Any]]] = []

    for path in JOB_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}

        job_id = str(data.get("job_id") or path.stem)
        sort_key = str(data.get("created_at") or path.stem)
        jobs.append((sort_key, job_id, path, data))

    jobs.sort(key=lambda item: item[0], reverse=True)

    for _, job_id, path, data in jobs[MAX_BUILD_RECORDS:]:
        cleanup_job_record(job_id, data, path)


cleanup_old_build_records()


def save_job(job_id: str, data: Dict[str, Any]) -> None:
    data["job_id"] = job_id
    job_file(job_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_job(job_id: str) -> Dict[str, Any]:
    path = job_file(job_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Job not found")

    return json.loads(path.read_text(encoding="utf-8"))


def update_job(job_id: str, **kwargs: Any) -> None:
    data = load_job(job_id)
    data.update(kwargs)
    save_job(job_id, data)


def safe_extract(zip_path: Path, dest_dir: Path) -> None:
    dest_resolved = dest_dir.resolve()

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            target = (dest_dir / member.filename).resolve()

            if not str(target).startswith(str(dest_resolved)):
                raise RuntimeError(f"Unsafe zip path detected: {member.filename}")

        zf.extractall(dest_dir)


def find_project_root(workspace: Path) -> Path:
    candidates: List[Tuple[int, Path]] = []

    for cmake in workspace.rglob("CMakeLists.txt"):
        project_dir = cmake.parent
        has_main = (project_dir / "main").is_dir()
        has_components = (project_dir / "components").is_dir()

        if has_main or has_components:
            depth = len(project_dir.relative_to(workspace).parts)
            candidates.append((depth, project_dir))

    if not candidates:
        raise RuntimeError("ESP-IDF project root not found")

    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def run_command(command: List[str], log_path: Path) -> None:
    with log_path.open("a", encoding="utf-8") as log:
        log.write("\n")
        log.write("========== RUN COMMAND ==========\n")
        log.write(" ".join(command) + "\n")
        log.write("=================================\n")
        log.flush()

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        assert process.stdout is not None

        for line in process.stdout:
            log.write(line)
            log.flush()

        return_code = process.wait()

        if return_code != 0:
            raise RuntimeError(f"Command failed with exit code {return_code}")




def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(value: str, field: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value or ""):
        raise HTTPException(status_code=400, detail=f"Invalid {field}")
    return value


def unique_strings(values: List[Any]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def configured_idf_images(extra: Optional[List[Any]] = None) -> List[str]:
    values: List[Any] = [DEFAULT_IDF_IMAGE, *DEFAULT_ALLOWED_IDF_IMAGES]
    if extra:
        values.extend(extra)
    return unique_strings(values)


def validate_idf_image(idf_image: str, allowed_images: Optional[List[str]] = None) -> str:
    image = (idf_image or DEFAULT_IDF_IMAGE).strip()
    allowed = allowed_images or configured_idf_images()

    if image in allowed:
        return image

    if not ALLOW_CUSTOM_IDF_IMAGE:
        raise HTTPException(status_code=400, detail=f"IDF image is not allowed: {image}")

    if not IDF_IMAGE_RE.fullmatch(image):
        raise HTTPException(status_code=400, detail="Invalid IDF Docker image")

    return image


def parse_semver(version: str) -> Tuple[int, int, int]:
    if not VERSION_RE.fullmatch(version or ""):
        raise HTTPException(status_code=400, detail="version must be x.y.z")
    return tuple(int(part) for part in version.split("."))  # type: ignore[return-value]


def normalize_ota_version(version: Optional[str]) -> Optional[str]:
    if not version:
        return None

    normalized = str(version).strip()
    if VERSION_SHORT_RE.fullmatch(normalized):
        return f"{normalized}.0"

    return normalized


def absolute_url(request: Request, path: str) -> str:
    base_url = OTA_PUBLIC_BASE_URL or str(request.url_for("index")).rstrip("/")
    return base_url + path


def ota_latest_path(project: str, chip: str, channel: str) -> str:
    query = urlencode({"project": project, "chip": chip, "channel": channel})
    return f"/api/ota/latest?{query}"


def ota_manifest_path(release_id: str) -> str:
    return f"/api/ota/manifest/{release_id}"


def ota_firmware_path(release_id: str) -> str:
    return f"/api/ota/firmware/{release_id}/app.bin"


def ota_release_urls(request: Request, meta: Dict[str, Any]) -> Dict[str, str]:
    release_id = safe_name(str(meta.get("release_id") or ""), "release_id")
    project = safe_name(str(meta.get("project") or ""), "project")
    chip = safe_name(str(meta.get("chip") or ""), "chip")
    channel = safe_name(str(meta.get("channel") or "stable"), "channel")

    return {
        "manifest_url": absolute_url(request, ota_latest_path(project, chip, channel)),
        "manifest_direct_url": absolute_url(request, ota_manifest_path(release_id)),
        "firmware_url": absolute_url(request, ota_firmware_path(release_id)),
    }


def manifest_with_current_urls(request: Request, release_id: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    current = dict(manifest)
    current["url"] = absolute_url(request, ota_firmware_path(release_id))
    return current


def meta_with_current_urls(request: Request, meta: Dict[str, Any]) -> Dict[str, Any]:
    current = dict(meta)
    urls = ota_release_urls(request, current)
    current.update(urls)
    current["url"] = urls["firmware_url"]
    return current


def read_project_version(project_dir: Path) -> Optional[str]:
    desc = project_dir / "build" / "project_description.json"
    if not desc.exists():
        return None
    try:
        data = json.loads(desc.read_text(encoding="utf-8"))
    except Exception:
        return None
    version = data.get("version")
    return normalize_ota_version(str(version)) if version else None


def find_app_bin(project_dir: Path) -> Path:
    build_dir = project_dir / "build"
    candidates = sorted(
        p for p in build_dir.glob("*.bin")
        if p.name not in {"firmware_merged.bin"} and p.is_file()
    )
    if not candidates:
        raise RuntimeError("app bin not found in build/")
    return candidates[0]


def collect_ota_build_info(job_id: str, project_dir: Path, project_name: str, target: str) -> Dict[str, Any]:
    app_bin = find_app_bin(project_dir)
    app_size = app_bin.stat().st_size
    app_sha256 = sha256_file(app_bin)
    return {
        "ota_app_bin": str(app_bin),
        "ota_app_bin_name": app_bin.name,
        "ota_app_size": app_size,
        "ota_app_sha256": app_sha256,
        "ota_publishable": app_size <= OTA_APP_PARTITION_SIZE,
        "ota_partition_limit": OTA_APP_PARTITION_SIZE,
        "project_version": read_project_version(project_dir),
        "project_name": project_name,
        "target": target,
    }


def channel_manifest_path(channel: str, project: str, chip: str) -> Path:
    return OTA_CHANNEL_DIR / channel / f"{project}_{chip}.json"


def latest_channel_manifest(channel: str, project: str, chip: str) -> Optional[Dict[str, Any]]:
    path = channel_manifest_path(channel, project, chip)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_ota_release_meta(release_id: str) -> Dict[str, Any]:
    path = OTA_RELEASE_DIR / release_id / "meta.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="OTA release not found")
    return json.loads(path.read_text(encoding="utf-8"))


def list_ota_release_meta(
    project: Optional[str] = None,
    chip: Optional[str] = None,
    channel: Optional[str] = None,
    job_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    releases: List[Dict[str, Any]] = []
    for meta_path in OTA_RELEASE_DIR.glob("*/meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if project and meta.get("project") != project:
            continue
        if chip and meta.get("chip") != chip:
            continue
        if channel and meta.get("channel") != channel:
            continue
        if job_id and meta.get("job_id") != job_id:
            continue
        releases.append(meta)

    releases.sort(key=lambda item: str(item.get("created_at") or item.get("release_id") or ""), reverse=True)
    return releases


def refresh_ota_channel_latest(project: str, chip: str, channel: str) -> Dict[str, Any]:
    pointer = channel_manifest_path(channel, project, chip)
    releases = list_ota_release_meta(project=project, chip=chip, channel=channel)

    if not releases:
        remove_path_if_managed(pointer, (OTA_CHANNEL_DIR,))
        try:
            pointer.parent.rmdir()
        except OSError:
            pass
        return {
            "project": project,
            "chip": chip,
            "channel": channel,
            "latest_release_id": None,
            "manifest_url": None,
        }

    latest: Optional[Dict[str, Any]] = None
    manifest_path: Optional[Path] = None
    for candidate in releases:
        candidate_manifest = OTA_RELEASE_DIR / str(candidate.get("release_id")) / "manifest.json"
        if candidate_manifest.exists():
            latest = candidate
            manifest_path = candidate_manifest
            break

    if latest is None or manifest_path is None:
        remove_path_if_managed(pointer, (OTA_CHANNEL_DIR,))
        return {
            "project": project,
            "chip": chip,
            "channel": channel,
            "latest_release_id": None,
            "manifest_url": None,
        }

    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(manifest_path.read_text(encoding="utf-8"), encoding="utf-8")
    return {
        "project": project,
        "chip": chip,
        "channel": channel,
        "latest_release_id": latest.get("release_id"),
        "manifest_url": latest.get("manifest_url"),
    }


def recompute_job_ota_release_state(job_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not job_id:
        return None

    remaining = list_ota_release_meta(job_id=job_id)
    try:
        load_job(job_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            return {"job_id": job_id, "job_exists": False, "published": bool(remaining)}
        raise

    if remaining:
        latest = remaining[0]
        update_job(
            job_id,
            ota_manifest_url=latest.get("manifest_url"),
            ota_firmware_url=latest.get("firmware_url"),
            ota_release_id=latest.get("release_id"),
        )
        return {
            "job_id": job_id,
            "job_exists": True,
            "published": True,
            "release_id": latest.get("release_id"),
            "manifest_url": latest.get("manifest_url"),
            "firmware_url": latest.get("firmware_url"),
        }

    update_job(job_id, ota_manifest_url=None, ota_firmware_url=None, ota_release_id=None)
    return {"job_id": job_id, "job_exists": True, "published": False}


def load_workspaces_config() -> Dict[str, Dict[str, Any]]:
    if not WORKSPACES_CONFIG.exists():
        raise HTTPException(status_code=500, detail="Workspaces config not found")

    try:
        config = json.loads(WORKSPACES_CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid workspaces config JSON: {exc}") from exc

    workspaces = config.get("workspaces")
    if workspaces is None:
        raise HTTPException(status_code=500, detail="Workspaces config missing 'workspaces'")

    if not isinstance(workspaces, dict):
        raise HTTPException(status_code=500, detail="Workspaces config 'workspaces' must be an object")

    return workspaces


def get_workspace_config(workspace_id: str) -> Dict[str, Any]:
    if not workspace_id:
        raise HTTPException(status_code=400, detail="Missing workspace_id")

    workspaces = load_workspaces_config()
    if workspace_id not in workspaces:
        raise HTTPException(status_code=404, detail="Workspace not found")

    cfg = workspaces[workspace_id]
    if not isinstance(cfg, dict):
        raise HTTPException(status_code=500, detail=f"Workspace config must be an object: {workspace_id}")

    for field in ("path", "project_name", "target", "idf_image"):
        if not cfg.get(field):
            raise HTTPException(status_code=500, detail=f"Workspace config missing '{field}': {workspace_id}")

    return cfg


def workspace_idf_images(cfg: Dict[str, Any]) -> List[str]:
    configured = cfg.get("idf_images")
    extra = configured if isinstance(configured, list) else []
    return configured_idf_images([cfg.get("idf_image"), *extra])


def resolve_workspace_project_dir(workspace_path: str) -> Path:
    workspace = Path(workspace_path).expanduser().resolve()

    if not workspace.exists():
        raise RuntimeError(f"Workspace path not found: {workspace}")

    if not workspace.is_dir():
        raise RuntimeError(f"Workspace path is not a directory: {workspace}")

    has_cmake = (workspace / "CMakeLists.txt").is_file()
    has_main_or_components = (workspace / "main").is_dir() or (workspace / "components").is_dir()
    if has_cmake and has_main_or_components:
        return workspace

    return find_project_root(workspace)


def package_firmware_and_update_job(job_id: str, project_dir: Path, project_name: str) -> None:
    log_path = log_file(job_id)

    update_job(job_id, status="packaging", message="Packaging firmware")

    package_output = subprocess.check_output(
        [
            str(PACKAGE_SCRIPT),
            str(project_dir),
            str(ARTIFACT_DIR),
            project_name,
            job_id,
        ],
        text=True,
        stderr=subprocess.STDOUT,
    )

    with log_path.open("a", encoding="utf-8") as log:
        log.write("\n========== PACKAGE OUTPUT ==========\n")
        log.write(package_output)
        log.write("\n====================================\n")

    artifact_path = Path(package_output.strip().splitlines()[-1])

    if not artifact_path.exists():
        raise RuntimeError(f"Artifact not found: {artifact_path}")

    job = load_job(job_id)
    ota_info = collect_ota_build_info(job_id, project_dir, project_name, job.get("target") or DEFAULT_TARGET)

    update_job(
        job_id,
        status="success",
        message="Build success",
        artifact=str(artifact_path),
        artifact_name=artifact_path.name,
        download_url=f"/api/artifacts/{artifact_path.name}",
        log_url=f"/api/logs/{job_id}",
        ota_manifest_url=None,
        ota_firmware_url=None,
        ota_release_id=None,
        finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        **ota_info,
    )


def build_worker(
    job_id: str,
    upload_path: Path,
    workspace: Path,
    project_name: str,
    idf_image: str,
    target: str,
) -> None:
    log_path = log_file(job_id)

    try:
        acquired = BUILD_LOCK.acquire(blocking=False)
        if not acquired:
            update_job(
                job_id,
                status="failed",
                message="Another build is running. Please retry later.",
                finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
            return

        try:
            update_job(job_id, status="extracting", message="Extracting uploaded zip")

            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"Job ID      : {job_id}\n")
                log.write("Source mode : upload_zip\n")
                log.write(f"Upload path : {upload_path}\n")
                log.write(f"Workspace   : {workspace}\n")
                log.write(f"Project name: {project_name}\n")
                log.write(f"IDF image   : {idf_image}\n")
                log.write(f"Target      : {target}\n")

            safe_extract(upload_path, workspace)

            update_job(job_id, status="checking", message="Finding ESP-IDF project root")
            project_dir = find_project_root(workspace)

            update_job(
                job_id,
                status="building",
                message="Docker build is running",
                project_dir=str(project_dir),
            )

            run_command(
                [
                    str(BUILD_SCRIPT),
                    str(project_dir),
                    project_name,
                    idf_image,
                    target,
                ],
                log_path,
            )

            package_firmware_and_update_job(job_id, project_dir, project_name)

        finally:
            BUILD_LOCK.release()

    except Exception as exc:
        update_job(
            job_id,
            status="failed",
            message=str(exc),
            log_url=f"/api/logs/{job_id}",
            finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        with log_path.open("a", encoding="utf-8") as log:
            log.write("\n========== BUILD FAILED ==========\n")
            log.write(str(exc) + "\n")
            log.write("==================================\n")


def workspace_build_worker(
    job_id: str,
    workspace_id: str,
    workspace_path: str,
    project_name: str,
    idf_image: str,
    target: str,
) -> None:
    log_path = log_file(job_id)

    try:
        acquired = BUILD_LOCK.acquire(blocking=False)
        if not acquired:
            update_job(
                job_id,
                status="failed",
                message="Another build is running. Please retry later.",
                finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            )
            return

        try:
            update_job(job_id, status="checking", message="Checking remote workspace")

            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"Job ID        : {job_id}\n")
                log.write("Source mode   : remote_workspace\n")
                log.write(f"Workspace ID  : {workspace_id}\n")
                log.write(f"Workspace path: {workspace_path}\n")
                log.write(f"Project name  : {project_name}\n")
                log.write(f"IDF image     : {idf_image}\n")
                log.write(f"Target        : {target}\n")

            project_dir = resolve_workspace_project_dir(workspace_path)

            update_job(
                job_id,
                status="building",
                message="Docker build is running from remote workspace",
                project_dir=str(project_dir),
            )

            run_command(
                [
                    str(BUILD_SCRIPT),
                    str(project_dir),
                    project_name,
                    idf_image,
                    target,
                ],
                log_path,
            )

            package_firmware_and_update_job(job_id, project_dir, project_name)

        finally:
            BUILD_LOCK.release()

    except Exception as exc:
        update_job(
            job_id,
            status="failed",
            message=str(exc),
            log_url=f"/api/logs/{job_id}",
            finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        with log_path.open("a", encoding="utf-8") as log:
            log.write("\n========== BUILD FAILED ==========\n")
            log.write(str(exc) + "\n")
            log.write("==================================\n")


def server_info() -> Dict[str, str]:
    return {
        "name": "ESP Remote Build Server",
        "docs": "/docs",
        "home": "/home",
        "tools": "/tools/esp",
        "esp_tools": "/tools/esp",
        "default_project": DEFAULT_PROJECT_NAME,
        "default_target": DEFAULT_TARGET,
        "default_idf_image": DEFAULT_IDF_IMAGE,
    }


def ordered_enabled_items(items: Any) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []

    def sort_key(item: Dict[str, Any]) -> Tuple[int, str]:
        try:
            order = int(item.get("order", 1000))
        except (TypeError, ValueError):
            order = 1000
        return order, str(item.get("id", ""))

    enabled_items = [
        item
        for item in items
        if isinstance(item, dict) and item.get("enabled", True)
    ]
    return sorted(enabled_items, key=sort_key)


def load_home_tool_registry() -> Dict[str, Any]:
    registry = DEFAULT_HOME_TOOL_REGISTRY

    if HOME_TOOLS_CONFIG.exists():
        try:
            loaded = json.loads(HOME_TOOLS_CONFIG.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"Invalid home tools config JSON: {exc}") from exc

        if not isinstance(loaded, dict):
            raise HTTPException(status_code=500, detail="Home tools config must be an object")

        registry = loaded

    sections = ordered_enabled_items(registry.get("sections"))
    section_ids = {str(section.get("id")) for section in sections}
    tools = [
        tool
        for tool in ordered_enabled_items(registry.get("tools"))
        if str(tool.get("section_id")) in section_ids
    ]

    return {
        "title": str(registry.get("title") or DEFAULT_HOME_TOOL_REGISTRY["title"]),
        "subtitle": str(registry.get("subtitle") or DEFAULT_HOME_TOOL_REGISTRY["subtitle"]),
        "sections": sections,
        "tools": tools,
    }


@app.get("/")
def index() -> RedirectResponse:
    return RedirectResponse(url="/home")


@app.get("/api/info")
def api_info() -> Dict[str, str]:
    return server_info()


@app.get("/api/home/tools")
def api_home_tools() -> Dict[str, Any]:
    return load_home_tool_registry()


@app.get("/api/idf-images")
def list_idf_images():
    return {
        "default_idf_image": DEFAULT_IDF_IMAGE,
        "allowed_idf_images": configured_idf_images(),
        "allow_custom": ALLOW_CUSTOM_IDF_IMAGE,
    }


def ui_file(relative_path: str) -> FileResponse:
    page_file = STATIC_DIR / relative_path

    if not page_file.exists():
        raise HTTPException(status_code=404, detail="UI page not found")

    return FileResponse(page_file, headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/home")
def zlyhub_home() -> FileResponse:
    return ui_file("home.html")


@app.get("/tools/esp")
def esp_tools_home() -> FileResponse:
    return ui_file("index.html")


@app.get("/tools/esp/build")
def esp_tools_build() -> FileResponse:
    return ui_file("pages/build.html")


@app.get("/tools/esp/flash")
def esp_tools_flash() -> FileResponse:
    return ui_file("pages/flash.html")


@app.get("/tools/esp/ota")
def esp_tools_ota() -> FileResponse:
    return ui_file("pages/ota.html")


@app.get("/tools/esp/jobs")
def esp_tools_jobs() -> FileResponse:
    return ui_file("pages/jobs.html")


@app.get("/tools/esp/settings")
def esp_tools_settings() -> FileResponse:
    return ui_file("pages/settings.html")


@app.get("/ui")
def legacy_ui_home() -> RedirectResponse:
    return RedirectResponse(url="/tools/esp")


@app.get("/ui/build")
def legacy_ui_build() -> RedirectResponse:
    return RedirectResponse(url="/tools/esp/build")


@app.get("/ui/flash")
def legacy_ui_flash() -> RedirectResponse:
    return RedirectResponse(url="/tools/esp/flash")


@app.get("/ui/ota")
def legacy_ui_ota() -> RedirectResponse:
    return RedirectResponse(url="/tools/esp/ota")


@app.get("/ui/jobs")
def legacy_ui_jobs() -> RedirectResponse:
    return RedirectResponse(url="/tools/esp/jobs")


@app.get("/ui/settings")
def legacy_ui_settings() -> RedirectResponse:
    return RedirectResponse(url="/tools/esp/settings")


@app.get("/api/workspaces")
def list_workspaces():
    workspaces = load_workspaces_config()
    items = []

    for workspace_id, cfg in workspaces.items():
        if not isinstance(cfg, dict):
            continue

        items.append(
            {
                "workspace_id": workspace_id,
                "display_name": cfg.get("display_name", workspace_id),
                "project_type": cfg.get("project_type", "esp_idf"),
                "project_name": cfg.get("project_name"),
                "target": cfg.get("target"),
                "idf_image": cfg.get("idf_image"),
                "idf_images": workspace_idf_images(cfg),
            }
        )

    return {"workspaces": items}


@app.post("/api/build/workspace")
async def build_from_workspace(payload: Dict[str, Any]):
    workspace_id = payload.get("workspace_id")
    cfg = get_workspace_config(workspace_id)

    workspace_path = cfg["path"]
    project_name = cfg["project_name"]
    target = cfg["target"]
    idf_image = validate_idf_image(str(payload.get("idf_image") or cfg["idf_image"]), workspace_idf_images(cfg))
    job_id = make_job_id()
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    save_job(
        job_id,
        {
            "status": "queued",
            "source_mode": "remote_workspace",
            "message": "Remote workspace build queued",
            "workspace_id": workspace_id,
            "workspace_path": workspace_path,
            "project_name": project_name,
            "target": target,
            "idf_image": idf_image,
            "log": str(log_file(job_id)),
            "created_at": now,
            "finished_at": None,
            "artifact": None,
            "artifact_name": None,
            "download_url": None,
            "log_url": f"/api/logs/{job_id}",
        },
    )
    cleanup_old_build_records()

    worker = threading.Thread(
        target=workspace_build_worker,
        args=(job_id, workspace_id, workspace_path, project_name, idf_image, target),
        daemon=True,
    )
    worker.start()

    return {
        "job_id": job_id,
        "status": "running",
        "status_url": f"/api/jobs/{job_id}",
        "log_url": f"/api/logs/{job_id}",
    }


@app.post("/api/build/upload")
async def build_from_upload(
    file: UploadFile = File(...),
    project_name: str = Form(DEFAULT_PROJECT_NAME),
    idf_image: str = Form(DEFAULT_IDF_IMAGE),
    target: str = Form(DEFAULT_TARGET),
):
    idf_image = validate_idf_image(idf_image)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip file is supported")

    job_id = make_job_id()

    upload_path = UPLOAD_DIR / f"{job_id}.zip"
    workspace = WORKSPACE_DIR / job_id
    workspace.mkdir(parents=True, exist_ok=True)

    size = 0

    with upload_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)

            if not chunk:
                break

            size += len(chunk)

            if size > MAX_UPLOAD_SIZE:
                out.close()
                upload_path.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Uploaded file too large")

            out.write(chunk)

    now = time.strftime("%Y-%m-%d %H:%M:%S")

    save_job(
        job_id,
        {
            "status": "uploaded",
            "source_mode": "upload_zip",
            "message": "Upload completed",
            "project_name": project_name,
            "target": target,
            "idf_image": idf_image,
            "upload_file": str(upload_path),
            "workspace": str(workspace),
            "log": str(log_file(job_id)),
            "created_at": now,
            "finished_at": None,
            "artifact": None,
            "artifact_name": None,
            "download_url": None,
            "log_url": f"/api/logs/{job_id}",
        },
    )
    cleanup_old_build_records()

    worker = threading.Thread(
        target=build_worker,
        args=(job_id, upload_path, workspace, project_name, idf_image, target),
        daemon=True,
    )
    worker.start()

    return {
        "job_id": job_id,
        "status": "running",
        "status_url": f"/api/jobs/{job_id}",
        "log_url": f"/api/logs/{job_id}",
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return load_job(job_id)


@app.get("/api/jobs")
def list_jobs():
    jobs = []

    for path in sorted(JOB_DIR.glob("*.json"), reverse=True):
        try:
            jobs.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue

    return jobs[:MAX_BUILD_RECORDS]


@app.get("/api/logs/{job_id}", response_class=PlainTextResponse)
def get_log(job_id: str):
    path = log_file(job_id)

    if not path.exists():
        raise HTTPException(status_code=404, detail="Log not found")

    return path.read_text(encoding="utf-8", errors="replace")



@app.post("/api/ota/publish/{job_id}")
def publish_ota_release(job_id: str, payload: Dict[str, Any], request: Request):
    job = load_job(job_id)
    if job.get("status") != "success":
        raise HTTPException(status_code=400, detail="Only successful build jobs can be published")
    if not job.get("ota_publishable"):
        raise HTTPException(status_code=400, detail="Build output is not OTA publishable")

    project = safe_name(str(job.get("project_name") or DEFAULT_PROJECT_NAME), "project")
    chip = safe_name(str(job.get("target") or DEFAULT_TARGET), "chip")
    channel = safe_name(str(payload.get("channel") or "test"), "channel")
    version = normalize_ota_version(str(payload.get("version") or "")) or ""
    min_version = normalize_ota_version(str(payload.get("min_version") or "")) or ""
    force = bool(payload.get("force", False))
    release_notes = str(payload.get("release_notes") or "")

    version_tuple = parse_semver(version)
    if min_version:
        parse_semver(min_version)

    existing = latest_channel_manifest(channel, project, chip)
    if existing and not force:
        existing_version = existing.get("version")
        if existing_version and VERSION_RE.fullmatch(str(existing_version)):
            if version_tuple <= parse_semver(str(existing_version)):
                raise HTTPException(
                    status_code=400,
                    detail="version must be greater than current channel version unless force=true",
                )

    app_bin = Path(str(job.get("ota_app_bin") or ""))
    if not app_bin.exists():
        raise HTTPException(status_code=404, detail="app bin not found for this job")

    size = app_bin.stat().st_size
    if size > OTA_APP_PARTITION_SIZE:
        raise HTTPException(status_code=400, detail="app bin is larger than OTA app partition limit")
    sha256 = sha256_file(app_bin)
    if job.get("ota_app_sha256") and sha256 != job.get("ota_app_sha256"):
        raise HTTPException(status_code=409, detail="app bin sha256 changed since build")

    release_id = make_job_id()
    release_dir = OTA_RELEASE_DIR / release_id
    release_dir.mkdir(parents=True, exist_ok=False)
    release_app = release_dir / "app.bin"
    shutil.copy2(app_bin, release_app)

    firmware_path = ota_firmware_path(release_id)
    manifest_path = ota_manifest_path(release_id)
    latest_path = ota_latest_path(project, chip, channel)
    firmware_url = absolute_url(request, firmware_path)
    manifest_url = absolute_url(request, latest_path)

    manifest = {
        "project": project,
        "chip": chip,
        "version": version,
        "min_version": min_version,
        "force": force,
        "url": firmware_url,
        "size": size,
        "sha256": sha256,
    }
    meta = {
        **manifest,
        "release_id": release_id,
        "job_id": job_id,
        "channel": channel,
        "release_notes": release_notes,
        "manifest_url": manifest_url,
        "manifest_direct_url": absolute_url(request, manifest_path),
        "firmware_url": firmware_url,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    (release_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (release_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    pointer = channel_manifest_path(channel, project, chip)
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    update_job(job_id, ota_manifest_url=manifest_url, ota_firmware_url=firmware_url, ota_release_id=release_id)
    return {**meta, "manifest": manifest}


@app.get("/api/ota/latest")
def get_latest_ota_manifest(request: Request, project: str, chip: str, channel: str = "stable"):
    project = safe_name(project, "project")
    chip = safe_name(chip, "chip")
    channel = safe_name(channel, "channel")

    releases = list_ota_release_meta(project=project, chip=chip, channel=channel)
    for release in releases:
        release_id = safe_name(str(release.get("release_id") or ""), "release_id")
        path = OTA_RELEASE_DIR / release_id / "manifest.json"
        if path.exists():
            manifest = json.loads(path.read_text(encoding="utf-8"))
            return manifest_with_current_urls(request, release_id, manifest)

    manifest = latest_channel_manifest(channel, project, chip)
    if not manifest:
        raise HTTPException(status_code=404, detail="OTA manifest not found")
    return manifest


@app.get("/api/ota/manifest/{release_id}")
def get_ota_manifest(request: Request, release_id: str):
    release_id = safe_name(release_id, "release_id")
    path = OTA_RELEASE_DIR / release_id / "manifest.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="OTA manifest not found")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return manifest_with_current_urls(request, release_id, manifest)


@app.get("/api/ota/firmware/{release_id}/app.bin")
def download_ota_firmware(release_id: str):
    release_id = safe_name(release_id, "release_id")
    path = OTA_RELEASE_DIR / release_id / "app.bin"
    if not path.exists():
        raise HTTPException(status_code=404, detail="OTA firmware not found")
    return FileResponse(path, media_type="application/octet-stream", filename="app.bin")


@app.get("/api/ota/releases")
def list_ota_releases(request: Request, project: Optional[str] = None, chip: Optional[str] = None):
    if project:
        project = safe_name(project, "project")
    if chip:
        chip = safe_name(chip, "chip")
    releases = [
        meta_with_current_urls(request, meta)
        for meta in list_ota_release_meta(project=project, chip=chip)
    ]
    return {"releases": releases}


@app.delete("/api/ota/releases/{release_id}")
def delete_ota_release(release_id: str):
    release_id = safe_name(release_id, "release_id")
    meta = load_ota_release_meta(release_id)
    project = safe_name(str(meta.get("project") or ""), "project")
    chip = safe_name(str(meta.get("chip") or ""), "chip")
    channel = safe_name(str(meta.get("channel") or ""), "channel")
    job_id = str(meta.get("job_id") or "")

    release_dir = OTA_RELEASE_DIR / release_id
    remove_path_if_managed(release_dir, (OTA_RELEASE_DIR,))

    latest = refresh_ota_channel_latest(project, chip, channel)
    job_state = recompute_job_ota_release_state(job_id)

    return {
        "deleted_release_id": release_id,
        "project": project,
        "chip": chip,
        "channel": channel,
        "job_id": job_id or None,
        "latest": latest,
        "job_state": job_state,
    }

@app.get("/api/artifacts/{filename}")
def download_artifact(filename: str):
    path = ARTIFACT_DIR / filename

    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")

    return FileResponse(path, filename=filename)
