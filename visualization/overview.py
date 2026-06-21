from __future__ import annotations

import pandas as pd

from analysis.stress_time import calculate_nachbelastung_seconds
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
        status = board.status
        if status is Status.GREEN and glitch_count:
            status = Status.ORANGE
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
                "Log-Stresszeit [h]": board.log_stress_seconds / 3600,
                "Rechnerische Nachbelastung [h]": calculate_nachbelastung_seconds(
                    run.planned_test_seconds, board.log_stress_seconds
                )
                / 3600,
                "Glitches": glitch_count,
                "T0 defekt": bool(glitch.get("t0_sensor_dead", False)),
                "T1 defekt": bool(glitch.get("t1_sensor_dead", False)),
            }
        )
    return pd.DataFrame(rows)
