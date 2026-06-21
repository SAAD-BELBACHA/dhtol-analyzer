from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd

from config import (
    CURRENT_DROP_THRESHOLD_A,
    CURRENT_MATCH_TOLERANCE_A,
    TIME_CORRELATION_WINDOW_S,
)


@dataclass
class CurrentAttributionResult:
    event_time: datetime
    current_before_a: float
    current_after_a: float
    current_drop_a: float
    estimated_failed_slots: int
    matched_board: Optional[str]
    ambiguous: bool
    reason: str


def attribute_current_drop(
    zone_current: pd.Series,
    event_time: datetime,
    slot_nominal_current_a: float,
    board_name: str = "",
    board_last_current_a: Optional[float] = None,
) -> CurrentAttributionResult:
    timestamp = pd.Timestamp(event_time)
    window = pd.Timedelta(seconds=TIME_CORRELATION_WINDOW_S)
    before = zone_current.loc[(zone_current.index >= timestamp - window) & (zone_current.index < timestamp)]
    after = zone_current.loc[(zone_current.index > timestamp) & (zone_current.index <= timestamp + window)]

    if before.empty or after.empty:
        return CurrentAttributionResult(
            event_time, 0.0, 0.0, 0.0, 0, None, True, "insufficient_current_data"
        )

    current_before = float(before.median())
    current_after = float(after.median())
    drop = max(0.0, current_before - current_after)
    nominal = max(float(slot_nominal_current_a), 0.0)
    estimated = round(drop / nominal) if nominal else 0

    fingerprint = board_last_current_a if board_last_current_a is not None else nominal
    matched = (
        board_name
        if board_name
        and drop >= CURRENT_DROP_THRESHOLD_A
        and abs(drop - fingerprint) <= CURRENT_MATCH_TOLERANCE_A
        else None
    )
    ambiguous = matched is None
    reason = "fingerprint_and_time_match" if matched else "mehrdeutig — manuelle Prüfung"

    return CurrentAttributionResult(
        event_time=event_time,
        current_before_a=current_before,
        current_after_a=current_after,
        current_drop_a=drop,
        estimated_failed_slots=max(0, estimated),
        matched_board=matched,
        ambiguous=ambiguous,
        reason=reason,
    )
