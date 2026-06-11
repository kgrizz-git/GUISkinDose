"""Characterization tests for rdsr_normalizer (refactor plan Phase 1.1).

rdsr_normalizer applies per-vendor translation offsets and rotation-direction
inversions. A regression there produces plausible-looking but numerically wrong
dose maps with **no error raised** — invisible without a pinned baseline.

These tests parse + normalize the three bundled RDSRs and assert exact
Tx/Ty/Tz/Ap1/Ap2 (and kVp/K_IRP) for the first rows against values captured
from current output. They are a safety net for the Phase 2/3 refactors: any
change that alters the normalized numbers must update these golden values
deliberately, not silently.

Golden values captured 2026-06-11 from the current implementation. The Philips
offsets (x=-0.3, y=105.5, z=-173.35 cm) and direction inversions live in
normalization_settings.json; pinning the end-to-end output covers them.
"""

from __future__ import annotations

import pydicom
import pytest

from mypyskindose import (
    get_path_to_example_rdsr_files,
    load_settings_example_json,
)
from mypyskindose.rdsr_normalizer import rdsr_normalizer
from mypyskindose.rdsr_parser import rdsr_parser
from mypyskindose.settings import PyskindoseSettings

_RDSR_DIR = get_path_to_example_rdsr_files()

# Per-file: expected (model, normalization_method, row_count) and the first-rows
# golden table. Tolerances are tight enough to catch a sign flip on any axis.
_GOLDEN: dict[str, dict] = {
    "siemens_axiom_artis.dcm": {
        "model": "AXIOM-Artis",
        "method": "Matched",
        "rows": 21,
        "first_rows": [
            {"Tx": 3.78, "Ty": 29.41, "Tz": 4.06, "Ap1": -0.1, "Ap2": -1.1, "kVp": 77.0, "K_IRP": 0.03},
            {"Tx": 2.16, "Ty": 29.41, "Tz": 3.33, "Ap1": -0.1, "Ap2": -1.1, "kVp": 74.0, "K_IRP": 0.02},
            {"Tx": -2.72, "Ty": 29.41, "Tz": 1.21, "Ap1": -0.1, "Ap2": -1.1, "kVp": 74.0, "K_IRP": 0.01},
        ],
    },
    "philips_allura_clarity_u104.dcm": {
        "model": "Allura Clarity",
        "method": "Matched",
        "rows": 25,
        "first_rows": [
            {"Tx": 8.1, "Ty": 26.4, "Tz": -20.9, "Ap1": 0.0, "Ap2": 0.0, "kVp": 57.5, "K_IRP": 0.0046},
            {"Tx": 8.1, "Ty": 26.4, "Tz": -20.9, "Ap1": 0.0, "Ap2": 0.0, "kVp": 55.74, "K_IRP": 0.0046},
            {"Tx": 8.4, "Ty": 26.4, "Tz": -22.2, "Ap1": 0.0, "Ap2": 0.0, "kVp": 60.07, "K_IRP": 0.0092},
        ],
    },
    "philips_allura_clarity_u601.dcm": {
        "model": "Allura Clarity",
        "method": "Matched",
        "rows": 29,
        "first_rows": [
            {"Tx": 3.9, "Ty": 13.1, "Tz": -0.31, "Ap1": -0.1, "Ap2": 0.1, "kVp": 48.58, "K_IRP": 0.0159},
            {"Tx": 1.2, "Ty": 13.1, "Tz": -0.4, "Ap1": -0.1, "Ap2": 0.1, "kVp": 48.77, "K_IRP": 0.0026},
            {"Tx": -2.5, "Ty": 13.1, "Tz": -0.4, "Ap1": -0.1, "Ap2": 0.1, "kVp": 52.67, "K_IRP": 0.0053},
        ],
    },
}

_TOL = 0.01  # cm / deg / mGy — tight enough to catch a sign flip


def _normalize(fname: str):
    raw = pydicom.dcmread(str(_RDSR_DIR / fname))
    parsed = rdsr_parser(raw, silence_pydicom_warnings=True)
    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    base["silence_pydicom_warnings"] = True
    settings = PyskindoseSettings(settings=base, output_format="dict")
    norm = rdsr_normalizer(parsed, settings=settings)
    return norm, settings


@pytest.mark.parametrize("fname", list(_GOLDEN))
def test_normalization_matches_expected_model_and_method(fname):
    norm, settings = _normalize(fname)
    spec = _GOLDEN[fname]
    ns = settings.normalization_settings
    assert ns.matched_model == spec["model"]
    assert ns.normalization_method == spec["method"]
    assert len(norm) == spec["rows"]


@pytest.mark.parametrize("fname", list(_GOLDEN))
def test_normalized_values_are_stable(fname):
    norm, _ = _normalize(fname)
    spec = _GOLDEN[fname]
    for i, expected in enumerate(spec["first_rows"]):
        for col, want in expected.items():
            got = float(norm.iloc[i][col])
            assert got == pytest.approx(want, abs=_TOL), (
                f"{fname} row {i} col {col}: got {got}, expected {want}"
            )


def test_philips_table_positions_need_no_swap():
    """Pins the finding from the lat/lon-swap investigation: Philips RDSR
    normalizes to physically plausible Tx/Tz with no swap applied.

    If a swap were wrongly introduced into the Philips path, Tx and Tz would
    exchange and these assertions would fail.
    """
    norm, _ = _normalize("philips_allura_clarity_u104.dcm")
    assert float(norm.iloc[0]["Tx"]) == pytest.approx(8.1, abs=_TOL)
    assert float(norm.iloc[0]["Tz"]) == pytest.approx(-20.9, abs=_TOL)
