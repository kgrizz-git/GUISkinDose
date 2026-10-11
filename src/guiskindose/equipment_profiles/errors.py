"""Closed, privacy-safe error type for equipment-profile parsing and validation.

An :class:`EquipmentProfileError` never carries a raw user value. It carries a stable code from
:class:`ProfileErrorCode`, a source-kind token, a field path built **only** from allowlisted names, and
optional integer counts. Unknown user keys are never echoed back; a field path names the closest allowlisted
parent instead. Raw exception causes are suppressed with ``raise ... from None`` so no library text leaks,
and ``repr`` is value-free.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ProfileErrorCode(StrEnum):
    """Stable error codes. The value is the wire token used by reports and diagnostics."""

    UNSUPPORTED_SOURCE_SUFFIX = "unsupported_source_suffix"
    UNSUPPORTED_SOURCE_ENCODING = "unsupported_source_encoding"
    UNREADABLE_SOURCE = "unreadable_source"
    EMPTY_SOURCE = "empty_source"
    OVERSIZED_SOURCE = "oversized_source"
    ROW_LIMIT_EXCEEDED = "row_limit_exceeded"
    PROFILE_LIMIT_EXCEEDED = "profile_limit_exceeded"
    MODEL_LIMIT_EXCEEDED = "model_limit_exceeded"
    ALIAS_LIMIT_EXCEEDED = "alias_limit_exceeded"
    SHEET_LIMIT_EXCEEDED = "sheet_limit_exceeded"
    NESTING_LIMIT_EXCEEDED = "nesting_limit_exceeded"
    MALFORMED_JSON = "malformed_json"
    MALFORMED_TABULAR = "malformed_tabular"
    MALFORMED_CONTAINER = "malformed_container"
    INFLATION_LIMIT_EXCEEDED = "inflation_limit_exceeded"
    UNSAFE_FORMULA = "unsafe_formula"
    SPREADSHEET_ERROR = "spreadsheet_error"
    INVALID_DATE_OBJECT = "invalid_date_object"
    SHEET_REQUIRED = "sheet_required"
    UNKNOWN_SHEET = "unknown_sheet"
    UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
    UNKNOWN_FIELD = "unknown_field"
    DUPLICATE_JSON_KEY = "duplicate_json_key"
    INVALID_TYPE = "invalid_type"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    BLANK_REQUIRED_CELL = "blank_required_cell"
    BLANK_DISALLOWED_CELL = "blank_disallowed_cell"
    EMPTY_DOMAIN = "empty_domain"
    EMPTY_COORDINATE_BLOCK = "empty_coordinate_block"
    INVALID_PROFILE_ID = "invalid_profile_id"
    INVALID_MANUFACTURER = "invalid_manufacturer"
    INVALID_MODEL_LIST = "invalid_model_list"
    ALIAS_AMBIGUOUS_TARGET = "alias_ambiguous_target"
    ALIAS_TARGET_MISMATCH = "alias_target_mismatch"
    WILDCARD_NOT_PERMITTED = "wildcard_not_permitted"
    PROMOTION_NOT_ACKNOWLEDGED = "promotion_not_acknowledged"
    INVALID_NUMBER = "invalid_number"
    INVALID_ENUM = "invalid_enum"
    INVALID_DATE = "invalid_date"
    VALUE_OUT_OF_RANGE = "value_out_of_range"
    DUPLICATE_PROFILE_ID = "duplicate_profile_id"
    DUPLICATE_COORDINATE_CLAIM = "duplicate_coordinate_claim"
    DUPLICATE_TRANSMISSION_KEY = "duplicate_transmission_key"
    CONFLICTING_PROFILE_METADATA = "conflicting_profile_metadata"
    CONFLICTING_PROFILE_CLAIM = "conflicting_profile_claim"
    UNSUPPORTED_PROFILE_CAPABILITY = "unsupported_profile_capability"
    # Reserved for later slices; never raised by the current core.
    STORE_CORRUPTION = "store_corruption"
    EXISTING_MODEL_OUT_OF_EXTENT = "existing_model_out_of_extent"
    EXPLICIT_SQLITE_COLLISION = "explicit_sqlite_collision"


_MESSAGES: dict[ProfileErrorCode, str] = {
    ProfileErrorCode.UNSUPPORTED_SOURCE_SUFFIX: "source file suffix is not accepted",
    ProfileErrorCode.UNSUPPORTED_SOURCE_ENCODING: "source text is not strict UTF-8",
    ProfileErrorCode.UNREADABLE_SOURCE: "source bytes could not be read",
    ProfileErrorCode.EMPTY_SOURCE: "source is empty",
    ProfileErrorCode.OVERSIZED_SOURCE: "source exceeds the byte bound",
    ProfileErrorCode.ROW_LIMIT_EXCEEDED: "aggregate logical rows exceed the bound",
    ProfileErrorCode.PROFILE_LIMIT_EXCEEDED: "profile count exceeds the bound",
    ProfileErrorCode.MODEL_LIMIT_EXCEEDED: "model list exceeds the bound",
    ProfileErrorCode.ALIAS_LIMIT_EXCEEDED: "alias collection exceeds the bound",
    ProfileErrorCode.SHEET_LIMIT_EXCEEDED: "workbook sheet count exceeds the bound",
    ProfileErrorCode.NESTING_LIMIT_EXCEEDED: "document nesting exceeds the depth bound",
    ProfileErrorCode.MALFORMED_JSON: "document is not well-formed JSON",
    ProfileErrorCode.MALFORMED_TABULAR: "tabular document is malformed",
    ProfileErrorCode.MALFORMED_CONTAINER: "spreadsheet container is malformed",
    ProfileErrorCode.INFLATION_LIMIT_EXCEEDED: "spreadsheet inflation exceeds the budget",
    ProfileErrorCode.UNSAFE_FORMULA: "cell holds a formula, not a literal value",
    ProfileErrorCode.SPREADSHEET_ERROR: "cell holds a spreadsheet error value",
    ProfileErrorCode.INVALID_DATE_OBJECT: "date value is not midnight of a single day",
    ProfileErrorCode.SHEET_REQUIRED: "a sheet must be selected for a multi-sheet workbook",
    ProfileErrorCode.UNKNOWN_SHEET: "selected sheet is not present in the workbook",
    ProfileErrorCode.UNSUPPORTED_SCHEMA_VERSION: "schema version is not supported",
    ProfileErrorCode.UNKNOWN_FIELD: "field name is not in the schema",
    ProfileErrorCode.DUPLICATE_JSON_KEY: "object repeats a key",
    ProfileErrorCode.INVALID_TYPE: "value has the wrong type or is null",
    ProfileErrorCode.MISSING_REQUIRED_FIELD: "required field is absent",
    ProfileErrorCode.BLANK_REQUIRED_CELL: "required cell is blank",
    ProfileErrorCode.BLANK_DISALLOWED_CELL: "cell must not be blank",
    ProfileErrorCode.EMPTY_DOMAIN: "profile has no coordinate or transmission content",
    ProfileErrorCode.EMPTY_COORDINATE_BLOCK: "coordinate block supplies no leaf",
    ProfileErrorCode.INVALID_PROFILE_ID: "profile id is not in the accepted form",
    ProfileErrorCode.INVALID_MANUFACTURER: "manufacturer is not in the accepted form",
    ProfileErrorCode.INVALID_MODEL_LIST: "model list is not in the accepted form",
    ProfileErrorCode.ALIAS_AMBIGUOUS_TARGET: "alias cannot be resolved to one target",
    ProfileErrorCode.ALIAS_TARGET_MISMATCH: "alias target is not a listed model",
    ProfileErrorCode.WILDCARD_NOT_PERMITTED: "wildcard use is not permitted here",
    ProfileErrorCode.PROMOTION_NOT_ACKNOWLEDGED: "wildcard promotion requires acknowledgement",
    ProfileErrorCode.INVALID_NUMBER: "number is not finite or is a boolean",
    ProfileErrorCode.INVALID_ENUM: "value is not one of the accepted literals",
    ProfileErrorCode.INVALID_DATE: "date is not a strict calendar date",
    ProfileErrorCode.VALUE_OUT_OF_RANGE: "number is outside the accepted range",
    ProfileErrorCode.DUPLICATE_PROFILE_ID: "profile id is used by more than one profile",
    ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM: "coordinate identity is claimed more than once",
    ProfileErrorCode.DUPLICATE_TRANSMISSION_KEY: "transmission key is used more than once",
    ProfileErrorCode.CONFLICTING_PROFILE_METADATA: "repeated profile metadata disagrees",
    ProfileErrorCode.CONFLICTING_PROFILE_CLAIM: "enabled profiles claim the same slot with different content",
    ProfileErrorCode.UNSUPPORTED_PROFILE_CAPABILITY: "profile capability is not supported by this activation",
    ProfileErrorCode.STORE_CORRUPTION: "user store content is unreadable (reserved)",
    ProfileErrorCode.EXISTING_MODEL_OUT_OF_EXTENT: "row exceeds the original extents (reserved)",
    ProfileErrorCode.EXPLICIT_SQLITE_COLLISION: "row collides with the explicit correction source (reserved)",
}

#: Codes that exist in the vocabulary but are deliberately not implemented yet.
#: ``sheet_limit_exceeded`` was reserved for the XLSX adapter and is now implemented by the preflight.
RESERVED_CODES = (
    ProfileErrorCode.SHEET_REQUIRED,
    ProfileErrorCode.STORE_CORRUPTION,
    ProfileErrorCode.EXISTING_MODEL_OUT_OF_EXTENT,
    ProfileErrorCode.EXPLICIT_SQLITE_COLLISION,
)

class EquipmentProfileError(Exception):
    """A value-free, stable-coded equipment-profile failure.

    Parameters
    ----------
    code:
        Stable code from :class:`ProfileErrorCode`.
    source_kind:
        Source-kind token (``json``, ``memory``, ...).
    field_path:
        Allowlisted field names forming the dotted location, closest allowlisted parent only. Never contains
        an unknown user-supplied key name.
    row_index:
        Optional 0-based row index within the source document.
    count:
        Optional integer count (for example, the number of rows involved).
    capability:
        Optional capability token from a closed vocabulary, for capability-gate failures.
    """

    __slots__ = ("_capability", "_code", "_count", "_field_path", "_row_index", "_source_kind")

    def __init__(
        self,
        code: ProfileErrorCode,
        *,
        source_kind: str,
        field_path: tuple[str, ...] = (),
        row_index: int | None = None,
        count: int | None = None,
        capability: str | None = None,
    ) -> None:
        super().__init__(code.value)
        self._code = code
        self._source_kind = source_kind
        self._field_path = tuple(field_path)
        self._row_index = row_index
        self._count = count
        self._capability = capability

    @property
    def code(self) -> ProfileErrorCode:
        """Stable error code."""
        return self._code

    @property
    def source_kind(self) -> str:
        """Source-kind token that produced the failure."""
        return self._source_kind

    @property
    def field_path(self) -> tuple[str, ...]:
        """Allowlisted dotted field location (never an unknown user key)."""
        return self._field_path

    @property
    def row_index(self) -> int | None:
        """0-based row index when the failure is row-specific."""
        return self._row_index

    @property
    def count(self) -> int | None:
        """Integer count when the failure is a limit or multiplicity breach."""
        return self._count

    @property
    def capability(self) -> str | None:
        """Closed-vocabulary capability token for capability-gate failures."""
        return self._capability

    def _details(self) -> str:
        parts: list[str] = []
        if self._field_path:
            parts.append("field=" + ".".join(self._field_path))
        if self._row_index is not None:
            parts.append(f"row={self._row_index}")
        if self._count is not None:
            parts.append(f"count={self._count}")
        if self._capability is not None:
            parts.append("capability=" + self._capability)
        return (" " + " ".join(parts)) if parts else ""

    def __str__(self) -> str:
        base = _MESSAGES.get(self._code, "equipment profile rejected")
        return f"{self._code.value} ({self._source_kind}): {base}{self._details()}"

    def __repr__(self) -> str:
        return (
            f"EquipmentProfileError(code={self._code.value!r}, source_kind={self._source_kind!r}, "
            f"field_path={self._field_path!r}, row_index={self._row_index!r}, count={self._count!r}, "
            f"capability={self._capability!r})"
        )


def describe_code(code: ProfileErrorCode) -> str:
    """Return the fixed, value-free message for a code."""
    return _MESSAGES[code]


def error_codes() -> tuple[ProfileErrorCode, ...]:
    """Return every code in the vocabulary, including reserved ones."""
    return tuple(ProfileErrorCode)


def is_implemented_code(code: Any) -> bool:
    """True when the code can actually be raised by the current core."""
    return isinstance(code, ProfileErrorCode) and code not in RESERVED_CODES
