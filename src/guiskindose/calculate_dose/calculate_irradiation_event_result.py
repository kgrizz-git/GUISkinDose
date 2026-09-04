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
from guiskindose.grid_interp import format_event_indices
from guiskindose.phantom_class import Phantom

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

    for ev in range(event, total_events):
        logger.debug(f"Calculating irradiation event {ev + 1} out of {total_events}")

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

        reported_kerma = float(normalized_data.K_IRP[ev])
        cf = float(kerma_cf[ev]) if ev < len(kerma_cf) else 1.0
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

        if pbar is not None:
            pbar.update()

    if pbar is not None:
        pbar.refresh()

    _emit_beam_miss_summary(
        missed_event_indices, total_events=total_events, settings=settings
    )
    output["missed_event_indices"] = missed_event_indices
    return output
