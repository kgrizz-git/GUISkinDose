"""Characterization tests pinning the post-fix behavior of ``calculate_k_tab``
and the per-cell table-transmission multiplication in the dose pipeline.

Chunk 1 of ``dev-docs/plans/archive/CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md`` documents
observed bugs so the later safeguard/fix can show exact regression deltas.  These
tests assert the *post-fix* contract.

Covered cases (plan §1):
  a. ``estimate_k_tab=True`` validates ``k_tab_val`` and rejects non-finite,
     <=0, or >1 values with ``ValueError``.  A valid value still returns the
     scalar repeated for every event.
  b. ``estimate_k_tab=False`` + AlluraClarity Plane B exact lookup returns 1.0
     (neutral fallback) and emits an invalid-inherited-data warning for the
     affected event index(es).
  c. Unit-level multiplication mirroring ``add_corrections_and_event_dose_to_output``:
     ``k_tab=0.0`` still zeroes table-hit intersected cells when passed directly,
     while a neutral factor (1.0) yields higher dose (PSD max increases), proving
     the dose-zeroing pathway.  (Note: ``calculate_k_tab`` no longer produces
     0.0; this test guards the downstream multiplication logic.)
  d. Valid Siemens AXIOM-Artis Single Plane and Philips AlluraClarity Plane A
     exact-match ``k_tab`` values from the CSV/golden must remain unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from guiskindose import constants as c
from guiskindose.calculate_dose.add_correction_and_event_dose_to_output import (
    add_corrections_and_event_dose_to_output,
)
from guiskindose.constants import (
    KEY_NORMALIZATION_ACQUISITION_PLANE,
    KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM,
    KEY_NORMALIZATION_FILTER_SIZE_COPPER,
    KEY_NORMALIZATION_KVP,
    KEY_NORMALIZATION_MODEL_NAME,
)
from guiskindose.corrections import _coerce_inherited_transmission, calculate_k_tab


def _db_path() -> str:
    # The settings example uses a relative "corrections.db". Resolve it to a
    # repository-root absolute path so the suite is robust to test CWD.
    repo_root = Path(__file__).resolve().parents[2]
    return str(repo_root / "corrections.db")


def _frame(kvp, cu, al, model, plane, n=1):
    return pd.DataFrame(
        data={
            KEY_NORMALIZATION_KVP: [kvp] * n,
            KEY_NORMALIZATION_FILTER_SIZE_COPPER: [cu] * n,
            KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM: [al] * n,
            KEY_NORMALIZATION_MODEL_NAME: [model] * n,
            KEY_NORMALIZATION_ACQUISITION_PLANE: [plane] * n,
        }
    )


def _capture_warnings(func, *args, **kwargs):
    messages: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    logger = logging.getLogger("guiskindose")
    handler = _Capture(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        result = func(*args, **kwargs)
    finally:
        logger.removeHandler(handler)
    return result, messages


# ---------------------------------------------------------------------------
# 1a. estimate_k_tab=True: range validation enforced
# ---------------------------------------------------------------------------

class TestCoerceInheritedTransmission:
    """Direct contract for ``_coerce_inherited_transmission``."""

    def test_valid_value_passes(self):
        assert _coerce_inherited_transmission(0.8) == pytest.approx(0.8)

    def test_zero_and_negative_reject(self):
        assert _coerce_inherited_transmission(0.0) is None
        assert _coerce_inherited_transmission(-0.1) is None

    def test_non_numeric_reject(self):
        assert _coerce_inherited_transmission("not-a-number") is None
        assert _coerce_inherited_transmission(None) is None
        assert _coerce_inherited_transmission(object()) is None

    def test_non_finite_reject(self):
        assert _coerce_inherited_transmission(float("nan")) is None
        assert _coerce_inherited_transmission(float("inf")) is None


class TestEstimateKTabValidation:
    """``estimate_k_tab=True`` now validates ``k_tab_val`` is finite and in (0, 1]."""

    def test_estimate_k_tab_zero_raises_value_error(self):
        data = _frame(kvp=80, cu=0.3, al=0, model="AXIOM-Artis", plane="Single Plane", n=3)
        with pytest.raises(ValueError, match="Invalid estimated k_tab_val"):
            calculate_k_tab(
                data_norm=data,
                corrections_db=_db_path(),
                estimate_k_tab=True,
                k_tab_val=0.0,
            )

    def test_estimate_k_tab_greater_than_one_raises_value_error(self):
        data = _frame(kvp=80, cu=0.3, al=0, model="AXIOM-Artis", plane="Single Plane", n=2)
        with pytest.raises(ValueError, match="Invalid estimated k_tab_val"):
            calculate_k_tab(
                data_norm=data,
                corrections_db=_db_path(),
                estimate_k_tab=True,
                k_tab_val=1.5,
            )

    def test_estimate_k_tab_valid_value_passes(self):
        data = _frame(kvp=80, cu=0.3, al=0, model="AXIOM-Artis", plane="Single Plane", n=2)
        result, _ = _capture_warnings(
            calculate_k_tab,
            data_norm=data,
            corrections_db=_db_path(),
            estimate_k_tab=True,
            k_tab_val=0.8,
        )
        assert result.values == [0.8, 0.8]
        assert result.statuses == ["estimated", "estimated"]


# ---------------------------------------------------------------------------
# 1b. AlluraClarity Plane B exact lookup → fallback to 1.0 with warning
# ---------------------------------------------------------------------------

class TestAlluraClarityPlaneBExactLookup:
    """AlluraClarity Plane B rows carry invalid k=0.0 in the CSV.  After the fix
    they fall back to neutral k_tab=1.0 and emit an invalid-inherited-data warning."""

    def test_allura_clarity_plane_b_exact_falls_back_to_one(self):
        """Representative (80 kVp, 0.4 mm Cu, 1.0 mm Al) exists in the CSV."""
        data = _frame(kvp=80, cu=0.4, al=1.0, model="AlluraClarity", plane="Plane B")
        result, messages = _capture_warnings(
            calculate_k_tab,
            data_norm=data,
            corrections_db=_db_path(),
            estimate_k_tab=False,
            k_tab_val=0.8,
        )
        assert result.values[0] == 1.0
        assert result.statuses[0] == "invalid_inherited"
        # Exact match path — no off-grid warnings expected.
        assert not any("interpolated" in m.lower() or "clamped" in m.lower() for m in messages)
        # Invalid inherited data warning must be present.
        assert any("invalid inherited" in m.lower() for m in messages)


# ---------------------------------------------------------------------------
# 1c. Unit-level dose multiplication: k_tab=0.0 zeroes table-hit cells
# ---------------------------------------------------------------------------

class TestKTabDoseMultiplicationPathway:
    """Regression tests for the dose-multiplication pathway.

    We call ``add_corrections_and_event_dose_to_output`` with synthetic inputs
    but the same ``temp[table_hits] = k_tab[event]`` logic as production code.

    ``calculate_k_tab`` no longer produces 0.0, but if an explicit 0.0 is passed
    directly to the dose pipeline it still zeroes table-hit cells.  A neutral
    factor (1.0) yields higher dose, proving the multiplication pathway is intact.
    """

    def _run_one_event(self, k_tab_value: float) -> tuple[np.ndarray, dict]:
        n_cells = 4
        hits = [True, True, False, False]  # 2 hit cells: indices 0 and 1
        table_hits = [False, True]  # second hit cell crosses the table

        # Synthetic patient: production only needs patient.r's length.
        patient = SimpleNamespace(r=np.zeros((n_cells, 3)))

        # Provide differing backscatter so PSD (dose_map.max()) is sensitive to
        # the table-hit scaling.
        def bs_interp(_x: np.ndarray) -> np.ndarray:
            return np.array([1.0, 2.0], dtype=float)

        normalized_data = pd.DataFrame(
            data={
                c.KEY_NORMALIZATION_KVP: [80.0],
                "HVL": [1.0],
                c.KEY_NORMALIZATION_AIR_KERMA: [1.0],
            }
        )

        output: dict[str, object] = {
            c.OUTPUT_KEY_CORRECTION_BACK_SCATTER: [None],
            c.OUTPUT_KEY_CORRECTION_MEDIUM: [None],
            c.OUTPUT_KEY_CORRECTION_TABLE: [None],
            c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW: [1.0],
            c.OUTPUT_KEY_DOSE_MAP: np.zeros(n_cells, dtype=float),
        }

        field_area = [25.0, 25.0]  # 2 hit cells (feeds fsl_mean in calculate_k_med)
        k_tab = [k_tab_value]

        out = add_corrections_and_event_dose_to_output(
            normalized_data=normalized_data,
            event=0,
            hits=hits,
            table_hits=table_hits,
            patient=patient,  # type: ignore[arg-type]
            back_scatter_interpolation=[bs_interp],  # type: ignore[list-item]
            field_area=field_area,
            k_tab=k_tab,
            corrections_db=_db_path(),
            output=output,
            kerma_cf=1.0,
        )
        return out[c.OUTPUT_KEY_DOSE_MAP], out

    def test_k_tab_zero_zeroes_table_hit_cells(self):
        dose_map, _ = self._run_one_event(k_tab_value=0.0)
        assert dose_map[0] > 0
        assert dose_map[1] == pytest.approx(0.0, abs=1e-12)
        assert dose_map.max() == pytest.approx(dose_map[0])

    def test_k_tab_nonzero_increases_psd_for_table_hit(self):
        dose_map_zero, _ = self._run_one_event(k_tab_value=0.0)
        dose_map_nonzero, _ = self._run_one_event(k_tab_value=1.0)

        # With our synthetic backscatter ratio (2.0), the table-hit cell becomes
        # the PSD when k_tab is neutral (1.0).
        assert dose_map_nonzero[1] > dose_map_nonzero[0]
        assert dose_map_nonzero.max() > dose_map_zero.max()

    def test_k_tab_greater_than_one_inflates_table_hit_cells(self):
        dose_map, _ = self._run_one_event(k_tab_value=1.5)
        assert dose_map[1] == pytest.approx(dose_map[0] * (2.0 * 1.5), rel=1e-6)


# ---------------------------------------------------------------------------
# 1d. Pin valid exact-match values from the CSV
# ---------------------------------------------------------------------------

class TestValidExactMatchKTabPins:
    """These values must remain unchanged by the safeguard fix because they are
    valid, non-zero, in-table exact matches."""

    def test_siemens_axiom_artis_single_plane_exact(self):
        data = _frame(kvp=80, cu=0.3, al=0, model="AXIOM-Artis", plane="Single Plane")
        result, _ = _capture_warnings(
            calculate_k_tab,
            data_norm=data,
            corrections_db=_db_path(),
            estimate_k_tab=False,
            k_tab_val=0.8,
        )
        assert result.values[0] == pytest.approx(0.7319, abs=1e-6)
        assert result.statuses[0] == "exact"

    def test_philips_allura_clarity_plane_a_exact(self):
        """AlluraClarity Plane A rows all resolve to 0.8."""
        data = _frame(kvp=80, cu=0.4, al=1.0, model="AlluraClarity", plane="Plane A")
        result, _ = _capture_warnings(
            calculate_k_tab,
            data_norm=data,
            corrections_db=_db_path(),
            estimate_k_tab=False,
            k_tab_val=0.8,
        )
        assert result.values[0] == pytest.approx(0.8, abs=1e-6)
        assert result.statuses[0] == "exact"
