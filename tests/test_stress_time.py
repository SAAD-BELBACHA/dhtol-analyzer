from datetime import datetime, timedelta

import pandas as pd

from analysis.stress_time import (
    calculate_nachbelastung_seconds,
    calculate_planned_gap,
    confirm_nachbelastung_from_current,
)


def test_nachbelastung_is_planned_minus_logged() -> None:
    assert calculate_nachbelastung_seconds(10 * 3600, 8 * 3600) == 2 * 3600


def test_nachbelastung_never_negative() -> None:
    assert calculate_nachbelastung_seconds(8 * 3600, 10 * 3600) == 0


def test_current_drop_confirms_short_post_stress_window() -> None:
    stop = datetime(2026, 3, 5, 9, 40, 37)
    index = [
        stop - timedelta(seconds=6),
        stop - timedelta(seconds=3),
        stop + timedelta(seconds=3),
        stop + timedelta(seconds=6),
    ]
    current = pd.Series([25.0, 24.9, 0.05, 0.05], index=index)
    result = calculate_planned_gap(1001 * 3600, 21)

    confirmed = confirm_nachbelastung_from_current(result, stop, current)

    assert confirmed.reason == "current_drop_detected"
    assert confirmed.confirmed_nachbelastung_seconds == 3.0


def test_missing_drop_in_partial_data_stays_unconfirmed() -> None:
    stop = datetime(2026, 3, 5, 9, 40, 37)
    current = pd.Series(
        [25.0, 24.9, 24.9],
        index=[
            stop - timedelta(seconds=3),
            stop + timedelta(seconds=3),
            stop + timedelta(seconds=6),
        ],
    )
    result = calculate_planned_gap(1001 * 3600, 21)

    confirmed = confirm_nachbelastung_from_current(result, stop, current)

    assert confirmed.reason == "current_did_not_drop_in_available_data"
    assert confirmed.confirmed_nachbelastung_seconds is None
