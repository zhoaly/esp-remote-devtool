from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


PACKAGING_DIR = Path(__file__).resolve().parents[1] / "packaging"
sys.path.insert(0, str(PACKAGING_DIR))

from generate_build_assets import version_tuple, write_icons, write_version_info


class PackagingAssetTests(unittest.TestCase):
    def test_icon_and_version_assets_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            assets_dir = root / "assets"
            version_file = root / "version_info.txt"

            write_icons(assets_dir)
            write_version_info(version_file, "0.1.0")

            with Image.open(assets_dir / "agent.ico") as image:
                self.assertEqual(image.format, "ICO")
            self.assertTrue((assets_dir / "tray-running.png").exists())
            self.assertIn(
                "ProductVersion', '0.1.0'",
                version_file.read_text(encoding="utf-8"),
            )

    def test_version_tuple_is_four_part(self) -> None:
        self.assertEqual(version_tuple("1.2.3"), (1, 2, 3, 0))


if __name__ == "__main__":
    unittest.main()
