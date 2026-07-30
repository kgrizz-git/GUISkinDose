import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from manual_tests.base_dev_settings import DEVELOPMENT_PARAMETERS
from mypyskindose.constants import (
    KEY_NORMALIZATION_ACQUISITION_PLANE,
    KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM,
    KEY_NORMALIZATION_FILTER_SIZE_COPPER,
    KEY_NORMALIZATION_KVP,
    KEY_NORMALIZATION_MODEL_NAME,
)
from mypyskindose.corrections import (
    calculate_k_bs,
    calculate_k_isq,
    calculate_k_med,
    calculate_k_tab,
)
from mypyskindose.geom_calc import fetch_and_append_hvl
from mypyskindose.settings import PyskindoseSettings

P = Path(__file__).parent.parent.parent
sys.path.insert(1, str(P.absolute()))

PATH_TO_DB = PyskindoseSettings(DEVELOPMENT_PARAMETERS).corrections_db_path


def test_fetch_hvl_from_database():

    expected = 6.549
    data_norm = pd.DataFrame({"kVp": [81.4], "filter_thickness_Al": [0], "filter_thickness_Cu": [0.3]})
    data_norm = fetch_and_append_hvl(data_norm=data_norm, inherent_filtration=3.1, corrections_db="corrections.db")
    actual = round(data_norm.HVL[0], 3)
    assert actual == expected


def test_calculate_unchanged_fluence_at_refernce_distance():
    expected = 1
    actual = calculate_k_isq(source=np.array([0, 0, 0]), cells=np.array([0, 100, 0]), dref=100)
    assert actual == expected


def test_calculate_increased_fluence_at_decreased_distance():
    expected = 4
    actual = calculate_k_isq(source=np.array([0, 0, 0]), cells=np.array([0, 50, 0]), dref=100)
    assert actual == expected


def test_calculate_decreased_fluence_at_increased_distance():
    expected = 0.25
    actual = calculate_k_isq(source=np.array([0, 0, 0]), cells=np.array([0, 200, 0]), dref=100)
    assert actual == expected


@pytest.mark.parametrize("n_hits", [1, 2, 3, 4, 10])
def test_k_isq_returns_one_value_per_hit_cell(n_hits):
    """2-D cells (n_hits, 3) must yield one ISL factor per cell for any n_hits.

    Regression for the (2,)/(3,) broadcast crash: events hitting <=3 skin cells
    previously fell to an axis=0 branch returning shape (3,)."""
    source = np.array([0, 0, 0])
    cells = np.tile([0, 100, 0], (n_hits, 1))  # n_hits cells, all 100 units away
    actual = calculate_k_isq(source=source, cells=cells, dref=100)
    assert actual.shape == (n_hits,)
    assert np.allclose(actual, 1.0)


def test_k_isq_per_cell_values_track_distance():
    """Each cell's ISL factor reflects its own source distance (not collapsed)."""
    source = np.array([0, 0, 0])
    cells = np.array([[0, 100, 0], [0, 50, 0], [0, 200, 0]])  # 3 hits -> previously buggy
    actual = calculate_k_isq(source=source, cells=cells, dref=100)
    assert actual.shape == (3,)
    assert np.allclose(actual, [1.0, 4.0, 0.25])


def test_fetch_correct_backscatter_correction_from_database():
    expected = 5 * [True]

    # Tabulated backscatter factor for param in data_norm
    tabulated_k_bs = [1.3, 1.458, 1.589, 1.617, 1.639]

    data_norm = pd.DataFrame({"kVp": 5 * [80], "HVL": 5 * [7.88], "FSL": [5, 10, 20, 25, 35]})

    # create interpolation object
    bs_interp = calculate_k_bs(data_norm)

    # interpolate at tabulated filed sizes
    k_bs = bs_interp[0](data_norm.FSL)

    diff = [100 * (abs(k_bs[i] - tabulated_k_bs[i])) / tabulated_k_bs[i] for i in range(len(tabulated_k_bs))]

    actual = [percent_difference <= 1 for percent_difference in diff]

    assert actual == expected


def test_fetch_correct_medium_correction_from_database():
    expected = [1.027, 1.026, 1.025, 1.025, 1.025]

    data = {"kVp": [80], "HVL": [4.99]}
    data_norm = pd.DataFrame(data)

    # Tests if we get a value in expected, for cells with different field
    # sizes with filed side length in [5 to 35] cm.
    actual = calculate_k_med(
        data_norm=data_norm,
        field_area=np.square([6, 10, 20, 22, 32]).tolist(),
        event=0,
        corrections_db=PATH_TO_DB,
    )
    assert actual in expected


def test_fetch_correct_table_correction_from_database():
    # Arrange
    expected = 0.7319

    data_norm = pd.DataFrame(
        data={
            KEY_NORMALIZATION_KVP: [80],
            KEY_NORMALIZATION_FILTER_SIZE_COPPER: [0.3],
            KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM: [0],
            KEY_NORMALIZATION_MODEL_NAME: ["AXIOM-Artis"],
            KEY_NORMALIZATION_ACQUISITION_PLANE: ["Single Plane"],
        }
    )

    # Act
    result = calculate_k_tab(data_norm=data_norm, estimate_k_tab=False, k_tab_val=0.8, corrections_db=PATH_TO_DB)

    actual = result[0]

    # Assert
    assert actual == expected


def test_fetch_correct_table_correction_from_database_when_machine_model_has_extra_blank_space():
    # Arrange
    expected = 0.8

    data_norm = pd.DataFrame(
        data={
            KEY_NORMALIZATION_KVP: [80],
            KEY_NORMALIZATION_FILTER_SIZE_COPPER: [0.4],
            KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM: [1.0],
            KEY_NORMALIZATION_MODEL_NAME: ["AlluraCla rity"],
            KEY_NORMALIZATION_ACQUISITION_PLANE: ["Plane A"],
        }
    )

    # Act
    result = calculate_k_tab(data_norm=data_norm, estimate_k_tab=False, k_tab_val=0.8, corrections_db=PATH_TO_DB)
    actual = result[0]

    # Assert
    assert actual == expected


def _k_tab(kvp, cu, al, model, plane):
    """Run calculate_k_tab on a one-row frame, capturing WARNING messages via a
    dedicated handler (robust to suite-wide logging state, unlike caplog)."""
    import logging

    data_norm = pd.DataFrame(
        data={
            KEY_NORMALIZATION_KVP: [kvp],
            KEY_NORMALIZATION_FILTER_SIZE_COPPER: [cu],
            KEY_NORMALIZATION_FILTER_SIZE_ALUMINUM: [al],
            KEY_NORMALIZATION_MODEL_NAME: [model],
            KEY_NORMALIZATION_ACQUISITION_PLANE: [plane],
        }
    )
    messages: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    logger = logging.getLogger("mypyskindose")
    handler = _Capture(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        result = calculate_k_tab(
            data_norm=data_norm, estimate_k_tab=False, k_tab_val=0.8, corrections_db=PATH_TO_DB
        )
    finally:
        logger.removeHandler(handler)
    return result[0], messages


def test_calculate_k_tab_unknown_device_fails_soft():
    """An unknown device/plane has no measured correction: fall back to k_tab=1.0
    and warn — never raise (regression for the `None[0]` TypeError crash)."""
    value, messages = _k_tab(kvp=80, cu=0.3, al=0, model="GE Innova", plane="Single Plane")
    assert value == 1.0
    assert any("no table-attenuation" in m.lower() for m in messages)


def test_calculate_k_tab_interpolates_off_grid_cu():
    """A Cu between two tabulated points interpolates strictly between the bracketing
    k_tab values for the same device/plane, and warns 'interpolated'."""
    lo, _ = _k_tab(kvp=80, cu=0.3, al=0, model="AXIOM-Artis", plane="Single Plane")
    hi, _ = _k_tab(kvp=80, cu=0.6, al=0, model="AXIOM-Artis", plane="Single Plane")
    mid, messages = _k_tab(kvp=80, cu=0.45, al=0, model="AXIOM-Artis", plane="Single Plane")
    assert min(lo, hi) < mid < max(lo, hi)
    assert any("interpolated" in m.lower() for m in messages)


def test_calculate_k_tab_clamps_out_of_range_kvp():
    """A kVp beyond the table ceiling (125) is clamped to the edge value (no crash,
    no extrapolation) and flagged 'clamped'."""
    edge, _ = _k_tab(kvp=125, cu=0.3, al=0, model="AXIOM-Artis", plane="Single Plane")
    beyond, messages = _k_tab(kvp=200, cu=0.3, al=0, model="AXIOM-Artis", plane="Single Plane")
    assert beyond == edge
    assert any("clamped" in m.lower() for m in messages)


def test_interpolate_off_grid_degenerate_kv_axis() -> None:
    from mypyskindose.corrections import _interpolate_off_grid
    from mypyskindose.grid_interp import STATUS_CLAMPED, STATUS_EXACT, STATUS_INTERPOLATED

    piv = pd.DataFrame(
        data=[[0.8, 0.9]], 
        index=[80.0], 
        columns=[0.3, 0.6]
    )
    piv.index.name = "kvp_kv"
    piv.columns.name = "filtration_added_mmcu"

    cache_key = ("AXIOM-Artis", "Single Plane", 0.0)
    pivot_cache: dict[tuple[str, str, float], pd.DataFrame] = {cache_key: piv}

    dummy_rows = pd.DataFrame({"filtration_added_mmal": [0.0]})

    # Interpolate along Cu axis only (midway between 0.8 and 0.9 is 0.85)
    val, status = _interpolate_off_grid(
        rows=dummy_rows, model="AXIOM-Artis", plane="Single Plane", 
        kvp=80.0, cu=0.45, al=0.0, pivot_cache=pivot_cache
    )
    assert abs(val - 0.85) < 1e-5
    assert status == STATUS_INTERPOLATED

    # Query directly on the only kVp row and a Cu grid node.
    val, status = _interpolate_off_grid(
        rows=dummy_rows, model="AXIOM-Artis", plane="Single Plane",
        kvp=80.0, cu=0.3, al=0.0, pivot_cache=pivot_cache
    )
    assert abs(val - 0.8) < 1e-5
    assert status == STATUS_EXACT

    # Query with KVp out of bounds (clamped to 80.0)
    val, status = _interpolate_off_grid(
        rows=dummy_rows, model="AXIOM-Artis", plane="Single Plane", 
        kvp=90.0, cu=0.45, al=0.0, pivot_cache=pivot_cache
    )
    assert abs(val - 0.85) < 1e-5
    assert status == STATUS_CLAMPED


def test_interpolate_off_grid_degenerate_cu_axis() -> None:
    """A one-Cu-column pivot supports kVp lookup and clamps other Cu values."""
    from mypyskindose.corrections import _interpolate_off_grid
    from mypyskindose.grid_interp import STATUS_CLAMPED, STATUS_EXACT

    piv = pd.DataFrame(data=[[0.8], [0.9]], index=[70.0, 80.0], columns=[0.3])
    cache_key = ("AXIOM-Artis", "Single Plane", 0.0)
    pivot_cache: dict[tuple[str, str, float], pd.DataFrame] = {cache_key: piv}
    dummy_rows = pd.DataFrame({"filtration_added_mmal": [0.0]})

    value, status = _interpolate_off_grid(
        rows=dummy_rows, model="AXIOM-Artis", plane="Single Plane",
        kvp=80.0, cu=0.3, al=0.0, pivot_cache=pivot_cache
    )
    assert value == pytest.approx(0.9)
    assert status == STATUS_EXACT

    value, status = _interpolate_off_grid(
        rows=dummy_rows, model="AXIOM-Artis", plane="Single Plane",
        kvp=80.0, cu=0.6, al=0.0, pivot_cache=pivot_cache
    )
    assert value == pytest.approx(0.9)
    assert status == STATUS_CLAMPED
