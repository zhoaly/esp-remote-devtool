from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class FileDownload:
    path: Path
    media_type: str
    filename: str | None = None
    cache_control: str | None = None
