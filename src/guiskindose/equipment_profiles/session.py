"""Frozen multi-source equipment-profile session (import-before-load assembly).

Combines validated profiles from file byte snapshots (JSON/CSV/TSV/XLSX),
in-memory documents, and store snapshots into one immutable, conflict-checked,
capability-gated session with a compiled custom index prepared once for
per-exam resolution. Files are read once at assembly — later mutation cannot
alter the session — and store snapshots arrive frozen, so the session never
opens a database. No application wiring reads this module yet.

Request collections are bounded before copying (declared lengths first, then
bounded iteration), and profile/row ceilings accrue incrementally while
loading: assembly stops before reading the next source once exceeded.
Published payload and provenance sort canonically (profiles by exact ID;
sources by kind, format, hash, and IDs), so reordered inputs assemble equal
sessions; input order affects diagnostics only. Path handling follows SPEC §8:
relative paths resolve against the working directory by default, or against
an explicit caller settings base directory; the process directory is never
changed and paths never enter errors, warnings, provenance, or reprs.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from guiskindose.equipment_profiles.canonical import active_set_hash, profile_hash
from guiskindose.equipment_profiles.capability import check_initial_capabilities
from guiskindose.equipment_profiles.conflicts import validate_profile_set
from guiskindose.equipment_profiles.constants import (
    JSON_SOURCE_SUFFIXES,
    MAX_AGGREGATE_ROWS,
    MAX_PROFILES,
    MAX_REVISION,
    MAX_SOURCES,
    SOURCE_KIND_CSV,
    SOURCE_KIND_JSON,
    SOURCE_KIND_MEMORY,
    SOURCE_KIND_STORE,
    SOURCE_KIND_TSV,
    SOURCE_KIND_XLSX,
    TABULAR_SUFFIX_TO_KIND,
    XLSX_SOURCE_SUFFIXES,
)
from guiskindose.equipment_profiles.csv_source import parse_csv_file
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.equipment_profiles.indexes import IndexedProfile, ProfileIndexes, build_profile_indexes
from guiskindose.equipment_profiles.json_source import ParsedDocument, parse_json_file, parse_memory_document
from guiskindose.equipment_profiles.models import Profile
from guiskindose.equipment_profiles.preparation import (
    PreparedBundledContext,
    PreparedCustomContext,
    prepare_bundled_context,
    prepare_custom_context,
)
from guiskindose.equipment_profiles.resolver import BundledCoordinateSet, CoordinateResolution, resolve_with_prepared
from guiskindose.equipment_profiles.store_types import SelectedRevision, StoreSnapshot, store_source_hash
from guiskindose.equipment_profiles.tsv_source import parse_tsv_file
from guiskindose.equipment_profiles.xlsx_source import parse_xlsx_file

__all__ = [
    "EquipmentProfileSession",
    "FileSource",
    "SessionProvenance",
    "SessionSourceProvenance",
    "assemble_session",
]

#: Adapter kinds a file source may name explicitly.
_FILE_FORMATS = (SOURCE_KIND_JSON, SOURCE_KIND_CSV, SOURCE_KIND_TSV, SOURCE_KIND_XLSX)

#: Suffix routing for file sources without an explicit format.
_FORMAT_BY_SUFFIX: dict[str, str] = {
    **dict.fromkeys(JSON_SOURCE_SUFFIXES, SOURCE_KIND_JSON),
    **dict(TABULAR_SUFFIX_TO_KIND),
    **dict.fromkeys(XLSX_SOURCE_SUFFIXES, SOURCE_KIND_XLSX),
}

#: Lowercase hex digests: 32 for store IDs, 64 for content hashes.
_HEX_32_RE = re.compile(r"\A[0-9a-f]{32}\Z")
_HEX_64_RE = re.compile(r"\A[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True, repr=False)
class FileSource:
    """One local profile file to snapshot at assembly.

    ``format`` optionally pins the adapter (``json``/``csv``/``tsv``/``xlsx``);
    without it the file suffix routes. ``sheet`` is the zero-based XLSX sheet
    index (``None`` reads the first sheet) and is rejected on other formats.
    The path never appears in errors, provenance, or reprs; the repr shows
    validated values only, so unvalidated sentinels render as ``None``.
    """

    path: str | os.PathLike[str]
    format: str | None = None
    sheet: int | None = None

    def __repr__(self) -> str:
        source_format = self.format if type(self.format) is str and self.format in _FILE_FORMATS else None
        sheet = self.sheet if type(self.sheet) is int and self.sheet >= 0 else None
        return f"FileSource(format={source_format!r}, sheet={sheet!r})"


@dataclass(frozen=True, slots=True)
class SessionSourceProvenance:
    """Default-safe audit record for one assembled source.

    ``kind`` is ``file``/``memory``/``store``; ``format`` names the file
    adapter kind or is ``None``. ``source_hash`` is the exact file-bytes hash,
    ``None`` for memory, or the locked store selection-set hash. Only
    identifiers, hashes, and counts — never paths, notes, raw text, station,
    or serial values.
    """

    kind: str
    format: str | None
    source_hash: str | None
    profile_ids: tuple[str, ...]
    revisions: tuple[tuple[str, int], ...]
    profile_count: int
    logical_rows: int


@dataclass(frozen=True, slots=True)
class SessionProvenance:
    """Default-safe audit record for the whole session assembly."""

    sources: tuple[SessionSourceProvenance, ...]
    total_profiles: int
    total_rows: int
    active_set_hash: str


@dataclass(frozen=True, slots=True)
class _SourceBatch:
    """One loaded source pending combination: profiles plus audit counters."""

    kind: str
    format: str | None
    lead_kind: str
    source_hash: str | None
    profile_ids: tuple[str, ...]
    revisions: tuple[tuple[str, int], ...]
    profiles: tuple[Profile, ...]
    logical_rows: int


@dataclass(frozen=True, slots=True, repr=False)
class EquipmentProfileSession:
    """One immutable assembled custom-profile session.

    ``profiles`` are the compiler's canonical output in exact profile-ID
    order — never caller-owned objects; ``prepared`` is the custom index
    prepared once for per-exam resolution. :meth:`resolve` answers exams
    without recompiling, revalidating, re-reading, or sharing mutable caches.
    """

    profiles: tuple[Profile, ...]
    prepared: PreparedCustomContext
    provenance: SessionProvenance
    active_set_hash: str

    @property
    def custom(self) -> ProfileIndexes:
        """The session's compiled custom index (== the prepared table)."""
        return self.prepared.index

    def resolve(
        self, identity: Any, bundled: BundledCoordinateSet | PreparedBundledContext
    ) -> CoordinateResolution:
        """Resolve one exam against a bundled set without recompiling custom.

        ``bundled`` accepts a compiled set (prepared per call) or an already
        prepared bundled context (zero per-exam preparation). Anything else
        fails closed.
        """
        if isinstance(bundled, PreparedBundledContext):
            prepared_bundled = bundled
        elif isinstance(bundled, BundledCoordinateSet):
            prepared_bundled = prepare_bundled_context(bundled)
        else:
            raise EquipmentProfileError(
                ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("bundled",)
            )
        return resolve_with_prepared(identity=identity, custom=self.prepared, bundled=prepared_bundled)

    def __repr__(self) -> str:
        return (
            f"EquipmentProfileSession(profiles={len(self.profiles)}, "
            f"sources={len(self.provenance.sources)}, active_set_hash={self.active_set_hash!r})"
        )


def _materialize_requests(value: Any, owner: str) -> list[Any]:
    """Copy one request collection under the shared source ceiling.

    The declared length is checked before any traversal or copy, then
    iteration re-checks the cap item by item so an inaccurate length cannot
    force unbounded work.
    """
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=(owner,))
    try:
        declared = len(value)
    except TypeError:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=(owner,)
        ) from None
    if declared > MAX_SOURCES:
        raise EquipmentProfileError(
            ProfileErrorCode.PROFILE_LIMIT_EXCEEDED, source_kind="memory", field_path=(owner,), count=declared
        )
    requests: list[Any] = []
    for item in value:
        requests.append(item)
        if len(requests) > MAX_SOURCES:
            raise EquipmentProfileError(
                ProfileErrorCode.PROFILE_LIMIT_EXCEEDED,
                source_kind="memory",
                field_path=(owner,),
                count=len(requests),
            )
    return requests


def _check_base_dir(value: Any) -> Path | None:
    """Validate the optional settings base directory without touching the filesystem."""
    if value is None:
        return None
    if not isinstance(value, (str, os.PathLike)):
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("settings_base_dir",)
        )
    return Path(_coerce_path_text(value, owner="settings_base_dir"))


def _coerce_path_text(value: Any, owner: str = "path") -> str:
    """Coerce a request path to text behind a closed boundary.

    A hostile ``os.PathLike`` may return bytes or raise arbitrary errors from
    ``__fspath__``; all of that collapses to a value-free error with the cause
    suppressed, so no raw message can leak. Bytes paths are rejected: the
    adapters are text-path oriented and surrogates must never reach errors.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, os.PathLike):
        try:
            text = os.fspath(value)
        except Exception:
            raise EquipmentProfileError(
                ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=(owner,)
            ) from None
        if isinstance(text, str):
            return text
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=(owner,)
        ) from None
    raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=(owner,))


def _resolve_format(request: FileSource, suffix: str) -> str:
    """The adapter kind for one file request: explicit format, else suffix routing."""
    if request.format is None:
        routed = _FORMAT_BY_SUFFIX.get(suffix.lower())
        if routed is None:
            raise EquipmentProfileError(
                ProfileErrorCode.UNSUPPORTED_SOURCE_SUFFIX, source_kind="memory", field_path=()
            )
        return routed
    if type(request.format) is not str or request.format not in _FILE_FORMATS:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_ENUM, source_kind="memory", field_path=("format",)
        )
    return request.format


def _check_file_request(request: Any) -> FileSource:
    """Validate one file request's shape; the path text is coerced separately."""
    if not isinstance(request, FileSource):
        raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("files",))
    _coerce_path_text(request.path)
    if request.sheet is not None and (type(request.sheet) is not int or request.sheet < 0):
        raise EquipmentProfileError(
            ProfileErrorCode.VALUE_OUT_OF_RANGE, source_kind="memory", field_path=("sheet",)
        )
    return request


def _resolve_request_path(raw: str, base: Path | None) -> Path:
    """Resolve coerced request text against the base directory or working directory.

    Absolute paths pass through untouched; the process directory is never changed.
    """
    candidate = Path(raw)
    if candidate.is_absolute() or base is None:
        return candidate
    return base / candidate


def _parse_file_source(resolved: Path, source_format: str, sheet: int | None) -> ParsedDocument:
    """Parse one resolved file with its adapter; the path never enters an error."""
    if source_format == SOURCE_KIND_JSON:
        return parse_json_file(str(resolved))
    if source_format == SOURCE_KIND_CSV:
        return parse_csv_file(str(resolved))
    if source_format == SOURCE_KIND_TSV:
        return parse_tsv_file(str(resolved))
    return parse_xlsx_file(str(resolved), sheet=sheet)


def _load_file_source(request: FileSource, base: Path | None) -> _SourceBatch:
    """Snapshot one file's bytes through its adapter into an immutable batch."""
    checked = _check_file_request(request)
    text = _coerce_path_text(checked.path)
    source_format = _resolve_format(checked, Path(text).suffix)
    if checked.sheet is not None and source_format != SOURCE_KIND_XLSX:
        raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("sheet",))
    document = _parse_file_source(_resolve_request_path(text, base), source_format, checked.sheet)
    return _SourceBatch(
        kind="file",
        format=source_format,
        lead_kind=source_format,
        source_hash=document.source_hash,
        profile_ids=tuple(profile.profile_id for profile in document.profiles),
        revisions=(),
        profiles=document.profiles,
        logical_rows=document.logical_rows,
    )


def _load_memory_document(raw: Any) -> _SourceBatch:
    """Validate one in-memory document into an immutable batch (no source hash)."""
    document = parse_memory_document(raw)
    return _SourceBatch(
        kind="memory",
        format=None,
        lead_kind=SOURCE_KIND_MEMORY,
        source_hash=None,
        profile_ids=tuple(profile.profile_id for profile in document.profiles),
        revisions=(),
        profiles=document.profiles,
        logical_rows=document.logical_rows,
    )


def _check_hex(text: Any, length: int, field_path: tuple[str, ...]) -> str:
    """Gate a lowercase hex digest shape without echoing the value."""
    pattern = _HEX_32_RE if length == 32 else _HEX_64_RE
    if type(text) is not str or pattern.match(text) is None:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=field_path
        )
    return text


def _check_snapshot_shape(snapshot: Any) -> None:
    """Gate snapshot envelope shape: store type, kind, tuple bodies, and bounds.

    Runs before any traversal so malformed or oversized selections fail
    without per-item work.
    """
    if not isinstance(snapshot, StoreSnapshot):
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("snapshots",)
        )
    if type(snapshot.source_kind) is not str or snapshot.source_kind != SOURCE_KIND_STORE:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_ENUM, source_kind="memory", field_path=("snapshots",)
        )
    if type(snapshot.selected) is not tuple or type(snapshot.profiles) is not tuple:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("snapshots",)
        )
    if len(snapshot.selected) > MAX_PROFILES or len(snapshot.profiles) > MAX_PROFILES:
        raise EquipmentProfileError(
            ProfileErrorCode.PROFILE_LIMIT_EXCEEDED, source_kind="memory", field_path=("snapshots",)
        )
    if len(snapshot.selected) != len(snapshot.profiles):
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("snapshots",)
        )
    _check_hex(snapshot.store_id, 32, ("snapshots", "store_id"))
    _check_hex(snapshot.source_hash, 64, ("snapshots", "source_hash"))


def _check_snapshot_records(snapshot: StoreSnapshot) -> tuple[tuple[tuple[str, int], ...], int, tuple[Profile, ...]]:
    """Re-verify one snapshot's records against content, bounded.

    Each selected record must pair a real revision with its profile: matching
    IDs, in-range revisions, well-shaped hashes, and content equal to the
    claimed hash. The locked wrapper hash and the row counter are recomputed
    and compared. Disagreements report conflicting metadata, like stale
    compile-time claims.
    """
    revisions: list[tuple[str, int]] = []
    entries: list[IndexedProfile] = []
    for selected, profile in zip(snapshot.selected, snapshot.profiles, strict=True):
        if not isinstance(selected, SelectedRevision) or not isinstance(profile, Profile):
            raise EquipmentProfileError(
                ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("snapshots",)
            )
        if type(selected.profile_id) is not str or selected.profile_id != profile.profile_id:
            raise EquipmentProfileError(
                ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("snapshots",)
            )
        if type(selected.revision) is not int or not 1 <= selected.revision <= MAX_REVISION:
            raise EquipmentProfileError(
                ProfileErrorCode.VALUE_OUT_OF_RANGE, source_kind="memory", field_path=("revision",)
            )
        selected_hash = _check_hex(selected.profile_hash, 64, ("snapshots", "profile_hash"))
        entries.append(IndexedProfile(profile, SOURCE_KIND_STORE, selected.revision, selected_hash))
        revisions.append((selected.profile_id, selected.revision))
    compiled = build_profile_indexes(entries)
    canonical_profiles = tuple(entry.profile for entry in compiled.profiles)
    by_id = {profile.profile_id: profile for profile in canonical_profiles}
    aligned_profiles = tuple(by_id[selected.profile_id] for selected in snapshot.selected)
    bounded_rows = sum(profile.logical_row_count() for profile in canonical_profiles)
    if store_source_hash(snapshot.store_id, snapshot.selected) != snapshot.source_hash:
        raise EquipmentProfileError(
            ProfileErrorCode.CONFLICTING_PROFILE_METADATA,
            source_kind=SOURCE_KIND_STORE,
            field_path=("source_hash",),
        )
    if type(snapshot.logical_rows) is not int or snapshot.logical_rows != bounded_rows:
        raise EquipmentProfileError(
            ProfileErrorCode.CONFLICTING_PROFILE_METADATA,
            source_kind=SOURCE_KIND_STORE,
            field_path=("logical_rows",),
        )
    return tuple(revisions), bounded_rows, aligned_profiles


def _load_snapshot(snapshot: Any) -> _SourceBatch:
    """Project one store snapshot's aligned selection into an immutable batch.

    Shape gates run before traversal; records re-verify against content with
    bounded counting. Content hashes and conflicts are re-verified downstream
    by index compilation.
    """
    _check_snapshot_shape(snapshot)
    assert isinstance(snapshot, StoreSnapshot)
    revisions, bounded_rows, canonical_profiles = _check_snapshot_records(snapshot)
    return _SourceBatch(
        kind="store",
        format=None,
        lead_kind=SOURCE_KIND_STORE,
        source_hash=snapshot.source_hash,
        profile_ids=tuple(selected.profile_id for selected in snapshot.selected),
        revisions=revisions,
        profiles=canonical_profiles,
        logical_rows=bounded_rows,
    )


def _request_lead_kind(
    file_requests: Sequence[FileSource], documents: Sequence[Any], snapshots: Sequence[Any]
) -> str:
    """First determinable source kind in input order, for diagnostics only."""
    for request in file_requests:
        if isinstance(request, FileSource):
            if type(request.format) is str and request.format in _FILE_FORMATS:
                return request.format
            try:
                suffix = Path(_coerce_path_text(request.path)).suffix.lower()
            except EquipmentProfileError:
                continue
            routed = _FORMAT_BY_SUFFIX.get(suffix)
            if routed is not None:
                return routed
    if documents:
        return SOURCE_KIND_MEMORY
    if snapshots:
        return SOURCE_KIND_STORE
    return SOURCE_KIND_MEMORY


def _accumulate(
    batch: _SourceBatch, totals: tuple[int, int], lead_kind: str
) -> tuple[int, int]:
    """Add one batch to the running ceilings, failing before the next source loads."""
    total_profiles = totals[0] + len(batch.profiles)
    if total_profiles > MAX_PROFILES:
        raise EquipmentProfileError(
            ProfileErrorCode.PROFILE_LIMIT_EXCEEDED, source_kind=lead_kind, count=total_profiles
        )
    total_rows = totals[1] + batch.logical_rows
    if total_rows > MAX_AGGREGATE_ROWS:
        raise EquipmentProfileError(
            ProfileErrorCode.ROW_LIMIT_EXCEEDED, source_kind=lead_kind, count=total_rows
        )
    return total_profiles, total_rows


def _source_sort_key(source: SessionSourceProvenance) -> tuple[str, str, str, tuple[str, ...]]:
    """Canonical source order: kind, format, hash, then IDs."""
    return (source.kind, source.format or "", source.source_hash or "", source.profile_ids)


def _session_provenance(
    batches: Sequence[_SourceBatch], active_hash: str
) -> SessionProvenance:
    """Assemble default-safe provenance with canonically ordered source records."""
    sources = tuple(
        sorted(
            (
                SessionSourceProvenance(
                    kind=batch.kind,
                    format=batch.format,
                    source_hash=batch.source_hash,
                    profile_ids=batch.profile_ids,
                    revisions=batch.revisions,
                    profile_count=len(batch.profiles),
                    logical_rows=batch.logical_rows,
                )
                for batch in batches
            ),
            key=_source_sort_key,
        )
    )
    return SessionProvenance(
        sources=sources,
        total_profiles=sum(source.profile_count for source in sources),
        total_rows=sum(source.logical_rows for source in sources),
        active_set_hash=active_hash,
    )


def assemble_session(
    *,
    files: Sequence[FileSource] = (),
    documents: Sequence[Any] = (),
    snapshots: Sequence[StoreSnapshot] = (),
    settings_base_dir: str | os.PathLike[str] | None = None,
) -> EquipmentProfileSession:
    """Assemble a frozen multi-source custom-profile session.

    Request counts are bounded before any loading; profile/row ceilings accrue
    incrementally while loading, stopping before the next source once exceeded.
    Then canonical conflicts and the capability gate run across all kinds
    before anything is published — a failure publishes nothing, so any prior
    session object is unaffected. An explicitly empty selection yields a valid
    empty custom session. Published profiles are the compiler's canonical
    output in exact ID order (never caller-owned objects); provenance sources
    sort canonically while input order affects diagnostics only. Raises
    value-free errors throughout.
    """
    base = _check_base_dir(settings_base_dir)
    file_requests = _materialize_requests(files, "files")
    document_requests = _materialize_requests(documents, "documents")
    snapshot_requests = _materialize_requests(snapshots, "snapshots")
    lead_kind = _request_lead_kind(file_requests, document_requests, snapshot_requests)
    if len(file_requests) + len(document_requests) + len(snapshot_requests) > MAX_SOURCES:
        raise EquipmentProfileError(
            ProfileErrorCode.PROFILE_LIMIT_EXCEEDED,
            source_kind=lead_kind,
            count=len(file_requests) + len(document_requests) + len(snapshot_requests),
        )
    batches: list[_SourceBatch] = []
    totals = (0, 0)
    for request in file_requests:
        batch = _load_file_source(request, base)
        totals = _accumulate(batch, totals, lead_kind)
        batches.append(batch)
    for raw in document_requests:
        batch = _load_memory_document(raw)
        totals = _accumulate(batch, totals, lead_kind)
        batches.append(batch)
    for snapshot in snapshot_requests:
        batch = _load_snapshot(snapshot)
        totals = _accumulate(batch, totals, lead_kind)
        batches.append(batch)
    combined: list[Profile] = []
    for batch in batches:
        combined.extend(batch.profiles)
    validate_profile_set(tuple(combined), source_kind=lead_kind)
    check_initial_capabilities(tuple(combined), source_kind=lead_kind)
    entries = [
        IndexedProfile(
            profile=profile,
            source_kind=batch.lead_kind,
            revision=batch.revisions[position][1] if batch.kind == "store" else None,
            profile_hash=profile_hash(profile),
        )
        for batch in batches
        for position, profile in enumerate(batch.profiles)
    ]
    custom = build_profile_indexes(entries)
    active_hash = active_set_hash(tuple(entry.profile for entry in custom.profiles))
    return EquipmentProfileSession(
        profiles=tuple(entry.profile for entry in custom.profiles),
        prepared=prepare_custom_context(custom),
        provenance=_session_provenance(batches, active_hash),
        active_set_hash=active_hash,
    )
