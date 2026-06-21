from datetime import datetime, timedelta

from analysis.fault_detector import faults_from_board_events, merge_board_faults
from models.data_models import Board, Fault, FaultType, Zone
from parsers.board_log import BoardEvent


def test_board_fault_summary_is_not_counted_as_second_fault() -> None:
    start = datetime(2026, 3, 5, 9, 40, 37)
    events = [
        BoardEvent(start, "OC err", FaultType.OC),
        BoardEvent(
            start + timedelta(seconds=14),
            "OC Error occurred",
            FaultType.OC,
        ),
    ]

    faults = faults_from_board_events(events)

    assert len(faults) == 1
    assert faults[0].timestamp == start


def test_host_and_board_fault_at_same_time_are_merged() -> None:
    start = datetime(2026, 3, 5, 9, 40, 37)
    board = Board(
        controller_id=58,
        zone=Zone.A,
        position=1,
        dut_name="58_1_2",
        hw_target="target58",
        nenn_strom_a=3.15,
        faults=[Fault(FaultType.OC, start)],
    )

    merge_board_faults(
        board,
        [Fault(FaultType.OC, start + timedelta(milliseconds=450))],
    )

    assert len(board.faults) == 1
