from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from parsers import tdms_diagnostics
from parsers.tdms_diagnostics import (
    TdmsDiagnosticError,
    compare_host_current_to_tdms,
    compare_log_tdms_series,
)


def test_nearest_timestamp_comparison_reports_diff_stats() -> None:
    start = datetime(2026, 1, 1)
    log = pd.Series(
        [1.0, 2.0],
        index=[start, start + timedelta(seconds=1)],
    )
    tdms = pd.Series(
        [1.01, 2.02],
        index=[
            start + timedelta(milliseconds=200),
            start + timedelta(seconds=1, milliseconds=100),
        ],
    )

    row = compare_log_tdms_series("PSU Strom", log, tdms, "current")

    assert row["Matched Samples"] == 2
    assert row["Status"] == "OK"
    assert round(row["Mean Abs Diff"], 3) == 0.015
    assert round(row["Max Abs Diff"], 3) == 0.02


def test_comparison_warns_when_threshold_is_exceeded() -> None:
    start = datetime(2026, 1, 1)
    log = pd.Series([1.0], index=[start])
    tdms = pd.Series([1.3], index=[start])

    row = compare_log_tdms_series("PSU Strom", log, tdms, "current")

    assert row["Status"] == "LOG und TDMS weichen ab"


def test_missing_tdms_file_returns_warning_row(tmp_path: Path) -> None:
    host_log = tmp_path / "run.2026-03-05.log"
    host_log.write_text(
        "2026-03-05 09:40:36\t"
        "psuV: 240, elV: 320, psuI: 14.6, elI: 10.3, V: 560, I: 24.9\n",
        encoding="utf-8",
    )

    frame = compare_host_current_to_tdms(
        host_log,
        tmp_path / "run-psu12-2026-03-05.tdms",
        tmp_path / "run-el12-2026-03-05.tdms",
    )

    assert len(frame) == 2
    assert all("TDMS-Datei fehlt" in status for status in frame["Status"])


def test_missing_nptdms_returns_warning_row(
    tmp_path: Path, monkeypatch
) -> None:
    host_log = tmp_path / "run.2026-03-05.log"
    host_log.write_text(
        "2026-03-05 09:40:36\t"
        "psuV: 240, elV: 320, psuI: 14.6, elI: 10.3, V: 560, I: 24.9\n",
        encoding="utf-8",
    )
    psu_tdms = tmp_path / "run-psu12-2026-03-05.tdms"
    el_tdms = tmp_path / "run-el12-2026-03-05.tdms"
    psu_tdms.write_text("placeholder", encoding="utf-8")
    el_tdms.write_text("placeholder", encoding="utf-8")

    def raise_missing():
        raise TdmsDiagnosticError("nptdms ist nicht installiert.")

    monkeypatch.setattr(tdms_diagnostics, "_tdms_file_class", raise_missing)

    frame = compare_host_current_to_tdms(host_log, psu_tdms, el_tdms)

    assert len(frame) == 2
    assert frame["Status"].tolist() == [
        "nptdms ist nicht installiert.",
        "nptdms ist nicht installiert.",
    ]
