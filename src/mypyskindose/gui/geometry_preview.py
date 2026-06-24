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
    state.active_exam_index = min(state.active_exam_index, n - 1)


def on_exams_loaded(state: AppState) -> None:
    """Set ``active_exam_index`` after loaders append exams."""
    n = len(state.loaded_exams)
    if n == 1:
        state.active_exam_index = 0
    else:
        clamp_active_exam_index(state)


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
