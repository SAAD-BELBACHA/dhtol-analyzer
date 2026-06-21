from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from models.data_models import Fault, FaultType, TestRun


BOARD_COLORS = (
    "#2E86DE",
    "#16A085",
    "#F39C12",
    "#8E44AD",
    "#E74C3C",
    "#00BCD4",
    "#A3CB38",
    "#E056FD",
    "#FF9F43",
    "#54A0FF",
    "#10AC84",
    "#EE5253",
)


def _downsample(frame: pd.DataFrame, max_points: int = 5000) -> pd.DataFrame:
    if len(frame) <= max_points:
        return frame
    step = max(1, len(frame) // max_points)
    return frame.iloc[::step]


def align_measurements_to_stress_start(
    measurements: pd.DataFrame,
) -> pd.DataFrame:
    frame = measurements.copy()
    if frame.empty:
        frame["elapsed_hours"] = pd.Series(dtype=float)
        return frame

    active = frame[
        frame["current"].abs().gt(0.5)
        & frame["v_in"].abs().gt(50.0)
    ]
    stress_start = pd.Timestamp(
        active["timestamp"].iloc[0]
        if not active.empty
        else frame["timestamp"].iloc[0]
    )
    frame["elapsed_hours"] = (
        pd.to_datetime(frame["timestamp"]) - stress_start
    ).dt.total_seconds() / 3600
    frame.attrs["stress_start"] = stress_start
    return frame


def stress_time_chart(run: TestRun) -> go.Figure:
    boards = run.all_boards
    logged = [board.log_stress_seconds / 3600 for board in boards]
    gaps = [
        max(0.0, run.planned_test_seconds - board.log_stress_seconds) / 3600
        for board in boards
    ]
    labels = [f"{board.zone.value}{board.position}: {board.dut_name}" for board in boards]

    figure = go.Figure()
    figure.add_bar(name="Log-Stresszeit", x=labels, y=logged, marker_color="#2E86DE")
    figure.add_bar(
        name="Rechnerische Nachbelastung",
        x=labels,
        y=gaps,
        marker_color="#F39C12",
    )
    figure.update_layout(
        barmode="stack",
        xaxis_title="Board",
        yaxis_title="Stunden",
        legend_title="Zeitanteil",
        margin=dict(l=20, r=20, t=35, b=20),
    )
    return figure


def electrical_chart(
    measurements: pd.DataFrame,
    faults: list[Fault] | None = None,
    board_label: str | None = None,
) -> go.Figure:
    frame = _downsample(measurements)
    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(
            "Board-Strom",
            "Eingangsspannung",
            "DUT-Ausgangsspannung",
        ),
    )
    signals = (
        ("current", "Board-Strom", "A", "#2E86DE", 1),
        ("v_in", "V_IN", "V", "#16A085", 2),
        ("vout_dut", "VOUT_DUT", "V", "#F39C12", 3),
    )
    for column, label, unit, color, row in signals:
        if column not in frame:
            continue
        figure.add_trace(
            go.Scatter(
                x=frame["timestamp"],
                y=frame[column],
                mode="lines",
                name=f"{label} [{unit}]",
                line=dict(color=color),
            ),
            row=row,
            col=1,
        )
        figure.update_yaxes(title_text=f"{unit}", row=row, col=1)

    fault_rows = {
        FaultType.OC: (1,),
        FaultType.OV: (2, 3),
        FaultType.GERR: (1, 2, 3),
        FaultType.NETWORK: (1, 2, 3),
    }
    signal_by_row = {
        row: (column, unit)
        for column, _, unit, _, row in signals
    }
    for fault in faults or []:
        rows = fault_rows.get(fault.fault_type, ())
        if not rows:
            continue
        label = f"⚠ {fault.fault_type.value}"
        if board_label:
            label = f"{label} · {board_label}"
        fault_time = pd.Timestamp(fault.timestamp)
        for row in rows:
            figure.add_vrect(
                x0=fault_time - pd.Timedelta(seconds=1),
                x1=fault_time + pd.Timedelta(seconds=1),
                fillcolor="#FF3B30",
                opacity=0.20,
                line_width=0,
                row=row,
                col=1,
            )
            column, unit = signal_by_row[row]
            if measurements.empty or column not in measurements:
                continue
            timestamps = pd.to_datetime(measurements["timestamp"])
            nearest_index = (timestamps - fault_time).abs().idxmin()
            marker_time = measurements.at[nearest_index, "timestamp"]
            marker_value = measurements.at[nearest_index, column]
            figure.add_trace(
                go.Scatter(
                    x=[marker_time],
                    y=[marker_value],
                    mode="markers",
                    name=label,
                    marker=dict(
                        color="#FF3B30",
                        size=13,
                        symbol="x",
                        line=dict(width=2),
                    ),
                    hovertemplate=(
                        f"{label}<br>Zeit: %{{x}}"
                        f"<br>Messwert: %{{y:.2f}} {unit}<extra></extra>"
                    ),
                    showlegend=row == rows[0],
                ),
                row=row,
                col=1,
            )
            if row == rows[0]:
                figure.add_annotation(
                    x=marker_time,
                    y=marker_value,
                    text=label,
                    showarrow=True,
                    arrowcolor="#FF3B30",
                    font=dict(color="#FF3B30"),
                    bgcolor="rgba(20,20,20,0.90)",
                    yshift=35,
                    row=row,
                    col=1,
                )
    figure.update_layout(
        height=780,
        title="Elektrische Messwerte · getrennte Skalen",
        hovermode="x unified",
        margin=dict(l=20, r=20, t=75, b=20),
    )
    figure.update_xaxes(title_text="Zeit", row=3, col=1)
    return figure


def all_board_current_chart(
    board_results: list[tuple[str, pd.DataFrame, list[Fault]]],
) -> go.Figure:
    figure = go.Figure()
    for index, (board_label, measurements, faults) in enumerate(board_results):
        if measurements.empty or "current" not in measurements:
            continue
        color = BOARD_COLORS[index % len(BOARD_COLORS)]
        frame = _downsample(measurements, max_points=3500)
        x_column = (
            "elapsed_hours"
            if "elapsed_hours" in frame
            else "timestamp"
        )
        figure.add_scatter(
            x=frame[x_column],
            y=frame["current"],
            mode="lines",
            name=board_label,
            line=dict(color=color, width=1.5),
        )
        timestamps = pd.to_datetime(measurements["timestamp"])
        for fault in faults:
            if fault.fault_type is not FaultType.OC:
                continue
            fault_time = pd.Timestamp(fault.timestamp)
            nearest_index = (timestamps - fault_time).abs().idxmin()
            marker_time = measurements.at[nearest_index, "timestamp"]
            marker_value = measurements.at[nearest_index, "current"]
            marker_x = (
                measurements.at[nearest_index, "elapsed_hours"]
                if "elapsed_hours" in measurements
                else marker_time
            )
            figure.add_scatter(
                x=[marker_x],
                y=[marker_value],
                mode="markers+text",
                name=f"OC · {board_label}",
                text=[f"OC · {board_label}"],
                textposition="top center",
                marker=dict(color="#FF3B30", size=14, symbol="x"),
                showlegend=False,
                hovertemplate=(
                    f"OC · {board_label}<br>Zeit: %{{x}}"
                    "<br>Strom: %{y:.2f} A<extra></extra>"
                ),
            )

    figure.update_layout(
        title="Alle Boards · Strom",
        xaxis_title=(
            "Stunden seit Stressbeginn"
            if any(
                "elapsed_hours" in measurements
                for _, measurements, _ in board_results
            )
            else "Zeit"
        ),
        yaxis_title="Board-Strom [A]",
        hovermode="x unified",
        margin=dict(l=20, r=20, t=55, b=20),
    )
    return figure


def all_board_voltage_chart(
    board_results: list[tuple[str, pd.DataFrame, list[Fault]]],
) -> go.Figure:
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.10,
        subplot_titles=(
            "Eingangsspannung V_IN",
            "DUT-Ausgangsspannung VOUT_DUT",
        ),
    )
    signals = (
        ("v_in", "V_IN", 1),
        ("vout_dut", "VOUT_DUT", 2),
    )
    for index, (board_label, measurements, faults) in enumerate(board_results):
        if measurements.empty:
            continue
        color = BOARD_COLORS[index % len(BOARD_COLORS)]
        frame = _downsample(measurements, max_points=3500)
        x_column = (
            "elapsed_hours"
            if "elapsed_hours" in frame
            else "timestamp"
        )
        timestamps = pd.to_datetime(measurements["timestamp"])
        for column, signal_label, row in signals:
            if column not in frame:
                continue
            figure.add_trace(
                go.Scatter(
                    x=frame[x_column],
                    y=frame[column],
                    mode="lines",
                    name=f"{board_label} · {signal_label}",
                    line=dict(color=color, width=1.5),
                    legendgroup=board_label,
                    showlegend=row == 1,
                ),
                row=row,
                col=1,
            )
            for fault in faults:
                if fault.fault_type is not FaultType.OV:
                    continue
                fault_time = pd.Timestamp(fault.timestamp)
                nearest_index = (timestamps - fault_time).abs().idxmin()
                marker_time = measurements.at[nearest_index, "timestamp"]
                marker_value = measurements.at[nearest_index, column]
                marker_x = (
                    measurements.at[nearest_index, "elapsed_hours"]
                    if "elapsed_hours" in measurements
                    else marker_time
                )
                figure.add_trace(
                    go.Scatter(
                        x=[marker_x],
                        y=[marker_value],
                        mode="markers+text",
                        name=f"OV · {board_label}",
                        text=[f"OV · {board_label}"],
                        textposition="top center",
                        marker=dict(
                            color="#FF3B30",
                            size=14,
                            symbol="x",
                        ),
                        showlegend=False,
                        hovertemplate=(
                            f"OV · {board_label}<br>Zeit: %{{x}}"
                            "<br>Spannung: %{y:.2f} V<extra></extra>"
                        ),
                    ),
                    row=row,
                    col=1,
                )

    figure.update_yaxes(title_text="V", row=1, col=1)
    figure.update_yaxes(title_text="V", row=2, col=1)
    figure.update_xaxes(
        title_text=(
            "Stunden seit Stressbeginn"
            if any(
                "elapsed_hours" in measurements
                for _, measurements, _ in board_results
            )
            else "Zeit"
        ),
        row=2,
        col=1,
    )
    figure.update_layout(
        height=650,
        title="Alle Boards · Spannungen",
        hovermode="x unified",
        margin=dict(l=20, r=20, t=75, b=20),
    )
    return figure


def zone_current_chart(series: pd.Series, label: str) -> go.Figure:
    frame = series.rename("current").to_frame().reset_index(names="timestamp")
    frame = _downsample(frame)
    figure = go.Figure(
        go.Scatter(
            x=frame["timestamp"],
            y=frame["current"],
            mode="lines",
            name=label,
            line=dict(color="#8E44AD"),
        )
    )
    figure.update_layout(
        xaxis_title="Zeit",
        yaxis_title="Gesamtstrom [A]",
        margin=dict(l=20, r=20, t=35, b=20),
    )
    return figure
