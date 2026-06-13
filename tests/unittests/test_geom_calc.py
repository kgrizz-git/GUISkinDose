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
