from __future__ import annotations

import json
from pathlib import Path

from app.builders.archive import safe_extract_zip
from app.builders.base import ArtifactSpec, BuildContext, BuildOutput
from app.builders.files import find_esp_project_root, is_managed_path, sha256_file
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


def _find_app_bin(project_dir: Path) -> Path:
    description = project_dir / "build" / "project_description.json"
    if description.exists():
        try:
            data = json.loads(description.read_text(encoding="utf-8"))
            app_name = data.get("app_bin") or data.get("project_name")
            if app_name:
                candidate = project_dir / "build" / str(app_name)
                if candidate.suffix != ".bin":
                    candidate = candidate.with_suffix(".bin")
                if candidate.exists():
                    return candidate
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    candidates = sorted(
        path
        for path in (project_dir / "build").glob("*.bin")
        if path.name != "firmware_merged.bin"
    )
    if not candidates:
        raise RuntimeError("Application binary not found")
    return candidates[0]


class EspBuilder:
    def run(self, context: BuildContext) -> BuildOutput:
        job = context.job
        request = job.request_json
        log_path = Path(job.log_path)
        source_mode = SourceMode(job.source_mode)

        if source_mode == SourceMode.UPLOAD:
            if not job.upload_path or not job.workspace_path:
                raise RuntimeError("Uploaded build is missing its source paths")
            context.update_stage(JobStage.EXTRACTING, "Extracting uploaded ESP-IDF project")
            safe_extract_zip(Path(job.upload_path), Path(job.workspace_path), context.settings)
            context.update_stage(JobStage.CHECKING, "Finding ESP-IDF project root")
            project_dir = find_esp_project_root(Path(job.workspace_path))
        else:
            context.update_stage(JobStage.CHECKING, "Checking configured ESP-IDF workspace")
            project_dir = _resolve_workspace(str(request["workspace_path"]))

        project_name = str(request["project_name"])
        target = str(request["target"])
        idf_image = str(request["idf_image"])
        container_name = f"esp-build-{job.id}"
        context.update_stage(JobStage.BUILDING, "Docker ESP-IDF build is running")
        context.runner.run(
            [
                str(context.settings.build_script),
                str(project_dir),
                project_name,
                idf_image,
                target,
                job.id,
            ],
            log_path,
            timeout_seconds=context.settings.esp_build_timeout_seconds,
            cancel_requested=context.cancel_requested,
            container_name=container_name,
        )

        context.update_stage(JobStage.PACKAGING, "Packaging firmware")
        context.runner.run(
            [
                str(context.settings.package_script),
                str(project_dir),
                str(context.settings.artifact_dir),
                project_name,
                job.id,
            ],
            log_path,
            timeout_seconds=120,
            cancel_requested=context.cancel_requested,
        )
        artifact_path = (
            context.settings.artifact_dir / f"{project_name}_{job.id}_firmware.zip"
        ).resolve()
        if not artifact_path.is_file() or not is_managed_path(
            artifact_path, (context.settings.artifact_dir,)
        ):
            raise RuntimeError("Firmware packager returned an invalid artifact path")

        app_bin = _find_app_bin(project_dir)
        app_size = app_bin.stat().st_size
        result = {
            "project_dir_name": project_dir.name,
            "ota_publishable": app_size <= context.settings.ota_app_partition_size,
            "ota_project_version": _read_project_version(project_dir),
            "ota_app_size": app_size,
            "ota_app_sha256": sha256_file(app_bin),
            "ota_app_bin_name": app_bin.name,
            "ota_partition_limit": context.settings.ota_app_partition_size,
            "_ota_app_path": str(app_bin.resolve()),
        }
        return BuildOutput(
            result=result,
            artifacts=[ArtifactSpec("firmware", artifact_path, "application/zip")],
        )
