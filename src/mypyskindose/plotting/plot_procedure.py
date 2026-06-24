import logging
from typing import Optional

import pandas as pd

from ..constants import MODE_PLOT_PROCEDURE
from ..phantom_class import Phantom
from .create_irradiation_event_procedure_plot_data import (
    create_irradiation_event_procedure_plot_data,
)
from .create_plot_and_save_to_file import create_plot_and_save_to_file
from .plot_layout import default_procedure_layout

logger = logging.getLogger(__name__)


def plot_procedure(
    mode: str,
    data_norm: pd.DataFrame,
    table: Phantom,
    pad: Phantom,
    include_patient: bool,
    patient: Optional[Phantom] = None,
    dark_mode: bool = True,
    notebook_mode: bool = False,
):
    """Create plot_procedure plot.

    Parameters
    ----------
    mode : str
        The function will only run if this is set to "plot_procedure".
    data_norm : pd.DataFrame
        RDSR data, normalized for compliance with PySkinDose.
    table : Phantom
        Patient support table phantom
    pad : Phantom
        Patient support pad phantom
    include_patient : bool
        Choose if the patient phantom should be included
    patient : Optional[Phantom], optional
        patient phantom, by default None
    dark_mode : bool, optional
        set dark mode for plots, by default True
    notebook_mode : bool, optional
        optimize plot size for notebooks, default is True.

    Raises
    ------
    IOError
        Raises error if patient not provided when include_patient = True

    """
    if mode != MODE_PLOT_PROCEDURE:
        return

    if include_patient and patient is None:
        logger.error("Plot procedure called with include patient but no patient input")
        raise IOError("Patient object must be given when include_patient set to True")

    logger.info(f"Plotting entire procedure with {len(data_norm)} irradiation events")

    title = f"<b>P</b>y<b>S</b>kin<b>D</b>ose [mode: {mode}]"

    meshes = [
        create_irradiation_event_procedure_plot_data(
            data_norm=data_norm,
            include_patient=include_patient,
            visible_status=(ind == 0),
            event=ind,
            patient=(patient if include_patient else None),
            table=table,
            pad=pad,
        )
        for ind in range(len(data_norm))
    ]

    data = [
        trace
        for plot_object in meshes[0].keys()
        for event in meshes
        for trace in [event.get(plot_object)]
        if trace is not None
    ]

    layout = default_procedure_layout(
        title=title,
        total_events=len(data_norm),
        dark_mode=dark_mode,
        notebook_mode=notebook_mode,
    )

    create_plot_and_save_to_file(mode=mode, data=data, layout=layout)
