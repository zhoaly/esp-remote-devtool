from __future__ import annotations

import zipfile
from dataclasses import replace
from pathlib import Path

from app.domain.jobs import JobKind, JobStatus, SourceMode
from app.services.worker import BuildWorker
from app.storage.repositories import ArtifactRepository, JobRepository


def write_zip(path: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_real_esp_builder_with_fake_processes(settings, database, tmp_path: Path) -> None:
    build_script = tmp_path / "fake-esp-build.sh"
    package_script = tmp_path / "fake-package.sh"
    write_executable(
        build_script,
        """#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$1/build/bootloader" "$1/build/partition_table"
printf app > "$1/build/demo.bin"
printf merged > "$1/build/firmware_merged.bin"
printf boot > "$1/build/bootloader/bootloader.bin"
printf partition > "$1/build/partition_table/partition-table.bin"
printf '{}' > "$1/build/flasher_args.json"
printf '{"project_name":"demo","app_bin":"demo.bin","project_version":"1.2.3"}' > "$1/build/project_description.json"
""",
    )
    write_executable(
        package_script,
        """#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$2"
printf package > "$2/${3}_${4}_firmware.zip"
echo "$2/${3}_${4}_firmware.zip"
""",
    )
    worker_settings = replace(
        settings,
        build_script=build_script,
        package_script=package_script,
        esp_build_timeout_seconds=10,
    )
    upload = settings.upload_dir / "esp.zip"
    write_zip(
        upload,
        {
            "demo/CMakeLists.txt": "cmake_minimum_required(VERSION 3.16)",
            "demo/main/main.c": "int main(void) { return 0; }",
        },
    )
    _, factory = database
    with factory.begin() as session:
        record = JobRepository(session).create(
            kind=JobKind.ESP,
            source_mode=SourceMode.UPLOAD.value,
            project_name="demo",
            request_json={
                "kind": "esp",
                "project_name": "demo",
                "target": "esp32s3",
                "idf_image": settings.default_idf_image,
            },
            upload_path=str(upload),
            workspace_path=str(settings.workspace_dir / "esp-e2e"),
            log_path=str(settings.log_dir / "esp-e2e.log"),
        )
        job_id = record.id

    assert BuildWorker(worker_settings, factory).run_once()
    with factory() as session:
        job = JobRepository(session).get(job_id)
        artifacts = ArtifactRepository(session).list_for_job(job_id)
        assert job.status == JobStatus.SUCCEEDED.value
        assert job.result_json["ota_project_version"] == "1.2.3"
        assert artifacts[0].filename == f"demo_{job_id}_firmware.zip"
    log = (settings.log_dir / "esp-e2e.log").read_text(encoding="utf-8")
    assert settings.default_idf_image in log
    assert "esp32s3" in log


def test_real_lvgl_builder_with_fake_process(settings, database, tmp_path: Path) -> None:
    build_script = tmp_path / "fake-lvgl-build.sh"
    write_executable(
        build_script,
        """#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$2"
printf '<html><body>preview</body></html>' > "$2/index.html"
""",
    )
    worker_settings = replace(
        settings,
        lvgl_build_script=build_script,
        lvgl_build_timeout_seconds=10,
    )
    upload = settings.upload_dir / "lvgl.zip"
    write_zip(upload, {"demo/CMakeLists.txt": "cmake_minimum_required(VERSION 3.16)"})
    _, factory = database
    with factory.begin() as session:
        record = JobRepository(session).create(
            kind=JobKind.LVGL,
            source_mode=SourceMode.UPLOAD.value,
            project_name="lvgl-demo",
            request_json={
                "kind": "lvgl",
                "project_name": "lvgl-demo",
                "width": 320,
                "height": 240,
                "lvgl_version": "9.x",
            },
            upload_path=str(upload),
            workspace_path=str(settings.workspace_dir / "lvgl-e2e"),
            log_path=str(settings.log_dir / "lvgl-e2e.log"),
        )
        job_id = record.id

    assert BuildWorker(worker_settings, factory).run_once()
    with factory() as session:
        job = JobRepository(session).get(job_id)
        artifacts = ArtifactRepository(session).list_for_job(job_id)
        assert job.status == JobStatus.SUCCEEDED.value
        assert job.result_json["preview_url"].endswith("/preview/index.html")
        assert artifacts[0].filename.endswith("_lvgl_preview.zip")
    assert (settings.lvgl_preview_dir / job_id / "index.html").is_file()
