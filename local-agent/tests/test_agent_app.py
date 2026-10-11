from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from agent_app import create_app
from config import AgentSettings


class AgentAppTests(unittest.TestCase):
    def test_factory_keeps_existing_api_routes(self) -> None:
        settings = AgentSettings(
            remote_build_url="https://build.example/api/v2/builds/esp/upload",
            default_project_name="demo",
            default_idf_image="espressif/idf:v6.0.1",
            default_target="esp32s3",
            allowed_origins=["https://build.example"],
        )
        app = create_app(settings)
        paths = {route.path for route in app.routes}

        self.assertTrue(
            {
                "/",
                "/api/serial_ports",
                "/api/flash_from_artifact",
                "/api/build_from_path",
                "/api/lvgl/build_from_path",
                "/api/lvgl/build_ui_from_path",
            }.issubset(paths)
        )
        self.assertIs(app.state.agent_settings, settings)

    def test_root_endpoint_reports_running(self) -> None:
        settings = AgentSettings(
            remote_build_url="https://build.example/api/v2/builds/esp/upload",
            default_project_name="demo",
            default_idf_image="idf",
            default_target="esp32s3",
            allowed_origins=["https://build.example"],
        )
        app = create_app(settings)
        root_route = next(route for route in app.routes if route.path == "/")
        payload = root_route.endpoint()

        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["remote_build_url"], settings.remote_build_url)


if __name__ == "__main__":
    unittest.main()
