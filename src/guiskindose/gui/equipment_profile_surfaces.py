"""Collect equipment-profile match blocks from GUI session state."""

from __future__ import annotations

from typing import Any

from guiskindose.equipment_capture import capture_to_mapping
from guiskindose.equipment_profile_display import has_equipment_profile_content

from .state import AppState


def _match_from_capture(capture: Any) -> dict[str, Any] | None:
    """Return the embedded match mapping from a capture, or None when absent."""
    try:
        body = capture_to_mapping(capture)
    except Exception:
        return None
    match = body.get("match")
    return match if has_equipment_profile_content(match) else None


def pre_calc_equipment_profile_blocks(app_state: AppState) -> list[tuple[str | None, dict[str, Any] | None]]:
    """Per-exam match mappings from staged captures (before or without a full calc)."""
    if not app_state.loaded_exams:
        return []
    multi = app_state.is_multi_exam
    blocks: list[tuple[str | None, dict[str, Any] | None]] = []
    for index, exam in enumerate(app_state.loaded_exams):
        capture = getattr(exam, "equipment_capture", None)
        if capture is None:
            continue
        match = _match_from_capture(capture)
        if match is None:
            continue
        label = f"Exam {index + 1}" if multi else None
        blocks.append((label, match))
    return blocks


def post_calc_equipment_profile_blocks(app_state: AppState) -> list[tuple[str | None, dict[str, Any] | None]]:
    """Per-exam match mappings from the last calculation output."""
    if app_state.is_multi_exam and app_state.multi_exam_result is not None:
        blocks: list[tuple[str | None, dict[str, Any] | None]] = []
        for exam in app_state.multi_exam_result.exams:
            match = getattr(exam, "equipment_profile_match", None)
            if has_equipment_profile_content(match):
                blocks.append((exam.exam_id, match))
        return blocks

    output = app_state.output
    if isinstance(output, dict):
        match = output.get("equipment_profile_match")
        if has_equipment_profile_content(match):
            return [(None, match)]
    return []
