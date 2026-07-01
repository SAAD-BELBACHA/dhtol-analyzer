from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class FaultType(Enum):
    OC = "OC"
    OV = "OV"
    OT = "OT"
    NETWORK = "Network"
    GERR = "GERR"
    NONE = "None"


class Zone(Enum):
    A = "A"
    B = "B"
    C = "C"


class Status(Enum):
    GREEN = "ok" # alles normal
    ORANGE = "warning" # OC, Entscheidung noch offen , T1-Sensor liefert falsche Werte.
    RED = "fault"   #  OC als echter Ausfall bestätigt


class TempMode(Enum):
    HV = "HVoltage"
    MV = "MVoltage"

# beschreibt genau neine board log messung 

@dataclass
class Measurement:
    timestamp: datetime
    v_in: float
    current: float
    vg_diff: float
    vout_dut: float
    vout_brd: float
    v_ls: float
    t0: float
    t1: float
    t0_glitch: bool = False
    t1_glitch: bool = False

# none = entscheidung offen , true = echter fehler , false = Scheinfehler

@dataclass
class Fault:
    fault_type: FaultType
    timestamp: datetime
    is_real: Optional[bool] = None
    decided_by: str = "pending"

#temp grund wann was 

@dataclass
class GlitchEvent:
    timestamp: datetime
    sensor: str
    raw_value: float
    reason: str


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


@dataclass
class Board:
    controller_id: Optional[int]
    zone: Zone
    position: int
    dut_name: str
    hw_target: str
    nenn_strom_a: float
    temp_mode: TempMode = TempMode.HV
    available_log_seconds: float = 0.0
    log_stress_seconds: float = 0.0
    log_gap_current_confirmed: Optional[bool] = None
    faults: list[Fault] = field(default_factory=list)
    glitches: list[GlitchEvent] = field(default_factory=list)
    t0_sensor_dead: bool = False
    t1_sensor_dead: bool = False
    metadata: Optional[BoardMetadata] = None
    data_path: Optional[Path] = None
    log_paths: list[Path] = field(default_factory=list)

# Prüft: Gibt es mindestens einen echten Fehler?
    
    @property
    def status(self) -> Status:
        if any(fault.is_real for fault in self.faults):
            return Status.RED
        if self.faults or self.glitches:
            return Status.ORANGE
        return Status.GREEN

    @property
    def missing_log_seconds(self) -> float:
        return max(0.0, self.log_stress_seconds - self.available_log_seconds)

    @property
    def effective_stress_seconds(self) -> float:
        if self.log_stress_seconds > 0:
            return self.log_stress_seconds
        return self.available_log_seconds


@dataclass
class ZoneData:
    zone: Zone
    boards: list[Board] = field(default_factory=list)
    total_current_series: object = None
    host_log_paths: list[Path] = field(default_factory=list)


@dataclass
class TestRun:
    test_name: str
    planned_test_seconds: float
    oven_temp_setpoint_c: float
    slot_nenn_strom_a: float
    zones: list[ZoneData] = field(default_factory=list)
    root_path: Optional[Path] = None
    warnings: list[str] = field(default_factory=list)

    @property
    def all_boards(self) -> list[Board]:
        return [board for zone in self.zones for board in zone.boards]

    def nachbelastung_seconds_for(self, board: Board) -> float:
        return max(
            0.0,
            self.planned_test_seconds - board.effective_stress_seconds,
        )
