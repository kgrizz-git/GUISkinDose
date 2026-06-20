import logging
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from mypyskindose import constants as c
from mypyskindose.calculate_dose.calculate_irradiation_event_result import (
    calculate_irradiation_event_result,
)
from mypyskindose.corrections import calculate_k_bs, calculate_k_tab
from mypyskindose.geom_calc import (
    apply_below_floor_kvp_policy,
    check_new_geometry,
    fetch_and_append_hvl,
    position_patient_phantom_on_table,
)
from mypyskindose.phantom_class import Phantom
from mypyskindose.settings import PyskindoseSettings

logger = logging.getLogger(__name__)


def calculate_dose(
    normalized_data: pd.DataFrame,
    settings: PyskindoseSettings,
    table: Phantom,
    pad: Phantom,
) -> Tuple[Optional[Phantom], Optional[Dict[str, Any]]]:
    """Calculate skin dose.

    This function initializes the skin dose calculations.

    Parameters
    ----------
    normalized_data : pd.DataFrame
        RDSR data, normalized for compliance with PySkinDose.
    settings : PyskindoseSettings
        Settings class for PySkinDose
    table : Phantom
        Patient support table phantom
    pad : Phantom
        Patient support pad phantom

    Returns
    -------
    Tuple[Phantom, Optional[Dict[str, Any]]]
        [description]

    """
    if settings.mode != c.MODE_CALCULATE_DOSE and settings.mode != c.MODE_PLOT_DOSEMAP:
        logger.debug("Mode not set to calculate dose. Returning without doing anything")
        return None, None

    logger.info("Start performing dose calculations")
    patient = Phantom(
        phantom_model=settings.phantom.model,
        phantom_dim=settings.phantom.dimension,
        human_mesh=settings.phantom.human_mesh,
    )

    # position objects in starting position
    position_patient_phantom_on_table(
        patient=patient,
        table=table,
        pad=pad,
        pad_thickness=settings.phantom.dimension.pad_thickness,
        patient_offset=[
            settings.phantom.patient_offset.d_lon,
            settings.phantom.patient_offset.d_ver,
            settings.phantom.patient_offset.d_lat,
        ],
        patient_orientation=settings.phantom.patient_orientation,
    )

    # Resolve events with kVp below the HVL table floor per the user's policy
    # (skip / manual / exam_average), before the HVL lookup sees them. Default
    # 'snap' is a no-op here — fetch_and_append_hvl clamps + flags such events.
    # calculate_dose runs once per exam, so 'exam_average' is naturally per-exam.
    normalized_data = apply_below_floor_kvp_policy(
        data_norm=normalized_data,
        policy=settings.below_floor_kvp_policy,
        manual_kvp=settings.below_floor_kvp_manual,
    )

    normalized_data = fetch_and_append_hvl(
        data_norm=normalized_data,
        inherent_filtration=settings.inherent_filtration,
        corrections_db=settings.corrections_db_path,
    )

    # Check which irradiation events that contains updated
    # geometry parameters since the previous irradiation event
    new_geometry = check_new_geometry(normalized_data)

    # fetch of k_bs interpolation object (k_bs=f(field_size))for all events
    back_scatter_interpolation = calculate_k_bs(data_norm=normalized_data)

    k_tab = calculate_k_tab(
        data_norm=normalized_data,
        estimate_k_tab=settings.estimate_k_tab,
        k_tab_val=settings.k_tab_val,
        corrections_db=settings.corrections_db_path,
    )

    total_number_of_events = len(normalized_data)

    if settings.plot.notebook_mode:
        from tqdm import tqdm_notebook as pbar
    else:
        from tqdm import tqdm as pbar

    output_template = _build_output_template(
        total_number_of_events=total_number_of_events, dose_map_size=len(patient.r)
    )

    output = calculate_irradiation_event_result(
        normalized_data=normalized_data,
        event=0,
        total_events=len(normalized_data),
        new_geometry=new_geometry,
        k_tab=k_tab,
        hits=[],
        patient=patient,
        table=table,
        pad=pad,
        back_scatter_interpolation=back_scatter_interpolation,
        output=output_template,
        pbar=pbar(total=total_number_of_events, leave=False, desc="calculating skindose"),
        corrections_db=settings.corrections_db_path,
    )

    return patient, output


def _build_output_template(total_number_of_events: int, dose_map_size: int) -> Dict[str, Any]:
    """Build the per-event output dictionary with type-accurate placeholders.

    Each per-event slot is overwritten by :func:`calculate_irradiation_event_result`
    and :func:`add_corrections_and_event_dose_to_output` on every event. Zero-hit
    events are handled explicitly in the latter; placeholders are nonetheless
    chosen to match each slot's final type and to avoid the ``[[]] * N`` /
    ``[np.array] * N`` shared-reference traps that would surface if a future
    change ever read or mutated a slot before its first assignment.
    """
    return {
        c.OUTPUT_KEY_HITS: [[] for _ in range(total_number_of_events)],
        c.OUTPUT_KEY_KERMA: [0.0] * total_number_of_events,
        c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW: [
            np.array([]) for _ in range(total_number_of_events)
        ],
        c.OUTPUT_KEY_CORRECTION_BACK_SCATTER: [np.array([]) for _ in range(total_number_of_events)],
        c.OUTPUT_KEY_CORRECTION_MEDIUM: [0.0] * total_number_of_events,
        c.OUTPUT_KEY_CORRECTION_TABLE: [0.0] * total_number_of_events,
        c.OUTPUT_KEY_DOSE_MAP: np.zeros(dose_map_size),
    }
