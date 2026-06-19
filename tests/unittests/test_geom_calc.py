import sys
from pathlib import Path

import numpy as np

from mypyskindose.geom_calc import Triangle, convert_from_m_to_cm, convert_from_mm_to_cm

P = Path(__file__).parent.parent.parent
sys.path.insert(1, str(P.absolute()))


def test_triangle_check_intersection():
    """Test of intersection algoritm.

    Test if the intersection algoritm returns the expected output for different
    cell segment combinations.
    """
    expected: list[bool | list[bool]] = [True, True, True, True, False, False, [True, False]]

    actual: list[bool | list[bool]] = [False] * len(expected)

    center = np.array([0, 0, 0])
    vertex_1 = np.array([1, 0, 0])
    vertex_2 = np.array([0, 0, 1])

    triangle = Triangle(center, vertex_1, vertex_2)

    # straight through central vertex. (Expected = True)
    beam = np.array([+0.0, +1.0, +0.0])
    cell = np.array([+0.0, -1.0, +0.0])
    actual[0] = triangle.check_intersection(beam, cell)

    # straight through first vertex. (Expected = True)
    beam = np.array([+1.0, +1.0, +0.0])
    cell = np.array([+1.0, -1.0, +0.0])
    actual[1] = triangle.check_intersection(beam, cell)

    # straight through second vertex (Expected = True)
    beam = np.array([+0.0, +1.0, +1.0])
    cell = np.array([+0.0, -1.0, +1.0])
    actual[2] = triangle.check_intersection(beam, cell)

    # straight through triangle (Expected = True)
    beam = np.array([+0.2, +1.0, +0.2])
    cell = np.array([+0.2, -1.0, +0.2])
    actual[3] = triangle.check_intersection(beam, cell)

    # outside p1 (Expected = False)
    beam = np.array([+0.5, +1.0, -0.1])
    cell = np.array([+0.5, -1.0, -0.1])
    actual[4] = triangle.check_intersection(beam, cell)

    # outside p2 (Expected = False)
    beam = np.array([-0.1, +1.0, +0.5])
    cell = np.array([-0.1, -1.0, +0.5])
    actual[5] = triangle.check_intersection(beam, cell)

    # through triangle and outside of hypotenuse (Expected = [True, False])
    beam = np.array([+0.3, +1.0, +0.3])
    cell = np.array([[+0.3, -1.0, +0.3], [+0.9, -1.0, +0.9]])
    actual[6] = triangle.check_intersection(beam, cell)

    assert actual == expected


def test_convert_measurements_from_mm_to_cm():
    """Test that the mm to cm convertion scales correctly."""
    measurement_in_mm = 1000
    same_measurement_in_cm = 100

    expected = same_measurement_in_cm
    actual = convert_from_mm_to_cm(measurement_in_mm)

    assert actual == expected


def test_convert_measurements_from_m_to_cm():
    """Test that the m to cm convertion scales correctly."""
    measurement_in_m = 2
    same_measurement_in_cm = 200

    expected = same_measurement_in_cm
    actual = convert_from_m_to_cm(measurement_in_m)

    assert actual == expected


def test_fetch_and_append_hvl_snaps_out_of_grid_events():
    """A below-floor-kVp event has no exact HVL grid match; it must not crash but
    be snapped to the nearest grid point with a finite HVL.

    Regression for the IndexError in fetch_and_append_hvl (`.iloc[0]` on an empty
    exact-match lookup). See dev-docs/plans/hvl-invalid-event-crash.md.
    """
    import pandas as pd

    from mypyskindose import load_settings_example_json
    from mypyskindose.geom_calc import fetch_and_append_hvl
    from mypyskindose.settings import PyskindoseSettings

    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    settings = PyskindoseSettings(settings=base, output_format="dict")

    # Event 0 is in-grid; event 1 (kVp ~ 0.003) is below the 25 kV table floor.
    data_norm = pd.DataFrame(
        {
            "kVp": [70.0, 0.003],
            "filter_thickness_Cu": [0.0, 0.0],
            "filter_thickness_Al": [0.0, 0.0],
        }
    )

    out = fetch_and_append_hvl(
        data_norm=data_norm.copy(),
        inherent_filtration=settings.inherent_filtration,
        corrections_db=settings.corrections_db_path,
    )

    assert "HVL" in out.columns
    assert out["HVL"].notna().all()  # both resolved — the out-of-grid one was snapped
    assert (out["HVL"] > 0).all()


def _hvl(kvp_list, cu_list, al_list=None):
    """Run fetch_and_append_hvl on a tiny synthetic frame, returning (HVL series,
    captured WARNING messages). Captures via a dedicated handler on the
    ``mypyskindose`` logger so it is robust to suite-wide logging state (unlike
    pytest's ``caplog``, which depends on root-logger propagation)."""
    import logging

    import pandas as pd

    from mypyskindose import load_settings_example_json
    from mypyskindose.geom_calc import fetch_and_append_hvl
    from mypyskindose.settings import PyskindoseSettings

    base = load_settings_example_json()
    base["mode"] = "calculate_dose"
    settings = PyskindoseSettings(settings=base, output_format="dict")
    n = len(kvp_list)
    data_norm = pd.DataFrame(
        {
            "kVp": [float(x) for x in kvp_list],
            "filter_thickness_Cu": [float(x) for x in cu_list],
            "filter_thickness_Al": [float(x) for x in (al_list or [0.0] * n)],
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
        out = fetch_and_append_hvl(
            data_norm=data_norm,
            inherent_filtration=settings.inherent_filtration,
            corrections_db=settings.corrections_db_path,
        )
    finally:
        logger.removeHandler(handler)
    return out["HVL"], messages


def test_fetch_and_append_hvl_interpolates_off_grid_cu():
    """A Cu value between two tabulated points (0.4, 0.6) yields an HVL strictly
    between the two node HVLs, and an 'interpolated' warning is emitted."""
    # Bracketing on-node values plus the off-node midpoint, same kVp.
    hvl, messages = _hvl(kvp_list=[80, 80, 80], cu_list=[0.4, 0.5, 0.6])

    lo, mid, hi = float(hvl.iloc[0]), float(hvl.iloc[1]), float(hvl.iloc[2])
    # HVL increases with added Cu; the interpolated point sits strictly between.
    assert min(lo, hi) < mid < max(lo, hi)
    assert any("interpolated" in m.lower() for m in messages)


def test_fetch_and_append_hvl_clamps_out_of_range_kvp():
    """A kVp beyond the table ceiling (175) is clamped to the edge value (no
    extrapolation, no crash) and flagged 'clamped'."""
    hvl, messages = _hvl(kvp_list=[175, 250], cu_list=[0.0, 0.0])

    edge, beyond = float(hvl.iloc[0]), float(hvl.iloc[1])
    assert beyond == edge  # clamped to the 175 kV edge, not extrapolated past it
    assert any("clamped" in m.lower() for m in messages)


def test_fetch_and_append_hvl_on_grid_emits_no_warning():
    """An all-on-node frame interpolates to exact tabulated values and is silent."""
    hvl, messages = _hvl(kvp_list=[70, 80], cu_list=[0.0, 0.3])

    assert hvl.notna().all()
    assert not any(("interpolated" in m.lower() or "clamped" in m.lower()) for m in messages)
