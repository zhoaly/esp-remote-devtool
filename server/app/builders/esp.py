from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.builders.archive import safe_extract_zip
from app.builders.base import ArtifactSpec, BuildContext, BuildOutput
from app.builders.docker import run_command
from app.builders.files import find_esp_project_root, sha256_file
from app.builders.firmware import find_app_bin, package_firmware
from app.domain.jobs import JobStage, SourceMode


def _resolve_workspace(path_value: str) -> Path:
    workspace = Path(path_value).expanduser().resolve()
    if not workspace.is_dir():
        raise RuntimeError(f"Workspace path not found: {workspace}")
    if (workspace / "CMakeLists.txt").is_file() and (
        (workspace / "main").is_dir() or (workspace / "components").is_dir()
    ):
        return workspace
    return find_esp_project_root(workspace)


def _read_project_version(project_dir: Path) -> str | None:
    description = project_dir / "build" / "project_description.json"
    if not description.exists():
        return None
    try:
        value = json.loads(description.read_text(encoding="utf-8")).get("project_version")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    return str(value) if value else None


class EspBuilder:
    def run(self, context: BuildContext) -> BuildOutput:
        job = context.job
        request = job.request_json
        log_path = context.settings.resolve_path(job.log_path)
        source_mode = SourceMode(job.source_mode)

        if source_mode == SourceMode.UPLOAD:
            if not job.upload_path or not job.workspace_path:
                raise RuntimeError("Uploaded build is missing its source paths")
            context.update_stage(JobStage.EXTRACTING, "Extracting uploaded ESP-IDF project")
            safe_extract_zip(
                context.settings.resolve_path(job.upload_path),
                context.settings.resolve_path(job.workspace_path),
                context.settings,
            )
            context.update_stage(JobStage.CHECKING, "Finding ESP-IDF project root")
            project_dir = find_esp_project_root(context.settings.resolve_path(job.workspace_path))
        else:
            context.update_stage(JobStage.CHECKING, "Checking configured ESP-IDF workspace")
            project_dir = _resolve_workspace(
                str(context.settings.resolve_path(str(request["workspace_path"])))
            )

        project_name = str(request["project_name"])
        target = str(request["target"])
        idf_image = str(request["idf_image"])
        container_name = f"esp-build-{job.id}"
        context.update_stage(JobStage.BUILDING, "Docker ESP-IDF build is running")
        build_dir = project_dir / "build"
        if build_dir.exists() or build_dir.is_symlink():
            if build_dir.is_symlink():
                raise RuntimeError("Refusing to clean a linked build directory")
            shutil.rmtree(build_dir)
        context.runner.run(
            [
                *run_command(container_name, project_dir),
                "-e",
                "IDF_GIT_SAFE_DIR=*",
                "-e",
                f"IDF_TARGET={target}",
                idf_image,
                "bash",
                "-c",
                "idf.py build && idf.py merge-bin -o firmware_merged.bin -f raw",
            ],
            log_path,
            timeout_seconds=context.settings.esp_build_timeout_seconds,
            cancel_requested=context.cancel_requested,
            container_name=container_name,
        )

        context.update_stage(JobStage.PACKAGING, "Packaging firmware")
        artifact_path = package_firmware(
            project_dir, context.settings.artifact_dir, project_name, job.id, target
        )
        app_bin = find_app_bin(project_dir)
        app_size = app_bin.stat().st_size
        result = {
            "project_dir_name": project_dir.name,
            "ota_publishable": app_size <= context.settings.ota_app_partition_size,
            "ota_project_version": _read_project_version(project_dir),
            "ota_app_size": app_size,
            "ota_app_sha256": sha256_file(app_bin),
            "ota_app_bin_name": app_bin.name,
            "ota_partition_limit": context.settings.ota_app_partition_size,
            "_ota_app_path": context.settings.stored_path(app_bin),
        }
        return BuildOutput(
            result=result,
            artifacts=[ArtifactSpec("firmware", artifact_path, "application/zip")],
        )
