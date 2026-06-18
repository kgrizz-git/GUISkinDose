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
    """Parse and normalise an RDSR file and append it to the exam list.

    Accumulating: each call adds one entry to ``state.loaded_exams`` and
    ``state.loaded_exam_meta`` rather than replacing the previous load.
    Returns ``(success, message)``.
    """
    from mypyskindose.input_adapters.models import InputAdapterResult, InputProvenance
    import pandas as pd

    try:
        settings = build_settings(state, mode="calculate_dose")

        # Manually parse and normalise so we can keep the raw version
        data_raw = pydicom.dcmread(str(file_path))
        data_parsed = rdsr_parser(data_raw, silence_pydicom_warnings=settings.silence_pydicom_warnings)

        # Save raw copy (last-loaded DICOM wins for the raw preview)
        state.rdsr_raw_df = data_parsed.copy()

        # Normalize
        df = rdsr_normalizer(data_parsed, settings=settings)

        if settings.remove_invalid_rows and len(df[df.kVp == 0]):
            df = df[df.kVp != 0].reset_index(drop=True)

        # Build a synthetic InputAdapterResult so DICOM and tabular exams are
        # handled uniformly in the exam list and by analyze_multiple_exams().
        provenance = InputProvenance(
            source_type="dicom",
            schema_name="dicom_rdsr",
            original_filename=file_path.name,
            header_row_index=0,
            detected_encoding="N/A",
            detected_delimiter=None,
            sheet_name=None,
            column_map={},
            unit_conversions={},
        )
        result = InputAdapterResult(
            normalized_data=df,
            raw_data=data_parsed.copy(),
            provenance=provenance,
            warnings=[],
            study_id=None,
        )

        # ── Accumulate ────────────────────────────────────────────────────
        state.loaded_exams.append(result)
        state.loaded_exam_meta.append({
            "file_name": file_path.name,
            "file_path": file_path,
            "source_type": "dicom",
            "schema": "dicom_rdsr",
            "sheet": None,
            "provenance": provenance,
            "warnings": [],
            "swap_lat_lon": False,
            "flip_ap1": False,
            "flip_ap2": False,
        })

        # Rebuild concat event preview from all loaded exams
        state.rdsr_df = pd.concat(
            [e.normalized_data for e in state.loaded_exams], ignore_index=True
        )
        state.is_multi_exam = len(state.loaded_exams) > 1

        # Update single-file-style fields so the rest of the UI is consistent
        state.file_path = file_path
        if len(state.loaded_exams) == 1:
            state.file_name = file_path.name
        else:
            state.file_name = f"{len(state.loaded_exams)} files"

        # Extract DICOM metadata for display (last-loaded wins)
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


def load_tabular(
    file_path: Path, state: AppState, replace_existing: bool = False
) -> tuple[bool, str]:
    """Load a tabular file (CSV/TSV/XLSX) and append exam(s) to the exam list.

    Accumulating: each call adds one or more entries to ``state.loaded_exams``
    and ``state.loaded_exam_meta`` rather than replacing previous loads.

    ``replace_existing`` re-parses a file already in the exam list (e.g. after a
    schema or sheet change): any exam(s) previously loaded from ``file_path`` are
    dropped before the freshly parsed one(s) are appended, so a re-parse updates
    the entry in place instead of duplicating it. The drop happens only after the
    parse succeeds, so a failed re-parse leaves the existing exam untouched.

    Returns ``(ok, message)``.
    """
    import pandas as pd
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

        # Re-parse of an existing entry: drop the stale exam(s) for this file now
        # that the new parse has succeeded, so the result replaces rather than
        # duplicates them.
        if replace_existing:
            _drop_exams_for_path(state, file_path)

        if isinstance(_raw, list):
            # Multi-study file: append all exams.
            # NOTE: coordinate transforms are intentionally NOT applied in the
            # multi-exam path — they must be applied per-exam (Phase 2.2).
            new_exams = _raw
            for exam in new_exams:
                state.loaded_exams.append(exam)
                state.loaded_exam_meta.append({
                    "file_name": file_path.name,
                    "file_path": file_path,
                    "source_type": file_path.suffix.lstrip("."),
                    "schema": exam.provenance.schema_name,
                    "sheet": state.input_sheet_name,
                    "provenance": exam.provenance,
                    "warnings": list(exam.warnings),
                    "swap_lat_lon": False,
                    "flip_ap1": False,
                    "flip_ap2": False,
                })
            result = _raw[0]  # use first exam's provenance for UI hints
            total_events = sum(len(e.normalized_data) for e in new_exams)
            msg = f"Loaded {len(new_exams)} exams, {total_events} total events from {file_path.name}"
        else:
            # Single-study file: apply per-file coordinate transforms, then append.
            result = _raw
            df = result.normalized_data.copy()

            # Coordinate transforms apply to single-exam tabular loads;
            # use current global state flags (which _set_transform_defaults() will
            # set correctly after this call returns).
            if state.swap_lat_lon and result.provenance.schema_name != "normalized":
                if "Tx" in df.columns and "Tz" in df.columns:
                    df["Tx"], df["Tz"] = df["Tz"].copy(), df["Tx"].copy()
            if state.flip_ap1 and "Ap1" in df.columns:
                df["Ap1"] = -df["Ap1"]
            if state.flip_ap2 and "Ap2" in df.columns:
                df["Ap2"] = -df["Ap2"]
            result.normalized_data = df

            state.loaded_exams.append(result)
            state.loaded_exam_meta.append({
                "file_name": file_path.name,
                "file_path": file_path,
                "source_type": file_path.suffix.lstrip("."),
                "schema": result.provenance.schema_name,
                "sheet": state.input_sheet_name,
                "provenance": result.provenance,
                "warnings": list(result.warnings),
                "swap_lat_lon": state.swap_lat_lon,
                "flip_ap1": state.flip_ap1,
                "flip_ap2": state.flip_ap2,
            })
            msg = f"Loaded {len(df)} events from {file_path.name} ({result.provenance.schema_name})"

        # Rebuild concat event preview from all loaded exams.
        state.rdsr_df = pd.concat(
            [e.normalized_data for e in state.loaded_exams], ignore_index=True
        )
        state.is_multi_exam = len(state.loaded_exams) > 1

        # Per-file state used by the import preview and schema re-parse path.
        state.rdsr_raw_df = result.raw_data
        state.file_path = file_path
        if len(state.loaded_exams) == 1:
            state.file_name = file_path.name
        else:
            state.file_name = f"{len(state.loaded_exams)} files"
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

        return True, msg
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
        if state.is_multi_exam:
            from mypyskindose.analyze_data import analyze_multiple_exams
            
            # analyze_multiple_exams internally handles logging and tqdm patch
            multi_result = analyze_multiple_exams(
                exams=state.loaded_exams,
                settings=settings,
            )
            
            state.multi_exam_result = multi_result
            state.calculation_done = True
            state.psd = float(multi_result.aggregate_psd)
            # sum of air kerma across exams
            state.air_kerma = sum(float(e.output.AirKerma) for e in multi_result.exams)
            
            # Surface calc warnings from the orchestrator run
            state.calc_warnings = list(_collector.messages)
            
            return True, f"Aggregate PSD = {multi_result.aggregate_psd:.2f} mGy across {len(state.loaded_exams)} exams"
        else:
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


def clear_multi_exam_state(state: AppState) -> None:
    """Clear all exam state from AppState (called by clear_all_exams in app.py)."""
    state.loaded_exams = []
    state.loaded_exam_meta = []
    state.is_multi_exam = False
    state.multi_exam_result = None
    state.active_exam_index = None


def _drop_exams_for_path(state: AppState, file_path: Path) -> None:
    """Remove every loaded exam (and its metadata) that came from ``file_path``.

    Used when re-parsing a file already in the exam list — a single file may have
    produced several exams (multi-study split), so all entries keyed to that path
    are removed together. Does not touch the temp file on disk; the caller is
    re-reading the same path.
    """
    keep_exams: list = []
    keep_meta: list[dict] = []
    for exam, meta in zip(state.loaded_exams, state.loaded_exam_meta):
        if meta.get("file_path") == file_path:
            continue
        keep_exams.append(exam)
        keep_meta.append(meta)
    state.loaded_exams = keep_exams
    state.loaded_exam_meta = keep_meta
