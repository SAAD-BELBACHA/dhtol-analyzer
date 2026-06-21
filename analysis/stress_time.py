from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd

from config import CURRENT_DROP_CONFIRM_SAMPLES, CURRENT_DROP_THRESHOLD_A


@dataclass
class StressTimeResult:
    logged_seconds: float
    planned_seconds: float
    calculated_nachbelastung_seconds: float
    confirmed_nachbelastung_seconds: Optional[float] = None
    stress_end: Optional[datetime] = None
    reason: str = "planned_minus_logged"


def calculate_nachbelastung_seconds(
    planned_test_seconds: float, log_stress_seconds: float
) -> float:
    return max(0.0, float(planned_test_seconds) - float(log_stress_seconds))


def calculate_planned_gap(
    planned_test_seconds: float, log_stress_seconds: float
) -> StressTimeResult:
    return StressTimeResult(
        logged_seconds=max(0.0, float(log_stress_seconds)),
        planned_seconds=max(0.0, float(planned_test_seconds)),
        calculated_nachbelastung_seconds=calculate_nachbelastung_seconds(
            planned_test_seconds, log_stress_seconds
        ),
    )


def confirm_nachbelastung_from_current(
    planned_result: StressTimeResult,
    log_stop: datetime,
    zone_current: Optional[pd.Series],
    threshold_a: float = CURRENT_DROP_THRESHOLD_A,
) -> StressTimeResult:
    if zone_current is None or zone_current.empty:
        planned_result.reason = "no_current_data"
        return planned_result

    stop_timestamp = pd.Timestamp(log_stop)
    before_stop = zone_current.loc[zone_current.index < stop_timestamp]
    after_stop = zone_current.loc[zone_current.index >= stop_timestamp]
    if before_stop.empty:
        planned_result.reason = "no_current_before_log_stop"
        return planned_result
    if after_stop.empty:
        planned_result.reason = "no_current_after_log_stop"
        return planned_result

    baseline_window = before_stop.iloc[-min(10, len(before_stop)) :]
    baseline = float(baseline_window.median())
    drop_mask = after_stop <= baseline - threshold_a
    confirmed_start = None
    confirmations = max(1, int(CURRENT_DROP_CONFIRM_SAMPLES))
    for index in range(0, len(drop_mask) - confirmations + 1):
        if bool(drop_mask.iloc[index : index + confirmations].all()):
            confirmed_start = drop_mask.index[index]
            break

    if confirmed_start is None:
        planned_result.reason = "current_did_not_drop_in_available_data"
        return planned_result

    stress_end = confirmed_start.to_pydatetime()
    confirmed = max(0.0, (stress_end - log_stop).total_seconds())
    planned_result.confirmed_nachbelastung_seconds = min(
        confirmed, planned_result.calculated_nachbelastung_seconds
    )
    planned_result.stress_end = stress_end
    planned_result.reason = "current_drop_detected"
    return planned_result
