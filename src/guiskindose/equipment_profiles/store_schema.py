"""Store schema definition, version handling, and strict validation helpers.

This module owns everything that must stay small, exact, and free of transaction logic so
``profile_store.py`` stays under the size and complexity gates without exemptions:

- the version-1 DDL and its exact verification (tables, columns, keys, constraints, triggers);
- strict row readers that never coerce a corrupt value and never echo one;
- selection and integer-argument validation with closed errors;
- stored-payload parsing that reuses the core JSON bounds before structural validation;
- strict type pre-checks for caller-supplied ``Profile`` objects, so canonical serialization can never
  coerce a wrong-typed hand-built value or leak a raw conversion error.
"""

from __future__ import annotations

import math
import re
import sqlite3
from collections.abc import Sequence
from typing import Any

from guiskindose.equipment_profiles.constants import (
    MAX_PROFILES,
    PROFILE_ID_PATTERN,
    SCHEMA_VERSION,
    SOURCE_KIND_STORE,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.equipment_profiles.json_source import check_document_bounds
from guiskindose.equipment_profiles.models import (
    Coordinates,
    Profile,
    RotationDirection,
    TranslationDirection,
    TranslationOffset,
    TransmissionRow,
)
from guiskindose.equipment_profiles.validation import validate_document

#: Store metadata schema version. Written to ``PRAGMA user_version`` and ``store_meta``.
STORE_SCHEMA_VERSION = 1

#: Maximum stored profile records in one database.
MAX_STORE_RECORDS = 256

#: Maximum revisions retained per profile.
MAX_REVISIONS_PER_PROFILE = 64

#: Maximum records returned by one listing call.
MAX_LIST_LIMIT = 64

#: Maximum distinct identities (live records plus delete tombstones) ever tracked by one database.
#: Tombstones are what make delete/recreate ABA-safe, so they cannot be dropped silently — but without a
#: bound, cycling through fresh IDs would grow them without limit. Creating a brand-new ID past this total
#: fails closed; deleting never does, because it removes one record for every tombstone it adds.
MAX_STORED_IDENTITIES = 1024


def new_store_id() -> str:
    """A random opaque store identifier, recorded once at initialization."""
    import secrets

    return secrets.token_hex(16)


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string. Timestamps are audit data, never hashed."""
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()

_DDL = (
    "CREATE TABLE store_meta(key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)",
    """CREATE TABLE profile_records(
        profile_id TEXT PRIMARY KEY NOT NULL,
        enabled INTEGER NOT NULL CHECK (enabled IN (0, 1)),
        current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
        generation INTEGER NOT NULL CHECK (generation >= 1),
        updated_utc TEXT NOT NULL
    )""",
    """CREATE TABLE profile_revisions(
        profile_id TEXT NOT NULL REFERENCES profile_records(profile_id),
        revision INTEGER NOT NULL CHECK (revision >= 1),
        payload_json TEXT NOT NULL,
        profile_hash TEXT NOT NULL,
        logical_rows INTEGER NOT NULL CHECK (logical_rows >= 1),
        created_utc TEXT NOT NULL,
        PRIMARY KEY (profile_id, revision)
    )""",
    """CREATE TABLE profile_tombstones(
        profile_id TEXT PRIMARY KEY NOT NULL,
        generation INTEGER NOT NULL CHECK (generation >= 1),
        next_revision INTEGER NOT NULL CHECK (next_revision >= 1)
    )""",
)

def _expected_tables() -> set[str]:
    """Table names derived from the DDL itself, so there is exactly one source of truth."""
    return {_ddl_table_name(statement) for statement in _DDL}


def _ddl_table_name(statement: str) -> str:
    """Extract the table name from one of our own DDL statements (never from the database)."""
    return statement.split("(", 1)[0].split()[-1]
_META_VERSION_KEY = "store_schema_version"
_META_STORE_ID_KEY = "store_id"

_PROFILE_ID_RE = re.compile(r"\A" + PROFILE_ID_PATTERN + r"\Z")
_HEX_32_RE = re.compile(r"\A[0-9a-f]{32}\Z")
_HEX_64_RE = re.compile(r"\A[0-9a-f]{64}\Z")

#: SQLite signed 64-bit range. Caller-supplied integers outside it can never bind, so they are rejected
#: before any query runs instead of leaking an ``OverflowError``.
SQLITE_INT_MIN = -(2**63)
_SQLITE_INT_MIN = SQLITE_INT_MIN
SQLITE_INT_MAX = 2**63 - 1
_SQLITE_INT_MAX = SQLITE_INT_MAX


def fail(code: ProfileErrorCode, **fields: Any) -> EquipmentProfileError:
    """Build a value-free store error with ``source_kind="store"``."""
    return EquipmentProfileError(code, source_kind=SOURCE_KIND_STORE, **fields)


def store_error(code: ProfileErrorCode, **fields: Any) -> EquipmentProfileError:
    """Public alias of :func:`fail` for sibling store modules, so error construction lives in one place."""
    return fail(code, **fields)


def normalize_db_error(error_class: type[BaseException]) -> EquipmentProfileError:
    """Map only the exception class of a sqlite3 failure into a stable, value-free store error.

    Mapping: unique/primary-key violations mean a concurrent writer won (``store_conflict``); lock and busy
    states mean the database is momentarily unavailable (``store_unavailable``); everything else means the
    content or the file cannot be trusted (``store_corruption``). No message, path, or row content is kept.
    """
    if issubclass(error_class, sqlite3.IntegrityError):
        return fail(ProfileErrorCode.STORE_CONFLICT)
    if issubclass(error_class, sqlite3.OperationalError):
        return fail(ProfileErrorCode.STORE_UNAVAILABLE)
    return fail(ProfileErrorCode.STORE_CORRUPTION)



def schema_statements() -> tuple[str, ...]:
    """The exact DDL statements that define a fresh version-1 database."""
    return _DDL


def table_names(connection: sqlite3.Connection) -> set[str]:
    """Read the user-table names of an attached database without writing anything.

    Bounded: at most one row past the expected table count is ever fetched, so a corrupt file with
    thousands of tables cannot force unbounded materialization.
    """
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' LIMIT ?",
            (len(_DDL) + 1,)
        ).fetchall()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    return {read_text(row[0]) for row in rows}


def _normalized_ddl(text: str) -> str:
    """Collapse a DDL statement to a canonical single-space form for exact comparison."""
    return " ".join(text.split())


def verify_schema(connection: sqlite3.Connection) -> None:
    """Read-only verification of a version-1 database. Performs no writes.

    Rejects missing or extra tables, any deviation from the exact expected DDL text (columns, types,
    nullability, primary keys, CHECK constraints, and the revision foreign key are all covered by the
    verbatim comparison), any trigger or view, extra metadata keys, and bad metadata values. Anything
    unexpected is ``store_corruption``: the file is left exactly as found.
    """
    try:
        _verify_tables(connection)
        _verify_ddl(connection)
        _verify_no_triggers_or_views(connection)
        _verify_meta(connection)
    except EquipmentProfileError:
        raise
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None


def _verify_tables(connection: sqlite3.Connection) -> None:
    if table_names(connection) != _expected_tables():
        raise fail(ProfileErrorCode.STORE_CORRUPTION)


def _verify_ddl(connection: sqlite3.Connection) -> None:
    for table in sorted(_expected_tables()):
        rows = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchall()
        if len(rows) != 1 or not isinstance(rows[0][0], str):
            raise fail(ProfileErrorCode.STORE_CORRUPTION)
        expected = next(
            statement for statement in _DDL if _ddl_table_name(statement) == table
        )
        if _normalized_ddl(rows[0][0]) != _normalized_ddl(expected):
            raise fail(ProfileErrorCode.STORE_CORRUPTION)


def _verify_no_triggers_or_views(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('trigger', 'view')"
    ).fetchone()
    if row is None or read_count(row[0], minimum=0) != 0:
        raise fail(ProfileErrorCode.STORE_CORRUPTION)


def _verify_meta(connection: sqlite3.Connection) -> None:
    rows = connection.execute("SELECT key, value FROM store_meta LIMIT 65").fetchall()
    if len(rows) > 64:
        raise fail(ProfileErrorCode.STORE_CORRUPTION)
    meta: dict[str, str] = {}
    for raw_key, raw_value in rows:
        key = read_text(raw_key)
        if key in meta:
            raise fail(ProfileErrorCode.STORE_CORRUPTION)
        meta[key] = read_text(raw_value)
    if set(meta) != {_META_VERSION_KEY, _META_STORE_ID_KEY}:
        raise fail(ProfileErrorCode.STORE_CORRUPTION)
    if meta[_META_VERSION_KEY] != str(STORE_SCHEMA_VERSION):
        raise fail(ProfileErrorCode.STORE_CORRUPTION)
    read_store_id(meta[_META_STORE_ID_KEY])


def check_foreign_key_violations(connection: sqlite3.Connection) -> None:
    """Reject orphan rows that violate the revision-to-record foreign key.

    Runs inside the caller's transaction before its work, so external DDL tampering or direct row
    deletion after initialization still fails closed instead of silently producing partial results.
    Reads at most one violation row: any violation at all is fatal. (SQLite pragmas take no LIMIT
    clause, so the bound is enforced by fetching a single row.)
    """
    try:
        violation = connection.execute("PRAGMA foreign_key_check").fetchone()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    if violation is not None:
        raise fail(ProfileErrorCode.STORE_CORRUPTION)



def read_store_id(value: Any) -> str:
    """Validate a store ID: exactly 32 lowercase hex characters, never echoed."""
    if not isinstance(value, str) or _HEX_32_RE.match(value) is None:
        raise fail(ProfileErrorCode.STORE_CORRUPTION)
    return value


def read_text(value: Any) -> str:
    """Read a TEXT column without coercion. Anything else is corruption, never echoed."""
    if not isinstance(value, str):
        raise fail(ProfileErrorCode.STORE_CORRUPTION)
    return value


def read_flag(value: Any) -> bool:
    """Read an ``enabled`` flag: exactly the integer 0 or 1, never a boolean lookalike."""
    if type(value) is not int or value not in (0, 1):
        raise fail(ProfileErrorCode.STORE_CORRUPTION)
    return value == 1


def read_count(value: Any, *, minimum: int = 0) -> int:
    """Read a non-negative integer counter without coercion."""
    if type(value) is not int or value < minimum:
        raise fail(ProfileErrorCode.STORE_CORRUPTION)
    return value


def read_revision_number(value: Any) -> int:
    """Read a positive revision number without coercion."""
    if type(value) is not int or value < 1:
        raise fail(ProfileErrorCode.STORE_CORRUPTION)
    return value


def read_hash(value: Any) -> str:
    """Read a SHA-256 hex digest without coercion or echo."""
    if not isinstance(value, str) or _HEX_64_RE.match(value) is None:
        raise fail(ProfileErrorCode.STORE_CORRUPTION)
    return value


def read_utc(value: Any) -> str:
    """Read a UTC timestamp string, checked for ISO-8601 shape without echoing it."""
    if not isinstance(value, str):
        raise fail(ProfileErrorCode.STORE_CORRUPTION)
    from datetime import datetime, timedelta

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise fail(ProfileErrorCode.STORE_CORRUPTION) from None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise fail(ProfileErrorCode.STORE_CORRUPTION)
    return value


def read_query_int(value: Any, *, minimum: int, maximum: int) -> int:
    """Validate a caller-supplied integer argument (limit, offset, revision) without coercion.

    Rejects booleans, non-integers, and anything outside SQLite's signed 64-bit range so binding it can
    never leak an ``OverflowError``. Out-of-contract values are ``value_out_of_range``.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise fail(ProfileErrorCode.VALUE_OUT_OF_RANGE)
    if value < minimum or value > maximum or value < _SQLITE_INT_MIN or value > _SQLITE_INT_MAX:
        raise fail(ProfileErrorCode.VALUE_OUT_OF_RANGE)
    return value


def check_profile_id_text(value: Any) -> str:
    """Validate a caller-supplied profile ID: a string matching the ID pattern, never echoed."""
    if not isinstance(value, str) or _PROFILE_ID_RE.match(value) is None:
        raise fail(ProfileErrorCode.INVALID_PROFILE_ID)
    return value


def normalize_selection(profile_ids: Sequence[str] | None) -> tuple[str, ...] | None:
    """Validate a snapshot selection before copying it: at most 64 entries, exact IDs, no repeats.

    A repeated ID in one selection is a duplicate, not a silent dedupe. Nothing caller-supplied is echoed.
    """
    if profile_ids is None:
        return None
    if isinstance(profile_ids, (str, bytes)) or not isinstance(profile_ids, Sequence):
        raise fail(ProfileErrorCode.INVALID_TYPE)
    if len(profile_ids) > MAX_PROFILES:
        raise fail(ProfileErrorCode.PROFILE_LIMIT_EXCEEDED, count=len(profile_ids))
    names: list[str] = []
    seen: set[str] = set()
    for name in profile_ids:
        checked = check_profile_id_text(name)
        if checked in seen:
            raise fail(ProfileErrorCode.DUPLICATE_PROFILE_ID)
        seen.add(checked)
        names.append(checked)
    return tuple(names)


def parse_stored_payload(text: str) -> Profile:
    """Parse, bound, and validate one stored canonical payload, returning its profile.

    Reuses the core JSON bounds (envelope counts, depth, node budget) before structural validation, so a
    stored payload gets exactly the same treatment as an incoming document. The byte bound is enforced on
    the text itself before parsing, as a second line of defense behind the pre-fetch length check. Every
    defect — oversized, duplicate keys, bad structure, over-budget shape, schema-invalid content — is a
    closed ``store_corruption``: a stored payload that fails anywhere means the database cannot be trusted,
    and no structural detail is reported.
    """
    if not isinstance(text, str):
        raise fail(ProfileErrorCode.STORE_CORRUPTION)
    try:
        size = len(text.encode("utf-8"))
    except ValueError:
        # UnicodeEncodeError derives from ValueError; listed separately it is redundant.
        raise fail(ProfileErrorCode.STORE_CORRUPTION) from None
    from guiskindose.equipment_profiles.constants import MAX_SOURCE_BYTES

    if size > MAX_SOURCE_BYTES:
        raise fail(ProfileErrorCode.STORE_CORRUPTION)
    try:
        import json

        payload = json.loads(text, object_pairs_hook=_rejecting_pairs_hook)
    except _DuplicateStoredKey:
        raise fail(ProfileErrorCode.STORE_CORRUPTION) from None
    except (ValueError, TypeError, RecursionError):
        raise fail(ProfileErrorCode.STORE_CORRUPTION) from None
    if not isinstance(payload, dict):
        raise fail(ProfileErrorCode.STORE_CORRUPTION)
    try:
        check_document_bounds({"schema_version": SCHEMA_VERSION, "profiles": [payload]}, source_kind=SOURCE_KIND_STORE)
        profiles = validate_document(
            {"schema_version": SCHEMA_VERSION, "profiles": [payload]}, source_kind=SOURCE_KIND_STORE
        )
    except EquipmentProfileError:
        raise fail(ProfileErrorCode.STORE_CORRUPTION) from None
    if len(profiles) != 1:
        raise fail(ProfileErrorCode.STORE_CORRUPTION)
    return profiles[0]


class _DuplicateStoredKey(Exception):
    """Private signal for a duplicate key in stored payload text; never escapes this module."""

    __slots__ = ()


def _rejecting_pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateStoredKey
        result[key] = value
    return result


def check_profile_types(profile: Any) -> Profile:
    """Strictly pre-validate a caller-supplied ``Profile`` before canonical serialization.

    Canonical serialization coerces (``float()``, ``bool()``), so a hand-built object with a wrong-typed
    value must be rejected *here*, with a closed error, before anything is serialized. Requires an actual
    ``Profile`` instance; validates every nested block and leaf type without coercion and without echoing
    values.
    """
    if not isinstance(profile, Profile):
        raise fail(ProfileErrorCode.INVALID_TYPE)
    if not isinstance(profile.profile_id, str) or not isinstance(profile.manufacturer, str):
        raise fail(ProfileErrorCode.INVALID_TYPE)
    if not isinstance(profile.models, tuple) or not all(isinstance(model, str) for model in profile.models):
        raise fail(ProfileErrorCode.INVALID_TYPE)
    _check_alias_fields(profile)
    _check_provenance_field(profile)
    if profile.coordinates is not None:
        _check_coordinates(profile.coordinates)
    if not isinstance(profile.transmission, tuple):
        raise fail(ProfileErrorCode.INVALID_TYPE)
    for row in profile.transmission:
        _check_transmission_row(row)
    if not isinstance(profile.promote_coordinate_wildcard, bool):
        raise fail(ProfileErrorCode.INVALID_TYPE)
    return profile


def _check_alias_fields(profile: Profile) -> None:
    """Strict container and element types for identity and alias fields."""
    if not isinstance(profile.manufacturer_aliases, tuple) or not all(
        isinstance(alias, str) for alias in profile.manufacturer_aliases
    ):
        raise fail(ProfileErrorCode.INVALID_TYPE)
    if not isinstance(profile.model_aliases, tuple) or not all(
        isinstance(pair, tuple) and len(pair) == 2 and all(isinstance(part, str) for part in pair)
        for pair in profile.model_aliases
    ):
        raise fail(ProfileErrorCode.INVALID_TYPE)


def _check_provenance_field(profile: Profile) -> None:
    """Strict type check for the optional provenance block."""
    if profile.provenance is None:
        return
    from guiskindose.equipment_profiles.models import Provenance

    if not isinstance(profile.provenance, Provenance):
        raise fail(ProfileErrorCode.INVALID_TYPE)
    for text in (profile.provenance.source, profile.provenance.notes):
        if text is not None and not isinstance(text, str):
            raise fail(ProfileErrorCode.INVALID_TYPE)


def _check_number(value: Any) -> None:
    """A finite number that is not a boolean; huge integers fail closed instead of overflowing."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise fail(ProfileErrorCode.INVALID_NUMBER)
    try:
        result = float(value)
    except (OverflowError, ValueError):
        raise fail(ProfileErrorCode.INVALID_NUMBER) from None
    if math.isnan(result) or result in (float("inf"), float("-inf")):
        raise fail(ProfileErrorCode.INVALID_NUMBER)


def _check_coordinates(coordinates: Coordinates) -> None:
    if not isinstance(coordinates, Coordinates):
        raise fail(ProfileErrorCode.INVALID_TYPE)
    _check_offset_block(coordinates.translation_offset)
    _check_sign_block(
        coordinates.translation_direction,
        TranslationDirection,
        ("x", "y", "z"),
    )
    _check_sign_block(
        coordinates.rotation_direction,
        RotationDirection,
        ("ap1", "ap2", "ap3", "at1", "at2", "at3"),
    )
    _check_scalar_leaves(coordinates)


def _check_offset_block(offset: TranslationOffset | None) -> None:
    if offset is None:
        return
    if not isinstance(offset, TranslationOffset):
        raise fail(ProfileErrorCode.INVALID_TYPE)
    for axis in (offset.x, offset.y, offset.z):
        if axis is not None:
            _check_number(axis)


def _check_sign_block(block: Any, kind: type, leaves: tuple[str, ...]) -> None:
    if block is None:
        return
    if not isinstance(block, kind):
        raise fail(ProfileErrorCode.INVALID_TYPE)
    for leaf in leaves:
        value = getattr(block, leaf)
        if value is not None and not isinstance(value, str):
            raise fail(ProfileErrorCode.INVALID_TYPE)


def _check_scalar_leaves(coordinates: Coordinates) -> None:
    swap = coordinates.swap_lateral_longitudinal
    if swap is not None and not isinstance(swap, bool):
        raise fail(ProfileErrorCode.INVALID_TYPE)
    mode = coordinates.field_size_mode
    if mode is not None and not isinstance(mode, str):
        raise fail(ProfileErrorCode.INVALID_TYPE)
    size = coordinates.detector_side_length
    if size is not None:
        _check_number(size)


def _check_transmission_row(row: Any) -> None:
    if not isinstance(row, TransmissionRow):
        raise fail(ProfileErrorCode.INVALID_TYPE)
    for text in (
        row.device_model,
        row.acquisition_plane,
        row.evidence_status,
        row.source,
        row.date,
        row.comment,
    ):
        if text is not None and not isinstance(text, str):
            raise fail(ProfileErrorCode.INVALID_TYPE)
    for number in (
        row.kvp_kv,
        row.filtration_added_mmcu,
        row.filtration_added_mmal,
        row.k_patient_support,
    ):
        _check_number(number)
