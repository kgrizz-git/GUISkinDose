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

from guiskindose import constants as c
from guiskindose import load_settings_example_json
from guiskindose.beam_class import Beam, BeamGeometryInputs
from guiskindose.calculate_dose.perform_calculations_for_new_geometries import (
    perform_calculations_for_new_geometries,
)
from guiskindose.phantom_class import Phantom
from guiskindose.settings import PyskindoseSettings

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


# ── batched beam-face normals ─────────────────────────────────────────


def test_batched_beam_normals_equal_the_four_cross_products(frame: pd.DataFrame) -> None:
    """``beam.N`` must be exactly the four face cross products, bit for bit.

    ``Beam._build`` computes the four face normals with one batched ``np.cross``
    instead of four scalar calls. That is only safe if the batched form is
    numpy's own kernel doing identical arithmetic, so the pin is exact equality
    against the explicit four-call form -- not ``allclose``. A tolerance here
    would hide exactly the kind of drift the edit is meant to rule out.

    Poses sweep past 90 degrees on each axis, where a sign or axis-order slip
    would be largest.
    """
    for event in range(len(frame)):
        inputs = BeamGeometryInputs.from_frame(data_norm=frame, event=event)
        for pose in _POSES:
            beam = Beam.from_inputs(inputs, *pose)
            unit = (beam.r[1:] - beam.r[0, :]).T
            unit = (unit / np.linalg.norm(unit, axis=0)).T
            expected = np.vstack(
                [
                    np.cross(unit[0, :], unit[1, :]),
                    np.cross(unit[1, :], unit[2, :]),
                    np.cross(unit[2, :], unit[3, :]),
                    np.cross(unit[3, :], unit[0, :]),
                ]
            )
            np.testing.assert_array_equal(
                beam.N,
                expected,
                err_msg=f"beam.N differs from the four cross products at event {event}, pose {pose}",
            )
            # Shape and row order are part of the contract: row i is the normal
            # of the face between vertices i and i+1, wrapping.
            assert beam.N.shape == (4, 3)
            np.testing.assert_array_equal(beam.N[3], np.cross(unit[3, :], unit[0, :]))


# ── threading through perform_calculations_for_new_geometries ──────────


def _phantoms() -> tuple[Phantom, Phantom, Phantom]:
    """Patient (cylinder), table and pad phantoms for a geometry comparison.

    A cylinder rather than the plane default: the plane phantom skips the
    entrance-cell branch of the hit mask, so a hit-mask disagreement between
    the two paths could hide there.
    """
    dimension = load_settings_example_json()
    dimension = PyskindoseSettings(settings=dimension).phantom.dimension
    return (
        Phantom(phantom_model=c.PHANTOM_MODEL_CYLINDER, phantom_dim=dimension),
        Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=dimension),
        Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=dimension),
    )


def _geometry_call(
    frame: pd.DataFrame,
    phantoms: tuple[Phantom, Phantom, Phantom],
    event: int,
    *,
    beam_inputs: BeamGeometryInputs | None = None,
    beam_angles_deg: tuple[float, float, float] | None = None,
):
    """One perform_calculations call with fresh empty cache arrays."""
    patient, table, pad = phantoms
    return perform_calculations_for_new_geometries(
        normalized_data=frame,
        event=event,
        new_geometry=True,
        patient=patient,
        table=table,
        pad=pad,
        hits=[],
        table_hits=[],
        field_area=[],
        k_isq=np.array([]),
        beam_inputs=beam_inputs,
        beam_angles_deg=beam_angles_deg,
    )


@pytest.fixture
def phantoms() -> tuple[Phantom, Phantom, Phantom]:
    """Fresh phantoms with their reference pose saved, ready to be positioned.

    ``save_position`` belongs here rather than inside ``_geometry_call``:
    ``Phantom.position`` translates from ``r_ref``, so re-saving before each call
    would accumulate one extra table offset per call and quietly move the
    patient off the beam. The real caller reaches this state once, through
    ``position_patient_phantom_on_table``.
    """
    phantoms = _phantoms()
    for phantom in phantoms:
        phantom.save_position()
    return phantoms


def _assert_same_geometry(left, right, context: str) -> None:
    for index, name in enumerate(("hits", "table_hits", "field_area", "k_isq")):
        np.testing.assert_array_equal(
            np.asarray(left[index]),
            np.asarray(right[index]),
            err_msg=f"{name} differs {context}",
        )


def test_hoisting_at_the_row_pose_changes_nothing(frame: pd.DataFrame, phantoms) -> None:
    """Hoisting the scalars for the row's *own* pose must be a no-op.

    This is the equivalence the coverage envelope relies on: ``beam_inputs`` and
    ``beam_angles_deg`` exist only to skip the per-candidate table reads. If they
    changed a number, enveloped events would silently disagree with static ones.
    Pinned against the unhoisted call rather than a stored fixture, so it stays
    true as both sides evolve.
    """
    event = 1
    row_pose = (float(frame.Ap1[event]), float(frame.Ap2[event]), float(frame.Ap3[event]))
    inputs = BeamGeometryInputs.from_frame(data_norm=frame, event=event)

    unhoisted = _geometry_call(frame, phantoms, event)
    hoisted = _geometry_call(frame, phantoms, event, beam_inputs=inputs, beam_angles_deg=row_pose)

    assert int(np.count_nonzero(np.asarray(hoisted[0], dtype=bool))) > 0, "the fixture must hit cells"
    _assert_same_geometry(unhoisted, hoisted, "between the hoisted and unhoisted paths")


def test_angle_override_replaces_the_row_pose(frame: pd.DataFrame, phantoms) -> None:
    """An angle override must build *that* pose, not the row's.

    Without this the previous test would still pass if the override were
    silently dropped. Offset from the row's own angles rather than hard-coded,
    so the beam keeps intersecting the cylinder.
    """
    event = 1
    pose = (
        float(frame.Ap1[event]) + 25.0,
        float(frame.Ap2[event]) - 10.0,
        float(frame.Ap3[event]) + 5.0,
    )
    assert pose != (float(frame.Ap1[event]), float(frame.Ap2[event]), float(frame.Ap3[event]))
    inputs = BeamGeometryInputs.from_frame(data_norm=frame, event=event)

    hoisted = _geometry_call(frame, phantoms, event, beam_inputs=inputs, beam_angles_deg=pose)

    # The same pose forced into a copied frame, evaluated the original way.
    posed = frame.copy()
    # Ap3 is an int64 column in normalized frames, which a fractional pose cannot
    # be written into; widen the angle columns first.
    for column in ("Ap1", "Ap2", "Ap3"):
        posed[column] = posed[column].astype(float)
    posed.at[event, "Ap1"] = pose[0]
    posed.at[event, "Ap2"] = pose[1]
    posed.at[event, "Ap3"] = pose[2]
    expected = _geometry_call(posed, phantoms, event)

    assert int(np.count_nonzero(np.asarray(hoisted[0], dtype=bool))) > 0, "the fixture must hit cells"
    _assert_same_geometry(hoisted, expected, "between the hoisted pose and the same pose in a frame")

    # And it is genuinely a different pose from the row's, so the override is
    # load-bearing rather than a no-op in disguise.
    row_pose_result = _geometry_call(frame, phantoms, event)
    assert not np.array_equal(np.asarray(hoisted[0]), np.asarray(row_pose_result[0]))


def test_half_an_override_is_rejected(frame: pd.DataFrame, phantoms) -> None:
    """One override without the other is an error, not a silent mixture.

    Hoisting the scalars while the angles keep coming from the table (or the
    reverse) would build a plausible-looking beam from two different sources,
    so the pair is all-or-nothing.
    """
    event = 1
    with pytest.raises(ValueError, match="beam_inputs and beam_angles_deg"):
        _geometry_call(
            frame,
            phantoms,
            event,
            beam_inputs=BeamGeometryInputs.from_frame(data_norm=frame, event=event),
        )
    with pytest.raises(ValueError, match="beam_inputs and beam_angles_deg"):
        _geometry_call(frame, phantoms, event, beam_angles_deg=(10.0, 0.0, 0.0))
