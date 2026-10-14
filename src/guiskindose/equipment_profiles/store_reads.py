"""Shared read helpers for the transactional profile store.

Module-level functions taking an explicit connection, so both ``profile_store.ProfileStore`` and
``store_writes`` can use them without inheritance or import cycles. Every helper is strict: row fields are
parsed with the no-coercion readers from :mod:`guiskindose.equipment_profiles.store_schema`, and any defect
is a value-free error that never echoes a value.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from guiskindose.equipment_profiles.conflicts import validate_profile_set
from guiskindose.equipment_profiles.constants import MAX_AGGREGATE_ROWS, MAX_PROFILES, SOURCE_KIND_STORE
from guiskindose.equipment_profiles.errors import ProfileErrorCode
from guiskindose.equipment_profiles.models import Profile
from guiskindose.equipment_profiles.store_schema import (
    normalize_db_error,
    read_count,
    read_flag,
    read_hash,
    read_revision_number,
    read_text,
    read_utc,
    store_error,
)
from guiskindose.equipment_profiles.store_types import (
    SelectedRevision,
    StoredRecord,
    StoredRevision,
    StoreSnapshot,
    store_source_hash,
)


def fetch_record_row(connection: sqlite3.Connection, profile_id: str) -> tuple[Any, ...] | None:
    """Fetch one raw record row, or ``None`` when the ID is absent. Never raises on absence."""
    try:
        return connection.execute(
            "SELECT profile_id, enabled, current_revision, generation, updated_utc "
            "FROM profile_records WHERE profile_id = ?",
            (profile_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None


def current_hash(connection: sqlite3.Connection, profile_id: str) -> str:
    """Read the stored hash of a record's current revision. Absence means corruption, not absence."""
    try:
        row = connection.execute(
            "SELECT profile_hash FROM profile_revisions WHERE profile_id = ? AND revision = "
            "(SELECT current_revision FROM profile_records WHERE profile_id = ?)",
            (profile_id, profile_id),
        ).fetchone()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    if row is None:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    return read_hash(row[0])


def record_from_row(connection: sqlite3.Connection, row: tuple[Any, ...]) -> StoredRecord:
    """Build record metadata from a raw record row, verifying the current revision's hash."""
    profile_id = read_text(row[0])
    enabled = read_flag(row[1])
    revision = read_revision_number(row[2])
    generation = read_revision_number(row[3])
    updated = read_utc(row[4])
    stored_hash = current_hash(connection, profile_id)
    return StoredRecord(
        profile_id=profile_id,
        enabled=enabled,
        current_revision=revision,
        generation=generation,
        profile_hash=stored_hash,
        updated_utc=updated,
    )


def fetch_revision_meta(
    connection: sqlite3.Connection, profile_id: str, revision: int
) -> tuple[Any, ...] | None:
    """Fetch a revision's ``(revision, logical_rows, length, type)`` after no materialization.

    The payload length and storage type are queried *before* the payload text is fetched, so an
    untrusted huge BLOB is never materialized into Python before its bound is checked.
    """
    try:
        return connection.execute(
            "SELECT revision, logical_rows, length(CAST(payload_json AS BLOB)), typeof(payload_json) "
            "FROM profile_revisions WHERE profile_id = ? AND revision = ?",
            (profile_id, revision),
        ).fetchone()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None


def fetch_revision_payload(
    connection: sqlite3.Connection, profile_id: str, revision: int
) -> tuple[str, str, str]:
    """Fetch ``(payload_json, profile_hash, created_utc)`` for a revision known to exist and fit."""
    try:
        row = connection.execute(
            "SELECT payload_json, profile_hash, created_utc FROM profile_revisions "
            "WHERE profile_id = ? AND revision = ?",
            (profile_id, revision),
        ).fetchone()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    if row is None:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    return read_text(row[0]), read_hash(row[1]), read_utc(row[2])


def check_payload_size(meta: tuple[Any, ...]) -> None:
    """Enforce the per-revision byte bound from a pre-fetched ``(revision, rows, length, type)`` row."""
    _revision, _rows, length, storage_type = meta
    if storage_type != "text":
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    from guiskindose.equipment_profiles.constants import MAX_SOURCE_BYTES

    size = read_count(length, minimum=0)
    if size > MAX_SOURCE_BYTES:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)


def check_logical_rows(meta: tuple[Any, ...], profile: Profile) -> None:
    """Reject a stored count that disagrees with the verified canonical payload."""
    if read_count(meta[1], minimum=1) != profile.logical_row_count():
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)


def verify_stored_payload(text: str, profile_id: str, expected_hash: str) -> Profile:
    """Re-parse, re-validate, re-hash, and re-count stored payload text on every read.

    A hand-edited database that is merely consistent-looking still fails closed: the payload must parse
    under the core JSON bounds, validate as exactly one profile with the expected ID, hash to the stored
    hash, and report a logical row count within bounds.
    """
    from guiskindose.equipment_profiles.store_schema import parse_stored_payload

    profile = parse_stored_payload(text)
    if profile.profile_id != profile_id:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    from guiskindose.equipment_profiles.canonical import profile_hash

    if profile_hash(profile) != expected_hash:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    if profile.logical_row_count() > MAX_AGGREGATE_ROWS:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    return profile


def revision_from_row(profile_id: str, row: tuple[Any, ...]) -> StoredRevision:
    """Build one stored revision from a verified ``(revision, payload, hash, created)`` row."""
    revision = read_revision_number(row[0])
    payload_json = read_text(row[1])
    stored_hash = read_hash(row[2])
    created_utc = read_utc(row[3])
    profile = verify_stored_payload(payload_json, profile_id, stored_hash)
    return StoredRevision(
        profile_id=profile_id,
        revision=revision,
        profile=profile,
        profile_hash=stored_hash,
        payload_json=payload_json,
        created_utc=created_utc,
    )


def verified_current_profile(connection: sqlite3.Connection, profile_id: str, revision: int) -> Profile:
    """Load and fully verify one current revision inside the caller's transaction."""
    meta = fetch_revision_meta(connection, profile_id, revision)
    if meta is None:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    check_payload_size(meta)
    payload_json, stored_hash, _created = fetch_revision_payload(connection, profile_id, revision)
    profile = verify_stored_payload(payload_json, profile_id, stored_hash)
    check_logical_rows(meta, profile)
    return profile


def revision_meta_for_record(
    connection: sqlite3.Connection, row: tuple[Any, ...]
) -> tuple[Any, ...] | None:
    """Fetch the size/type pre-check row for a record row's current revision."""
    name = read_text(row[0])
    revision = read_revision_number(row[2])
    return fetch_revision_meta(connection, name, revision)


def verified_record(connection: sqlite3.Connection, row: tuple[Any, ...]) -> StoredRecord:
    """Build record metadata from a raw record row, verifying its current revision first."""
    meta = revision_meta_for_record(connection, row)
    if meta is None:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    check_payload_size(meta)
    name = read_text(row[0])
    revision = read_revision_number(row[2])
    payload_json, stored_hash, _created = fetch_revision_payload(connection, name, revision)
    profile = verify_stored_payload(payload_json, name, stored_hash)
    check_logical_rows(meta, profile)
    return record_from_row(connection, row)


def enabled_names(connection: sqlite3.Connection) -> list[tuple[str, int]]:
    """List ``(profile_id, current_revision)`` for enabled records, detecting an oversized set.

    Reads at most one row past the profile ceiling so an oversized enabled set is detected before its
    payloads are materialized.
    """
    try:
        rows = connection.execute(
            "SELECT profile_id, current_revision FROM profile_records WHERE enabled = 1 "
            "ORDER BY profile_id LIMIT ?",
            (MAX_PROFILES + 1,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    if len(rows) > MAX_PROFILES:
        raise store_error(ProfileErrorCode.PROFILE_LIMIT_EXCEEDED, count=len(rows))
    return [(read_text(row[0]), read_revision_number(row[1])) for row in rows]


def check_global_caps(connection: sqlite3.Connection, selected_names: list[str]) -> None:
    """Verify a hand-edited file still respects the global growth caps before reading it.

    Every count is a single integer, never a materialized row list: the record total, the revision total,
    the distinct revision identities, and the tombstone total are each checked before any per-profile loop
    runs, so a corrupt file with millions of orphan rows cannot force unbounded work. Anything over a cap is
    corruption of the file's invariants, not a limit breach.
    """
    from guiskindose.equipment_profiles.store_schema import MAX_REVISIONS_PER_PROFILE, MAX_STORE_RECORDS

    try:
        total_records = connection.execute("SELECT COUNT(*) FROM profile_records").fetchone()
        total_revisions = connection.execute("SELECT COUNT(*) FROM profile_revisions").fetchone()
        distinct_revisions = connection.execute(
            "SELECT COUNT(DISTINCT profile_id) FROM profile_revisions"
        ).fetchone()
        total_tombstones = connection.execute("SELECT COUNT(*) FROM profile_tombstones").fetchone()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    for value in (total_records, total_revisions, distinct_revisions, total_tombstones):
        if value is None or not isinstance(value[0], int):
            raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    if total_records[0] > MAX_STORE_RECORDS:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    if total_revisions[0] > MAX_STORE_RECORDS * MAX_REVISIONS_PER_PROFILE:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    if distinct_revisions[0] > MAX_STORE_RECORDS:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    check_identity_capacity(total_records[0], total_tombstones[0])
    counts = _revision_counts_by_profile(connection)
    selected = set(selected_names)
    for raw_id, raw_count in counts:
        name = read_text(raw_id)
        if not isinstance(raw_count, int) or raw_count > MAX_REVISIONS_PER_PROFILE:
            raise store_error(ProfileErrorCode.STORE_CORRUPTION)
        if name in selected and raw_count < 1:
            raise store_error(ProfileErrorCode.STORE_CORRUPTION)


def check_identity_capacity(live_records: int, tombstones: int) -> None:
    """Enforce the total-identity bound (live records plus tombstones) without materializing either."""
    from guiskindose.equipment_profiles.store_schema import MAX_STORED_IDENTITIES

    if live_records + tombstones > MAX_STORED_IDENTITIES:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)


def _revision_counts_by_profile(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    """Per-profile revision counts, safe to fetch only after the totals above have bounded the groups."""
    try:
        return connection.execute(
            "SELECT profile_id, COUNT(*) FROM profile_revisions GROUP BY profile_id"
        ).fetchall()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None


def check_database_caps(connection: sqlite3.Connection) -> None:
    """Enforce the growth caps with three single-integer queries, for every transaction.

    Cheap enough to run on ordinary reads and writes — not only on snapshots — so a file edited between
    calls cannot silently exceed the invariants any operation relies on.
    """
    try:
        total_records = connection.execute("SELECT COUNT(*) FROM profile_records").fetchone()
        total_revisions = connection.execute("SELECT COUNT(*) FROM profile_revisions").fetchone()
        total_tombstones = connection.execute("SELECT COUNT(*) FROM profile_tombstones").fetchone()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    from guiskindose.equipment_profiles.store_schema import MAX_REVISIONS_PER_PROFILE, MAX_STORE_RECORDS

    for value in (total_records, total_revisions, total_tombstones):
        if value is None or not isinstance(value[0], int):
            raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    if total_records[0] > MAX_STORE_RECORDS:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    if total_revisions[0] > MAX_STORE_RECORDS * MAX_REVISIONS_PER_PROFILE:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    check_identity_capacity(total_records[0], total_tombstones[0])


def plan_selection(
    connection: sqlite3.Connection, names: list[str]
) -> list[tuple[str, int, int]]:
    """Resolve each selected ID to ``(profile_id, current_revision, stored logical rows)``."""
    planned: list[tuple[str, int, int]] = []
    for name in names:
        record = fetch_record_row(connection, name)
        if record is None:
            raise store_error(ProfileErrorCode.STORE_NOT_FOUND)
        revision = read_revision_number(record[2])
        try:
            row = connection.execute(
                "SELECT logical_rows FROM profile_revisions WHERE profile_id = ? AND revision = ?",
                (name, revision),
            ).fetchone()
        except sqlite3.Error as exc:
            raise normalize_db_error(type(exc)) from None
        if row is None:
            raise store_error(ProfileErrorCode.STORE_CORRUPTION)
        planned.append((name, revision, read_count(row[0], minimum=1)))
    return planned


def check_aggregate_rows(total: int) -> None:
    """Enforce the aggregate logical-row ceiling on a pre-materialization total."""
    if total > MAX_AGGREGATE_ROWS:
        raise store_error(ProfileErrorCode.ROW_LIMIT_EXCEEDED, count=total)


def store_id_value(connection: sqlite3.Connection) -> str:
    """Read and strictly validate the database's opaque store ID."""
    from guiskindose.equipment_profiles.store_schema import read_store_id

    try:
        row = connection.execute("SELECT value FROM store_meta WHERE key = 'store_id'").fetchone()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    if row is None:
        raise store_error(ProfileErrorCode.STORE_CORRUPTION)
    return read_store_id(row[0])


def enabled_revision_metas(
    connection: sqlite3.Connection, *, exclude: str | None = None
) -> list[tuple[str, int, int]]:
    """List ``(profile_id, revision, logical_rows)`` for enabled records, detecting an oversized set.

    Reads at most one row past the ceiling so an oversized enabled set is detected before payloads load.
    Uses a LEFT JOIN and rejects a missing revision side: an enabled record whose current revision row is
    absent is corruption, and an INNER JOIN would silently omit it from conflict validation.
    """
    try:
        rows = connection.execute(
            "SELECT r.profile_id, r.current_revision, v.logical_rows FROM profile_records r "
            "LEFT JOIN profile_revisions v ON v.profile_id = r.profile_id "
            "AND v.revision = r.current_revision "
            "WHERE r.enabled = 1 ORDER BY r.profile_id LIMIT ?",
            (MAX_PROFILES + 1,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise normalize_db_error(type(exc)) from None
    metas: list[tuple[str, int, int]] = []
    for raw_id, raw_revision, raw_rows in rows:
        name = read_text(raw_id)
        if exclude is not None and name == exclude:
            continue
        if raw_rows is None:
            raise store_error(ProfileErrorCode.STORE_CORRUPTION)
        metas.append((name, read_revision_number(raw_revision), read_count(raw_rows, minimum=1)))
    return metas


def assemble_snapshot(
    connection: sqlite3.Connection,
    store_id: str,
    planned: list[tuple[str, int, int]],
) -> StoreSnapshot:
    """Load, verify, conflict-check, and hash one planned selection inside the caller's transaction."""
    selected: list[SelectedRevision] = []
    profiles: list[Profile] = []
    for name, revision, _rows in planned:
        meta = fetch_revision_meta(connection, name, revision)
        if meta is None:
            raise store_error(ProfileErrorCode.STORE_CORRUPTION)
        check_payload_size(meta)
        payload_json, stored_hash, created_utc = fetch_revision_payload(connection, name, revision)
        stored = revision_from_row(name, (revision, payload_json, stored_hash, created_utc))
        check_logical_rows(meta, stored.profile)
        selected.append(
            SelectedRevision(profile_id=name, revision=revision, profile_hash=stored.profile_hash)
        )
        profiles.append(stored.profile)
    ordered = sorted(zip(selected, profiles, strict=True), key=lambda pair: pair[0].profile_id)
    ordered_selected = tuple(item for item, _profile in ordered)
    ordered_profiles = tuple(item for _item, item in ordered)
    check_aggregate_rows(sum(profile.logical_row_count() for profile in ordered_profiles))
    validate_profile_set(ordered_profiles, source_kind=SOURCE_KIND_STORE)

    source_hash = store_source_hash(store_id, ordered_selected)
    return StoreSnapshot(
        store_id=store_id,
        source_kind=SOURCE_KIND_STORE,
        selected=ordered_selected,
        profiles=ordered_profiles,
        source_hash=source_hash,
        logical_rows=sum(profile.logical_row_count() for profile in ordered_profiles),
    )
