from __future__ import annotations

import plotly.graph_objects as go

from models.data_models import TestRun


def ttf_plot(run: TestRun) -> go.Figure:
    labels: list[str] = []
    hours: list[float] = []
    colors: list[str] = []
    for board in run.all_boards:
        for fault in board.faults:
            labels.append(f"{board.zone.value}{board.position}: {board.dut_name}")
            hours.append(board.log_stress_seconds / 3600)
            colors.append("#C0392B" if fault.is_real else "#F39C12")

    figure = go.Figure()
    if labels:
        figure.add_scatter(
            x=hours,
            y=labels,
            mode="markers",
            marker=dict(color=colors, size=11),
            name="Fehler",
        )
    figure.update_layout(
        xaxis_title="TTF / Log-Stresszeit [h]",
        yaxis_title="Board",
        margin=dict(l=20, r=20, t=35, b=20),
    )
    return figure
