from datetime import datetime, timedelta

import pandas as pd

from analysis.current_attribution import attribute_current_drop


def test_current_drop_matches_board_fingerprint() -> None:
    event = datetime(2026, 1, 1, 12, 0, 5)
    index = [event + timedelta(seconds=offset) for offset in range(-5, 6)]
    values = [16.0 if timestamp < event else 14.0 for timestamp in index]
    series = pd.Series(values, index=index)

    result = attribute_current_drop(
        series,
        event,
        slot_nominal_current_a=2.0,
        board_name="88_1_2",
        board_last_current_a=2.0,
    )

    assert result.current_drop_a == 2.0
    assert result.estimated_failed_slots == 1
    assert result.matched_board == "88_1_2"
    assert not result.ambiguous
