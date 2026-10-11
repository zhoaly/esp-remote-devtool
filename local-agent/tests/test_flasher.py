from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from flash_helper import extract_artifact
from flasher import _esptool_worker, build_esptool_args


class FlasherTests(unittest.TestCase):
    def test_build_esptool_args_matches_existing_flash_contract(self) -> None:
        firmware = Path("C:/firmware/firmware_merged.bin")
        args = build_esptool_args(firmware, "COM7", 460800, "esp32s3")

        self.assertEqual(args[:2], ["--chip", "esp32s3"])
        self.assertIn("write_flash", args)
        self.assertEqual(args[-2:], ["0x0", str(firmware)])

    def test_worker_captures_success_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            result_path = Path(temporary_dir) / "result.json"
            with patch("flasher.esptool.main", side_effect=lambda _args: print("ok")):
                _esptool_worker(["version"], str(result_path))

            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertTrue(payload["ok"])
            self.assertIn("ok", payload["log"])

    def test_worker_captures_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            result_path = Path(temporary_dir) / "result.json"
            with patch(
                "flasher.esptool.main",
                side_effect=RuntimeError("serial failed"),
            ):
                _esptool_worker(["version"], str(result_path))

            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertFalse(payload["ok"])
            self.assertIn("serial failed", payload["error"])

    def test_extract_rejects_parent_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            archive_path = root / "firmware.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../outside.bin", b"bad")

            with self.assertRaises(RuntimeError):
                extract_artifact(archive_path, root)


if __name__ == "__main__":
    unittest.main()
