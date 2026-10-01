"""Calculates field intersections and inverse-square law corrections for new event geometries."""

import logging
from collections.abc import Sequence

import numpy as np
import pandas as pd

from guiskindose import constants as c
from guiskindose.beam_class import Beam
from guiskindose.corrections import calculate_k_isq
from guiskindose.geom_calc import check_table_hits, scale_field_area
from guiskindose.phantom_class import Phantom

logger = logging.getLogger(__name__)


def perform_calculations_for_new_geometries(
    normalized_data: pd.DataFrame,
    event: int,
    new_geometry: bool,
    patient: Phantom,
    table: Phantom,
    pad: Phantom,
    hits: Sequence[bool] | np.ndarray,
    table_hits: Sequence[bool] | np.ndarray,
    field_area: Sequence[float] | np.ndarray,
    k_isq: np.ndarray,
) -> tuple[
    Sequence[bool] | np.ndarray,
    Sequence[bool] | np.ndarray,
    Sequence[float] | np.ndarray,
    np.ndarray,
]:
    """Calculate beam intersections, field areas, and inverse-square corrections.

    If the geometry hasn't changed since the previous event (``new_geometry=False``),
    returns the previous event's intersection and correction arrays unchanged.
    When ``new_geometry=True`` but the beam hits no skin cells, returns empty
    ``table_hits``, ``field_area``, and ``k_isq`` arrays rather than carrying
    forward values from the prior event.

    Parameters
    ----------
    normalized_data : pd.DataFrame
        RDSR data, normalized for compliance with PySkinDose.
    event : int
        Index of the current irradiation event.
    new_geometry : bool
        Whether the irradiation geometry has changed since the preceding event.
    patient : Phantom
        Patient skin surface phantom.
    table : Phantom
        Patient support table phantom.
    pad : Phantom
        Patient support pad phantom.
    hits : Sequence[bool] or np.ndarray
        Boolean hit/miss status of each skin cell from the previous event. A boolean
        array is accepted as well as a list of booleans.
    table_hits : Sequence[bool] or np.ndarray
        Whether the beam passes through the table for each hit cell. A boolean array is
        accepted as well as a list of booleans.
    field_area : Sequence[float] or np.ndarray
        X-ray field area in cm^2 for each hit skin cell. An array is accepted as well as
        a list of floats.
    k_isq : np.ndarray
        Inverse-square-law correction factors.

    Returns
    -------
    tuple[Sequence[bool] or np.ndarray, Sequence[bool] or np.ndarray, Sequence[float] or np.ndarray, np.ndarray]
        Updated hits, table_hits, field_area, and k_isq. ``hits`` is a boolean array and
        ``table_hits`` a boolean array on the new-geometry path, while
        ``field_area`` stays a list of floats; the ``new_geometry=False`` cache path
        passes the caller's own containers straight through.
    """
    if not new_geometry:
        return hits, table_hits, field_area, k_isq

    beam = Beam(data_norm=normalized_data, event=event, plot_setup=False)

    patient.position(data_norm=normalized_data, event=event)
    table.position(data_norm=normalized_data, event=event)
    pad.position(data_norm=normalized_data, event=event)

    logger.debug("Checking which skin cells are hit by the beam")
    hits = beam.check_hit_mask(patient=patient)

    # .any(), not sum()/any(): those iterate an ndarray element by element in Python,
    # boxing every value, which is far slower than the reduction.
    if hits.any():
        logger.debug("Checking which hit skin cells need table correction")
        table_hits = check_table_hits(source=beam.r[0, :], table=table, beam=beam, cells=patient.r[hits])

        logger.debug("Calculating X-Ray field area at the location of each skin cell")
        field_area = scale_field_area(
            data_norm=normalized_data,
            event=event,
            patient=patient,
            hits=hits,
            source=beam.r[0, :],
        )

        logger.debug("Calculating inverse-square law fluence correction")
        k_isq = calculate_k_isq(
            source=beam.r[0, :],
            cells=patient.r[hits],
            dref=normalized_data[c.DATA_DS_IRP][0],
        )
    else:
        # Avoid carrying table_hits / field_area / k_isq forward from a prior event
        # when this new-geometry event hits no skin cells.
        table_hits = []
        field_area = []
        k_isq = np.array([])

    return hits, table_hits, field_area, k_isq
