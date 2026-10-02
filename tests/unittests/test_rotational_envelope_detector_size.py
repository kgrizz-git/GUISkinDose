"""The rotational envelope must read each beam scalar from the row it always did.

The Phase-2 hoist resolves one :class:`BeamGeometryInputs` per event and reuses
it for every candidate pose. That is only sound if the record is built from the
*same place* the per-candidate beams used to read from -- and for one scalar,
``DSL``, that place is not the obvious one.

``Beam`` has always taken detector side length at index ``0`` rather than at the
event index (see ``BeamGeometryInputs.from_frame``). On a full event table that
means the procedure's *first* event. But the envelope's candidates were built
from a one-row, index-reset frame, where index ``0`` is the *parent event's* row.
So enveloped events and static events have always disagreed about which row
supplies ``DSL``, and the hoist must preserve each side's own behaviour rather
than unify them.

Every test here varies ``DSL`` per row on purpose. With a fixture whose rows agree
on ``DSL`` the whole distinction is invisible -- which is how reading the wrong
row reached a commit before this file existed.

Scope, stated plainly, and it is narrower than it first looks: ``DSL`` scales ``Beam.det_r`` and
nothing else. The dose chain reads ``beam.r``, ``beam.N`` and ``beam.r[0, :]``, never ``det_r``. And
no *candidate* beam's ``det_r`` is read by anything at all — ``Beam.from_inputs`` is called from
exactly one place (the envelope's candidate loop), while every consumer of ``det_r``
(``create_mesh3d``, ``create_wireframes``, ``create_geometry_plot_texts``, ``format_export_data``)
builds its own beam from the event table, where ``DSL[0]`` was already the first event's row.

So reading the wrong row changed ``det_r`` on beams that nothing inspects: no dose value moved and
no plotted or exported geometry changed. The regression was silent, not merely ungated — which makes
the gate below a value pin rather than a user-visible-break catcher, and the only thing standing
between this invariant and the next change to the envelope loop.
``test_dsl_never_reaches_the_dose_chain`` additionally pins the scope claim, so that if a future
change starts feeding ``det_r`` into the hit mask or a correction, this reasoning is caught rather
than silently inherited.
"""

from __future__ import annotations

import numpy as np
import pytest
from test_rotational_envelope_dose import _frame_with_spin, _run, _settings

from guiskindose.beam_class import Beam

# Distinct per row, so no two rows can be mistaken for each other.
_DSL_BY_ROW = (30, 35, 42)


def _dsl_varied_frame():
    """The rotational two-event frame with per-row detector sizes."""
    frame = _frame_with_spin()
    for row, dsl in enumerate(_DSL_BY_ROW[: len(frame)]):
        frame.at[row, "DSL"] = dsl
    assert float(frame.DSL[0]) != float(frame.DSL[1]), "rows must disagree on DSL for these tests to mean anything"
    return frame


def test_candidates_read_the_parent_events_detector_size(monkeypatch) -> None:
    """Every candidate beam must be sized from its own event's DSL row.

    Captures each ``BeamGeometryInputs`` the envelope hands to
    ``Beam.from_inputs``. Building the record from the full event table instead of
    the index-reset candidate frame would hand it row 0's value, which is the
    regression being pinned.
    """
    frame = _dsl_varied_frame()

    captured: list[float] = []
    import guiskindose.calculate_dose.perform_calculations_for_new_geometries as geometry_module

    real_from_inputs = geometry_module.Beam.from_inputs

    def _recording_from_inputs(inputs, *angles):
        captured.append(inputs.dsl)
        return real_from_inputs(inputs, *angles)

    monkeypatch.setattr(geometry_module.Beam, "from_inputs", staticmethod(_recording_from_inputs))
    _run(frame.copy(), _settings(angular_step_deg=10.0))

    assert captured, "the envelope must build candidate beams through from_inputs"
    assert set(captured) == {float(frame.DSL[1])}


def test_hoisted_candidate_detector_geometry_matches_the_frame_built_beam(monkeypatch) -> None:
    """The hoisted candidate's plotted detector box must be the old one, exactly.

    The direct gate on the regression: capture a candidate beam as the envelope
    builds it, and compare ``det_r`` (and the beam pyramid, for good measure)
    against a beam built the pre-Phase-2 way -- ``Beam`` from a one-row,
    index-reset copy of the parent event. Exact equality, since this is meant to
    be the same arithmetic on the same numbers.
    """
    frame = _dsl_varied_frame()

    captured: list[tuple[tuple[float, float, float], Beam]] = []
    import guiskindose.calculate_dose.perform_calculations_for_new_geometries as geometry_module

    real_from_inputs = geometry_module.Beam.from_inputs

    def _recording_from_inputs(inputs, *angles):
        beam = real_from_inputs(inputs, *angles)
        captured.append(((angles[0], angles[1], angles[2]), beam))
        return beam

    monkeypatch.setattr(geometry_module.Beam, "from_inputs", staticmethod(_recording_from_inputs))
    _run(frame.copy(), _settings(angular_step_deg=10.0))

    assert captured, "the envelope must build candidate beams through from_inputs"

    assert len({angles for angles, _ in captured}) > 1, "the envelope must vary the pose across candidates"

    # The pre-Phase-2 construction, per candidate pose: a one-row frame copied
    # from the parent event, which is what made DSL[0] mean "the parent event's
    # DSL" for the envelope.
    parent_frame = frame.iloc[[1]].reset_index(drop=True)
    for column in ("Ap1", "Ap2", "Ap3"):
        parent_frame[column] = parent_frame[column].astype(float)

    for angles, beam in captured:
        posed = parent_frame.copy()
        posed.at[0, "Ap1"] = angles[0]
        posed.at[0, "Ap2"] = angles[1]
        posed.at[0, "Ap3"] = angles[2]
        legacy = Beam(data_norm=posed, event=0)
        for attribute in ("det_r", "r", "N"):
            np.testing.assert_array_equal(
                getattr(beam, attribute),
                getattr(legacy, attribute),
                err_msg=f"candidate {attribute} differs from the legacy beam at pose {angles}",
            )


def test_static_events_still_read_the_first_rows_detector_size() -> None:
    """The static path keeps its own DSL behaviour; the hoist must not touch it.

    Not a claim that the two sides should agree -- they have never agreed, and
    reconciling them is a numbers change with its own discussion. This pins the
    static side so a future attempt to "fix" one cannot quietly move the other.
    """
    frame = _dsl_varied_frame()

    for event in range(len(frame)):
        # plot_setup zeroes the rotation, so the detector stays axis-aligned and
        # its half-width reads directly as max|det_r[:, 0]| == DSL / 2.
        beam = Beam(data_norm=frame, event=event, plot_setup=True)
        assert float(np.abs(beam.det_r[:, 0]).max()) == pytest.approx(float(frame.DSL[0]) / 2.0)


def test_dsl_never_reaches_the_dose_chain() -> None:
    """Why the dose goldens could not have caught the wrong-row regression.

    ``DSL`` scales ``det_r`` alone. This asserts that directly, so the reason is
    recorded in a test rather than only in prose: if a future change starts
    feeding ``det_r`` into the hit mask or a correction, this goes red and the
    scope note in this module's docstring needs rewriting.
    """
    frame = _dsl_varied_frame()
    baseline = _run(frame.copy(), _settings(angular_step_deg=10.0))

    perturbed = frame.copy()
    perturbed.at[1, "DSL"] = int(perturbed.DSL[1]) + 7
    changed = _run(perturbed, _settings(angular_step_deg=10.0))

    np.testing.assert_array_equal(
        np.asarray(baseline["dose_map"]),
        np.asarray(changed["dose_map"]),
        err_msg="changing the parent event's DSL moved the dose map: DSL now reaches the dose chain",
    )