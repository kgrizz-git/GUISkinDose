"""Patient-offset and table-origin handler helpers for the GUI.

Extracted from helpers.py to keep file sizes under the CI line cap. Covers global
offset reset/sync on load, preview offset resolution, and table-origin staging.
"""

from __future__ import annotations

from .page_context import PageContext
from .state import AppState, reset_results, state


def reset_global_offsets_on_new_load(app_state: AppState) -> None:
    """Zero global patient offsets and coordinate flags before a fresh file load."""
    app_state.d_lon = 0.0
    app_state.d_ver = 0.0
    app_state.d_lat = 0.0
    app_state.swap_lat_lon = False
    app_state.flip_ap1 = False
    app_state.flip_ap2 = False


def restore_globals_from_exam_meta(app_state: AppState, meta0: dict) -> None:
    """Restore global offset and coordinate flags from the sole remaining exam meta."""
    app_state.swap_lat_lon = bool(meta0.get("swap_lat_lon", False))
    app_state.flip_ap1 = bool(meta0.get("flip_ap1", False))
    app_state.flip_ap2 = bool(meta0.get("flip_ap2", False))
    app_state.d_lon = float(meta0.get("d_lon", 0.0))
    app_state.d_ver = float(meta0.get("d_ver", 0.0))
    app_state.d_lat = float(meta0.get("d_lat", 0.0))


def sync_global_patient_offset_to_single_exam_meta(app_state: AppState) -> None:
    """Mirror global patient offset into meta[0] when only one exam is loaded."""
    if len(app_state.loaded_exams) == 1 and app_state.loaded_exam_meta:
        m = app_state.loaded_exam_meta[0]
        m["d_lon"] = app_state.d_lon
        m["d_ver"] = app_state.d_ver
        m["d_lat"] = app_state.d_lat


def active_exam_index_for_offsets(app_state: AppState) -> int:
    """0-based exam index used for Geometry patient-offset read/write."""
    if app_state.is_multi_exam and app_state.active_exam_index is not None:
        return app_state.active_exam_index
    return 0


def read_patient_offset_value(
    app_state: AppState,
    attr: str,
    active_index: int | None = None,
) -> float:
    """Read one patient-offset axis from per-exam meta (multi) or globals (single)."""
    idx = active_index if active_index is not None else active_exam_index_for_offsets(app_state)
    if app_state.is_multi_exam and idx < len(app_state.loaded_exam_meta):
        return float(app_state.loaded_exam_meta[idx].get(attr, 0.0))
    return float(getattr(app_state, attr))


def apply_patient_offset_slider_tick(app_state: AppState, attr: str, value: float) -> None:
    """Geometry slider tick: write meta[active] in multi-exam, globals + meta[0] in single."""
    if app_state.is_multi_exam:
        idx = active_exam_index_for_offsets(app_state)
        if idx < len(app_state.loaded_exam_meta):
            app_state.loaded_exam_meta[idx][attr] = float(value)
    else:
        setattr(app_state, attr, float(value))
        sync_global_patient_offset_to_single_exam_meta(app_state)


def reset_patient_offset_for_active(app_state: AppState) -> None:
    """Zero patient offset for the active exam (multi) or globals + meta[0] (single)."""
    if app_state.is_multi_exam:
        idx = active_exam_index_for_offsets(app_state)
        if idx < len(app_state.loaded_exam_meta):
            m = app_state.loaded_exam_meta[idx]
            m["d_lon"] = 0.0
            m["d_ver"] = 0.0
            m["d_lat"] = 0.0
    else:
        app_state.d_lon = 0.0
        app_state.d_ver = 0.0
        app_state.d_lat = 0.0
        sync_global_patient_offset_to_single_exam_meta(app_state)


def on_global_patient_offset_scrub(ctx: PageContext) -> None:
    sync_global_patient_offset_to_single_exam_meta(state)


def on_global_patient_offset_change(ctx: PageContext) -> None:
    on_global_patient_offset_scrub(ctx)
    reset_results()
    ctx.refresh_per_exam()


def effective_table_origin(meta: dict) -> dict[str, float]:
    detected = meta.get("table_origin_detected") or {"x": 0.0, "y": 0.0, "z": 0.0}
    ov = meta.get("table_origin_override")
    if ov is not None:
        return {k: float(ov.get(k, detected[k])) for k in ("x", "y", "z")}
    return {k: float(detected[k]) for k in ("x", "y", "z")}


def stage_table_origin_axis(meta: dict, axis: str, value: float) -> None:
    """Tick path: update per-exam table-origin override meta only (O(1), no DataFrame work)."""
    detected = meta.get("table_origin_detected") or {"x": 0.0, "y": 0.0, "z": 0.0}
    if meta.get("table_origin_override") is None:
        meta["table_origin_override"] = dict(detected)
    meta["table_origin_override"][axis] = float(value)


def commit_table_origin_transform(app_state: AppState, exam_index: int) -> None:
    """Debounced / discrete commit: re-derive normalized event data from base + flags."""
    from .exam_transforms import apply_exam_transforms

    apply_exam_transforms(app_state, exam_index)


def any_table_origin_override(app_state: AppState) -> bool:
    return any(m.get("table_origin_override") is not None for m in app_state.loaded_exam_meta)
