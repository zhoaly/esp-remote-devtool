from __future__ import annotations

import getpass
import os
import plistlib
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from app.builders.docker import docker_executable
from app.core.config import SERVER_DIR, Settings


def _systemd_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


def write_config(target: str, output: Path, env_file: Path, settings: Settings) -> None:
    args = [
        sys.executable,
        str(SERVER_DIR / "manage.py"),
        "--env-file",
        str(env_file),
        "--base-dir",
        str(settings.base_dir),
        "--data-dir",
        str(settings.data_dir),
        "--docker-executable",
        docker_executable(),
        "start",
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    settings.ensure_directories()
    if target == "launchd":
        output.write_bytes(
            plistlib.dumps(
                {
                    "Label": "net.zlyhub.esp-remote",
                    "ProgramArguments": args,
                    "WorkingDirectory": str(SERVER_DIR),
                    "RunAtLoad": True,
                    "KeepAlive": True,
                    "ExitTimeOut": 45,
                    "StandardOutPath": str(settings.log_dir / "service.log"),
                    "StandardErrorPath": str(settings.log_dir / "service-error.log"),
                }
            )
        )
    elif target == "systemd":
        output.write_text(
            "[Unit]\nDescription=ESP Remote API and Worker\nAfter=network-online.target docker.service\n"
            "Wants=network-online.target\n\n[Service]\nType=simple\n"
            f"WorkingDirectory={_systemd_quote(str(SERVER_DIR))}\n"
            f"ExecStart={' '.join(map(_systemd_quote, args))}\n"
            f"ExecStop={' '.join(map(_systemd_quote, [*args[:-1], 'stop']))}\n"
            "Restart=on-failure\nRestartSec=5\nTimeoutStopSec=50\n"
            "KillMode=mixed\n\n[Install]\nWantedBy=default.target\n",
            encoding="utf-8",
        )
    else:
        pythonw = Path(args[0]).with_name("pythonw.exe")
        if pythonw.is_file():
            args[0] = str(pythonw)
        args += ["--log-file", str(settings.log_dir / "service.log")]
        ns = "http://schemas.microsoft.com/windows/2004/02/mit/task"
        ET.register_namespace("", ns)
        task = ET.Element(f"{{{ns}}}Task", version="1.2")

        def child(parent, tag, text=None, **attrs):
            item = ET.SubElement(parent, f"{{{ns}}}{tag}", attrs)
            item.text = text
            return item

        triggers = child(task, "Triggers")
        child(child(triggers, "LogonTrigger"), "Enabled", "true")
        principals = child(task, "Principals")
        principal = child(principals, "Principal", id="Author")
        username = getpass.getuser()
        if os.getenv("USERDOMAIN"):
            username = f"{os.environ['USERDOMAIN']}\\{username}"
        child(principal, "UserId", username)
        child(principal, "LogonType", "InteractiveToken")
        child(principal, "RunLevel", "LeastPrivilege")
        config = child(task, "Settings")
        child(config, "MultipleInstancesPolicy", "IgnoreNew")
        child(config, "DisallowStartIfOnBatteries", "false")
        child(config, "StopIfGoingOnBatteries", "false")
        child(config, "ExecutionTimeLimit", "PT0S")
        restart = child(config, "RestartOnFailure")
        child(restart, "Interval", "PT1M")
        child(restart, "Count", "999")
        actions = child(task, "Actions", Context="Author")
        action = child(actions, "Exec")
        child(action, "Command", args[0])
        child(action, "Arguments", subprocess.list2cmdline(args[1:]))
        child(action, "WorkingDirectory", str(SERVER_DIR))
        output.write_bytes(ET.tostring(task, encoding="utf-16", xml_declaration=True))
