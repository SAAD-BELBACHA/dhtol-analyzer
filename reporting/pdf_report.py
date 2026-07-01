from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
from typing import Any, Iterable
from xml.sax.saxutils import escape

import pandas as pd

from analysis.fault_detector import faults_from_board_events
from models.data_models import TestRun
from parsers.board_log import parse_board_logs_for_plot
from parsers.folder_loader import load_zone_current
from visualization.charts import (
    align_measurements_to_stress_start,
    all_board_current_chart,
    all_board_voltage_chart,
    stress_time_chart,
    zone_current_chart,
)
from visualization.glitch_view import all_board_temperature_chart


class PdfReportError(RuntimeError):
    """Raised when the PDF report cannot be generated."""


@dataclass(frozen=True)
class ReportChart:
    title: str
    figure: Any


def format_report_hours(value: float) -> str:
    return f"{value / 3600:.2f} h"


def pdf_report_filename(test_name: str, date_scope: str) -> str:
    period = "all" if date_scope == "__all__" else date_scope
    raw_name = f"dhtol_report_{test_name}_{period}.pdf"
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_name).strip("._")
    return safe_name or "dhtol_report.pdf"


def build_report_summary(
    run: TestRun,
    overview_frame: pd.DataFrame,
    period_label: str,
    glitch_summary: dict[str, dict[str, object]] | None = None,
) -> list[str]:
    glitch_summary = glitch_summary or {}
    paragraphs = [
        (
            f"Testlauf {run.test_name} mit {len(run.zones)} Zone(n) und "
            f"{len(run.all_boards)} Board(s). Zeitraum: {period_label}. "
            f"Geplante Testzeit: {format_report_hours(run.planned_test_seconds)}."
        ),
        (
            "Quellenregel: MTPX liefert die geplante Testzeit. DATA liefert "
            "die Stresszeit pro DUT. Nachbelastung = MTPX geplante Zeit minus "
            "DATA Stresszeit. Board-Log ist Kontrollquelle fuer Messkurven und "
            "Logging-Luecken. Host-Log liefert Zonenstrom. TDMS ist nur "
            "optionaler Genauigkeitscheck und aendert die Rechnung nicht."
        ),
    ]

    if overview_frame.empty:
        paragraphs.append("Keine Board-Uebersicht verfuegbar.")
        return paragraphs

    status_counts = overview_frame.get("Status", pd.Series(dtype=object)).value_counts()
    red_count = int(status_counts.get("Rot", 0))
    orange_count = int(status_counts.get("Gelb", 0))
    paragraphs.append(
        f"Status: {red_count} rot, {orange_count} gelb, "
        f"{int(status_counts.get('Gruen', status_counts.get('Grün', 0)))} gruen."
    )

    if "Nachbelastung laut DATA [h]" in overview_frame:
        max_gap = float(overview_frame["Nachbelastung laut DATA [h]"].max())
        mean_gap = float(overview_frame["Nachbelastung laut DATA [h]"].mean())
        paragraphs.append(
            f"Nachbelastung laut DATA: maximal {max_gap:.2f} h, "
            f"Durchschnitt {mean_gap:.2f} h."
        )

    if "Abweichung DATA - Board-Logs [h]" in overview_frame:
        missing = overview_frame[
            overview_frame["Abweichung DATA - Board-Logs [h]"].astype(float) > 0.0
        ]
        if missing.empty:
            paragraphs.append(
                "DATA-Stresszeit und Board-Log-Zeit zeigen keine relevanten "
                "fehlenden Log-Zeiten."
            )
        else:
            worst = missing.sort_values(
                "Abweichung DATA - Board-Logs [h]", ascending=False
            ).iloc[0]
            paragraphs.append(
                f"{len(missing)} Board(s) haben kuerzere Board-Logs als DATA. "
                f"Groesste Abweichung: {worst.get('DUT', 'unbekannt')} mit "
                f"{float(worst['Abweichung DATA - Board-Logs [h]']):.2f} h. "
                "Nachbelastung bleibt DATA-basiert."
            )

    glitch_count = 0
    if "Glitches" in overview_frame:
        glitch_count = int(overview_frame["Glitches"].fillna(0).astype(int).sum())
    elif glitch_summary:
        glitch_count = sum(
            int(item.get("glitch_count", 0)) for item in glitch_summary.values()
        )
    paragraphs.append(f"Temperatur-Glitches im Bericht: {glitch_count}.")

    return paragraphs


def build_report_charts(run: TestRun, date_scope: str) -> list[ReportChart]:
    charts: list[ReportChart] = [
        ReportChart("Stresszeit und Nachbelastung", stress_time_chart(run))
    ]
    board_results = []
    temperature_results = []
    date_filter = None if date_scope == "__all__" else date_scope

    for board in run.all_boards:
        selected_paths = (
            board.log_paths
            if date_filter is None
            else [path for path in board.log_paths if date_filter in path.name]
        )
        parsed = parse_board_logs_for_plot(selected_paths)
        if parsed.measurements.empty:
            continue
        aligned = align_measurements_to_stress_start(parsed.measurements)
        faults = faults_from_board_events(parsed.events)
        label = f"{board.zone.value}{board.position} - {board.dut_name}"
        board_results.append((label, aligned, faults))
        temperature_results.append((label, aligned, board.temp_mode, faults))

    if temperature_results:
        charts.append(
            ReportChart(
                "Alle Boards - Temperaturen",
                all_board_temperature_chart(temperature_results),
            )
        )
    if board_results:
        charts.append(
            ReportChart("Alle Boards - Strom", all_board_current_chart(board_results))
        )
        charts.append(
            ReportChart(
                "Alle Boards - Spannungen", all_board_voltage_chart(board_results)
            )
        )

    for zone_data in run.zones:
        current = load_zone_current(zone_data, date_filter, "combined")
        if current is None or current.empty:
            continue
        charts.append(
            ReportChart(
                f"Zonenstrom - Zone {zone_data.zone.value}",
                zone_current_chart(current, f"PSU + EL Zone {zone_data.zone.value}"),
            )
        )

    return charts


def chart_to_png_bytes(
    figure: Any,
    width: int = 1200,
    height: int = 680,
    scale: int = 2,
) -> bytes:
    try:
        return figure.to_image(
            format="png",
            width=width,
            height=height,
            scale=scale,
        )
    except Exception as exc:  # pragma: no cover - exact Plotly errors vary
        message = str(exc)
        if "kaleido" in message.lower() or "chrome" in message.lower():
            raise PdfReportError(
                "Chart-Export fehlt: Installiere kaleido und pruefe Chrome/Plotly "
                "Bildexport. PDF ohne Graphen ist moeglich, aber dieser Bericht "
                "braucht Graphen."
            ) from exc
        raise PdfReportError(f"Chart konnte nicht exportiert werden: {message}") from exc


def _load_reportlab() -> dict[str, Any]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            Image,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ModuleNotFoundError as exc:
        raise PdfReportError(
            "PDF-Abhaengigkeit fehlt: reportlab. Installiere requirements.txt "
            "oder `python -m pip install reportlab`."
        ) from exc

    return {
        "A4": A4,
        "Image": Image,
        "PageBreak": PageBreak,
        "Paragraph": Paragraph,
        "ParagraphStyle": ParagraphStyle,
        "SimpleDocTemplate": SimpleDocTemplate,
        "Spacer": Spacer,
        "Table": Table,
        "TableStyle": TableStyle,
        "TA_CENTER": TA_CENTER,
        "cm": cm,
        "colors": colors,
        "getSampleStyleSheet": getSampleStyleSheet,
        "landscape": landscape,
    }


def _paragraph(text: object, style: Any, paragraph_class: Any) -> Any:
    html = escape(str(text)).replace("\n", "<br/>")
    return paragraph_class(html, style)


def _table(
    rows: list[list[object]],
    paragraph_class: Any,
    table_class: Any,
    table_style_class: Any,
    styles: dict[str, Any],
    colors: Any,
    col_widths: list[float] | None = None,
) -> Any:
    wrapped = [
        [_paragraph(value, styles["table_header" if index == 0 else "table"], paragraph_class)
         for value in row]
        for index, row in enumerate(rows)
    ]
    table = table_class(wrapped, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        table_style_class(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF7")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#17324D")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C9D3DF")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _overview_rows(overview_frame: pd.DataFrame) -> list[list[object]]:
    columns = [
        "Zone",
        "Position",
        "Controller",
        "DUT",
        "Status",
        "DATA-Stresszeit [h]",
        "Board-Log-Stresszeit [h]",
        "Abweichung DATA - Board-Logs [h]",
        "Nachbelastung laut DATA [h]",
        "Nachbelastung laut Board-Log [h]",
        "Glitches",
    ]
    header_labels = {
        "Position": "Pos.",
        "Controller": "Ctrl.",
        "DATA-Stresszeit [h]": "DATA Stress [h]",
        "Board-Log-Stresszeit [h]": "Board-Log [h]",
        "Abweichung DATA - Board-Logs [h]": "Diff [h]",
        "Nachbelastung laut DATA [h]": "Nachbel. DATA [h]",
        "Nachbelastung laut Board-Log [h]": "Nachbel. Board-Log [h]",
    }
    existing_columns = [column for column in columns if column in overview_frame]
    rows: list[list[object]] = [
        [header_labels.get(column, column) for column in existing_columns]
    ]
    for _, row in overview_frame[existing_columns].iterrows():
        values: list[object] = []
        for column in existing_columns:
            value = row[column]
            if column.endswith("[h]"):
                values.append(f"{float(value):.2f}")
            else:
                values.append(value)
        rows.append(values)
    return rows


def _draw_footer(canvas: Any, document: Any) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColorRGB(0.35, 0.35, 0.35)
    canvas.drawRightString(
        document.pagesize[0] - document.rightMargin,
        0.45 * 28.3464567,
        f"Seite {document.page}",
    )
    canvas.restoreState()


def build_pdf_report(
    run: TestRun,
    overview_frame: pd.DataFrame,
    period_label: str,
    glitch_summary: dict[str, dict[str, object]] | None = None,
    engineer_notes: str = "",
    charts: Iterable[ReportChart] = (),
    folder_path: str | Path | None = None,
) -> bytes:
    rl = _load_reportlab()
    buffer = BytesIO()
    page_size = rl["landscape"](rl["A4"])
    doc = rl["SimpleDocTemplate"](
        buffer,
        pagesize=page_size,
        leftMargin=1.2 * rl["cm"],
        rightMargin=1.2 * rl["cm"],
        topMargin=1.0 * rl["cm"],
        bottomMargin=1.0 * rl["cm"],
        pageCompression=0,
    )

    base_styles = rl["getSampleStyleSheet"]()
    styles = {
        "title": rl["ParagraphStyle"](
            "ReportTitle",
            parent=base_styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            alignment=rl["TA_CENTER"],
            textColor=rl["colors"].HexColor("#17324D"),
            spaceAfter=14,
        ),
        "heading": rl["ParagraphStyle"](
            "ReportHeading",
            parent=base_styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=rl["colors"].HexColor("#17324D"),
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": rl["ParagraphStyle"](
            "ReportBody",
            parent=base_styles["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            spaceAfter=5,
        ),
        "small": rl["ParagraphStyle"](
            "ReportSmall",
            parent=base_styles["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=rl["colors"].HexColor("#4C5B66"),
        ),
        "table": rl["ParagraphStyle"](
            "ReportTable",
            parent=base_styles["BodyText"],
            fontName="Helvetica",
            fontSize=7,
            leading=8.5,
        ),
        "table_header": rl["ParagraphStyle"](
            "ReportTableHeader",
            parent=base_styles["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7,
            leading=8.5,
        ),
    }

    story: list[Any] = [
        _paragraph("DHTOL Testbericht", styles["title"], rl["Paragraph"]),
    ]
    folder_label = str(folder_path or run.root_path or "")
    metadata_rows = [
        ["Feld", "Wert"],
        ["Test", run.test_name],
        ["Ordner", folder_label],
        ["Zeitraum", period_label],
        ["Geplante Testzeit", format_report_hours(run.planned_test_seconds)],
        ["Zonen", len(run.zones)],
        ["Boards", len(run.all_boards)],
        ["Nennstrom je Board", f"{run.slot_nenn_strom_a:g} A"],
        ["Ofen-Solltemperatur", f"{run.oven_temp_setpoint_c:g} C"],
    ]
    story.append(
        _table(
            metadata_rows,
            rl["Paragraph"],
            rl["Table"],
            rl["TableStyle"],
            styles,
            rl["colors"],
            col_widths=[4.0 * rl["cm"], 19.5 * rl["cm"]],
        )
    )
    story.append(rl["Spacer"](1, 0.25 * rl["cm"]))

    story.append(_paragraph("Automatische Zusammenfassung", styles["heading"], rl["Paragraph"]))
    for paragraph in build_report_summary(
        run,
        overview_frame,
        period_label,
        glitch_summary,
    ):
        story.append(_paragraph(paragraph, styles["body"], rl["Paragraph"]))

    if engineer_notes.strip():
        story.append(_paragraph("Engineer Notes", styles["heading"], rl["Paragraph"]))
        story.append(_paragraph(engineer_notes.strip(), styles["body"], rl["Paragraph"]))

    story.append(rl["PageBreak"]())
    story.append(_paragraph("Board-Uebersicht", styles["heading"], rl["Paragraph"]))
    overview_rows = _overview_rows(overview_frame)
    if len(overview_rows) > 1:
        story.append(
            _table(
                overview_rows,
                rl["Paragraph"],
                rl["Table"],
                rl["TableStyle"],
                styles,
                rl["colors"],
                col_widths=[
                    0.8 * rl["cm"],
                    1.0 * rl["cm"],
                    1.2 * rl["cm"],
                    3.0 * rl["cm"],
                    1.3 * rl["cm"],
                    2.0 * rl["cm"],
                    2.0 * rl["cm"],
                    1.4 * rl["cm"],
                    2.4 * rl["cm"],
                    2.7 * rl["cm"],
                    1.3 * rl["cm"],
                ][: len(overview_rows[0])],
            )
        )
    else:
        story.append(_paragraph("Keine Board-Daten verfuegbar.", styles["body"], rl["Paragraph"]))

    chart_list = list(charts)
    if chart_list:
        story.append(rl["PageBreak"]())
        story.append(_paragraph("Graphen", styles["heading"], rl["Paragraph"]))
        for index, chart in enumerate(chart_list):
            if index:
                story.append(rl["PageBreak"]())
            story.append(_paragraph(chart.title, styles["heading"], rl["Paragraph"]))
            image_data = chart_to_png_bytes(chart.figure)
            image = rl["Image"](BytesIO(image_data))
            width_ratio = doc.width / image.imageWidth
            height_ratio = (doc.height - 1.6 * rl["cm"]) / image.imageHeight
            ratio = min(width_ratio, height_ratio, 1.0)
            image.drawWidth = image.imageWidth * ratio
            image.drawHeight = image.imageHeight * ratio
            story.append(image)

    try:
        doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    except PdfReportError:
        raise
    except Exception as exc:
        raise PdfReportError(f"PDF konnte nicht erzeugt werden: {exc}") from exc

    return buffer.getvalue()
