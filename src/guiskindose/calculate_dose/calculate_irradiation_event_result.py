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
)
from guiskindose.calculate_dose.perform_calculations_for_new_geometries import (
    perform_calculations_for_new_geometries,
)
from guiskindose.calculate_dose.rotational_event import (
    _angular_step,
    _calculate_envelope_event,
    _emit_rotational_summary,
    _include_static,
    _rotational_mode,
    _static_ledger_input,
    _use_envelope,
)
from guiskindose.grid_interp import format_event_indices
from guiskindose.phantom_class import Phantom
from guiskindose.rotational_acquisition import classify_rotational_event
from guiskindose.rotational_envelope import (
    LedgerEventInput,
    build_handling_ledger,
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
                cached_hits=hits,
                cached_table_hits=table_hits,
                cached_field_area=field_area,
                cached_k_isq=k_isq,
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
