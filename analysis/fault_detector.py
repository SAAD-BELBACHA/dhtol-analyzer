from __future__ import annotations

from collections.abc import Iterable

from config import BOARD_FAULT_SUMMARY_WINDOW_S, FAULT_SOURCE_MERGE_TOLERANCE_S
from models.data_models import Board, Fault, FaultType
from parsers.board_log import BoardEvent


def faults_from_board_events(events: Iterable[BoardEvent]) -> list[Fault]:
    faults: list[Fault] = []
    seen: set[tuple[FaultType, object]] = set()
    last_fault_by_type: dict[FaultType, Fault] = {}
    for event in sorted(events, key=lambda item: item.timestamp):
        if event.fault_type is FaultType.NONE:
            continue
        key = (event.fault_type, event.timestamp)
        if key in seen:
            continue
        previous = last_fault_by_type.get(event.fault_type)
        is_summary = "ERROR OCCURRED" in event.text.upper()
        if (
            is_summary
            and previous is not None
            and 0
            <= (event.timestamp - previous.timestamp).total_seconds()
            <= BOARD_FAULT_SUMMARY_WINDOW_S
        ):
            continue
        seen.add(key)
        fault = Fault(
            fault_type=event.fault_type,
            timestamp=event.timestamp,
            is_real=None,
            decided_by="pending",
        )
        faults.append(fault)
        last_fault_by_type[event.fault_type] = fault
    return faults


def merge_board_faults(board: Board, detected: Iterable[Fault]) -> None:
    for fault in detected:
        duplicate = any(
            existing.fault_type is fault.fault_type
            and abs((existing.timestamp - fault.timestamp).total_seconds())
            <= FAULT_SOURCE_MERGE_TOLERANCE_S
            for existing in board.faults
        )
        if not duplicate:
            board.faults.append(fault)
    board.faults.sort(key=lambda fault: fault.timestamp)
