from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from models.data_models import FaultType


_TIMEOUT_PATTERN = re.compile(
    r"TARGET:\s*(?P<target>[^,]+),\s*"
    r"TIMED OUT on:\s*(?P<timestamp>[^,]+),\s*"
    r"Error occured:\s*(?P<error>[^,]+),\s*"
    r"Time stressed:\s*(?P<stress>[^,]+),\s*"
    r"DUT NAME:\s*(?P<dut>.+)$",
    re.IGNORECASE,
)
_CURRENT_PATTERN = re.compile(
    r"psuV:\s*(?P<psu_v>[-+\d.eE]+),\s*"
    r"elV:\s*(?P<el_v>[-+\d.eE]+),\s*"
    r"psuI:\s*(?P<psu_i>[-+\d.eE]+),\s*"
    r"elI:\s*(?P<el_i>[-+\d.eE]+),.*?"
    r"\bI:\s*(?P<total_i>[-+\d.eE]+)",
    re.IGNORECASE,
)


@dataclass
class HostTimeout:
    hw_target: str
    timestamp: datetime
    fault_type: FaultType
    stressed_seconds: float
    dut_name: str
    source_path: Path


def _parse_duration(value: str) -> float:
    try:
        parts = [float(part) for part in value.strip().split(":")]
    except ValueError:
        return 0.0
    if len(parts) != 3:
        return 0.0
    return max(0.0, parts[0] * 3600 + parts[1] * 60 + parts[2])


def _fault_type(value: str) -> FaultType:
    normalized = value.strip().upper()
    if normalized == "OC":
        return FaultType.OC
    if normalized == "OV":
        return FaultType.OV
    if normalized in {"OT", "TEMP", "TEMPERR"}:
        return FaultType.OT
    if normalized == "GERR":
        return FaultType.GERR
    if "NETWORK" in normalized:
        return FaultType.NETWORK
    return FaultType.NONE


def parse_host_log(path: str | Path) -> list[HostTimeout]:
    source = Path(path)
    timeouts: list[HostTimeout] = []
    try:
        handle = source.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return timeouts

    with handle:
        for raw_line in handle:
            payload = raw_line.rstrip("\r\n").split("\t", 1)[-1]
            match = _TIMEOUT_PATTERN.search(payload)
            if not match:
                continue
            try:
                timestamp = datetime.fromisoformat(match.group("timestamp").strip())
            except ValueError:
                continue
            timeouts.append(
                HostTimeout(
                    hw_target=match.group("target").strip(),
                    timestamp=timestamp,
                    fault_type=_fault_type(match.group("error")),
                    stressed_seconds=_parse_duration(match.group("stress")),
                    dut_name=match.group("dut").strip(),
                    source_path=source,
                )
            )
    return timeouts


def parse_host_logs(paths: Iterable[str | Path]) -> list[HostTimeout]:
    records: list[HostTimeout] = []
    for path in sorted((Path(item) for item in paths), key=lambda item: item.name):
        records.extend(parse_host_log(path))
    return sorted(records, key=lambda item: item.timestamp)


def parse_host_current_series(paths: Iterable[str | Path]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for source in sorted((Path(item) for item in paths), key=lambda item: item.name):
        try:
            handle = source.open("r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with handle:
            for raw_line in handle:
                try:
                    timestamp_text, payload = raw_line.rstrip("\r\n").split("\t", 1)
                    timestamp = datetime.fromisoformat(timestamp_text)
                except ValueError:
                    continue
                match = _CURRENT_PATTERN.search(payload)
                if not match:
                    continue
                try:
                    row = {key: float(value) for key, value in match.groupdict().items()}
                except ValueError:
                    continue
                row["timestamp"] = timestamp
                rows.append(row)
    return pd.DataFrame(rows)
