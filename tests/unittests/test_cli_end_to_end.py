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
