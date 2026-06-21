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


def test_host_log_current_is_used_when_tdms_is_missing(tmp_path: Path) -> None:
    host_log = tmp_path / "run.2026-03-05.log"
    host_log.write_text(
        "2026-03-05 09:40:36\t"
        "psuV: 240, elV: 320, psuI: 14.6, elI: 10.3, V: 560, I: 24.9\n",
        encoding="utf-8",
    )
    zone = ZoneData(zone=Zone.A, host_log_paths=[host_log])

    total = load_zone_current(zone, "2026-03-05", "combined")

    assert total is not None
    assert total.tolist() == [24.9]


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
