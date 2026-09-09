"""Characterization tests pinning the CURRENT (pre-fix) behavior of ``calculate_k_tab``
and the per-cell table-transmission multiplication in the dose pipeline.

Chunk 1 of ``dev-docs/plans/CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md`` documents
observed bugs so the later safeguard/fix can show exact regression deltas.  These
tests intentionally assert the *current* (buggy) contract; they must be updated
when the fix ships.

Covered cases (plan §1):
  a. ``estimate_k_tab=True`` returns ``[k_tab_val] * n`` with no range validation
     (accepts 0.0 and values >1.0).
  b. ``estimate_k_tab=False`` + AlluraClarity Plane B exact lookup returns 0.0 for
     a representative (kVp, Cu, Al) present in the CSV.
  c. Unit-level multiplication mirroring ``add_corrections_and_event_dose_to_output``:
     ``k_tab=0.0`` zeroes table-hit intersected cells, while a neutral factor
     (1.0) yields higher dose (PSD max increases), proving the dose-zeroing
     pathway.
  d. Valid Siemens AXIOM-Artis Single Plane and Philips AlluraClarity Plane A
     exact-match ``k_tab`` values from the CSV/golden (must remain 0.8 for typical
     Allura Plane A).
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
from guiskindose.corrections import calculate_k_tab


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
# 1a. estimate_k_tab=True: no range validation for 0.0 or >1.0
# ---------------------------------------------------------------------------

class TestEstimateKTabNoValidation:
    """The ``estimate_k_tab`` path returns the user-supplied scalar for every
    event with no range check.  Current behavior documents the missing guard."""

    def test_estimate_k_tab_returns_zero_without_error(self):
        data = _frame(kvp=80, cu=0.3, al=0, model="AXIOM-Artis", plane="Single Plane", n=3)
        result, _ = _capture_warnings(
            calculate_k_tab,
            data_norm=data,
            corrections_db=_db_path(),
            estimate_k_tab=True,
            k_tab_val=0.0,
        )
        assert result == [0.0, 0.0, 0.0]

    def test_estimate_k_tab_returns_greater_than_one_without_error(self):
        data = _frame(kvp=80, cu=0.3, al=0, model="AXIOM-Artis", plane="Single Plane", n=2)
        result, _ = _capture_warnings(
            calculate_k_tab,
            data_norm=data,
            corrections_db=_db_path(),
            estimate_k_tab=True,
            k_tab_val=1.5,
        )
        assert result == [1.5, 1.5]


# ---------------------------------------------------------------------------
# 1b. AlluraClarity Plane B exact lookup → 0.0
# ---------------------------------------------------------------------------

class TestAlluraClarityPlaneBExactLookup:
    """All 304 inherited AlluraClarity Plane B rows carry k=0.0.  A representative
    exact-match query confirms the current (buggy) return of 0.0."""

    def test_allura_clarity_plane_b_exact_returns_zero(self):
        """Representative (80 kVp, 0.4 mm Cu, 1.0 mm Al) exists in the CSV."""
        data = _frame(kvp=80, cu=0.4, al=1.0, model="AlluraClarity", plane="Plane B")
        result, messages = _capture_warnings(
            calculate_k_tab,
            data_norm=data,
            corrections_db=_db_path(),
            estimate_k_tab=False,
            k_tab_val=0.8,
        )
        assert result[0] == 0.0
        # Exact match — no off-grid warning expected
        assert not any("interpolated" in m.lower() or "clamped" in m.lower() for m in messages)


# ---------------------------------------------------------------------------
# 1c. Unit-level dose multiplication: k_tab=0.0 zeroes table-hit cells
# ---------------------------------------------------------------------------

class TestKTabDoseMultiplicationPathway:
    """Characterize the *real* dose-multiplication behavior.

    We call ``add_corrections_and_event_dose_to_output`` with synthetic inputs
    but the same ``temp[table_hits] = k_tab[event]`` logic as production code.

    These tests are pre-fix characterization: they pin the current contract
    that passing k_tab=0.0 will zero dose for table-hit cells.
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
        assert result[0] == pytest.approx(0.7319, abs=1e-6)

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
        assert result[0] == pytest.approx(0.8, abs=1e-6)
