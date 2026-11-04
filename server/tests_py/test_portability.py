from __future__ import annotations

import json
import os
import plistlib
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import pytest
from app.builders.docker import bind_mount, run_command
from app.core.config import SERVER_DIR
from app.core.processes import popen_options, terminate_tree
from app.domain.jobs import JobKind, JobStage, JobStatus, SourceMode
from app.main import create_app
from app.service_config import write_config
from app.storage.database import create_database_engine
from app.storage.portability import portable_value, relocate_data
from app.storage.repositories import ArtifactRepository, JobRepository
from fastapi.testclient import TestClient
from filelock import FileLock


def test_managed_paths_survive_a_move(settings, tmp_path):
    path = settings.workspace_dir / "项目 with spaces" / "demo.bin"
    value = settings.stored_path(path)
    assert value == "workspaces/项目 with spaces/demo.bin"
    moved = replace(settings, data_dir=tmp_path / "new data")
    assert moved.resolve_path(value) == moved.data_dir / value
    assert settings.resolve_path(str(path)) == path
    with pytest.raises(ValueError):
        settings.resolve_path("../escape")
    if os.name != "nt":
        with pytest.raises(ValueError, match="Foreign"):
            settings.resolve_path("C:/old/data/logs/test.log")


@pytest.mark.parametrize(
    "root,value",
    [
        ("/old/data", "/old/data/logs/a.log"),
        (r"C:\old\data", r"C:\old\data\logs\a.log"),
    ],
)
def test_legacy_paths_use_the_source_platform_rules(root, value):
    assert portable_value(value, [root]) == "logs/a.log"
    assert portable_value(root + "-sibling/a", [root]) == root + "-sibling/a"


def test_relocation_is_previewed_backed_up_and_idempotent(settings, database):
    _, factory = database
    with factory.begin() as session:
        job_id = (
            JobRepository(session)
            .create(
                kind=JobKind.ESP,
                source_mode=SourceMode.UPLOAD.value,
                project_name="demo",
                request_json={"kind": "esp"},
                log_path="/old/data/logs/test.log",
                upload_path="/old/data/uploads/test.zip",
            )
            .id
        )
    preview = relocate_data(settings, ["/old/data"])
    assert preview["changed_paths"] == 2 and preview["backup"] is None
    with factory() as session:
        assert JobRepository(session).get(job_id).log_path == "/old/data/logs/test.log"
    result = relocate_data(settings, ["/old/data"], apply=True)
    assert Path(result["backup"]).is_file()
    with factory() as session:
        assert JobRepository(session).get(job_id).log_path == "logs/test.log"
    assert relocate_data(settings, ["/old/data"], apply=True)["changed_paths"] == 0


def test_moved_data_keeps_logs_downloads_and_ota_working(settings, database, tmp_path):
    engine, factory = database
    app_bin = settings.workspace_dir / "demo/build/demo.bin"
    app_bin.parent.mkdir(parents=True)
    app_bin.write_bytes(b"firmware")
    (settings.log_dir / "demo.log").write_bytes(b"build complete\n")
    package = settings.artifact_dir / "demo.zip"
    package.write_bytes(b"package")
    with factory.begin() as session:
        jobs = JobRepository(session)
        job = jobs.create(
            kind=JobKind.ESP,
            source_mode=SourceMode.UPLOAD.value,
            project_name="demo",
            request_json={
                "kind": "esp",
                "target": "esp32s3",
                "idf_image": settings.default_idf_image,
            },
            log_path="logs/demo.log",
        )
        jobs.transition(job, JobStatus.RUNNING, "running", stage=JobStage.BUILDING)
        jobs.transition(
            job,
            JobStatus.SUCCEEDED,
            "done",
            result={
                "ota_publishable": True,
                "_ota_app_path": settings.stored_path(app_bin),
            },
        )
        job_id = job.id
        artifact_id = (
            ArtifactRepository(session)
            .create(
                job_id=job_id,
                kind="firmware",
                filename="demo.zip",
                path="artifacts/demo.zip",
                media_type="application/zip",
                size=7,
                sha256="test",
            )
            .id
        )
    engine.dispose()
    destination = tmp_path / "moved data"
    shutil.copytree(settings.data_dir, destination)
    path_fields = (
        "data_dir",
        "upload_dir",
        "workspace_dir",
        "artifact_dir",
        "ota_release_dir",
        "lvgl_preview_dir",
        "log_dir",
        "database_path",
        "worker_lock_path",
    )
    moved = replace(
        settings,
        **{
            field: destination / getattr(settings, field).relative_to(settings.data_dir)
            for field in path_fields
        },
    )
    moved_engine = create_database_engine(moved)
    try:
        with TestClient(create_app(moved, moved_engine)) as client:
            assert client.get(f"/api/v2/jobs/{job_id}/logs").json()["content"] == "build complete\n"
            assert client.get(f"/api/v2/artifacts/{artifact_id}").content == b"package"
            release = client.post(
                "/api/v2/ota/releases",
                json={
                    "job_id": job_id,
                    "channel": "test",
                    "version": "1.0.0",
                },
            )
            assert release.status_code == 201, release.text
            assert client.get(f"/api/v2/ota/firmware/{release.json()['id']}").content == b"firmware"
    finally:
        moved_engine.dispose()


def test_worker_lock_excludes_a_second_process(tmp_path):
    lock_path = tmp_path / "worker.lock"
    with FileLock(lock_path, timeout=0):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from filelock import FileLock; FileLock(sys.argv[1], timeout=0).acquire()",
                str(lock_path),
            ],
            capture_output=True,
            timeout=15,
        )
    assert result.returncode != 0
    assert b"Timeout" in result.stderr


def test_mount_csv_and_native_docker_command(tmp_path, monkeypatch):
    import csv

    import app.builders.docker as docker

    source = tmp_path / "目录 with spaces,comma"
    source.mkdir()
    fields = next(csv.reader([bind_mount(source, "/project")[1]]))
    assert f"source={source.resolve()}" in fields
    monkeypatch.setattr(docker, "docker_executable", lambda: "docker")
    monkeypatch.setattr(docker.sys, "platform", "win32")
    monkeypatch.delenv("ESP_DOCKER_USER", raising=False)
    command = run_command("esp-test", source)
    assert "--user" not in command
    assert "bash" not in command


@pytest.mark.parametrize("target", ["systemd", "launchd", "windows"])
def test_service_config_uses_same_entry_point(settings, tmp_path, target):
    output = tmp_path / target
    write_config(target, output, tmp_path / ".env", settings)
    if target == "launchd":
        value = plistlib.loads(output.read_bytes())
        assert value["ProgramArguments"][-1] == "start"
        assert str(settings.data_dir) in value["ProgramArguments"]
    elif target == "windows":
        value = ET.fromstring(output.read_bytes())
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        assert "manage.py" in value.find(".//t:Arguments", ns).text
    else:
        assert "ExecStop=" in output.read_text()
        assert "--data-dir" in output.read_text()


def test_server_start_stop_restart_and_worker_recovery(tmp_path):
    # Real API and worker processes, isolated from the developer's runtime data.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    data = tmp_path / "服务 data"
    env = os.environ.copy()
    env.update(
        ESP_SERVER_BASE_DIR=str(SERVER_DIR),
        ESP_SERVER_DATA_DIR=str(data),
        ESP_SERVER_HOST="127.0.0.1",
        ESP_SERVER_PORT=str(port),
        ESP_SERVER_IPV6_PROXY="0",
        PYTHONUTF8="1",
    )
    command = [
        sys.executable,
        str(SERVER_DIR / "manage.py"),
        "--env-file",
        str(tmp_path / "absent.env"),
    ]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(2):
        process = subprocess.Popen(
            [*command, "start", "--skip-docker-check"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **popen_options(),
        )
        try:
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                assert process.poll() is None, process.communicate()[0].decode(errors="replace")
                try:
                    with opener.open(f"http://127.0.0.1:{port}/api/v2/info", timeout=1) as response:
                        assert json.load(response)["version"] == "0.2.0"
                    break
                except (OSError, urllib.error.URLError):
                    time.sleep(0.2)
            else:
                pytest.fail("Server did not become ready")
            stopped = subprocess.run([*command, "stop"], env=env, capture_output=True, timeout=50)
            assert stopped.returncode == 0, stopped.stderr.decode(errors="replace")
            output = process.communicate(timeout=10)[0]
            assert process.returncode == 0, output.decode(errors="replace")
            assert b"Persistent build worker" in output
        finally:
            if process.poll() is None:
                terminate_tree(process)
