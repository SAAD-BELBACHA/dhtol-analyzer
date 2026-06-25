from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class Zone(Enum):
    A = "A"
    B = "B"
    C = "C"


class TempMode(Enum):
    HV = "HVoltage"
    MV = "MVoltage"


@dataclass
class OvenplanEntry:
    controller_id: Optional[int]
    position: int
    zone: Zone
    dut_name: str
    hw_target: str
    load_board: str = ""
    dut_board: str = ""
    uc_fsm: str = ""


@dataclass
class ParsedConfig:
    test_name: str
    zone: Optional[Zone]
    temp_mode: TempMode
    instruments: list[str] = field(default_factory=list)
    ovenplan_entries: list[OvenplanEntry] = field(default_factory=list)
    source_path: Optional[Path] = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class BoardMetadata:
    log_stress_seconds: float = 0.0
    firmware_version: str = ""
    source_path: Optional[Path] = None
