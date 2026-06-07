from typing import Any, Dict, Union

import pandas as pd

from mypyskindose import constants as c
from mypyskindose.calculate_dose.calculate_dose import calculate_dose
from mypyskindose.format_export_data import (
    PySkinDoseOutput,
    format_analysis_result_for_export,
)
from mypyskindose.helpers.calculate_rotation_matrices import calculate_rotation_matrices
from mypyskindose.phantom_class import Phantom
from mypyskindose.plotting.create_dose_map_plot import create_dose_map_plot
from mypyskindose.plotting.create_geometry_plot import create_geometry_plot
from mypyskindose.settings import PyskindoseSettings, initialize_settings
from mypyskindose.debug import dprint


def analyze_data(
    normalized_data: pd.DataFrame,
    settings: Union[str, dict, PyskindoseSettings],
) -> Union[Dict[str, Any], str, PySkinDoseOutput]:
    """Analyze data och settings, and runs PySkinDose in desired mode.

    Parameters
    ----------
    normalized_data : pd.DataFrame
        RDSR data, normalized for compliance with PySkinDose.
    settings : Union[str, dict, PyskindoseSettings]
        Settings class for PySkinDose

    Returns
    -------
    Dict[str, Any]
        output dictionary containing calculation specifics such as dose map, correction
        factors, etc.

    """
    settings = initialize_settings(settings)

    if settings.output_format not in c.RUN_ARGUMENTS_VALID_OUTPUT_FORMATS:
        raise ValueError(
            f"Invalid output format specified. Must be one of {'.'.join(c.RUN_ARGUMENTS_VALID_OUTPUT_FORMATS)}"
        )

    dprint("CALCULATION", "Creating table and pad phantoms")
    # create table, pad and patient phantoms.
    table = Phantom(phantom_model=c.PHANTOM_MODEL_TABLE, phantom_dim=settings.phantom.dimension)

    pad = Phantom(phantom_model=c.PHANTOM_MODEL_PAD, phantom_dim=settings.phantom.dimension)

    dprint("CALCULATION", "Calculating rotation matrices")
    normalized_data = calculate_rotation_matrices(normalized_data)

    dprint("RENDERING", "Creating geometry plot")
    create_geometry_plot(normalized_data=normalized_data, table=table, pad=pad, settings=settings)

    dprint("CALCULATION", "Calculating dose")
    patient, output = calculate_dose(normalized_data=normalized_data, settings=settings, table=table, pad=pad)

    if settings.output_format in [c.RUN_ARGUMENTS_OUTPUT_DICT, c.RUN_ARGUMENTS_OUTPUT_JSON]:
        dprint("PROCESSING", "Formatting analysis result for export")
        mypyskindose_output: Union[PySkinDoseOutput, dict[str, Any], str] = format_analysis_result_for_export(
            output, patient=patient, table=table, pad=pad, data_norm=normalized_data, settings=settings
        )

        return mypyskindose_output

    dprint("RENDERING", "Creating dose map plot")
    create_dose_map_plot(
        patient=patient,
        settings=settings,
        dose_map=(
            output[c.OUTPUT_KEY_DOSE_MAP] if settings.mode in (c.MODE_CALCULATE_DOSE, c.MODE_PLOT_DOSEMAP) else None
        ),
    )

    if settings.output_format == c.RUN_ARGUMENTS_OUTPUT_HTML:
        return output
