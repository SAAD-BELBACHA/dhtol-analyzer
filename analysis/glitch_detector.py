from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from config import (
    TEMP_DEAD_SENSOR_WINDOW_S,
    TEMP_INSTABILITY_DIRECTION_CHANGE_MIN,
    TEMP_INSTABILITY_EFFICIENCY_MAX,
    TEMP_INSTABILITY_RANGE_C,
    TEMP_MAX_DTDT_C_PER_S,
    TEMP_MIN_PLAUSIBLE_DELTA_C,
    TEMP_PHYS_MAX_C,
    TEMP_PHYS_MIN_C,
    MAX_GLITCH_EVENTS_PER_SENSOR,
)
from models.data_models import GlitchEvent


@dataclass
class GlitchDetectionResult:
    measurements: pd.DataFrame
    events: list[GlitchEvent]
    t0_sensor_dead: bool
    t1_sensor_dead: bool


@dataclass
class GlitchSummary:
    glitch_count: int = 0
    t0_sensor_dead: bool = False
    t1_sensor_dead: bool = False


def _dead_sensor(mask: pd.Series, timestamps: pd.Series) -> bool:
    start = None
    for flagged, timestamp in zip(mask.to_numpy(), timestamps):
        if flagged and start is None:
            start = timestamp
        elif not flagged:
            start = None
        if start is not None and (timestamp - start).total_seconds() >= TEMP_DEAD_SENSOR_WINDOW_S:
            return True
    return False


def _sensor_flags(
    frame: pd.DataFrame, sensor: str, oven_setpoint_c: float
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    values = pd.to_numeric(frame[sensor], errors="coerce")
    lower_bound = max(
        TEMP_PHYS_MIN_C, float(oven_setpoint_c) - TEMP_MIN_PLAUSIBLE_DELTA_C
    )
    physical_bounds = (
        values.lt(TEMP_PHYS_MIN_C)
        | values.gt(TEMP_PHYS_MAX_C)
        | values.isna()
    )

    seconds = frame["timestamp"].diff().dt.total_seconds()
    rate = values.diff().abs().div(seconds.where(seconds > 0))
    rate_flags = rate.gt(TEMP_MAX_DTDT_C_PER_S).fillna(False)

    indexed = pd.Series(values.to_numpy(), index=pd.DatetimeIndex(frame["timestamp"]))
    warming_rate = values.diff().rolling(
        int(TEMP_DEAD_SENSOR_WINDOW_S), min_periods=10
    ).mean()
    warming = pd.Series(
        warming_rate.gt(0.01).to_numpy(), index=frame.index
    ).fillna(False)
    plausibility_low = values.lt(lower_bound) & ~warming
    bounds = physical_bounds | plausibility_low

    rolling = indexed.rolling(
        f"{int(TEMP_DEAD_SENSOR_WINDOW_S)}s", min_periods=10
    )
    rolling_range = rolling.max() - rolling.min()

    differences = indexed.diff()
    total_variation = differences.abs().rolling(
        int(TEMP_DEAD_SENSOR_WINDOW_S), min_periods=10
    ).sum()
    net_change = indexed.diff(int(TEMP_DEAD_SENSOR_WINDOW_S) - 1).abs()
    movement_efficiency = net_change.div(total_variation.where(total_variation > 0))

    directions = np.sign(differences).replace(0, np.nan)
    direction_changes = (
        directions.ne(directions.shift())
        .astype(float)
        .rolling(int(TEMP_DEAD_SENSOR_WINDOW_S), min_periods=10)
        .mean()
    )

    instability = (
        rolling_range.gt(TEMP_INSTABILITY_RANGE_C)
        & movement_efficiency.lt(TEMP_INSTABILITY_EFFICIENCY_MAX)
        & direction_changes.gt(TEMP_INSTABILITY_DIRECTION_CHANGE_MIN)
    )
    instability = pd.Series(instability.to_numpy(), index=frame.index).fillna(False)

    combined = bounds | rate_flags | instability
    return combined, bounds, physical_bounds, rate_flags, instability


def detect_temperature_glitches(
    measurements: pd.DataFrame, oven_setpoint_c: float
) -> GlitchDetectionResult:
    frame = measurements.copy()
    if frame.empty:
        frame["t0_glitch"] = pd.Series(dtype=bool)
        frame["t1_glitch"] = pd.Series(dtype=bool)
        return GlitchDetectionResult(frame, [], False, False)

    frame = frame.sort_values("timestamp").reset_index(drop=True)
    events: list[GlitchEvent] = []
    dead: dict[str, bool] = {}

    for sensor in ("t0", "t1"):
        combined, bounds, physical_bounds, rate, instability = _sensor_flags(
            frame, sensor, oven_setpoint_c
        )
        frame[f"{sensor}_glitch"] = combined
        frame[f"{sensor}_smooth"] = frame[sensor].rolling(
            window=5, center=True, min_periods=1
        ).median()
        dead[sensor] = _dead_sensor(instability, frame["timestamp"]) or _dead_sensor(
            physical_bounds, frame["timestamp"]
        )

        flagged_indices = np.flatnonzero(combined.to_numpy())[
            :MAX_GLITCH_EVENTS_PER_SENSOR
        ]
        for index in flagged_indices:
            if bounds.iloc[index]:
                reason = "out_of_bounds"
            elif rate.iloc[index]:
                reason = "rate_too_high"
            else:
                reason = "sensor_unstable"
            events.append(
                GlitchEvent(
                    timestamp=frame.at[index, "timestamp"],
                    sensor=sensor.upper(),
                    raw_value=float(frame.at[index, sensor]),
                    reason=reason,
                )
            )

        if dead[sensor]:
            first_index = int(np.flatnonzero(combined.to_numpy())[0])
            events.append(
                GlitchEvent(
                    timestamp=frame.at[first_index, "timestamp"],
                    sensor=sensor.upper(),
                    raw_value=float(frame.at[first_index, sensor]),
                    reason="sensor_dead",
                )
            )

    return GlitchDetectionResult(
        measurements=frame,
        events=events,
        t0_sensor_dead=dead["t0"],
        t1_sensor_dead=dead["t1"],
    )


def summarize_temperature_glitch_groups(
    measurement_groups: Iterable[pd.DataFrame], oven_setpoint_c: float
) -> GlitchSummary:
    summary = GlitchSummary()
    for measurements in measurement_groups:
        result = detect_temperature_glitches(measurements, oven_setpoint_c)
        summary.glitch_count += int(
            result.measurements.get("t0_glitch", pd.Series(dtype=bool)).sum()
            + result.measurements.get("t1_glitch", pd.Series(dtype=bool)).sum()
        )
        summary.t0_sensor_dead = (
            summary.t0_sensor_dead or result.t0_sensor_dead
        )
        summary.t1_sensor_dead = (
            summary.t1_sensor_dead or result.t1_sensor_dead
        )
    return summary


def summarize_temperature_log_paths(
    path_groups: list[list[str]], oven_setpoint_c: float
) -> GlitchSummary:
    from parsers.board_log import parse_temperature_logs

    return summarize_temperature_glitch_groups(
        (
            parse_temperature_logs(paths)
            for paths in path_groups
        ),
        oven_setpoint_c,
    )
