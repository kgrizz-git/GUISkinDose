import logging
from typing import Any, Dict, List, TYPE_CHECKING

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline
from tqdm import tqdm

from mypyskindose import constants as c
from mypyskindose.grid_interp import format_event_indices
from mypyskindose.phantom_class import Phantom
from mypyskindose.calculate_dose.add_correction_and_event_dose_to_output import (
    add_corrections_and_event_dose_to_output,
)
from mypyskindose.calculate_dose.perform_calculations_for_new_geometries import (
    perform_calculations_for_new_geometries,
)

if TYPE_CHECKING:
    from mypyskindose.settings import PyskindoseSettings

logger = logging.getLogger(__name__)


def calculate_irradiation_event_result(
    normalized_data: pd.DataFrame,
    event: int,
    total_events: int,
    new_geometry: List[bool],
    k_tab: List[float],
    hits: List[bool],
    patient: Phantom,
    table: Phantom,
    pad: Phantom,
    back_scatter_interpolation: List[CubicSpline],
    output: Dict[str, Any],
    corrections_db: str,
    table_hits: List[bool] | None = None,
    field_area: List[float] | None = None,
    k_isq: np.ndarray | None = None,
    pbar: tqdm | None = None,
    settings: "PyskindoseSettings | None" = None,
    exam_id: str | None = None,
    kerma_cf: List[float] | None = None,
) -> Dict[str, Any]:
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
    if table_hits is None:
        table_hits = []
    if field_area is None:
        field_area = []
    if k_isq is None:
        k_isq = np.array([])
    if kerma_cf is None:
        kerma_cf = [1.0] * total_events

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

            # positional .iloc — safer than label-based [ev] (redundant given
            # rdsr_normalizer's guaranteed RangeIndex, but defensive for warnings)
            kVp = float(normalized_data[c.KEY_NORMALIZATION_KVP].iloc[ev])
            filter_desc = (
                f"{normalized_data.filter_thickness_Cu.iloc[ev]:g} mm Cu + "
                f"{normalized_data.filter_thickness_Al.iloc[ev]:g} mm Al"
            )
            # float() wraps guard against NaN in corrupted data (rare but defensive)
            # Note: float(np.nan) → nan, which displays as "field nan cm²" — acceptable
            # in a warning context; the value won't crash the format string.
            field_area_cm2 = (
                float(normalized_data.FS_lat.iloc[ev])
                * float(normalized_data.FS_long.iloc[ev])
            )

            exam_str = f"exam {exam_id}, " if exam_id else ""
            msg = (
                f"Event {ev + 1}/{total_events} ({exam_str}{kVp:.0f} kVp, "
                f"{filter_desc}, field {field_area_cm2:.1f} cm²): "
                f"beam does not intersect patient — check patient offsets and vendor coordinate frame."
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

    # Post-loop diagnostics
    K = len(missed_event_indices)
    if total_events > 0 and K == total_events:
        logger.warning(
            "All %d events missed the patient phantom — "
            "dose map is all zeros; check patient offsets and vendor coordinate frame.",
            total_events,
        )
    elif settings is not None and settings.beam_miss_warn == "summary" and 0 < K < total_events:
        logger.warning(
            "Run %d events; %d event(s) missed the patient phantom: %s.",
            total_events,
            K,
            format_event_indices(missed_event_indices),
        )

    output["missed_event_indices"] = missed_event_indices

    return output
