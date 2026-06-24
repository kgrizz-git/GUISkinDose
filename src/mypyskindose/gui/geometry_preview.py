"""Active-exam index lifecycle and sliced preview frames for the Geometry tab."""

from __future__ import annotations

import pandas as pd

from .exam_transforms import EXAM_COLUMN, EXAM_INDEX_COLUMN
from .state import AppState


def clamp_active_exam_index(state: AppState) -> None:
    """Keep ``active_exam_index`` in range and sync ``is_multi_exam``."""
    n = len(state.loaded_exams)
    state.is_multi_exam = n > 1
    if n == 0:
        state.active_exam_index = None
    elif state.active_exam_index is None:
        state.active_exam_index = 0
    else:
        state.active_exam_index = min(state.active_exam_index, n - 1)


def adjust_active_exam_index_after_remove(state: AppState, removed_index: int) -> None:
    """Reconcile ``active_exam_index`` after an exam row is removed."""
    n = len(state.loaded_exams)
    state.is_multi_exam = n > 1
    if n == 0:
        state.active_exam_index = None
        return
    active = state.active_exam_index
    if active is None:
        state.active_exam_index = 0
        return
    if removed_index < active:
        state.active_exam_index = active - 1
    elif removed_index == active:
        state.active_exam_index = max(0, active - 1)
    idx = state.active_exam_index if state.active_exam_index is not None else 0
    state.active_exam_index = min(idx, n - 1)


def on_exams_loaded(state: AppState) -> None:
    """Set ``active_exam_index`` after loaders append exams."""
    n = len(state.loaded_exams)
    if n == 1:
        state.active_exam_index = 0
    else:
        clamp_active_exam_index(state)


def exam_select_value(
    active_exam_index: int | None,
    option_indices: set[int] | frozenset[int],
) -> int | None:
    """NiceGUI select value: None when empty; else active index if valid, else first option."""
    if not option_indices:
        return None
    idx = active_exam_index if active_exam_index is not None else 0
    return idx if idx in option_indices else min(option_indices)


def effective_patient_offset_for_preview(
    state: AppState,
    active_exam_index: int | None = None,
) -> tuple[float, float, float]:
    """Patient offset for the Geometry preview phantom."""
    idx = active_exam_index if active_exam_index is not None else state.active_exam_index
    if state.is_multi_exam and idx is not None and idx < len(state.loaded_exam_meta):
        m = state.loaded_exam_meta[idx]
        return (
            float(m.get("d_lon", 0.0)),
            float(m.get("d_ver", 0.0)),
            float(m.get("d_lat", 0.0)),
        )
    return (state.d_lon, state.d_ver, state.d_lat)


def rdsr_df_for_geometry_preview(
    state: AppState,
    *,
    active_exam_index: int | None = None,
    composite: bool = False,
) -> pd.DataFrame | None:
    """Return a preview-sized event frame (tags stripped) for ``make_geometry_fig``."""
    if state.rdsr_df is None:
        return None

    df = state.rdsr_df
    if state.is_multi_exam and not composite:
        idx = active_exam_index if active_exam_index is not None else state.active_exam_index
        if idx is not None and EXAM_INDEX_COLUMN in df.columns:
            df = df[df[EXAM_INDEX_COLUMN] == idx]

    out = df.drop(columns=[EXAM_INDEX_COLUMN, EXAM_COLUMN], errors="ignore").copy()
    return out.reset_index(drop=True)


def preview_event_count(
    state: AppState,
    *,
    active_exam_index: int | None = None,
    composite: bool = False,
) -> int:
    """Event count for the current Geometry preview slice."""
    df = rdsr_df_for_geometry_preview(
        state,
        active_exam_index=active_exam_index,
        composite=composite,
    )
    return len(df) if df is not None else 0


def resolve_composite_for_render(
    *,
    composite_preview: bool,
    last_table_origin_scrub: bool,
) -> bool:
    """Whether the Geometry preview should include all exams' events."""
    if last_table_origin_scrub:
        return True
    return composite_preview


def composite_preview_after_exam_mode_change(
    was_multi_exam: bool,
    is_multi_exam: bool,
    current_composite_preview: bool,
) -> bool:
    """Reset composite toggle when transitioning multi-exam → single-exam (T28)."""
    if was_multi_exam and not is_multi_exam:
        return False
    return current_composite_preview


_C4_TABLE_ORIGIN_PREVIEW_CAPTION = (
    "Table shift applies to the selected exam. Preview shows all exams; "
    "you will see this exam's table move relative to the others."
)


def geometry_preview_caption(
    state: AppState,
    *,
    composite_preview: bool,
    last_table_origin_scrub: bool,
) -> str:
    """User-facing preview caption for multi-exam Geometry (C3 / C4)."""
    if not state.is_multi_exam:
        return ""
    exam_num = (state.active_exam_index or 0) + 1
    if last_table_origin_scrub:
        return _C4_TABLE_ORIGIN_PREVIEW_CAPTION
    if composite_preview:
        return (
            f"Preview: all exams' events; phantom position is exam #{exam_num} only — "
            "other exams use their own offsets at Calculate."
        )
    return f"Preview: exam #{exam_num} events only, phantom at this exam's offset."


def clamp_geometry_event_index(
    state: AppState,
    current_index: int,
    *,
    active_exam_index: int | None = None,
    composite: bool = False,
) -> int:
    """Clamp a Geometry event index to the current preview slice (N4)."""
    if state.rdsr_df is None:
        return 0
    slice_count = preview_event_count(
        state,
        active_exam_index=active_exam_index,
        composite=composite,
    )
    if slice_count <= 0:
        return 0
    return min(max(0, current_index), slice_count - 1)


def composite_live_preview_paused(
    state: AppState,
    *,
    last_preview_mode: str | None,
    composite_preview: bool,
    last_table_origin_scrub: bool,
    pause_threshold: int = 30,
) -> bool:
    """True when plot_procedure live preview should show PAUSED (T8, T27)."""
    if last_preview_mode != "plot_procedure" or not state.is_multi_exam:
        return False
    composite = resolve_composite_for_render(
        composite_preview=composite_preview,
        last_table_origin_scrub=last_table_origin_scrub,
    )
    if not composite:
        return False
    active_idx = state.active_exam_index
    return preview_event_count(state, active_exam_index=active_idx, composite=True) > pause_threshold
