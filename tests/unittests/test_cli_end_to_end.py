"""End-to-end CLI runs through ``python -m guiskindose`` with bundled example inputs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from guiskindose import (
    get_path_to_example_kerma_meter_file,
    get_path_to_example_rdsr_files,
    get_path_to_example_tabular_files,
    load_settings_example_json,
)

_RDSR = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"
_OLDER_BIPLANE = get_path_to_example_tabular_files() / "radimetrics_example_older_export_biplane.csv"
_NEWER_SINGLE = get_path_to_example_tabular_files() / "radimetrics_example_newer_export_single_tube.csv"
_CAL = get_path_to_example_kerma_meter_file()
_LEAK_WORDS = ("calibration_factors_example", "radimetrics_example", "siemens_axiom", "DEMO-ROOM", "/Users/")


def _write_settings(path: Path, **top: Any) -> Path:
    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    base["phantom"]["model"] = "cylinder"
    base["plot"]["plot_dosemap"] = False
    base["plot"]["notebook_mode"] = False
    km = top.pop("km", None)
    base.update(top)
    if km:
        base["kerma_meter_correction"].update(km)
    path.write_text(json.dumps(base), encoding="utf-8")
    return path


def _run(*args: str) -> tuple[dict[str, Any], str]:
    proc = subprocess.run([sys.executable, "-m", "guiskindose", *args], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr[-300:]
    return json.loads(proc.stdout.strip().splitlines()[-1]), proc.stderr


def _tubes(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["tube"]: row for row in result["tube_summary"]}


def test_settings_file_and_output_format_flags_are_honoured(tmp_path: Path) -> None:
    """--settings is read (the default k_tab mode gives the measured-table PSD) and --output-format prints JSON."""
    settings = _write_settings(tmp_path / "s.json")
    result, _ = _run("-f", str(_RDSR), "-s", str(settings), "--output-format", "json")
    assert result["psd"] == pytest.approx(1.1773, abs=1e-3)
    assert set(result["events"]["k_tab_statuses"]) == {"exact"}


def test_k_tab_modes_through_the_settings_file(tmp_path: Path) -> None:
    estimate, _ = _run(
        "-f",
        str(_RDSR),
        "-s",
        str(_write_settings(tmp_path / "e.json", k_tab_mode="estimate")),
        "--output-format",
        "json",
    )
    assert estimate["psd"] == pytest.approx(1.3020, abs=1e-3)
    assert set(estimate["events"]["k_tab_statuses"]) == {"estimated"}


def test_legacy_estimate_k_tab_key_maps_with_a_deprecation_warning(tmp_path: Path) -> None:
    settings = _write_settings(tmp_path / "legacy.json")
    data = json.loads(settings.read_text(encoding="utf-8"))
    data.pop("k_tab_mode")
    data["estimate_k_tab"] = True
    settings.write_text(json.dumps(data), encoding="utf-8")
    result, stderr = _run("-f", str(_RDSR), "-s", str(settings), "--output-format", "json")
    assert result["psd"] == pytest.approx(1.3020, abs=1e-3)
    assert "estimate_k_tab is deprecated" in stderr


def test_example_calibration_file_and_calibration_date_select_the_period(tmp_path: Path) -> None:
    settings = _write_settings(tmp_path / "cal.json", km={"enable": True, "file": str(_CAL)})
    common = [
        "-f",
        str(_OLDER_BIPLANE),
        "-s",
        str(settings),
        "--input-schema",
        "radimetrics",
        "--kerma-meter-explicit-label",
        "DEMO-ROOM-2",
    ]
    old, _ = _run(*common, "--kerma-meter-calibration-date", "1901-06-01")
    new, stderr = _run(*common, "--kerma-meter-calibration-date", "1902-06-01")
    assert _tubes(old)["A"]["applied_cf"] == pytest.approx(0.98)
    assert _tubes(new)["A"]["applied_cf"] == pytest.approx(1.03)
    assert _tubes(new)["B"]["cf_source"] == "file"
    assert not any(word in stderr for word in _LEAK_WORDS)


def test_missing_factors_log_a_count_only_warning_without_labels(tmp_path: Path) -> None:
    settings = _write_settings(tmp_path / "on.json", km={"enable": True})
    result, stderr = _run("-f", str(_RDSR), "-s", str(settings), "--output-format", "json")
    assert _tubes(result)["single"]["cf_source"] == "default"
    assert "1 detected (equipment, tube) pair(s) have no factor" in stderr
    assert not any(word in stderr for word in _LEAK_WORDS)


def test_radimetrics_examples_report_per_tube_summaries(tmp_path: Path) -> None:
    settings = _write_settings(tmp_path / "rad.json", km={"enable": True})
    older, _ = _run("-f", str(_OLDER_BIPLANE), "-s", str(settings), "--input-schema", "radimetrics")
    newer, _ = _run("-f", str(_NEWER_SINGLE), "-s", str(settings), "--input-schema", "radimetrics")
    assert set(_tubes(older)) == {"A", "B"}
    assert [_tubes(older)[t]["events"] for t in ("A", "B")] == [4, 4]
    assert set(_tubes(newer)) == {"single"}
    assert _tubes(newer)["single"]["events"] == 5


def test_multi_exam_csv_prints_structured_json_without_file_names(tmp_path: Path) -> None:
    import shutil

    source = Path(__file__).resolve().parents[1] / "fixtures" / "tabular_inputs" / "normalized_events_multistudy.csv"
    csv_path = tmp_path / "patient_name_secret.csv"
    shutil.copy(source, csv_path)
    settings = _write_settings(tmp_path / "multi.json")
    proc = subprocess.run(
        [sys.executable, "-m", "guiskindose", "-f", str(csv_path), "-s", str(settings), "--input-schema", "normalized"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-300:]
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert len(result["exams"]) >= 2
    assert "aggregate_psd" in result
    assert "patient_name_secret" not in proc.stdout + proc.stderr
    assert str(tmp_path) not in proc.stdout + proc.stderr
    assert "source_file" not in proc.stdout


def test_multi_file_run_honours_the_aggregate_flag(tmp_path: Path) -> None:
    settings = _write_settings(tmp_path / "agg.json")
    proc = subprocess.run(
        [sys.executable, "-m", "guiskindose", "-f", str(_RDSR), str(_RDSR), "-s", str(settings), "--aggregate"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-300:]
    assert float(proc.stdout.strip().splitlines()[-1]) > 0


def _noncid_dosetrack_csv(tmp_path: Path) -> Path:
    import csv

    source = Path(__file__).resolve().parents[1] / "fixtures" / "tabular_inputs" / "dosetrack_events.csv"
    rows = list(csv.reader(source.read_text(encoding="utf-8").splitlines()))
    column = rows[0].index("Plane Code")
    for index, row in enumerate(rows[1:], 1):
        row[column] = "1" if index % 2 else "2"
    path = tmp_path / "dosetrack_noncid.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)
    return path


def test_dosetrack_ambiguous_plane_codes_need_a_map_and_the_map_reaches_the_preview(tmp_path: Path) -> None:
    csv_path = _noncid_dosetrack_csv(tmp_path)
    args = [
        sys.executable,
        "-m",
        "guiskindose",
        "-f",
        str(csv_path),
        "--input-schema",
        "dosetrack",
        "--input-preview-only",
    ]
    without = subprocess.run(args, capture_output=True, text=True, check=False)
    assert without.returncode != 0
    assert "Operation failed" in without.stderr
    assert str(tmp_path) not in without.stderr
    with_map = subprocess.run(
        [*args, "--plane-code-map", "1:Plane A,2:Plane B"], capture_output=True, text=True, check=False
    )
    assert with_map.returncode == 0, with_map.stderr[-300:]
    assert "Events loaded: 5" in with_map.stdout


def test_swap_lat_lon_flag_changes_psd_on_radimetrics(tmp_path: Path) -> None:
    settings = _write_settings(tmp_path / "swap.json")
    common = [
        "-f",
        str(_NEWER_SINGLE),
        "-s",
        str(settings),
        "--input-schema",
        "radimetrics",
        "--output-format",
        "json",
    ]
    baseline, _ = _run(*common)
    swapped, stderr = _run(*common, "--swap-lat-lon")
    assert swapped["psd"] != baseline["psd"]
    assert swapped["psd"] > 0
    assert not any(word in stderr for word in _LEAK_WORDS)


def test_dosetrack_plane_code_map_gives_tubes_in_a_full_run(tmp_path: Path) -> None:
    settings = _write_settings(tmp_path / "dt.json")
    result, _ = _run(
        "-f", str(_noncid_dosetrack_csv(tmp_path)), "--input-schema", "dosetrack", "-s", str(settings),
        "--plane-code-map", "1:Plane A,2:Plane B", "--output-format", "json",
    )  # fmt: skip
    assert {row["tube"]: row["events"] for row in result["tube_summary"]} == {"A": 3, "B": 2}
