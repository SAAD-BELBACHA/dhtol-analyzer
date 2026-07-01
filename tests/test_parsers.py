from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from models.data_models import FaultType, TempMode, Zone
from parsers.board_data import parse_board_data
from parsers.board_log import (
    available_log_seconds,
    measurement_time_bounds,
    parse_board_log,
    parse_board_logs_for_plot,
)
from parsers.config_json import parse_config_json
from parsers.mtpx import parse_planned_test_seconds


def test_config_json_parses_ovenplan(tmp_path: Path) -> None:
    source = tmp_path / "run_A_test.json"
    source.write_text(
        json.dumps(
            {
                "Test Name": "run_A_test",
                "Ovenplan": [
                    {
                        "Zone": "A",
                        "Slot": "1",
                        "DUT": "88_1_2",
                        "HW Target": "abc123",
                    }
                ],
                "Testplans": [{"functions": [{"code": "f_MV = true"}]}],
            }
        ),
        encoding="utf-8",
    )

    parsed = parse_config_json(source)

    assert parsed.zone is Zone.A
    assert parsed.temp_mode is TempMode.MV
    assert parsed.ovenplan_entries[0].controller_id == 88


def test_config_json_accepts_named_duts_without_controller_id(
    tmp_path: Path,
) -> None:
    source = tmp_path / "run_A_test.json"
    source.write_text(
        json.dumps(
            {
                "Test Name": "run_A_test",
                "Ovenplan": [
                    {
                        "Zone": "A",
                        "Slot": "1",
                        "DUT": "aa",
                        "HW Target": "abc123",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    parsed = parse_config_json(source)

    assert not parsed.warnings
    assert parsed.ovenplan_entries[0].dut_name == "aa"
    assert parsed.ovenplan_entries[0].controller_id is None


def test_mtpx_parses_safe_stop_time_expression(tmp_path: Path) -> None:
    source = tmp_path / "run.mtpx"
    source.write_text(
        json.dumps(
            {
                "templateValues": [
                    {"templateName": "stop_time", "templateValue": "10*3600"}
                ]
            }
        ),
        encoding="utf-8",
    )

    assert parse_planned_test_seconds(source) == 36_000


def test_board_data_parses_stress_time_and_firmware_only(tmp_path: Path) -> None:
    source = tmp_path / "board.data"
    source.write_text(
        json.dumps(
            {
                "Test Info": {"Cycles": 2, "Seconds": 123.5},
                "HW History": [
                    {
                        "HW Info": {
                            "hostname": "abc",
                            "IP": "1.2.3.4",
                            "MAC": "00-00",
                            "version": {"hw": "5.0", "fw": "9.0"},
                        }
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    metadata = parse_board_data(source)

    assert metadata is not None
    assert metadata.log_stress_seconds == 123.5
    assert metadata.firmware_version == "9.0"
    assert not hasattr(metadata, "cycles")
    assert not hasattr(metadata, "hostname")
    assert not hasattr(metadata, "ip_address")
    assert not hasattr(metadata, "mac_address")
    assert not hasattr(metadata, "hardware_version")


def test_board_log_skips_broken_rows(tmp_path: Path) -> None:
    source = tmp_path / "board.log"
    source.write_text(
        "2026-01-01 00:00:00\t1;2;3;4;5;6;7;8\n"
        "broken line\n"
        "2026-01-01 00:00:01\tOC err\n",
        encoding="utf-8",
    )

    parsed = parse_board_log(source)

    assert len(parsed.measurements) == 1
    assert len(parsed.events) == 1
    assert parsed.skipped_lines == 1


def test_available_log_seconds_uses_real_file_coverage(
    tmp_path: Path,
) -> None:
    first = tmp_path / "board.2026-01-01.log"
    first.write_text(
        "2026-01-01 00:00:00\t1;2;3;4;5;6;7;8\n"
        "2026-01-01 01:00:00\t1;2;3;4;5;6;7;8\n",
        encoding="utf-8",
    )
    second = tmp_path / "board.2026-01-02.log"
    second.write_text(
        "2026-01-02 00:00:00\t1;2;3;4;5;6;7;8\n"
        "2026-01-02 02:00:00\t1;2;3;4;5;6;7;8\n"
        "2026-01-02 02:00:01\tOC err\n",
        encoding="utf-8",
    )

    assert measurement_time_bounds(first) == (
        datetime(2026, 1, 1, 0, 0),
        datetime(2026, 1, 1, 1, 0),
    )
    assert available_log_seconds([first, second]) == 3 * 3600


def test_board_plot_logs_group_multiple_days_and_keep_events(
    tmp_path: Path,
) -> None:
    paths = []
    for day in (1, 2):
        source = tmp_path / f"board.2026-01-0{day}.log"
        lines = [
            (
                f"2026-01-0{day} 00:00:{second:02d}\t"
                "240;2;3;560;559;1;85;84\n"
            )
            for second in range(20)
        ]
        if day == 2:
            lines.append("2026-01-02 00:01:00\tOC err\n")
        source.write_text("".join(lines), encoding="utf-8")
        paths.append(source)

    parsed = parse_board_logs_for_plot(paths, max_points=12)

    assert len(parsed.measurements) <= 13
    assert parsed.measurements["timestamp"].dt.day.min() == 1
    assert parsed.measurements["timestamp"].dt.day.max() == 2
    assert len(parsed.events) == 1
    assert parsed.events[0].fault_type is FaultType.OC
