from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
from nptdms import TdmsFile

from config import LOCAL_TIMEZONE


def _local_timestamps(values: object) -> pd.DatetimeIndex:
    return (
        pd.to_datetime(values, utc=True)
        .tz_convert(LOCAL_TIMEZONE)
        .tz_localize(None)
    )


def read_instrument_current(path: str | Path) -> Optional[pd.Series]:
    source = Path(path)
    if not source.exists() or source.stat().st_size == 0:
        return None
    try:
        with TdmsFile.open(source) as tdms:
            values = tdms["Current"]["1"][:]
            times = tdms["Current"]["1_time"][:]
    except (OSError, KeyError, ValueError, TypeError):
        return None
    if len(values) == 0 or len(values) != len(times):
        return None
    return pd.Series(
        values,
        index=_local_timestamps(times),
        name="current_a",
        dtype="float64",
    ).sort_index()


def read_instrument_currents(paths: Iterable[str | Path]) -> Optional[pd.Series]:
    series = [item for path in paths if (item := read_instrument_current(path)) is not None]
    if not series:
        return None
    result = pd.concat(series).sort_index()
    return result[~result.index.duplicated(keep="last")]


def combine_instrument_currents(
    psu_current: Optional[pd.Series], el_current: Optional[pd.Series]
) -> Optional[pd.Series]:
    if psu_current is None or el_current is None:
        return None
    if psu_current.empty or el_current.empty:
        return None

    psu = (
        psu_current.rename("psu_current")
        .rename_axis("timestamp")
        .sort_index()
        .reset_index()
    )
    el = (
        el_current.rename("el_current")
        .rename_axis("timestamp")
        .sort_index()
        .reset_index()
    )
    aligned = pd.merge_asof(
        psu,
        el,
        on="timestamp",
        direction="nearest",
        tolerance=pd.Timedelta(seconds=2),
    ).dropna()
    if aligned.empty:
        return None
    return pd.Series(
        aligned["psu_current"].to_numpy() + aligned["el_current"].to_numpy(),
        index=pd.DatetimeIndex(aligned["timestamp"]),
        name="current_a",
    )


def read_mqtt_channel(
    path: str | Path, hw_target: str, channel: str
) -> Optional[pd.Series]:
    source = Path(path)
    if not source.exists() or source.stat().st_size == 0:
        return None
    try:
        with TdmsFile.open(source) as tdms:
            values = tdms[hw_target][channel][:]
            times = tdms[hw_target][f"{channel}_time"][:]
    except (OSError, KeyError, ValueError, TypeError):
        return None
    if len(values) == 0 or len(values) != len(times):
        return None
    return pd.Series(
        values,
        index=_local_timestamps(times),
        name=channel,
        dtype="float64",
    ).sort_index()
