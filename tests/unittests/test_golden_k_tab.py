"""Golden regression test for ``corrections.calculate_k_tab``.

Pre-Phase-3a baseline captured 2026-07-28 against the pre-refactor
``calculate_k_tab`` (CCN 15). Phase 3c extracts helpers
``_match_device_rows`` / ``_interpolate_off_grid`` / ``_log_k_tab_warnings``
from this function; the golden table here pins the per-event lookup result
and the WARNING-status classification (exact / interpolated / clamped /
fallback_1.0) so the refactor cannot change either.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import pytest

from guiskindose import get_path_to_example_rdsr_files, load_settings_example_json
from guiskindose.constants import (
    KEY_NORMALIZATION_ACQUISITION_PLANE,
    KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM,
    KEY_NORMALIZATION_FILTER_SIZE_COPPER,
    KEY_NORMALIZATION_KVP,
    KEY_NORMALIZATION_MODEL_NAME,
)
from guiskindose.corrections import calculate_k_tab
from guiskindose.rdsr_normalizer import rdsr_normalizer
from guiskindose.rdsr_parser import rdsr_parser
from guiskindose.settings import PyskindoseSettings

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "golden" / "k_tab_golden.json"


@pytest.fixture(autouse=True)
def _restore_logger_level():
    """Ensure the suite's logging state is permissive enough for the per-test
    WARNING handler to receive records. Does NOT silence the logger (we need the
    WARNING records to classify exact/interpolated/clamped/fallback status)."""
    logger = logging.getLogger("guiskindose")
    original_level = logger.level
    original_disabled = logger.disabled
    if logger.level > logging.WARNING or logger.disabled:
        logger.setLevel(logging.NOTSET)
        logger.disabled = False
    yield
    logger.setLevel(original_level)
    logger.disabled = original_disabled


def _db_path() -> str:
    return PyskindoseSettings(settings=load_settings_example_json()).corrections_db_path


def _run_k_tab(case: dict) -> tuple[float, str]:
    """Run calculate_k_tab on a one-row frame and return (value, status)."""
    data_norm = pd.DataFrame(
        data={
            KEY_NORMALIZATION_KVP: [case["kvp"]],
            KEY_NORMALIZATION_FILTER_SIZE_COPPER: [case["cu"]],
            KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM: [case["al"]],
            KEY_NORMALIZATION_MODEL_NAME: [case["model"]],
            KEY_NORMALIZATION_ACQUISITION_PLANE: [case["plane"]],
        }
    )
    result = calculate_k_tab(
        data_norm=data_norm,
        estimate_k_tab=False,
        k_tab_val=0.8,
        corrections_db=_db_path(),
    )
    value = float(result.values[0])
    status = result.statuses[0]
    return value, status


def _load_cases() -> list[dict]:
    blob = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return blob["cases"]


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: f"{c['model']}-{c['plane']}-kvp{c['kvp']}-cu{c['cu']}-al{c['al']}")
def test_k_tab_matches_known_input(case: dict) -> None:
    """Per-case golden regression: known (model, plane, kvp, cu, al) → known k_tab and status."""
    value, status = _run_k_tab(case)
    assert value == pytest.approx(case["expected_k_tab"], abs=1e-6)
    assert status == case["expected_status"], (
        f"Status mismatch for {case['model']}/{case['plane']} kvp={case['kvp']}: "
        f"expected {case['expected_status']!r}, got {status!r}"
    )


def test_k_tab_golden_fixture_is_loadable() -> None:
    """The fixture JSON must parse and have a `cases` list with at least one entry."""
    cases = _load_cases()
    assert cases, "k_tab_golden.json fixture is empty"
    required = {"model", "plane", "kvp", "cu", "al", "expected_k_tab", "expected_status"}
    for case in cases:
        assert required.issubset(case.keys()), f"case missing keys: {case}"


class TestKTabStatusExportInclusion:
    """k_tab statuses are included additively in dict/JSON export."""

    def test_table_statuses_present_in_dict_export(self):
        import pydicom

        from guiskindose.analyze_data import analyze_data

        base = load_settings_example_json()
        base["mode"] = "calculate_dose"
        base["silence_pydicom_warnings"] = True
        base["phantom"]["model"] = "cylinder"
        base["plot"]["notebook_mode"] = False
        base["plot"]["plot_dosemap"] = False
        settings = PyskindoseSettings(settings=base, output_format="dict")

        rdsr_path = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"
        parsed = rdsr_parser(pydicom.dcmread(str(rdsr_path)), silence_pydicom_warnings=True)
        norm = rdsr_normalizer(data_parsed=parsed, settings=settings)

        result = analyze_data(normalized_data=norm, settings=settings)
        assert isinstance(result, dict)
        assert "corrections" in result
        assert "table_statuses" in result["corrections"]
        assert "events" in result
        assert "k_tab_statuses" in result["events"]
        statuses = result["events"]["k_tab_statuses"]
        assert isinstance(statuses, list)
        assert len(statuses) == len(norm)

    def test_table_statuses_present_in_json_export(self):
        import pydicom

        from guiskindose.analyze_data import analyze_data

        base = load_settings_example_json()
        base["mode"] = "calculate_dose"
        base["silence_pydicom_warnings"] = True
        base["phantom"]["model"] = "cylinder"
        base["plot"]["notebook_mode"] = False
        base["plot"]["plot_dosemap"] = False
        settings = PyskindoseSettings(settings=base, output_format="json")

        rdsr_path = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"
        parsed = rdsr_parser(pydicom.dcmread(str(rdsr_path)), silence_pydicom_warnings=True)
        norm = rdsr_normalizer(data_parsed=parsed, settings=settings)

        result = analyze_data(normalized_data=norm, settings=settings)
        assert isinstance(result, str)
        import json as _json
        parsed_result = _json.loads(result)
        assert "corrections" in parsed_result
        assert "table_statuses" in parsed_result["corrections"]
        assert "events" in parsed_result
        assert "k_tab_statuses" in parsed_result["events"]
