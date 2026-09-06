"""Top-level public API for GUISkinDose.

Re-exports the primary classes and convenience helpers used to run skin-dose
calculations from DICOM RDSR data. All geometry is expressed in cm unless noted.
"""
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version

from .analyze_data import analyze_data as analyze_data
from .beam_class import Beam as Beam
from .geom_calc import check_new_geometry as check_new_geometry
from .geom_calc import fetch_and_append_hvl as fetch_and_append_hvl
from .geom_calc import position_patient_phantom_on_table as position_patient_phantom_on_table
from .geom_calc import scale_field_area as scale_field_area
from .main import analyze_input_file as analyze_input_file
from .phantom_class import Phantom as Phantom
from .plotting import plot_geometry as plot_geometry
from .rdsr_normalizer import rdsr_normalizer as rdsr_normalizer
from .rdsr_parser import rdsr_parser as rdsr_parser
from .settings import PyskindoseSettings as PyskindoseSettings

try:
    __version__ = _distribution_version("guiskindose")
except PackageNotFoundError:  # source tree imported without installation
    __version__ = "0.0.0+unknown"


def load_settings_example_json() -> dict:
    """Load the bundled example settings as a dictionary."""
    import json
    from pathlib import Path

    return json.loads((Path(__file__).parent / "settings_example.json").read_text())


def print_available_human_phantoms():
    """Print the bundled human phantom STL stems to stdout."""
    from pathlib import Path

    phantom_data_dir = Path(__file__).parent / "phantom_data"
    phantoms = [
        phantom.stem for phantom in phantom_data_dir.glob("*.stl") if "_reduced_" not in phantom.stem
    ]

    for phantom in phantoms:
        print(phantom)


def print_example_rdsr_files():
    """Print the packaged example RDSR filenames to stdout."""
    rdsr_data_dir = get_path_to_example_rdsr_files()
    files = [file.name for file in rdsr_data_dir.glob("*.dcm")]

    print("Available RDSR files:\n")
    for filename in files:
        # nosemgrep: mypyskindose-filename-var-to-log-or-stdout -- bundled public fixture name shown on request; reviewed 2026-07-16
        print(f"\t{filename}")

    print("\nFiles are packaged with GUISkinDose example data.")


def get_path_to_example_rdsr_files():
    """Return the pathlib.Path to the bundled example RDSR directory."""
    from pathlib import Path

    return Path(__file__).parent / "example_data" / "RDSR"
