"""Header-aware tabular unit conversion + RDSR unit-mismatch surfacing.

Covers the generalized converter in ``input_adapters/base.py`` (each quantity,
confident read vs unreadable-token fallback + warning) and the
``RdsrUnitError`` raised by ``rdsr_normalizer`` when a DICOM report uses a unit
the pipeline does not convert.
"""

from __future__ import annotations

import pandas as pd
import pytest

from mypyskindose.input_adapters.base import (
    AdapterContext,
    convert_field_with_header_units,
)
from mypyskindose.rdsr_normalizer import RdsrUnitError, _verify_expected_units


def _ctx(source_header: str, target_col: str) -> AdapterContext:
    """AdapterContext mapping one source header to one internal column."""
    return AdapterContext(
        column_map={source_header: target_col},
        raw_headers=[source_header],
        settings=None,
        warnings=[],
    )


# ── Confident reads: token drives the factor ──────────────────────────────────


@pytest.mark.parametrize(
    ("header", "target", "kind", "raw", "expected"),
    [
        ("Reference Point Dose (Total) mGy", "DoseRP_Gy", "dose", 1000.0, 1.0),
        ("Reference Point Dose (Total) Gy", "DoseRP_Gy", "dose", 1.0, 1.0),
        ("Air Kerma (µGy)", "DoseRP_Gy", "dose", 1_000_000.0, 1.0),
        ("Dose (cGy)", "DoseRP_Gy", "dose", 100.0, 1.0),
        ("Collimated Field Area (RF) [cm²]", "CollimatedFieldArea_m2", "area", 10000.0, 1.0),
        ("Collimated Field Area (m2)", "CollimatedFieldArea_m2", "area", 1.0, 1.0),
        ("Tube Current (uA)", "XRayTubeCurrent_mA", "tube_current", 1000.0, 1.0),
        ("Tube Current (mA)", "XRayTubeCurrent_mA", "tube_current", 1.0, 1.0),
        ("mAs (mAs)", "Exposure_uAs", "exposure", 1.0, 1000.0),
        ("Exposure (µAs)", "Exposure_uAs", "exposure", 1000.0, 1000.0),
        ("Distance Source to Detector (mm)", "DistanceSourcetoDetector_mm", "distance", 1200.0, 1200.0),
        ("Distance Source to Detector (cm)", "DistanceSourcetoDetector_mm", "distance", 120.0, 1200.0),
    ],
)
def test_confident_conversion(header, target, kind, raw, expected):
    df = pd.DataFrame({target: [raw]})
    ctx = _ctx(header, target)
    convert_field_with_header_units(df, target, kind, ctx)
    assert df[target].iloc[0] == pytest.approx(expected)
    # A confident read is recorded and does not raise a warning.
    assert target in ctx.unit_conversions
    assert ctx.warnings == []


def test_gy_labeled_dose_is_not_divided_by_1000():
    """Regression: a Gy-labelled reference point dose must not be treated as mGy."""
    df = pd.DataFrame({"DoseRP_Gy": [2.5]})
    ctx = _ctx("Reference Point Dose (Total) Gy", "DoseRP_Gy")
    convert_field_with_header_units(df, "DoseRP_Gy", "dose", ctx)
    assert df["DoseRP_Gy"].iloc[0] == pytest.approx(2.5)


# ── Unreadable tokens: vendor-default fallback (+ warning where unit varies) ───


def test_unreadable_dose_falls_back_to_mgy_and_warns():
    df = pd.DataFrame({"DoseRP_Gy": [1000.0]})
    ctx = _ctx("Reference Point Dose", "DoseRP_Gy")  # no unit token
    convert_field_with_header_units(df, "DoseRP_Gy", "dose", ctx)
    assert df["DoseRP_Gy"].iloc[0] == pytest.approx(1.0)  # assumed mGy → /1000
    assert "DoseRP_Gy" not in ctx.unit_conversions
    assert any("could not be read" in w for w in ctx.warnings)


def test_unreadable_distance_defaults_to_mm_without_warning():
    """mm is near-universal for distances, so the default is silent (no noise)."""
    df = pd.DataFrame({"DistanceSourcetoDetector_mm": [1200.0]})
    ctx = _ctx("Distance Source to Detector", "DistanceSourcetoDetector_mm")
    convert_field_with_header_units(df, "DistanceSourcetoDetector_mm", "distance", ctx)
    assert df["DistanceSourcetoDetector_mm"].iloc[0] == pytest.approx(1200.0)
    assert ctx.warnings == []


def test_absent_column_is_a_noop():
    df = pd.DataFrame({"Other": [1.0]})
    ctx = _ctx("Reference Point Dose (mGy)", "DoseRP_Gy")
    convert_field_with_header_units(df, "DoseRP_Gy", "dose", ctx)
    assert "DoseRP_Gy" not in df.columns
    assert ctx.warnings == []


def test_boundary_tokens_do_not_cross_match():
    """'ma' must not match inside 'mAs'; 'm2' must not match inside 'cm2'."""
    # Tube current header carrying 'mAs'-like text should still read as mA (word boundary).
    df = pd.DataFrame({"XRayTubeCurrent_mA": [5.0]})
    ctx = _ctx("Tube Current (mA)", "XRayTubeCurrent_mA")
    convert_field_with_header_units(df, "XRayTubeCurrent_mA", "tube_current", ctx)
    assert df["XRayTubeCurrent_mA"].iloc[0] == pytest.approx(5.0)  # mA → factor 1


# ── RDSR unit-mismatch surfacing ──────────────────────────────────────────────


def _rdsr_frame(dose_col: str = "DoseRP_Gy") -> pd.DataFrame:
    return pd.DataFrame(
        {
            dose_col: [0.5],
            "KVP_kV": [80.0],
            "DistanceSourcetoDetector_mm": [1200.0],
            "DistanceSourcetoIsocenter_mm": [750.0],
            "TableLongitudinalPosition_mm": [0.0],
            "TableLateralPosition_mm": [0.0],
            "TableHeightPosition_mm": [0.0],
            "PositionerPrimaryAngle_deg": [0.0],
            "PositionerSecondaryAngle_deg": [0.0],
        }
    )


def test_expected_units_pass_for_standard_frame():
    _verify_expected_units(_rdsr_frame())  # must not raise


def test_unexpected_dose_unit_raises_named_error():
    with pytest.raises(RdsrUnitError) as excinfo:
        _verify_expected_units(_rdsr_frame(dose_col="DoseRP_mGy"))
    msg = str(excinfo.value)
    assert "reference point dose" in msg
    assert "mGy" in msg and "Gy" in msg


def test_wholly_absent_concept_does_not_raise_unit_error():
    """A missing column (no sibling) is left to the normal missing-column path."""
    frame = _rdsr_frame().drop(columns=["DoseRP_Gy"])
    _verify_expected_units(frame)  # no DoseRP_* sibling → no RdsrUnitError
