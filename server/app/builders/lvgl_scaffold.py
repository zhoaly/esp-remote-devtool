from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from app.builders.files import remove_managed_path
from app.core.config import Settings


def load_lvgl_ui_manifest(workspace: Path) -> dict[str, Any] | None:
    manifest_path = workspace / "lvgl_sim.json"
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid lvgl_sim.json: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("source_type") != "ui_package":
        raise RuntimeError("Unsupported lvgl_sim.json manifest")
    return manifest


def _normalize_entry_call(value: Any) -> str:
    item = str(value or "ui_init").strip()
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", item):
        return f"{item}()"
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\(\)", item):
        return item
    raise RuntimeError("LVGL UI entry call must be a function name or empty function call")


def _normalize_header(value: Any) -> str:
    item = str(value or "").strip().replace("\\", "/").strip("/")
    if not item:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_./-]+\.h", item) or ".." in Path(item).parts:
        raise RuntimeError("LVGL UI entry header must be a relative .h path")
    return item


def _normalize_dirs(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        item = str(value or "").strip().replace("\\", "/").strip("/")
        if not item:
            continue
        if Path(item).is_absolute() or ".." in Path(item).parts:
            raise RuntimeError(f"Invalid LVGL UI relative path: {item}")
        if item not in result:
            result.append(item)
    return result


def _is_ui_source(path: Path) -> bool:
    if path.suffix.lower() not in {".c", ".cc", ".cpp", ".cxx"}:
        return False
    if path.name in {"main.c", "freertos_main.c", "freertos_posix_port.c", "hal.c", "mouse_cursor_icon.c"}:
        return False
    return not set(path.parts).intersection({"hal", "freertos", "FreeRTOS", "build", "bin", ".git"})


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "/").replace('"', '\\"') + '"'


def _demo_sources(entry_call: str) -> list[str]:
    match = re.fullmatch(r"(lv_demo_[A-Za-z0-9_]+)\(\)", entry_call)
    if not match:
        return []
    return {
        "lv_demo_widgets": [
            "demos/lv_demos.c",
            "demos/widgets/assets/img_clothes.c",
            "demos/widgets/assets/img_demo_widgets_avatar.c",
            "demos/widgets/assets/img_demo_widgets_needle.c",
            "demos/widgets/assets/img_lvgl_logo.c",
            "demos/widgets/lv_demo_widgets.c",
            "demos/widgets/lv_demo_widgets_analytics.c",
            "demos/widgets/lv_demo_widgets_components.c",
            "demos/widgets/lv_demo_widgets_profile.c",
            "demos/widgets/lv_demo_widgets_shop.c",
        ],
        "lv_demo_benchmark": ["demos/lv_demos.c", "demos/benchmark/lv_demo_benchmark.c"],
    }.get(match.group(1), [])


def _write_main(path: Path, entry_call: str, entry_header: str) -> None:
    header = ""
    if entry_header:
        header = f'#if __has_include("{entry_header}")\n#include "{entry_header}"\n#endif\n'
    elif entry_call.startswith("lv_demo_"):
        header = f"void {entry_call[:-2]}(void);\n"
    path.write_text(
        f'''#include "lvgl/lvgl.h"
#include <emscripten.h>
{header}
static void lvgl_tick(void * user_data)
{{
    (void)user_data;
    lv_timer_handler();
}}

int main(void)
{{
    lv_init();
    lv_display_t * display = lv_sdl_window_create(LVGL_SIM_WIDTH, LVGL_SIM_HEIGHT);
    lv_display_set_default(display);
    lv_indev_t * mouse = lv_sdl_mouse_create();
    lv_indev_set_display(mouse, display);
    lv_indev_t * mousewheel = lv_sdl_mousewheel_create();
    lv_indev_set_display(mousewheel, display);
    lv_indev_t * keyboard = lv_sdl_keyboard_create();
    lv_indev_set_display(keyboard, display);
    {entry_call};
    emscripten_set_main_loop_arg(lvgl_tick, NULL, 0, 1);
    return 0;
}}
''',
        encoding="utf-8",
    )


def _write_conf(path: Path, entry_call: str) -> None:
    path.write_text(
        f'''#ifndef LV_CONF_H
#define LV_CONF_H
#define LV_COLOR_DEPTH 32
#define LV_USE_OS LV_OS_NONE
#define LV_USE_LOG 1
#define LV_LOG_LEVEL LV_LOG_LEVEL_WARN
#define LV_USE_SDL 1
#define LV_USE_DRAW_SDL 0
#define LV_USE_DEMO_WIDGETS {"1" if "lv_demo_widgets" in entry_call else "0"}
#define LV_USE_DEMO_BENCHMARK {"1" if "lv_demo_benchmark" in entry_call else "0"}
#define LV_USE_DEMO_STRESS 0
#define LV_USE_DEMO_RENDER 0
#define LV_USE_PERF_MONITOR 0
#define LV_USE_MEM_MONITOR 0
#endif
''',
        encoding="utf-8",
    )


def prepare_lvgl_ui_scaffold(
    workspace: Path,
    manifest: dict[str, Any],
    width: int,
    height: int,
    settings: Settings,
) -> Path:
    entry_call = _normalize_entry_call(manifest.get("entry_call"))
    entry_header = _normalize_header(manifest.get("entry_header"))
    include_dirs = _normalize_dirs(manifest.get("include_dirs"))
    web_project = workspace / "_lvgl_web_project"
    package_dir = web_project / "ui_package"
    src_dir = web_project / "src"

    if web_project.exists():
        remove_managed_path(web_project, (settings.workspace_dir,))
    package_dir.mkdir(parents=True, exist_ok=True)
    src_dir.mkdir(parents=True, exist_ok=True)

    for path in workspace.rglob("*"):
        if web_project == path or web_project in path.parents:
            continue
        if not path.is_file() or path.name == "lvgl_sim.json":
            continue
        target = package_dir / path.relative_to(workspace)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

    sources = [
        path.relative_to(web_project).as_posix()
        for path in sorted(package_dir.rglob("*"))
        if path.is_file() and _is_ui_source(path.relative_to(package_dir))
    ]
    source_lines = "\n".join(f"    {_quote(item)}" for item in sources)
    includes = ['"${CMAKE_CURRENT_SOURCE_DIR}/ui_package"'] + [
        f'"${{CMAKE_CURRENT_SOURCE_DIR}}/ui_package/{item}"' for item in include_dirs
    ]
    include_lines = "\n".join(f"    {item}" for item in includes)
    demo_sources = _demo_sources(entry_call)
    demo_block = "\n".join(
        f'''if(LVGL_UPSTREAM_SOURCE_DIR AND EXISTS "${{LVGL_UPSTREAM_SOURCE_DIR}}/{source}")
    list(APPEND UI_SOURCES "${{LVGL_UPSTREAM_SOURCE_DIR}}/{source}")
endif()'''
        for source in demo_sources
    )
    demo_include = '''
if(LVGL_UPSTREAM_SOURCE_DIR AND EXISTS "${LVGL_UPSTREAM_SOURCE_DIR}/demos")
    target_include_directories(index PRIVATE "${LVGL_UPSTREAM_SOURCE_DIR}/demos")
endif()
''' if demo_sources else ""
    local_source = "/lvgl_source" if settings.lvgl_source_dir else ""

    (web_project / "CMakeLists.txt").write_text(
        f'''cmake_minimum_required(VERSION 3.20)
project(lvgl_ui_web C CXX)
set(CMAKE_C_STANDARD 99)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_EXECUTABLE_SUFFIX ".html")
add_compile_options(-sUSE_SDL=2)
add_link_options(-sUSE_SDL=2)
set(LV_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LV_BUILD_DEMOS OFF CACHE BOOL "" FORCE)
set(CONFIG_LV_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(CONFIG_LV_BUILD_DEMOS OFF CACHE BOOL "" FORCE)
set(LVGL_LOCAL_SOURCE_DIR {_quote(local_source)} CACHE PATH "Local LVGL source")
set(LVGL_UPSTREAM_SOURCE_DIR "")
if(LVGL_LOCAL_SOURCE_DIR AND EXISTS "${{LVGL_LOCAL_SOURCE_DIR}}/CMakeLists.txt")
    set(LVGL_UPSTREAM_SOURCE_DIR "${{LVGL_LOCAL_SOURCE_DIR}}")
    add_subdirectory("${{LVGL_LOCAL_SOURCE_DIR}}" lvgl)
else()
    include(FetchContent)
    FetchContent_Declare(lvgl GIT_REPOSITORY {_quote(settings.lvgl_git_repo)} GIT_TAG {_quote(settings.lvgl_git_ref)} GIT_SHALLOW TRUE)
    FetchContent_MakeAvailable(lvgl)
    set(LVGL_UPSTREAM_SOURCE_DIR "${{lvgl_SOURCE_DIR}}")
endif()
set(UI_SOURCES
{source_lines}
)
{demo_block}
add_executable(index src/main.c ${{UI_SOURCES}})
target_compile_definitions(index PRIVATE LV_CONF_INCLUDE_SIMPLE LVGL_SIM_WIDTH={width} LVGL_SIM_HEIGHT={height})
target_include_directories(index PRIVATE
{include_lines}
    "${{CMAKE_CURRENT_SOURCE_DIR}}"
)
{demo_include}
target_link_libraries(index PRIVATE lvgl)
target_link_options(index PRIVATE -sUSE_SDL=2 -sALLOW_MEMORY_GROWTH=1 -sASSERTIONS=1)
''',
        encoding="utf-8",
    )
    _write_conf(web_project / "lv_conf.h", entry_call)
    _write_main(src_dir / "main.c", entry_call, entry_header)
    return web_project
