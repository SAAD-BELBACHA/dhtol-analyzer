from datetime import datetime

import pandas as pd

from models.data_models import Fault, FaultType
from models.data_models import TempMode
from visualization.charts import (
    align_measurements_to_stress_start,
    all_board_current_chart,
    all_board_voltage_chart,
    electrical_chart,
)
from visualization.overview import board_overview_frame
from visualization.glitch_view import (
    all_board_temperature_chart,
    temperature_sensor_labels,
    temperature_glitch_chart,
)


def test_hv_temperature_labels_use_both_switches() -> None:
    labels = temperature_sensor_labels(TempMode.HV)

    assert labels["t0"] == "T0 · Low-Side-Schalter"
    assert labels["t1"] == "T1 · High-Side-Schalter"


def test_mv_temperature_labels_replace_high_side_with_dut_board() -> None:
    labels = temperature_sensor_labels(TempMode.MV)

    assert labels["t0"] == "T0 · Low-Side-Schalter"
    assert labels["t1"] == "T1 · DUT-Board"


def test_oc_fault_is_only_added_to_electrical_current_chart() -> None:
    timestamp = datetime(2026, 3, 5, 9, 40, 37)
    measurements = pd.DataFrame(
        {
            "timestamp": [timestamp],
            "t0": [50.0],
            "t1": [40.0],
            "current": [3.0],
            "v_in": [240.0],
            "vout_dut": [560.0],
        }
    )
    fault = Fault(FaultType.OC, timestamp)

    temperature = temperature_glitch_chart(
        measurements,
        TempMode.HV,
        [fault],
        "Zone A · Position 1 · 58_1_2",
    )
    electrical = electrical_chart(
        measurements,
        [fault],
        "Zone A · Position 1 · 58_1_2",
    )

    expected = "⚠ OC · Zone A · Position 1 · 58_1_2"
    assert not temperature.layout.annotations
    assert not temperature.layout.shapes
    fault_annotations = [
        annotation.text
        for annotation in electrical.layout.annotations
        if str(annotation.text).startswith("⚠")
    ]
    assert fault_annotations == [expected]
    assert len(electrical.layout.shapes) == 1
    assert electrical.layout.yaxis.title.text == "A"
    assert electrical.layout.yaxis2.title.text == "V"
    assert electrical.layout.yaxis3.title.text == "V"


def test_ot_fault_is_only_added_to_temperature_chart() -> None:
    timestamp = datetime(2026, 3, 5, 9, 40, 37)
    measurements = pd.DataFrame(
        {
            "timestamp": [timestamp],
            "t0": [50.0],
            "t1": [40.0],
            "current": [3.0],
            "v_in": [240.0],
            "vout_dut": [560.0],
        }
    )
    fault = Fault(FaultType.OT, timestamp)

    temperature = temperature_glitch_chart(
        measurements, TempMode.HV, [fault]
    )
    electrical = electrical_chart(measurements, [fault])

    assert temperature.layout.annotations[0].text == "⚠ OT"
    assert len(temperature.layout.shapes) == 1
    assert not any(
        str(annotation.text).startswith("⚠")
        for annotation in electrical.layout.annotations
    )
    assert not electrical.layout.shapes


def test_all_board_charts_show_each_board() -> None:
    timestamp = datetime(2026, 3, 5, 9, 40, 37)
    first = pd.DataFrame(
        {
            "timestamp": [timestamp],
            "t0": [50.0],
            "t1": [40.0],
            "current": [3.0],
            "v_in": [240.0],
            "vout_dut": [560.0],
        }
    )
    second = pd.DataFrame(
        {
            "timestamp": [timestamp],
            "t0": [55.0],
            "t1": [45.0],
            "current": [2.5],
            "v_in": [241.0],
            "vout_dut": [559.0],
        }
    )
    fault = Fault(FaultType.OC, timestamp)

    temperatures = all_board_temperature_chart(
        [
            ("A1 · board-1", first, TempMode.HV, [fault]),
            ("A2 · board-2", second, TempMode.HV, []),
        ]
    )
    currents = all_board_current_chart(
        [
            ("A1 · board-1", first, [fault]),
            ("A2 · board-2", second, []),
        ]
    )
    voltages = all_board_voltage_chart(
        [
            ("A1 · board-1", first, [fault]),
            ("A2 · board-2", second, []),
        ]
    )

    assert len(temperatures.data) == 4
    assert any(trace.name == "A1 · board-1" for trace in currents.data)
    assert any(trace.name == "A2 · board-2" for trace in currents.data)
    assert any(trace.name == "OC · A1 · board-1" for trace in currents.data)
    assert len(voltages.data) == 4
    assert voltages.layout.yaxis.title.text == "V"
    assert voltages.layout.yaxis2.title.text == "V"


def test_all_board_voltage_chart_marks_ov_fault() -> None:
    timestamp = datetime(2026, 3, 5, 9, 40, 37)
    measurements = pd.DataFrame(
        {
            "timestamp": [timestamp],
            "v_in": [240.0],
            "vout_dut": [560.0],
        }
    )

    figure = all_board_voltage_chart(
        [
            (
                "A1 · board-1",
                measurements,
                [Fault(FaultType.OV, timestamp)],
            )
        ]
    )

    assert sum(trace.name == "OV · A1 · board-1" for trace in figure.data) == 2


def test_board_comparison_aligns_on_stress_start() -> None:
    start = datetime(2026, 3, 5, 9, 30)
    measurements = pd.DataFrame(
        {
            "timestamp": [
                start,
                start.replace(minute=31),
                start.replace(minute=32),
            ],
            "v_in": [0.0, 240.0, 240.0],
            "current": [0.0, 2.0, 2.0],
        }
    )

    aligned = align_measurements_to_stress_start(measurements)

    assert aligned["elapsed_hours"].tolist() == [
        -1 / 60,
        0.0,
        1 / 60,
    ]


def test_overview_uses_data_for_nachbelastung_and_shows_board_log_gap() -> None:
    from models.data_models import Board, TestRun, Zone, ZoneData

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
    run = TestRun(
        test_name="run",
        planned_test_seconds=10 * 3600,
        oven_temp_setpoint_c=25.0,
        slot_nenn_strom_a=2.0,
        zones=[ZoneData(zone=Zone.A, boards=[board])],
    )

    row = board_overview_frame(run).iloc[0]

    assert row["DATA-Stresszeit [h]"] == 8.0
    assert row["Board-Log-Stresszeit [h]"] == 6.0
    assert row["Abweichung DATA - Board-Logs [h]"] == 2.0
    assert row["Strombestätigung"] == "Nicht bestätigt"
    assert row["Hinweis"] == "⚠ 2.00 h weniger Board-Logzeit als DATA · Strom nicht bestätigt"
    assert row["Nachbelastung laut DATA [h]"] == 2.0
    assert row["Nachbelastung laut Board-Log [h]"] == 4.0
    assert row["Status"] == "Gelb"


def test_overview_keeps_data_nachbelastung_when_current_confirms_gap() -> None:
    from models.data_models import Board, TestRun, Zone, ZoneData

    board = Board(
        controller_id=58,
        zone=Zone.A,
        position=1,
        dut_name="58_1_2",
        hw_target="target58",
        nenn_strom_a=2.0,
        available_log_seconds=6 * 3600,
        log_stress_seconds=8 * 3600,
        log_gap_current_confirmed=True,
    )
    run = TestRun(
        test_name="run",
        planned_test_seconds=10 * 3600,
        oven_temp_setpoint_c=25.0,
        slot_nenn_strom_a=2.0,
        zones=[ZoneData(zone=Zone.A, boards=[board])],
    )

    row = board_overview_frame(run).iloc[0]

    assert row["DATA-Stresszeit [h]"] == 8.0
    assert row["Board-Log-Stresszeit [h]"] == 6.0
    assert row["Strombestätigung"] == "Bestätigt"
    assert row["Hinweis"] == "⚠ 2.00 h weniger Board-Logzeit als DATA · Nachbelastung mit DATA"
    assert row["Nachbelastung laut DATA [h]"] == 2.0
    assert row["Nachbelastung laut Board-Log [h]"] == 4.0
    assert row["Status"] == "Gelb"
