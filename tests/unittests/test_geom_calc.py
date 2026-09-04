import sys
from pathlib import Path

import numpy as np

from guiskindose.geom_calc import Triangle, convert_from_m_to_cm, convert_from_mm_to_cm

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

    from guiskindose import load_settings_example_json
    from guiskindose.geom_calc import fetch_and_append_hvl
    from guiskindose.settings import PyskindoseSettings

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
    ``guiskindose`` logger so it is robust to suite-wide logging state (unlike
    pytest's ``caplog``, which depends on root-logger propagation)."""
    import logging

    import pandas as pd

    from guiskindose import load_settings_example_json
    from guiskindose.geom_calc import fetch_and_append_hvl
    from guiskindose.settings import PyskindoseSettings

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

    logger = logging.getLogger("guiskindose")
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


# ── Below-floor kVp policy (Phase 2) ─────────────────────────────────────────


def _apply_policy(kvp_list, policy, manual_kvp=70.0):
    """Run apply_below_floor_kvp_policy on a synthetic frame, returning
    (resulting kVp list, captured WARNING messages). Captures via a dedicated
    handler on the ``guiskindose`` logger (robust to suite-wide logging state)."""
    import logging

    import pandas as pd

    from guiskindose.geom_calc import apply_below_floor_kvp_policy

    data_norm = pd.DataFrame(
        {
            "kVp": [float(x) for x in kvp_list],
            "filter_thickness_Cu": [0.0] * len(kvp_list),
            "filter_thickness_Al": [0.0] * len(kvp_list),
        }
    )

    messages: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    logger = logging.getLogger("guiskindose")
    handler = _Capture(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        out = apply_below_floor_kvp_policy(
            data_norm=data_norm, policy=policy, manual_kvp=manual_kvp
        )
    finally:
        logger.removeHandler(handler)
    return [float(x) for x in out["kVp"].tolist()], messages


def test_count_below_floor_events_returns_indices():
    """count_below_floor_events flags exactly the sub-25 kV rows by position."""
    import pandas as pd

    from guiskindose.geom_calc import count_below_floor_events

    df = pd.DataFrame({"kVp": [70.0, 10.0, 25.0, 0.003, 24.9]})
    # 25.0 is on the floor (not below); 10, 0.003, 24.9 are below.
    assert count_below_floor_events(df) == [1, 3, 4]


def test_below_floor_policy_snap_is_noop():
    """'snap' leaves kVp untouched and emits no warning (status quo)."""
    out, messages = _apply_policy([70.0, 10.0], policy="snap")
    assert out == [70.0, 10.0]
    assert messages == []


def test_below_floor_policy_skip_drops_rows():
    """'skip' drops the below-floor rows and reindexes, warning about the drop."""
    out, messages = _apply_policy([70.0, 10.0, 80.0], policy="skip")
    assert out == [70.0, 80.0]
    assert any("skip" in m.lower() and "dropped" in m.lower() for m in messages)


def test_below_floor_policy_manual_substitutes_value():
    """'manual' replaces every below-floor kVp with the manual value, in place."""
    out, messages = _apply_policy([70.0, 10.0, 5.0], policy="manual", manual_kvp=66.0)
    assert out == [70.0, 66.0, 66.0]
    assert any("manual" in m.lower() and "66" in m for m in messages)


def test_below_floor_policy_exam_average_uses_in_floor_mean():
    """'exam_average' replaces below-floor kVp with the mean of the in-floor events."""
    # In-floor events: 60, 80 → mean 70. Below-floor: 10.
    out, messages = _apply_policy([60.0, 10.0, 80.0], policy="exam_average")
    assert out == [60.0, 70.0, 80.0]
    assert any("exam_average" in m.lower() or "exam mean" in m.lower() for m in messages)


def test_below_floor_policy_uses_positions_when_index_labels_repeat():
    """Only below-floor rows change when the input frame has duplicate index labels."""
    import pandas as pd

    from guiskindose.geom_calc import apply_below_floor_kvp_policy

    data_norm = pd.DataFrame(
        {
            "kVp": [10.0, 70.0, 5.0, 90.0],
            "filter_thickness_Cu": [0.0] * 4,
            "filter_thickness_Al": [0.0] * 4,
        },
        index=[0, 0, 1, 2],
    )

    manual = apply_below_floor_kvp_policy(data_norm, policy="manual", manual_kvp=66.0)
    average = apply_below_floor_kvp_policy(data_norm, policy="exam_average", manual_kvp=66.0)

    assert manual["kVp"].tolist() == [66.0, 70.0, 66.0, 90.0]
    assert average["kVp"].tolist() == [80.0, 70.0, 80.0, 90.0]


def test_below_floor_policy_exam_average_all_below_falls_back_to_snap():
    """An all-below-floor frame has no in-floor mean → fall back to snap + warn,
    leaving kVp unchanged so Phase 1 clamps it."""
    out, messages = _apply_policy([10.0, 5.0], policy="exam_average")
    assert out == [10.0, 5.0]
    assert any("fall" in m.lower() and "snap" in m.lower() for m in messages)
