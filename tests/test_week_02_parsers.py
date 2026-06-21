from __future__ import annotations

import json
from pathlib import Path

from models.data_models import TempMode, Zone
from parsers.board_data import parse_board_data
from parsers.config_json import parse_config_json
from parsers.mtpx import parse_planned_test_seconds


def test_config_json_parses_ovenplan_and_mv_mode(tmp_path: Path) -> None:
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
                "Testplans": [
                    {"functions": [{"code": "f_MV = true"}]}
                ],
            }
        ),
        encoding="utf-8",
    )

    parsed = parse_config_json(source)

    assert parsed.zone is Zone.A
    assert parsed.temp_mode is TempMode.MV
    assert parsed.ovenplan_entries[0].controller_id == 88
    assert parsed.ovenplan_entries[0].position == 1


def test_config_json_accepts_named_dut(tmp_path: Path) -> None:
    source = tmp_path / "run_A_test.json"
    source.write_text(
        json.dumps(
            {
                "Test Name": "run_A_test",
                "Ovenplan": [
                    {
                        "Zone": "A",
                        "Slot": "2",
                        "DUT": "aa",
                        "HW Target": "target-aa",
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


def test_config_json_returns_warning_for_broken_file(
    tmp_path: Path,
) -> None:
    source = tmp_path / "run_A_test.json"
    source.write_text("{broken", encoding="utf-8")

    parsed = parse_config_json(source)

    assert parsed.ovenplan_entries == []
    assert parsed.warnings


def test_mtpx_parses_safe_stop_time_expression(tmp_path: Path) -> None:
    source = tmp_path / "run.mtpx"
    source.write_text(
        json.dumps(
            {
                "templateValues": [
                    {
                        "templateName": "stop_time",
                        "templateValue": "1001*3600",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert parse_planned_test_seconds(source) == 1001 * 3600


def test_mtpx_rejects_executable_expression(tmp_path: Path) -> None:
    source = tmp_path / "run.mtpx"
    source.write_text(
        json.dumps(
            {
                "templateValues": [
                    {
                        "templateName": "stop_time",
                        "templateValue": "__import__('os').system('echo no')",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert parse_planned_test_seconds(source) is None


def test_board_data_parses_stress_and_latest_hardware(
    tmp_path: Path,
) -> None:
    source = tmp_path / "board.data"
    source.write_text(
        json.dumps(
            {
                "Test Info": {"Cycles": 2, "Seconds": 123.5},
                "HW History": [
                    {
                        "HW Info": {
                            "hostname": "controller-88",
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
    assert metadata.cycles == 2
    assert metadata.hostname == "controller-88"
    assert metadata.hardware_version == "5.0"
    assert metadata.firmware_version == "9.0"
