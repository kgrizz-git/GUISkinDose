"""Initialization and orchestration of the main dose calculation loop."""

import logging
from typing import Any

import numpy as np
import pandas as pd

from guiskindose import constants as c
from guiskindose.calculate_dose.calculate_irradiation_event_result import (
    calculate_irradiation_event_result,
)
from guiskindose.corrections import calculate_k_bs, calculate_k_tab
from guiskindose.geom_calc import (
    apply_below_floor_kvp_policy,
    check_new_geometry,
    fetch_and_append_hvl,
    position_patient_phantom_on_table,
)
from guiskindose.kerma_correction import (
    all_ones_correction,
    distinct_auto_resolved_equipment_keys,
    load_correction_table,
    merge_tables,
    resolve_correction_factors,
)
from guiskindose.phantom_class import Phantom
from guiskindose.settings import PyskindoseSettings

logger = logging.getLogger(__name__)


def _resolve_kerma_meter_cf(
    normalized_data: pd.DataFrame,
    settings: PyskindoseSettings,
) -> list[float]:
    """Resolve per-event kerma-meter CF; skip I/O when disabled."""
    km = settings.kerma_meter_correction
    n = len(normalized_data)
    if not km.enable:
        return all_ones_correction(n).factors

    file_table = None
    table_meta: dict[str, object] | None = None
    if km.mode == "prompt" and km.in_memory_table is None:
        # Non-GUI / prompt without a confirmed table → fail-soft.
        logger.warning(
            "kerma-meter correction: mode=prompt without an in-memory table; "
            "using default_factor=%.4g for all events.",
            km.default_factor,
        )
    elif km.file is not None:
        try:
            file_table = load_correction_table(km.file, km.file_sheet)
            table_meta = {"source_stem": km.file.stem}
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            logger.warning(
                "kerma-meter correction: failed to load table (%s); "
                "using default_factor=%.4g.",
                type(exc).__name__,
                km.default_factor,
            )

    if km.explicit_label:
        auto_keys = distinct_auto_resolved_equipment_keys(normalized_data)
        if len(auto_keys) > 1:
            logger.warning(
                "kerma-meter correction: explicit_label collapses %d distinct "
                "auto-resolved equipment keys onto one label.",
                len(auto_keys),
            )

    table = merge_tables(file_table, km.in_memory_table)
    result = resolve_correction_factors(
        normalized_data,
        table,
        explicit_label=km.explicit_label,
        default_factor=km.default_factor,
        table_metadata=table_meta,
    )
    return result.factors


def calculate_dose(
    normalized_data: pd.DataFrame,
    settings: PyskindoseSettings,
    table: Phantom,
    pad: Phantom,
    exam_id: str | None = None,
) -> tuple[Phantom | None, dict[str, Any] | None, pd.DataFrame | None]:
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
    Tuple[Optional[Phantom], Optional[Dict[str, Any]], Optional[pd.DataFrame]]
        Patient phantom, dose-loop output dict, and the post-below-floor-policy
        event frame actually used by the dose loop (for export length alignment).
        When the mode does not calculate dose, all three values are ``None``.

    """
    if settings.mode != c.MODE_CALCULATE_DOSE and settings.mode != c.MODE_PLOT_DOSEMAP:
        logger.debug("Mode not set to calculate dose. Returning without doing anything")
        return None, None, None

    logger.info("Start performing dose calculations")
    patient = Phantom(
        phantom_model=settings.phantom.model,
        phantom_dim=settings.phantom.dimension,
        human_mesh=settings.phantom.human_mesh,
        human_scale=(settings.phantom.scale_lat, settings.phantom.scale_ap, settings.phantom.scale_lon),
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

    kerma_cf = _resolve_kerma_meter_cf(normalized_data, settings)

    total_number_of_events = len(normalized_data)

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
        pbar=_make_progress_bar(settings.plot.notebook_mode, total_number_of_events),
        corrections_db=settings.corrections_db_path,
        settings=settings,
        exam_id=exam_id,
        kerma_cf=kerma_cf,
    )

    # Return the post-policy frame separately so export packaging can match
    # dose-loop event lengths after below-floor ``skip`` without stuffing a
    # DataFrame into the public output dict.
    return patient, output, normalized_data


def _make_progress_bar(notebook_mode: bool, total: int):
    """Return a tqdm progress bar for the dose loop.

    When ``notebook_mode`` is set (e.g. the bundled ``settings_example.json``) but the
    Jupyter widget backend is unavailable — as in headless CLI/export runs without
    ``ipywidgets`` installed — ``tqdm_notebook`` raises ``ImportError: IProgress not
    found`` at construction. Fall back to the plain text bar so dose calculation never
    crashes purely over progress-bar rendering.
    """
    kwargs = {"total": total, "leave": False, "desc": "calculating skindose"}
    if notebook_mode:
        try:
            from tqdm import tqdm_notebook

            return tqdm_notebook(**kwargs)
        except ImportError:
            pass
    from tqdm import tqdm

    return tqdm(**kwargs)


def _build_output_template(total_number_of_events: int, dose_map_size: int) -> dict[str, Any]:
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
        c.OUTPUT_KEY_KERMA_CORRECTED: [0.0] * total_number_of_events,
        c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW: [
            np.array([]) for _ in range(total_number_of_events)
        ],
        c.OUTPUT_KEY_CORRECTION_BACK_SCATTER: [np.array([]) for _ in range(total_number_of_events)],
        c.OUTPUT_KEY_CORRECTION_MEDIUM: [0.0] * total_number_of_events,
        c.OUTPUT_KEY_CORRECTION_TABLE: [0.0] * total_number_of_events,
        c.OUTPUT_KEY_CORRECTION_KERMA_METER: [1.0] * total_number_of_events,
        c.OUTPUT_KEY_DOSE_MAP: np.zeros(dose_map_size),
    }
