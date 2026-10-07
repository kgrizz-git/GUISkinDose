"""Pure formatters for Calculate/Settings patient-offset and table-origin summaries."""

from __future__ import annotations

from collections.abc import Sequence

from .state import AppState

_C6_MULTI_EXAM_PHANTOM = (
    "Patient offsets are managed per-exam in multi-exam mode. Adjust them in the "
    "Geometry tab or the Per-exam corrections section in Settings (including "
    "Apply global to all when seeding new exams)."
)


def format_patient_offsets(app_state: AppState) -> str:
    """One-line patient-offset summary for the Calculate tab."""
    if not app_state.loaded_exams:
        return "—"
    if not app_state.is_multi_exam:
        return (
            f"lon: {app_state.d_lon:.1f}, ver: {app_state.d_ver:.1f}, "
            f"lat: {app_state.d_lat:.1f} cm"
        )
    metas = app_state.loaded_exam_meta
    n = len(metas)
    parts: list[str] = []
    for i in range(min(n, 3)):
        m = metas[i]
        parts.append(
            f"Exam #{i + 1}: lon={float(m.get('d_lon', 0.0)):.1f}, "
            f"ver={float(m.get('d_ver', 0.0)):.1f}, "
            f"lat={float(m.get('d_lat', 0.0)):.1f} cm"
        )
    line = ", ".join(parts)
    if n > 3:
        line += f", and {n - 3} more"
    return line


def format_table_offset_line(app_state: AppState) -> str:
    """One-line table-offset summary for Calculate and Settings tabs."""
    if app_state.is_multi_exam:
        return "Per-exam: see Per-exam corrections below."
    method = app_state.normalization_method
    if method == "Unknown":
        return "—"
    if method == "Tabular":
        return "X: 0.0, Y: 0.0, Z: 0.0 cm (tabular — no auto-detected origin)"
    return (
        f"X: {app_state.table_offset_x:.1f}, Y: {app_state.table_offset_y:.1f}, "
        f"Z: {app_state.table_offset_z:.1f} cm"
    )


def format_scale_cm_label(scale_factor: float, baseline_cm: float) -> str:
    """Format the scale factor and its scaled mesh dimension for one slider."""
    if not baseline_cm:
        return f"{scale_factor:.2f}x  (—)"
    cm = scale_factor * baseline_cm
    return f"{scale_factor:.2f}x  ({cm:.1f} cm)"


def multi_exam_phantom_offset_caption() -> str:
    """Settings Phantom expansion caption when global spinboxes are hidden (C6)."""
    return _C6_MULTI_EXAM_PHANTOM


def format_tube_summary(blocks: Sequence[tuple[str | None, list[dict] | None]]) -> str:
    """Multi-line "dose by tube" text for the Results tab; empty when not worth showing.

    Parameters
    ----------
    blocks : list[tuple[str | None, list[dict] | None]]
        ``(exam label or None, tube summary rows)`` per exam. Exams whose summary is a
        lone single-plane tube are skipped, since they repeat the headline numbers.

    Returns
    -------
    str
        One line per tube plus a closing note that per-tube peaks do not sum to the
        peak skin dose. No equipment labels appear.
    """
    from guiskindose.export.sections import (
        TUBE_NOTE,
        has_tube_content,
        tube_cf_text,
        tube_row_cells,
        tube_source_text,
    )

    lines: list[str] = []
    for label, summary in blocks:
        if not has_tube_content(summary):
            continue
        prefix = f"{label}: " if label else ""
        for row in summary or []:
            tube, _events, reported, corrected, _cf, _source, peak = tube_row_cells(row)
            lines.append(
                f"{prefix}{tube}: reported {reported} mGy, corrected {corrected} mGy, "
                f"CF {tube_cf_text(row)} ({tube_source_text(row)}), peak {peak} mGy"
            )
    if not lines:
        return ""
    return "\n".join(["Dose by tube", *lines, TUBE_NOTE])
