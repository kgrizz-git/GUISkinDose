"""OOXML container and worksheet-budget preflight for the XLSX equipment-profile adapter.

This module exists so the canonical core stays stdlib-only and JSON-only imports never pull in openpyxl: every
function imports the library **inside** the function body, so a caller that only parses JSON, CSV, or TSV never
imports it.

It answers four questions before any worksheet row is materialized, and never answers them by trusting archive
metadata:

1. **Is the container sound?** The archive is opened from the in-memory byte snapshot, its entry list is
   bounded, and duplicate or directory-spoofing names are rejected.
2. **Does actual inflation fit the budget?** Each member is inflated by streaming real decompressed bytes in
   chunks and counting them, so a forged central-directory ``file_size`` cannot smuggle a zip bomb.
3. **Do the actual worksheet coordinates fit?** The row, column, and cell budgets are enforced against the
   coordinates really present in the worksheet XML (see :mod:`guiskindose.equipment_profiles.xlsx_xml`), never
   against a declared ``<dimension>``.
4. **Which sheet is selected?** The index is resolved against the **workbook's own worksheet catalog**, not
   against part filenames, so nonstandard part naming cannot desynchronize it.

Nothing is ever extracted to the filesystem, no link target is resolved, no formula is evaluated, and no sheet
name is retained. All failures raise :class:`EquipmentProfileError` with a stable code and the caller's source
kind; no sheet name, path, cell text, or library message is included in any error.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from guiskindose.equipment_profiles import constants as _constants
from guiskindose.equipment_profiles.constants import (
    SOURCE_KIND_XLSX,
    WORKSHEET_ENTRY_PREFIX,
    WORKSHEET_ENTRY_SUFFIX,
    XLSX_STREAM_CHUNK_BYTES,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode

#: Ceiling on the number of archive entries accepted at all, independent of the sheet budget.
_ZIP_ENTRY_LIMIT = 16 + 64


def sheet_limit() -> int:
    """Read the live worksheet-count ceiling from the constants module."""
    return _constants.MAX_XLSX_SHEETS


def inflation_budgets() -> tuple[int, int]:
    """Read the live ``(member, total)`` inflation budgets from the constants module."""
    return (
        _constants.MAX_XLSX_MEMBER_BYTES,
        _constants.MAX_XLSX_TOTAL_INFLATED_BYTES,
    )


class _Inflater:
    """Streams and counts actual decompressed member bytes against the budgets."""

    __slots__ = ("_archive", "_member_limit", "_total", "_total_limit")

    def __init__(self, archive: zipfile.ZipFile) -> None:
        self._archive = archive
        self._member_limit, self._total_limit = inflation_budgets()
        self._total = 0

    def count(self, info: zipfile.ZipInfo) -> int:
        """Inflate one member in chunks and return its actual byte count.

        The declared central-directory size is used only as an early cheap reject; the authoritative count
        comes from the bytes actually read.
        """
        declared = max(info.file_size, 0)
        if declared > self._member_limit:
            raise EquipmentProfileError(
                ProfileErrorCode.INFLATION_LIMIT_EXCEEDED, source_kind=SOURCE_KIND_XLSX
            )
        if self._total + declared > self._total_limit:
            raise EquipmentProfileError(
                ProfileErrorCode.INFLATION_LIMIT_EXCEEDED, source_kind=SOURCE_KIND_XLSX
            )
        member_bytes = 0
        try:
            with self._archive.open(info, "r") as member:
                while True:
                    chunk = member.read(XLSX_STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    member_bytes += len(chunk)
                    if member_bytes > self._member_limit:
                        raise EquipmentProfileError(
                            ProfileErrorCode.INFLATION_LIMIT_EXCEEDED, source_kind=SOURCE_KIND_XLSX
                        )
                    if self._total + member_bytes > self._total_limit:
                        raise EquipmentProfileError(
                            ProfileErrorCode.INFLATION_LIMIT_EXCEEDED, source_kind=SOURCE_KIND_XLSX
                        )
        except EquipmentProfileError:
            raise
        except (zipfile.BadZipFile, OSError, EOFError, RuntimeError, ValueError):
            raise EquipmentProfileError(
                ProfileErrorCode.MALFORMED_CONTAINER, source_kind=SOURCE_KIND_XLSX
            ) from None
        self._total += member_bytes
        return member_bytes


def _check_entries(entries: Sequence[zipfile.ZipInfo]) -> None:
    """Reject duplicate entry names, directory-spoofing entries, and over-broad archives."""
    if len(entries) > _ZIP_ENTRY_LIMIT:
        raise EquipmentProfileError(
            ProfileErrorCode.MALFORMED_CONTAINER, source_kind=SOURCE_KIND_XLSX, count=len(entries)
        )
    seen: set[str] = set()
    for info in entries:
        name = info.filename
        if not name or name in seen or _is_directory_spoof(name):
            raise EquipmentProfileError(
                ProfileErrorCode.MALFORMED_CONTAINER, source_kind=SOURCE_KIND_XLSX
            )
        seen.add(name)


def _is_directory_spoof(name: str) -> bool:
    """True for a name that ends in a separator without being flagged as a directory entry."""
    return name.endswith("/") or name.endswith("\\")


def _is_worksheet_part(name: str) -> bool:
    return name.startswith(WORKSHEET_ENTRY_PREFIX) and name.endswith(WORKSHEET_ENTRY_SUFFIX)


def worksheet_part_count(entries: Sequence[zipfile.ZipInfo]) -> int:
    """Count worksheet parts in an already-hygiene-checked entry list.

    This is an early container bound only. The authoritative sheet count used for selection comes from the
    workbook's own worksheet catalog, so a nonstandard part name cannot desynchronize it.
    """
    return sum(1 for info in entries if _is_worksheet_part(info.filename))


def preflight_container(raw: bytes, *, source_kind: str = SOURCE_KIND_XLSX) -> int:
    """Validate the archive's structure and actual inflation, returning the worksheet-part count.

    Raises ``unreadable_source`` for non-ZIP bytes, ``inflation_limit_exceeded`` when actual inflation
    exceeds a budget, and ``malformed_container`` for any other structural problem. Causes are always
    suppressed so no library message leaks. The compressed byte ceiling is the file adapter's concern; this
    function only checks what the archive inflates to.
    """
    if not raw:
        raise EquipmentProfileError(ProfileErrorCode.EMPTY_SOURCE, source_kind=source_kind)
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, EOFError, ValueError):
        raise EquipmentProfileError(
            ProfileErrorCode.MALFORMED_CONTAINER, source_kind=source_kind
        ) from None
    with archive:
        _check_entries(archive.infolist())
        inflater = _Inflater(archive)
        for info in archive.infolist():
            if info.is_dir():
                continue
            inflater.count(info)
        return worksheet_part_count(archive.infolist())


def resolve_sheet(worksheet_count: int, selected: int | None, *, source_kind: str = SOURCE_KIND_XLSX) -> int:
    """Resolve the zero-based sheet index to read against the workbook's own worksheet count.

    A single-sheet workbook defaults to sheet ``0``. With two or more worksheets a selection is mandatory, so
    an absent selection is ``sheet_required``. An out-of-range, negative, or non-integer selection is
    ``unknown_sheet``. Sheet **names are never used here and are never retained**, so no name can reach a
    diagnostic.
    """
    if worksheet_count <= 0:
        raise EquipmentProfileError(ProfileErrorCode.EMPTY_SOURCE, source_kind=source_kind)
    limit = sheet_limit()
    if worksheet_count > limit:
        raise EquipmentProfileError(
            ProfileErrorCode.SHEET_LIMIT_EXCEEDED, source_kind=source_kind, count=worksheet_count
        )
    if selected is None:
        if worksheet_count > 1:
            raise EquipmentProfileError(ProfileErrorCode.SHEET_REQUIRED, source_kind=source_kind)
        return 0
    if not isinstance(selected, int) or isinstance(selected, bool):
        raise EquipmentProfileError(ProfileErrorCode.UNKNOWN_SHEET, source_kind=source_kind)
    if selected < 0 or selected >= worksheet_count:
        raise EquipmentProfileError(ProfileErrorCode.UNKNOWN_SHEET, source_kind=source_kind)
    return selected


@dataclass(frozen=True, slots=True)
class SheetShape:
    """Actual dimensions counted from XML coordinates, never from declared metadata."""

    rows: int
    columns: int
    cells: int


def _iter_rows(worksheet: Any) -> Any:
    return worksheet.iter_rows()


def count_worksheet(worksheet: Any, *, source_kind: str = SOURCE_KIND_XLSX) -> SheetShape:
    """Count the actual rows, columns, and cells of one worksheet, enforcing the budgets.

    Iterating ``iter_rows`` yields rows as the reader materializes them, so the count reflects what a
    downstream read actually touches rather than what a declared ``<dimension>`` claims.
    """
    rows = 0
    columns = 0
    cells = 0
    for row in _iter_rows(worksheet):
        rows += 1
        if rows > _row_limit():
            raise EquipmentProfileError(
                ProfileErrorCode.ROW_LIMIT_EXCEEDED, source_kind=source_kind, count=rows
            )
        width = len(row)
        if width > _column_limit():
            raise EquipmentProfileError(
                ProfileErrorCode.ROW_LIMIT_EXCEEDED, source_kind=source_kind, count=width
            )
        columns = max(columns, width)
        cells += width
        if cells > _cell_limit():
            raise EquipmentProfileError(
                ProfileErrorCode.ROW_LIMIT_EXCEEDED, source_kind=source_kind, count=cells
            )
    return SheetShape(rows=rows, columns=columns, cells=cells)


def _row_limit() -> int:
    return _limits()[0]


def _column_limit() -> int:
    return _limits()[1]


def _cell_limit() -> int:
    return _limits()[2]


def _limits() -> tuple[int, int, int]:
    """Read the live budget constants, so tests can monkeypatch them on this module."""

    return (
        _constants.MAX_XLSX_PREFLIGHT_ROWS,
        _constants.MAX_XLSX_PREFLIGHT_COLS,
        _constants.MAX_XLSX_PREFLIGHT_CELLS,
    )
