from __future__ import annotations

import contextlib
import io
import json
import multiprocessing
import shutil
from pathlib import Path

import esptool
from flash_helper import download_artifact_zip, extract_artifact

FLASH_TIMEOUT_SECONDS = 180


def build_esptool_args(
    firmware_path: Path,
    com_port: str,
    baud: int,
    chip: str,
) -> list[str]:
    return [
        "--chip",
        chip,
        "-p",
        com_port,
        "-b",
        str(baud),
        "--before",
        "default-reset",
        "--after",
        "hard-reset",
        "write_flash",
        "0x0",
        str(firmware_path),
    ]


def _esptool_worker(command: list[str], result_path_value: str) -> None:
    result_path = Path(result_path_value)
    output = io.StringIO()
    payload: dict[str, object]

    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            esptool.main(command)
        payload = {"ok": True, "log": output.getvalue()}
    except BaseException as exc:
        payload = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "log": output.getvalue(),
        }

    try:
        result_path.write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return


def run_esptool_process(
    command: list[str],
    result_path: Path,
    timeout: int = FLASH_TIMEOUT_SECONDS,
) -> str:
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=_esptool_worker,
        args=(command, str(result_path)),
        name="ESPFlashWorker",
    )
    process.start()
    process.join(timeout)

    if process.is_alive():
        process.terminate()
        process.join(5)
        raise RuntimeError(f"Flash timed out after {timeout} seconds")

    if not result_path.exists():
        raise RuntimeError(
            f"Flash worker exited without a result (exit code {process.exitcode})"
        )

    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid flash worker result: {exc}") from exc

    log = str(payload.get("log", ""))
    if not payload.get("ok"):
        error = str(payload.get("error", "esptool failed"))
        raise RuntimeError("\n".join(part for part in (error, log) if part))
    return log


def flash_firmware(
    artifact_url: str,
    com_port: str,
    baud: int,
    chip: str,
) -> dict[str, object]:
    if not com_port.upper().startswith("COM"):
        raise ValueError("Invalid COM port")
    if baud <= 0:
        raise ValueError("Baud rate must be positive")

    work_dir: Path | None = None
    try:
        work_dir, zip_path = download_artifact_zip(artifact_url)
        firmware_path = extract_artifact(zip_path, work_dir)
        result_path = work_dir / "esptool-result.json"
        command = build_esptool_args(firmware_path, com_port, baud, chip)
        log = run_esptool_process(command, result_path)
        return {
            "status": "success",
            "message": "Flash success",
            "com_port": com_port,
            "baud": baud,
            "log": log,
        }
    finally:
        if work_dir is not None:
            shutil.rmtree(work_dir, ignore_errors=True)
