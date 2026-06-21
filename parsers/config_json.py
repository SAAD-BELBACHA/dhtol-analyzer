from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator, Optional

from models.data_models import OvenplanEntry, ParsedConfig, TempMode, Zone


_DUT_ID_PATTERN = re.compile(r"(\d+)_(\d+)_(\d+)$")
_ZONE_PATTERN = re.compile(r"(?:^|_)([ABC])(?:_|$)", re.IGNORECASE)
_TEMP_MODE_PATTERN = re.compile(r"\bf_MV\s*=\s*(true|false)\b", re.IGNORECASE)


def _walk_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_strings(child)


def _parse_zone(value: object) -> Optional[Zone]:
    try:
        return Zone(str(value).strip().upper())
    except (TypeError, ValueError):
        return None


def _zone_from_test_name(test_name: str) -> Optional[Zone]:
    match = _ZONE_PATTERN.search(test_name)
    return _parse_zone(match.group(1)) if match else None


def _temp_mode_from_data(data: dict[str, Any]) -> TempMode:
    for text in _walk_strings(data.get("Testplans", [])):
        match = _TEMP_MODE_PATTERN.search(text)
        if match:
            return TempMode.MV if match.group(1).lower() == "true" else TempMode.HV
    return TempMode.HV


def parse_config_json(path: str | Path) -> ParsedConfig:
    source = Path(path)
    fallback_name = source.stem
    warnings: list[str] = []

    try:
        with source.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return ParsedConfig(
            test_name=fallback_name,
            zone=_zone_from_test_name(fallback_name),
            temp_mode=TempMode.HV,
            source_path=source,
            warnings=[f"JSON konnte nicht gelesen werden: {exc}"],
        )

    test_name = str(data.get("Test Name") or fallback_name)
    fallback_zone = _zone_from_test_name(test_name)
    temp_mode = _temp_mode_from_data(data)
    instruments = [str(item) for item in data.get("Instruments", []) if item]
    entries: list[OvenplanEntry] = []

    ovenplan = data.get("Ovenplan", [])
    if not isinstance(ovenplan, list):
        ovenplan = []
        warnings.append("Ovenplan ist keine Liste.")

    for index, row in enumerate(ovenplan, start=1):
        if not isinstance(row, dict):
            warnings.append(f"Ovenplan-Eintrag {index} übersprungen: kein Objekt.")
            continue

        dut_name = str(row.get("DUT") or "").strip()
        id_match = _DUT_ID_PATTERN.search(dut_name)
        zone = _parse_zone(row.get("Zone")) or fallback_zone

        try:
            position = int(str(row.get("Slot") or "").strip())
        except ValueError:
            position = 0

        if not dut_name or not zone or position <= 0:
            warnings.append(
                f"Ovenplan-Eintrag {index} übersprungen: DUT, Zone oder Slot ungültig."
            )
            continue

        entries.append(
            OvenplanEntry(
                controller_id=int(id_match.group(1)) if id_match else None,
                position=position,
                zone=zone,
                dut_name=dut_name,
                hw_target=str(row.get("HW Target") or "").strip(),
                load_board=str(row.get("LoadBoard") or "").strip(),
                dut_board=str(row.get("DUTBoard") or "").strip(),
                uc_fsm=str(row.get("uC FSM") or "").strip(),
            )
        )

    return ParsedConfig(
        test_name=test_name,
        zone=fallback_zone or (entries[0].zone if entries else None),
        temp_mode=temp_mode,
        instruments=instruments,
        ovenplan_entries=entries,
        source_path=source,
        warnings=warnings,
    )
