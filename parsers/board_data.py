from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from models.data_models import BoardMetadata


def parse_board_data(path: str | Path) -> Optional[BoardMetadata]:
    source = Path(path)
    try:
        with source.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None

    test_info = data.get("Test Info") or {}
    history = data.get("HW History") or []
    latest = history[-1] if isinstance(history, list) and history else {}
    hardware = latest.get("HW Info") or {}
    version = hardware.get("version") or {}

    try:
        seconds = float(test_info.get("Seconds") or 0.0)
    except (TypeError, ValueError):
        seconds = 0.0

    return BoardMetadata(
        log_stress_seconds=max(0.0, seconds),
        firmware_version=str(version.get("fw") or ""),
        source_path=source,
    )
