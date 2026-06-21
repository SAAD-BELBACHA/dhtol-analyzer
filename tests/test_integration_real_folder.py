from pathlib import Path

import pytest

from analysis.glitch_detector import detect_temperature_glitches
from parsers.folder_loader import load_board_date, load_testrun


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    not any(ROOT.glob("*.mtpx")), reason="Echte Testdaten sind nicht vorhanden."
)
def test_real_folder_has_eight_boards_and_known_glitches() -> None:
    run = load_testrun(ROOT)

    assert len(run.zones) == 1
    assert len(run.all_boards) == 8
    assert run.planned_test_seconds == 1001 * 3600

    defective_positions: list[int] = []
    for board in run.all_boards:
        parsed = load_board_date(board, "2026-05-08")
        glitches = detect_temperature_glitches(
            parsed.measurements, run.oven_temp_setpoint_c
        )
        if glitches.t0_sensor_dead or glitches.t1_sensor_dead:
            defective_positions.append(board.position)

    assert defective_positions == [3, 6, 7, 8]
