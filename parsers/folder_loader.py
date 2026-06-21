from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from analysis.fault_detector import faults_from_board_events, merge_board_faults
from config import BOARDS_PER_ZONE
from models.data_models import Board, Fault, TestRun, Zone, ZoneData
from parsers.board_log import BoardLogResult, parse_board_events, parse_board_logs
from parsers.board_data import parse_board_data
from parsers.config_json import parse_config_json
from parsers.host_log import parse_host_current_series, parse_host_logs
from parsers.mtpx import parse_planned_test_seconds
from parsers.tdms_reader import combine_instrument_currents, read_instrument_currents


_CURRENT_PATTERN = re.compile(r"_(\d+)A(\d+)?(?:_|$)", re.IGNORECASE)
_OVEN_PATTERN = re.compile(r"_(-?\d+(?:\.\d+)?)degree(?:_|$)", re.IGNORECASE)
_DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")
_REVISION_SUFFIXES = {".json", ".mtpx", ".data", ".log", ".tdms"}


def _file_date(path: Path) -> Optional[str]:
    matches = _DATE_PATTERN.findall(path.name)
    return matches[-1] if matches else None


def folder_revision(folder_path: str | Path) -> str:
    root = Path(folder_path).expanduser().resolve()
    digest = hashlib.blake2b(digest_size=16)
    for path in sorted(
        (
            item
            for item in root.rglob("*")
            if item.is_file() and item.suffix.lower() in _REVISION_SUFFIXES
        ),
        key=lambda item: str(item.relative_to(root)),
    ):
        try:
            stat = path.stat()
        except OSError:
            continue
        relative = str(path.relative_to(root))
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
    return digest.hexdigest()


@dataclass(frozen=True)
class TestRunCandidate:
    run_id: str
    root_path: Path
    family_name: str
    config_paths: tuple[Path, ...]
    test_names: tuple[str, ...]
    zones: tuple[str, ...]
    board_count: int
    evidence_files: int
    relative_folder: str

    @property
    def display_name(self) -> str:
        temperature_match = _OVEN_PATTERN.search(self.family_name)
        temperature = (
            f"{temperature_match.group(1)} °C" if temperature_match else "Temperatur ?"
        )
        board_label = "Board" if self.board_count == 1 else "Boards"
        if self.relative_folder == ".":
            kind = "Haupttest" if self.evidence_files > 1 else "Konfiguration"
        elif self.relative_folder.lower() == "single":
            kind = "Single-Langzeittest"
        elif "tp_check" in self.relative_folder.lower():
            kind = "SAM13-Systemcheck"
        else:
            kind = self.relative_folder
        return f"{kind} · {temperature} · {self.board_count} {board_label}"


def _nominal_current(test_name: str) -> float:
    match = _CURRENT_PATTERN.search(test_name)
    if not match:
        return 0.0
    whole, decimals = match.groups()
    return float(f"{whole}.{decimals}") if decimals else float(whole)


def _oven_temperature(test_name: str) -> float:
    match = _OVEN_PATTERN.search(test_name)
    return float(match.group(1)) if match else 0.0


def _matching_data_file(
    root: Path, test_name: str, dut_name: str
) -> Optional[Path]:
    candidates = [
        root / f"{test_name}.{dut_name}.data",
        root / f"{test_name}_{dut_name}.data",
    ]
    candidates = [path for path in candidates if path.exists()]
    return candidates[0] if candidates else None


def _matching_board_logs(
    root: Path, test_name: str, dut_name: str
) -> list[Path]:
    candidates = set(root.glob(f"{test_name}.{dut_name}.*.log"))
    candidates.update(root.glob(f"{test_name}_{dut_name}_*.log"))
    return sorted(candidates, key=lambda path: path.name)


def _matching_files(root: Path, test_name: str, marker: str, suffix: str) -> list[Path]:
    return sorted(root.glob(f"{test_name}{marker}*{suffix}"), key=lambda path: path.name)


def _matching_host_logs(root: Path, test_name: str) -> list[Path]:
    pattern = re.compile(
        rf"^{re.escape(test_name)}\.\d{{4}}-\d{{2}}-\d{{2}}\.log$"
    )
    return sorted(
        (path for path in root.glob(f"{test_name}.*.log") if pattern.match(path.name)),
        key=lambda path: path.name,
    )


def _family_name(test_name: str, zone: Optional[Zone]) -> str:
    if zone is None:
        return test_name
    return test_name.replace(f"_{zone.value}_", "_{ZONE}_", 1)


def _evidence_count(root: Path, test_name: str) -> int:
    patterns = (
        f"{test_name}.*.data",
        f"{test_name}.*.log",
        f"{test_name}-*.tdms",
        f"{test_name}.store",
        f"{test_name}.mtpx",
    )
    return sum(len(list(root.glob(pattern))) for pattern in patterns)


def discover_test_runs(
    folder_path: str | Path, recursive: bool = True
) -> list[TestRunCandidate]:
    search_root = Path(folder_path).expanduser().resolve()
    config_paths = (
        search_root.rglob("*.json") if recursive else search_root.glob("*.json")
    )
    grouped: dict[tuple[Path, str], list[tuple[Path, object]]] = {}

    for path in sorted(config_paths):
        parsed = parse_config_json(path)
        if not parsed.ovenplan_entries:
            continue
        key = (path.parent.resolve(), _family_name(parsed.test_name, parsed.zone))
        grouped.setdefault(key, []).append((path, parsed))

    candidates: list[TestRunCandidate] = []
    for (run_root, family_name), items in grouped.items():
        relative = str(run_root.relative_to(search_root)) if run_root != search_root else "."
        test_names = tuple(sorted({parsed.test_name for _, parsed in items}))
        zones = tuple(
            sorted(
                {
                    entry.zone.value
                    for _, parsed in items
                    for entry in parsed.ovenplan_entries
                }
            )
        )
        board_keys = {
            (entry.zone.value, entry.position, entry.dut_name)
            for _, parsed in items
            for entry in parsed.ovenplan_entries
        }
        evidence = sum(_evidence_count(run_root, name) for name in test_names)
        run_id = f"{relative}::{family_name}"
        candidates.append(
            TestRunCandidate(
                run_id=run_id,
                root_path=run_root,
                family_name=family_name,
                config_paths=tuple(sorted(path for path, _ in items)),
                test_names=test_names,
                zones=zones,
                board_count=len(board_keys),
                evidence_files=evidence,
                relative_folder=relative,
            )
        )

    return sorted(
        candidates,
        key=lambda item: (
            item.relative_folder != ".",
            -item.evidence_files,
            item.relative_folder,
            item.family_name,
        ),
    )


def _host_current_series(
    zone_data: ZoneData, date: Optional[str], instrument: str
) -> Optional[pd.Series]:
    paths = [
        path
        for path in zone_data.host_log_paths
        if date is None or _file_date(path) == date
    ]
    frame = parse_host_current_series(paths)
    if frame.empty:
        return None
    column = {
        "psu": "psu_i",
        "el": "el_i",
        "combined": "total_i",
    }.get(instrument)
    if column is None or column not in frame:
        return None
    series = pd.Series(
        frame[column].to_numpy(dtype=float),
        index=pd.DatetimeIndex(frame["timestamp"]),
        name="current_a",
    ).sort_index()
    return series[~series.index.duplicated(keep="last")]


def available_board_dates(board: Board) -> list[str]:
    dates = {date for path in board.log_paths if (date := _file_date(path))}
    return sorted(dates)


def load_board_date(board: Board, date: Optional[str] = None) -> BoardLogResult:
    paths = (
        board.log_paths
        if date is None
        else [path for path in board.log_paths if _file_date(path) == date]
    )
    return parse_board_logs(paths)


def load_zone_current(
    zone_data: ZoneData, date: Optional[str] = None, instrument: str = "psu"
) -> Optional[pd.Series]:
    instrument = instrument.lower()
    psu = read_instrument_currents(
        path
        for path in zone_data.psu_paths
        if date is None or _file_date(path) == date
    )
    if instrument == "psu":
        return psu if psu is not None else _host_current_series(
            zone_data, date, "psu"
        )
    el = read_instrument_currents(
        path
        for path in zone_data.el_paths
        if date is None or _file_date(path) == date
    )
    if instrument == "el":
        return el if el is not None else _host_current_series(
            zone_data, date, "el"
        )
    combined = combine_instrument_currents(psu, el)
    return combined if combined is not None else _host_current_series(
        zone_data, date, "combined"
    )


def load_testrun(
    folder_path: str | Path, run_id: Optional[str] = None
) -> TestRun:
    search_root = Path(folder_path).expanduser().resolve()
    warnings: list[str] = []
    candidates = discover_test_runs(search_root)

    if not candidates:
        return TestRun(
            test_name=search_root.name,
            planned_test_seconds=0.0,
            oven_temp_setpoint_c=0.0,
            slot_nenn_strom_a=0.0,
            root_path=search_root,
            warnings=["Keine lesbare Testkonfiguration mit Ovenplan gefunden."],
        )

    if run_id is None:
        candidate = candidates[0]
        if len(candidates) > 1:
            warnings.append(
                f"{len(candidates)} Testläufe gefunden; automatisch gewählt: "
                f"{candidate.display_name}"
            )
    else:
        candidate = next(
            (item for item in candidates if item.run_id == run_id), None
        )
        if candidate is None:
            return TestRun(
                test_name=search_root.name,
                planned_test_seconds=0.0,
                oven_temp_setpoint_c=0.0,
                slot_nenn_strom_a=0.0,
                root_path=search_root,
                warnings=[f"Testlauf nicht gefunden: {run_id}"],
            )

    root = candidate.root_path
    configs = [parse_config_json(path) for path in candidate.config_paths]
    planned_values: list[float] = []
    zone_map: dict[Zone, ZoneData] = {}
    boards_by_dut: dict[str, Board] = {}
    test_names: list[str] = []

    for parsed in configs:
        test_names.append(parsed.test_name)
        warnings.extend(parsed.warnings)
        mtpx_path = root / f"{parsed.test_name}.mtpx"
        planned = parse_planned_test_seconds(mtpx_path)
        if planned is not None:
            planned_values.append(planned)
        else:
            warnings.append(f"Geplante Testzeit fehlt: {mtpx_path.name}")

        mqtt_paths = _matching_files(root, parsed.test_name, "-mqtt-", ".tdms")
        psu_paths = _matching_files(root, parsed.test_name, "-psu12-", ".tdms")
        el_paths = _matching_files(root, parsed.test_name, "-el12-", ".tdms")
        host_paths = _matching_host_logs(root, parsed.test_name)

        for entry in parsed.ovenplan_entries:
            zone_data = zone_map.setdefault(entry.zone, ZoneData(zone=entry.zone))
            zone_data.psu_paths = sorted(
                set(zone_data.psu_paths + psu_paths), key=lambda path: path.name
            )
            zone_data.el_paths = sorted(
                set(zone_data.el_paths + el_paths), key=lambda path: path.name
            )
            zone_data.host_log_paths = sorted(
                set(zone_data.host_log_paths + host_paths), key=lambda path: path.name
            )

            data_path = _matching_data_file(root, parsed.test_name, entry.dut_name)
            metadata = parse_board_data(data_path) if data_path else None
            board = Board(
                controller_id=entry.controller_id,
                zone=entry.zone,
                position=entry.position,
                dut_name=entry.dut_name,
                hw_target=entry.hw_target,
                nenn_strom_a=_nominal_current(parsed.test_name),
                temp_mode=parsed.temp_mode,
                log_stress_seconds=(
                    metadata.log_stress_seconds if metadata is not None else 0.0
                ),
                metadata=metadata,
                data_path=data_path,
                log_paths=_matching_board_logs(
                    root, parsed.test_name, entry.dut_name
                ),
                mqtt_paths=mqtt_paths,
            )
            zone_data.boards.append(board)
            boards_by_dut[board.dut_name] = board

    for zone_data in zone_map.values():
        zone_data.boards.sort(key=lambda board: board.position)
        if len(zone_data.boards) > BOARDS_PER_ZONE:
            warnings.append(
                f"Zone {zone_data.zone.value} enthält {len(zone_data.boards)} Boards."
            )
        for timeout in parse_host_logs(zone_data.host_log_paths):
            board = boards_by_dut.get(timeout.dut_name)
            if board is None:
                continue
            board.faults.append(
                Fault(
                    fault_type=timeout.fault_type,
                    timestamp=timeout.timestamp,
                    is_real=None,
                    decided_by="pending",
                )
            )
        # Board-log faults are merged after the authoritative host-log timeouts so
        # that merge_board_faults() drops board-log duplicates of the same fault.
        for board in zone_data.boards:
            board_events = parse_board_events(board.log_paths)
            merge_board_faults(board, faults_from_board_events(board_events))

    if planned_values and max(planned_values) != min(planned_values):
        warnings.append("Zonen besitzen unterschiedliche geplante Testzeiten.")

    primary_name = test_names[0]
    return TestRun(
        test_name=primary_name,
        planned_test_seconds=max(planned_values, default=0.0),
        oven_temp_setpoint_c=_oven_temperature(primary_name),
        slot_nenn_strom_a=_nominal_current(primary_name),
        zones=sorted(zone_map.values(), key=lambda item: item.zone.value),
        root_path=root,
        warnings=warnings,
    )
