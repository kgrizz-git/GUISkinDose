"""Write operations for the transactional profile store.

Module-level functions taking an explicit ``store`` handle, so ``profile_store.ProfileStore`` stays small
without inheritance or import cycles (the handle type is imported only under ``TYPE_CHECKING``). Every
operation runs inside the handle's transaction wrapper and rolls back on any failure; see
:mod:`guiskindose.equipment_profiles.profile_store` for the transaction contract.
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from guiskindose.equipment_profiles import store_schema as _store_schema
from guiskindose.equipment_profiles.canonical import canonical_json_bytes, canonical_profile_dict, profile_hash
from guiskindose.equipment_profiles.conflicts import validate_profile_set
from guiskindose.equipment_profiles.constants import (
    MAX_AGGREGATE_ROWS,
    MAX_PROFILES,
    MAX_SOURCE_BYTES,
    SCHEMA_VERSION,
    SOURCE_KIND_STORE,
)
from guiskindose.equipment_profiles.errors import ProfileErrorCode
from guiskindose.equipment_profiles.models import Profile
from guiskindose.equipment_profiles.store_reads import (
    enabled_revision_metas,
    fetch_record_row,
    record_from_row,
    verified_current_profile,
)
from guiskindose.equipment_profiles.store_schema import (
    SQLITE_INT_MAX,
    check_profile_id_text,
    check_profile_types,
    normalize_db_error,
    read_flag,
    read_query_int,
    read_revision_number,
    store_error,
    utc_now_iso,
)
from guiskindose.equipment_profiles.store_types import StoredRecord
from guiskindose.equipment_profiles.validation import validate_document

if TYPE_CHECKING:
    from guiskindose.equipment_profiles.profile_store import ProfileStore


def _new_revision_numbers(
    connection: sqlite3.Connection,
    profile: Profile,
    record: Any,
    expected: int | None,
) -> tuple[int, int, bool]:
    """Resolve generation, revision, and enablement for a new-revision write.

    Creating a record expects absence (continuing any tombstoned generation);
    updating requires the expected current revision. Re-enabling an enabled
    record is validated against the would-be enabled set before anything is
    written.
    """
    if record is None:
        if expected is not None:
            raise store_error(ProfileErrorCode.STORE_CONFLICT)
        generation, revision = _consume_tombstone(connection, profile.profile_id)
        _check_record_capacity(connection)
        _check_identity_capacity_for_create(connection)
        return generation, revision, False
    if expected is None:
        raise store_error(ProfileErrorCode.STORE_CONFLICT)
    current = read_revision_number(record[2])
    if current != expected:
        raise store_error(ProfileErrorCode.STORE_CONFLICT)
    generation = read_revision_number(record[3]) + 1
    _check_revision_capacity(connection, profile.profile_id)
    revision, enabled = current + 1, read_flag(record[1])
    if enabled:
        _validate_would_be_enabled(connection, profile, exclude=profile.profile_id)
    return generation, revision, enabled


def save_new_revision(
    store: ProfileStore, profile: Profile, *, expected_current_revision: int | None = None
) -> StoredRecord:
    """Save ``profile`` as a new immutable revision and return the updated record metadata.

    The candidate is strictly type-checked and then round-trip validated — serialized to its canonical
    mapping, re-parsed, and re-hashed — so a hand-built ``Profile`` that cannot survive its own canonical
    form never reaches the database, and no raw conversion error ever escapes. Creating a record expects
    absence; updating an existing record **requires** ``expected_current_revision``, so an accidental
    omission cannot overwrite newer content. A brand-new record starts **disabled** with generation 1; a
    recreated ID continues its tombstoned generation and revision number, never reusing either.
    Unsupported feature capabilities may be persisted but are never activated or applied here; activation
    is a separate, later step.
    """
    check_profile_types(profile)
    payload, content_hash, rows = _roundtrip_candidate(profile)
    expected = _validate_expected(expected_current_revision)

    def work(connection: sqlite3.Connection) -> StoredRecord:
        record = fetch_record_row(connection, profile.profile_id)
        generation, revision, enabled = _new_revision_numbers(connection, profile, record, expected)
        created = utc_now_iso()
        return _persist_new_revision(
            connection, profile, record, generation, revision, enabled,
            payload, content_hash, rows, created,
        )

    return store._write(work)


def _persist_new_revision(
    connection: sqlite3.Connection,
    profile: Profile,
    record: Any,
    generation: int,
    revision: int,
    enabled: bool,
    payload: str,
    content_hash: str,
    rows: int,
    created: str,
) -> StoredRecord:
    """Write the record and revision rows for a resolved new revision, then return metadata."""
    if record is None:
        connection.execute(
            "INSERT INTO profile_records(profile_id, enabled, current_revision, generation, "
            "updated_utc) VALUES (?, 0, ?, ?, ?)",
            (profile.profile_id, revision, generation, created),
        )
    else:
        connection.execute(
            "UPDATE profile_records SET current_revision = ?, generation = ?, updated_utc = ? "
            "WHERE profile_id = ?",
            (revision, generation, created, profile.profile_id),
        )
    try:
        connection.execute(
            "INSERT INTO profile_revisions(profile_id, revision, payload_json, profile_hash, "
            "logical_rows, created_utc) VALUES (?, ?, ?, ?, ?, ?)",
            (profile.profile_id, revision, payload, content_hash, rows, created),
        )
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    return StoredRecord(
        profile_id=profile.profile_id,
        enabled=enabled,
        current_revision=revision,
        generation=generation,
        profile_hash=content_hash,
        updated_utc=created,
    )


def _persist_enabled_state(
    connection: sqlite3.Connection, name: str, enabled: bool, generation: int
) -> StoredRecord:
    """Write the enablement/generation update, then return the refreshed metadata."""
    updated = utc_now_iso()
    try:
        connection.execute(
            "UPDATE profile_records SET enabled = ?, generation = ?, updated_utc = ? "
            "WHERE profile_id = ?",
            (1 if enabled else 0, generation + 1, updated, name),
        )
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    refreshed = fetch_record_row(connection, name)
    if refreshed is None:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    return record_from_row(connection, refreshed)


def _validate_expected(expected: int | None) -> int | None:
    if expected is None:
        return None
    return read_query_int(expected, minimum=1, maximum=SQLITE_INT_MAX)


def _consume_tombstone(connection: sqlite3.Connection, profile_id: str) -> tuple[int, int]:
    """Consume a delete tombstone, continuing its generation and revision monotonically.

    Returns ``(generation, first_revision)``. Without a tombstone the ID is brand new: generation 1,
    revision 1. Either way a delete/recreate cycle can never silently reuse a revision number.
    """
    try:
        row = connection.execute(
            "SELECT generation, next_revision FROM profile_tombstones WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    if row is None:
        return 1, 1
    generation = read_revision_number(row[0])
    revision = read_revision_number(row[1])
    try:
        connection.execute("DELETE FROM profile_tombstones WHERE profile_id = ?", (profile_id,))
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    return generation, revision


def _roundtrip_candidate(profile: Profile) -> tuple[str, str, int]:
    """Serialize, re-validate, and re-hash a save candidate; return ``(payload_json, hash, rows)``."""
    try:
        mapping = canonical_profile_dict(profile)
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise store_error(ProfileErrorCode.STORE_CORRUPTION) from None
    reparsed = validate_document(
        {"schema_version": SCHEMA_VERSION, "profiles": [mapping]}, source_kind=SOURCE_KIND_STORE
    )
    if len(reparsed) != 1 or canonical_profile_dict(reparsed[0]) != mapping:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    content_hash = profile_hash(reparsed[0])
    try:
        payload = canonical_json_bytes(mapping).decode("utf-8")
    except (ValueError, TypeError, OverflowError):
        raise store_error(ProfileErrorCode.STORE_CORRUPTION) from None
    if len(payload.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise store_error(ProfileErrorCode.OVERSIZED_SOURCE, count=MAX_SOURCE_BYTES)
    return payload, content_hash, reparsed[0].logical_row_count()


def _check_record_capacity(connection: sqlite3.Connection) -> None:
    try:
        count = connection.execute("SELECT COUNT(*) FROM profile_records").fetchone()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    if count is None or not isinstance(count[0], int) or count[0] >= _store_schema.MAX_STORE_RECORDS:
        raise store_error(
            ProfileErrorCode.STORE_LIMIT_EXCEEDED, count=_store_schema.MAX_STORE_RECORDS
        )


def _check_identity_capacity_for_create(connection: sqlite3.Connection) -> None:
    """Enforce the total-identity bound before a brand-new ID is added.

    Deleting removes one record for every tombstone it adds, so creation is the only path that grows the
    total. Both counts are single integers; the payloads are never touched.
    """
    try:
        records = connection.execute("SELECT COUNT(*) FROM profile_records").fetchone()
        tombstones = connection.execute("SELECT COUNT(*) FROM profile_tombstones").fetchone()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    if records is None or tombstones is None:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    if (
        not isinstance(records[0], int)
        or not isinstance(tombstones[0], int)
        or records[0] + tombstones[0] + 1 > _store_schema.MAX_STORED_IDENTITIES
    ):
        raise store_error(
            ProfileErrorCode.STORE_LIMIT_EXCEEDED, count=_store_schema.MAX_STORED_IDENTITIES
        )


def _check_revision_capacity(connection: sqlite3.Connection, profile_id: str) -> None:
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM profile_revisions WHERE profile_id = ?", (profile_id,)
        ).fetchone()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    if count is None or not isinstance(count[0], int) or count[0] >= _store_schema.MAX_REVISIONS_PER_PROFILE:
        raise store_error(
            ProfileErrorCode.STORE_LIMIT_EXCEEDED, count=_store_schema.MAX_REVISIONS_PER_PROFILE
        )


def _validate_would_be_enabled(
    connection: sqlite3.Connection, candidate: Profile, *, exclude: str
) -> None:
    """Validate the would-be enabled set — every enabled current revision plus one candidate.

    Bounds the enabled set (at most 64 profiles, at most 10,000 aggregate stored rows) before loading
    any payload, then loads, verifies, and conflict-checks the whole set atomically inside the caller's
    transaction.
    """
    metas = enabled_revision_metas(connection, exclude=exclude)
    if len(metas) >= MAX_PROFILES:
        raise store_error(ProfileErrorCode.PROFILE_LIMIT_EXCEEDED, count=len(metas) + 1)
    if sum(rows for _name, _rev, rows in metas) + candidate.logical_row_count() > MAX_AGGREGATE_ROWS:
        raise store_error(ProfileErrorCode.ROW_LIMIT_EXCEEDED)
    profiles = [verified_current_profile(connection, name, revision) for name, revision, _ in metas]
    profiles.append(candidate)
    validate_profile_set(tuple(profiles), source_kind=SOURCE_KIND_STORE)


def _resolve_enabled_mutation(
    connection: sqlite3.Connection,
    name: str,
    enabled: bool,
    expected: int | None,
    wanted_generation: int | None,
) -> tuple[int, Profile]:
    """Fetch, expectation-check, and verify the mutation target, validating conflicts.

    Returns the current generation and the verified candidate profile. A
    missing record, a mismatched expectation, or a conflicting enable all fail
    closed before anything is written.
    """
    record = fetch_record_row(connection, name)
    if record is None:
        raise store_error(ProfileErrorCode.STORE_NOT_FOUND)
    current = read_revision_number(record[2])
    generation = read_revision_number(record[3])
    if expected is not None and current != expected:
        raise store_error(ProfileErrorCode.STORE_CONFLICT)
    if wanted_generation is not None and generation != wanted_generation:
        raise store_error(ProfileErrorCode.STORE_CONFLICT)
    # The current revision is verified on every mutation path, not only when enabling: the returned
    # metadata carries its hash, so a tampered payload must fail here too.
    candidate = verified_current_profile(connection, name, current)
    if enabled:
        _validate_would_be_enabled(connection, candidate, exclude=name)
    return generation, candidate


def set_enabled(
    store: ProfileStore, profile_id: str, enabled: bool, *, expected_current_revision: int | None = None, expected_generation: int | None = None
) -> StoredRecord:
    """Enable or disable one record, returning its updated metadata.

    Enabling runs the canonical conflict validation across the would-be enabled set atomically: if the
    candidate would make two enabled profiles claim the same slot or key, the whole write rolls back and
    the canonical error propagates. Disabling never conflicts. The content revision is untouched; only the
    record-state ``generation`` advances, so a future GUI compare-and-swap can target metadata races that
    content revision alone cannot see. Callers that need race protection must pass
    ``expected_current_revision``; an omitted expectation is unconditional caller-controlled behaviour.
    """

    name = check_profile_id_text(profile_id)
    if not isinstance(enabled, bool):
        raise store_error(ProfileErrorCode.INVALID_TYPE)
    expected = _validate_expected(expected_current_revision)
    wanted_generation = _validate_expected(expected_generation)

    def work(connection: sqlite3.Connection) -> StoredRecord:
        generation, _candidate = _resolve_enabled_mutation(connection, name, enabled, expected, wanted_generation)
        return _persist_enabled_state(connection, name, enabled, generation)

    return store._write(work)


def delete_record(
    store: ProfileStore, profile_id: str, *, expected_current_revision: int | None = None, expected_generation: int | None = None
) -> None:
    """Delete one record and all of its revisions atomically, leaving a generation tombstone.

    The tombstone continues the record-state generation and the revision numbering, so recreating the
    same ID can never silently reuse a revision number (no ABA reuse). Callers that need race protection
    must pass ``expected_current_revision``.
    """
    name = check_profile_id_text(profile_id)
    expected = _validate_expected(expected_current_revision)
    wanted_generation = _validate_expected(expected_generation)

    def work(connection: sqlite3.Connection) -> None:
        record = fetch_record_row(connection, name)
        if record is None:
            raise store_error(ProfileErrorCode.STORE_NOT_FOUND)
        current = read_revision_number(record[2])
        generation = read_revision_number(record[3])
        if expected is not None and current != expected:
            raise store_error(ProfileErrorCode.STORE_CONFLICT)
        if wanted_generation is not None and generation != wanted_generation:
            raise store_error(ProfileErrorCode.STORE_CONFLICT)
        try:
            connection.execute("DELETE FROM profile_revisions WHERE profile_id = ?", (name,))
            connection.execute("DELETE FROM profile_records WHERE profile_id = ?", (name,))
            connection.execute(
                "INSERT INTO profile_tombstones(profile_id, generation, next_revision) "
                "VALUES (?, ?, ?) "
                "ON CONFLICT(profile_id) DO UPDATE SET generation = excluded.generation, "
                "next_revision = excluded.next_revision",
                (name, generation + 1, current + 1),
            )
        except sqlite3.Error as exc:
            raise normalize_db_error(type(exc)) from None

    store._write(work)
