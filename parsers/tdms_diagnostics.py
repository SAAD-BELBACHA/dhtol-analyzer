from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from parsers.board_log import parse_board_logs
from parsers.host_log import parse_host_current_series


TDMS_TIMEZONE = "Europe/Vienna"
TOLERANCE = pd.Timedelta(seconds=2)
RESULT_COLUMNS = [
    "Signal",
    "LOG Samples",
    "TDMS Samples",
    "Matched Samples",
    "LOG Median",
    "TDMS Median",
    "Mean Abs Diff",
    "Max Abs Diff",
    "Status",
]

_THRESHOLDS = {
    "current": (0.02, 0.10),
    "temperature": (0.10, 1.00),
    "voltage": (1.00, 10.00),
}


class TdmsDiagnosticError(RuntimeError):
    pass


def _tdms_file_class():
    try:
        from nptdms import TdmsFile
    except ImportError as exc:
        raise TdmsDiagnosticError(
            "nptdms ist nicht installiert."
        ) from exc
    return TdmsFile


def _datetime_index(values: object) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.to_datetime(values)).astype("datetime64[ns]")


def _tdms_datetime_index(values: object) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(
        pd.to_datetime(values, utc=True)
        .tz_convert(TDMS_TIMEZONE)
        .tz_localize(None)
        .astype("datetime64[ns]")
    )


def read_tdms_channel(path: str | Path, group: str, channel: str) -> pd.Series:
    source = Path(path)
    if not source.exists():
        raise TdmsDiagnosticError(f"TDMS-Datei fehlt: {source.name}")
    if source.stat().st_size == 0:
        raise TdmsDiagnosticError(f"TDMS-Datei ist leer: {source.name}")

    tdms_file = _tdms_file_class()
    try:
        with tdms_file.open(source) as tdms:
            values = tdms[group][channel][:]
            times = tdms[group][f"{channel}_time"][:]
    except (OSError, KeyError, ValueError, TypeError) as exc:
        raise TdmsDiagnosticError(
            f"TDMS-Kanal fehlt oder ist nicht lesbar: {source.name} / {group}.{channel}"
        ) from exc

    if len(values) == 0 or len(values) != len(times):
        raise TdmsDiagnosticError(
            f"TDMS-Kanal hat keine passenden Zeitwerte: {source.name} / {group}.{channel}"
        )

    return pd.Series(
        values,
        index=_tdms_datetime_index(times),
        name="tdms",
        dtype="float64",
    ).sort_index()


def _status(signal_type: str, matched: int, mean_abs: float, max_abs: float) -> str:
    if matched <= 0:
        return "Keine passenden Zeitpunkte"
    mean_limit, max_limit = _THRESHOLDS[signal_type]
    if mean_abs <= mean_limit and max_abs <= max_limit:
        return "OK"
    return "LOG und TDMS weichen ab"


def _error_row(signal: str, log_samples: int, status: str) -> dict[str, object]:
    return {
        "Signal": signal,
        "LOG Samples": log_samples,
        "TDMS Samples": 0,
        "Matched Samples": 0,
        "LOG Median": None,
        "TDMS Median": None,
        "Mean Abs Diff": None,
        "Max Abs Diff": None,
        "Status": status,
    }


def compare_log_tdms_series(
    signal: str,
    log_series: pd.Series,
    tdms_series: pd.Series,
    signal_type: str,
) -> dict[str, object]:
    if signal_type not in _THRESHOLDS:
        raise ValueError(f"Unbekannter Signaltyp: {signal_type}")

    log = pd.Series(
        pd.to_numeric(log_series, errors="coerce").to_numpy(dtype=float),
        index=_datetime_index(log_series.index),
        name="log",
    ).dropna().sort_index()
    tdms = pd.Series(
        pd.to_numeric(tdms_series, errors="coerce").to_numpy(dtype=float),
        index=_datetime_index(tdms_series.index),
        name="tdms",
    ).dropna().sort_index()

    if log.empty:
        return _error_row(signal, 0, "Keine LOG-Daten")
    if tdms.empty:
        return _error_row(signal, len(log), "Keine TDMS-Daten")

    aligned = pd.merge_asof(
        log.rename_axis("timestamp").reset_index(),
        tdms.rename_axis("timestamp").reset_index(),
        on="timestamp",
        direction="nearest",
        tolerance=TOLERANCE,
    ).dropna()

    if aligned.empty:
        return {
            "Signal": signal,
            "LOG Samples": len(log),
            "TDMS Samples": len(tdms),
            "Matched Samples": 0,
            "LOG Median": float(log.median()),
            "TDMS Median": float(tdms.median()),
            "Mean Abs Diff": None,
            "Max Abs Diff": None,
            "Status": "Keine passenden Zeitpunkte",
        }

    diff = aligned["log"] - aligned["tdms"]
    mean_abs = float(diff.abs().mean())
    max_abs = float(diff.abs().max())
    return {
        "Signal": signal,
        "LOG Samples": len(log),
        "TDMS Samples": len(tdms),
        "Matched Samples": len(aligned),
        "LOG Median": float(aligned["log"].median()),
        "TDMS Median": float(aligned["tdms"].median()),
        "Mean Abs Diff": mean_abs,
        "Max Abs Diff": max_abs,
        "Status": _status(signal_type, len(aligned), mean_abs, max_abs),
    }


def _host_log_series(host_log_path: str | Path, column: str) -> pd.Series:
    frame = parse_host_current_series([host_log_path])
    if frame.empty or column not in frame:
        return pd.Series(dtype="float64")
    return pd.Series(
        frame[column].to_numpy(dtype=float),
        index=_datetime_index(frame["timestamp"]),
        name=column,
    ).sort_index()


def compare_host_current_to_tdms(
    host_log_path: str | Path,
    psu_tdms_path: str | Path,
    el_tdms_path: str | Path,
) -> pd.DataFrame:
    specs = (
        ("PSU Strom", "psu_i", psu_tdms_path),
        ("EL Strom", "el_i", el_tdms_path),
    )
    rows: list[dict[str, object]] = []
    for signal, column, tdms_path in specs:
        log_series = _host_log_series(host_log_path, column)
        try:
            tdms_series = read_tdms_channel(tdms_path, "Current", "1")
        except TdmsDiagnosticError as exc:
            rows.append(_error_row(signal, len(log_series), str(exc)))
            continue
        rows.append(
            compare_log_tdms_series(signal, log_series, tdms_series, "current")
        )
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)


_BOARD_SIGNAL_SPECS = (
    ("V_IN", "v_in", "voltage"),
    ("VG_DIFF", "vg_diff", "voltage"),
    ("VOUT_DUT", "vout_dut", "voltage"),
    ("VOUT_BRD", "vout_brd", "voltage"),
    ("V_LS", "v_ls", "voltage"),
    ("T0", "t0", "temperature"),
    ("T1", "t1", "temperature"),
)


def compare_board_log_to_tdms(
    board_log_path: str | Path,
    mqtt_tdms_path: str | Path,
    hw_target: str,
) -> pd.DataFrame:
    parsed = parse_board_logs([board_log_path])
    measurements = parsed.measurements
    rows: list[dict[str, object]] = []

    for signal, log_column, signal_type in _BOARD_SIGNAL_SPECS:
        if measurements.empty or log_column not in measurements:
            log_series = pd.Series(dtype="float64")
        else:
            log_series = pd.Series(
                measurements[log_column].to_numpy(dtype=float),
                index=_datetime_index(measurements["timestamp"]),
                name=log_column,
            ).sort_index()

        try:
            tdms_series = read_tdms_channel(mqtt_tdms_path, hw_target, signal)
        except TdmsDiagnosticError as exc:
            rows.append(_error_row(signal, len(log_series), str(exc)))
            continue
        rows.append(
            compare_log_tdms_series(signal, log_series, tdms_series, signal_type)
        )

    return pd.DataFrame(rows, columns=RESULT_COLUMNS)
