from __future__ import annotations

import ctypes
import logging
import multiprocessing
import os
import sys
import tempfile
import threading
import webbrowser
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import StringVar, Tk, Toplevel, messagebox, ttk

os.environ.setdefault("PYSTRAY_BACKEND", "win32")

import pystray
import requests
from agent_app import create_app
from agent_runtime import AgentServerController, ServerSnapshot, ServerStatus
from config import (
    derive_remote_info_url,
    derive_remote_ui_url,
    get_log_dir,
    has_saved_configuration,
    load_settings,
    save_user_settings,
    settings_to_user_dict,
    validate_remote_build_url,
)
from flasher import run_esptool_process
from PIL import Image

APP_NAME = "ESP Remote Build Agent"
MUTEX_NAME = r"Local\ESPRemoteBuildAgent"
CONTROL_WINDOW_TITLE = "ESPRemoteBuildAgentControlWindow"
LOGGER = logging.getLogger(__name__)


def resource_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / relative_path


def setup_logging() -> Path:
    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "agent.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not any(
        isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename) == log_path
        for handler in root_logger.handlers
    ):
        handler = RotatingFileHandler(
            log_path,
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s"
            )
        )
        root_logger.addHandler(handler)
    return log_path


class SingleInstance:
    def __init__(self, name: str) -> None:
        self._handle: int | None = None
        self._name = name

    def acquire(self) -> bool:
        if sys.platform != "win32":
            return True

        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_bool,
            ctypes.c_wchar_p,
        ]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_bool
        kernel32.SetLastError(0)
        handle = kernel32.CreateMutexW(None, False, self._name)
        if not handle:
            return False
        self._handle = handle
        return kernel32.GetLastError() != 183

    def release(self) -> None:
        if self._handle and sys.platform == "win32":
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None


def show_native_message(message: str, title: str = APP_NAME) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x40)


class SettingsWindow:
    def __init__(
        self,
        root: Tk,
        on_saved: Callable[[], None],
    ) -> None:
        self._root = root
        self._on_saved = on_saved
        self._window: Toplevel | None = None
        self._variables: dict[str, StringVar] = {}
        self._status_var = StringVar(root, "")

    def show(self) -> None:
        if self._window and self._window.winfo_exists():
            self._window.deiconify()
            self._window.lift()
            self._window.focus_force()
            return

        settings = load_settings()
        values = settings_to_user_dict(settings)
        self._window = Toplevel(self._root)
        self._window.title(f"{APP_NAME} 设置")
        self._window.resizable(False, False)
        self._window.protocol("WM_DELETE_WINDOW", self._window.destroy)

        icon_path = resource_path("assets/agent.ico")
        if icon_path.exists():
            try:
                self._window.iconbitmap(default=str(icon_path))
            except Exception:
                LOGGER.debug("Unable to set settings window icon", exc_info=True)

        frame = ttk.Frame(self._window, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")

        fields = (
            ("remote_build_url", "远程构建上传 URL"),
            ("default_project_name", "默认项目名"),
            ("default_idf_image", "默认 IDF 镜像"),
            ("default_target", "默认目标芯片"),
        )
        for row, (key, label) in enumerate(fields):
            ttk.Label(frame, text=label).grid(
                row=row,
                column=0,
                sticky="w",
                padx=(0, 12),
                pady=6,
            )
            variable = StringVar(self._window, values[key])
            self._variables[key] = variable
            width = 52 if key == "remote_build_url" else 36
            ttk.Entry(frame, textvariable=variable, width=width).grid(
                row=row,
                column=1,
                sticky="ew",
                pady=6,
            )

        endpoint_row = len(fields)
        ttk.Label(frame, text="本地 Agent 地址").grid(
            row=endpoint_row,
            column=0,
            sticky="w",
            padx=(0, 12),
            pady=6,
        )
        ttk.Label(frame, text="http://127.0.0.1:8765").grid(
            row=endpoint_row,
            column=1,
            sticky="w",
            pady=6,
        )

        ttk.Label(
            frame,
            textvariable=self._status_var,
            foreground="#4a5568",
        ).grid(
            row=endpoint_row + 1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(8, 2),
        )

        buttons = ttk.Frame(frame)
        buttons.grid(
            row=endpoint_row + 2,
            column=0,
            columnspan=2,
            sticky="e",
            pady=(14, 0),
        )
        ttk.Button(
            buttons,
            text="测试连接",
            command=self._test_connection,
        ).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="取消", command=self._window.destroy).grid(
            row=0,
            column=1,
            padx=(0, 8),
        )
        ttk.Button(buttons, text="保存", command=self._save).grid(
            row=0,
            column=2,
        )

        self._window.update_idletasks()
        width = self._window.winfo_width()
        height = self._window.winfo_height()
        x = max(0, (self._window.winfo_screenwidth() - width) // 2)
        y = max(0, (self._window.winfo_screenheight() - height) // 3)
        self._window.geometry(f"+{x}+{y}")
        self._window.lift()
        self._window.focus_force()

    def _form_values(self) -> dict[str, str]:
        return {key: variable.get() for key, variable in self._variables.items()}

    def set_status(self, value: str) -> None:
        self._status_var.set(value)

    def _save(self) -> None:
        try:
            path = save_user_settings(self._form_values())
        except ValueError as exc:
            messagebox.showerror("设置无效", str(exc), parent=self._window)
            return
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc), parent=self._window)
            return

        LOGGER.info("Agent settings saved to %s", path)
        self._status_var.set("设置已保存，正在重启本地 Agent…")
        self._on_saved()

    def _test_connection(self) -> None:
        try:
            url = derive_remote_info_url(
                validate_remote_build_url(self._variables["remote_build_url"].get())
            )
        except ValueError as exc:
            messagebox.showerror("地址无效", str(exc), parent=self._window)
            return

        self._status_var.set(f"正在测试 {url} …")

        def request_worker() -> None:
            try:
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                payload = response.json()
                name = (
                    payload.get("name", "Remote build server")
                    if isinstance(payload, dict)
                    else "Remote build server"
                )
                result = f"连接成功：{name}"
            except (requests.RequestException, ValueError) as exc:
                result = f"连接失败：{exc}"
            self._root.after(0, lambda: self._status_var.set(result))

        threading.Thread(
            target=request_worker,
            name="ESPAgentConnectionTest",
            daemon=True,
        ).start()


class TrayApplication:
    def __init__(self, root: Tk) -> None:
        self._root = root
        self._controller = AgentServerController()
        self._settings_window = SettingsWindow(root, self._save_and_restart)
        self._last_status: ServerStatus | None = None
        self._exit_started = False
        self._images = self._load_tray_images()
        self._icon = pystray.Icon(
            "ESPRemoteBuildAgent",
            self._images[ServerStatus.STARTING],
            APP_NAME,
            menu=pystray.Menu(
                pystray.MenuItem(
                    self._status_text,
                    lambda _icon, _item: None,
                    enabled=False,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "打开 ESP 工具页面",
                    self._open_remote_ui,
                    default=True,
                ),
                pystray.MenuItem("设置", self._show_settings),
                pystray.MenuItem("打开日志目录", self._open_logs),
                pystray.MenuItem("重试 / 重启 Agent", self._restart),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", self._exit),
            ),
        )

    def _load_tray_images(self) -> dict[ServerStatus, Image.Image]:
        paths = {
            ServerStatus.STARTING: "assets/tray-starting.png",
            ServerStatus.RUNNING: "assets/tray-running.png",
            ServerStatus.ERROR: "assets/tray-error.png",
            ServerStatus.STOPPED: "assets/tray-stopped.png",
            ServerStatus.STOPPING: "assets/tray-starting.png",
        }
        return {
            status: Image.open(resource_path(path)).convert("RGBA")
            for status, path in paths.items()
        }

    def run(self, show_settings_on_start: bool) -> None:
        self._icon.run_detached()
        self._controller.start()
        self._root.after(250, self._poll_status)
        if show_settings_on_start:
            self._root.after(500, self._settings_window.show)
        self._root.mainloop()

    def _status_text(self, _item: pystray.MenuItem) -> str:
        snapshot = self._controller.snapshot()
        labels = {
            ServerStatus.STARTING: "状态：正在启动",
            ServerStatus.RUNNING: "状态：运行中 (127.0.0.1:8765)",
            ServerStatus.STOPPING: "状态：正在停止",
            ServerStatus.STOPPED: "状态：已停止",
            ServerStatus.ERROR: "状态：启动失败",
        }
        return labels[snapshot.status]

    def _poll_status(self) -> None:
        if self._exit_started:
            return

        snapshot = self._controller.snapshot()
        if snapshot.status != self._last_status:
            self._apply_status(snapshot)
        self._root.after(500, self._poll_status)

    def _apply_status(self, snapshot: ServerSnapshot) -> None:
        self._last_status = snapshot.status
        self._icon.icon = self._images[snapshot.status]
        self._icon.title = self._status_text(None)  # type: ignore[arg-type]
        self._icon.update_menu()

        if snapshot.status == ServerStatus.ERROR:
            message = snapshot.error or "本地 Agent 启动失败"
            LOGGER.error(message)
            try:
                self._icon.notify(message, APP_NAME)
            except Exception:
                LOGGER.debug("Unable to show tray notification", exc_info=True)

    def _open_remote_ui(
        self,
        _icon: pystray.Icon | None = None,
        _item: pystray.MenuItem | None = None,
    ) -> None:
        try:
            webbrowser.open(derive_remote_ui_url(load_settings().remote_build_url))
        except ValueError as exc:
            message = str(exc)
            self._root.after(
                0,
                lambda: messagebox.showerror("地址无效", message),
            )

    def _show_settings(
        self,
        _icon: pystray.Icon | None = None,
        _item: pystray.MenuItem | None = None,
    ) -> None:
        self._root.after(0, self._settings_window.show)

    def _open_logs(
        self,
        _icon: pystray.Icon | None = None,
        _item: pystray.MenuItem | None = None,
    ) -> None:
        log_dir = get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(log_dir)

    def _restart(
        self,
        _icon: pystray.Icon | None = None,
        _item: pystray.MenuItem | None = None,
    ) -> None:
        self._root.after(0, self._restart_server)

    def _restart_server(self) -> None:
        try:
            self._controller.restart()
        except Exception as exc:
            LOGGER.exception("Unable to restart local agent")
            messagebox.showerror("重启失败", str(exc))

    def _save_and_restart(self) -> None:
        self._restart_server()
        snapshot = self._controller.wait_until_ready(5)
        if snapshot.status == ServerStatus.RUNNING:
            self._settings_window.set_status("设置已保存，Agent 已重新启动。")
        elif snapshot.status == ServerStatus.ERROR:
            self._settings_window.set_status(
                f"设置已保存，但 Agent 启动失败：{snapshot.error}"
            )
        else:
            self._settings_window.set_status(
                "设置已保存，Agent 仍在启动，请查看托盘状态。"
            )

    def _exit(
        self,
        _icon: pystray.Icon | None = None,
        _item: pystray.MenuItem | None = None,
    ) -> None:
        self._root.after(0, self.shutdown)

    def shutdown(self) -> None:
        if self._exit_started:
            return
        self._exit_started = True
        LOGGER.info("Stopping ESP Remote Build Agent")
        self._controller.stop()
        self._icon.stop()
        self._root.quit()
        self._root.destroy()


def main() -> int:
    multiprocessing.freeze_support()
    setup_logging()
    instance = SingleInstance(MUTEX_NAME)
    if not instance.acquire():
        show_native_message("ESP Remote Build Agent 已经在运行。")
        return 0

    root: Tk | None = None
    application: TrayApplication | None = None
    try:
        LOGGER.info("Starting %s", APP_NAME)
        first_run = not has_saved_configuration()
        root = Tk()
        root.withdraw()
        root.title(CONTROL_WINDOW_TITLE)
        root.protocol("WM_DELETE_WINDOW", lambda: application and application.shutdown())

        icon_path = resource_path("assets/agent.ico")
        if icon_path.exists():
            try:
                root.iconbitmap(default=str(icon_path))
            except Exception:
                LOGGER.debug("Unable to set root window icon", exc_info=True)

        application = TrayApplication(root)
        application.run(show_settings_on_start=first_run)
        return 0
    except BaseException as exc:
        LOGGER.exception("Fatal tray application error")
        show_native_message(f"ESP Remote Build Agent 启动失败：\n{exc}")
        return 1
    finally:
        if application:
            application.shutdown()
        elif root:
            root.destroy()
        instance.release()


def run_self_test() -> int:
    try:
        settings = load_settings()
        app = create_app(settings)
        if app.title != "ESP Local Upload Agent":
            raise RuntimeError("FastAPI application was not created")
        for asset in (
            "assets/agent.ico",
            "assets/tray-running.png",
            "assets/tray-starting.png",
            "assets/tray-error.png",
            "assets/tray-stopped.png",
        ):
            if not resource_path(asset).exists():
                raise RuntimeError(f"Packaged resource is missing: {asset}")
        import esptool
        import serial

        if not esptool or not serial:
            raise RuntimeError("Required flash dependencies are unavailable")
        with tempfile.TemporaryDirectory(prefix="esp_agent_selftest_") as temp_dir:
            result_path = Path(temp_dir) / "esptool-result.json"
            log = run_esptool_process(["version"], result_path, timeout=20)
            if "esptool" not in log.lower():
                raise RuntimeError("Frozen esptool worker returned unexpected output")
        return 0
    except BaseException:
        LOGGER.exception("Packaged self-test failed")
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if "--self-test" in sys.argv:
        setup_logging()
        raise SystemExit(run_self_test())
    raise SystemExit(main())
