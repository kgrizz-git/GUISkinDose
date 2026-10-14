"""Value-free formatting for custom equipment-profile match records.

Shared by the GUI review surfaces and rich export tables. Accepts only the
public ``equipment_profile_match`` mapping shape (profile_id, source, notice,
and related provenance fields). Never echoes paths, station, serial, or raw
identity text beyond permitted notice labels.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from guiskindose.equipment_profiles.constants import RESOLUTION_COMPLETE, RESOLUTION_PARTIAL

EQUIPMENT_PROFILE_SECTION_TITLE = "Custom equipment profile match"
EQUIPMENT_PROFILE_HEADER = ["Profile", "Source", "Match", "Notice"]


def _is_mapping(value: Any) -> bool:
    return isinstance(value, dict)


def has_equipment_profile_content(match: dict[str, Any] | None) -> bool:
    """True when *match* carries a displayable profile match record."""
    if not _is_mapping(match):
        return False
    profile_id = match.get("profile_id")
    notice = match.get("notice")
    return isinstance(profile_id, str) and profile_id and _is_mapping(notice) and isinstance(notice.get("text"), str)


def equipment_match_kind_label(match: dict[str, Any]) -> str:
    """Human-readable complete vs partial label from the structured notice."""
    notice = match.get("notice") if _is_mapping(match) else None
    kind = notice.get("kind") if _is_mapping(notice) else None
    if kind == RESOLUTION_COMPLETE:
        return "Complete"
    if kind == RESOLUTION_PARTIAL:
        return "Partial"
    return "Unknown"


def equipment_match_row_cells(match: dict[str, Any]) -> list[str]:
    """One table row for a match mapping (no equipment labels or file paths)."""
    profile_id = str(match.get("profile_id", ""))
    source = str(match.get("source", ""))
    notice = match.get("notice") if _is_mapping(match) else {}
    text = str(notice.get("text", "")) if _is_mapping(notice) else ""
    return [profile_id, source, equipment_match_kind_label(match), text]


def equipment_profile_report_table(
    blocks: Sequence[tuple[str | None, dict[str, Any] | None]],
) -> list[list[str]]:
    """Build a header plus one row per exam x match (optional Exam column)."""
    shown = [(label, match) for label, match in blocks if has_equipment_profile_content(match)]
    if not shown:
        return []
    labelled = any(label is not None for label, _ in shown)
    rows: list[list[str]] = [(["Exam"] if labelled else []) + EQUIPMENT_PROFILE_HEADER]
    for label, match in shown:
        assert match is not None
        rows.append(([label or ""] if labelled else []) + equipment_match_row_cells(match))
    return rows


def format_equipment_profile_blocks(blocks: Sequence[tuple[str | None, dict[str, Any] | None]]) -> str:
    """Multi-line summary for Calculate/Results (empty when nothing to show)."""
    lines: list[str] = []
    for label, match in blocks:
        if not has_equipment_profile_content(match):
            continue
        assert match is not None
        prefix = f"{label}: " if label else ""
        cells = equipment_match_row_cells(match)
        lines.append(f"{prefix}{cells[0]} ({cells[1]}) — {cells[2]} match")
        if cells[3]:
            lines.append(f"{prefix}{cells[3]}")
    return "\n".join(lines)
