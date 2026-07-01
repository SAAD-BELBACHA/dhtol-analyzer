from __future__ import annotations

import math
import mmap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

import pandas as pd

from models.data_models import FaultType


MEASUREMENT_COLUMNS = [
    "timestamp",
    "v_in",
    "current",
    "vg_diff",
    "vout_dut",
    "vout_brd",
    "v_ls",
    "t0",
    "t1",
]


@dataclass
class BoardEvent:
    timestamp: datetime
    text: str
    fault_type: FaultType = FaultType.NONE
    source_path: Path | None = None


@dataclass
class BoardLogResult:
    measurements: pd.DataFrame = field(
        default_factory=lambda: pd.DataFrame(columns=MEASUREMENT_COLUMNS)
    )
    events: list[BoardEvent] = field(default_factory=list)
    skipped_lines: int = 0


def _fault_type(text: str) -> FaultType:
    normalized = text.upper()
    if "OC ERR" in normalized:
        return FaultType.OC
    if "OV ERR" in normalized:
        return FaultType.OV
    if "OT ERR" in normalized or "TEMP ERR" in normalized:
        return FaultType.OT
    if "GERR" in normalized:
        return FaultType.GERR
    return FaultType.NONE


def _is_relevant_event(text: str) -> bool:
    normalized = text.upper()
    return any(
        marker in normalized
        for marker in ("OC ERR", "OV ERR", "OT ERR", "TEMP ERR", "GERR", "PIC STOPPED")
    )


def _split_line(raw_line: str) -> tuple[str, str] | None:
    """Split a raw log line into (timestamp_text, payload) or None if malformed."""
    parts = raw_line.rstrip("\r\n").split("\t", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else None


def _is_measurement(payload: str) -> bool:
    """A measurement payload has 8 ``;``-separated numeric fields."""
    return payload.count(";") == 7


def parse_board_log(path: str | Path) -> BoardLogResult:
    source = Path(path)
    rows: list[tuple[object, ...]] = []
    events: list[BoardEvent] = []
    skipped = 0

    try:
        handle = source.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return BoardLogResult(skipped_lines=1)

    with handle:
        for raw_line in handle:
            split = _split_line(raw_line)
            if split is None:
                skipped += 1
                continue
            timestamp_text, payload = split
            try:
                timestamp = datetime.fromisoformat(timestamp_text)
            except (ValueError, TypeError):
                skipped += 1
                continue

            if _is_measurement(payload):
                try:
                    numeric = tuple(float(value) for value in payload.split(";"))
                except ValueError:
                    skipped += 1
                    continue
                rows.append((timestamp, *numeric))
                continue

            if _is_relevant_event(payload):
                events.append(
                    BoardEvent(
                        timestamp=timestamp,
                        text=payload.strip(),
                        fault_type=_fault_type(payload),
                        source_path=source,
                    )
                )

    frame = pd.DataFrame.from_records(rows, columns=MEASUREMENT_COLUMNS)
    return BoardLogResult(measurements=frame, events=events, skipped_lines=skipped)


def parse_board_events(paths: Iterable[str | Path]) -> list[BoardEvent]:
    """Scan board logs for fault/stop events only, skipping measurement rows.

    Cheaper than :func:`parse_board_logs` because it never builds a DataFrame
    and never parses the numeric measurement lines.
    """
    events: list[BoardEvent] = []
    for source in sorted((Path(item) for item in paths), key=lambda item: item.name):
        try:
            handle = source.open("r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with handle:
            for raw_line in handle:
                split = _split_line(raw_line)
                if split is None:
                    continue
                timestamp_text, payload = split
                if _is_measurement(payload) or not _is_relevant_event(payload):
                    continue
                try:
                    timestamp = datetime.fromisoformat(timestamp_text)
                except (ValueError, TypeError):
                    continue
                events.append(
                    BoardEvent(
                        timestamp=timestamp,
                        text=payload.strip(),
                        fault_type=_fault_type(payload),
                        source_path=source,
                    )
                )
    return events


def parse_board_logs(paths: Iterable[str | Path]) -> BoardLogResult:
    frames: list[pd.DataFrame] = []
    events: list[BoardEvent] = []
    skipped = 0

    for path in sorted((Path(item) for item in paths), key=lambda item: item.name):
        result = parse_board_log(path)
        if not result.measurements.empty:
            frames.append(result.measurements)
        events.extend(result.events)
        skipped += result.skipped_lines

    frame = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=MEASUREMENT_COLUMNS)
    )
    if not frame.empty:
        frame = frame.sort_values("timestamp").drop_duplicates("timestamp")
        frame = frame.reset_index(drop=True)
    return BoardLogResult(measurements=frame, events=events, skipped_lines=skipped)


def measurement_time_bounds(
    path: str | Path,
) -> tuple[datetime, datetime] | None:
    source = Path(path)
    try:
        handle = source.open("rb")
    except OSError:
        return None

    with handle:
        try:
            if source.stat().st_size == 0:
                return None
            content = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        except (OSError, ValueError):
            return None

        with content:
            first: datetime | None = None
            position = 0
            while position < len(content):
                line_end = content.find(b"\n", position)
                if line_end < 0:
                    line_end = len(content)
                raw_line = content[position:line_end].decode(
                    "utf-8", errors="replace"
                )
                split = _split_line(raw_line)
                if split is not None and _is_measurement(split[1]):
                    try:
                        first = datetime.fromisoformat(split[0])
                    except ValueError:
                        first = None
                    if first is not None:
                        break
                position = line_end + 1

            if first is None:
                return None

            last: datetime | None = None
            position = len(content)
            while position > 0:
                line_start = content.rfind(
                    b"\n", 0, max(0, position - 1)
                )
                raw_line = content[line_start + 1 : position].decode(
                    "utf-8", errors="replace"
                )
                split = _split_line(raw_line)
                if split is not None and _is_measurement(split[1]):
                    try:
                        last = datetime.fromisoformat(split[0])
                    except ValueError:
                        last = None
                    if last is not None:
                        break
                position = line_start if line_start >= 0 else 0

    if last is None or last < first:
        return None
    return first, last


def available_log_seconds(paths: Iterable[str | Path]) -> float:
    total_seconds = 0.0
    for path in paths:
        bounds = measurement_time_bounds(path)
        if bounds is None:
            continue
        first, last = bounds
        total_seconds += max(0.0, (last - first).total_seconds())
    return total_seconds


def parse_board_logs_for_plot(
    paths: Iterable[str | Path],
    max_points: int = 5000,
) -> BoardLogResult:
    sources = sorted((Path(item) for item in paths), key=lambda item: item.name)
    if not sources:
        return BoardLogResult()

    rows: list[tuple[object, ...]] = []
    events: list[BoardEvent] = []
    skipped = 0
    total_bytes = sum(
        source.stat().st_size for source in sources if source.exists()
    )
    sample_step = max(1, total_bytes // max(1, max_points * 75))
    measurement_index = 0
    last_measurement_raw: tuple[str, str] | None = None

    for source in sources:
        try:
            handle = source.open("r", encoding="utf-8", errors="replace")
        except OSError:
            skipped += 1
            continue

        with handle:
            for raw_line in handle:
                split = _split_line(raw_line)
                if split is None:
                    skipped += 1
                    continue
                timestamp_text, payload = split

                if _is_measurement(payload):
                    last_measurement_raw = (timestamp_text, payload)
                    keep = measurement_index % sample_step == 0
                    measurement_index += 1
                    if not keep:
                        continue
                    try:
                        timestamp = datetime.fromisoformat(timestamp_text)
                        numeric = tuple(
                            float(value) for value in payload.split(";")
                        )
                    except (ValueError, TypeError):
                        skipped += 1
                        continue
                    rows.append((timestamp, *numeric))
                    continue

                if not _is_relevant_event(payload):
                    continue
                try:
                    timestamp = datetime.fromisoformat(timestamp_text)
                except ValueError:
                    skipped += 1
                    continue
                events.append(
                    BoardEvent(
                        timestamp=timestamp,
                        text=payload.strip(),
                        fault_type=_fault_type(payload),
                        source_path=source,
                    )
                )

    if last_measurement_raw is not None:
        timestamp_text, payload = last_measurement_raw
        try:
            last_measurement = (
                datetime.fromisoformat(timestamp_text),
                *(float(value) for value in payload.split(";")),
            )
            if not rows or rows[-1][0] != last_measurement[0]:
                rows.append(last_measurement)
        except (ValueError, TypeError):
            skipped += 1
    combined = pd.DataFrame.from_records(rows, columns=MEASUREMENT_COLUMNS)
    if not combined.empty:
        combined = combined.sort_values("timestamp").drop_duplicates("timestamp")
        if len(combined) > max_points:
            step = max(1, math.ceil(len(combined) / max_points))
            combined = combined.iloc[::step]
        combined = combined.reset_index(drop=True)
    return BoardLogResult(
        measurements=combined,
        events=events,
        skipped_lines=skipped,
    )


def parse_temperature_logs(paths: Iterable[str | Path]) -> pd.DataFrame:
    rows: list[tuple[datetime, float, float]] = []
    for source in sorted(
        (Path(item) for item in paths), key=lambda item: item.name
    ):
        try:
            handle = source.open("r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with handle:
            for raw_line in handle:
                split = _split_line(raw_line)
                if split is None or not _is_measurement(split[1]):
                    continue
                timestamp_text, payload = split
                values = payload.split(";")
                try:
                    rows.append(
                        (
                            datetime.fromisoformat(timestamp_text),
                            float(values[6]),
                            float(values[7]),
                        )
                    )
                except (ValueError, TypeError):
                    continue

    frame = pd.DataFrame.from_records(
        rows, columns=["timestamp", "t0", "t1"]
    )
    if not frame.empty:
        frame = frame.sort_values("timestamp").drop_duplicates("timestamp")
        frame = frame.reset_index(drop=True)
    return frame
