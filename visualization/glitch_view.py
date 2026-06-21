from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from models.data_models import Fault, FaultType, TempMode
from visualization.charts import BOARD_COLORS


def _add_fault_markers(
    figure: go.Figure,
    faults: list[Fault],
    board_label: str | None = None,
) -> None:
    for fault in faults:
        if fault.fault_type is not FaultType.OT:
            continue
        label = f"⚠ {fault.fault_type.value}"
        if board_label:
            label = f"{label} · {board_label}"
        figure.add_vline(
            x=fault.timestamp,
            line_color="#FF3B30",
            line_width=2,
            line_dash="dash",
        )
        figure.add_annotation(
            x=fault.timestamp,
            y=1,
            yref="paper",
            text=label,
            showarrow=True,
            arrowcolor="#FF3B30",
            font=dict(color="#FF3B30"),
            bgcolor="rgba(20,20,20,0.85)",
        )


def temperature_sensor_labels(temp_mode: TempMode) -> dict[str, str]:
    if temp_mode is TempMode.MV:
        return {
            "t0": "T0 · Low-Side-Schalter",
            "t1": "T1 · DUT-Board",
        }
    return {
        "t0": "T0 · Low-Side-Schalter",
        "t1": "T1 · High-Side-Schalter",
    }


def temperature_glitch_chart(
    measurements: pd.DataFrame,
    temp_mode: TempMode = TempMode.HV,
    faults: list[Fault] | None = None,
    board_label: str | None = None,
    max_points: int = 7000,
) -> go.Figure:
    if len(measurements) > max_points:
        step = max(1, len(measurements) // max_points)
        display = measurements.iloc[::step]
    else:
        display = measurements

    figure = go.Figure()
    colors = {"t0": "#16A085", "t1": "#2980B9"}
    labels = temperature_sensor_labels(temp_mode)
    for sensor in ("t0", "t1"):
        figure.add_scatter(
            x=display["timestamp"],
            y=display.get(f"{sensor}_smooth", display[sensor]),
            mode="lines",
            name=f"{labels[sensor]} · geglättet",
            line=dict(color=colors[sensor]),
        )
        mask = measurements.get(f"{sensor}_glitch", False)
        if not isinstance(mask, pd.Series):
            continue
        flagged = measurements.loc[mask]
        if len(flagged) > 1500:
            flagged = flagged.iloc[:: max(1, len(flagged) // 1500)]
        figure.add_scatter(
            x=flagged["timestamp"],
            y=flagged[sensor],
            mode="markers",
            name=f"{labels[sensor]} · Glitch",
            marker=dict(color="#E74C3C", size=5),
        )

    _add_fault_markers(figure, faults or [], board_label)
    figure.update_layout(
        xaxis_title="Zeit",
        yaxis_title="Temperatur [°C]",
        margin=dict(l=20, r=20, t=35, b=20),
    )
    return figure


def all_board_temperature_chart(
    board_results: list[
        tuple[str, pd.DataFrame, TempMode, list[Fault]]
    ],
    max_points_per_board: int = 3500,
) -> go.Figure:
    figure = go.Figure()
    for index, (board_label, measurements, temp_mode, faults) in enumerate(
        board_results
    ):
        if measurements.empty:
            continue
        step = max(1, len(measurements) // max_points_per_board)
        display = measurements.iloc[::step]
        x_column = (
            "elapsed_hours"
            if "elapsed_hours" in display
            else "timestamp"
        )
        color = BOARD_COLORS[index % len(BOARD_COLORS)]
        labels = temperature_sensor_labels(temp_mode)
        figure.add_scatter(
            x=display[x_column],
            y=display.get("t0_smooth", display["t0"]),
            mode="lines",
            name=f"{board_label} · {labels['t0']}",
            line=dict(color=color, width=1.5),
        )
        figure.add_scatter(
            x=display[x_column],
            y=display.get("t1_smooth", display["t1"]),
            mode="lines",
            name=f"{board_label} · {labels['t1']}",
            line=dict(color=color, width=1.5, dash="dot"),
        )
        for fault in faults:
            if fault.fault_type is not FaultType.OT:
                continue
            stress_start = measurements.attrs.get("stress_start")
            fault_x = (
                (
                    pd.Timestamp(fault.timestamp)
                    - pd.Timestamp(stress_start)
                ).total_seconds()
                / 3600
                if stress_start is not None
                else fault.timestamp
            )
            figure.add_vline(
                x=fault_x,
                line_color="#FF3B30",
                line_width=2,
                line_dash="dash",
            )
            figure.add_annotation(
                x=fault_x,
                y=1,
                yref="paper",
                text=f"OT · {board_label}",
                showarrow=True,
                font=dict(color="#FF3B30"),
            )

    figure.update_layout(
        title="Alle Boards · Temperaturen",
        xaxis_title=(
            "Stunden seit Stressbeginn"
            if any(
                "elapsed_hours" in measurements
                for _, measurements, _, _ in board_results
            )
            else "Zeit"
        ),
        yaxis_title="Temperatur [°C]",
        hovermode="x unified",
        margin=dict(l=20, r=20, t=55, b=20),
    )
    return figure
