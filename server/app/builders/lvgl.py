from __future__ import annotations

import shutil
from pathlib import Path

from app.builders.archive import safe_extract_zip
from app.builders.base import ArtifactSpec, BuildContext, BuildOutput
from app.builders.files import find_lvgl_project_root, slug_name
from app.builders.lvgl_scaffold import load_lvgl_ui_manifest, prepare_lvgl_ui_scaffold
from app.domain.jobs import JobStage, SourceMode


class LvglBuilder:
    def run(self, context: BuildContext) -> BuildOutput:
        job = context.job
        request = job.request_json
        source_mode = SourceMode(job.source_mode)
        log_path = Path(job.log_path)

        if source_mode in {SourceMode.UPLOAD, SourceMode.UI_UPLOAD}:
            if not job.upload_path or not job.workspace_path:
                raise RuntimeError("Uploaded LVGL build is missing its source paths")
            workspace = Path(job.workspace_path)
            context.update_stage(JobStage.EXTRACTING, "Extracting uploaded LVGL project")
            safe_extract_zip(Path(job.upload_path), workspace, context.settings)
            manifest = load_lvgl_ui_manifest(workspace)
            if manifest:
                context.update_stage(JobStage.GENERATING, "Generating LVGL WebAssembly project")
                project_dir = prepare_lvgl_ui_scaffold(
                    workspace,
                    manifest,
                    int(request["width"]),
                    int(request["height"]),
                    context.settings,
                )
            else:
                project_dir = find_lvgl_project_root(workspace)
        else:
            context.update_stage(JobStage.CHECKING, "Checking configured LVGL workspace")
            workspace = Path(str(request["workspace_path"])).expanduser().resolve()
            if not workspace.is_dir():
                raise RuntimeError(f"LVGL workspace path not found: {workspace}")
            project_dir = find_lvgl_project_root(workspace)

        preview_dir = context.settings.lvgl_preview_dir / job.id
        preview_dir.mkdir(parents=True, exist_ok=True)
        container_name = f"lvgl-build-{job.id}"
        context.update_stage(JobStage.BUILDING, "Docker Emscripten build is running")
        context.runner.run(
            [
                "bash",
                str(context.settings.lvgl_build_script),
                str(project_dir),
                str(preview_dir),
                context.settings.lvgl_emsdk_image,
                str(request["width"]),
                str(request["height"]),
                context.settings.lvgl_source_dir,
                context.settings.lvgl_sdl2_port_dir,
                context.settings.lvgl_emsdk_cache_dir,
                job.id,
            ],
            log_path,
            timeout_seconds=context.settings.lvgl_build_timeout_seconds,
            cancel_requested=context.cancel_requested,
            container_name=container_name,
        )
        if not (preview_dir / "index.html").is_file():
            raise RuntimeError("LVGL preview index.html not found")

        context.update_stage(JobStage.PACKAGING, "Packaging LVGL preview")
        archive_base = context.settings.artifact_dir / (
            f"{slug_name(job.project_name, 'lvgl_project')}_{job.id}_lvgl_preview"
        )
        archive_path = Path(shutil.make_archive(str(archive_base), "zip", preview_dir))
        return BuildOutput(
            result={"preview_url": f"/api/v2/jobs/{job.id}/preview/index.html"},
            artifacts=[ArtifactSpec("lvgl_preview", archive_path, "application/zip")],
        )
