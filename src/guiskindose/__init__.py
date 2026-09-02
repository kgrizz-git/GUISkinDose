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


def load_settings_example_json() -> dict:
    import json
    from pathlib import Path

    return json.loads((Path(__file__).parent / "settings_example.json").read_text())


def print_available_human_phantoms():
    from pathlib import Path

    phantom_data_dir = Path(__file__).parent / "phantom_data"
    phantoms = [
        phantom.stem for phantom in phantom_data_dir.glob("*.stl") if "_reduced_" not in phantom.stem
    ]

    for phantom in phantoms:
        print(phantom)


def print_example_rdsr_files():
    rdsr_data_dir = get_path_to_example_rdsr_files()
    files = [file.name for file in rdsr_data_dir.glob("*.dcm")]

    print("Available RDSR files:\n")
    for filename in files:
        # nosemgrep: mypyskindose-filename-var-to-log-or-stdout -- bundled public fixture name shown on request; reviewed 2026-07-16
        print(f"\t{filename}")

    print("\nFiles are packaged with MyPySkinDose example data.")


def get_path_to_example_rdsr_files():
    from pathlib import Path

    return Path(__file__).parent / "example_data" / "RDSR"
