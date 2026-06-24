"""Load RDSR and tabular exams into AppState."""

from __future__ import annotations

import traceback
from pathlib import Path

import pydicom

from mypyskindose.rdsr_parser import rdsr_parser
from mypyskindose.rdsr_normalizer import rdsr_normalizer

from .exam_transforms import (
    _apply_transform_flags,
    _drop_exams_for_path,
    _exam_is_ge,
    rebuild_rdsr_df,
)
from .offset_handlers import reset_global_offsets_on_new_load
from .settings_builder import build_settings
from .state import AppState


def load_rdsr(file_path: Path, state: AppState) -> tuple[bool, str]:
    """Parse and normalise an RDSR file and append it to the exam list.

    Accumulating: each call adds one entry to ``state.loaded_exams`` and
    ``state.loaded_exam_meta`` rather than replacing the previous load.
    Returns ``(success, message)``.
    """
    from mypyskindose.input_adapters.models import InputAdapterResult, InputProvenance

    try:
        # T20: seed per-exam meta from globals before reset zeros them.
        seed_d_lon = state.d_lon
        seed_d_ver = state.d_ver
        seed_d_lat = state.d_lat
        reset_global_offsets_on_new_load(state)
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

        # Auto-detected table origin from manufacturer/model matching — captured
        # per exam so the Phase 2.5 override can pre-fill and reset to it.
        norm = settings.normalization_settings

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
            # Pristine copy for the per-exam transform engine (Phase 2.2/2.5).
            # DICOM has no swap/flip toggles, but the table-origin override
            # (Phase 2.5) re-bases from this base.
            "base_data": df.copy(),
            "swap_lat_lon": False,
            "flip_ap1": False,
            "flip_ap2": False,
            # Axis-direction sign flips (Phase 2.4) — not exposed for DICOM (its
            # trans_dir convention is matched at normalization); seeded False so the
            # meta schema is uniform across exam types.
            "flip_tx": False,
            "flip_ty": False,
            "flip_tz": False,
            # Auto-detected table origin (from manufacturer/model matching) that a
            # manual override would replace; None override = use auto (Phase 2.5).
            "table_origin_detected": {
                "x": float(norm.trans_offset.x),
                "y": float(norm.trans_offset.y),
                "z": float(norm.trans_offset.z),
            },
            "table_origin_override": None,
            # Per-exam patient offset (Phase 2.3): default to the pre-reset global
            # offset; editable per exam in the loaded-exam list. Only consumed in
            # multi-exam mode (analyze_multiple_exams); single-exam uses global.
            "d_lon": seed_d_lon,
            "d_ver": seed_d_ver,
            "d_lat": seed_d_lat,
            "normalization_method": norm.normalization_method,
        })

        # Rebuild concat event preview from all loaded exams
        rebuild_rdsr_df(state)
        state.is_multi_exam = len(state.loaded_exams) > 1

        # Update single-file-style fields so the rest of the UI is consistent
        state.file_path = file_path
        if len(state.loaded_exams) == 1:
            state.file_name = file_path.name
        else:
            state.file_name = f"{len(state.loaded_exams)} files"

        # Extract DICOM metadata for display (last-loaded wins)
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
    from mypyskindose.input_adapters.registry import (
        SchemaDetectionError,
        read_and_normalize_input,
    )

    try:
        # T20: capture globals before reset; on re-parse keep current globals.
        seed_d_lon = state.d_lon
        seed_d_ver = state.d_ver
        seed_d_lat = state.d_lat
        if not replace_existing:
            reset_global_offsets_on_new_load(state)
        settings = build_settings(state, mode="calculate_dose")
        schema = state.input_schema or "auto"

        _raw = read_and_normalize_input(
            file_path,
            input_schema=schema,
            settings=settings,
            sheet_name=state.input_sheet_name,
        )

        # Re-parse of an existing entry (schema/sheet change): preserve the user's
        # per-exam coordinate-transform flags across the re-parse, then drop the
        # stale exam(s) now that the new parse has succeeded so the result replaces
        # rather than duplicates them.
        preserved_flags: list[dict] = []
        if replace_existing:
            preserved_flags = [
                {
                    "swap_lat_lon": m.get("swap_lat_lon", False),
                    "flip_ap1": m.get("flip_ap1", False),
                    "flip_ap2": m.get("flip_ap2", False),
                    "flip_tx": m.get("flip_tx", False),
                    "flip_ty": m.get("flip_ty", False),
                    "flip_tz": m.get("flip_tz", False),
                }
                for m in state.loaded_exam_meta
                if m.get("file_path") == file_path
            ]
            _drop_exams_for_path(state, file_path)

        if isinstance(_raw, list):
            # Multi-study file: append all exams. Coordinate transforms are applied
            # per-exam (Phase 2.2): each exam keeps a pristine ``base_data`` copy and
            # its own swap/flip flags, defaulting to an auto GE lat/lon swap for
            # non-normalized exports (preserved across a re-parse).
            new_exams = _raw
            for j, exam in enumerate(new_exams):
                schema_name = exam.provenance.schema_name
                base = exam.normalized_data.copy()
                if j < len(preserved_flags):
                    flags = preserved_flags[j]
                else:
                    flags = {
                        "swap_lat_lon": schema_name != "normalized" and _exam_is_ge(exam),
                        "flip_ap1": False,
                        "flip_ap2": False,
                        "flip_tx": False,
                        "flip_ty": False,
                        "flip_tz": False,
                    }
                exam.normalized_data = _apply_transform_flags(
                    base, flags["swap_lat_lon"], flags["flip_ap1"],
                    flags["flip_ap2"], schema_name,
                    flip_tx=flags.get("flip_tx", False),
                    flip_ty=flags.get("flip_ty", False),
                    flip_tz=flags.get("flip_tz", False),
                )
                state.loaded_exams.append(exam)
                state.loaded_exam_meta.append({
                    "file_name": file_path.name,
                    "file_path": file_path,
                    "source_type": file_path.suffix.lstrip("."),
                    "schema": schema_name,
                    "sheet": state.input_sheet_name,
                    "provenance": exam.provenance,
                    "warnings": list(exam.warnings),
                    "base_data": base,
                    "swap_lat_lon": flags["swap_lat_lon"],
                    "flip_ap1": flags["flip_ap1"],
                    "flip_ap2": flags["flip_ap2"],
                    "flip_tx": flags.get("flip_tx", False),
                    "flip_ty": flags.get("flip_ty", False),
                    "flip_tz": flags.get("flip_tz", False),
                    # Tabular exports carry no normalization trans_offset, so the
                    # auto-detected origin is zero; a manual override (Phase 2.5) is
                    # then an absolute table-origin shift.
                    "table_origin_detected": {"x": 0.0, "y": 0.0, "z": 0.0},
                    "table_origin_override": None,
                    "d_lon": seed_d_lon,
                    "d_ver": seed_d_ver,
                    "d_lat": seed_d_lat,
                    "normalization_method": "Tabular",
                })
            result = _raw[0]  # use first exam's provenance for UI hints
            total_events = sum(len(e.normalized_data) for e in new_exams)
            msg = f"Loaded {len(new_exams)} exams, {total_events} total events from {file_path.name}"
        else:
            # Single-study file: keep a pristine base copy and apply the current
            # global coordinate-transform flags (which _set_transform_defaults()
            # finalises after this call). Storing base_data keeps the single-exam
            # entry consistent with the per-exam engine, so it transitions cleanly
            # if more files are added (Phase 2.2).
            result = _raw
            base = result.normalized_data.copy()
            if replace_existing and preserved_flags:
                flags = preserved_flags[0]
            else:
                flags = {
                    "swap_lat_lon": state.swap_lat_lon,
                    "flip_ap1": state.flip_ap1,
                    "flip_ap2": state.flip_ap2,
                    "flip_tx": False,
                    "flip_ty": False,
                    "flip_tz": False,
                }
            result.normalized_data = _apply_transform_flags(
                base, flags["swap_lat_lon"], flags["flip_ap1"],
                flags["flip_ap2"], result.provenance.schema_name,
                flip_tx=flags.get("flip_tx", False),
                flip_ty=flags.get("flip_ty", False),
                flip_tz=flags.get("flip_tz", False),
            )
            state.loaded_exams.append(result)
            state.loaded_exam_meta.append({
                "file_name": file_path.name,
                "file_path": file_path,
                "source_type": file_path.suffix.lstrip("."),
                "schema": result.provenance.schema_name,
                "sheet": state.input_sheet_name,
                "provenance": result.provenance,
                "warnings": list(result.warnings),
                "base_data": base,
                "swap_lat_lon": flags["swap_lat_lon"],
                "flip_ap1": flags["flip_ap1"],
                "flip_ap2": flags["flip_ap2"],
                "flip_tx": flags.get("flip_tx", False),
                "flip_ty": flags.get("flip_ty", False),
                "flip_tz": flags.get("flip_tz", False),
                "table_origin_detected": {"x": 0.0, "y": 0.0, "z": 0.0},
                "table_origin_override": None,
                "d_lon": seed_d_lon,
                "d_ver": seed_d_ver,
                "d_lat": seed_d_lat,
                "normalization_method": "Tabular",
            })
            msg = f"Loaded {len(result.normalized_data)} events from {file_path.name} ({result.provenance.schema_name})"

        # Rebuild concat event preview from all loaded exams.
        rebuild_rdsr_df(state)
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
