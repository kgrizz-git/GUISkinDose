"""Active-exam index lifecycle and sliced preview frames for the Geometry tab."""

from __future__ import annotations

import pandas as pd

from .exam_transforms import EXAM_COLUMN, EXAM_INDEX_COLUMN
from .state import AppState

_GE_WARNING_TOKEN = "ge manufacturer detected"


def geometry_vendor_notice(
    meta: dict,
    *,
    manufacturer: str = "",
    model: str = "",
    normalization_method: str = "",
) -> str:
    """Return a compact active-exam coordinate-convention notice for Geometry."""
    warnings = " ".join(meta.get("warnings", []) or []).lower()
    mfr = (manufacturer or meta.get("manufacturer") or "").strip()
    mdl = (model or meta.get("model") or "").strip()
    schema = (meta.get("schema") or "").strip()
    source = (meta.get("source_type") or "").strip().upper()
    method = (meta.get("normalization_method") or normalization_method or "").strip()
    parts: list[str] = []
    if mfr or mdl or method or schema:
        subject = " / ".join(s for s in (mfr, mdl) if s)
        details = " · ".join(s for s in (source, schema, method) if s)
        parts.append("Active exam: " + " · ".join(s for s in (subject, details) if s))
    if method == "Fallback":
        parts.append("Default normalization in use; verify Tx/Tz axes and table signs before calculation.")
    if _GE_WARNING_TOKEN in warnings or "ge" in mfr.lower():
        if meta.get("swap_lat_lon", False):
            parts.append("GE handling is already normalized; manual Tx/Tz swap is active and may double-correct.")
        else:
            parts.append("GE lateral/longitudinal handling is already applied during normalization.")
    elif "philips" in mfr.lower():
        parts.append("Philips large table offsets make missed or double normalization visibly wrong.")
    elif meta.get("swap_lat_lon", False):
        parts.append("Manual Tx/Tz swap is active; verify the source/export convention to avoid missed or double swaps.")
    if any(meta.get(k, False) for k in ("flip_tx", "flip_ty", "flip_tz")):
        parts.append("Axis-direction flip reverses table motion about detected origin; fix mirrored origins manually.")
    return " ".join(parts)


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


def event_context_caption(
    state: AppState,
    *,
    current_index: int,
    active_exam_index: int | None = None,
    composite: bool = False,
) -> str:
    """User-facing 1-based caption for the Geometry event stepper row.

    ``current_index`` is the 0-based internal value; the returned label adds 1
    so "Event 1 / N" means the first of N events. Checks ``composite`` to choose
    between the "Exam #N" and "all exams" suffixes when ``state.is_multi_exam``
    is true.

    Examples (current_index shown in parens, output in quotes):
      single-exam, 23 events, current_index 5   -> "Event 6 / 23"
      multi-exam exam #2 (idx 1), 7 events, current_index 3 -> "Event 4 / 7 · Exam #2"
      multi-exam composite, 51 events, current_index 9     -> "Event 10 / 51 · all exams"
      empty slice, current_index 0              -> "Event 0 / 0"
    """
    count = preview_event_count(
        state, active_exam_index=active_exam_index, composite=composite
    )
    if count <= 0:
        return "Event 0 / 0"
    safe_idx = clamp_geometry_event_index(
        state, current_index,
        active_exam_index=active_exam_index, composite=composite,
    )
    display_idx = safe_idx + 1
    if state.is_multi_exam:
        if composite:
            return f"Event {display_idx} / {count} · all exams"
        exam_num = (active_exam_index if active_exam_index is not None
                    else state.active_exam_index or 0) + 1
        return f"Event {display_idx} / {count} · Exam #{exam_num}"
    return f"Event {display_idx} / {count}"


# ────────────────────────────────────────────────────────────────────
# Performance guard: this is the "Plotly trace count" mitigation
# referenced in dev-docs/TO_DO.md ("account for Plotly trace count and
# large datasets").
#
# Scope: ALL plot_procedure live previews — single-exam, multi-exam
# non-composite, and multi-exam composite. In every one of these paths
# make_geometry_fig -> plot_procedure builds one trace set per event
# (plot_procedure.py:65-84), so the figure grows linearly with the
# active slice's event count.
#
# We pause live preview above 30 events so patient/table offset-slider
# adjustments while in Full-procedure mode do not trigger expensive
# reactive re-renders, and show the large-data spinner above 100
# (geometry.py:498 for composite count, geometry.py:500 for single-exam).
#
# plot_event mode does NOT need this guard — exactly one event per render,
# so the trace set is small and fixed regardless of slice size.
# plot_setup mode renders no events.
#
# If you add a new preview path that grows traces per event, extend
# `procedure_live_preview_paused` rather than adding a sibling guard.
# ────────────────────────────────────────────────────────────────────
def procedure_live_preview_paused(
    state: AppState,
    *,
    last_preview_mode: str | None,
    composite_preview: bool,
    last_table_origin_scrub: bool,
    pause_threshold: int = 30,
) -> bool:
    """True when plot_procedure live preview should show the PAUSED badge.

    Pause policy applies to ALL plot_procedure paths, not only composite:
    plot_procedure.py builds one trace set per event regardless of composite
    flag, so the figure grows linearly with total event count in every path.
    """
    if last_preview_mode != "plot_procedure":
        return False
    if state.is_multi_exam:
        composite = resolve_composite_for_render(
            composite_preview=composite_preview,
            last_table_origin_scrub=last_table_origin_scrub,
        )
        active_idx = state.active_exam_index
        count = preview_event_count(
            state, active_exam_index=active_idx, composite=composite
        )
    else:
        # Single-exam branch: call preview_event_count(state), which lives in
        # this same module (geometry_preview.py:98) and returns len(state.rdsr_df)
        # for single-exam slices without introducing import cycles.
        count = preview_event_count(state)
    return count > pause_threshold


def event_select_options(slice_count: int) -> dict[int, str]:
    """Return dropdown options mapping 1-indexed event numbers to string labels."""
    if slice_count <= 0:
        return {1: "1"}
    return {i: str(i) for i in range(1, slice_count + 1)}


def exam_selector_options(state: AppState) -> dict[int, str]:
    """Return dropdown options mapping exam index to display label."""
    if not state.loaded_exam_meta:
        return {0: "#1 · Exam 1"}
    return {
        i: f"#{i + 1} · {meta.get('file_name', '—')}"
        for i, meta in enumerate(state.loaded_exam_meta)
    }


