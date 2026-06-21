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
    try:
        cycles = int(test_info.get("Cycles") or 0)
    except (TypeError, ValueError):
        cycles = 0

    return BoardMetadata(
        log_stress_seconds=max(0.0, seconds),
        cycles=max(0, cycles),
        hostname=str(hardware.get("hostname") or ""),
        ip_address=str(hardware.get("IP") or ""),
        mac_address=str(hardware.get("MAC") or ""),
        hardware_version=str(version.get("hw") or ""),
        firmware_version=str(version.get("fw") or ""),
        source_path=source,
    )
