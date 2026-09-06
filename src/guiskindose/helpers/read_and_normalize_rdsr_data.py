"""Read an RDSR file and normalize it into the internal event DataFrame.

Reads a DICOM RDSR (or preparsed JSON), parses it, normalizes vendor
conventions, and optionally drops invalid kVp rows.
"""
import logging
from pathlib import Path

import pandas as pd
import pydicom

from guiskindose.rdsr_normalizer import rdsr_normalizer
from guiskindose.rdsr_parser import rdsr_parser
from guiskindose.settings import PyskindoseSettings

logger = logging.getLogger(__name__)


def read_and_normalise_rdsr_data(rdsr_filepath: str | None, settings: PyskindoseSettings) -> pd.DataFrame:
    """Load and normalize RDSR event data for downstream dose calculations.

    Parameters
    ----------
    rdsr_filepath : str | None
        Explicit path to an RDSR DICOM or JSON file. When *None*, the path
        is derived from *settings.rdsr_filename* in the bundled example
        data directory.
    settings : PyskindoseSettings
        Runtime settings controlling parsing and normalization behavior.

    Returns
    -------
    pd.DataFrame
        Normalized DataFrame of irradiation events ready for geometry
        reconstruction and dose accumulation.
    """
    path: Path = (
        Path(rdsr_filepath)
        if rdsr_filepath
        else Path(__file__).parent.parent / "example_data/RDSR" / settings.rdsr_filename
    )

    # Log only the file type, never the path/name — RDSR filenames routinely
    # contain PHI (patient name, MRN, accession) in clinical use.
    logger.debug("Reading RDSR data from a %s file", path.suffix.lower() or "(no suffix)")

    # If provided, load preparsed rdsr data in .json format
    if path.suffix.lower() == ".json":
        return pd.read_json(path)

    # else load RDSR data with pydicom
    data_raw = pydicom.dcmread(path)

    # parse RDSR data from raw .dicom file
    data_parsed = rdsr_parser(data_raw, silence_pydicom_warnings=settings.silence_pydicom_warnings)

    # normalized rdsr for compliance with PySkinDose
    normalized_data = rdsr_normalizer(data_parsed, settings=settings)

    if settings.remove_invalid_rows and (invalid_kvp_rows := len(normalized_data[normalized_data.kVp == 0])):
        print(f"Removing {invalid_kvp_rows} rows with kVp value = 0")
        normalized_data = normalized_data[normalized_data.kVp != 0].reset_index(drop=True)

    return normalized_data
