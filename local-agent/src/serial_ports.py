from __future__ import annotations

from serial.tools import list_ports


def list_serial_ports(default_port: str = "COM7") -> dict[str, object]:
    ports: list[dict[str, str]] = []

    for port in list_ports.comports():
        ports.append(
            {
                "device": port.device,
                "description": port.description,
                "hwid": port.hwid,
            }
        )

    if ports and not any(item["device"] == default_port for item in ports):
        default_port = ports[0]["device"]

    return {"ports": ports, "default_port": default_port}
