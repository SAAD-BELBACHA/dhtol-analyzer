from __future__ import annotations

import pytest

from models.data_models import Board, TestRun as DhtolTestRun, Zone, ZoneData
from reporting.pdf_report import (
    PdfReportError,
    _overview_rows,
    build_pdf_report,
    build_report_summary,
    chart_to_png_bytes,
    pdf_report_filename,
)
from visualization.overview import board_overview_frame


def _sample_report_data():
    board = Board(
        controller_id=58,
        zone=Zone.A,
        position=1,
        dut_name="58_1_2",
        hw_target="target58",
        nenn_strom_a=2.0,
        available_log_seconds=6 * 3600,
        log_stress_seconds=8 * 3600,
        log_gap_current_confirmed=False,
    )
    run = DhtolTestRun(
        test_name="2026-05-06_A_SP212AGA_2A_25degree",
        planned_test_seconds=10 * 3600,
        oven_temp_setpoint_c=25.0,
        slot_nenn_strom_a=2.0,
        zones=[ZoneData(zone=Zone.A, boards=[board])],
    )
    overview = board_overview_frame(
        run,
        {"58_1_2": {"glitch_count": 2}},
    )
    return run, overview


def test_report_summary_names_calculation_sources() -> None:
    run, overview = _sample_report_data()

    summary = "\n".join(build_report_summary(run, overview, "Alle Tage"))

    assert "MTPX" in summary
    assert "DATA" in summary
    assert "Nachbelastung = MTPX geplante Zeit minus DATA Stresszeit" in summary
    assert "Board-Log ist Kontrollquelle" in summary
    assert "Host-Log liefert Zonenstrom" in summary
    assert "TDMS ist nur optionaler Genauigkeitscheck" in summary


def test_pdf_generator_returns_non_empty_pdf_bytes() -> None:
    pytest.importorskip("reportlab")
    run, overview = _sample_report_data()

    pdf_bytes = build_pdf_report(
        run=run,
        overview_frame=overview,
        period_label="Alle Tage",
        engineer_notes="Nachbelastung mit DATA pruefen.",
        charts=[],
        folder_path="/tmp/testlauf",
    )

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


def test_pdf_table_keeps_data_and_board_log_columns_separately() -> None:
    _run, overview = _sample_report_data()

    headers = _overview_rows(overview)[0]

    assert "DATA Stress [h]" in headers
    assert "Board-Log [h]" in headers
    assert "Nachbel. DATA [h]" in headers
    assert "Nachbel. Board-Log [h]" in headers


def test_missing_chart_export_dependency_returns_clear_error() -> None:
    class MissingKaleidoFigure:
        def to_image(self, **_kwargs):
            raise ValueError("Image export requires kaleido")

    with pytest.raises(PdfReportError, match="kaleido"):
        chart_to_png_bytes(MissingKaleidoFigure())


def test_pdf_report_filename_is_sanitized() -> None:
    assert (
        pdf_report_filename("run A/SP212AGA", "2026-05-06")
        == "dhtol_report_run_A_SP212AGA_2026-05-06.pdf"
    )
