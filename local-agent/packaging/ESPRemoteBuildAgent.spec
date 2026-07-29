from pathlib import Path

from PyInstaller.utils.hooks import collect_all


PACKAGING_DIR = Path(SPECPATH).resolve()
PROJECT_ROOT = PACKAGING_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"
ASSETS_DIR = PROJECT_ROOT / "assets"
VERSION_FILE = PROJECT_ROOT / "build" / "version_info.txt"

esptool_datas, esptool_binaries, esptool_hiddenimports = collect_all("esptool")

datas = [
    (str(ASSETS_DIR / "agent.ico"), "assets"),
    (str(ASSETS_DIR / "tray-running.png"), "assets"),
    (str(ASSETS_DIR / "tray-starting.png"), "assets"),
    (str(ASSETS_DIR / "tray-error.png"), "assets"),
    (str(ASSETS_DIR / "tray-stopped.png"), "assets"),
    *esptool_datas,
]

analysis = Analysis(
    [str(SRC_DIR / "tray_main.py")],
    pathex=[str(SRC_DIR)],
    binaries=esptool_binaries,
    datas=datas,
    hiddenimports=[*esptool_hiddenimports, "pystray._win32"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pystray._appindicator",
        "pystray._darwin",
        "pystray._gtk",
        "pystray._xorg",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ESPRemoteBuildAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(ASSETS_DIR / "agent.ico"),
    version=str(VERSION_FILE),
    manifest=str(PACKAGING_DIR / "app.manifest"),
)

collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    name="ESPRemoteBuildAgent",
)
