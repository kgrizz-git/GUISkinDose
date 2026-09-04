"""Golden regression test for the full calculate-dose pipeline.

Pre-Phase-3a golden baseline captured 2026-07-28 against the pre-refactor
``calculate_dose`` / ``analyze_data`` pipeline on the bundled Siemens AXIOM
Artis RDSR fixture (cylinder phantom). Any refactor that changes PSD in
``PySkinDoseOutput`` (Phase 3a dataclass, Phase 3b Phantom.__init__, etc.)
must keep these golden values within tolerance.
"""

from __future__ import annotations

import logging
from typing import cast

import numpy as np
import pydicom
import pytest

from guiskindose import get_path_to_example_rdsr_files, load_settings_example_json
from guiskindose.analyze_data import analyze_data
from guiskindose.rdsr_normalizer import rdsr_normalizer
from guiskindose.rdsr_parser import rdsr_parser
from guiskindose.settings import PyskindoseSettings

_RDSR = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"

# Baseline captured 2026-07-28 against main HEAD (cylinder phantom, 21 events).
# Matches the existing _GOLDEN_SIEMENS_CYLINDER block in test_calculate_dose.py
# — frozen here as a Phase-3 precondition so the export-level PSD value has
# its own dedicated regression net independent of the calculate_dose internal
# template test.
_GOLDEN_PSD_MGY = 1.3020214659058027
_GOLDEN_AIR_KERMA_GY = 1.35
_GOLDEN_N_EVENTS = 21


@pytest.fixture(autouse=True)
def _quiet_logs():
    logging.getLogger("guiskindose").setLevel(logging.WARNING)
    yield


def _run_dict() -> dict:
    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    base["silence_pydicom_warnings"] = True
    base["phantom"]["model"] = "cylinder"
    base["plot"]["notebook_mode"] = False
    base["plot"]["plot_dosemap"] = False
    settings = PyskindoseSettings(settings=base, output_format="dict")
    parsed = rdsr_parser(pydicom.dcmread(str(_RDSR)), silence_pydicom_warnings=True)
    norm = rdsr_normalizer(parsed, settings=settings)
    # output_format="dict" guarantees a dict result (not str / PySkinDoseOutput).
    return cast(dict, analyze_data(normalized_data=norm.copy(), settings=settings))


def test_golden_psd_value_unchanged_after_phases() -> None:
    """Peak skin dose for the Siemens cylinder RDSR must match the frozen golden value (±1e-6 mGy)."""
    out = _run_dict()
    assert out["psd"] == pytest.approx(_GOLDEN_PSD_MGY, abs=1e-6, rel=1e-9)


def test_golden_air_kerma_unchanged_after_phases() -> None:
    """Total air kerma sum must match the frozen golden value (±1e-9 Gy)."""
    out = _run_dict()
    assert out["air_kerma"] == pytest.approx(_GOLDEN_AIR_KERMA_GY, abs=1e-9)


def test_golden_event_count_unchanged_after_phases() -> None:
    """The Siemens fixture must produce exactly 21 events in the export."""
    out = _run_dict()
    events = out.get("events")
    assert events is not None
    assert isinstance(events, dict)
    assert events["number_of_events"] == _GOLDEN_N_EVENTS


def test_golden_dose_map_nonzero_sum_unchanged_after_phases() -> None:
    """The dose map's positive-cell sum must match the existing golden dose_sum
    captured in test_calculate_dose.py (±1e-6 Gy). Pinning the sum (not the full
    array) keeps the test tolerant to float32 vs float64 reorderings while still
    catching any real shift in dose distribution."""
    out = _run_dict()
    dose_map = out["dose_map"]
    # Export makes the dose map sparse: list of (index, dose) pairs only for dose>0.
    total = sum(d for _, d in dose_map)
    assert total == pytest.approx(47.835152878258654, abs=1e-6)
    assert all(d > 0.0 for _, d in dose_map)


def test_golden_patient_offset_keys_present_after_phases() -> None:
    """export['patient']['offsets'] must expose the three base offset keys."""
    out = _run_dict()
    offsets = out["patient"]["offsets"]
    assert set(offsets.keys()) == {"long", "vert", "lat"}
    assert all(isinstance(v, (int, float)) for v in offsets.values())


def test_golden_dose_map_dtype_is_finite_after_phases() -> None:
    """No NaN or inf in the rendered dose map (defends against the assessment-flagged NaN path)."""
    out = _run_dict()
    dose_map = out["dose_map"]
    vals = np.array([d for _, d in dose_map], dtype=float)
    assert np.all(np.isfinite(vals))
