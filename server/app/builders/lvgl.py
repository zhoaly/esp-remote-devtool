from __future__ import annotations

import shutil
from pathlib import Path

from app.builders.archive import safe_extract_zip
from app.builders.base import ArtifactSpec, BuildContext, BuildOutput
from app.builders.docker import bind_mount, run_command
from app.builders.files import find_lvgl_project_root, slug_name, stage_web_preview
from app.builders.lvgl_scaffold import load_lvgl_ui_manifest, prepare_lvgl_ui_scaffold
from app.domain.jobs import JobStage, SourceMode

LVGL_BUILD = r"""
set -euo pipefail
rm -rf build_web
emcmake cmake -S . -B build_web -DLVGL_SIM_WIDTH="$LVGL_SIM_WIDTH" -DLVGL_SIM_HEIGHT="$LVGL_SIM_HEIGHT"
cmake --build build_web -j"$(nproc)"
"""


class LvglBuilder:
    def run(self, context: BuildContext) -> BuildOutput:
        job = context.job
        request = job.request_json
        source_mode = SourceMode(job.source_mode)
        log_path = context.settings.resolve_path(job.log_path)

        if source_mode in {SourceMode.UPLOAD, SourceMode.UI_UPLOAD}:
            if not job.upload_path or not job.workspace_path:
                raise RuntimeError("Uploaded LVGL build is missing its source paths")
            workspace = context.settings.resolve_path(job.workspace_path)
            context.update_stage(JobStage.EXTRACTING, "Extracting uploaded LVGL project")
            safe_extract_zip(
                context.settings.resolve_path(job.upload_path), workspace, context.settings
            )
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
            workspace = context.settings.resolve_path(str(request["workspace_path"]))
            if not workspace.is_dir():
                raise RuntimeError(f"LVGL workspace path not found: {workspace}")
            project_dir = find_lvgl_project_root(workspace)

        preview_dir = context.settings.lvgl_preview_dir / job.id
        preview_dir.mkdir(parents=True, exist_ok=True)
        container_name = f"lvgl-build-{job.id}"
        args = run_command(container_name, project_dir)
        args += [
            "-e",
            f"LVGL_SIM_WIDTH={request['width']}",
            "-e",
            f"LVGL_SIM_HEIGHT={request['height']}",
        ]
        settings = context.settings
        if settings.lvgl_source_dir:
            source = Path(settings.lvgl_source_dir).expanduser().resolve()
            if not (source / "CMakeLists.txt").is_file():
                raise RuntimeError("LVGL_SOURCE_DIR is invalid")
            args += bind_mount(source, "/lvgl_source", readonly=True)
            # Keep the legacy mount for uploaded CMake projects, and expose a
            # directory literally named lvgl for namespaced UI includes.
            args += bind_mount(source, "/opt/lvgl_include/lvgl", readonly=True)
        if settings.lvgl_sdl2_port_dir:
            port = Path(settings.lvgl_sdl2_port_dir).expanduser().resolve()
            if not (port / "include/SDL.h").is_file():
                raise RuntimeError("LVGL_SDL2_PORT_DIR is invalid")
            args += bind_mount(port, "/emscripten_ports/sdl2", readonly=True)
            args += ["-e", "EMCC_LOCAL_PORTS=sdl2=/emscripten_ports/sdl2"]
        if settings.lvgl_emsdk_cache_dir:
            cache = Path(settings.lvgl_emsdk_cache_dir).expanduser().resolve()
            cache.mkdir(parents=True, exist_ok=True)
            args += bind_mount(cache, "/emscripten_cache")
            args += ["-e", "EM_CACHE=/emscripten_cache"]
        context.update_stage(JobStage.BUILDING, "Docker Emscripten build is running")
        context.runner.run(
            [*args, settings.lvgl_emsdk_image, "bash", "-c", LVGL_BUILD],
            log_path,
            timeout_seconds=context.settings.lvgl_build_timeout_seconds,
            cancel_requested=context.cancel_requested,
            container_name=container_name,
        )
        context.update_stage(JobStage.PACKAGING, "Packaging LVGL preview")
        stage_web_preview(project_dir / "build_web", preview_dir)
        archive_base = context.settings.artifact_dir / (
            f"{slug_name(job.project_name, 'lvgl_project')}_{job.id}_lvgl_preview"
        )
        archive_path = Path(shutil.make_archive(str(archive_base), "zip", preview_dir))
        return BuildOutput(
            result={"preview_url": f"/api/v2/jobs/{job.id}/preview/index.html"},
            artifacts=[ArtifactSpec("lvgl_preview", archive_path, "application/zip")],
        )
