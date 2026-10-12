"""CLI file inputs for custom equipment profiles (experimental).

Reads repeatable ``--equipment-profile`` paths (JSON/CSV/TSV/XLSX, relative
paths resolve against the working directory), the optional global
``--equipment-profile-sheet`` selector, an explicit ``--equipment-profile-store``
database, and repeatable ``--equipment-profile-id`` selectors; assembles one
frozen candidate session through the canonical file/snapshot path and binds it
to run settings before any exam read. With a store and no IDs, every enabled
current record is used; explicit IDs select their current revisions regardless
of the enable flag (one-run selection, never persisted). Sheet names and
indexes flow through untouched to the guarded adapter, which resolves them
against the opened workbook's own catalog on the same bounded bytes used for
hashing and parsing — this module never lists workbooks itself. The store
opens read-only and is never created, migrated, or written. All
source/conflict/capability failures surface before exam reads; a failed
candidate never mutates settings, and an already-bound runtime session is
never replaced silently.

:class:`EquipmentProfileError` is not a :class:`UserFacingInputError`:
failures convert at this boundary to fixed, value-free
``UserFacingInputError`` messages (stable code, source kind, row/count
only — never paths, cells, IDs, notes, or causes). No wildcard promotion
activation, no transmission activation, no store writes/commands, and no
GUI wiring in this module; headless settings-JSON composition is owned by
``cli_settings``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from guiskindose.equipment_profiles import (
    EquipmentProfileSession,
)
from guiskindose.equipment_profiles.constants import MAX_SOURCES, MAX_XLSX_SHEETS
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.equipment_profiles.store_schema import normalize_selection
from guiskindose.privacy import UserFacingInputError
from guiskindose.settings import PyskindoseSettings
from guiskindose.settings_equipment_profiles import _assemble_composed, _parse_request, _ValidatedRequest

logger = logging.getLogger(__name__)

GUI_EQUIPMENT_PROFILES_MESSAGE = (
    "Equipment profile inputs (--equipment-profile, --equipment-profile-sheet, "
    "--equipment-profile-store, --equipment-profile-id) apply only to headless runs, "
    "not --mode gui."
)

_XLSX_SUFFIX = ".xlsx"
_INVALID_PATH_MESSAGE = "Equipment profile paths must be explicit paths."
_INVALID_SHEET_MESSAGE = "Equipment profile sheet selection is not valid."

__all__ = [
    "GUI_EQUIPMENT_PROFILES_MESSAGE",
    "bind_equipment_session",
    "equipment_profile_args_present",
    "equipment_session_from_args",
]


def equipment_profile_args_present(args: Any) -> bool:
    """True when any profile flag is set (for the GUI-mode guard)."""
    return (
        getattr(args, "equipment_profile", None) is not None
        or getattr(args, "equipment_profile_sheet", None) is not None
        or getattr(args, "equipment_profile_store", None) is not None
        or getattr(args, "equipment_profile_id", None) is not None
    )


def _coerce_cli_path(entry: Any) -> str:
    """Strict path text behind the existing os.fspath boundary.

    Plain ``str`` passes through; ``PathLike`` coerces via ``os.fspath`` with
    hostile hooks and bytes results refused closed, mirroring the session
    request boundary. Anything else fails closed with no path echo.
    """
    if isinstance(entry, str):
        return entry
    if isinstance(entry, os.PathLike):
        try:
            text = os.fspath(entry)
        except Exception:
            raise UserFacingInputError(
                _INVALID_PATH_MESSAGE
            ) from None
        if isinstance(text, str):
            return text
        raise UserFacingInputError(_INVALID_PATH_MESSAGE)
    raise UserFacingInputError(_INVALID_PATH_MESSAGE)


def _parse_sheet_selector(raw: Any) -> int | str | None:
    """Parse the global sheet selector: plain digits select by 0-based index, else a name.

    Only ``None``, exact ``int``, and exact ``str`` are accepted — booleans,
    floats, and arbitrary objects fail closed rather than coercing. Negative
    indexes and indexes beyond the worksheet-count ceiling fail here before
    any profile I/O. Int-like detection is plain decimal digits only, so a
    numeric-looking title is never hijacked by an accidental ``int()`` parse.
    """
    if raw is None:
        return None
    if type(raw) is int:
        return _checked_sheet_index(raw)
    if type(raw) is not str:
        raise UserFacingInputError(_INVALID_SHEET_MESSAGE)
    stripped = raw.strip()
    if not stripped:
        raise UserFacingInputError("Equipment profile sheet selection is empty.")
    if stripped.isascii() and stripped.isdigit():
        # Strip zeros before converting so arbitrarily long numeric arguments
        # cannot reach Python's integer-string limit or allocate a huge integer.
        digits = stripped.lstrip("0") or "0"
        if len(digits) > len(str(MAX_XLSX_SHEETS - 1)):
            raise UserFacingInputError(_INVALID_SHEET_MESSAGE)
        return _checked_sheet_index(int(digits))
    if len(stripped) > 1 and stripped[0] == "-" and stripped[1:].isascii() and stripped[1:].isdigit():
        raise UserFacingInputError(_INVALID_SHEET_MESSAGE)
    return raw


def _checked_sheet_index(index: int) -> int:
    """Reject selectors that cannot fit the canonical worksheet ceiling."""
    if not 0 <= index < MAX_XLSX_SHEETS:
        raise UserFacingInputError(_INVALID_SHEET_MESSAGE)
    return index


def _normalize_id_selection(ids_raw: Any, store_raw: Any) -> tuple[str, ...] | None:
    """Validate the stored-ID selector: refused without a store, else canonical tuple.

    Exact builtin list/tuple only; duplicates, over-long lists, and
    off-pattern IDs fail closed with nothing echoed. Returns None when no
    IDs were requested (enabled current records apply).
    """
    if ids_raw is None:
        return None
    if store_raw is None:
        raise UserFacingInputError("Equipment profile IDs need a profile store.")
    if type(ids_raw) not in (list, tuple):
        raise UserFacingInputError("Equipment profile IDs must be a list of profile IDs.")
    if len(ids_raw) <= MAX_SOURCES and any(type(name) is not str for name in ids_raw):
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_PROFILE_ID, source_kind="memory", field_path=("store",)
        )
    return normalize_selection(ids_raw)


def _cli_paths(raw: Any) -> list[str]:
    """Validate and bound CLI path entries before copying or source I/O."""
    paths: list[str] = []
    if raw is None:
        raw = []
    if type(raw) not in (list, tuple):
        raise UserFacingInputError(
            "Equipment profile paths must be a list of explicit paths."
        )
    if len(raw) > MAX_SOURCES:
        raise EquipmentProfileError(
            ProfileErrorCode.PROFILE_LIMIT_EXCEEDED,
            source_kind="memory",
            field_path=("files",),
            count=len(raw),
        )
    for entry in raw:
        if len(paths) >= MAX_SOURCES:
            raise EquipmentProfileError(
                ProfileErrorCode.PROFILE_LIMIT_EXCEEDED,
                source_kind="memory",
                field_path=("files",),
                count=len(paths) + 1,
            )
        paths.append(_coerce_cli_path(entry))
    return paths


def _cli_request_from_args(args: Any) -> _ValidatedRequest | None:
    """Parse CLI profile flags into a validated request (pure; no I/O).

    Returns None when no flag is set. Path entries keep their CLI
    UserFacing shape messages; suffix, sheet, and format validation reuses
    the canonical config seam so both sides fail identically before any
    source I/O (CLI str indices/names keep their normalization semantics,
    CLI paths stay working-directory relative). Store opens and assembly
    happen later through the shared composed path.
    """
    raw = getattr(args, "equipment_profile", None)
    sheet_raw = getattr(args, "equipment_profile_sheet", None)
    store_raw = getattr(args, "equipment_profile_store", None)
    ids_raw = getattr(args, "equipment_profile_id", None)
    if raw is None and sheet_raw is None and store_raw is None and ids_raw is None:
        return None
    paths = _cli_paths(raw)
    selection = _normalize_id_selection(ids_raw, store_raw)
    selector = _parse_sheet_selector(sheet_raw)
    if selector is not None and not any(
        Path(text).suffix.lower() == _XLSX_SUFFIX for text in paths
    ):
        raise UserFacingInputError(
            "Equipment profile sheet selection needs an XLSX profile file."
        )
    store_text = _coerce_cli_path(store_raw) if store_raw is not None else None
    files = []
    for text in paths:
        mapping: dict[str, Any] = {"path": text}
        if selector is not None and Path(text).suffix.lower() == _XLSX_SUFFIX:
            mapping["sheet"] = selector
        files.append(mapping)
    config: dict[str, Any] = {"files": files}
    if store_text is not None:
        store_request: dict[str, Any] = {"path": store_text}
        if selection is not None:
            store_request["ids"] = selection
        config["store"] = store_request
    return _parse_request(config, None)


def equipment_session_from_args(args: Any) -> EquipmentProfileSession | None:
    """Assemble one candidate session from CLI profile flags, or None when absent.

    The file list must be an exact builtin list or tuple (declared length
    checked before any copy, traversal, or I/O, then rechecked while bounded
    copying); generators, bare strings, and mappings fail closed. The ID list
    follows the same exact-shape rule with canonical duplicate/pattern
    validation, and the mixed file-plus-snapshot request total stays within
    ``MAX_SOURCES`` before any profile or store I/O. An explicit store opens
    read-only (never created) and snapshots either every enabled current
    record or the requested IDs at their current revisions. Returns None when
    no flag is set. Raises fixed, value-free :class:`UserFacingInputError` on
    any request/source/conflict/capability failure. Never mutates caller
    state; the caller binds the result last.
    """
    try:
        return _assemble_composed(_cli_request_from_args(args), None)
    except EquipmentProfileError as exc:
        raise UserFacingInputError(str(exc)) from None


def bind_equipment_session(settings: PyskindoseSettings, session: EquipmentProfileSession | None) -> None:
    """Attach an assembled session; refuse to silently replace a bound one."""
    if session is None:
        return
    if getattr(settings, "equipment_profile_session", None) is not None:
        raise UserFacingInputError("Equipment profile session is already configured.")
    settings.equipment_profile_session = session
