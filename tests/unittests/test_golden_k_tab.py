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

from guiskindose import load_settings_example_json
from guiskindose.constants import (
    KEY_NORMALIZATION_ACQUISITION_PLANE,
    KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM,
    KEY_NORMALIZATION_FILTER_SIZE_COPPER,
    KEY_NORMALIZATION_KVP,
    KEY_NORMALIZATION_MODEL_NAME,
)
from guiskindose.corrections import calculate_k_tab
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
    """Run calculate_k_tab on a one-row frame, capture WARNING messages via a
    dedicated handler (robust to suite-wide logging state, unlike caplog)."""
    messages: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    logger = logging.getLogger("guiskindose")
    handler = _Capture(level=logging.WARNING)
    logger.addHandler(handler)
    try:
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
        value = float(result[0])
    finally:
        logger.removeHandler(handler)

    status = "exact"
    for msg in messages:
        mlow = msg.lower()
        if "interpolated" in mlow:
            status = "interpolated"
        elif "clamped" in mlow:
            status = "clamped"
        elif "no table-attenuation" in mlow:
            status = "fallback_1.0"
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
