"""Rotational coverage-envelope evaluation for the dose event loop.

Pure helpers plus the per-event envelope evaluator. The main loop in
``calculate_irradiation_event_result`` classifies rows and delegates here;
this module never touches shared output dicts outside what it returns.
"""

import logging
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline

from guiskindose import constants as c
from guiskindose.calculate_dose.add_correction_and_event_dose_to_output import (
    compute_event_dose_vector,
)
from guiskindose.calculate_dose.perform_calculations_for_new_geometries import (
    perform_calculations_for_new_geometries,
)
from guiskindose.phantom_class import Phantom
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
    """
    frame = pd.DataFrame([parent_row.values], columns=parent_row.index)
    frame["Ap1"] = ap1
    frame["Ap2"] = ap2
    return frame


def _is_contradictory(classification: Any) -> bool:
    """Stationary-coded event with measured endpoint motion (unknown class)."""
    return (
        classification.classification == "unknown"
        and "contradictory_static" in classification.reason_codes
    )


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
        requested, effective, fallback = "Auto", "static", "unusable_domain"
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
    cached_hits: list[bool],
    cached_table_hits: list[bool],
    cached_field_area: list[float],
    cached_k_isq: np.ndarray,
) -> tuple[list[bool], list[bool], list[float], np.ndarray, LedgerEventInput, dict[str, Any], bool]:
    """Evaluate one rotational event as a coverage envelope.

    Returns ``(hits, table_hits, field_area, k_isq, ledger_input, details,
    missed)`` where the geometry arrays are the static-pose evaluation (cache
    continuity for the next event — including the ``new_geometry=False`` reuse
    path, which is why the live cache arrays are threaded in rather than
    rebuilt from empties) while the dose map receives the cellwise maximum
    over all candidates. Per-event kerma records are unchanged.
    """
    ap1 = float(row["Ap1"])
    ap2 = float(row["Ap2"])
    ap1_end = _finite_or_none(row.get("Ap1_end"))
    ap2_end = _finite_or_none(row.get("Ap2_end"))
    primary_moves = "primary_endpoint_motion" in classification.reason_codes
    secondary_moves = "secondary_endpoint_motion" in classification.reason_codes

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
    # and the geometry cache; its dose is discarded, never accumulated. The
    # live cache arrays are threaded through so a new_geometry=False event
    # reuses the true preceding geometry instead of collapsing to empties.
    static_hits, static_table_hits, static_field_area, static_k_isq = (
        perform_calculations_for_new_geometries(
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
    )
    _, static_k_bs, static_k_med = compute_event_dose_vector(
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
    spline = back_scatter_interpolation[ev]
    k_tab_scalar = k_tab[ev]
    n_cells = len(patient.r)

    def _compute(pose_index: int, pose_ap1: float, pose_ap2: float) -> tuple[CandidateResult, list[bool]]:
        frame = _candidate_frame(parent_frame.iloc[0], pose_ap1, pose_ap2)
        candidate_hits, candidate_table_hits, candidate_field_area, candidate_k_isq = (
            perform_calculations_for_new_geometries(
                normalized_data=frame,
                event=0,
                new_geometry=True,
                patient=patient,
                table=table,
                pad=pad,
                hits=[],
                table_hits=[],
                field_area=[],
                k_isq=np.array([]),
            )
        )
        if not any(candidate_hits):
            return (
                CandidateResult(
                    candidate_id=f"candidate_{pose_index}",
                    dose_vector=np.zeros(n_cells),
                    hit_count=0,
                    missed=True,
                ),
                list(candidate_hits),
            )
        vector, candidate_k_bs, candidate_k_med = compute_event_dose_vector(
            event_frame=frame,
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
                hit_count=int(sum(1 for _ in filter(None, candidate_hits))),
                missed=False,
                k_bs_min=float(np.min(k_bs_vals)) if k_bs_vals.size else None,
                k_bs_max=float(np.max(k_bs_vals)) if k_bs_vals.size else None,
                k_med=float(candidate_k_med),
            ),
            list(candidate_hits),
        )

    union_mask: list[bool] = [False] * n_cells

    def _generate() -> Any:
        for pose_index, (pose_ap1, pose_ap2) in enumerate(domain.unique_poses):
            result, candidate_hits = _compute(pose_index, pose_ap1, pose_ap2)
            for index, hit in enumerate(candidate_hits):
                union_mask[index] = union_mask[index] or bool(hit)
            yield result

    evaluation = evaluate_envelope(
        _generate(),
        n_cells=n_cells,
        zeros=np.zeros,
        maximum=np.maximum,
        argmax_cell=lambda vector: (int(np.argmax(vector)), float(np.max(vector))),
    )

    # Restore the parent static pose on the shared phantoms: candidates leave
    # them positioned at the final synthetic pose, and the returned phantom
    # plus any intervening cache-dependent reads must observe the parent.
    patient.position(data_norm=normalized_data, event=ev)
    table.position(data_norm=normalized_data, event=ev)
    pad.position(data_norm=normalized_data, event=ev)

    output[c.OUTPUT_KEY_DOSE_MAP] += evaluation.dose_vector
    # Discard the static-pose dose computed above: the envelope vector is the
    # event contribution. The static evaluation exists only for slots/cache.

    # NOTE for future readers of output["hits"]: this is the candidate UNION
    # mask for enveloped events, not the static-pose hit list (see
    # details["hits_basis"]). Correction tables keyed off hits must account
    # for that; the static-pose corrections in the slots below describe the
    # reported pose only (details["legacy_correction_basis"]).
    union_hits: list[bool] = union_mask

    output[c.OUTPUT_KEY_HITS][ev] = union_hits
    output[c.OUTPUT_KEY_KERMA][ev] = reported_kerma
    output[c.OUTPUT_KEY_KERMA_CORRECTED][ev] = reported_kerma * cf
    output[c.OUTPUT_KEY_CORRECTION_KERMA_METER][ev] = cf
    output[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW][ev] = static_k_isq
    output[c.OUTPUT_KEY_CORRECTION_BACK_SCATTER][ev] = static_k_bs
    output[c.OUTPUT_KEY_CORRECTION_MEDIUM][ev] = static_k_med
    output[c.OUTPUT_KEY_CORRECTION_TABLE][ev] = k_tab[ev]

    winner_index = None
    winner_ap1: float | None = None
    winner_ap2: float | None = None
    if evaluation.winner_candidate_id is not None:
        try:
            winner_index = int(evaluation.winner_candidate_id.split("_")[1])
            winner_ap1, winner_ap2 = domain.unique_poses[winner_index]
        except (IndexError, ValueError):
            winner_index = None

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
        # Semantic split, stated explicitly: the union hit mask describes all
        # cells touched by any candidate, while the legacy per-event
        # correction slots below record the reported static pose only.
        "hits_basis": "candidate_union",
        "legacy_correction_basis": "static_pose",
    }
    ledger_input = LedgerEventInput(
        event_index=ev,
        classification=classification,
        requested_handling="Auto",
        effective_handling="coverage",
        fallback_reason="contradictory_static" if _is_contradictory(classification) else "",
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


