"""Tests for :mod:`guiskindose.settings.phantom_dimensions`."""

from __future__ import annotations

from guiskindose.settings.phantom_dimensions import PhantomDimensions

_MINIMAL_DIMENSIONS = {
    "plane_length": 120,
    "plane_width": 40,
    "plane_resolution": "sparse",
    "cylinder_length": 150,
    "cylinder_radii_a": 20.0,
    "cylinder_radii_b": 10.0,
    "cylinder_resolution": "sparse",
    "table_thickness": 5,
    "table_length": 281.5,
    "table_width": 45,
    "pad_thickness": 4,
    "pad_width": 45,
    "pad_length": 281.5,
}


def test_update_attrs_str_refreshes_cached_summary() -> None:
    """Changing a dimension and calling update_attrs_str rebuilds attrs_str."""
    dims = PhantomDimensions(_MINIMAL_DIMENSIONS)
    original = dims.attrs_str

    dims.plane_length = 999
    dims.update_attrs_str()

    assert dims.attrs_str != original
    assert "dimensions" in dims.attrs_str
    assert "999" in dims.attrs_str
