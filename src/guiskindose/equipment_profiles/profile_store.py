"""Transactional local user profile store repository (SQLite, stdlib only).

This module implements the store side of the contract in ``dev-docs/EQUIPMENT_PROFILE_SCHEMA.md`` §12. It is a
separate, user-owned SQLite database — never ``corrections_db_path``, never bundled package data — holding
canonical profile payloads with immutable per-profile revisions. There is no application, GUI, CLI,
normalization, or dose-path wiring here: callers persist and reload validated profiles, and a later activation
step consumes the immutable snapshots this module hands back.

Every rule the repository enforces is local and checkable:

- **Explicit lifecycle.** Constructing ``ProfileStore`` touches nothing. ``initialize()`` creates a fresh
  version-1 database or verifies an existing one *without mutating it*; anything else is rejected.
- **One transaction per mutation.** Every write runs inside an explicit ``BEGIN IMMEDIATE`` / ``COMMIT`` pair
  and rolls back on *any* failure — including unexpected ones — so a failed save, enable, or delete leaves no
  partial state and no open transaction behind.
- **Optimistic concurrency with explicit semantics.** Creating a record expects absence; updating an existing
  record *requires* ``expected_current_revision``, so an accidental omission cannot overwrite newer content.
  Enable and delete honor an optional ``expected_current_revision``; callers that need race protection (the GUI
  layer always does) must pass it. Every record also carries a monotonically bumped ``generation`` token, and a
  deleted ID leaves a tombstone, so a delete/recreate cycle can never silently reuse a revision number.
- **No trust, even of our own rows.** Every stored payload is length- and type-checked before it is fetched,
  re-parsed, re-validated, and re-hashed on *every* read, and the parsed row count is rechecked against the
  stored count. A hand-edited database that is merely consistent-looking still fails closed.
- **Value-free diagnostics.** Every failure is an :class:`EquipmentProfileError` with a stable code. No profile
  ID, payload text, note, path, SQL fragment, raw caller key, or library message ever appears in an error, and
  raw causes are always suppressed.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Self, TypeVar

from guiskindose.equipment_profiles.constants import MAX_PROFILES
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.equipment_profiles.models import Profile
from guiskindose.equipment_profiles.store_reads import (
    assemble_snapshot,
    check_aggregate_rows,
    check_global_caps,
    check_logical_rows,
    enabled_names,
    fetch_record_row,
    fetch_revision_meta,
    fetch_revision_payload,
    plan_selection,
    revision_from_row,
    store_id_value,
    verified_record,
)
from guiskindose.equipment_profiles.store_schema import (
    MAX_LIST_LIMIT,
    SQLITE_INT_MAX,
    check_profile_id_text,
    new_store_id,
    normalize_db_error,
    normalize_selection,
    read_count,
    read_query_int,
    read_revision_number,
    schema_statements,
    store_error,
    table_names,
    verify_schema,
)
from guiskindose.equipment_profiles.store_types import (
    StoredRecord,
    StoredRevision,
    StoreSnapshot,
)

#: Name of the store file inside the user-owned GUISkinDose configuration area.
STORE_FILENAME = "equipment_profiles.sqlite3"

#: SQLite busy timeout, seconds.
_BUSY_TIMEOUT_SECONDS = 10.0

T = TypeVar("T")


def default_store_path() -> Path:
    """Return the default user-owned store path without creating or reading anything.

    Pure path computation in the existing ``~/.guiskindose`` configuration area (the same area as
    ``gui/window_prefs.py``): no directory is created, no file is touched, and no platform branch is needed.
    """
    return Path.home() / ".guiskindose" / STORE_FILENAME


def _validate_path(path: str | os.PathLike[str]) -> Path:
    """Validate a store path argument without touching the filesystem. Never echoes the path."""
    try:
        text = os.fspath(path)
    except TypeError:
        raise store_error(ProfileErrorCode.INVALID_TYPE) from None
    if not isinstance(text, str) or "\x00" in text:
        raise store_error(ProfileErrorCode.INVALID_TYPE) from None
    return Path(text)


class ProfileStore:
    """A transactional handle on one user-owned equipment-profile database.

    Constructing a handle performs no I/O. ``initialize()`` (or the ``open()`` classmethod) creates a fresh
    database or verifies an existing one. Every public method raises only value-free
    :class:`EquipmentProfileError`.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = _validate_path(path)
        self._connection: sqlite3.Connection | None = None

    @classmethod
    def open(cls, path: str | os.PathLike[str]) -> Self:
        """Construct a handle and initialize it in one explicit step."""
        store = cls(path)
        store.initialize()
        return store

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the database connection. Idempotent."""
        connection, self._connection = self._connection, None
        if connection is not None:
            with contextlib.suppress(sqlite3.Error):
                connection.close()

    @property
    def path(self) -> Path:
        """The database path this handle was constructed with. Never logged by this module."""
        return self._path

    # -- lifecycle ----------------------------------------------------------

    def initialize(self) -> None:
        """Create a fresh version-1 database or verify an existing one, without mutating a rejected one.

        Fresh empty databases are created only at the current schema version. A nonempty unversioned
        database, a future version, or a corrupt schema is rejected with a value-free error and the file is
        left exactly as found. Re-initializing a handle closes its previous connection first.
        """
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise store_error(ProfileErrorCode.STORE_UNAVAILABLE) from None
        try:
            connection = sqlite3.connect(
                str(self._path), timeout=_BUSY_TIMEOUT_SECONDS, isolation_level=None
            )
        except (OSError, ValueError, sqlite3.Error):
            raise store_error(ProfileErrorCode.STORE_UNAVAILABLE) from None
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            version = self._user_version(connection)
            tables = table_names(connection)
            if version == 0 and not tables:
                self._create_schema(connection)
            elif version == 0:
                raise store_error(ProfileErrorCode.STORE_CORRUPTION)
            elif version == 1:
                verify_schema(connection)
            else:
                raise store_error(ProfileErrorCode.UNSUPPORTED_STORE_VERSION)
        except EquipmentProfileError:
            connection.close()
            raise
        except sqlite3.Error as exc:
            connection.close()
            raise normalize_db_error(type(exc)) from None
        self.close()
        self._connection = connection

    def _user_version(self, connection: sqlite3.Connection) -> int:
        try:
            row = connection.execute("PRAGMA user_version").fetchone()
        except sqlite3.Error as exc:
            raise normalize_db_error(type(exc)) from None
        if row is None:
            raise store_error(ProfileErrorCode.STORE_CORRUPTION)
        return read_count(row[0], minimum=0)

    def _create_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in schema_statements():
                connection.execute(statement)
            connection.execute(
                "INSERT INTO store_meta(key, value) VALUES (?, ?)", ("store_schema_version", "1")
            )
            connection.execute(
                "INSERT INTO store_meta(key, value) VALUES (?, ?)", ("store_id", new_store_id())
            )
            connection.execute("PRAGMA user_version = 1")
            connection.execute("COMMIT")
        except BaseException:
            self._rollback_quietly(connection)
            raise

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise store_error(ProfileErrorCode.STORE_UNAVAILABLE)
        return self._connection

    # -- transactions -------------------------------------------------------

    def _guard_reentrancy(self, connection: sqlite3.Connection) -> None:
        """Refuse a nested or leaked transaction instead of stacking work onto it."""
        if connection.in_transaction:
            raise store_error(ProfileErrorCode.STORE_UNAVAILABLE)

    def _write(self, work: Callable[[sqlite3.Connection], T]) -> T:
        """Run ``work`` inside one ``BEGIN IMMEDIATE`` transaction, rolling back on any failure.

        ``EquipmentProfileError`` passes through untouched. ``sqlite3`` failures are normalized. *Any* other
        exception — including an unexpected one — rolls the transaction back, closes the handle so no leaked
        transaction can poison later calls, and normalizes to a closed error, except for cancellation, which
        is preserved: ``KeyboardInterrupt`` and ``SystemExit`` roll back, close, and re-raise unchanged.
        """
        connection = self._require_connection()
        self._guard_reentrancy(connection)
        try:
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise normalize_db_error(type(exc)) from None
        try:
            self._reverify(connection)
            result = work(connection)
        except EquipmentProfileError:
            self._rollback_quietly(connection)
            raise
        except sqlite3.Error as exc:
            self._rollback_quietly(connection)
            raise normalize_db_error(type(exc)) from None
        except (KeyboardInterrupt, SystemExit):
            self._rollback_quietly(connection)
            self.close()
            raise
        except BaseException:
            self._rollback_quietly(connection)
            self.close()
            raise store_error(ProfileErrorCode.STORE_CORRUPTION) from None
        try:
            connection.execute("COMMIT")
        except sqlite3.Error as exc:
            self._rollback_quietly(connection)
            raise normalize_db_error(type(exc)) from None
        return result

    def _reverify(self, connection: sqlite3.Connection) -> None:
        """Re-verify schema, foreign keys, and growth caps inside every transaction.

        External DDL tampering or direct row edits after initialization must fail closed on the next
        operation, not silently produce partial results. All checks are read-only single or bounded queries.
        """
        from guiskindose.equipment_profiles.store_reads import check_database_caps
        from guiskindose.equipment_profiles.store_schema import check_foreign_key_violations, verify_schema

        verify_schema(connection)
        check_foreign_key_violations(connection)
        check_database_caps(connection)

    def _rollback_quietly(self, connection: sqlite3.Connection) -> None:
        with contextlib.suppress(sqlite3.Error):
            connection.execute("ROLLBACK")

    def _read(self, work: Callable[[sqlite3.Connection], T]) -> T:
        """Run ``work`` inside one deferred read transaction, so a snapshot sees a single consistent state.

        A plain ``BEGIN`` (not ``IMMEDIATE``) is used deliberately: readers must not take the writer lock.
        Failure handling mirrors :meth:`_write`, including cancellation preservation.
        """
        connection = self._require_connection()
        self._guard_reentrancy(connection)
        try:
            connection.execute("BEGIN")
        except sqlite3.Error as exc:
            raise normalize_db_error(type(exc)) from None
        try:
            self._reverify(connection)
            result = work(connection)
        except EquipmentProfileError:
            self._rollback_quietly(connection)
            raise
        except sqlite3.Error as exc:
            self._rollback_quietly(connection)
            raise normalize_db_error(type(exc)) from None
        except (KeyboardInterrupt, SystemExit):
            self._rollback_quietly(connection)
            self.close()
            raise
        except BaseException:
            self._rollback_quietly(connection)
            self.close()
            raise store_error(ProfileErrorCode.STORE_CORRUPTION) from None
        try:
            connection.execute("COMMIT")
        except sqlite3.Error as exc:
            self._rollback_quietly(connection)
            raise normalize_db_error(type(exc)) from None
        return result

    # -- public reads -------------------------------------------------------

    def read_revision(self, profile_id: str, revision: int | None = None) -> StoredRevision:
        """Read one stored revision (the current revision when ``revision`` is None)."""
        name = check_profile_id_text(profile_id)
        wanted = (
            None
            if revision is None
            else read_query_int(revision, minimum=1, maximum=SQLITE_INT_MAX)
        )

        def work(connection: sqlite3.Connection) -> StoredRevision:
            record = fetch_record_row(connection, name)
            if record is None:
                raise store_error(ProfileErrorCode.STORE_NOT_FOUND)
            target = read_revision_number(record[2]) if wanted is None else wanted
            meta = fetch_revision_meta(connection, name, target)
            if meta is None:
                raise store_error(ProfileErrorCode.STORE_NOT_FOUND)
            from guiskindose.equipment_profiles.store_reads import check_payload_size

            check_payload_size(meta)
            payload_json, stored_hash, created_utc = fetch_revision_payload(connection, name, target)
            stored = revision_from_row(name, (target, payload_json, stored_hash, created_utc))
            check_logical_rows(meta, stored.profile)
            return stored

        return self._read(work)

    def list_records(self, limit: int = MAX_PROFILES, offset: int = 0) -> tuple[StoredRecord, ...]:
        """List stored record metadata ordered by exact ``profile_id``, with validated pagination.

        Each listed record's current revision payload and hash are verified, because every read
        revalidates.
        """
        limit = read_query_int(limit, minimum=0, maximum=MAX_LIST_LIMIT)
        offset = read_query_int(offset, minimum=0, maximum=SQLITE_INT_MAX)

        def work(connection: sqlite3.Connection) -> tuple[StoredRecord, ...]:
            try:
                rows = connection.execute(
                    "SELECT profile_id, enabled, current_revision, generation, updated_utc "
                    "FROM profile_records ORDER BY profile_id LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            except sqlite3.Error as exc:
                raise normalize_db_error(type(exc)) from None
            records: list[StoredRecord] = []
            for row in rows:
                records.append(verified_record(connection, row))
            return tuple(records)

        return self._read(work)

    def selected_snapshot(self, profile_ids: Sequence[str] | None = None) -> StoreSnapshot:
        """Load an immutable snapshot of the selected current revisions in one read transaction.

        With no selection, every enabled record is selected; an empty enabled store yields a valid empty
        snapshot. Bounds (at most 64 unique IDs, at most 10,000 aggregate logical rows) are checked before
        payloads are materialized where possible, and the canonical conflict check runs over the assembled
        profiles so an explicitly conflicting selection fails closed.
        """
        names = normalize_selection(profile_ids)

        def work(connection: sqlite3.Connection) -> StoreSnapshot:
            store_id = store_id_value(connection)
            selected_names = (
                [name for name, _rev in enabled_names(connection)] if names is None else list(names)
            )
            if len(selected_names) > MAX_PROFILES:
                raise store_error(ProfileErrorCode.PROFILE_LIMIT_EXCEEDED, count=len(selected_names))
            check_global_caps(connection, selected_names)
            planned = plan_selection(connection, selected_names)
            check_aggregate_rows(sum(rows for _name, _rev, rows in planned))
            return assemble_snapshot(connection, store_id, planned)

        return self._read(work)

    # -- public writes (implemented in store_writes; thin wrappers keep the public surface here) --

    def save_new_revision(
        self, profile: Profile, *, expected_current_revision: int | None = None
    ) -> StoredRecord:
        """Save ``profile`` as a new immutable revision; see :mod:`store_writes` for the contract."""
        from guiskindose.equipment_profiles import store_writes

        return store_writes.save_new_revision(
            self, profile, expected_current_revision=expected_current_revision
        )

    def set_enabled(
        self, profile_id: str, enabled: bool, *, expected_current_revision: int | None = None, expected_generation: int | None = None
    ) -> StoredRecord:
        """Enable or disable one record; see :mod:`store_writes` for the contract."""
        from guiskindose.equipment_profiles import store_writes

        return store_writes.set_enabled(
            self, profile_id, enabled, expected_current_revision=expected_current_revision, expected_generation=expected_generation
        )

    def delete_record(self, profile_id: str, *, expected_current_revision: int | None = None, expected_generation: int | None = None) -> None:
        """Delete one record and its revisions; see :mod:`store_writes` for the contract."""
        from guiskindose.equipment_profiles import store_writes

        store_writes.delete_record(
            self, profile_id, expected_current_revision=expected_current_revision, expected_generation=expected_generation
        )
