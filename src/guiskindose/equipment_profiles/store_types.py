"""Immutable store metadata, revision, and snapshot types for the local user profile store.

Every type is a frozen dataclass holding only tuples, scalars, and other frozen models: no list, dict, or set is
exposed, so a loaded record cannot be mutated by a caller and no mutable payload leaks in. The generated
``repr`` is suppressed wherever a field holds profile-local free text (the canonical payload), because that
text must not reach logs or diagnostics through a repr. Record and revision *identifiers* — profile IDs,
revision numbers, hashes, counts — are ordinary audit data and may appear in diagnostics.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from guiskindose.equipment_profiles.canonical import canonical_json_bytes
from guiskindose.equipment_profiles.constants import SCHEMA_VERSION, SOURCE_KIND_STORE
from guiskindose.equipment_profiles.models import Profile

#: Version of the store metadata envelope itself. Written to ``PRAGMA user_version`` and to
#: ``store_meta.store_schema_version``. Fresh databases are created only at this version.
STORE_SCHEMA_VERSION = 1

#: Source kind carried by every snapshot and every store failure.
STORE_SOURCE_KIND = SOURCE_KIND_STORE


@dataclass(frozen=True, slots=True)
class StoredRecord:
    """One stored profile's metadata: identity, enablement, and revision pointer.

    This carries no profile content — only identifiers, flags, counts, and hashes — so it is safe for
    listings and diagnostics.
    """

    profile_id: str
    enabled: bool
    current_revision: int
    generation: int
    profile_hash: str
    updated_utc: str


@dataclass(frozen=True, slots=True, repr=False)
class StoredRevision:
    """One immutable stored revision: the validated profile, its canonical payload, and its provenance.

    ``profile_hash`` covers the profile content and its provenance (§7 of the contract) and excludes the
    store ID, revision number, timestamps, and enablement. ``repr`` shows identifiers only; the payload text
    and any free text inside ``profile`` are suppressed.
    """

    profile_id: str
    revision: int
    profile: Profile
    profile_hash: str
    payload_json: str
    created_utc: str

    def __repr__(self) -> str:
        return (
            f"StoredRevision(profile_id={self.profile_id!r}, revision={self.revision}, "
            f"profile_hash={self.profile_hash!r}, created_utc={self.created_utc!r})"
        )


@dataclass(frozen=True, slots=True)
class SelectedRevision:
    """One revision selected into a snapshot: identity, revision, and the content hash at selection time."""

    profile_id: str
    revision: int
    profile_hash: str


@dataclass(frozen=True, slots=True)
class StoreSnapshot:
    """An immutable, self-contained snapshot of selected store revisions.

    Built inside a single read transaction before any mutable data escapes. ``source_hash`` is the locked
    selected-revision-set hash: it covers the store schema version, the opaque store ID, and the sorted
    selected ``{profile_id, revision, profile_hash}`` records — never filenames, paths, timestamps, or
    enablement. Suitable as the input to a later activation step.
    """

    store_id: str
    source_kind: str
    selected: tuple[SelectedRevision, ...]
    profiles: tuple[Profile, ...]
    source_hash: str
    logical_rows: int

    def __len__(self) -> int:
        return len(self.profiles)


def store_source_hash(
    store_id: str, selected: Sequence[SelectedRevision]
) -> str:
    """Compute the locked selected-revision-set hash for a store and its selection.

    The wrapper is ``{"schema_version": 1, "store_schema_version": 1, "store_id": …,
    "records": [{profile_id, revision, profile_hash} …]}`` with records ordered by exact ``profile_id``.
    Deterministic: the same store and selection always produce the same hash.
    """
    records = [
        {"profile_id": item.profile_id, "revision": item.revision, "profile_hash": item.profile_hash}
        for item in sorted(selected, key=lambda item: item.profile_id)
    ]
    wrapper = {
        "schema_version": SCHEMA_VERSION,
        "store_schema_version": STORE_SCHEMA_VERSION,
        "store_id": store_id,
        "records": records,
    }
    return hashlib.sha256(canonical_json_bytes(wrapper)).hexdigest()
