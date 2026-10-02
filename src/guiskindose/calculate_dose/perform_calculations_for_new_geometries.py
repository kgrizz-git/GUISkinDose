"""Calculates field intersections and inverse-square law corrections for new event geometries."""

import logging
from collections.abc import Sequence

import numpy as np
import pandas as pd

from guiskindose import constants as c
from guiskindose.beam_class import Beam, BeamGeometryInputs
from guiskindose.corrections import calculate_k_isq
from guiskindose.geom_calc import check_table_hits, scale_field_area_array
from guiskindose.phantom_class import Phantom

logger = logging.getLogger(__name__)


def _build_beam(
    *,
    normalized_data: pd.DataFrame,
    event: int,
    beam_inputs: BeamGeometryInputs | None,
    beam_angles_deg: tuple[float, float, float] | None,
) -> Beam:
    """Build the event's beam, from hoisted scalars or from the event table.

    With neither override this is exactly ``Beam(data_norm=normalized_data,
    event=event)``, so every existing caller's numbers are untouched. With both,
    the scalars and the pose angles come from the caller — the rotational
    candidate loop, which evaluates many poses of one event against one set of
    scalars.

    Raises
    ------
    ValueError
        If only one of the two overrides is supplied. Half an override would
        silently mix one source of scalars with the other's angles, so it is
        rejected rather than guessed at.
    """
    if (beam_inputs is None) != (beam_angles_deg is None):
        raise ValueError(
            "beam_inputs and beam_angles_deg must be given together; supply both "
            "to hoist an event's beam scalars, or neither to read them from "
            "normalized_data."
        )
    if beam_inputs is None or beam_angles_deg is None:
        return Beam(data_norm=normalized_data, event=event, plot_setup=False)
    return Beam.from_inputs(beam_inputs, *beam_angles_deg)


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
    *,
    reposition: bool = True,
    beam_inputs: BeamGeometryInputs | None = None,
    beam_angles_deg: tuple[float, float, float] | None = None,
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
    reposition : bool, keyword-only
        Whether to (re)position the three phantoms at this event's pose.
        ``False`` is for callers that have already positioned them — the
        rotational candidate loop, where every candidate shares the parent
        event's pose, so one positioning covers the whole domain. Defaults to
        ``True``, which keeps every existing caller's behaviour unchanged.
    beam_inputs : BeamGeometryInputs, keyword-only
        Pre-resolved beam scalars, letting a caller that already holds them skip
        the per-event table reads (Phase 2 of
        ROTATIONAL_ENVELOPE_PERFORMANCE_PLAN). Defaults to ``None``, which reads
        them from ``normalized_data`` at ``event``. Only honoured together with
        ``beam_angles_deg``.
    beam_angles_deg : tuple[float, float, float], keyword-only
        The pose's (Ap1, Ap2, Ap3) in degrees, overriding the angles
        ``normalized_data`` holds at ``event``. Used by the rotational candidate
        loop, whose poses are not in any table row. Must be given with
        ``beam_inputs``: either both are supplied, or neither is and the beam is
        built from ``normalized_data`` exactly as before.

    Raises
    ------
    ValueError
        If only one of ``beam_inputs`` and ``beam_angles_deg`` is supplied.

    Returns
    -------
    tuple[Sequence[bool] or np.ndarray, Sequence[bool] or np.ndarray, Sequence[float] or np.ndarray, np.ndarray]
        Updated hits, table_hits, field_area, and k_isq. ``hits`` is a boolean array,
        ``table_hits`` a boolean array, and ``field_area`` a float array on the
        new-geometry path; the ``new_geometry=False`` cache path
        passes the caller's own containers straight through.
    """
    if not new_geometry:
        return hits, table_hits, field_area, k_isq

    beam = _build_beam(
        normalized_data=normalized_data,
        event=event,
        beam_inputs=beam_inputs,
        beam_angles_deg=beam_angles_deg,
    )

    if reposition:
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
        field_area = scale_field_area_array(
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
