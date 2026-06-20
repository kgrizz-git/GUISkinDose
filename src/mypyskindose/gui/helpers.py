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

# Display-only column added to the concatenated multi-exam preview frame
# (state.rdsr_df) so the Data Table can show which exam each row came from. It is
# never sent to the dose calculation: the single-exam calc path drops it before
# analyze_data, and the multi-exam path reads per-exam normalized_data directly.
EXAM_COLUMN = "Exam"


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
    base["below_floor_kvp_policy"] = state.below_floor_kvp_policy
    base["below_floor_kvp_manual"] = state.below_floor_kvp_manual
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
            # Per-exam patient offset (Phase 2.3): default to the current global
            # offset; editable per exam in the loaded-exam list. Only consumed in
            # multi-exam mode (analyze_multiple_exams); single-exam uses global.
            "d_lon": state.d_lon,
            "d_ver": state.d_ver,
            "d_lat": state.d_lat,
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
                    "d_lon": state.d_lon,
                    "d_ver": state.d_ver,
                    "d_lat": state.d_lat,
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
                "d_lon": state.d_lon,
                "d_ver": state.d_ver,
                "d_lat": state.d_lat,
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
            
            # Per-exam patient offsets (Phase 2.3). Each exam's offset is stored in
            # its loaded_exam_meta entry (defaulting to the global offset at load
            # time, editable in the upload tab). Fall back to the global offset for
            # any exam whose meta is missing a value.
            per_exam_offsets = [
                [
                    float(m.get("d_lon", state.d_lon)),
                    float(m.get("d_ver", state.d_ver)),
                    float(m.get("d_lat", state.d_lat)),
                ]
                for m in state.loaded_exam_meta
            ]

            # Audit note (Phase 2.5): a manual table-origin override materially
            # changes the dose map, so record it per exam (lands in
            # ExamResult.warnings → export) for any exam with an active override.
            per_exam_extra_warnings = [
                _table_origin_override_note(m) for m in state.loaded_exam_meta
            ]

            # analyze_multiple_exams internally handles logging and tqdm patch
            multi_result = analyze_multiple_exams(
                exams=state.loaded_exams,
                settings=settings,
                per_exam_offsets=per_exam_offsets,
                per_exam_extra_warnings=per_exam_extra_warnings,
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
                # analyze_data internally calls calculate_rotation_matrices.
                # Drop the display-only exam tag if present (defensive — single-exam
                # frames don't carry it, but never let it reach the calculation).
                calc_df = state.rdsr_df.drop(columns=EXAM_COLUMN, errors="ignore").copy()
                output = analyze_data(normalized_data=calc_df, settings=settings)
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


def below_floor_event_count(state: AppState) -> int:
    """Total events across all loaded exams with kVp below the HVL table floor.

    Drives the pre-calc prompt: the floor policy is applied per exam inside
    ``calculate_dose``, so this mirrors that by summing each exam's normalized
    frame. Returns 0 when nothing is loaded.
    """
    from mypyskindose.geom_calc import count_below_floor_events

    total = 0
    for exam in state.loaded_exams:
        df = getattr(exam, "normalized_data", None)
        if df is not None:
            total += len(count_below_floor_events(df))
    return total


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


_GE_MANUFACTURER_WARNING = "ge manufacturer detected"


def _exam_is_ge(exam) -> bool:
    """True if a tabular exam's import warnings flag GE equipment.

    GE stores lat/lon in the opposite convention to MyPySkinDose, so GE exports
    need a Tx ↔ Tz swap. Tabular adapters surface the detected manufacturer as a
    warning; DICOM conventions are handled at normalization, not here.
    """
    warnings_lower = " ".join(getattr(exam, "warnings", []) or []).lower()
    return _GE_MANUFACTURER_WARNING in warnings_lower


def _apply_transform_flags(
    base,
    swap_lat_lon,
    flip_ap1,
    flip_ap2,
    schema_name,
    table_origin_override=None,
    table_origin_detected=None,
    flip_tx=False,
    flip_ty=False,
    flip_tz=False,
):
    """Return a copy of ``base`` with the coordinate-correction flags applied.

    Always derives from the pristine ``base`` frame, so applying is idempotent and
    order-independent (each flag is an involution). The lat/lon swap and the
    axis-direction sign flips are skipped for the already-canonical ``normalized``
    schema.

    ``flip_tx`` / ``flip_ty`` / ``flip_tz`` (Phase 2.4): reverse the sign
    (direction) of a table-position axis, mirroring a per-manufacturer
    ``trans_dir`` of ``-`` at normalization. The reversal pivots about the
    auto-detected origin (``col → 2·detected − col``), so it reverses the table
    *motion* without moving the origin; for tabular exports (``detected`` = 0) this
    is a plain negation. Applied first, in the detected (pre-swap) frame.

    ``table_origin_override`` (Phase 2.5): when set (a ``{"x","y","z"}`` cm dict),
    re-bases the table position columns by ``(override − detected)``, applied in
    the detected (pre-swap) frame so the numeric origin shift composes correctly
    with any swap/flip. ``table_origin_detected`` is the auto-detected origin the
    override replaces (defaults to zero per axis).
    """
    df = base.copy()
    detected = table_origin_detected or {"x": 0.0, "y": 0.0, "z": 0.0}
    if schema_name != "normalized":
        for flip, col, key in (
            (flip_tx, "Tx", "x"),
            (flip_ty, "Ty", "y"),
            (flip_tz, "Tz", "z"),
        ):
            if flip and col in df.columns:
                pivot = float(detected.get(key, 0.0))
                df[col] = 2.0 * pivot - df[col]
    if table_origin_override is not None:
        for col, key in (("Tx", "x"), ("Ty", "y"), ("Tz", "z")):
            if col in df.columns:
                delta = float(table_origin_override.get(key, 0.0)) - float(
                    detected.get(key, 0.0)
                )
                if delta:
                    df[col] = df[col] + delta
    if (
        swap_lat_lon
        and schema_name != "normalized"
        and "Tx" in df.columns
        and "Tz" in df.columns
    ):
        df["Tx"], df["Tz"] = df["Tz"].copy(), df["Tx"].copy()
    if flip_ap1 and "Ap1" in df.columns:
        df["Ap1"] = -df["Ap1"]
    if flip_ap2 and "Ap2" in df.columns:
        df["Ap2"] = -df["Ap2"]
    return df


def exam_supports_transforms(exam, meta: dict) -> bool:
    """True if per-exam coordinate-transform toggles are meaningful for this exam.

    Only non-normalized tabular exams qualify: DICOM conventions are applied at
    normalization, and the ``normalized`` schema is already in MyPySkinDose
    convention.
    """
    src = (meta.get("source_type") or "").lower()
    if src in ("", "dicom", "dcm"):
        return False
    schema = meta.get("schema") or getattr(
        getattr(exam, "provenance", None), "schema_name", ""
    )
    return schema != "normalized"


def _table_origin_override_note(meta: dict) -> list[str]:
    """Return a one-item audit note if this exam has an active table-origin
    override, else an empty list (for ``per_exam_extra_warnings``)."""
    override = meta.get("table_origin_override")
    if override is None:
        return []
    detected = meta.get("table_origin_detected") or {"x": 0.0, "y": 0.0, "z": 0.0}
    return [
        "Manual table-origin override applied: "
        f"({override.get('x', 0.0)}, {override.get('y', 0.0)}, "
        f"{override.get('z', 0.0)}) cm "
        f"(auto-detected was ({detected.get('x', 0.0)}, "
        f"{detected.get('y', 0.0)}, {detected.get('z', 0.0)}) cm)."
    ]


def exam_supports_table_origin(exam, meta: dict) -> bool:
    """True if a manual table-origin override is meaningful for this exam.

    Any exam with table-position columns qualifies: a DICOM exam with a misdetected
    scanner (fallback normalization), or a tabular export lacking convention
    metadata. Requires a stored pristine ``base_data`` to re-base from.
    """
    base = meta.get("base_data")
    if base is None:
        return False
    cols = getattr(base, "columns", [])
    return any(c in cols for c in ("Tx", "Ty", "Tz"))


def rebuild_rdsr_df(state: AppState) -> None:
    """Rebuild ``state.rdsr_df`` from all loaded exams' normalized data.

    Single source of truth for the concatenated event preview. In multi-exam mode
    each row is tagged with a leading :data:`EXAM_COLUMN` (``"#<n> · <file>"``) so
    the Data Table can show which exam it came from; single-exam frames are left
    untouched (no extra column). The tag is display/export only — see
    :data:`EXAM_COLUMN`. No-op-safe: clears ``rdsr_df`` when no exams are loaded.
    """
    import pandas as pd

    if not state.loaded_exams:
        state.rdsr_df = None
        return

    multi = len(state.loaded_exams) > 1
    frames = []
    for i, exam in enumerate(state.loaded_exams):
        df = exam.normalized_data
        if multi:
            df = df.copy()
            meta = state.loaded_exam_meta[i] if i < len(state.loaded_exam_meta) else {}
            df.insert(0, EXAM_COLUMN, f"#{i + 1} · {meta.get('file_name', '—')}")
        frames.append(df)
    state.rdsr_df = pd.concat(frames, ignore_index=True)


def apply_exam_transforms(state: AppState, index: int) -> None:
    """Re-derive one exam's normalized_data from its base + flags; rebuild preview.

    Reads ``loaded_exam_meta[index]`` for the pristine ``base_data`` and the
    swap/flip flags, writes the transformed frame back to
    ``loaded_exams[index].normalized_data``, and rebuilds the concatenated
    ``state.rdsr_df`` preview from all exams. No-op if the exam has no stored base
    (e.g. a DICOM exam, which has no coordinate toggles).
    """
    if not (0 <= index < len(state.loaded_exams)):
        return
    exam = state.loaded_exams[index]
    meta = state.loaded_exam_meta[index] if index < len(state.loaded_exam_meta) else {}
    base = meta.get("base_data")
    if base is None:
        return
    schema_name = meta.get("schema") or getattr(
        getattr(exam, "provenance", None), "schema_name", ""
    )
    exam.normalized_data = _apply_transform_flags(
        base,
        meta.get("swap_lat_lon", False),
        meta.get("flip_ap1", False),
        meta.get("flip_ap2", False),
        schema_name,
        table_origin_override=meta.get("table_origin_override"),
        table_origin_detected=meta.get("table_origin_detected"),
        flip_tx=meta.get("flip_tx", False),
        flip_ty=meta.get("flip_ty", False),
        flip_tz=meta.get("flip_tz", False),
    )
    rebuild_rdsr_df(state)


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
