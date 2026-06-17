"""GUI helper functions: build settings objects, run calculations, etc."""

from __future__ import annotations

import logging
import traceback
from pathlib import Path
import pydicom

from mypyskindose import load_settings_example_json
from mypyskindose.rdsr_parser import rdsr_parser
from mypyskindose.rdsr_normalizer import rdsr_normalizer
from mypyskindose.settings import PyskindoseSettings

from .state import AppState


class _CalcWarningCollector(logging.Handler):
    """Collects WARNING+ log messages emitted during a dose calculation so the GUI
    can surface them (e.g. how many events had their HVL snapped to the grid)."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


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
    except Exception as exc:
        # Log the full traceback for debugging; surface a concise message to the UI.
        print(traceback.format_exc())
        return False, f"Could not read this DICOM RDSR file: {exc}"


def get_excel_sheets(file_path: Path) -> list[str]:
    """Return the sheet names from an Excel file, or [] on error."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        names = wb.sheetnames
        wb.close()
        return names
    except Exception:
        return []


def load_tabular(file_path: Path, state: AppState) -> tuple[bool, str]:
    """Load a tabular file (CSV/TSV/XLSX) via the input_adapters registry.

    Returns ``(ok, message)``. On failure the message is a concise, user-facing
    string (not a traceback); the full traceback is still logged to the console
    for debugging. Auto-detection failures get a specific "choose a schema" hint.
    """
    from mypyskindose.input_adapters.registry import (
        SchemaDetectionError,
        read_and_normalize_input,
    )

    try:
        settings = build_settings(state, mode="calculate_dose")
        schema = state.input_schema or "auto"

        _raw = read_and_normalize_input(
            file_path,
            input_schema=schema,
            settings=settings,
            sheet_name=state.input_sheet_name,
        )
        if isinstance(_raw, list):
            ids = [r.study_id or "?" for r in _raw]
            raise ValueError(
                f"This file contains {len(_raw)} separate studies "
                f"({', '.join(ids)}). "
                "Use the multi-exam API (analyze_multiple_input_files) or "
                "export a single study before loading here."
            )
        result = _raw

        df = result.normalized_data.copy()

        if state.swap_lat_lon and result.provenance.schema_name != "normalized":
            if "Tx" in df.columns and "Tz" in df.columns:
                df["Tx"], df["Tz"] = df["Tz"].copy(), df["Tx"].copy()
        if state.flip_ap1 and "Ap1" in df.columns:
            df["Ap1"] = -df["Ap1"]
        if state.flip_ap2 and "Ap2" in df.columns:
            df["Ap2"] = -df["Ap2"]

        state.rdsr_df = df
        state.rdsr_raw_df = result.raw_data
        state.file_path = file_path
        state.import_provenance = result.provenance
        state.import_warnings = list(result.warnings)
        state.import_has_errors = False

        state.manufacturer = ""
        state.model = ""
        state.normalization_method = "Tabular"
        state.table_offset_x = 0.0
        state.table_offset_y = 0.0
        state.table_offset_z = 0.0
        state.normalization_warnings = []

        return True, f"Loaded {len(df)} events from {file_path.name} ({result.provenance.schema_name})"
    except SchemaDetectionError:
        # Not a real parse error — the file just didn't clearly match a known
        # vendor format. Guide the user to pick one explicitly instead of
        # dumping a traceback.
        print(traceback.format_exc())
        state.import_has_errors = True
        return False, (
            "Couldn't auto-detect this file's format. Open the “Input schema” "
            "selector below and choose the matching format (e.g. Radimetrics CSV, "
            "DoseTrack, Raw RDSR-like, or Normalized), then upload the file again."
        )
    except Exception as exc:
        # Genuine read/validation error: log the full traceback for debugging but
        # surface only a concise one-line message in the UI.
        print(traceback.format_exc())
        state.import_has_errors = True
        return False, f"Could not read this file: {exc}"


def run_calculation(state: AppState, progress_cb=None) -> tuple[bool, str]:
    """Run the full dose calculation. Returns (success, message).

    progress_cb: optional callable(fraction: float, label: str) for UI updates.
    """
    try:
        from mypyskindose.analyze_data import analyze_data
        from mypyskindose.debug import dprint

        settings = build_settings(state, mode="calculate_dose", output_format="dict")

        # Don't log state.file_name — it can carry PHI (patient name/MRN).
        dprint("CALCULATION", "Starting calculation")
        dprint("CALCULATION", f"Phantom: {state.phantom_model}, Offsets: {state.d_lon}, {state.d_ver}, {state.d_lat}")
        dprint("CALCULATION", f"Normalization: {state.normalization_method}")

        # Patch tqdm so we can forward progress to the UI
        if progress_cb is not None:
            _patch_tqdm(progress_cb, total=event_count_from_state(state))

        if state.rdsr_df is None:
            return False, "No RDSR data loaded."

        # Capture WARNING+ logs from the core calc (e.g. HVL lookups snapped for
        # out-of-range events) so they can be surfaced in the GUI, not just the
        # console. analyze_data runs on this (worker) thread, so a temporary
        # handler on the mypyskindose logger collects its records.
        state.calc_warnings = []
        _collector = _CalcWarningCollector()
        _calc_logger = logging.getLogger("mypyskindose")
        _calc_logger.addHandler(_collector)
        try:
            # analyze_data internally calls calculate_rotation_matrices
            output = analyze_data(normalized_data=state.rdsr_df.copy(), settings=settings)
        finally:
            _calc_logger.removeHandler(_collector)
        state.calc_warnings = list(_collector.messages)

        if not isinstance(output, dict):
            return False, "Unexpected calculation output format."

        state.output = output
        state.calculation_done = True
        state.psd = float(output["psd"])
        state.air_kerma = float(output["air_kerma"])
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

        tqdm_module.tqdm.update = new_update  # type: ignore[method-assign]
    except Exception as exc:
        from mypyskindose.debug import dprint

        dprint("CALCULATION", f"tqdm progress patch skipped: {exc}")


def get_example_rdsr_files() -> list[Path]:
    """Return list of bundled example RDSR .dcm files."""
    from mypyskindose import get_path_to_example_rdsr_files

    rdsr_dir = get_path_to_example_rdsr_files()
    return sorted(rdsr_dir.glob("*.dcm"))


def get_human_mesh_names() -> list[str]:
    """Return available human mesh names (full-resolution only)."""
    phantom_dir = Path(__file__).parent.parent / "phantom_data"
    return sorted(p.stem for p in phantom_dir.glob("*.stl") if not p.stem.endswith("_reduced_1000t"))
