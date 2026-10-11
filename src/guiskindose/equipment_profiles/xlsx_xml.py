"""Streaming OOXML worksheet XML preflight for the XLSX equipment-profile adapter.

This module is the only place that parses worksheet XML. It exists because openpyxl's read-only parser is
**dimension-driven**: it sizes its output from the workbook's declared ``<dimension>`` and will silently
truncate a sheet that understates its content. A truncated read would drop whole profiles without any error,
so the declared dimension is never trusted for sizing.

Instead, each worksheet part is parsed here with a bounded, streaming expat parser that:

- never builds a tree, so a huge sheet cannot be materialized into memory;
- **ignores the declared ``<dimension>``** and bounds the work on the coordinates that are actually present;
- validates every row and cell reference, rejecting out-of-range, repeated, and malformed coordinates;
- rejects DTDs, entity declarations, and external entity references outright;
- fails closed on any parse failure with a value-free :class:`EquipmentProfileError`.

Because the bounds are known before openpyxl runs, the adapter can call ``reset_dimensions()`` on the reader and
iterate the real cells without ever allocating padding from a forged dimension.
"""

from __future__ import annotations

import io
import re
import zipfile
import zlib
from typing import Any
from xml.parsers import expat

from guiskindose.equipment_profiles import constants as _constants
from guiskindose.equipment_profiles.constants import (
    SOURCE_KIND_XLSX,
    WORKSHEET_ENTRY_PREFIX,
    WORKSHEET_ENTRY_SUFFIX,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode

#: Largest row number and column count any OOXML worksheet may name. These are format limits, not budgets:
#: a reference beyond them is malformed, and the budgets above are what actually bound the work.
_MAX_OOCXML_ROWS = 1_048_576
_MAX_OOCXML_COLUMNS = 16_384

_ROW_ELEMENT = "row"
_CELL_ELEMENT = "c"
_DIMENSION_ELEMENT = "dimension"


def worksheet_budgets() -> tuple[int, int, int]:
    """Read the live ``(rows, columns, cells)`` budgets from the constants module.

    Read at call time rather than bound at import time, so a deployment or a test that lowers a bound sees it
    applied without re-importing this module.
    """
    return (
        _constants.MAX_XLSX_PREFLIGHT_ROWS,
        _constants.MAX_XLSX_PREFLIGHT_COLS,
        _constants.MAX_XLSX_PREFLIGHT_CELLS,
    )

_COLUMN_REF_RE = re.compile(r"\A[A-Z]+\Z")
_CELL_REF_RE = re.compile(r"\A([A-Z]+)([0-9]+)\Z")


def column_index(column_ref: str) -> int | None:
    """Convert an OOXML column reference (``A``, ``AA``, ``XFD``) to a one-based index.

    Returns ``None`` when the reference is not a well-formed column name, so callers never see a partial parse.
    """
    if len(column_ref) > 3 or not _COLUMN_REF_RE.match(column_ref):
        return None
    index = 0
    for character in column_ref:
        index = index * 26 + (ord(character) - ord("A") + 1)
    return index


def cell_reference(reference: str) -> tuple[int, int] | None:
    """Split a cell reference (``A1``, ``XFD1048576``) into one-based ``(row, column)``."""
    if len(reference) > 10:
        return None
    match = _CELL_REF_RE.match(reference)
    if match is None:
        return None
    column = column_index(match.group(1))
    if column is None:
        return None
    row = int(match.group(2))
    if row < 1:
        return None
    return row, column


def _reject_doctype(name: str, sysid: str | None, pubid: str | None, has_internal_subset: bool) -> int:
    """Refuse any DTD, so no entity or notation-based expansion is possible."""
    raise EquipmentProfileError(ProfileErrorCode.MALFORMED_CONTAINER, source_kind=SOURCE_KIND_XLSX)


def _reject_entity(context, base, sysid, pubid) -> bool:
    """Refuse every external entity reference."""
    return False


class _WorksheetGuard:
    """Validate namespace-aware worksheet structure and strictly increasing coordinates."""

    def __init__(self, source_kind: str) -> None:
        self._source_kind = source_kind
        self._row_limit, self._column_limit, self._cell_limit = worksheet_budgets()
        self._rows = self._columns = self._cells = 0
        self._current_row = self._current_column = 0
        self._path: list[str] = []
        self._has_sheet_data = False

    def _fail(self, count: int = 0) -> EquipmentProfileError:
        return EquipmentProfileError(
            ProfileErrorCode.MALFORMED_CONTAINER, source_kind=self._source_kind, count=count
        )

    def start_element(self, name: str, attrs: dict[str, str]) -> None:
        local = name.removeprefix("http://schemas.openxmlformats.org/spreadsheetml/2006/main}")
        self._path.append(local)
        if len(self._path) > 32:
            raise self._fail()
        if len(self._path) == 1 and local != "worksheet":
            raise self._fail()
        if local == "sheetData":
            if self._path != ["worksheet", "sheetData"] or self._has_sheet_data:
                raise self._fail()
            self._has_sheet_data = True
        elif local == _ROW_ELEMENT:
            if self._path != ["worksheet", "sheetData", "row"]:
                raise self._fail()
            self._open_row(attrs)
        elif local == _CELL_ELEMENT:
            if self._path != ["worksheet", "sheetData", "row", "c"]:
                raise self._fail()
            self._open_cell(attrs)

    def end_element(self, name: str) -> None:
        self._path.pop()

    def _open_row(self, attrs: dict[str, str]) -> None:
        reference = attrs.get("r")
        row = self._current_row + 1 if reference is None else self._row_reference(reference)
        if row <= self._current_row or row > min(self._row_limit, _MAX_OOCXML_ROWS):
            raise self._fail(row)
        self._current_row = row
        self._current_column = 0
        self._rows += 1

    def _row_reference(self, reference: str) -> int:
        if not re.fullmatch(r"[1-9][0-9]{0,6}", reference):
            raise self._fail()
        return int(reference)

    def _open_cell(self, attrs: dict[str, str]) -> None:
        reference = attrs.get("r")
        resolved = (self._current_row, self._current_column + 1) if reference is None else cell_reference(reference)
        if resolved is None:
            raise self._fail()
        row, column = resolved
        if row != self._current_row or not self._current_column < column <= min(self._column_limit, _MAX_OOCXML_COLUMNS):
            raise self._fail()
        self._current_column = column
        self._columns = max(self._columns, column)
        self._cells += 1
        if self._cells > self._cell_limit:
            raise self._fail(self._cells)

    @property
    def bounds(self) -> tuple[int, int, int]:
        if not self._has_sheet_data:
            raise self._fail()
        return self._rows, self._columns, self._cells


def _parser(guard: _WorksheetGuard) -> Any:
    """Build a streaming expat parser bound to ``guard``."""
    parser = expat.ParserCreate(namespace_separator="}")
    parser.buffer_text = False
    parser.StartDoctypeDeclHandler = _reject_doctype
    parser.ExternalEntityRefHandler = _reject_entity
    parser.UnparsedEntityDeclHandler = lambda *_args: None  # never reached: DTDs are refused
    # ``ordered_attributes`` is irrelevant; the handler only needs names and values.
    parser.StartElementHandler = guard.start_element
    parser.EndElementHandler = guard.end_element
    return parser


def validate_worksheet_xml(payload: bytes, *, source_kind: str) -> tuple[int, int, int]:
    """Validate one worksheet part's XML and return its actual ``(rows, columns, cells)``.

    The declared ``<dimension>`` is ignored for sizing: only the coordinates actually present bound the work.
    Any DTD, entity, malformed reference, duplicate coordinate, or parse failure is a closed
    ``malformed_container`` error with no raw cause.
    """
    guard = _WorksheetGuard(source_kind)
    parser = _parser(guard)
    try:
        parser.Parse(payload, True)
    except expat.ExpatError:
        raise EquipmentProfileError(
            ProfileErrorCode.MALFORMED_CONTAINER, source_kind=source_kind
        ) from None
    except EquipmentProfileError:
        raise
    return guard.bounds


def worksheet_entry_names(archive: zipfile.ZipFile) -> tuple[str, ...]:
    """Resolve worksheet parts from content types, including nonstandard part names."""
    names = {
        info.filename for info in archive.infolist()
        if info.filename.startswith(WORKSHEET_ENTRY_PREFIX) and info.filename.endswith(WORKSHEET_ENTRY_SUFFIX)
    }
    parser = expat.ParserCreate(namespace_separator="}")
    parser.StartDoctypeDeclHandler = _reject_doctype
    parser.ExternalEntityRefHandler = _reject_entity

    def collect(name: str, attrs: dict[str, str]) -> None:
        if name != "http://schemas.openxmlformats.org/package/2006/content-types}Override":
            return
        if attrs.get("ContentType") != "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml":
            return
        part = attrs.get("PartName", "").removeprefix("/")
        if not part or any(piece in {"", ".", ".."} for piece in part.split("/")) or "\\" in part:
            raise EquipmentProfileError(ProfileErrorCode.MALFORMED_CONTAINER, source_kind=SOURCE_KIND_XLSX)
        names.add(part)

    parser.StartElementHandler = collect
    with archive.open("[Content_Types].xml") as member:
        while chunk := member.read(_constants.XLSX_STREAM_CHUNK_BYTES):
            parser.Parse(chunk, False)
        parser.Parse(b"", True)
    return tuple(sorted(names))


def validate_worksheet_parts(raw: bytes, *, source_kind: str = SOURCE_KIND_XLSX) -> tuple[tuple[int, int, int], ...]:
    """Validate every worksheet part of an archive, returning one bounds tuple per part.

    Runs after the inflation preflight, so each member read here is already inside the byte budget. A part that
    is unreadable or unparseable fails closed. Part names come from the same hygiene-checked entry list the
    inflation pass used, so no name is trusted twice.
    """
    bounds: list[tuple[int, int, int]] = []
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, EOFError, ValueError, zlib.error):
        raise EquipmentProfileError(
            ProfileErrorCode.MALFORMED_CONTAINER, source_kind=source_kind
        ) from None
    with archive:
        for name in worksheet_entry_names(archive):
            try:
                payload = archive.read(name)
            except (zipfile.BadZipFile, OSError, EOFError, zlib.error, KeyError, RuntimeError, ValueError):
                raise EquipmentProfileError(
                    ProfileErrorCode.MALFORMED_CONTAINER, source_kind=source_kind
                ) from None
            bounds.append(validate_worksheet_xml(payload, source_kind=source_kind))
    return tuple(bounds)
