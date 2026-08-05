"""Per-exam coordinate transforms and multi-exam rdsr_df preview rebuild."""

from __future__ import annotations

from pathlib import Path

from .state import AppState
from .table_origins import detected_table_origin, effective_table_origin

# Display-only column added to the concatenated multi-exam preview frame
# (state.rdsr_df) so the Data Table can show which exam each row came from. It is
# never sent to the dose calculation: the single-exam calc path drops it before
# analyze_data, and the multi-exam path reads per-exam normalized_data directly.
EXAM_COLUMN = "Exam"
# Internal 0-based exam index for preview slicing (not shown in Data Table exports).
EXAM_INDEX_COLUMN = "__exam_index__"

_GE_MANUFACTURER_WARNING = "ge manufacturer detected"


def clear_multi_exam_state(state: AppState) -> None:
    """Clear all exam state from AppState (called by clear_all_exams in app.py)."""
    state.loaded_exams = []
    state.loaded_exam_meta = []
    state.is_multi_exam = False
    state.multi_exam_result = None
    state.active_exam_index = None


def _exam_is_ge(exam) -> bool:
    """True if a tabular exam's import warnings flag GE equipment."""
    warnings_lower = " ".join(getattr(exam, "warnings", []) or []).lower()
    return _GE_MANUFACTURER_WARNING in warnings_lower


def _apply_axis_direction_flips(df, detected: dict, *, flip_tx, flip_ty, flip_tz) -> None:
    """In-place reverse table-position axis directions about the detected origin."""
    for flip, col, key in (
        (flip_tx, "Tx", "x"),
        (flip_ty, "Ty", "y"),
        (flip_tz, "Tz", "z"),
    ):
        if flip and col in df.columns:
            pivot = float(detected.get(key, 0.0))
            df[col] = 2.0 * pivot - df[col]


def _apply_table_origin_override(df, detected: dict, override: dict) -> None:
    """In-place re-base table position columns by ``(override − detected)``."""
    for col, key in (("Tx", "x"), ("Ty", "y"), ("Tz", "z")):
        if col not in df.columns:
            continue
        delta = float(override.get(key, 0.0)) - float(detected.get(key, 0.0))
        if delta:
            df[col] = df[col] + delta


def _apply_lat_lon_swap(df) -> None:
    """In-place swap Tx/Tz when both columns are present."""
    if "Tx" in df.columns and "Tz" in df.columns:
        df["Tx"], df["Tz"] = df["Tz"].copy(), df["Tx"].copy()


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
        _apply_axis_direction_flips(
            df, detected, flip_tx=flip_tx, flip_ty=flip_ty, flip_tz=flip_tz
        )
    if table_origin_override is not None:
        _apply_table_origin_override(df, detected, table_origin_override)
    if swap_lat_lon and schema_name != "normalized":
        _apply_lat_lon_swap(df)
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
    source_note = (
        "Manual table-origin override applied in GUI transform source frame: "
        f"({override.get('x', 0.0)}, {override.get('y', 0.0)}, "
        f"{override.get('z', 0.0)}) cm "
        f"(auto-detected was ({detected.get('x', 0.0)}, "
        f"{detected.get('y', 0.0)}, {detected.get('z', 0.0)}) cm)."
    )
    if not meta.get("swap_lat_lon", False):
        return [source_note]
    final = effective_table_origin(meta)
    final_detected = detected_table_origin(meta)
    return [
        source_note
        + " Final plotted-frame origin after manual Tx/Tz swap: "
        f"({final['x']}, {final['y']}, {final['z']}) cm "
        f"(auto-detected ({final_detected['x']}, {final_detected['y']}, "
        f"{final_detected['z']}) cm)."
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
            df.insert(0, EXAM_INDEX_COLUMN, i)
            df.insert(1, EXAM_COLUMN, f"#{i + 1} · {meta.get('file_name', '—')}")
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


def commit_table_origin_transform(app_state: AppState, exam_index: int) -> None:
    """Re-derive normalized event data after a debounced table-origin update."""
    apply_exam_transforms(app_state, exam_index)


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
