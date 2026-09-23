"""Unit tests for the shared rotational-acquisition classifier."""

from __future__ import annotations

import math

import pytest

from guiskindose.rotational_acquisition import (
    MOTION_THRESHOLD_DEG,
    circular_separation_deg,
    classify_rotational_event,
)


def _row(**overrides):
    base = {
        "Ap1": 90.0,
        "Ap2": 0.0,
        "Ap1_end": 90.0,
        "Ap2_end": 0.0,
        "acquisition_type": "Fluoroscopy",
    }
    base.update(overrides)
    return base


def test_circular_separation_handles_wrap():
    assert circular_separation_deg(179.0, -179.0) == pytest.approx(2.0)
    assert circular_separation_deg(90.0, -120.0) == pytest.approx(150.0)
    assert circular_separation_deg(10.0, 10.0) == pytest.approx(0.0)


def test_coded_rotational_wins_with_endpoints():
    result = classify_rotational_event(
        _row(acquisition_type="Rotational Acquisition", acquisition_type_code="113613", Ap1_end=-120.0)
    )
    assert result.classification == "rotational"
    assert result.confidence == "coded"
    assert "type_code_rotational" in result.reason_codes
    assert "primary_endpoint_motion" in result.reason_codes
    assert result.usable_endpoints is True
    assert result.primary_separation_deg == pytest.approx(150.0)


def test_meaning_rotational_without_code():
    result = classify_rotational_event(_row(acquisition_type="Rotational Acquisition"))
    assert (result.classification, result.confidence) == ("rotational", "meaning")
    assert result.usable_endpoints is False
    assert "equal_endpoints" in result.reason_codes


def test_meaning_rotational_without_any_endpoints():
    result = classify_rotational_event(
        _row(acquisition_type="Rotational Acquisition", Ap1_end=None, Ap2_end=None)
    )
    assert result.classification == "rotational"
    assert "missing_or_invalid_endpoints" in result.reason_codes


def test_stepping_identity_wins_over_motion():
    result = classify_rotational_event(
        _row(acquisition_type="Stepping Acquisition", acquisition_type_code="113612", Ap1_end=-120.0)
    )
    assert result.classification == "positioner_motion"
    assert result.confidence == "coded"


def test_angle_only_motion_is_rotational_angle_inferred():
    result = classify_rotational_event(_row(acquisition_type="Fluoroscopy", Ap1_end=-120.0))
    assert result.classification == "rotational"
    assert result.confidence == "angle_motion"
    assert result.usable_endpoints is True


def test_contradictory_static_needs_explicit_choice():
    result = classify_rotational_event(
        _row(
            acquisition_type="Stationary Acquisition",
            acquisition_type_code="113611",
            Ap1_end=-120.0,
        )
    )
    assert result.classification == "unknown"
    assert "contradictory_static" in result.reason_codes


def test_static_equal_endpoints_and_plain_static():
    assert classify_rotational_event(_row()).classification == "static"
    assert (
        classify_rotational_event(
            _row(acquisition_type="Stationary Acquisition", acquisition_type_code="113611")
        ).classification
        == "static"
    )


def test_text_alias_triggers_but_never_direction():
    result = classify_rotational_event(_row(acquisition_type="Fluoroscopy", protocol_text="Gastro Roll 4s"))
    assert result.classification == "rotational"
    assert result.confidence == "text_alias"
    assert "text_alias_rotational" in result.reason_codes


def test_text_alias_requires_whole_token():
    assert classify_rotational_event(_row(protocol_text="Controller check")).classification == "static"


@pytest.mark.parametrize(
    "separation,expected_motion",
    [(0.0, False), (1.99, False), (2.0, True), (2.01, True)],
)
def test_motion_threshold_boundaries(separation, expected_motion):
    result = classify_rotational_event(_row(Ap1_end=90.0 + separation))
    assert ("primary_endpoint_motion" in result.reason_codes) is expected_motion


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), "not-a-number", True])
def test_invalid_endpoints_are_not_motion(bad):
    result = classify_rotational_event(_row(Ap1_end=bad, Ap2_end=bad))
    assert "primary_endpoint_motion" not in result.reason_codes
    assert "secondary_endpoint_motion" not in result.reason_codes


def test_one_axis_only_motion_is_usable():
    result = classify_rotational_event(_row(Ap1_end=100.0, Ap2_end=None))
    assert result.usable_endpoints is True
    assert result.primary_separation_deg == pytest.approx(10.0)
    assert result.secondary_separation_deg is None


def test_threshold_constant_is_two_degrees():
    assert MOTION_THRESHOLD_DEG == 2.0
    assert math.isclose(circular_separation_deg(0.0, 2.0), 2.0)
