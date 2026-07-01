from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse


app = FastAPI(title="ESP Remote Build Server", version="0.1.0")

SERVER_DIR = Path(__file__).resolve().parents[1]
BASE_DIR = Path(os.getenv("ESP_SERVER_BASE_DIR", SERVER_DIR)).resolve()
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
WORKSPACE_DIR = DATA_DIR / "workspaces"
ARTIFACT_DIR = DATA_DIR / "artifacts"
LOG_DIR = DATA_DIR / "logs"
JOB_DIR = DATA_DIR / "jobs"
STATIC_DIR = BASE_DIR / "app" / "static"
CONFIG_DIR = BASE_DIR / "config"
WORKSPACES_CONFIG = CONFIG_DIR / "workspaces.json"

BUILD_SCRIPT = BASE_DIR / "scripts" / "build_uploaded_project.sh"
PACKAGE_SCRIPT = BASE_DIR / "scripts" / "package_firmware.sh"

DEFAULT_PROJECT_NAME = os.getenv("ESP_DEFAULT_PROJECT_NAME", "ESP32_S3_wifi_ble_hub")
DEFAULT_IDF_IMAGE = os.getenv("ESP_DEFAULT_IDF_IMAGE", "espressif/idf:v6.0.1")
DEFAULT_TARGET = os.getenv("ESP_DEFAULT_TARGET", "esp32s3")
MAX_UPLOAD_SIZE = int(os.getenv("ESP_MAX_UPLOAD_SIZE_MB", "200")) * 1024 * 1024

BUILD_LOCK = threading.Lock()


for directory in (UPLOAD_DIR, WORKSPACE_DIR, ARTIFACT_DIR, LOG_DIR, JOB_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def make_job_id() -> str:
    return time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]


def job_file(job_id: str) -> Path:
    return JOB_DIR / f"{job_id}.json"


def log_file(job_id: str) -> Path:
    return LOG_DIR / f"{job_id}.log"


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

    update_job(
        job_id,
        status="success",
        message="Build success",
        artifact=str(artifact_path),
        artifact_name=artifact_path.name,
        download_url=f"/api/artifacts/{artifact_path.name}",
        log_url=f"/api/logs/{job_id}",
        finished_at=time.strftime("%Y-%m-%d %H:%M:%S"),
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


@app.get("/")
def index() -> Dict[str, str]:
    return {
        "name": "ESP Remote Build Server",
        "docs": "/docs",
        "ui": "/ui",
        "default_project": DEFAULT_PROJECT_NAME,
        "default_target": DEFAULT_TARGET,
        "default_idf_image": DEFAULT_IDF_IMAGE,
    }


@app.get("/ui")
def ui() -> FileResponse:
    index_file = STATIC_DIR / "index.html"

    if not index_file.exists():
        raise HTTPException(status_code=404, detail="UI page not found")

    return FileResponse(index_file, headers={"Cache-Control": "no-store, max-age=0"})


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
    idf_image = cfg["idf_image"]
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

    return jobs[:50]


@app.get("/api/logs/{job_id}", response_class=PlainTextResponse)
def get_log(job_id: str):
    path = log_file(job_id)

    if not path.exists():
        raise HTTPException(status_code=404, detail="Log not found")

    return path.read_text(encoding="utf-8", errors="replace")


@app.get("/api/artifacts/{filename}")
def download_artifact(filename: str):
    path = ARTIFACT_DIR / filename

    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")

    return FileResponse(path, filename=filename)
