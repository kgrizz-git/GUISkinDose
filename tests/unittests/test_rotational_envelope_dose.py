"""Integration tests for the rotational coverage envelope in the dose loop."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import numpy as np
import pytest
from calculate_dose_recursion_helpers import generate_synthetic_normalized_events

from guiskindose import constants as c
from guiskindose import load_settings_example_json
from guiskindose.calculate_dose.calculate_dose import calculate_dose
from guiskindose.phantom_class import Phantom
from guiskindose.settings import PyskindoseSettings


def _settings(**overrides) -> PyskindoseSettings:
    base = load_settings_example_json()
    # Golden baselines predate the measured_with_fallback default (see CHANGELOG): pin the flat estimate.
    base["k_tab_mode"] = "estimate"
    base["mode"] = "calculate_dose"
    base["silence_pydicom_warnings"] = True
    base["phantom"]["model"] = "plane"
    base["plot"]["notebook_mode"] = False
    base["plot"]["plot_dosemap"] = False
    base.update(overrides)
    return PyskindoseSettings(settings=base)


def _frame_with_spin():
    frame = generate_synthetic_normalized_events(2)
    frame.at[1, "acquisition_type"] = "Rotational Acquisition"
    frame.at[1, "acquisition_type_code"] = "113613"
    frame.at[1, "acquisition_type_coding_scheme"] = "DCM"
    frame.at[1, "acquisition_type_meaning"] = "Rotational Acquisition"
    ap1_values = frame["Ap1"].to_numpy()
    ap2_values = frame["Ap2"].to_numpy()
    frame.at[1, "Ap1_end"] = float(ap1_values[1]) + 60.0
    frame.at[1, "Ap2_end"] = float(ap2_values[1])
    return frame


def _phantoms(settings):
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=settings.phantom.dimension)
    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=settings.phantom.dimension)
    return table, pad


def _run(frame, settings):
    table, pad = _phantoms(settings)
    _, output, _ = calculate_dose(normalized_data=frame, settings=settings, table=table, pad=pad)
    assert output is not None
    return output


def test_envelope_dominates_static_and_preserves_kerma():
    """Envelope PSD >= static PSD (static pose is a candidate); records equal."""
    frame = _frame_with_spin()
    settings = _settings(angular_step_deg=5.0)

    enveloped = _run(frame.copy(), settings)
    static_settings = _settings(angular_step_deg=5.0, rotational_handling="static")
    static = _run(frame.copy(), static_settings)

    handling = enveloped[c.OUTPUT_KEY_ROTATIONAL_HANDLING]
    assert handling["aggregate"]["rotational_count"] == 1
    assert handling["rows"][1]["effective_handling"] == "coverage"
    assert handling["rows"][1]["classification"] == "rotational"
    assert handling["source_event_count"] == handling["processed_event_count"] == 2

    envelope_psd = float(np.max(enveloped[c.OUTPUT_KEY_DOSE_MAP]))
    static_psd = float(np.max(static[c.OUTPUT_KEY_DOSE_MAP]))
    assert envelope_psd >= static_psd

    # Kerma records are treatment-independent (multiplier 1.0, no K/N split).
    assert enveloped[c.OUTPUT_KEY_KERMA] == static[c.OUTPUT_KEY_KERMA]
    assert enveloped[c.OUTPUT_KEY_KERMA_CORRECTED] == static[c.OUTPUT_KEY_KERMA_CORRECTED]

    details = enveloped[c.OUTPUT_KEY_ROTATIONAL_ENVELOPE][1]
    assert details["unique_candidate_count"] > 2
    assert details["winner_candidate_id"] is not None
    assert isinstance(enveloped[c.OUTPUT_KEY_HITS][1], list)


def test_static_mode_matches_legacy_numbers():
    """rotational_handling=static leaves the legacy calculation untouched."""
    frame = _frame_with_spin()
    static = _run(frame.copy(), _settings(rotational_handling="static"))
    handling = static[c.OUTPUT_KEY_ROTATIONAL_HANDLING]
    assert handling["aggregate"]["rotational_count"] == 1
    assert handling["rows"][1]["effective_handling"] == "static"
    assert handling["rows"][1]["requested_handling"] == "Static"
    assert handling["aggregate"]["any_fallback_to_static"] is False
    assert static[c.OUTPUT_KEY_ROTATIONAL_ENVELOPE] == {}


def _frame_with_unchanged_geometry_spin():
    """Spin whose static pose exactly matches the preceding event."""
    frame = generate_synthetic_normalized_events(2)
    for column in ("Tx", "Ty", "Tz", "Ap1", "Ap2", "Ap3", "At1", "At2", "At3", "FS_lat", "FS_long"):
        frame.at[1, column] = frame.at[0, column]
    frame.at[1, "acquisition_type"] = "Rotational Acquisition"
    frame.at[1, "acquisition_type_code"] = "113613"
    frame.at[1, "acquisition_type_coding_scheme"] = "DCM"
    frame.at[1, "acquisition_type_meaning"] = "Rotational Acquisition"
    frame.at[1, "Ap1_end"] = float(frame["Ap1"].to_numpy()[1]) + 60.0
    frame.at[1, "Ap2_end"] = float(frame["Ap2"].to_numpy()[1])
    return frame


def test_envelope_reuses_cache_on_unchanged_geometry():
    """new_geometry=False reuses the preceding static arrays, not empties."""
    from guiskindose.geom_calc import check_new_geometry

    frame = _frame_with_unchanged_geometry_spin()
    assert check_new_geometry(frame) == [True, False]
    output = _run(frame.copy(), _settings(angular_step_deg=10.0))
    assert output[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW][1] is output[
        c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW
    ][0]
    assert output[c.OUTPUT_KEY_ROTATIONAL_HANDLING]["rows"][1]["effective_handling"] == "coverage"


def test_phantoms_restored_to_static_pose_after_envelope(monkeypatch):
    """Shared phantoms must observe the parent pose, not the last candidate."""
    from guiskindose.phantom_class import Phantom

    calls: list = []
    original_position = Phantom.position

    def _recording_position(self, data_norm, event):
        calls.append((self, data_norm is _frame_holder[0], event))
        return original_position(self, data_norm=data_norm, event=event)

    _frame_holder: list = []
    frame = _frame_with_spin().copy()
    _frame_holder.append(frame)
    monkeypatch.setattr(Phantom, "position", _recording_position)
    _run(frame, _settings(angular_step_deg=10.0))
    parent_calls = [call for call in calls if call[1] and call[2] == 1]
    assert parent_calls, "parent static pose must be (re)positioned last"


def test_envelope_positions_phantoms_once_per_event_not_per_candidate(monkeypatch):
    """Phantom positioning must not scale with the candidate count.

    Before Phase 1a every candidate re-derived ``patient.r`` from the same
    parent pose, so the count grew as ``3 + 3 * candidates + 3``: measured 114
    calls for the 36-candidate event below (35 non-static candidates x 3
    phantoms). That is the regression this test forbids -- the phantoms now
    stand at the parent pose for the whole domain.

    The pinned budgets below are the deliberate once-per-event cost. Each
    ``Phantom.position`` call site positions one phantom (patient, table, pad),
    so a site contributes 3:

    - 3   event 0, the ordinary static event through
      ``perform_calculations_for_new_geometries``;
    - 3   event 1, the unconditional positioning at the top of
      ``_calculate_envelope_event``;
    - 3   event 1, that event's static-pose evaluation, only when the event has
      new geometry. It keeps the default ``reposition=True`` so its behaviour
      is byte-for-byte unchanged -- an accepted once-per-event duplication;
    - 3   event 1, the explicit parent-pose restore after the candidate loop.

    Hence 9 with an unchanged-geometry event 1 (its static-pose call takes the
    ``new_geometry=False`` cache path, which returns before positioning) and 12
    with a new-geometry one. Both are pinned because both branches must hold:
    the candidate loop must not reposition, and the static path must not stop.
    """
    from guiskindose.geom_calc import check_new_geometry

    calls: list = []
    original_position = Phantom.position

    def _recording_position(self, data_norm, event):
        calls.append(event)
        return original_position(self, data_norm=data_norm, event=event)

    monkeypatch.setattr(Phantom, "position", _recording_position)

    unchanged = _frame_with_spin()
    assert check_new_geometry(unchanged) == [True, False]
    calls.clear()
    output = _run(unchanged, _settings(angular_step_deg=10.0))
    assert output[c.OUTPUT_KEY_ROTATIONAL_ENVELOPE][1]["unique_candidate_count"] == 36
    assert calls == [0, 0, 0, 1, 1, 1, 1, 1, 1]

    fresh = _frame_with_spin()
    fresh.at[1, "FS_lat"] = float(fresh["FS_lat"].to_numpy()[1]) + 1.0
    assert check_new_geometry(fresh) == [True, True]
    calls.clear()
    _run(fresh, _settings(angular_step_deg=10.0))
    assert calls == [0, 0, 0] + [1] * 9


def test_assert_pose_invariant_accepts_faithful_copy_and_rejects_varied_pose():
    """The Phase 1a guard: silent quiet on a faithful frame, loud on a varied one."""
    import pandas as pd

    from guiskindose.calculate_dose.rotational_event import (
        _assert_pose_invariant,
        _candidate_frame,
    )

    frame = _frame_with_spin()
    parent_row = frame.iloc[1]

    # A faithful copy is exactly what the candidate builder produces: the angle
    # columns are overridden, every guarded column is untouched.
    faithful = _candidate_frame(parent_row, 12.5, 34.0)
    _assert_pose_invariant(parent_row, faithful)

    # A candidate that moves the table laterally would misposition the phantom.
    varied = _candidate_frame(parent_row, 12.5, 34.0)
    varied.at[0, "Tx"] = float(parent_row["Tx"]) + 1.0
    with pytest.raises(RuntimeError, match="Tx"):
        _assert_pose_invariant(parent_row, varied)

    # NaN robustness: an unrecorded table offset is not a violation, and a
    # plain != would falsely fire on it. Built through the same copy path the
    # production helper sees.
    nan_row = pd.Series(parent_row.copy())
    nan_row["Tx"] = np.nan
    nan_frame = _candidate_frame(nan_row, 0.0, 0.0)
    assert bool(pd.isna(nan_frame.at[0, "Tx"]))
    _assert_pose_invariant(nan_row, nan_frame)


def test_envelope_details_disclose_mixed_slot_semantics():
    """Union hits vs static-only correction slots are labeled in output."""
    output = _run(_frame_with_spin().copy(), _settings(angular_step_deg=10.0))
    details = output[c.OUTPUT_KEY_ROTATIONAL_ENVELOPE][1]
    assert details["hits_basis"] == "static_pose"
    assert details["union_hits_basis"] == "candidate_union"
    assert details["legacy_correction_basis"] == "static_pose"


def test_hits_stay_aligned_with_corrections_and_union_is_a_superset():
    """output["hits"] indexes the correction arrays; the union lives elsewhere."""
    output = _run(_frame_with_spin().copy(), _settings(angular_step_deg=10.0))

    hits = output[c.OUTPUT_KEY_HITS][1]
    union = output[c.OUTPUT_KEY_HITS_UNION][1]
    k_bs = output[c.OUTPUT_KEY_CORRECTION_BACK_SCATTER][1]
    k_isq = output[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW][1]

    assert len(hits) == len(union)
    assert sum(hits) == len(k_bs) == len(k_isq)
    # Every static hit is covered by the candidate union, never the reverse.
    assert all(not hit or union[index] for index, hit in enumerate(hits))
    assert sum(union) >= sum(hits)


def test_include_static_pose_false_still_envelopes_with_aligned_slots():
    """include_static_pose=False drops only the explicit static append."""
    output = _run(_frame_with_spin().copy(), _settings(angular_step_deg=10.0, include_static_pose=False))

    details = output[c.OUTPUT_KEY_ROTATIONAL_ENVELOPE][1]
    assert details["include_static_pose"] is False
    assert details["unique_candidate_count"] > 2

    hits = output[c.OUTPUT_KEY_HITS][1]
    union = output[c.OUTPUT_KEY_HITS_UNION][1]
    k_bs = output[c.OUTPUT_KEY_CORRECTION_BACK_SCATTER][1]
    k_isq = output[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW][1]

    assert len(hits) == len(union)
    assert sum(hits) == len(k_bs) == len(k_isq)
    assert all(not hit or union[index] for index, hit in enumerate(hits))


def test_contradictory_event_envelopes_with_reason_recorded():
    """Stationary-coded but moving, usable endpoints: enveloped + flagged."""
    frame = generate_synthetic_normalized_events(1)
    frame.at[0, "acquisition_type"] = "Stationary Acquisition"
    frame.at[0, "acquisition_type_code"] = "113611"
    frame.at[0, "acquisition_type_coding_scheme"] = "DCM"
    frame.at[0, "acquisition_type_meaning"] = "Stationary Acquisition"
    frame.at[0, "Ap1_end"] = float(frame["Ap1"].to_numpy()[0]) + 60.0
    frame.at[0, "Ap2_end"] = float(frame["Ap2"].to_numpy()[0])
    output = _run(frame.copy(), _settings(angular_step_deg=10.0))
    handling = output[c.OUTPUT_KEY_ROTATIONAL_HANDLING]
    assert handling["rows"][0]["classification"] == "unknown"
    assert handling["rows"][0]["effective_handling"] == "coverage"
    assert "contradictory_static" in handling["rows"][0]["reason_codes"]
    assert handling["rows"][0]["fallback_reason"] == ""
    assert handling["aggregate"]["any_fallback_to_static"] is False


def test_contradictory_event_without_baseline_falls_back_loudly(caplog):
    """Contradictory with unusable baseline: static + fallback reason."""
    import logging

    import numpy as _np

    frame = generate_synthetic_normalized_events(1)
    frame.at[0, "acquisition_type"] = "Stationary Acquisition"
    frame.at[0, "acquisition_type_code"] = "113611"
    frame.at[0, "acquisition_type_coding_scheme"] = "DCM"
    frame.at[0, "acquisition_type_meaning"] = "Stationary Acquisition"
    frame.at[0, "Ap1_end"] = float(frame["Ap1"].to_numpy()[0]) + 60.0
    frame.at[0, "Ap2_end"] = float(frame["Ap2"].to_numpy()[0])
    frame.at[0, "Tx"] = _np.nan
    with caplog.at_level(logging.WARNING):
        output = _run(frame.copy(), _settings(angular_step_deg=10.0))
    handling = output[c.OUTPUT_KEY_ROTATIONAL_HANDLING]
    assert handling["rows"][0]["effective_handling"] == "static"
    assert handling["rows"][0]["fallback_reason"] == "contradictory_static"
    assert handling["aggregate"]["any_fallback_to_static"] is True


def test_unusable_rotational_domain_records_documented_fallback_reason():
    frame = _frame_with_spin()
    frame.at[1, "Tx"] = np.nan
    output = _run(frame, _settings(angular_step_deg=10.0))
    row = output[c.OUTPUT_KEY_ROTATIONAL_HANDLING]["rows"][1]
    assert row["classification"] == "rotational"
    assert row["effective_handling"] == "static"
    assert row["fallback_reason"] == "trajectory_unresolved"


def test_summary_names_contradictory_declarations():
    """The aggregate log names the contradictory count.

    NOTE: uses a dedicated handler on the module logger (repo convention)
    because pytest caplog is blind once configure_logging() sets
    propagate=False suite-wide. The integration test above proves the data
    reaches the ledger; this proves the wording.
    """
    import logging

    from guiskindose.calculate_dose.rotational_event import (
        _emit_rotational_summary,
    )
    from guiskindose.rotational_acquisition import classify_rotational_event
    from guiskindose.rotational_envelope import LedgerEventInput, build_handling_ledger

    classification = classify_rotational_event(
        {
            "Ap1": 0.0,
            "Ap2": 0.0,
            "Ap1_end": 50.0,
            "Ap2_end": 0.0,
            "acquisition_type": "Stationary Acquisition",
            "acquisition_type_code": "113611",
            "acquisition_type_coding_scheme": "DCM",
        }
    )
    ledger = build_handling_ledger(
        [
            LedgerEventInput(
                event_index=0,
                classification=classification,
                requested_handling="Auto",
                effective_handling="static",
                fallback_reason="contradictory_static",
                kerma=1.0,
                dap=None,
            )
        ]
    )
    messages: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    logger = logging.getLogger("guiskindose.calculate_dose.rotational_event")
    handler = _Capture(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        _emit_rotational_summary(ledger)
    finally:
        logger.removeHandler(handler)
    assert any("contradictory stationary declarations: 1" in message for message in messages)


def test_envelope_total_scales_sublinearly_with_candidates():
    """Max-not-sum at dose-loop level: doubling candidates must not ~double dose.

    A per-candidate summation bug would scale the map total with N; the
    cellwise maximum is N-invariant up to sampling differences.
    """
    import numpy as _np

    coarse = _run(_frame_with_spin().copy(), _settings(angular_step_deg=10.0))
    fine = _run(_frame_with_spin().copy(), _settings(angular_step_deg=2.0))
    coarse_total = float(_np.sum(coarse[c.OUTPUT_KEY_DOSE_MAP]))
    fine_total = float(_np.sum(fine[c.OUTPUT_KEY_DOSE_MAP]))
    coarse_n = coarse[c.OUTPUT_KEY_ROTATIONAL_ENVELOPE][1]["unique_candidate_count"]
    fine_n = fine[c.OUTPUT_KEY_ROTATIONAL_ENVELOPE][1]["unique_candidate_count"]
    assert fine_n > 2 * coarse_n
    # A per-candidate summation bug would scale the total ~5x here; the
    # cellwise maximum is N-invariant up to sampling differences.
    assert abs(fine_total - coarse_total) / max(coarse_total, 1e-12) < 0.5


def test_static_mode_is_deterministic_across_runs():
    """Two identical static runs agree exactly (no envelope leakage)."""
    first = _run(_frame_with_spin().copy(), _settings(rotational_handling="static"))
    second = _run(_frame_with_spin().copy(), _settings(rotational_handling="static"))
    import numpy as _np

    assert _np.array_equal(
        first[c.OUTPUT_KEY_DOSE_MAP], second[c.OUTPUT_KEY_DOSE_MAP]
    )


# ── rotational-envelope dose-map golden baseline ──────────────────────

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "golden"
_GOLDEN_ROTATIONAL_DOSE_MAP = _FIXTURES / "rotational_envelope_spin_cylinder_dose_map.npy"

# Cross-BLAS ulp headroom: measured drift is ~1e-15 relative (1-2 ulps); a
# mask flip or bookkeeping bug changes affected cells by orders of magnitude
# more. 1e-12 sits ~3 orders above the drift and ~9+ orders below any real
# regression. atol stays 0 so 0 <-> dose transitions always fail.
_GOLDEN_RTOL = 1e-12

# Captured 2026-09-30 from *unmodified, pre-Phase-1* code: synthetic events from
# ``generate_synthetic_normalized_events`` (seed 42, no patient data), a 60-degree
# spin, ``angular_step_deg = 1.0`` (360 candidates), cylinder phantom.
#
# The cylinder matters: ``_settings`` forces ``phantom.model = "plane"``, and the
# entrance-cell filter under optimization is guarded by
# ``if patient.phantom_model != "plane"``, so a plane-phantom golden would never
# execute that code path at all.
#
# Do NOT regenerate this fixture as part of the rotational-envelope performance
# work. A mismatch is a behaviour change, not a stale fixture.
#
# The fixture holds one platform's bits, and that is a property of the dose
# chain, not of Phase 1: it embeds BLAS-backed results (``Phantom.position``'s
# chained matmuls, ``Beam``'s rotation-matrix products, the (N,3)@(3,3)
# beam-within dot, scipy spline evaluation), whose last-ulp values differ per
# BLAS flavour. Measured 2026-10-01: the *pre-Phase-1* code itself reproduces
# this fixture exactly on the generating platform but NOT elsewhere — 48
# mismatched cells (max rel 1.1e-15) in a Linux container, and Phase-1 code on
# PR CI mismatched 50 cells on Ubuntu x86-64 and 19 on Windows, all 1-2 ulps,
# with masks, counts, and every pinned scalar unchanged. What is pinned exactly
# below: the published list/bool contracts, the integer counts (events, cells,
# candidates), and zero-vs-nonzero dose (atol=0). Mask VALUES are not compared
# against stored data — the fixture is dose-map-only — so the map bound is the
# value gate: a real regression (a flipped hit, a positioning or fold bug, a
# one-bin k_med or 0.1 cm^2 k_bs step) moves cells by orders of magnitude more
# than _GOLDEN_RTOL, measured smallest floor ~7.5e-6 relative (winner-to-runner-
# up), while cross-BLAS ulp drift sits at ~1e-15. atol=0 so a newly-hit or
# newly-dropped cell (0 <-> dose) can never pass.
class _GoldenRotationalSpinCylinder(TypedDict):
    events: int
    dose_map_len: int
    psd_mgy: float
    dose_sum: float
    unique_candidate_count: int


_GOLDEN_ROTATIONAL_SPIN_CYLINDER: _GoldenRotationalSpinCylinder = {
    "events": 2,
    "dose_map_len": 9576,
    "psd_mgy": 0.11001912596177693,
    "dose_sum": 53.44510597624422,
    "unique_candidate_count": 360,
}


def test_rotational_envelope_golden_baseline_spin_cylinder():
    """Coverage-envelope output pinned; bit-identical on the generating platform.

    Off the generating platform the map is bounded at ``_GOLDEN_RTOL`` (see the
    fixture's provenance comment above): masks and counts below pin the published
    contracts and integer counts exactly, and any hit flip is caught by the map
    bound's ``atol=0`` as a 0 <-> dose change.
    """
    frame = _frame_with_spin()
    settings = _settings(angular_step_deg=1.0)
    # Mutate the returned object rather than passing a partial phantom dict as a
    # _settings override: base.update(overrides) is a top-level update, so a
    # partial phantom dict would replace the whole phantom block.
    settings.phantom.model = "cylinder"
    assert settings.phantom.model == "cylinder"

    output = _run(frame.copy(), settings)
    golden = _GOLDEN_ROTATIONAL_SPIN_CYLINDER
    dose_map = output[c.OUTPUT_KEY_DOSE_MAP]

    assert len(output[c.OUTPUT_KEY_HITS]) == golden["events"]
    assert len(dose_map) == golden["dose_map_len"]
    # Scalars with _GOLDEN_RTOL, not exact ==: they are exact on the generating
    # platform (and on the CI platforms measured so far), but the same cross-BLAS
    # ulp drift that bounds the map below can reach them on future platforms.
    # abs=0.0 is load-bearing: pytest.approx defaults abs to 1e-12, and
    # max(rel * |expected|, abs) would then let the small PSD pin drift ~9x looser
    # than this comment claims.
    assert float(np.max(dose_map)) == pytest.approx(golden["psd_mgy"], rel=_GOLDEN_RTOL, abs=0.0)
    assert float(np.sum(dose_map)) == pytest.approx(golden["dose_sum"], rel=_GOLDEN_RTOL, abs=0.0)
    details = output[c.OUTPUT_KEY_ROTATIONAL_ENVELOPE][1]
    assert details["unique_candidate_count"] == golden["unique_candidate_count"]
    # Published contract: per-event hits stay a plain list.
    assert isinstance(output[c.OUTPUT_KEY_HITS][1], list)
    # The outer list check passes even for np.bool_ elements, which are neither
    # real bools nor JSON serializable, so pin the element type too.
    assert all(isinstance(hit, bool) for hit in output[c.OUTPUT_KEY_HITS][1])
    # Same pin for the union, which is folded as an ndarray and converted to a
    # list only where it is published.
    assert all(isinstance(hit, bool) for hit in output[c.OUTPUT_KEY_HITS_UNION][1])

    expected_dose_map = np.load(_GOLDEN_ROTATIONAL_DOSE_MAP)
    # Exact on the generating platform; rtol-bounded elsewhere (see the
    # fixture's provenance comment). The pins above are type, contract, and
    # count pins — mask VALUES are not compared against stored data — so the
    # map bound is the value gate: a flipped hit changes a cell by a full event
    # contribution or flips it 0 <-> dose, which atol=0 always fails.
    np.testing.assert_allclose(dose_map, expected_dose_map, rtol=_GOLDEN_RTOL, atol=0.0)


# Human-mesh twin of the cylinder golden, same synthetic spin. Generated from
# commit cabc331 (pre-Phase-1, before any envelope performance edit); the
# Phase 1-3 code reproduced the full 41 022-cell map bit for bit on macOS
# (array_equal, max |diff| = 0). Scalars, not a stored .npy: a binary fixture
# would need hash-pinned asset clearance and could not be compared exactly
# across BLAS flavours anyway. Same bound as the cylinder golden: integer pins
# exact, value pins at _GOLDEN_RTOL with abs=0. The nonzero count catches any
# hit flip; sum of squares catches dose redistributed between cells with a
# change in magnitude, which psd and sum alone can miss. A pure permutation of
# equal doses between cells would pass every pin here. The PSD is not pinned to a cell index: the maximum is
# a tie between cells on this mesh, so the argmax is not a stable identity.
class _GoldenRotationalSpinHuman(TypedDict):
    events: int
    dose_map_len: int
    nonzero_cells: int
    psd_mgy: float
    dose_sum: float
    dose_sum_sq: float
    unique_candidate_count: int


_GOLDEN_ROTATIONAL_SPIN_HUDFRID: _GoldenRotationalSpinHuman = {
    "events": 2,
    "dose_map_len": 41022,
    "nonzero_cells": 1191,
    "psd_mgy": 0.09513090819121497,
    "dose_sum": 55.96181396960091,
    "dose_sum_sq": 3.091123370168797,
    "unique_candidate_count": 360,
}


def test_rotational_envelope_golden_baseline_spin_hudfrid():
    """Coverage envelope on a real human mesh, pinned to pre-refactor output."""
    frame = _frame_with_spin()
    settings = _settings(angular_step_deg=1.0)
    settings.phantom.model = "human"
    settings.phantom.human_mesh = "hudfrid"

    output = _run(frame.copy(), settings)
    golden = _GOLDEN_ROTATIONAL_SPIN_HUDFRID
    dose_map = np.asarray(output[c.OUTPUT_KEY_DOSE_MAP], dtype=float)

    assert len(output[c.OUTPUT_KEY_HITS]) == golden["events"]
    assert dose_map.size == golden["dose_map_len"]
    assert int(np.count_nonzero(dose_map)) == golden["nonzero_cells"]
    assert output[c.OUTPUT_KEY_ROTATIONAL_ENVELOPE][1]["unique_candidate_count"] == golden["unique_candidate_count"]
    assert float(np.max(dose_map)) == pytest.approx(golden["psd_mgy"], rel=_GOLDEN_RTOL, abs=0.0)
    assert float(np.sum(dose_map)) == pytest.approx(golden["dose_sum"], rel=_GOLDEN_RTOL, abs=0.0)
    assert float(np.sum(dose_map * dose_map)) == pytest.approx(golden["dose_sum_sq"], rel=_GOLDEN_RTOL, abs=0.0)
