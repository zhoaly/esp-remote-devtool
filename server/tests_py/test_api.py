from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from app.domain.jobs import JobKind, JobStage, JobStatus, SourceMode
from app.main import create_app
from app.storage.repositories import JobRepository
from fastapi.testclient import TestClient


def zip_payload() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("demo/CMakeLists.txt", "cmake_minimum_required(VERSION 3.16)")
        archive.writestr("demo/main/main.c", "int main(void) { return 0; }")
    return output.getvalue()


def test_v2_upload_cancel_retry_and_v1_removal(settings, database) -> None:
    engine, factory = database
    app = create_app(settings, engine)
    with TestClient(app) as client:
        response = client.post(
            "/api/v2/builds/esp/upload",
            files={"file": ("demo.zip", zip_payload(), "application/zip")},
            data={
                "project_name": "demo",
                "idf_image": settings.default_idf_image,
                "target": "esp32s3",
            },
        )
        assert response.status_code == 202, response.text
        job = response.json()
        assert job["status"] == "queued"
        assert job["configuration"]["kind"] == "esp"
        assert "workspace_path" not in response.text

        old_api = client.get("/api/build/upload")
        assert old_api.status_code == 404
        assert old_api.json()["error"]["code"] == "http_error"
        assert client.get("/api/v2/jobs?kind=esp").json()[0]["id"] == job["id"]

        canceled = client.post(f"/api/v2/jobs/{job['id']}/cancel")
        assert canceled.status_code == 200
        assert canceled.json()["status"] == "canceled"

        retried = client.post(f"/api/v2/jobs/{job['id']}/retry")
        assert retried.status_code == 202
        assert retried.json()["retry_of_job_id"] == job["id"]
        assert retried.json()["status"] == "queued"

        with factory() as session:
            original_record = JobRepository(session).get(job["id"])
            retry_record = JobRepository(session).get(retried.json()["id"])
            assert retry_record.upload_path != original_record.upload_path
            assert Path(retry_record.upload_path or "").read_bytes() == Path(
                original_record.upload_path or ""
            ).read_bytes()


def test_standard_validation_error(settings, database) -> None:
    engine, _ = database
    with TestClient(create_app(settings, engine)) as client:
        response = client.post(
            "/api/v2/builds/esp/upload",
            files={"file": ("demo.zip", zip_payload(), "application/zip")},
            data={"project_name": "<script>", "idf_image": "bad image", "target": "esp32s3"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def test_configuration_workspace_and_lvgl_submission_routes(settings, database) -> None:
    engine, _ = database
    esp_workspace = settings.workspace_dir / "configured-esp"
    lvgl_workspace = settings.workspace_dir / "configured-lvgl"
    esp_workspace.mkdir()
    lvgl_workspace.mkdir()
    settings.workspaces_config.write_text(
        json.dumps(
            {
                "workspaces": {
                    "esp-demo": {
                        "path": str(esp_workspace),
                        "project_type": "esp_idf",
                        "project_name": "esp-demo",
                        "target": "esp32s3",
                        "idf_image": settings.default_idf_image,
                    },
                    "lvgl-demo": {
                        "path": str(lvgl_workspace),
                        "project_type": "lvgl",
                        "project_name": "lvgl-demo",
                        "width": 320,
                        "height": 240,
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    with TestClient(create_app(settings, engine)) as client:
        assert client.get("/api/v2/info").json()["version"] == "0.2.0"
        assert client.get("/api/v2/home/tools").status_code == 200
        assert client.get("/api/v2/config/esp").json()["allow_custom"] is False
        assert len(client.get("/api/v2/workspaces?kind=esp").json()["workspaces"]) == 1
        assert len(client.get("/api/v2/workspaces?kind=lvgl").json()["workspaces"]) == 1

        esp = client.post("/api/v2/builds/esp/workspace", json={"workspace_id": "esp-demo"})
        assert esp.status_code == 202
        assert esp.json()["configuration"]["kind"] == "esp"

        lvgl = client.post(
            "/api/v2/builds/lvgl/workspace", json={"workspace_id": "lvgl-demo"}
        )
        assert lvgl.status_code == 202
        assert lvgl.json()["configuration"]["kind"] == "lvgl"

        for endpoint in ("upload", "ui-upload"):
            submitted = client.post(
                f"/api/v2/builds/lvgl/{endpoint}",
                files={"file": ("demo.zip", zip_payload(), "application/zip")},
                data={"project_name": "lvgl-demo", "width": "320", "height": "240"},
            )
            assert submitted.status_code == 202
            assert submitted.json()["source_mode"] == (
                "upload" if endpoint == "upload" else "ui_upload"
            )


def test_incremental_log_response(settings, database) -> None:
    engine, _ = database
    app = create_app(settings, engine)
    with TestClient(app) as client:
        created = client.post(
            "/api/v2/builds/esp/upload",
            files={"file": ("demo.zip", zip_payload(), "application/zip")},
            data={
                "project_name": "demo",
                "idf_image": settings.default_idf_image,
                "target": "esp32s3",
            },
        ).json()
        (settings.log_dir / f"{created['id']}.log").write_text("first\nsecond\n", encoding="utf-8")
        first = client.get(f"/api/v2/jobs/{created['id']}/logs?offset=0&limit=6").json()
        second = client.get(
            f"/api/v2/jobs/{created['id']}/logs?offset={first['next_offset']}&limit=100"
        ).json()
        assert first["content"] == "first\n"
        assert second["content"] == "second\n"


def test_ota_release_lifecycle(settings, database) -> None:
    engine, factory = database
    app_bin = settings.workspace_dir / "ota-demo" / "build" / "demo.bin"
    app_bin.parent.mkdir(parents=True)
    app_bin.write_bytes(b"firmware")
    with factory.begin() as session:
        jobs = JobRepository(session)
        record = jobs.create(
            kind=JobKind.ESP,
            source_mode=SourceMode.WORKSPACE.value,
            project_name="ota-demo",
            request_json={
                "kind": "esp",
                "project_name": "ota-demo",
                "target": "esp32s3",
                "idf_image": settings.default_idf_image,
                "workspace_path": str(settings.workspace_dir / "ota-demo"),
            },
            log_path=str(settings.log_dir / "ota-demo.log"),
        )
        jobs.transition(record, JobStatus.RUNNING, "running", stage=JobStage.BUILDING)
        jobs.transition(
            record,
            JobStatus.SUCCEEDED,
            "done",
            result={
                "ota_publishable": True,
                "ota_app_sha256": None,
                "_ota_app_path": str(app_bin),
            },
        )
        job_id = record.id

    with TestClient(create_app(settings, engine)) as client:
        published = client.post(
            "/api/v2/ota/releases",
            json={"job_id": job_id, "channel": "test", "version": "1.0.0"},
        )
        assert published.status_code == 201, published.text
        release = published.json()
        assert release["job_id"] == job_id
        assert client.get(
            "/api/v2/ota/latest?project=ota-demo&chip=esp32s3&channel=test"
        ).json()["version"] == "1.0.0"
        assert client.get(f"/api/v2/ota/manifests/{release['id']}").json()["sha256"]
        firmware = client.get(f"/api/v2/ota/firmware/{release['id']}")
        assert firmware.status_code == 200
        assert firmware.content == b"firmware"
        assert client.delete(f"/api/v2/ota/releases/{release['id']}").status_code == 200
        missing = client.get(f"/api/v2/ota/manifests/{release['id']}")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "ota_release_not_found"
