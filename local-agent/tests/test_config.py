from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

import config


class ConfigTests(unittest.TestCase):
    def test_save_and_reload_user_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            config_path = Path(temporary_dir) / "config.json"
            with patch.dict(
                os.environ,
                {"ESP_LOCAL_AGENT_CONFIG_PATH": str(config_path)},
                clear=False,
            ):
                saved_path = config.save_user_settings(
                    {
                        "remote_build_url": "https://build.example/api/v2/builds/esp/upload/",
                        "default_project_name": "demo",
                        "default_idf_image": "espressif/idf:v6.0.1",
                        "default_target": "esp32s3",
                    }
                )
                settings = config.load_settings()
                payload = json.loads(config_path.read_text(encoding="utf-8"))

            self.assertEqual(saved_path, config_path.resolve())
            self.assertEqual(
                settings.remote_build_url,
                "https://build.example/api/v2/builds/esp/upload",
            )
            self.assertEqual(settings.host, "127.0.0.1")
            self.assertEqual(settings.port, 8765)
            self.assertIn("https://build.example", settings.allowed_origins)
            self.assertNotIn("allowed_origins", payload)

    def test_tray_save_preserves_remote_build_servers(self) -> None:
        servers = {
            "https://second.example": "https://second.example/api/v2/builds/esp/upload"
        }
        with tempfile.TemporaryDirectory() as temporary_dir:
            config_path = Path(temporary_dir) / "config.json"
            config_path.write_text(json.dumps({"remote_build_servers": servers}), encoding="utf-8")
            with patch.dict(os.environ, {"ESP_LOCAL_AGENT_CONFIG_PATH": str(config_path)}):
                config.save_user_settings(config.settings_to_user_dict(config.load_settings()))
                self.assertEqual(config.load_settings().remote_build_servers, servers)

    def test_invalid_remote_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            config.validate_remote_build_url("build.example/api/v2/builds/esp/upload")

    def test_remote_urls_are_derived_from_upload_origin(self) -> None:
        upload_url = "https://build.example:8443/api/v2/builds/esp/upload"
        self.assertEqual(
            config.derive_remote_ui_url(upload_url),
            "https://build.example:8443/tools/esp",
        )
        self.assertEqual(
            config.derive_remote_info_url(upload_url),
            "https://build.example:8443/api/v2/info",
        )


if __name__ == "__main__":
    unittest.main()
