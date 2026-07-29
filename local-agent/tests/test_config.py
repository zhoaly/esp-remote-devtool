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
                        "remote_build_url": "https://build.example/api/build/upload/",
                        "default_project_name": "demo",
                        "default_idf_image": "espressif/idf:v6.0.1",
                        "default_target": "esp32s3",
                    }
                )
                settings = config.load_settings()

            self.assertEqual(saved_path, config_path)
            self.assertEqual(
                settings.remote_build_url,
                "https://build.example/api/build/upload",
            )
            self.assertEqual(settings.host, "127.0.0.1")
            self.assertEqual(settings.port, 8765)
            self.assertIn("https://build.example", settings.allowed_origins)
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertNotIn("allowed_origins", payload)

    def test_invalid_remote_url_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            config.validate_remote_build_url("build.example/api/build/upload")

    def test_remote_urls_are_derived_from_upload_origin(self) -> None:
        upload_url = "https://build.example:8443/api/build/upload"
        self.assertEqual(
            config.derive_remote_ui_url(upload_url),
            "https://build.example:8443/tools/esp",
        )
        self.assertEqual(
            config.derive_remote_info_url(upload_url),
            "https://build.example:8443/api/info",
        )


if __name__ == "__main__":
    unittest.main()
