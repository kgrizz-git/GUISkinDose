"""Rotational coverage-envelope evaluation for the dose event loop.

Pure helpers plus the per-event envelope evaluator. The main loop in
``calculate_irradiation_event_result`` classifies rows and delegates here;
this module never touches shared output dicts outside what it returns.
"""

import logging
import math
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline

from guiskindose import constants as c
from guiskindose.beam_class import BeamGeometryInputs
from guiskindose.calculate_dose.add_correction_and_event_dose_to_output import (
    compute_event_dose_vector,
)
from guiskindose.calculate_dose.perform_calculations_for_new_geometries import (
    perform_calculations_for_new_geometries,
)
from guiskindose.phantom_class import Phantom
from guiskindose.rotational_acquisition import circular_separation_deg
from guiskindose.rotational_envelope import (
    CandidateResult,
    HandlingLedger,
    LedgerEventInput,
    build_candidate_domain,
    closed_circle_domain,
    evaluate_envelope,
    is_disclosed_row,
)

if TYPE_CHECKING:
    from guiskindose.settings import PyskindoseSettings

logger = logging.getLogger(__name__)

# Pose-match tolerance for recognizing the reported static pose among the
# candidate poses (angles are re-derived through _canonical, so compare on
# the circle rather than by raw float equality).
_STATIC_POSE_TOL_DEG = 1e-9

# Columns a candidate frame must not vary: the C-arm angles Ap1/Ap2 (and Ap3)
# move the beam only, so every candidate of one event shares these and one
# phantom positioning at the parent pose is valid for the whole domain.
# Rx/Ry/Rz are included even though they are derived from At1-At3: they are
# what Phantom.position actually reads, so guarding the derived value as
# well as its inputs keeps the check honest if calculate_rotation_matrices
# ever changes.
_POSE_INVARIANT_COLUMNS: Final[tuple[str, ...]] = ("Tx", "Ty", "Tz", "At1", "At2", "At3", "Rx", "Ry", "Rz")

_ROTATION_MATRIX_COLUMNS: Final[frozenset[str]] = frozenset(("Rx", "Ry", "Rz"))


def _rotational_mode(settings: "PyskindoseSettings | None") -> str:
    if settings is None:
        return c.ROTATIONAL_HANDLING_COVERAGE
    return getattr(settings, "rotational_handling", c.ROTATIONAL_HANDLING_COVERAGE)


def _angular_step(settings: "PyskindoseSettings | None") -> float:
    if settings is None:
        return c.ROTATIONAL_ANGULAR_STEP_DEFAULT
    return float(getattr(settings, "angular_step_deg", c.ROTATIONAL_ANGULAR_STEP_DEFAULT))


def _include_static(settings: "PyskindoseSettings | None") -> bool:
    if settings is None:
        return True
    return bool(getattr(settings, "include_static_pose", True))


def _candidate_frame(parent_row: pd.Series, ap1: float, ap2: float) -> pd.DataFrame:
    """One-row frame copying the parent event with pose angles overridden.

    The index is reset to ``[0]``: downstream geometry code addresses rows
    positionally (``event=0``), and the parent index must not leak through.

    Called once per event (Phase 1g). The result is **not** mutated afterwards:
    since Phase 2 a candidate pose's angles travel as arguments
    (``beam_angles_deg``) rather than being written into this frame, so it holds
    the parent's angles throughout. Two things still need it — the pose-invariant
    guard, which requires a faithful copy to check, and the event frame the
    candidate dose vectors are computed from.

    The index reset is also load-bearing for ``DSL``: ``Beam`` takes detector
    side length at index ``0``, which on this one-row frame is the *parent
    event's* row. See :meth:`BeamGeometryInputs.from_frame`.
    """
    frame = pd.DataFrame([parent_row.values], columns=parent_row.index)
    frame["Ap1"] = ap1
    frame["Ap2"] = ap2
    return frame


def _assert_pose_invariant(parent_row: pd.Series, frame: pd.DataFrame) -> None:
    """Fail loudly if a candidate frame varies a column the pose fix depends on.

    The phantoms are positioned once per event and that positioning is reused
    across the whole candidate domain, which is only sound while candidates
    differ from their parent row in the beam angles alone. Checked once per
    event (Phase 1g builds the frame once per event too), so the cost is
    negligible and a future regression that lets a candidate vary a pose column
    surfaces as a clear error instead of a silently mispositioned phantom.

    Raises
    ------
    RuntimeError
        If any column in :data:`_POSE_INVARIANT_COLUMNS` differs between the
        parent row and the candidate frame. The message names the column but
        never its value: repository privacy rules forbid logging data values.
    """
    for column in _POSE_INVARIANT_COLUMNS:
        parent_value: Any = parent_row[column]
        candidate_value: Any = frame.at[0, column]
        if column in _ROTATION_MATRIX_COLUMNS:
            matches = np.array_equal(
                np.asarray(parent_value, dtype=float),
                np.asarray(candidate_value, dtype=float),
                equal_nan=True,
            )
        else:
            # NaN counts as equal to NaN: a plain != would reject the very case
            # the guard must stay quiet about (an unrecorded table offset).
            parent_number = float(parent_value)
            candidate_number = float(candidate_value)
            matches = parent_number == candidate_number or (math.isnan(parent_number) and math.isnan(candidate_number))
        if not matches:
            raise RuntimeError(
                f"Candidate frame varies pose column {column!r}, which the "
                "once-per-event phantom positioning assumes is constant. "
                "Candidate frames may only override the beam angles."
            )


def _is_contradictory(classification: Any) -> bool:
    """Stationary-coded event with measured endpoint motion (unknown class)."""
    return classification.classification == "unknown" and "contradictory_static" in classification.reason_codes


def _use_envelope(classification: Any, rotational_mode: str) -> bool:
    """Whether an event takes the coverage-envelope path (not legacy static).

    Contradictory (stationary-coded, moving) events with usable endpoints
    also envelop under coverage mode: the measured angles exist, the code
    conflict is disclosed loudly, and the ledger records the contradiction.
    """
    if rotational_mode != c.ROTATIONAL_HANDLING_COVERAGE:
        return False
    if classification.classification == "rotational" and classification.usable_baseline_geometry:
        if classification.usable_endpoints:
            return True
        # Type-only 360 fallback needs a coded/meaning/alias basis, never
        # bare angle inference without endpoints.
        return classification.confidence in ("coded", "meaning", "text_alias")
    return (
        _is_contradictory(classification)
        and classification.usable_endpoints
        and classification.usable_baseline_geometry
    )


def _static_ledger_input(
    *,
    ev: int,
    row: pd.Series,
    classification: Any,
    rotational_mode: str,
    kerma: float,
    dap: float | None,
) -> LedgerEventInput:
    """Ledger entry for a legacy-static calculation (with fallback reason)."""
    if rotational_mode == c.ROTATIONAL_HANDLING_STATIC:
        requested, effective, fallback = "Static", "static", ""
    elif rotational_mode == c.ROTATIONAL_HANDLING_SCENARIOS:
        requested, effective, fallback = "Scenarios", "static", "scenario_mode_deferred"
    elif classification.classification in ("rotational", "positioner_motion"):
        requested, effective, fallback = "Auto", "static", "trajectory_unresolved"
        if "contradictory_static" in classification.reason_codes:
            fallback = "contradictory_static"
        if classification.classification == "positioner_motion":
            fallback = "positioner_motion_needs_override"
    elif _is_contradictory(classification):
        # Reached only under coverage handling without usable endpoints:
        # enveloped contradictories never arrive here.
        requested, effective, fallback = "Auto", "static", "contradictory_static"
    else:
        requested, effective, fallback = "Auto", "static", ""
    return LedgerEventInput(
        event_index=ev,
        classification=classification,
        requested_handling=requested,
        effective_handling=effective,
        fallback_reason=fallback,
        ap1_start=_finite_or_none(row.get("Ap1")),
        ap2_start=_finite_or_none(row.get("Ap2")),
        ap1_end=_finite_or_none(row.get("Ap1_end")),
        ap2_end=_finite_or_none(row.get("Ap2_end")),
        kerma=kerma,
        dap=dap,
    )


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _calculate_envelope_event(
    *,
    ev: int,
    row: pd.Series,
    classification: Any,
    normalized_data: pd.DataFrame,
    patient: Phantom,
    table: Phantom,
    pad: Phantom,
    back_scatter_interpolation: list[CubicSpline],
    k_tab: list[float],
    kerma_full: float,
    cf: float,
    reported_kerma: float,
    dap: float | None,
    corrections_db: str,
    output: dict[str, Any],
    new_geometry_flag: bool,
    step_deg: float,
    include_static: bool,
    cached_hits: Sequence[bool] | np.ndarray,
    cached_table_hits: Sequence[bool] | np.ndarray,
    cached_field_area: Sequence[float] | np.ndarray,
    cached_k_isq: np.ndarray,
) -> tuple[
    Sequence[bool] | np.ndarray,
    Sequence[bool] | np.ndarray,
    Sequence[float] | np.ndarray,
    np.ndarray,
    LedgerEventInput,
    dict[str, Any],
    bool,
]:
    """Evaluate one rotational event as a coverage envelope.

    Returns ``(hits, table_hits, field_area, k_isq, ledger_input, details,
    missed)`` where the geometry arrays are the static-pose evaluation (cache
    continuity for the next event — including the ``new_geometry=False`` reuse
    path, which is why the live cache arrays are threaded in rather than
    rebuilt from empties) while the dose map receives the cellwise maximum
    over all candidates. Per-event kerma records are unchanged.

    The ``cached_*`` arguments accept a boolean array as well as a list of
    booleans (and ``cached_field_area`` an array of floats): the hot path
    carries ndarrays, while the ``new_geometry=False`` path passes the caller's
    own containers straight through. The returned ``hits`` and ``table_hits``
    are boolean arrays on the new-geometry path, mirroring the inputs; the
    published ``output`` slots always hold real Python bools.
    """
    ap1 = float(row["Ap1"])
    ap2 = float(row["Ap2"])
    ap1_end = _finite_or_none(row.get("Ap1_end"))
    ap2_end = _finite_or_none(row.get("Ap2_end"))
    primary_moves = "primary_endpoint_motion" in classification.reason_codes
    secondary_moves = "secondary_endpoint_motion" in classification.reason_codes

    # Candidates never vary Tx/Ty/Tz or At1-At3, so one positioning at the
    # parent pose is valid for the whole domain. Done unconditionally rather
    # than under new_geometry_flag so the candidate loop never depends on
    # the cache invariant.
    patient.position(data_norm=normalized_data, event=ev)
    table.position(data_norm=normalized_data, event=ev)
    pad.position(data_norm=normalized_data, event=ev)

    if primary_moves or secondary_moves:
        domain = build_candidate_domain(
            ap1_start=ap1,
            ap2_start=ap2,
            ap1_end=ap1_end,
            ap2_end=ap2_end,
            primary_moves=primary_moves,
            secondary_moves=secondary_moves,
            step_deg=step_deg,
            include_static_pose=include_static,
            static_ap1=ap1,
            static_ap2=ap2,
        )
        domain_label = "endpoint_paths"
    else:
        domain = closed_circle_domain(ap1_start=ap1, ap2_fixed=ap2, step_deg=step_deg)
        domain_label = "full_circle"

    # Static-pose evaluation first: its arrays feed the legacy per-event slots
    # and the geometry cache, and its dose vector doubles as the static-pose
    # candidate response (see _static_candidate below) so the loop never
    # repeats that geometry/physics work. The live cache arrays are threaded
    # through so a new_geometry=False event reuses the true preceding geometry
    # instead of collapsing to empties.
    static_hits, static_table_hits, static_field_area, static_k_isq = perform_calculations_for_new_geometries(
        normalized_data=normalized_data,
        event=ev,
        new_geometry=new_geometry_flag,
        patient=patient,
        table=table,
        pad=pad,
        hits=cached_hits,
        table_hits=cached_table_hits,
        field_area=cached_field_area,
        k_isq=cached_k_isq,
    )
    static_vector, static_k_bs, static_k_med = compute_event_dose_vector(
        event_frame=normalized_data.iloc[[ev]],
        event=ev,
        hits=static_hits,
        table_hits=static_table_hits,
        field_area=static_field_area,
        k_isq=static_k_isq,
        k_bs_spline=back_scatter_interpolation[ev],
        k_tab_scalar=k_tab[ev],
        kerma_full=kerma_full,
        corrections_db=corrections_db,
        n_cells=len(patient.r),
        emit_warnings=False,
    )

    parent_frame = normalized_data.iloc[[ev]]
    # A one-row faithful copy of the parent, built once for the whole domain
    # (Phase 1g). Since Phase 2 the per-pose angles travel as arguments instead
    # of being written into this frame, so it no longer varies across the loop:
    # what it is still for is the invariant guard below, and as the event frame
    # the candidate dose vectors are computed from (kVp and HVL, which
    # calculate_k_med reads; both are pose-independent).
    candidate_frame = _candidate_frame(parent_frame.iloc[0], ap1, ap2)
    _assert_pose_invariant(parent_frame.iloc[0], candidate_frame)
    # Beam scalars for this event, resolved once for the whole domain (Phase 2).
    # Every candidate shares them -- the pose columns are the only thing
    # _candidate_frame overrides -- so reading them per candidate was reading the
    # same nine DataFrame cells 360 times over.
    #
    # Built from candidate_frame at index 0, NOT from normalized_data at ev.
    # Those agree on every scalar except DSL: BeamGeometryInputs.from_frame takes
    # DSL at index 0 (see its docstring), which on the index-reset candidate frame
    # is the *parent event's* DSL. That is what the candidate loop has always
    # used, because it built its beams from this very frame. Reading it from
    # normalized_data instead would silently switch every enveloped event to the
    # procedure's first-event DSL -- a numbers change, invisible on fixtures
    # whose rows agree on DSL. (Static events still use the first event's DSL;
    # that inconsistency predates this work and is not Phase 2's to settle.)
    beam_inputs = BeamGeometryInputs.from_frame(data_norm=candidate_frame, event=0)
    # Ap3 is a pose column no candidate overrides, so it too is fixed for the
    # domain; read once, alongside the scalars. No index quirk here, so the
    # parent event's row is the obvious place to read it from.
    ap3_deg = float(normalized_data.Ap3[ev])
    spline = back_scatter_interpolation[ev]
    k_tab_scalar = k_tab[ev]
    n_cells = len(patient.r)

    def _compute(pose_index: int, pose_ap1: float, pose_ap2: float) -> tuple[CandidateResult, np.ndarray]:
        candidate_hits_raw, candidate_table_hits, candidate_field_area, candidate_k_isq = (
            perform_calculations_for_new_geometries(
                normalized_data=candidate_frame,
                event=0,
                new_geometry=True,
                patient=patient,
                table=table,
                pad=pad,
                hits=[],
                table_hits=[],
                field_area=[],
                k_isq=np.array([]),
                # Already positioned at the parent pose above, and every
                # candidate shares it.
                reposition=False,
                beam_inputs=beam_inputs,
                beam_angles_deg=(pose_ap1, pose_ap2, ap3_deg),
            )
        )
        # The new-geometry path always hands back an ndarray; asarray is a no-op
        # there and only narrows the declared Sequence|ndarray union. Keeping the
        # raw mask (rather than a list comprehension over it) is what lets the
        # union fold and the hit count both stay vectorized.
        candidate_hits = np.asarray(candidate_hits_raw, dtype=bool)
        # .any(), not sum()/any(): those iterate an ndarray element by element in
        # Python, boxing every value, which is far slower than the reduction.
        if not candidate_hits.any():
            return (
                CandidateResult(
                    candidate_id=f"candidate_{pose_index}",
                    dose_vector=np.zeros(n_cells),
                    hit_count=0,
                    missed=True,
                ),
                candidate_hits,
            )
        vector, candidate_k_bs, candidate_k_med = compute_event_dose_vector(
            event_frame=candidate_frame,
            event=0,
            hits=candidate_hits,
            table_hits=candidate_table_hits,
            field_area=candidate_field_area,
            k_isq=candidate_k_isq,
            k_bs_spline=spline,
            k_tab_scalar=k_tab_scalar,
            kerma_full=kerma_full,
            corrections_db=corrections_db,
            n_cells=n_cells,
            emit_warnings=False,
        )
        k_bs_vals = np.atleast_1d(np.asarray(candidate_k_bs, dtype=float))
        return (
            CandidateResult(
                candidate_id=f"candidate_{pose_index}",
                dose_vector=vector,
                hit_count=int(np.count_nonzero(candidate_hits)),
                missed=False,
                k_bs_min=float(np.min(k_bs_vals)) if k_bs_vals.size else None,
                k_bs_max=float(np.max(k_bs_vals)) if k_bs_vals.size else None,
                k_med=float(candidate_k_med),
            ),
            candidate_hits,
        )

    # An ndarray, not a list: the union is folded once per candidate with a
    # vectorized logical_or (Phase 1e) instead of a Python or-loop over all
    # cells, and the published list is converted once where it is read.
    union_mask = np.zeros(n_cells, dtype=bool)

    def _is_static_pose(pose_ap1: float, pose_ap2: float) -> bool:
        return (
            circular_separation_deg(pose_ap1, ap1) <= _STATIC_POSE_TOL_DEG
            and circular_separation_deg(pose_ap2, ap2) <= _STATIC_POSE_TOL_DEG
        )

    def _static_candidate(pose_index: int) -> tuple[CandidateResult, np.ndarray]:
        """Reuse the slot/static evaluation as that pose's candidate response.

        The reported static pose is always a domain member (path start or the
        ``include_static_pose`` append), and re-evaluating it in the loop would
        repeat identical geometry/physics work already done for the legacy
        slots and the geometry cache.
        """
        if not np.asarray(static_hits, dtype=bool).any():
            return (
                CandidateResult(
                    candidate_id=f"candidate_{pose_index}",
                    dose_vector=static_vector,
                    hit_count=0,
                    missed=True,
                ),
                np.asarray(static_hits, dtype=bool),
            )
        k_bs_vals = np.atleast_1d(np.asarray(static_k_bs, dtype=float))
        return (
            CandidateResult(
                candidate_id=f"candidate_{pose_index}",
                dose_vector=static_vector,
                hit_count=int(np.count_nonzero(static_hits)),
                missed=False,
                k_bs_min=float(np.min(k_bs_vals)) if k_bs_vals.size else None,
                k_bs_max=float(np.max(k_bs_vals)) if k_bs_vals.size else None,
                k_med=float(static_k_med),
            ),
            np.asarray(static_hits, dtype=bool),
        )

    def _generate() -> Any:
        for pose_index, (pose_ap1, pose_ap2) in enumerate(domain.unique_poses):
            if _is_static_pose(pose_ap1, pose_ap2):
                result, candidate_hits = _static_candidate(pose_index)
            else:
                result, candidate_hits = _compute(pose_index, pose_ap1, pose_ap2)
            # asarray so the fold works whether the candidate handed back the
            # raw ndarray or a cached list passthrough.
            np.logical_or(union_mask, np.asarray(candidate_hits, dtype=bool), out=union_mask)
            yield result

    evaluation = evaluate_envelope(
        _generate(),
        n_cells=n_cells,
        zeros=np.zeros,
        # In-place fold: evaluate_envelope only ever reads the accumulator back,
        # and writing into it stops allocating a fresh n_cells array per
        # candidate. The contract ("returns the folded array") still holds --
        # np.maximum with out= returns the first argument.
        maximum=lambda a, b: np.maximum(a, b, out=a),
        # The caller destructures `_, value =` and discards the index, so only
        # the peak value is computed. The two-tuple contract of
        # evaluate_envelope is unchanged; if the index is ever wanted it comes
        # back as a real feature, not as an accidental by-product.
        argmax_cell=lambda vector: (0, float(vector.max())),
    )

    # Restore the parent static pose on the shared phantoms. They already stand
    # there: the candidates never reposition at all, so this is an explicit
    # invariant restore rather than a correction, and the returned phantom plus
    # any intervening cache-dependent reads observe the parent.
    patient.position(data_norm=normalized_data, event=ev)
    table.position(data_norm=normalized_data, event=ev)
    pad.position(data_norm=normalized_data, event=ev)

    output[c.OUTPUT_KEY_DOSE_MAP] += evaluation.dose_vector
    # The envelope vector (cellwise max over candidates, including the reused
    # static-pose response) is the event contribution; the static dose is
    # never accumulated separately.

    # output["hits"] stays the STATIC-pose hit list so it remains index-aligned
    # with the per-hit-cell correction arrays stored below (k_isq and k_bs both
    # have one entry per static hit; PySkinDoseOutput.sparse_hit_indices()
    # pairs them positionally). The candidate union mask — every cell touched by
    # any evaluated pose — is published separately under output["hits_union"],
    # which is a superset and therefore cannot index those arrays.
    # Converted here, once: union_mask is an ndarray, and list(ndarray) would
    # publish np.bool_ elements, which are neither real bools nor JSON
    # serializable.
    union_hits: list[bool] = [bool(hit) for hit in union_mask]

    output[c.OUTPUT_KEY_HITS][ev] = [bool(hit) for hit in static_hits]
    output[c.OUTPUT_KEY_HITS_UNION][ev] = union_hits
    output[c.OUTPUT_KEY_KERMA][ev] = reported_kerma
    output[c.OUTPUT_KEY_KERMA_CORRECTED][ev] = reported_kerma * cf
    output[c.OUTPUT_KEY_CORRECTION_KERMA_METER][ev] = cf
    output[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW][ev] = static_k_isq
    output[c.OUTPUT_KEY_CORRECTION_BACK_SCATTER][ev] = static_k_bs
    output[c.OUTPUT_KEY_CORRECTION_MEDIUM][ev] = static_k_med
    output[c.OUTPUT_KEY_CORRECTION_TABLE][ev] = k_tab[ev]

    winner_ap1: float | None = None
    winner_ap2: float | None = None
    if evaluation.winner_candidate_id is not None:
        try:
            winner_index = int(evaluation.winner_candidate_id.split("_")[1])
            winner_ap1, winner_ap2 = domain.unique_poses[winner_index]
        except (IndexError, ValueError):
            # Malformed candidate id: keep winner_ap1/winner_ap2 as None.
            pass

    missed = evaluation.total_miss
    details = {
        "candidate_domain": domain_label,
        "requested_path_count": len(domain.paths),
        "unique_candidate_count": domain.unique_pose_count,
        "angular_step_deg": step_deg,
        "include_static_pose": include_static,
        "winner_candidate_id": evaluation.winner_candidate_id,
        "winner_ap1": winner_ap1,
        "winner_ap2": winner_ap2,
        "hit_candidate_count": evaluation.hit_candidate_count,
        "partial_miss": 0 < evaluation.hit_candidate_count < evaluation.candidate_count,
        "k_bs_range": list(evaluation.k_bs_range),
        "k_med_range": list(evaluation.k_med_range),
        "direction_source": "unknown",
        "multiplier": 1.0,
        "aggregation_rule": "max_within_sum_between",
        # Semantic split, stated explicitly: output["hits"] and the per-event
        # correction slots both describe the reported static pose, while
        # output["hits_union"] describes every cell touched by any candidate.
        "hits_basis": "static_pose",
        "union_hits_basis": "candidate_union",
        "legacy_correction_basis": "static_pose",
    }
    ledger_input = LedgerEventInput(
        event_index=ev,
        classification=classification,
        requested_handling="Auto",
        effective_handling="coverage",
        # The contradiction is already present in reason_codes; this event
        # ran as coverage, so it did not fall back to static.
        fallback_reason="",
        ap1_start=ap1,
        ap2_start=ap2,
        ap1_end=ap1_end,
        ap2_end=ap2_end,
        candidate_domain=domain_label,
        requested_path_count=len(domain.paths),
        unique_candidate_count=domain.unique_pose_count,
        angular_step_deg=step_deg,
        include_static_pose=include_static,
        direction_source="unknown",
        kerma=reported_kerma,
        dap=dap,
        k_bs_range=evaluation.k_bs_range,
        k_med_range=evaluation.k_med_range,
    )
    return static_hits, static_table_hits, static_field_area, static_k_isq, ledger_input, details, missed


def _emit_rotational_summary(ledger: HandlingLedger) -> None:
    """One aggregate log line for rotational handling (beam-miss precedent).

    The envelope-kerma fraction sums coverage rows only: detection-weighted
    sums would mislabel static-handled kerma as enveloped.
    """
    disclosed = [
        {
            "classification": row.classification,
            "reason_codes": list(row.reason_codes),
            "effective_handling": row.effective_handling,
            "kerma": row.kerma,
        }
        for row in ledger.rows
    ]
    disclosed = [row for row in disclosed if is_disclosed_row(row)]
    if not disclosed:
        return
    enveloped = [row for row in disclosed if row["effective_handling"] == "coverage"]
    envelope_kerma = sum(float(row["kerma"] or 0.0) for row in enveloped)
    contradictory = sum(1 for row in disclosed if "contradictory_static" in row["reason_codes"])
    fraction = envelope_kerma / ledger.total_kerma if ledger.total_kerma > 0 else 0.0
    logger.warning(
        "Rotational handling: %d enveloped of %d disclosed events "
        "(%.1f%% of K_IRP in rotational envelopes); contradictory stationary "
        "declarations: %d; static fallbacks: %s.",
        len(enveloped),
        len(disclosed),
        100.0 * fraction,
        contradictory,
        "yes" if ledger.any_fallback_to_static else "no",
    )
