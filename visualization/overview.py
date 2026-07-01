from __future__ import annotations

import pandas as pd

from analysis.stress_time import calculate_nachbelastung_seconds
from config import LOG_COVERAGE_WARNING_SECONDS
from models.data_models import Status, TestRun


STATUS_LABELS = {
    Status.GREEN: "Grün",
    Status.ORANGE: "Gelb",
    Status.RED: "Rot",
}


def board_overview_frame(
    run: TestRun, glitch_summary: dict[str, dict[str, object]] | None = None
) -> pd.DataFrame:
    glitch_summary = glitch_summary or {}
    rows: list[dict[str, object]] = []
    for board in run.all_boards:
        glitch = glitch_summary.get(board.dut_name, {})
        glitch_count = int(glitch.get("glitch_count", 0))
        missing_log_seconds = board.missing_log_seconds
        status = board.status
        if status is Status.GREEN and (
            glitch_count
            or missing_log_seconds > LOG_COVERAGE_WARNING_SECONDS
        ):
            status = Status.ORANGE
        if missing_log_seconds > LOG_COVERAGE_WARNING_SECONDS:
            log_warning = (
                f"⚠ {missing_log_seconds / 3600:.2f} h weniger Board-Logzeit als DATA · "
                + (
                    "Nachbelastung mit DATA"
                    if board.log_gap_current_confirmed is True
                    else "Strom nicht bestätigt"
                )
            )
        else:
            log_warning = "—"
        rows.append(
            {
                "Zone": board.zone.value,
                "Position": board.position,
                "Controller": (
                    board.controller_id if board.controller_id is not None else "—"
                ),
                "DUT": board.dut_name,
                "HW Target": board.hw_target,
                "Status": STATUS_LABELS[status],
                "Hinweis": log_warning,
                "DATA-Stresszeit [h]": board.log_stress_seconds / 3600,
                "Board-Log-Stresszeit [h]": board.available_log_seconds / 3600,
                "Abweichung DATA - Board-Logs [h]": missing_log_seconds / 3600,
                "Strombestätigung": (
                    "Bestätigt"
                    if board.log_gap_current_confirmed is True
                    else "Nicht bestätigt"
                    if board.log_gap_current_confirmed is False
                    else "Nicht nötig"
                ),
                "Nachbelastung laut DATA [h]": calculate_nachbelastung_seconds(
                    run.planned_test_seconds, board.effective_stress_seconds
                )
                / 3600,
                "Nachbelastung laut Board-Log [h]": calculate_nachbelastung_seconds(
                    run.planned_test_seconds, board.available_log_seconds
                )
                / 3600,
                "Glitches": glitch_count,
                "T0 defekt": bool(glitch.get("t0_sensor_dead", False)),
                "T1 defekt": bool(glitch.get("t1_sensor_dead", False)),
            }
        )
    return pd.DataFrame(rows)
