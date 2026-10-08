"""Applies physics corrections and adds event skin dose to the cumulative dose map."""

import logging
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline

from guiskindose import constants as c
from guiskindose.calculate_dose.tube_dose import add_event_dose
from guiskindose.corrections import calculate_k_med
from guiskindose.phantom_class import Phantom

logger = logging.getLogger(__name__)


def compute_event_dose_vector(
    *,
    event_frame: pd.DataFrame,
    event: int,
    hits: Sequence[bool] | np.ndarray,
    table_hits: Sequence[bool] | np.ndarray,
    field_area: Sequence[float] | np.ndarray,
    k_isq: np.ndarray,
    k_bs_spline: CubicSpline,
    k_tab_scalar: float,
    kerma_full: float,
    corrections_db: str,
    n_cells: int,
    emit_warnings: bool = True,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Compute one pose's skin-dose vector without touching shared output.

    Pure arithmetic mirror of the accumulation below: full event kerma times
    inverse-square, medium, backscatter, and table-path corrections. A total
    miss yields an all-zero vector with empty backscatter and 0.0 medium
    (0.0 means "not applied", matching the legacy convention).

    Parameters
    ----------
    event_frame : pd.DataFrame
        RDSR data, normalized for compliance with PySkinDose.
    event : int
        Irradiation event index.
    hits : Sequence[bool] or np.ndarray
        Boolean hit/miss status of each skin cell. A boolean array is accepted as well
        as a list of booleans.
    table_hits : Sequence[bool] or np.ndarray
        Whether the beam passes through the table for each hit cell. A boolean array is
        accepted as well as a list of booleans.
    field_area : Sequence[float] or np.ndarray
        X-ray field area in (cm^2) for each hit skin cell. An array is accepted as well
        as a list of floats.
    k_isq : np.ndarray
        Inverse-square-law correction factors.
    k_bs_spline : CubicSpline
        Backscatter interpolation for this event.
    k_tab_scalar : float
        Table correction factor for this event.
    kerma_full : float
        Reference-point air kerma for this event, including the kerma-meter factor.
    corrections_db : str
        Path to the corrections SQLite database.
    n_cells : int
        Number of patient skin cells.
    emit_warnings : bool
        Whether correction lookups emit warnings (the default is True).

    Returns
    -------
    tuple[np.ndarray, np.ndarray, float]
        This pose's dose vector, its backscatter factors, and its medium factor (0.0
        means "not applied").

    """
    event_dose = np.zeros(n_cells)
    # No-op when hits is already a boolean array; keeps the list form accepted.
    hits_arr = np.asarray(hits, dtype=bool)
    # .any(), not sum()/any(): those iterate an ndarray element by element in Python,
    # boxing every value, which is far slower than the reduction.
    if not hits_arr.any():
        return event_dose, np.array([]), 0.0

    k_bs = k_bs_spline(np.sqrt(field_area))
    k_med = calculate_k_med(
        data_norm=event_frame,
        field_area=field_area,
        event=event,
        corrections_db=corrections_db,
        emit_warnings=emit_warnings,
    )

    event_dose[hits_arr] += kerma_full
    event_dose[hits_arr] *= k_isq
    event_dose[hits_arr] *= k_med
    event_dose[hits_arr] *= k_bs

    temp = np.ones(len(table_hits))
    temp[np.asarray(table_hits, dtype=bool)] = k_tab_scalar
    event_dose[hits_arr] *= temp

    return event_dose, np.asarray(k_bs), float(k_med)


def add_corrections_and_event_dose_to_output(
    normalized_data: pd.DataFrame,
    event: int,
    hits: Sequence[bool] | np.ndarray,
    table_hits: Sequence[bool] | np.ndarray,
    patient: Phantom,
    back_scatter_interpolation: list[CubicSpline],
    field_area: Sequence[float] | np.ndarray,
    k_tab: list[float],
    corrections_db: str,
    output: dict[str, Any],
    kerma_cf: float = 1.0,
) -> dict[str, Any]:
    """Add correction factors and event dose to output dictionary.

    Parameters
    ----------
    normalized_data : pd.DataFrame
        RDSR data, normalized for compliance with PySkinDose.
    event : int
        Irradiation event index.
    hits : Sequence[bool] or np.ndarray
        Boolean hit/miss status of each skin cell, of the same length as the number of
        patient skin cells. True for all entrance skin cells that are hit by the beam for
        a specific irradiation event. A boolean array is accepted as well as a list of
        booleans.
    table_hits : Sequence[bool] or np.ndarray
        For each hit, whether the beam passes through the patient support table. A boolean
        array is accepted as well as a list of booleans.
    patient : Phantom
        Patient phantom, either of type plane, cylinder or human, i.e. instance of class
        Phantom
    back_scatter_interpolation : List[CubicSpline]
        List of interpolation objects to used to estimate backscatter correction from
        the correction database
    field_area : Sequence[float] or np.ndarray
        X-ray field area in (cm^2) for each phantom skin cell that are hit by the X-ray
        beam. An array is accepted as well as a list of floats.
    k_tab : List[float]
        List of table correction factors
    corrections_db : str
        A string defining the path to the corrections SQLite db
    output : Dict[str, Any]
        Dictionary containing outputs to store from the calculations. E.g. dose map and
        correction factors.
    kerma_cf : float
        Kerma-meter correction factor for this event (applied once to reported K_IRP).

    Returns
    -------
    Dict[str, Any]
        Dictionary containing outputs to store from the calculations. E.g. dose map and
        correction factors.

    """
    event_dose, k_bs, k_med = compute_event_dose_vector(
        event_frame=normalized_data,
        event=event,
        hits=hits,
        table_hits=table_hits,
        field_area=field_area,
        k_isq=output[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW][event],
        k_bs_spline=back_scatter_interpolation[event],
        k_tab_scalar=k_tab[event],
        kerma_full=float(normalized_data.K_IRP[event]) * float(kerma_cf),
        corrections_db=corrections_db,
        n_cells=len(patient.r),
    )

    output[c.OUTPUT_KEY_CORRECTION_BACK_SCATTER][event] = k_bs
    output[c.OUTPUT_KEY_CORRECTION_MEDIUM][event] = k_med
    output[c.OUTPUT_KEY_CORRECTION_TABLE][event] = k_tab[event]

    logger.debug(
        "Calculating event skin dose by applying each correction factor to the reference point air kerma"
    )

    add_event_dose(output, event, event_dose)

    return output
