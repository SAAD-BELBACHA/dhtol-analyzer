from datetime import datetime, timedelta

import pandas as pd

from analysis.glitch_detector import (
    detect_temperature_glitches,
    summarize_temperature_glitch_groups,
)


def _frame(t1_values: list[float]) -> pd.DataFrame:
    start = datetime(2026, 1, 1)
    return pd.DataFrame(
        {
            "timestamp": [start + timedelta(seconds=index) for index in range(len(t1_values))],
            "t0": [85.0] * len(t1_values),
            "t1": t1_values,
        }
    )


def test_stable_temperatures_are_not_glitches() -> None:
    result = detect_temperature_glitches(_frame([84.0] * 40), 85.0)

    assert not result.measurements["t0_glitch"].any()
    assert not result.measurements["t1_glitch"].any()
    assert not result.t1_sensor_dead


def test_unstable_sensor_is_marked_dead() -> None:
    values = [85.0, 70.0] * 60
    result = detect_temperature_glitches(_frame(values), 85.0)

    assert result.measurements["t1_glitch"].any()
    assert result.t1_sensor_dead


def test_monotonic_warmup_is_not_a_dead_sensor() -> None:
    values = [25.0 + index * 0.3 for index in range(200)]
    result = detect_temperature_glitches(_frame(values), 85.0)

    assert not result.t1_sensor_dead


def test_grouped_glitch_summary_combines_days() -> None:
    stable_day = _frame([85.0] * 40)
    unstable_day = _frame([85.0, 70.0] * 60)

    summary = summarize_temperature_glitch_groups(
        [stable_day, unstable_day], 85.0
    )

    assert summary.glitch_count > 0
    assert summary.t1_sensor_dead
