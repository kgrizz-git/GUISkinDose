"""Load RDSR and tabular exams into AppState."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
import pydicom

from mypyskindose.rdsr_parser import rdsr_parser
from mypyskindose.rdsr_normalizer import RdsrUnitError, rdsr_normalizer
from mypyskindose.privacy import safe_error_event

from .exam_transforms import (
    _apply_transform_flags,
    _drop_exams_for_path,
    rebuild_rdsr_df,
)
from .geometry_preview import on_exams_loaded
from .offset_handlers import reset_global_offsets_on_new_load
from .settings_builder import build_settings
from .state import AppState


logger = logging.getLogger(__name__)


def _record_load_failure(operation: str, exc: BaseException) -> None:
    """Record a value-free load failure without persisting source-data details."""
    safe_error_event(logger, operation, exc)


def _raw_extracted_view(result) -> pd.DataFrame | None:
    """Build the 'raw (un-normalized)' Data-tab view from a tabular adapter result.

    ``result.raw_data`` is the verbatim ``header=None`` file read, so it still
    carries any pre-header banner/numbering rows and uses positional integer
    column names. For the raw *view* we want the raw source *values* with the
    real column headers promoted and the pre-header junk / wholly-blank rows
    dropped — i.e. what the adapter actually extracted, minus column mapping,
    renaming, and numeric coercion. ``extract_table`` does exactly this using the
    header row the adapter already detected. Falls back to the verbatim frame if
    anything is missing (e.g. a synthetic DICOM result).
    """
    from mypyskindose.input_adapters.base import extract_table

    raw = getattr(result, "raw_data", None)
    header_idx = getattr(getattr(result, "provenance", None), "header_row_index", None)
    if raw is None or header_idx is None:
        return raw
    try:
        _, extracted = extract_table(raw, int(header_idx))
        return extracted.reset_index(drop=True)
    except Exception:
        return raw


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
        on_exams_loaded(state)
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

        return True, f"Loaded {len(df)} irradiation events"
    except RdsrUnitError as exc:
        # Unit mismatch is a specific, actionable condition — surface the
        # unit-naming message (units are not PHI) instead of the generic error.
        _record_load_failure("DICOM_RDSR_UNIT_MISMATCH", exc)
        return False, str(exc)
    except Exception as exc:
        _record_load_failure("DICOM_RDSR_LOAD", exc)
        return False, "Could not read this DICOM RDSR file. Check the file and try again."


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
    from mypyskindose.input_adapters.registry import SchemaDetectionError

    try:
        result, msg = _parse_tabular(file_path, state, replace_existing=replace_existing)
        # Finalize stays inside the try so failures in the post-load state wiring
        # (concat rebuild, provenance) surface as the graceful error below rather
        # than propagating uncaught, matching the pre-refactor behaviour.
        _finalize_tabular_state(state, file_path, result)
    except SchemaDetectionError as exc:
        return _wrap_tabular_schema_detection(state, exc)
    except Exception as exc:
        _record_load_failure("TABULAR_LOAD", exc)
        state.import_has_errors = True
        return False, "Could not read this file. Check the file and try again."

    return True, msg


def _parse_tabular(
    file_path: Path,
    state: AppState,
    *,
    replace_existing: bool = False,
) -> tuple[Any, str]:
    """Read a tabular file, build per-exam meta, append to ``state`` exam list.

    Returns ``(result_for_finalize, message)`` where ``result_for_finalize`` is
    the adapter result used by :func:`_finalize_tabular_state` for provenance /
    raw view wiring. Raises ``SchemaDetectionError`` or any adapter error to be
    translated by the caller.
    """
    from mypyskindose.input_adapters.registry import read_and_normalize_input

    # T20: capture globals before reset; on re-parse keep current globals.
    seed_d_lon = state.d_lon
    seed_d_ver = state.d_ver
    seed_d_lat = state.d_lat
    if not replace_existing:
        reset_global_offsets_on_new_load(state)
    settings = build_settings(state, mode="calculate_dose")
    schema = state.input_schema or "auto"

    raw = read_and_normalize_input(
        file_path,
        input_schema=schema,
        settings=settings,
        sheet_name=state.input_sheet_name,
    )

    preserved_flags = _collect_preserved_flags(state, file_path, replace_existing)
    if replace_existing:
        _drop_exams_for_path(state, file_path)

    if isinstance(raw, list):
        return _append_multi_study_exams(raw, state, file_path, seed_d_lon, seed_d_ver, seed_d_lat, preserved_flags)
    return _append_single_study_exam(raw, state, file_path, seed_d_lon, seed_d_ver, seed_d_lat, preserved_flags)


def _collect_preserved_flags(
    state: AppState, file_path: Path, replace_existing: bool
) -> list[dict]:
    """Collect per-exam coordinate-transform flags from prior loads of file_path."""
    if not replace_existing:
        return []
    return [
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


def _default_transform_flags(state: AppState) -> dict:
    return {
        "swap_lat_lon": state.swap_lat_lon,
        "flip_ap1": state.flip_ap1,
        "flip_ap2": state.flip_ap2,
        "flip_tx": False,
        "flip_ty": False,
        "flip_tz": False,
    }


def _blank_transform_flags() -> dict:
    return {
        "swap_lat_lon": False,
        "flip_ap1": False,
        "flip_ap2": False,
        "flip_tx": False,
        "flip_ty": False,
        "flip_tz": False,
    }


def _build_exam_meta_entry(
    state: AppState,
    file_path: Path,
    schema_name: str,
    base: pd.DataFrame,
    provenance,
    warnings,
    flags: dict,
    seed_d_lon: float,
    seed_d_ver: float,
    seed_d_lat: float,
) -> dict:
    """Construct a per-exam meta entry shared by single and multi-study paths."""
    return {
        "file_name": file_path.name,
        "file_path": file_path,
        "source_type": file_path.suffix.lstrip("."),
        "schema": schema_name,
        "sheet": state.input_sheet_name,
        "provenance": provenance,
        "warnings": list(warnings),
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
    }


def _append_multi_study_exams(
    raw_exams: list,
    state: AppState,
    file_path: Path,
    seed_d_lon: float,
    seed_d_ver: float,
    seed_d_lat: float,
    preserved_flags: list[dict],
) -> tuple[Any, str]:
    """Append every exam from a multi-study tabular file and rebuild concat preview."""
    new_exams = raw_exams
    for j, exam in enumerate(new_exams):
        schema_name = exam.provenance.schema_name
        base = exam.normalized_data.copy()
        flags = preserved_flags[j] if j < len(preserved_flags) else _blank_transform_flags()
        exam.normalized_data = _apply_transform_flags(
            base, flags["swap_lat_lon"], flags["flip_ap1"],
            flags["flip_ap2"], schema_name,
            flip_tx=flags.get("flip_tx", False),
            flip_ty=flags.get("flip_ty", False),
            flip_tz=flags.get("flip_tz", False),
        )
        state.loaded_exams.append(exam)
        state.loaded_exam_meta.append(
            _build_exam_meta_entry(
                state, file_path, schema_name, base, exam.provenance, exam.warnings,
                flags, seed_d_lon, seed_d_ver, seed_d_lat,
            )
        )
    result_for_finalize = raw_exams[0]  # use first exam's provenance for UI hints
    total_events = sum(len(e.normalized_data) for e in new_exams)
    msg = f"Loaded {len(new_exams)} exams, {total_events} total events"
    return result_for_finalize, msg


def _append_single_study_exam(
    result,
    state: AppState,
    file_path: Path,
    seed_d_lon: float,
    seed_d_ver: float,
    seed_d_lat: float,
    preserved_flags: list[dict],
) -> tuple[Any, str]:
    """Append a single-exam tabular file and rebuild concat preview."""
    base = result.normalized_data.copy()
    flags = preserved_flags[0] if (preserved_flags) else _default_transform_flags(state)
    result.normalized_data = _apply_transform_flags(
        base, flags["swap_lat_lon"], flags["flip_ap1"],
        flags["flip_ap2"], result.provenance.schema_name,
        flip_tx=flags.get("flip_tx", False),
        flip_ty=flags.get("flip_ty", False),
        flip_tz=flags.get("flip_tz", False),
    )
    state.loaded_exams.append(result)
    state.loaded_exam_meta.append(
        _build_exam_meta_entry(
            state, file_path, result.provenance.schema_name, base, result.provenance, result.warnings,
            flags, seed_d_lon, seed_d_ver, seed_d_lat,
        )
    )
    msg = f"Loaded {len(result.normalized_data)} events ({result.provenance.schema_name})"
    return result, msg


def _finalize_tabular_state(state: AppState, file_path: Path, result) -> None:
    """Apply shared post-load state: concat preview, file naming, provenance, offsets."""
    rebuild_rdsr_df(state)
    on_exams_loaded(state)
    state.is_multi_exam = len(state.loaded_exams) > 1

    # Per-file state used by the import preview and schema re-parse path.
    # The raw *view* shows the extracted source values (real headers, no
    # pre-header banner/blank rows), not the verbatim header=None dump.
    state.rdsr_raw_df = _raw_extracted_view(result)
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


def _wrap_tabular_schema_detection(state: AppState, exc: BaseException) -> tuple[bool, str]:
    """Translate a SchemaDetectionError into the user-facing retry hint."""
    _record_load_failure("TABULAR_SCHEMA_DETECTION", exc)
    state.import_has_errors = True
    return False, (
        "Couldn't auto-detect this file's format. Open the “Input schema” "
        "selector below and choose the matching format (e.g. Radimetrics CSV, "
        "DoseTrack, Raw RDSR-like, or Normalized), then upload the file again."
    )
