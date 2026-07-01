from __future__ import annotations

import json
from pathlib import Path

from models.data_models import Board, Zone, ZoneData
from parsers.folder_loader import (
    available_board_dates,
    discover_test_runs,
    folder_revision,
    load_board_date,
    load_testrun,
    load_zone_current,
)


def test_folder_loader_supports_three_zones_and_24_boards(tmp_path: Path) -> None:
    controller_id = 1
    for zone in ("A", "B", "C"):
        test_name = f"run_{zone}_sample_2A_85degree"
        ovenplan = []
        for position in range(1, 9):
            ovenplan.append(
                {
                    "Zone": zone,
                    "Slot": str(position),
                    "DUT": f"{controller_id}_{controller_id * 2 - 1}_{controller_id * 2}",
                    "HW Target": f"target{controller_id:02d}",
                }
            )
            controller_id += 1

        (tmp_path / f"{test_name}.json").write_text(
            json.dumps(
                {
                    "Test Name": test_name,
                    "Ovenplan": ovenplan,
                    "Testplans": [{"functions": [{"code": "f_MV = false"}]}],
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / f"{test_name}.mtpx").write_text(
            json.dumps(
                {
                    "templateValues": [
                        {"templateName": "stop_time", "templateValue": "1000*3600"}
                    ]
                }
            ),
            encoding="utf-8",
        )

    run = load_testrun(tmp_path)

    assert len(run.zones) == 3
    assert [len(zone.boards) for zone in run.zones] == [8, 8, 8]
    assert len(run.all_boards) == 24
    assert [zone.zone.value for zone in run.zones] == ["A", "B", "C"]


def test_multiple_test_names_in_one_folder_are_not_merged(tmp_path: Path) -> None:
    names = [
        "2026-03-03_A_sample_3A15_25degree",
        "2026-03-03_A_sample_3A15_5degree",
    ]
    for test_name in names:
        (tmp_path / f"{test_name}.json").write_text(
            json.dumps(
                {
                    "Test Name": test_name,
                    "Ovenplan": [
                        {
                            "Zone": "A",
                            "Slot": "1",
                            "DUT": "58_1_2",
                            "HW Target": "target58",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / f"{test_name}.mtpx").write_text(
            json.dumps(
                {
                    "templateValues": [
                        {"templateName": "stop_time", "templateValue": "1001*3600"}
                    ]
                }
            ),
            encoding="utf-8",
        )

    (tmp_path / f"{names[0]}.58_1_2.2026-03-05.log").write_text(
        "2026-03-05 00:00:00\t1;2;3;4;5;6;7;8\n",
        encoding="utf-8",
    )

    candidates = discover_test_runs(tmp_path)

    assert len(candidates) == 2
    runs = [load_testrun(tmp_path, candidate.run_id) for candidate in candidates]
    assert [len(run.all_boards) for run in runs] == [1, 1]
    assert {run.oven_temp_setpoint_c for run in runs} == {5.0, 25.0}

    default_run = load_testrun(tmp_path)
    assert default_run.oven_temp_setpoint_c == 25.0
    assert len(default_run.all_boards) == 1


def test_nested_folders_are_discovered_as_separate_runs(tmp_path: Path) -> None:
    nested = tmp_path / "Single"
    nested.mkdir()
    test_name = "2026-03-03_A_sample_3A15_25degree"
    (nested / f"{test_name}.json").write_text(
        json.dumps(
            {
                "Test Name": test_name,
                "Ovenplan": [
                    {
                        "Zone": "A",
                        "Slot": "1",
                        "DUT": "58_1_2",
                        "HW Target": "target58",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    candidates = discover_test_runs(tmp_path)

    assert len(candidates) == 1
    assert candidates[0].relative_folder == "Single"


def test_host_log_current_is_used_for_all_instruments(tmp_path: Path) -> None:
    host_log = tmp_path / "run.2026-03-05.log"
    host_log.write_text(
        "2026-03-05 09:40:36\t"
        "psuV: 240, elV: 320, psuI: 14.6, elI: 10.3, V: 560, I: 24.9\n",
        encoding="utf-8",
    )
    zone = ZoneData(zone=Zone.A, host_log_paths=[host_log])

    psu = load_zone_current(zone, "2026-03-05", "psu")
    el = load_zone_current(zone, "2026-03-05", "el")
    total = load_zone_current(zone, "2026-03-05", "combined")

    assert psu is not None
    assert psu.tolist() == [14.6]
    assert el is not None
    assert el.tolist() == [10.3]
    assert total is not None
    assert total.tolist() == [24.9]


def test_zone_current_is_missing_without_host_log_current(
    tmp_path: Path,
) -> None:
    host_log = tmp_path / "run.2026-03-05.log"
    host_log.write_text(
        "2026-03-05 09:40:36\tTARGET: target58, TIMED OUT on: "
        "2026-03-05 09:40:36, Error occured: OC, Time stressed: "
        "00:00:21, DUT NAME: 58_1_2\n",
        encoding="utf-8",
    )
    zone = ZoneData(zone=Zone.A, host_log_paths=[host_log])

    assert load_zone_current(zone, "2026-03-05", "combined") is None


def test_board_days_are_grouped_but_can_be_filtered(tmp_path: Path) -> None:
    board = Board(
        controller_id=58,
        zone=Zone.A,
        position=1,
        dut_name="58_1_2",
        hw_target="target58",
        nenn_strom_a=3.15,
        log_paths=[],
    )
    for date in ("2026-03-05", "2026-03-06"):
        path = tmp_path / f"run.58_1_2.{date}.log"
        path.write_text(
            f"{date} 00:00:00\t1;2;3;4;5;6;7;8\n",
            encoding="utf-8",
        )
        board.log_paths.append(path)

    assert available_board_dates(board) == ["2026-03-05", "2026-03-06"]
    assert len(load_board_date(board).measurements) == 2
    assert len(load_board_date(board, "2026-03-06").measurements) == 1


def test_testrun_detects_deleted_log_coverage(tmp_path: Path) -> None:
    test_name = "run_A_sample_3A15_25degree"
    dut_name = "58_1_2"
    (tmp_path / f"{test_name}.json").write_text(
        json.dumps(
            {
                "Test Name": test_name,
                "Ovenplan": [
                    {
                        "Zone": "A",
                        "Slot": "1",
                        "DUT": dut_name,
                        "HW Target": "target58",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / f"{test_name}.mtpx").write_text(
        json.dumps(
            {
                "templateValues": [
                    {"templateName": "stop_time", "templateValue": "10*3600"}
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / f"{test_name}.{dut_name}.data").write_text(
        json.dumps({"Test Info": {"Seconds": 8 * 3600}}),
        encoding="utf-8",
    )
    (tmp_path / f"{test_name}.{dut_name}.2026-03-05.log").write_text(
        "2026-03-05 00:00:00\t1;2;3;4;5;6;7;8\n"
        "2026-03-05 06:00:00\t1;2;3;4;5;6;7;8\n",
        encoding="utf-8",
    )

    run = load_testrun(tmp_path)
    board = run.all_boards[0]

    assert board.log_stress_seconds == 8 * 3600
    assert board.available_log_seconds == 6 * 3600
    assert board.log_gap_current_confirmed is False
    assert board.effective_stress_seconds == 8 * 3600
    assert run.nachbelastung_seconds_for(board) == 2 * 3600


def test_deleted_log_coverage_is_confirmed_by_host_current(
    tmp_path: Path,
) -> None:
    test_name = "run_A_sample_2A_25degree"
    dut_name = "58_1_2"
    (tmp_path / f"{test_name}.json").write_text(
        json.dumps(
            {
                "Test Name": test_name,
                "Ovenplan": [
                    {
                        "Zone": "A",
                        "Slot": "1",
                        "DUT": dut_name,
                        "HW Target": "target58",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / f"{test_name}.mtpx").write_text(
        json.dumps(
            {
                "templateValues": [
                    {"templateName": "stop_time", "templateValue": "10*3600"}
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / f"{test_name}.{dut_name}.data").write_text(
        json.dumps({"Test Info": {"Seconds": 8 * 3600}}),
        encoding="utf-8",
    )
    (tmp_path / f"{test_name}.{dut_name}.2026-03-05.log").write_text(
        "2026-03-05 00:00:00\t1;2;3;4;5;6;7;8\n"
        "2026-03-05 06:00:00\t1;2;3;4;5;6;7;8\n",
        encoding="utf-8",
    )
    host_lines = []
    for minute in range(0, 121, 2):
        hour, minute_of_hour = divmod(6 * 60 + minute, 60)
        host_lines.append(
            f"2026-03-05 {hour:02d}:{minute_of_hour:02d}:00\t"
            "psuV: 240, elV: 320, psuI: 1.2, elI: 0.8, "
            "V: 560, I: 2.0\n"
        )
    (tmp_path / f"{test_name}.2026-03-05.log").write_text(
        "".join(host_lines),
        encoding="utf-8",
    )

    run = load_testrun(tmp_path)
    board = run.all_boards[0]

    assert board.log_gap_current_confirmed is True
    assert board.effective_stress_seconds == 8 * 3600
    assert run.nachbelastung_seconds_for(board) == 2 * 3600


def test_named_duts_are_loaded_as_boards(tmp_path: Path) -> None:
    test_name = "run_A_sample_3A15_25degree"
    (tmp_path / f"{test_name}.json").write_text(
        json.dumps(
            {
                "Test Name": test_name,
                "Ovenplan": [
                    {
                        "Zone": "A",
                        "Slot": str(position),
                        "DUT": dut_name,
                        "HW Target": f"target-{dut_name}",
                    }
                    for position, dut_name in enumerate(
                        ("aa", "bb", "cc", "dd"), start=1
                    )
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / f"{test_name}.mtpx").write_text(
        json.dumps(
            {
                "templateValues": [
                    {"templateName": "stop_time", "templateValue": "1001*3600"}
                ]
            }
        ),
        encoding="utf-8",
    )

    candidates = discover_test_runs(tmp_path)
    run = load_testrun(tmp_path, candidates[0].run_id)

    assert candidates[0].board_count == 4
    assert [board.dut_name for board in run.all_boards] == [
        "aa",
        "bb",
        "cc",
        "dd",
    ]
    assert all(board.controller_id is None for board in run.all_boards)


def test_folder_revision_changes_when_log_changes(tmp_path: Path) -> None:
    log_path = tmp_path / "run.2026-03-05.log"
    log_path.write_text("first\n", encoding="utf-8")
    before = folder_revision(tmp_path)

    log_path.write_text("first\nsecond\n", encoding="utf-8")
    after = folder_revision(tmp_path)

    assert before != after


def test_folder_revision_ignores_tdms_files(tmp_path: Path) -> None:
    log_path = tmp_path / "run.2026-03-05.log"
    log_path.write_text("first\n", encoding="utf-8")
    before = folder_revision(tmp_path)

    tdms_path = tmp_path / "run-psu12-2026-03-05.tdms"
    tdms_path.write_text("tdms placeholder\n", encoding="utf-8")
    after = folder_revision(tmp_path)

    assert before == after
