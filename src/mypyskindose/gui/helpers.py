"""GUI helper functions: build settings objects, run calculations, etc.

Public API is re-exported here for backward compatibility. Implementation lives in
focused modules (``settings_builder``, ``exam_loaders``, ``exam_transforms``,
``offset_handlers``) to stay under the CI per-file line cap.
"""

from __future__ import annotations

import logging
import traceback
from pathlib import Path

from .exam_loaders import get_excel_sheets, load_rdsr, load_tabular
from .exam_transforms import (
    EXAM_COLUMN,
    _table_origin_override_note,  # noqa: F401 — tests import via helpers
    apply_exam_transforms,
    clear_multi_exam_state,
    exam_supports_table_origin,
    exam_supports_transforms,
    rebuild_rdsr_df,
)
from .offset_handlers import (
    any_table_origin_override,
    commit_table_origin_transform,
    effective_table_origin,
    on_global_patient_offset_change,
    on_global_patient_offset_scrub,
    reset_global_offsets_on_new_load,
    restore_globals_from_exam_meta,
    stage_table_origin_axis,
    sync_global_patient_offset_to_single_exam_meta,
)
from .settings_builder import build_settings, fallback_normalization_exam_count
from .state import AppState

__all__ = [
    "EXAM_COLUMN",
    "any_table_origin_override",
    "apply_exam_transforms",
    "below_floor_event_count",
    "build_settings",
    "clear_multi_exam_state",
    "commit_table_origin_transform",
    "effective_patient_offset_for_preview",
    "effective_table_origin",
    "event_count_from_state",
    "exam_supports_table_origin",
    "exam_supports_transforms",
    "fallback_normalization_exam_count",
    "get_example_rdsr_files",
    "get_excel_sheets",
    "get_human_mesh_names",
    "load_rdsr",
    "load_tabular",
    "on_global_patient_offset_change",
    "on_global_patient_offset_scrub",
    "rebuild_rdsr_df",
    "reset_global_offsets_on_new_load",
    "restore_globals_from_exam_meta",
    "run_calculation",
    "stage_table_origin_axis",
    "sync_global_patient_offset_to_single_exam_meta",
]


class _CalcWarningCollector(logging.Handler):
    """Collects WARNING+ log messages emitted during a dose calculation so the GUI
    can surface them (e.g. how many events had their HVL snapped to the grid)."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def effective_patient_offset_for_preview(app_state: AppState) -> tuple[float, float, float]:
    """Patient offset used by the Geometry preview (global until active_exam_index ships)."""
    return (app_state.d_lon, app_state.d_ver, app_state.d_lat)


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
