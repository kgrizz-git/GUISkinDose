"""GUI helper functions: build settings objects, run calculations, etc."""

from __future__ import annotations

import traceback
from pathlib import Path
import pydicom

from mypyskindose import load_settings_example_json
from mypyskindose.rdsr_parser import rdsr_parser
from mypyskindose.rdsr_normalizer import rdsr_normalizer
from mypyskindose.settings import PyskindoseSettings

from .state import AppState


def build_settings(state: AppState, mode: str = "calculate_dose", output_format: str = "dict") -> PyskindoseSettings:
    """Construct a PyskindoseSettings object from current UI state."""
    base = load_settings_example_json()

    base["mode"] = mode
    base["estimate_k_tab"] = state.estimate_k_tab
    base["k_tab_val"] = state.k_tab_val
    base["inherent_filtration"] = state.inherent_filtration
    base["remove_invalid_rows"] = state.remove_invalid_rows
    base["silence_pydicom_warnings"] = True

    base["phantom"]["model"] = state.phantom_model
    base["phantom"]["human_mesh"] = state.human_mesh
    base["phantom"]["patient_orientation"] = state.patient_orientation
    base["phantom"]["patient_offset"]["d_lon"] = state.d_lon
    base["phantom"]["patient_offset"]["d_ver"] = state.d_ver
    base["phantom"]["patient_offset"]["d_lat"] = state.d_lat

    base["plot"]["dark_mode"] = state.dark_mode
    base["plot"]["plot_dosemap"] = False  # we handle plotting ourselves
    base["plot"]["interactivity"] = True
    base["plot"]["notebook_mode"] = False
    base["plot"]["colorscale"] = state.colorscale

    # Point corrections DB to the package root
    db_path = Path(__file__).parent.parent.parent.parent / "corrections.db"
    if db_path.exists():
        base["corrections_db_path"] = str(db_path)

    return PyskindoseSettings(settings=base, output_format=output_format)


def load_rdsr(file_path: Path, state: AppState) -> tuple[bool, str]:
    """Parse and normalise an RDSR file. Returns (success, message)."""
    try:
        settings = build_settings(state, mode="calculate_dose")
        
        # Manually parse and normalise so we can keep the raw version
        data_raw = pydicom.dcmread(str(file_path))
        data_parsed = rdsr_parser(data_raw, silence_pydicom_warnings=settings.silence_pydicom_warnings)
        
        # Save raw copy
        state.rdsr_raw_df = data_parsed.copy()
        
        # Normalize
        df = rdsr_normalizer(data_parsed, settings=settings)
        
        if settings.remove_invalid_rows and len(df[df.kVp == 0]):
            df = df[df.kVp != 0].reset_index(drop=True)

        state.rdsr_df = df
        state.file_path = file_path
        state.file_name = file_path.name

        # Extract metadata for the GUI
        norm = settings.normalization_settings
        state.manufacturer = norm.matched_manufacturer
        state.model = norm.matched_model
        state.normalization_method = norm.normalization_method
        state.table_offset_x = norm.trans_offset.x
        state.table_offset_y = norm.trans_offset.y
        state.table_offset_z = norm.trans_offset.z
        state.normalization_warnings = []
        if state.normalization_method == "Fallback":
            state.normalization_warnings.append(
                f"Scanner model '{state.model}' not found. Using default normalization settings."
            )

        return True, f"Loaded {len(df)} irradiation events from {file_path.name}"
    except Exception:
        err = traceback.format_exc()
        print(err)
        return False, err


def run_calculation(state: AppState, progress_cb=None) -> tuple[bool, str]:
    """Run the full dose calculation. Returns (success, message).

    progress_cb: optional callable(fraction: float, label: str) for UI updates.
    """
    try:
        from mypyskindose.analyze_data import analyze_data
        from mypyskindose.debug import dprint

        settings = build_settings(state, mode="calculate_dose", output_format="dict")

        dprint("CALCULATION", f"Starting calculation for {state.file_name}")
        dprint("CALCULATION", f"Phantom: {state.phantom_model}, Offsets: {state.d_lon}, {state.d_ver}, {state.d_lat}")
        dprint("CALCULATION", f"Normalization: {state.normalization_method}")

        # Patch tqdm so we can forward progress to the UI
        if progress_cb is not None:
            _patch_tqdm(progress_cb, total=event_count_from_state(state))

        # analyze_data internally calls calculate_rotation_matrices
        output = analyze_data(normalized_data=state.rdsr_df.copy(), settings=settings)

        state.output = output
        state.calculation_done = True
        state.psd = output["psd"]
        state.air_kerma = output["air_kerma"]
        return True, f"PSD = {output['psd']:.2f} mGy"
    except Exception:
        err = traceback.format_exc()
        print(err)
        return False, err


def event_count_from_state(state: AppState) -> int:
    if state.rdsr_df is None:
        return 0
    return len(state.rdsr_df)


def _patch_tqdm(progress_cb, total: int):
    """Monkey-patch tqdm so dose calculation progress reaches the UI."""
    try:
        import tqdm as tqdm_module

        original_update = tqdm_module.tqdm.update

        def new_update(self, n=1):
            original_update(self, n)
            if total > 0:
                progress_cb(self.n / total, f"Event {self.n} / {total}")

        tqdm_module.tqdm.update = new_update
    except Exception:
        pass  # progress patching is best-effort


def get_example_rdsr_files() -> list[Path]:
    """Return list of bundled example RDSR .dcm files."""
    from mypyskindose import get_path_to_example_rdsr_files

    rdsr_dir = get_path_to_example_rdsr_files()
    return sorted(rdsr_dir.glob("*.dcm"))


def get_human_mesh_names() -> list[str]:
    """Return available human mesh names (full-resolution only)."""
    phantom_dir = Path(__file__).parent.parent / "phantom_data"
    return sorted(p.stem for p in phantom_dir.glob("*.stl") if not p.stem.endswith("_reduced_1000t"))
