from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

import requests


def parse_remote_response(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def upload_project_zip(
    remote_build_url: str,
    zip_path: str,
    project_name: str,
    idf_image: str,
    target: str,
) -> dict[str, Any]:
    with open(zip_path, "rb") as file_handle:
        files = {"file": (zip_path, file_handle, "application/zip")}
        data = {
            "project_name": project_name,
            "idf_image": idf_image,
            "target": target,
        }
        response = requests.post(
            remote_build_url,
            files=files,
            data=data,
            timeout=(10, 60),
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Remote build server returned error: {response.status_code} {response.text}"
        )

    return {
        "status": "uploaded",
        "local_zip": zip_path,
        "remote_response": parse_remote_response(response),
    }


def derive_lvgl_build_url(remote_build_url: str) -> str:
    if remote_build_url.endswith("/api/build/upload"):
        return remote_build_url[: -len("/api/build/upload")] + "/api/lvgl/build/upload"
    parsed = urlparse(remote_build_url)
    if parsed.scheme and parsed.netloc:
        return urlunparse((parsed.scheme, parsed.netloc, "/api/lvgl/build/upload", "", "", ""))
    return "/api/lvgl/build/upload"


def upload_lvgl_project_zip(
    remote_build_url: str,
    zip_path: str,
    project_name: str,
    width: int,
    height: int,
) -> dict[str, Any]:
    lvgl_build_url = derive_lvgl_build_url(remote_build_url)

    with open(zip_path, "rb") as file_handle:
        files = {"file": (zip_path, file_handle, "application/zip")}
        data = {
            "project_name": project_name,
            "width": str(width),
            "height": str(height),
        }
        response = requests.post(
            lvgl_build_url,
            files=files,
            data=data,
            timeout=(10, 60),
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Remote LVGL build server returned error: {response.status_code} {response.text}"
        )

    return {
        "status": "uploaded",
        "local_zip": zip_path,
        "remote_url": lvgl_build_url,
        "remote_response": parse_remote_response(response),
    }
