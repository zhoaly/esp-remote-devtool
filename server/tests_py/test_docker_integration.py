from __future__ import annotations

import os
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from app.builders.docker import docker_environment, docker_executable, run_command
from app.builders.process import BuildTimedOut, ProcessRunner

pytestmark = pytest.mark.skipif(
    os.getenv("ESP_TEST_DOCKER") != "1", reason="Set ESP_TEST_DOCKER=1 for real Linux Docker tests"
)


def test_real_docker_mount_and_timeout_cleanup(tmp_path):
    project = tmp_path / "工程 with spaces,comma"
    project.mkdir()
    name = f"esp-portability-{uuid.uuid4().hex}"
    image = "python:3.12-alpine"
    subprocess.run(
        [docker_executable(), "pull", image], check=True, timeout=180, env=docker_environment()
    )
    runner = ProcessRunner()
    runner.run(
        [
            *run_command(name, project),
            image,
            "python",
            "-c",
            "from pathlib import Path; Path('/project/result.txt').write_text('ok')",
        ],
        tmp_path / "docker.log",
        timeout_seconds=30,
        cancel_requested=lambda: False,
        container_name=name,
    )
    assert (project / "result.txt").read_text() == "ok"
    with pytest.raises(BuildTimedOut):
        runner.run(
            [*run_command(name, project), image, "python", "-c", "import time; time.sleep(120)"],
            tmp_path / "timeout.log",
            timeout_seconds=2,
            cancel_requested=lambda: False,
            container_name=name,
        )
    assert (
        subprocess.run(
            [docker_executable(), "inspect", name], capture_output=True, env=docker_environment()
        ).returncode
        != 0
    )


def test_reverse_proxy_can_reach_the_host_through_gateway(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"gateway-ok")

        def log_message(self, *_args):
            pass

    server = HTTPServer(("0.0.0.0", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    name = f"esp-gateway-{uuid.uuid4().hex}"
    try:
        ProcessRunner().run(
            [
                *run_command(name, tmp_path),
                "--add-host",
                "host.docker.internal:host-gateway",
                "python:3.12-alpine",
                "python",
                "-c",
                "import urllib.request; p=urllib.request.build_opener(urllib.request.ProxyHandler({})); "
                f"r=p.open('http://host.docker.internal:{server.server_port}',timeout=10); "
                "assert r.read()==b'gateway-ok'",
            ],
            tmp_path / "gateway.log",
            timeout_seconds=30,
            cancel_requested=lambda: False,
            container_name=name,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
