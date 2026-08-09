import logging

import numpy as np
import pandas as pd

from mypyskindose import constants as c
from mypyskindose.beam_class import Beam
from mypyskindose.corrections import calculate_k_isq
from mypyskindose.geom_calc import check_table_hits, scale_field_area
from mypyskindose.phantom_class import Phantom

logger = logging.getLogger(__name__)


def perform_calculations_for_new_geometries(
    normalized_data: pd.DataFrame,
    event: int,
    new_geometry: bool,
    patient: Phantom,
    table: Phantom,
    pad: Phantom,
    hits: list[bool],
    table_hits: list[bool],
    field_area: list[float],
    k_isq: np.ndarray,
):
    if not new_geometry:
        return hits, table_hits, field_area, k_isq

    beam = Beam(data_norm=normalized_data, event=event, plot_setup=False)

    patient.position(data_norm=normalized_data, event=event)
    table.position(data_norm=normalized_data, event=event)
    pad.position(data_norm=normalized_data, event=event)

    logger.debug("Checking which skin cells are hit by the beam")
    hits = beam.check_hit(patient=patient)

    if sum(hits):
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
