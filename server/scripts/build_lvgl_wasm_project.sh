#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$1"
OUTPUT_DIR="$2"
EMSDK_IMAGE="${3:-emscripten/emsdk:latest}"
WIDTH="${4:-128}"
HEIGHT="${5:-296}"
LVGL_SOURCE_DIR="${6:-}"
SDL2_PORT_DIR="${7:-}"
EMSDK_CACHE_DIR="${8:-}"

if [ ! -d "$PROJECT_DIR" ]; then
    echo "ERROR: project dir not found: $PROJECT_DIR"
    exit 1
fi

if [ ! -f "$PROJECT_DIR/CMakeLists.txt" ]; then
    echo "ERROR: CMakeLists.txt not found in LVGL project root: $PROJECT_DIR"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
rm -rf "$OUTPUT_DIR"/*

echo "========== LVGL WebAssembly Build =========="
echo "Project dir : $PROJECT_DIR"
echo "Output dir  : $OUTPUT_DIR"
echo "EMSDK image : $EMSDK_IMAGE"
echo "Canvas      : ${WIDTH}x${HEIGHT}"
echo "LVGL source : ${LVGL_SOURCE_DIR:-FetchContent}"
echo "SDL2 port   : ${SDL2_PORT_DIR:-Emscripten default}"
echo "EMSDK cache : ${EMSDK_CACHE_DIR:-container default}"
echo "============================================"

DOCKER_ARGS=(
    --rm
    -i
    --user "$(id -u):$(id -g)"
    -e HOME=/tmp
    -e LVGL_SIM_WIDTH="$WIDTH"
    -e LVGL_SIM_HEIGHT="$HEIGHT"
    -v "$PROJECT_DIR:/project"
    -v "$OUTPUT_DIR:/out"
    -w /project
)

if [ -n "$LVGL_SOURCE_DIR" ]; then
    if [ ! -f "$LVGL_SOURCE_DIR/CMakeLists.txt" ]; then
        echo "ERROR: LVGL source dir is invalid: $LVGL_SOURCE_DIR"
        exit 1
    fi
    DOCKER_ARGS+=(-v "$LVGL_SOURCE_DIR:/lvgl_source:ro")
fi

if [ -n "$SDL2_PORT_DIR" ]; then
    if [ ! -f "$SDL2_PORT_DIR/include/SDL.h" ]; then
        echo "ERROR: SDL2 port dir is invalid: $SDL2_PORT_DIR"
        exit 1
    fi
    DOCKER_ARGS+=(
        -v "$SDL2_PORT_DIR:/emscripten_ports/sdl2:ro"
        -e EMCC_LOCAL_PORTS=sdl2=/emscripten_ports/sdl2
    )
fi

if [ -n "$EMSDK_CACHE_DIR" ]; then
    mkdir -p "$EMSDK_CACHE_DIR"
    DOCKER_ARGS+=(
        -v "$EMSDK_CACHE_DIR:/emscripten_cache"
        -e EM_CACHE=/emscripten_cache
    )
fi

docker run "${DOCKER_ARGS[@]}" \
    "$EMSDK_IMAGE" \
    bash -lc '
        set -euo pipefail

        rm -rf build_web
        emcmake cmake -S . -B build_web \
            -DLVGL_SIM_WIDTH="${LVGL_SIM_WIDTH}" \
            -DLVGL_SIM_HEIGHT="${LVGL_SIM_HEIGHT}"
        cmake --build build_web -j"$(nproc)"

        copy_preview_dir() {
            local candidate="$1"
            if [ -f "$candidate/index.html" ]; then
                cp -a "$candidate"/. /out/
                return 0
            fi
            return 1
        }

        copy_preview_dir build_web ||
        copy_preview_dir build_web/bin ||
        copy_preview_dir build_web/dist ||
        copy_preview_dir build_web/src ||
        {
            found_index="$(find build_web -maxdepth 4 -type f -name index.html | head -n 1)"
            if [ -z "$found_index" ]; then
                echo "ERROR: index.html not found in Emscripten build output"
                exit 1
            fi
            cp -a "$(dirname "$found_index")"/. /out/
        }

        test -f /out/index.html
    '

echo "========== LVGL Build Finished =========="
find "$OUTPUT_DIR" -maxdepth 2 -type f | sort
