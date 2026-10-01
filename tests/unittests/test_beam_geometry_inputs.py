"""Tests for the Phase-2 beam-scalar hoist (``BeamGeometryInputs``).

The coverage envelope builds one :class:`Beam` per candidate pose while every
scalar it needs is constant across the domain, so
:meth:`Beam.from_inputs` must be interchangeable with the DataFrame constructor
*exactly* — these tests assert bit equality, not ``allclose``.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest
from calculate_dose_recursion_helpers import generate_synthetic_normalized_events

from guiskindose.beam_class import Beam, BeamGeometryInputs

# Poses chosen to cover the trig quadrants and both the +-1 boundaries the
# rotation matrices care about; a change in the sign/axis handling of any of
# them moves the vertices by whole centimetres, not by ulps.
_POSES = ((0.0, 0.0, 0.0), (37.5, -12.25, 3.0), (180.0, 90.0, -45.0), (-179.5, 179.5, 89.9))

_GEOMETRY_ATTRIBUTES = ("r", "N", "det_r", "ijk", "det_ijk")


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    return generate_synthetic_normalized_events(3)


def test_inputs_are_read_from_the_requested_event(frame: pd.DataFrame) -> None:
    """Every field comes from row ``event`` — except DSL, which is row 0."""
    inputs = BeamGeometryInputs.from_frame(data_norm=frame, event=2)

    assert inputs == BeamGeometryInputs(
        dsi=float(frame.DSI[2]),
        dsd=float(frame.DSD[2]),
        fs_long=float(frame.FS_long[2]),
        fs_lat=float(frame.FS_lat[2]),
        did=float(frame.DID[2]),
        dsl=float(frame.DSL[0]),
    )


def test_dsl_quirk_is_preserved_not_fixed(frame: pd.DataFrame) -> None:
    """``DSL`` stays read at index 0, the quirk ``Beam`` has always had.

    Detector side length has always come from the *first* event regardless of
    which event is being built. Silently switching to ``DSL[event]`` would change
    numbers for every event after the first, so it is pinned here as-is.

    The rows must actually disagree on ``DSL`` for the pin to mean anything: the
    synthetic fixture clones one RDSR row and perturbs only ``Tx``/``Ap1``, so
    every row would otherwise carry the same ``DSL`` and the assertion would pass
    whichever index ``from_frame`` read. Hence the explicit per-row values, and
    hence the assertion that they took effect.
    """
    varied = frame.copy()
    # Integer values: DSL is an int64 column, and pandas 2.x refuses a
    # fractional assignment into it, which would raise instead of testing
    # anything.
    for index, dsl in enumerate((30, 35, 42)):
        varied.at[index, "DSL"] = dsl
    assert len({float(varied.DSL[index]) for index in range(3)}) == 3, "fixture rows must disagree on DSL"

    for event in range(len(varied)):
        assert BeamGeometryInputs.from_frame(data_norm=varied, event=event).dsl == float(varied.DSL[0])

    # And the pin bites on the geometry itself: a beam built for the last event
    # gets row 0's detector size, not its own. plot_setup zeroes the rotation, so
    # the detector corners stay axis-aligned and the half-width is readable as
    # max|det_r[:, 0]| == DSL / 2.
    zero_angle_beam = Beam(data_norm=varied, event=2, plot_setup=True)
    assert float(np.abs(zero_angle_beam.det_r[:, 0]).max()) == pytest.approx(float(varied.DSL[0]) / 2.0)
    assert float(np.abs(zero_angle_beam.det_r[:, 2]).max()) == pytest.approx(float(varied.DSL[0]) / 2.0)
    assert float(varied.DSL[0]) != float(varied.DSL[2])


def test_inputs_record_is_frozen(frame: pd.DataFrame) -> None:
    """A record cannot be edited into something no beam was built for."""
    inputs = BeamGeometryInputs.from_frame(data_norm=frame, event=0)

    with pytest.raises(dataclasses.FrozenInstanceError):
        inputs.dsd = 1.0  # type: ignore[misc]


def test_from_inputs_matches_the_dataframe_constructor_bit_for_bit(frame: pd.DataFrame) -> None:
    """``from_inputs`` is the DataFrame path with the table reads hoisted out."""
    # Ap3 is an int64 column in normalized frames, which a fractional pose cannot
    # be written into; the integer-angle path is pinned separately below.
    posed_frame = frame.copy()
    for column in ("Ap1", "Ap2", "Ap3"):
        posed_frame[column] = posed_frame[column].astype(float)

    for event in range(len(frame)):
        inputs = BeamGeometryInputs.from_frame(data_norm=posed_frame, event=event)
        for pose in _POSES:
            # Pose forced into the frame, so the comparison is against a beam the
            # original constructor would itself have produced for those angles.
            posed = posed_frame.copy()
            posed.at[event, "Ap1"] = pose[0]
            posed.at[event, "Ap2"] = pose[1]
            posed.at[event, "Ap3"] = pose[2]

            reference = Beam(data_norm=posed, event=event)
            hoisted = Beam.from_inputs(inputs, *pose)

            for attribute in _GEOMETRY_ATTRIBUTES:
                np.testing.assert_array_equal(
                    getattr(reference, attribute),
                    getattr(hoisted, attribute),
                    err_msg=f"{attribute} differs at event {event}, pose {pose}",
                )


def test_plot_setup_path_still_forces_zero_angulation(frame: pd.DataFrame) -> None:
    """``plot_setup=True`` must equal a zero-angle beam from ``from_inputs``.

    ``plot_setup`` is a debugging entry point that ignores the table's angles,
    so it is also the one place where the adapter's angle handling could quietly
    disagree with ``from_inputs``.
    """
    inputs = BeamGeometryInputs.from_frame(data_norm=frame, event=1)
    # A non-zero pose in the table, so a regression that leaks the table angles
    # into the plot_setup path would be visible.
    posed = frame.copy()
    posed.at[1, "Ap1"] = 42.0
    posed.at[1, "Ap2"] = -17.0
    posed.at[1, "Ap3"] = 5.0

    setup_beam = Beam(data_norm=posed, event=1, plot_setup=True)
    zero_beam = Beam.from_inputs(inputs, 0.0, 0.0, 0.0)

    for attribute in _GEOMETRY_ATTRIBUTES:
        np.testing.assert_array_equal(
            getattr(setup_beam, attribute),
            getattr(zero_beam, attribute),
            err_msg=f"{attribute} differs on the plot_setup path",
        )


def test_from_inputs_ignores_angle_dtype(frame: pd.DataFrame) -> None:
    """Integer and float angles must build the same beam.

    ``Ap3`` is an integer column in normalized frames while ``Ap1``/``Ap2`` are
    floats, and the candidate loop supplies Python floats for all three, so the
    integer-typed column is the one case where the two paths could diverge.
    """
    inputs = BeamGeometryInputs.from_frame(data_norm=frame, event=0)
    assert isinstance(int(frame.Ap3[0]), int)

    from_table = Beam.from_inputs(inputs, float(frame.Ap1[0]), float(frame.Ap2[0]), int(frame.Ap3[0]))
    as_floats = Beam.from_inputs(inputs, float(frame.Ap1[0]), float(frame.Ap2[0]), float(frame.Ap3[0]))

    for attribute in _GEOMETRY_ATTRIBUTES:
        np.testing.assert_array_equal(
            getattr(from_table, attribute),
            getattr(as_floats, attribute),
            err_msg=f"{attribute} differs between integer and float angle inputs",
        )
