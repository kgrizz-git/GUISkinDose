"""Iterates through irradiation events to calculate geometries and skin dose contributions."""

import logging
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline
from tqdm import tqdm

from guiskindose import constants as c
from guiskindose.calculate_dose.add_correction_and_event_dose_to_output import (
    add_corrections_and_event_dose_to_output,
    compute_event_dose_vector,
)
from guiskindose.calculate_dose.perform_calculations_for_new_geometries import (
    perform_calculations_for_new_geometries,
)
from guiskindose.grid_interp import format_event_indices
from guiskindose.phantom_class import Phantom
from guiskindose.rotational_acquisition import classify_rotational_event
from guiskindose.rotational_envelope import (
    CandidateResult,
    HandlingLedger,
    LedgerEventInput,
    build_candidate_domain,
    build_handling_ledger,
    closed_circle_domain,
    evaluate_envelope,
)

if TYPE_CHECKING:
    from guiskindose.settings import PyskindoseSettings

logger = logging.getLogger(__name__)


def _default_mutable_event_state(
    *,
    table_hits: list[bool] | None,
    field_area: list[float] | None,
    k_isq: np.ndarray | None,
    kerma_cf: list[float] | None,
    total_events: int,
) -> tuple[list[bool], list[float], np.ndarray, list[float]]:
    """Normalize optional mutable per-event buffers for the event loop."""
    return (
        [] if table_hits is None else table_hits,
        [] if field_area is None else field_area,
        np.array([]) if k_isq is None else k_isq,
        ([1.0] * total_events if kerma_cf is None else kerma_cf),
    )


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


def _evaluate_candidate(
    *,
    frame: pd.DataFrame,
    candidate_id: str,
    kerma_full: float,
    spline: CubicSpline,
    k_tab_scalar: float,
    corrections_db: str,
    patient: Phantom,
    table: Phantom,
    pad: Phantom,
    n_cells: int,
) -> CandidateResult:
    """Full-K dose response of one candidate pose (no shared-state writes)."""
    hits, table_hits, field_area, k_isq = perform_calculations_for_new_geometries(
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
    if not any(hits):
        return CandidateResult(
            candidate_id=candidate_id,
            dose_vector=np.zeros(n_cells),
            hit_count=0,
            missed=True,
        )
    vector, k_bs, k_med = compute_event_dose_vector(
        event_frame=frame,
        event=0,
        hits=hits,
        table_hits=table_hits,
        field_area=field_area,
        k_isq=k_isq,
        k_bs_spline=spline,
        k_tab_scalar=k_tab_scalar,
        kerma_full=kerma_full,
        corrections_db=corrections_db,
        n_cells=n_cells,
        emit_warnings=False,
    )
    k_bs_vals = np.atleast_1d(np.asarray(k_bs, dtype=float))
    return CandidateResult(
        candidate_id=candidate_id,
        dose_vector=vector,
        hit_count=int(sum(1 for _ in filter(None, hits))),
        missed=False,
        k_bs_min=float(np.min(k_bs_vals)) if k_bs_vals.size else None,
        k_bs_max=float(np.max(k_bs_vals)) if k_bs_vals.size else None,
        k_med=float(k_med),
    )


def _use_envelope(classification: Any, rotational_mode: str) -> bool:
    """Whether an event takes the coverage-envelope path (not legacy static)."""
    return (
        rotational_mode == c.ROTATIONAL_HANDLING_COVERAGE
        and classification.classification == "rotational"
        and classification.usable_endpoints
        and classification.usable_baseline_geometry
    ) or (
        rotational_mode == c.ROTATIONAL_HANDLING_COVERAGE
        and classification.classification == "rotational"
        and not classification.usable_endpoints
        and classification.usable_baseline_geometry
        and classification.confidence in ("coded", "meaning", "text_alias")
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
    total_events: int,
    exam_id: str | None,
    settings: "PyskindoseSettings | None",
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
    rotational_mode: str,
    step_deg: float,
    include_static: bool,
) -> tuple[list[bool], list[bool], list[float], np.ndarray, LedgerEventInput, dict[str, Any], bool]:
    """Evaluate one rotational event as a coverage envelope.

    Returns ``(hits, table_hits, field_area, k_isq, ledger_input, details,
    missed)`` where the geometry arrays are the static-pose evaluation (cache
    continuity for the next event) while the dose map receives the cellwise
    maximum over all candidates. Per-event kerma records are unchanged.
    """
    del rotational_mode  # coverage is established by the caller.
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
    # and the geometry cache; its dose is discarded, never accumulated.
    static_hits, static_table_hits, static_field_area, static_k_isq = (
        perform_calculations_for_new_geometries(
            normalized_data=normalized_data,
            event=ev,
            new_geometry=new_geometry_flag,
            patient=patient,
            table=table,
            pad=pad,
            hits=[],
            table_hits=[],
            field_area=[],
            k_isq=np.array([]),
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

    def _compute(pose_index: int, pose_ap1: float, pose_ap2: float) -> CandidateResult:
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
            return CandidateResult(
                candidate_id=f"candidate_{pose_index}",
                dose_vector=np.zeros(n_cells),
                hit_count=0,
                missed=True,
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
        union_holder.append(candidate_hits)
        return CandidateResult(
            candidate_id=f"candidate_{pose_index}",
            dose_vector=vector,
            hit_count=int(sum(1 for _ in filter(None, candidate_hits))),
            missed=False,
            k_bs_min=float(np.min(k_bs_vals)) if k_bs_vals.size else None,
            k_bs_max=float(np.max(k_bs_vals)) if k_bs_vals.size else None,
            k_med=float(candidate_k_med),
        )

    union_holder: list[list[bool]] = []
    evaluations: list[CandidateResult] = []
    for pose_index, (pose_ap1, pose_ap2) in enumerate(domain.unique_poses):
        evaluations.append(_compute(pose_index, pose_ap1, pose_ap2))
    evaluation = evaluate_envelope(
        evaluations,
        n_cells=n_cells,
        zeros=np.zeros,
        maximum=np.maximum,
        argmax_cell=lambda vector: (int(np.argmax(vector)), float(np.max(vector))),
    )

    output[c.OUTPUT_KEY_DOSE_MAP] += evaluation.dose_vector

    union_hits: list[bool] = [False] * n_cells
    for candidate_hits in union_holder:
        for index, hit in enumerate(candidate_hits):
            union_hits[index] = union_hits[index] or bool(hit)

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
    }
    ledger_input = LedgerEventInput(
        event_index=ev,
        classification=classification,
        requested_handling="Auto",
        effective_handling="coverage",
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
    )
    return static_hits, static_table_hits, static_field_area, static_k_isq, ledger_input, details, missed


def _emit_rotational_summary(ledger: HandlingLedger, *, total_events: int) -> None:
    """One aggregate log line for rotational handling (beam-miss precedent)."""
    if ledger.rotational_count == 0 and ledger.positioner_motion_count == 0:
        return
    fraction = (
        ledger.rotational_kerma / ledger.total_kerma if ledger.total_kerma > 0 else 0.0
    )
    logger.warning(
        "Rotational handling: %d rotational + %d positioner-motion of %d events "
        "(%.1f%% of K_IRP in rotational envelopes); static fallbacks: %s.",
        ledger.rotational_count,
        ledger.positioner_motion_count,
        total_events,
        100.0 * fraction,
        "yes" if ledger.any_fallback_to_static else "no",
    )


def _beam_miss_event_message(
    normalized_data: pd.DataFrame,
    *,
    event: int,
    total_events: int,
    exam_id: str | None,
) -> str:
    """Build the per-event beam-miss warning text for one irradiation event."""
    kVp = float(normalized_data[c.KEY_NORMALIZATION_KVP].iloc[event])
    filter_desc = (
        f"{normalized_data.filter_thickness_Cu.iloc[event]:g} mm Cu + "
        f"{normalized_data.filter_thickness_Al.iloc[event]:g} mm Al"
    )
    field_area_cm2 = (
        float(normalized_data.FS_lat.iloc[event]) * float(normalized_data.FS_long.iloc[event])
    )
    exam_str = f"exam {exam_id}, " if exam_id else ""
    return (
        f"Event {event + 1}/{total_events} ({exam_str}{kVp:.0f} kVp, "
        f"{filter_desc}, field {field_area_cm2:.1f} cm²): "
        f"beam does not intersect patient — check patient offsets and vendor coordinate frame."
    )


def _emit_beam_miss_summary(
    missed_event_indices: list[int],
    *,
    total_events: int,
    settings: "PyskindoseSettings | None",
) -> None:
    """Emit post-loop diagnostics for events that missed the patient phantom."""
    missed_count = len(missed_event_indices)
    if total_events > 0 and missed_count == total_events:
        logger.warning(
            "All %d events missed the patient phantom — "
            "dose map is all zeros; check patient offsets and vendor coordinate frame.",
            total_events,
        )
        return
    if settings is not None and settings.beam_miss_warn == "summary" and 0 < missed_count < total_events:
        logger.warning(
            "Run %d events; %d event(s) missed the patient phantom: %s.",
            total_events,
            missed_count,
            format_event_indices(missed_event_indices),
        )


def calculate_irradiation_event_result(
    normalized_data: pd.DataFrame,
    event: int,
    total_events: int,
    new_geometry: list[bool],
    k_tab: list[float],
    hits: list[bool],
    patient: Phantom,
    table: Phantom,
    pad: Phantom,
    back_scatter_interpolation: list[CubicSpline],
    output: dict[str, Any],
    corrections_db: str,
    table_hits: list[bool] | None = None,
    field_area: list[float] | None = None,
    k_isq: np.ndarray | None = None,
    pbar: tqdm | None = None,
    settings: "PyskindoseSettings | None" = None,
    exam_id: str | None = None,
    kerma_cf: list[float] | None = None,
    source_event_count: int | None = None,
) -> dict[str, Any]:
    """Conducts skin dose calculation.

    This function loops though all irradiation events in the the normalized data, and
    calculates the skin dose contribution from each event.

    Parameters
    ----------
    normalized_data : pd.DataFrame
        RDSR data, normalized for compliance with PySkinDose.
    event : starting event index
        Index of starting irradiation event
    total_events :
        Total number of irradiation events
    new_geometry : List[bool]
        A boolean list that specifies whether the irradiation geometry has changes since
        the preceding event. See the function check_new_geometry
    k_tab : List[float]
        List of table correction factors
    hits : List[bool]
        A boolean list that specifies (for a single event) the hit/miss status of each
        skin cell upon the patient phantom.
    patient : Phantom
        Patient skin surface phantom
    table : Phantom
        Patient support table phantom
    pad : Phantom
        Patient support pad phantom
    back_scatter_interpolation : List[CubicSpline]
        List of interpolation objects to used to estimate backscatter correction from
        the correction database
    output : Dict[str, Any]
        Dictionary containing outputs to store from the calculations. E.g. dose map and
        correction factors.
    corrections_db : str
        A string defining the path to the corrections SQLite db
    table_hits : List[bool], optional
        A boolean list that specfies (for each hit), if the bean passes through the
        patient support table, by default None
    field_area : List[float], optional
        X-ray field area in (cm^2) for each phantom skin cell that are hit by the X-ray
        beam, by default None
    k_isq : np.array, optional
        Inverse-square-law correction factors, by default None
    pbar : tqdm
        progress bar object
    kerma_cf : List[float], optional
        Per-event kerma-meter correction factors (default all 1.0).

    Returns
    -------
    Dict[str, Any]
        Dictionary containing skin dose calculation results.

    """
    table_hits, field_area, k_isq, kerma_cf = _default_mutable_event_state(
        table_hits=table_hits,
        field_area=field_area,
        k_isq=k_isq,
        kerma_cf=kerma_cf,
        total_events=total_events,
    )

    missed_event_indices: list[int] = []
    ledger_inputs: list[LedgerEventInput] = []
    envelope_details: dict[int, dict[str, Any]] = {}
    rotational_mode = _rotational_mode(settings)
    step_deg = _angular_step(settings)
    include_static = _include_static(settings)
    dap_series = normalized_data.get("DoseAreaProduct_Gym2")
    classifications = [classify_rotational_event(dict(normalized_data.iloc[ev])) for ev in range(event, total_events)]

    for loop_index, ev in enumerate(range(event, total_events)):
        logger.debug(f"Calculating irradiation event {ev + 1} out of {total_events}")
        classification = classifications[loop_index]
        row = normalized_data.iloc[ev]

        reported_kerma = float(normalized_data.K_IRP[ev])
        cf = float(kerma_cf[ev]) if ev < len(kerma_cf) else 1.0
        kerma_full = reported_kerma * cf
        try:
            dap_value = None if dap_series is None else dap_series.iloc[ev]
            dap = None if dap_value is None or (isinstance(dap_value, float) and np.isnan(dap_value)) else float(dap_value)
        except (IndexError, KeyError, TypeError, ValueError):
            dap = None

        if _use_envelope(classification, rotational_mode):
            (
                hits,
                table_hits,
                field_area,
                k_isq,
                ledger_input,
                details,
                event_missed,
            ) = _calculate_envelope_event(
                ev=ev,
                row=row,
                classification=classification,
                normalized_data=normalized_data,
                total_events=total_events,
                exam_id=exam_id,
                settings=settings,
                patient=patient,
                table=table,
                pad=pad,
                back_scatter_interpolation=back_scatter_interpolation,
                k_tab=k_tab,
                kerma_full=kerma_full,
                cf=cf,
                reported_kerma=reported_kerma,
                dap=dap,
                corrections_db=corrections_db,
                output=output,
                new_geometry_flag=new_geometry[ev],
                rotational_mode=rotational_mode,
                step_deg=step_deg,
                include_static=include_static,
            )
            ledger_inputs.append(ledger_input)
            envelope_details[ev] = details
            if event_missed:
                missed_event_indices.append(ev)
                msg = _beam_miss_event_message(
                    normalized_data, event=ev, total_events=total_events, exam_id=exam_id
                )
                if settings is not None and settings.beam_miss_warn == "per_event":
                    logger.warning(msg)
        else:
            hits, table_hits, field_area, k_isq = perform_calculations_for_new_geometries(
                normalized_data=normalized_data,
                event=ev,
                new_geometry=new_geometry[ev],
                patient=patient,
                table=table,
                pad=pad,
                hits=hits,
                table_hits=table_hits,
                field_area=field_area,
                k_isq=k_isq,
            )

            if not any(hits):
                missed_event_indices.append(ev)
                msg = _beam_miss_event_message(
                    normalized_data, event=ev, total_events=total_events, exam_id=exam_id
                )
                if settings is not None and settings.beam_miss_warn == "per_event":
                    logger.warning(msg)

            logger.debug("Saving event data")

            output[c.OUTPUT_KEY_HITS][ev] = hits
            output[c.OUTPUT_KEY_KERMA][ev] = reported_kerma
            output[c.OUTPUT_KEY_KERMA_CORRECTED][ev] = reported_kerma * cf
            output[c.OUTPUT_KEY_CORRECTION_KERMA_METER][ev] = cf
            output[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW][ev] = k_isq

            output = add_corrections_and_event_dose_to_output(
                normalized_data=normalized_data,
                event=ev,
                hits=hits,
                table_hits=table_hits,
                patient=patient,
                back_scatter_interpolation=back_scatter_interpolation,
                field_area=field_area,
                k_tab=k_tab,
                output=output,
                corrections_db=corrections_db,
                kerma_cf=cf,
            )
            ledger_inputs.append(
                _static_ledger_input(
                    ev=ev,
                    row=row,
                    classification=classification,
                    rotational_mode=rotational_mode,
                    kerma=reported_kerma,
                    dap=dap,
                )
            )

        if pbar is not None:
            pbar.update()

    if pbar is not None:
        pbar.refresh()

    _emit_beam_miss_summary(
        missed_event_indices, total_events=total_events, settings=settings
    )
    output["missed_event_indices"] = missed_event_indices

    ledger = build_handling_ledger(ledger_inputs)
    output[c.OUTPUT_KEY_ROTATIONAL_HANDLING] = {
        "rows": [
            {
                "event_index": row.event_index,
                "classification": row.classification,
                "reason_codes": list(row.reason_codes),
                "confidence": row.confidence,
                "requested_handling": row.requested_handling,
                "effective_handling": row.effective_handling,
                "fallback_reason": row.fallback_reason,
                "ap1_start": row.ap1_start,
                "ap2_start": row.ap2_start,
                "ap1_end": row.ap1_end,
                "ap2_end": row.ap2_end,
                "primary_separation_deg": row.primary_separation_deg,
                "secondary_separation_deg": row.secondary_separation_deg,
                "candidate_domain": row.candidate_domain,
                "requested_path_count": row.requested_path_count,
                "unique_candidate_count": row.unique_candidate_count,
                "angular_step_deg": row.angular_step_deg,
                "include_static_pose": row.include_static_pose,
                "direction_source": row.direction_source,
                "kerma": row.kerma,
                "dap": row.dap,
                "multiplier": row.multiplier,
                "aggregation_rule": row.aggregation_rule,
            }
            for row in ledger.rows
        ],
        "aggregate": {
            "total_events": ledger.total_events,
            "rotational_count": ledger.rotational_count,
            "positioner_motion_count": ledger.positioner_motion_count,
            "static_count": ledger.static_count,
            "unknown_count": ledger.unknown_count,
            "rotational_kerma": ledger.rotational_kerma,
            "total_kerma": ledger.total_kerma,
            "any_fallback_to_static": ledger.any_fallback_to_static,
        },
        "source_event_count": total_events if source_event_count is None else source_event_count,
        "processed_event_count": total_events,
    }
    output[c.OUTPUT_KEY_ROTATIONAL_ENVELOPE] = envelope_details
    _emit_rotational_summary(ledger, total_events=total_events)
    return output
