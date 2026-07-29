from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


CANVAS_SIZE = 256
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def create_agent_icon(status_color: str | None = None) -> Image.Image:
    image = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle(
        (18, 18, 238, 238),
        radius=50,
        fill="#12315A",
        outline="#2F80ED",
        width=10,
    )
    draw.rounded_rectangle(
        (62, 62, 194, 194),
        radius=24,
        fill="#EAF4FF",
        outline="#80BFFF",
        width=8,
    )

    for offset in (82, 112, 142, 172):
        draw.rounded_rectangle((42, offset, 70, offset + 10), radius=4, fill="#80BFFF")
        draw.rounded_rectangle((186, offset, 214, offset + 10), radius=4, fill="#80BFFF")
        draw.rounded_rectangle((offset, 42, offset + 10, 70), radius=4, fill="#80BFFF")
        draw.rounded_rectangle((offset, 186, offset + 10, 214), radius=4, fill="#80BFFF")

    draw.polygon(
        (
            (139, 78),
            (98, 137),
            (126, 137),
            (113, 179),
            (158, 119),
            (130, 119),
        ),
        fill="#F5A623",
    )

    if status_color:
        draw.ellipse(
            (166, 166, 238, 238),
            fill="#FFFFFF",
            outline="#12315A",
            width=5,
        )
        draw.ellipse((177, 177, 227, 227), fill=status_color)

    return image


def write_icons(assets_dir: Path) -> None:
    assets_dir.mkdir(parents=True, exist_ok=True)
    base = create_agent_icon()
    base.save(
        assets_dir / "agent.ico",
        format="ICO",
        sizes=[(size, size) for size in ICON_SIZES],
    )

    statuses = {
        "tray-running.png": "#22C55E",
        "tray-starting.png": "#F5A623",
        "tray-error.png": "#EF4444",
        "tray-stopped.png": "#94A3B8",
    }
    for filename, color in statuses.items():
        create_agent_icon(color).resize((64, 64), Image.Resampling.LANCZOS).save(
            assets_dir / filename,
            format="PNG",
        )


def version_tuple(version: str) -> tuple[int, int, int, int]:
    parts = version.strip().split(".")
    if not 1 <= len(parts) <= 4 or any(not item.isdigit() for item in parts):
        raise ValueError(f"Invalid numeric version: {version}")
    values = [int(item) for item in parts]
    values.extend([0] * (4 - len(values)))
    return tuple(values)  # type: ignore[return-value]


def write_version_info(output_path: Path, version: str) -> None:
    numeric = version_tuple(version)
    comma_version = ", ".join(str(item) for item in numeric)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({comma_version}),
    prodvers=({comma_version}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404B0',
        [
          StringStruct('CompanyName', 'zhoaly'),
          StringStruct('FileDescription', 'ESP Remote Build Agent'),
          StringStruct('FileVersion', '{version}'),
          StringStruct('InternalName', 'ESPRemoteBuildAgent'),
          StringStruct('OriginalFilename', 'ESPRemoteBuildAgent.exe'),
          StringStruct('ProductName', 'ESP Remote Build Agent'),
          StringStruct('ProductVersion', '{version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--version-file", type=Path, required=True)
    args = parser.parse_args()

    write_icons(args.assets_dir.resolve())
    write_version_info(args.version_file.resolve(), args.version)


if __name__ == "__main__":
    main()
