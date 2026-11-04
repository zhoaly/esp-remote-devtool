from __future__ import annotations

import csv
import json
import sys
import zipfile
from pathlib import Path

import pytest
from app.builders.process import ProcessRunner
from app.domain.jobs import JobKind, JobStatus, SourceMode
from app.services.worker import BuildWorker
from app.storage.repositories import ArtifactRepository, JobRepository


@pytest.fixture()
def fake_docker(tmp_path, monkeypatch):
    script = tmp_path / "fake_docker.py"
    script.write_text(
        """import csv, json, pathlib, sys
args = sys.argv[1:]
mounts = {}
for index, arg in enumerate(args):
    if arg == "--mount":
        fields = dict(item.split("=", 1) for item in next(csv.reader([args[index+1]])) if "=" in item)
        mounts[fields["target"]] = pathlib.Path(fields["source"])
project = mounts["/project"]
(project / "docker-arguments.json").write_text(json.dumps(args), encoding="utf-8")
if "/out" in mounts:
    (mounts["/out"] / "index.html").write_text("<html>preview</html>", encoding="utf-8")
    (mounts["/out"] / "index.wasm").write_bytes(b"wasm")
else:
    build = project / "build"
    (build / "bootloader").mkdir(parents=True)
    (build / "partition_table").mkdir()
    for name in ("demo.bin", "firmware_merged.bin", "bootloader/bootloader.bin", "partition_table/partition-table.bin"):
        (build / name).write_bytes(b"firmware")
    (build / "flasher_args.json").write_text("{}", encoding="utf-8")
    (build / "project_description.json").write_text(json.dumps({"project_name":"demo", "app_bin":"demo.bin", "project_version":"1.2.3"}), encoding="utf-8")
""",
        encoding="utf-8",
    )
    original = ProcessRunner.run

    def run(self, command, *args, **kwargs):
        return original(self, [sys.executable, str(script), *command[1:]], *args, **kwargs)

    monkeypatch.setattr(ProcessRunner, "run", run)
    monkeypatch.setattr(ProcessRunner, "cleanup_container", staticmethod(lambda _: None))


@pytest.mark.parametrize("kind", [JobKind.ESP, JobKind.LVGL])
def test_builder_uses_docker_and_python_packaging(settings, database, fake_docker, kind):
    upload = settings.upload_dir / "source.zip"
    with zipfile.ZipFile(upload, "w") as archive:
        archive.writestr(
            "工程 with spaces,comma/CMakeLists.txt", "cmake_minimum_required(VERSION 3.16)"
        )
        archive.writestr("工程 with spaces,comma/main/main.c", "int main(void) { return 0; }")
    _, factory = database
    configuration = {"kind": kind.value, "project_name": "demo"}
    if kind == JobKind.ESP:
        configuration.update(target="esp32s3", idf_image=settings.default_idf_image)
    else:
        configuration.update(width=320, height=240, lvgl_version="9.x")
    with factory.begin() as session:
        job = JobRepository(session).create(
            kind=kind,
            source_mode=SourceMode.UPLOAD.value,
            project_name="demo",
            request_json=configuration,
            upload_path=settings.stored_path(upload),
            workspace_path=f"workspaces/{kind.value}-test",
            log_path=f"logs/{kind.value}.log",
        )
        job_id = job.id
    assert BuildWorker(settings, factory).run_once()
    with factory() as session:
        job = JobRepository(session).get(job_id)
        assert job.status == JobStatus.SUCCEEDED.value, job.error_message
        artifact = ArtifactRepository(session).list_for_job(job_id)[0]
        assert not Path(artifact.path).is_absolute()
        with zipfile.ZipFile(settings.resolve_path(artifact.path)) as archive:
            if kind == JobKind.ESP:
                info = json.loads(archive.read("ota_info.json"))
                assert info["chip"] == "esp32s3"
                assert info["size"] == len(b"firmware")
                assert "firmware_merged.sha256" in archive.namelist()
                assert job.result_json["ota_project_version"] == "1.2.3"
                assert not Path(job.result_json["_ota_app_path"]).is_absolute()
            else:
                assert archive.read("index.wasm") == b"wasm"
    arguments = json.loads(
        next(
            (settings.workspace_dir / f"{kind.value}-test").rglob("docker-arguments.json")
        ).read_text(encoding="utf-8")
    )
    mounts = [
        next(csv.reader([arguments[i + 1]]))
        for i, value in enumerate(arguments)
        if value == "--mount"
    ]
    assert any("target=/project" in mount for mount in mounts)
    assert "bash" in arguments  # Bash is a container command, never the host executable.
    if kind == JobKind.ESP:
        assert "IDF_TARGET=esp32s3" in arguments
        assert settings.default_idf_image in arguments
