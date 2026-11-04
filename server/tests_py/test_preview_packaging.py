from __future__ import annotations

import os

import pytest
from app.builders.files import stage_web_preview


@pytest.mark.parametrize("relative", [".", "bin", "dist", "src", "custom/web"])
def test_preview_keeps_runtime_assets_and_excludes_build_inputs(tmp_path, relative):
    build = tmp_path / "build_web"
    root = build / relative
    runtime = {
        "index.html": b"preview",
        "index.js": b"script",
        "index.wasm": b"\x00asm",
        "index.data": b"preloaded",
        "assets/font.bin": b"font",
    }
    compiler = {
        "_deps/lvgl/private.c": b"private source",
        "CMakeFiles/main.o": b"object",
        "CMakeCache.txt": b"host paths",
        "lib/liblvgl.a": b"library",
        "cmake_install.cmake": b"install script",
    }
    for name, data in {**runtime, **compiler}.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    output = tmp_path / "preview"
    stage_web_preview(build, output)
    actual = {
        p.relative_to(output).as_posix(): p.read_bytes() for p in output.rglob("*") if p.is_file()
    }
    assert actual == runtime


@pytest.mark.skipif(os.name == "nt", reason="Creating symlinks requires Windows developer mode")
def test_preview_does_not_follow_links_outside_build(tmp_path):
    build = tmp_path / "build_web"
    build.mkdir()
    (build / "index.html").write_text("preview")
    private = tmp_path / "private.txt"
    private.write_text("must not be published")
    (build / "secret.txt").symlink_to(private)
    (build / "linked-dir").symlink_to(tmp_path, target_is_directory=True)
    output = tmp_path / "preview"
    stage_web_preview(build, output)
    assert sorted(p.name for p in output.iterdir()) == ["index.html"]
