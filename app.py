from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from analysis.fault_detector import faults_from_board_events
from analysis.glitch_detector import (
    detect_temperature_glitches,
    summarize_temperature_log_paths,
)
from analysis.stress_time import (
    calculate_planned_gap,
    confirm_nachbelastung_from_current,
)
from config import LOG_COVERAGE_WARNING_SECONDS
from parsers.folder_loader import (
    available_board_dates,
    discover_test_runs,
    load_board_date,
    load_testrun,
    load_zone_current,
)
from parsers.board_log import parse_board_logs_for_plot
from parsers.tdms_diagnostics import (
    compare_board_log_to_tdms,
    compare_host_current_to_tdms,
)
from parsers.uploaded_archive import UploadedArchiveError, extract_uploaded_zip
from reporting.pdf_report import (
    PdfReportError,
    build_pdf_report,
    build_report_charts,
    pdf_report_filename,
)
from visualization.charts import (
    align_measurements_to_stress_start,
    all_board_current_chart,
    all_board_voltage_chart,
    electrical_chart,
    stress_time_chart,
    zone_current_chart,
)
from visualization.glitch_view import (
    all_board_temperature_chart,
    temperature_glitch_chart,
    temperature_sensor_labels,
)
from visualization.overview import board_overview_frame
from visualization.ttf_plot import ttf_plot


st.set_page_config(page_title="DHTOL Analyzer", page_icon="⚡", layout="wide")


def load_selected_testrun(folder_path: str, run_id: str):
    return load_testrun(folder_path, run_id)


def find_test_candidates(folder_path: str):
    return discover_test_runs(folder_path)


def analyze_board(
    folder_path: str,
    run_id: str,
    dut_name: str,
    date_scope: str,
):
    run = load_testrun(folder_path, run_id)
    board = next(
        (board for board in run.all_boards if board.dut_name == dut_name), None
    )
    if board is None:
        st.error(f"Board nicht gefunden: {dut_name}")
        st.stop()
    date = None if date_scope == "__all__" else date_scope
    parsed = load_board_date(board, date)
    glitches = detect_temperature_glitches(
        parsed.measurements, run.oven_temp_setpoint_c
    )
    faults = faults_from_board_events(parsed.events)
    return parsed, glitches, faults


def scan_glitches(
    folder_path: str,
    run_id: str,
    date_scope: str,
) -> dict[str, dict[str, object]]:
    run = load_testrun(folder_path, run_id)
    summary: dict[str, dict[str, object]] = {}
    for board in run.all_boards:
        result = summarize_temperature_log_paths(
            [
                [
                    str(path)
                    for path in board.log_paths
                    if date_scope in path.name
                ]
            ],
            run.oven_temp_setpoint_c,
        )
        summary[board.dut_name] = {
            "glitch_count": result.glitch_count,
            "t0_sensor_dead": result.t0_sensor_dead,
            "t1_sensor_dead": result.t1_sensor_dead,
        }
    return summary


def analyze_zone_current(
    folder_path: str,
    run_id: str,
    zone_name: str,
    date_scope: str,
    instrument: str,
):
    run = load_testrun(folder_path, run_id)
    zone_data = next(
        (zone for zone in run.zones if zone.zone.value == zone_name), None
    )
    if zone_data is None:
        return None
    date = None if date_scope == "__all__" else date_scope
    return load_zone_current(zone_data, date, instrument)


def analyze_fault_confirmation(
    folder_path: str,
    run_id: str,
    zone_name: str,
    event_time_iso: str,
    logged_seconds: float,
):
    run = load_testrun(folder_path, run_id)
    zone_data = next(
        (zone for zone in run.zones if zone.zone.value == zone_name), None
    )
    if zone_data is None:
        st.error(f"Zone nicht gefunden: {zone_name}")
        st.stop()
    event_time = pd.Timestamp(event_time_iso).to_pydatetime()
    current = load_zone_current(
        zone_data, event_time.date().isoformat(), "combined"
    )
    result = calculate_planned_gap(run.planned_test_seconds, logged_seconds)
    return confirm_nachbelastung_from_current(result, event_time, current)


def format_hours(seconds: float) -> str:
    return f"{seconds / 3600:,.2f} h".replace(",", "X").replace(".", ",").replace("X", ".")


def fault_row(board, fault) -> dict[str, object]:
    """One fault rendered as a table row, shared by the board-detail and all-boards views."""
    return {
        "Zone": board.zone.value,
        "Position": board.position,
        "Controller": board.controller_id if board.controller_id is not None else "—",
        "DUT / Board": board.dut_name,
        "Zeit": fault.timestamp,
        "Fehlertyp": fault.fault_type.value,
    }


def _path_signature(path: Path) -> tuple[str, int, int]:
    try:
        stat = path.stat()
    except OSError:
        return (str(path), -1, -1)
    return (str(path), stat.st_size, stat.st_mtime_ns)


@st.cache_data(show_spinner=False)
def compare_host_current_to_tdms_cached(
    host_log_signature: tuple[str, int, int],
    psu_tdms_signature: tuple[str, int, int],
    el_tdms_signature: tuple[str, int, int],
) -> pd.DataFrame:
    return compare_host_current_to_tdms(
        host_log_signature[0],
        psu_tdms_signature[0],
        el_tdms_signature[0],
    )


@st.cache_data(show_spinner=False)
def compare_board_log_to_tdms_cached(
    board_log_signature: tuple[str, int, int],
    mqtt_tdms_signature: tuple[str, int, int],
    hw_target: str,
) -> pd.DataFrame:
    return compare_board_log_to_tdms(
        board_log_signature[0],
        mqtt_tdms_signature[0],
        hw_target,
    )


def _date_log_path(paths: list[Path], date: str) -> Path | None:
    suffix = f".{date}.log"
    return next((path for path in paths if path.name.endswith(suffix)), None)


def _tdms_path_from_host_log(host_log_path: Path, date: str, marker: str) -> Path:
    suffix = f".{date}.log"
    test_name = host_log_path.name[: -len(suffix)]
    return host_log_path.with_name(f"{test_name}-{marker}-{date}.tdms")


def _tdms_path_from_board_log(
    board_log_path: Path, dut_name: str, date: str
) -> Path:
    suffix = f".{dut_name}.{date}.log"
    test_name = board_log_path.name[: -len(suffix)]
    return board_log_path.with_name(f"{test_name}-mqtt-{date}.tdms")


def _render_tdms_comparison(frame: pd.DataFrame) -> None:
    if frame.empty:
        st.warning("Keine TDMS-Vergleichsdaten.")
        return
    if frame["Status"].eq("OK").all():
        st.success("LOG und TDMS stimmen innerhalb der Toleranzen überein.")
    else:
        st.warning("LOG und TDMS weichen mindestens bei einem Signal ab.")
    st.dataframe(
        frame,
        hide_index=True,
        use_container_width=True,
        column_config={
            "LOG Median": st.column_config.NumberColumn(format="%.6f"),
            "TDMS Median": st.column_config.NumberColumn(format="%.6f"),
            "Mean Abs Diff": st.column_config.NumberColumn(format="%.6f"),
            "Max Abs Diff": st.column_config.NumberColumn(format="%.6f"),
        },
    )


st.title("DHTOL Analyzer")
st.caption("Stresszeit, Nachbelastung, Fehler und Temperatur-Glitches")

source_mode = st.sidebar.radio(
    "Datenquelle",
    ["Lokaler Ordner", "ZIP hochladen"],
    help=(
        "Lokal: Pfad auf diesem Rechner. Cloud: ZIP-Datei mit Testlauf-Daten "
        "im Browser hochladen."
    ),
)

if source_mode == "ZIP hochladen":
    uploaded_archive = st.sidebar.file_uploader(
        "Testlauf-ZIP",
        type=["zip"],
        help="ZIP mit JSON, MTPX, DATA, Board-Logs, Host-Logs und optional TDMS.",
    )
    if uploaded_archive is None:
        st.info("Testlauf-ZIP hochladen.")
        st.stop()
    try:
        folder = extract_uploaded_zip(
            uploaded_archive.getvalue(),
            uploaded_archive.name,
        )
    except UploadedArchiveError as error:
        st.error(str(error))
        st.stop()
else:
    folder_path = st.sidebar.text_input(
        "Testlauf-Ordner",
        value="",
        placeholder="/Users/name/Desktop/Testlauf",
    )
    if not folder_path.strip():
        st.info("Testlauf-Ordner eingeben.")
        st.stop()

    folder = Path(folder_path.strip()).expanduser()
    if not folder.is_dir():
        st.error("Ordner nicht gefunden.")
        st.stop()

resolved_folder = str(folder.resolve())
candidates = find_test_candidates(resolved_folder)
if not candidates:
    st.error("Keine Testläufe gefunden.")
    st.stop()

selected_run_id = candidates[0].run_id
run = load_selected_testrun(resolved_folder, selected_run_id)
if not run.all_boards:
    st.error("Keine Boards gefunden.")
    for warning in run.warnings:
        st.warning(warning)
    st.stop()

columns = st.columns(4)
columns[0].metric("Zonen", len(run.zones))
columns[1].metric("Boards", len(run.all_boards))
columns[2].metric("Geplante Testzeit", format_hours(run.planned_test_seconds))
columns[3].metric("Nennstrom je Board", f"{run.slot_nenn_strom_a:g} A")

for warning in run.warnings:
    st.warning(warning)

boards_with_missing_logs = [
    board
    for board in run.all_boards
    if board.missing_log_seconds > LOG_COVERAGE_WARNING_SECONDS
]
if boards_with_missing_logs:
    missing_labels = [
        (
            f"Zone {board.zone.value}, Position {board.position}, "
            f"{board.dut_name}: "
            f"{board.missing_log_seconds / 3600:.2f} h fehlen – "
            + (
                "Host-/Zonenstrom vorhanden; Nachbelastung wird mit DATA berechnet"
                if board.log_gap_current_confirmed is True
                else "Nachbelastung wird trotzdem mit DATA berechnet"
            )
        )
        for board in boards_with_missing_logs
    ]
    st.warning(
        "Abweichung zwischen DATA und Board-Logs erkannt. "
        + " · ".join(missing_labels)
    )

all_dates = sorted(
    {date for board in run.all_boards for date in available_board_dates(board)}
)
if not all_dates:
    st.warning("Testkonfiguration gefunden, aber keine Board-Tageslogs vorhanden.")
    st.stop()

period_mode = st.sidebar.radio(
    "Zeitraum",
    ["Alle Tage", "Bestimmter Tag"],
    help=(
        "Alle täglichen Logdateien eines Testlaufs werden automatisch gruppiert. "
        "Wähle „Bestimmter Tag“, wenn du gezielt einen Tag untersuchen möchtest."
    ),
)

if period_mode == "Alle Tage":
    date_scope = "__all__"
    day_file_label = "Tagesdatei" if len(all_dates) == 1 else "Tagesdateien"
    period_label = f"Alle Tage ({len(all_dates)} {day_file_label})"
else:
    date_search = st.sidebar.text_input(
        "Datum suchen",
        placeholder="z. B. 2026-03-08",
        help="Filtert vorhandene Tagesdateien nach vollständigem oder teilweisem Datum.",
    ).strip()
    filtered_dates = [
        date for date in all_dates if not date_search or date_search in date
    ]
    if not filtered_dates:
        st.sidebar.error("Kein passendes Datum gefunden.")
        st.stop()
    date_scope = st.sidebar.selectbox(
        "Analyse-Tag",
        filtered_dates,
        index=max(0, len(filtered_dates) - 1),
    )
    period_label = date_scope

glitch_analysis_date = (
    all_dates[-1] if date_scope == "__all__" else date_scope
)
with st.spinner("Temperatur-Glitches werden automatisch analysiert …"):
    glitch_summary = scan_glitches(
        resolved_folder,
        selected_run_id,
        glitch_analysis_date,
    )

overview_tab, board_tab, current_tab, fault_tab = st.tabs(
    ["Übersicht", "Board-Detail", "Zonenstrom", "Fehler / TTF"]
)

with overview_tab:
    st.subheader(f"Board-Status · {period_label}")
    st.caption(
        f"Temperatur-Glitch-Analyse automatisch · Prüftag: {glitch_analysis_date}"
    )
    if boards_with_missing_logs:
        affected_boards = [
            (
                f"Zone {board.zone.value} · Position {board.position} · "
                f"{board.dut_name}: {board.missing_log_seconds / 3600:.2f} h "
                "weniger Board-Logzeit als DATA"
                + (
                    " · Nachbelastung wird mit DATA berechnet"
                    if board.log_gap_current_confirmed is True
                    else " · Board-Log nur Kontrolle"
                )
            )
            for board in boards_with_missing_logs
        ]
        st.warning(
            "⚠ Betroffene Boards: " + " | ".join(affected_boards)
        )
    overview = board_overview_frame(run, glitch_summary)
    st.dataframe(
        overview,
        use_container_width=True,
        hide_index=True,
        column_config={
            "DATA-Stresszeit [h]": st.column_config.NumberColumn(
                format="%.2f"
            ),
            "Board-Log-Stresszeit [h]": st.column_config.NumberColumn(
                format="%.2f"
            ),
            "Abweichung DATA - Board-Logs [h]": st.column_config.NumberColumn(
                format="%.2f"
            ),
            "Nachbelastung laut DATA [h]": st.column_config.NumberColumn(
                format="%.2f"
            ),
            "Nachbelastung laut Board-Log [h]": st.column_config.NumberColumn(
                format="%.2f"
            ),
        },
    )
    st.plotly_chart(stress_time_chart(run), use_container_width=True)
    st.info(
        "Nachbelastung wird mit DATA-Stresszeit pro DUT berechnet. "
        "Board-Log-Zeit wird zusätzlich angezeigt, um Kommunikations- oder Logging-Lücken zu erkennen. "
        "Host-/Zonenstrom ist nur eine Plausibilitätsprüfung."
    )
    st.subheader("PDF-Testbericht")
    engineer_notes = st.text_area(
        "Engineer Notes",
        value="",
        placeholder="Optionale Bemerkungen fuer den Bericht",
        key="pdf_engineer_notes",
    )
    report_state_key = f"pdf_report_{selected_run_id}_{date_scope}"
    if st.button("PDF-Bericht erstellen", key="build_pdf_report"):
        try:
            with st.spinner("PDF-Bericht wird erstellt ..."):
                report_charts = build_report_charts(run, date_scope)
                report_bytes = build_pdf_report(
                    run=run,
                    overview_frame=overview,
                    period_label=period_label,
                    glitch_summary=glitch_summary,
                    engineer_notes=engineer_notes,
                    charts=report_charts,
                    folder_path=resolved_folder,
                )
            st.session_state[report_state_key] = {
                "bytes": report_bytes,
                "filename": pdf_report_filename(run.test_name, date_scope),
            }
            st.success("PDF-Bericht bereit.")
        except PdfReportError as error:
            st.error(str(error))

    report_payload = st.session_state.get(report_state_key)
    if report_payload:
        st.download_button(
            "PDF-Bericht herunterladen",
            data=report_payload["bytes"],
            file_name=report_payload["filename"],
            mime="application/pdf",
            key=f"download_{report_state_key}",
        )

with board_tab:
    board_labels = {"Alle Boards": None}
    for board in run.all_boards:
        glitch = glitch_summary.get(board.dut_name, {})
        has_temperature_fault = bool(
            glitch.get("glitch_count", 0)
            or glitch.get("t0_sensor_dead", False)
            or glitch.get("t1_sensor_dead", False)
        )
        if board.faults:
            status_label = "🔴 Fehler"
        elif has_temperature_fault:
            status_label = "🟡 Temperaturfehler"
        else:
            status_label = "🟢 OK"
        board_labels[
            f"{status_label} · Zone {board.zone.value} · "
            f"Position {board.position} · {board.dut_name}"
        ] = board
    selected_label = st.selectbox(
        "Board",
        list(board_labels),
        index=1 if len(board_labels) > 1 else 0,
    )
    selected_board = board_labels[selected_label]
    if selected_board is None:
        st.caption(
            f"Alle Boards gleichzeitig · Zeitraum: {period_label}"
        )
        if date_scope == "__all__":
            st.info(
                "Alle Tageslogs pro Board automatisch gruppiert. "
                "Kurven auf jeweiligen Stressbeginn ausgerichtet."
            )

        all_board_results = []
        all_temperature_results = []
        all_fault_rows: list[dict[str, object]] = []
        with st.spinner("Alle Boards werden geladen …"):
            for board in run.all_boards:
                selected_paths = (
                    board.log_paths
                    if date_scope == "__all__"
                    else [
                        path
                        for path in board.log_paths
                        if date_scope in path.name
                    ]
                )
                parsed = parse_board_logs_for_plot(selected_paths)
                aligned_measurements = align_measurements_to_stress_start(
                    parsed.measurements
                )
                faults = faults_from_board_events(parsed.events)
                board_label = (
                    f"{board.zone.value}{board.position} · {board.dut_name}"
                )
                all_board_results.append(
                    (board_label, aligned_measurements, faults)
                )
                all_temperature_results.append(
                    (
                        board_label,
                        aligned_measurements,
                        board.temp_mode,
                        faults,
                    )
                )
                for fault in faults:
                    all_fault_rows.append(fault_row(board, fault))

        st.plotly_chart(
            all_board_temperature_chart(all_temperature_results),
            use_container_width=True,
        )
        st.plotly_chart(
            all_board_current_chart(all_board_results),
            use_container_width=True,
        )
        st.plotly_chart(
            all_board_voltage_chart(all_board_results),
            use_container_width=True,
        )
        if all_fault_rows:
            st.subheader("Erkannte Fehler · Alle Boards")
            st.dataframe(
                pd.DataFrame(all_fault_rows),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.success("Keine Board-Fehler im gewählten Zeitraum erkannt.")
    else:
        selected_dates = available_board_dates(selected_board)
        st.caption(
            f"Zeitraum: {period_label} · "
            f"verfügbare Board-Tage: {len(selected_dates)}"
        )
        if st.button(
            "TDMS gegen Board-Log prüfen",
            key=f"tdms_board_{selected_board.dut_name}_{date_scope}",
        ):
            if date_scope == "__all__":
                st.warning("Bitte bestimmten Tag auswählen.")
            else:
                board_log_path = _date_log_path(selected_board.log_paths, date_scope)
                if board_log_path is None:
                    st.warning("Kein Board-Log für diesen Tag gefunden.")
                else:
                    mqtt_tdms_path = _tdms_path_from_board_log(
                        board_log_path, selected_board.dut_name, date_scope
                    )
                    with st.spinner("TDMS wird mit Board-Log verglichen …"):
                        tdms_result = compare_board_log_to_tdms_cached(
                            _path_signature(board_log_path),
                            _path_signature(mqtt_tdms_path),
                            selected_board.hw_target,
                        )
                    _render_tdms_comparison(tdms_result)
        if st.checkbox(
            "Board-Messdaten laden",
            key="load_board_detail",
            help="Lädt alle gruppierten Tage oder nur den ausgewählten Tag.",
        ):
            parsed, glitches, detected_faults = analyze_board(
                resolved_folder,
                selected_run_id,
                selected_board.dut_name,
                date_scope,
            )
            sensor_labels = temperature_sensor_labels(selected_board.temp_mode)

            detail_columns = st.columns(5)
            detail_columns[0].metric(
                "Messwerte", f"{len(parsed.measurements):,}".replace(",", ".")
            )
            detail_columns[1].metric(
                f"{sensor_labels['t0']} · Glitches",
                int(glitches.measurements["t0_glitch"].sum()),
            )
            detail_columns[2].metric(
                f"{sensor_labels['t1']} · Glitches",
                int(glitches.measurements["t1_glitch"].sum()),
            )
            detail_columns[3].metric(
                f"{sensor_labels['t0']} · Status",
                "Defekt" if glitches.t0_sensor_dead else "OK",
            )
            detail_columns[4].metric(
                f"{sensor_labels['t1']} · Status",
                "Defekt" if glitches.t1_sensor_dead else "OK",
            )

            if selected_board.temp_mode.value == "HVoltage":
                st.caption(
                    "HV-Betrieb: T0 = Low-Side-Schalter-Temperatur, "
                    "T1 = High-Side-Schalter-Temperatur."
                )
            else:
                st.caption(
                    "MV-Betrieb: T0 = Low-Side-Schalter-Temperatur, "
                    "T1 = DUT-Board-Temperatur. Keine High-Side-Temperatur."
                )

            fault_board_label = (
                f"Zone {selected_board.zone.value} · "
                f"Position {selected_board.position} · "
                f"{selected_board.dut_name}"
            )
            st.plotly_chart(
                temperature_glitch_chart(
                    glitches.measurements,
                    selected_board.temp_mode,
                    detected_faults,
                    fault_board_label,
                ),
                use_container_width=True,
            )
            if any(
                fault.fault_type.value in {"OC", "OV", "GERR", "Network"}
                for fault in detected_faults
            ):
                st.info(
                    "Elektrischer Fehler: roter Bereich und rotes X zeigen "
                    "Fehlerzeit und nächstliegenden Messwert."
                )
            st.plotly_chart(
                electrical_chart(
                    parsed.measurements,
                    detected_faults,
                    fault_board_label,
                ),
                use_container_width=True,
            )

            if detected_faults:
                st.subheader(
                    f"Erkannte Fehler · Zone {selected_board.zone.value} · "
                    f"Position {selected_board.position} · "
                    f"{selected_board.dut_name}"
                )
                st.dataframe(
                    pd.DataFrame(
                        [fault_row(selected_board, fault) for fault in detected_faults]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )

with current_tab:
    zone_names = [zone.zone.value for zone in run.zones]
    selected_zone = st.selectbox("Zone", zone_names)
    selected_zone_data = next(
        (zone for zone in run.zones if zone.zone.value == selected_zone), None
    )
    instrument = st.radio(
        "Instrument", ["PSU + EL", "PSU", "EL"], horizontal=True
    )
    if st.button(
        "TDMS gegen Host-Log prüfen",
        key=f"tdms_zone_{selected_zone}_{date_scope}",
    ):
        if date_scope == "__all__":
            st.warning("Bitte bestimmten Tag auswählen.")
        elif selected_zone_data is None:
            st.warning("Zone nicht gefunden.")
        else:
            host_log_path = _date_log_path(selected_zone_data.host_log_paths, date_scope)
            if host_log_path is None:
                st.warning("Kein Host-Log für diesen Tag gefunden.")
            else:
                psu_tdms_path = _tdms_path_from_host_log(
                    host_log_path, date_scope, "psu12"
                )
                el_tdms_path = _tdms_path_from_host_log(
                    host_log_path, date_scope, "el12"
                )
                with st.spinner("TDMS wird mit Host-Log verglichen …"):
                    tdms_result = compare_host_current_to_tdms_cached(
                        _path_signature(host_log_path),
                        _path_signature(psu_tdms_path),
                        _path_signature(el_tdms_path),
                    )
                _render_tdms_comparison(tdms_result)
    if st.checkbox(
        "Zonenstrom laden",
        key="load_zone_current",
        help="Lädt Host-LOG-Strom für alle gruppierten Tage oder den ausgewählten Tag.",
    ):
        current = analyze_zone_current(
            resolved_folder,
            selected_run_id,
            selected_zone,
            date_scope,
            "combined" if instrument == "PSU + EL" else instrument.lower(),
        )
        if current is None or current.empty:
            st.warning("Keine Stromdaten für Auswahl.")
        else:
            st.metric("Median Gesamtstrom", f"{current.median():.3f} A")
            st.plotly_chart(
                zone_current_chart(current, f"{instrument} Zone {selected_zone}"),
                use_container_width=True,
            )

with fault_tab:
    fault_rows: list[dict[str, object]] = []
    for board in run.all_boards:
        for fault_index, fault in enumerate(board.faults):
            options = ["offen", "echt", "fake"]
            current_choice = (
                "echt"
                if fault.is_real is True
                else "fake"
                if fault.is_real is False
                else "offen"
            )
            if fault.fault_type.value == "Network":
                decision = current_choice
                decision_source = "App/Stromprüfung"
            else:
                decision = st.selectbox(
                    f"{board.dut_name} · {fault.fault_type.value} · {fault.timestamp}",
                    options,
                    index=options.index(current_choice),
                    key=f"fault_{board.dut_name}_{fault_index}",
                )
                decision_source = "Engineer"

            fault.is_real = (
                True if decision == "echt" else False if decision == "fake" else None
            )
            fault.decided_by = (
                "engineer"
                if decision_source == "Engineer" and decision != "offen"
                else "app"
                if decision_source != "Engineer" and decision != "offen"
                else "pending"
            )
            confirmation = analyze_fault_confirmation(
                resolved_folder,
                selected_run_id,
                board.zone.value,
                fault.timestamp.isoformat(),
                board.log_stress_seconds,
            )
            fault_rows.append(
                {
                    "Zone": board.zone.value,
                    "Position": board.position,
                    "DUT": board.dut_name,
                    "Zeit": fault.timestamp,
                    "Fehler": fault.fault_type.value,
                    "Entscheidung": decision,
                    "Entschieden durch": decision_source,
                    "Stromprüfung": confirmation.reason,
                    "Bestätigte Nachbelastung [s]": (
                        confirmation.confirmed_nachbelastung_seconds
                    ),
                }
            )
    if fault_rows:
        st.dataframe(pd.DataFrame(fault_rows), hide_index=True, use_container_width=True)
        st.plotly_chart(ttf_plot(run), use_container_width=True)
    else:
        st.success("Keine Timeout-Zusammenfassungen im Host-Log gefunden.")
