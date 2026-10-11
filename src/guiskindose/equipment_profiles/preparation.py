"""Once-per-session preparation boundary for coordinate resolution.

Validates compiled custom indexes and bundled sets a single time — entry
context, structural shape, recomputed content hashes, and compiler-derived
claim tables — so per-exam resolution rebuilds only lookup maps without
recompiling, revalidating, or reading files and stores. Prepared contexts are
frozen tuples-only values validated in ``__post_init__``; hand-built or
corrupted inputs fail closed at construction or preparation, never at resolve
time. See :mod:`guiskindose.equipment_profiles.resolver` for the ladder that
consumes these contexts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from guiskindose.equipment_profiles.bundled import BundledCoordinateSet
from guiskindose.equipment_profiles.capability import check_initial_capabilities
from guiskindose.equipment_profiles.constants import (
    MAX_ALIASES,
    MAX_MODELS,
    MAX_PROFILES,
    MAX_REVISION,
    MAX_TRANSMISSION_ROWS,
    SOURCE_KINDS,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.equipment_profiles.indexes import (
    CoordinateClaim,
    CoordinateIndex,
    IndexedProfile,
    ProfileIndexes,
    build_profile_indexes,
)
from guiskindose.equipment_profiles.models import (
    Coordinates,
    Profile,
    Provenance,
    RotationDirection,
    TranslationDirection,
    TranslationOffset,
    TransmissionRow,
    coordinate_leaf_values,
)

__all__ = [
    "PreparedBundledContext",
    "PreparedCustomContext",
    "prepare_bundled_context",
    "prepare_custom_context",
]


def _reject_shape(source_kind: str, field_path: tuple[str, ...]) -> None:
    """Raise for a wrong-shaped compiled container; callers never see raw state."""
    raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind=source_kind, field_path=field_path)


def _check_text_field(value: Any, source_kind: str, field_path: tuple[str, ...]) -> None:
    """Gate a structural string field: exactly ``str``."""
    if type(value) is not str:
        _reject_shape(source_kind, field_path)


def _check_str_tuple(values: Any, source_kind: str, field_path: tuple[str, ...]) -> None:
    """Gate a structural string collection: a tuple of strings, never a list."""
    if type(values) is not tuple:
        _reject_shape(source_kind, field_path)
    for item in values:
        if type(item) is not str:
            _reject_shape(source_kind, field_path)


def _check_alias_pairs(pairs: Any, source_kind: str) -> None:
    """Gate structural model aliases: a tuple of ``(alias, target)`` string pairs."""
    if type(pairs) is not tuple:
        _reject_shape(source_kind, ("model_aliases",))
    for pair in pairs:
        if (
            type(pair) is not tuple
            or len(pair) != 2
            or type(pair[0]) is not str
            or type(pair[1]) is not str
        ):
            _reject_shape(source_kind, ("model_aliases",))


def _check_coordinate_blocks(coordinates: Coordinates, source_kind: str) -> None:
    """Gate structural coordinate block types, then every leaf value type."""
    if coordinates.translation_offset is not None and not isinstance(
        coordinates.translation_offset, TranslationOffset
    ):
        _reject_shape(source_kind, ("coordinates", "translation_offset"))
    if coordinates.translation_direction is not None and not isinstance(
        coordinates.translation_direction, TranslationDirection
    ):
        _reject_shape(source_kind, ("coordinates", "translation_direction"))
    if coordinates.rotation_direction is not None and not isinstance(
        coordinates.rotation_direction, RotationDirection
    ):
        _reject_shape(source_kind, ("coordinates", "rotation_direction"))
    _check_leaf_types(coordinates, source_kind)


def _check_leaf_types(coordinates: Coordinates, source_kind: str) -> None:
    """Gate structural leaf value types: exact floats, signs, and flags.

    Canonical profiles validated through the boundary always carry floats for
    numbers (never ints or booleans), strings for signs and modes, and exact
    booleans for the swap switch. Anything else is not a compiled profile.
    """
    for path, value in coordinate_leaf_values(coordinates):
        block, _, name = path.partition(".")
        field_path = (block, name or block)
        if path == "swap_lateral_longitudinal":
            if type(value) is not bool:
                _reject_shape(source_kind, field_path)
        elif block in ("translation_offset", "detector_side_length"):
            if type(value) is not float:
                _reject_shape(source_kind, field_path)
        elif not isinstance(value, str):
            _reject_shape(source_kind, field_path)


def _check_bounded_collections(profile: Profile, source_kind: str) -> None:
    """Gate structural collection bounds: exact tuples within their ceilings."""
    for values in (
        profile.models,
        profile.manufacturer_aliases,
        profile.model_aliases,
        profile.transmission,
    ):
        if type(values) is not tuple:
            _reject_shape(source_kind, ("profile",))
    if (
        len(profile.models) > MAX_MODELS
        or len(profile.manufacturer_aliases) > MAX_ALIASES
        or len(profile.model_aliases) > MAX_ALIASES
        or len(profile.transmission) > MAX_TRANSMISSION_ROWS
    ):
        _reject_shape(source_kind, ("profile",))
def _check_identity_fields(profile: Profile, source_kind: str) -> None:
    """Gate structural identity fields: texts, string tuples, and alias pairs."""
    _check_text_field(profile.profile_id, source_kind, ("profile_id",))
    _check_text_field(profile.manufacturer, source_kind, ("manufacturer",))
    _check_str_tuple(profile.models, source_kind, ("models",))
    _check_str_tuple(profile.manufacturer_aliases, source_kind, ("manufacturer_aliases",))
    _check_alias_pairs(profile.model_aliases, source_kind)


def _check_domain_fields(profile: Profile, source_kind: str) -> None:
    """Gate structural domain fields: provenance, coordinates, rows, and flag."""
    provenance = profile.provenance
    if provenance is not None and not isinstance(provenance, Provenance):
        _reject_shape(source_kind, ("provenance",))
    coordinates = profile.coordinates
    if coordinates is not None:
        if not isinstance(coordinates, Coordinates):
            _reject_shape(source_kind, ("coordinates",))
        else:
            _check_coordinate_blocks(coordinates, source_kind)
    rows = profile.transmission
    if type(rows) is not tuple:
        _reject_shape(source_kind, ("transmission",))
    else:
        for row in rows:
            if not isinstance(row, TransmissionRow):
                _reject_shape(source_kind, ("transmission",))
    if type(profile.promote_coordinate_wildcard) is not bool:
        _reject_shape(source_kind, ("promote_coordinate_wildcard",))


def _check_profile_containers(profile: Profile, source_kind: str) -> None:
    """Gate one profile's structural shape: exact immutable containers and types.

    Ranges and vocabularies are compile-time business; this only ensures the
    object the resolver walks is shaped like a canonical profile, so no raw
    ``KeyError``/``AttributeError``/``TypeError`` can escape a hand-built
    input. Mutable lists where tuples belong fail here.
    """
    _check_bounded_collections(profile, source_kind)
    _check_identity_fields(profile, source_kind)
    _check_domain_fields(profile, source_kind)


def _gate_custom_entries(entries: tuple[IndexedProfile, ...]) -> None:
    """Run the initial capability gate over every custom profile with its own kind.

    Alias-, wildcard-, promotion-, and transmission-bearing custom profiles
    fail ``unsupported_profile_capability`` here — never silently ignored, and
    never partially applied. Bundled entries are not gated: built-in aliases
    and the wildcard ladder belong to the bundled layer.
    """
    for entry in entries:
        check_initial_capabilities((entry.profile,), source_kind=entry.source_kind)


#: Claimed content hashes are lowercase SHA-256 hex digests, like every hash here.
_HEX_64_RE = re.compile(r"\A[0-9a-f]{64}\Z")


def _check_entry_context(entry: Any, owner: str) -> IndexedProfile:
    """Validate one compiled entry's source context with closed errors.

    Mirrors the index layer's entry check (exact-``str`` source kind in
    vocabulary, exact-``int`` revision in range, lowercase-64-hex hash, real
    profile): the resolver never trusts a hand-built context. Paths carry the
    ``custom``/``bundled`` owner for diagnostics.
    """
    if not isinstance(entry, IndexedProfile):
        raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=(owner,))
    kind = entry.source_kind
    if type(kind) is not str or kind not in SOURCE_KINDS:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_ENUM, source_kind="memory", field_path=(owner, "source_kind")
        )
    revision = entry.revision
    if revision is not None and (
        type(revision) is not int or not 1 <= revision <= MAX_REVISION
    ):
        raise EquipmentProfileError(
            ProfileErrorCode.VALUE_OUT_OF_RANGE, source_kind=kind, field_path=(owner, "revision")
        )
    claimed = entry.profile_hash
    if type(claimed) is not str or _HEX_64_RE.match(claimed) is None:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind=kind, field_path=(owner, "profile_hash")
        )
    if not isinstance(entry.profile, Profile):
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind=kind, field_path=(owner, "profile")
        )
    return entry


def _prepare_entry(entry: Any, owner: str) -> IndexedProfile:
    """Validate one compiled entry's context, structure, and claimed hash, once.

    Recomputes the canonical hash: a corrupted hash fails
    ``conflicting_profile_metadata``, exactly like a stale compile-time claim.
    """
    checked = _check_entry_context(entry, owner)
    _check_profile_containers(checked.profile, checked.source_kind)
    return build_profile_indexes((checked,)).profiles[0]


def _prepare_claims(
    table: CoordinateIndex, by_id: dict[str, IndexedProfile], owner: str
) -> None:
    """Validate one coordinate claim table against its prepared entries, once.

    The table must be a real coordinate index with parallel tuple keys/claims
    of well-shaped pairs, and every claim must reference a prepared entry.
    Dangling references fail closed instead of raising a raw ``KeyError`` at
    lookup time. The transmission tables are out of this slice and
    intentionally unchecked.
    """
    claims_owner = (owner, "claims")
    if not isinstance(table, CoordinateIndex):
        _reject_shape("memory", claims_owner)
        return
    if type(table.keys) is not tuple or type(table.claims) is not tuple:
        _reject_shape("memory", claims_owner)
    if len(table.keys) != len(table.claims):
        _reject_shape("memory", claims_owner)
    for key in table.keys:
        if type(key) is not tuple or len(key) != 2 or type(key[0]) is not str or type(key[1]) is not str:
            _reject_shape("memory", (owner, "keys"))
    expected = build_profile_indexes(tuple(by_id.values())).coordinates
    if table != expected:
        _reject_shape("memory", claims_owner)
    for claim in table.claims:
        if not isinstance(claim, CoordinateClaim) or claim.profile_id not in by_id:
            _reject_shape("memory", claims_owner)


def _prepare_profiles(profiles: Any, owner: str) -> tuple[IndexedProfile, ...]:
    """Validate one entry tuple: exact tuple container, then each entry once."""
    if type(profiles) is not tuple:
        _reject_shape("memory", (owner, "profiles"))
    if len(profiles) > MAX_PROFILES:
        _reject_shape("memory", (owner, "profiles"))
    prepared = tuple(_prepare_entry(entry, owner) for entry in profiles)
    return build_profile_indexes(prepared).profiles


@dataclass(frozen=True, slots=True, repr=False)
class PreparedCustomContext:
    """Once-prepared custom side for per-exam resolution without recompiling.

    Holds the validated coordinate table, the validated entries, and the lead
    source kind — tuples and frozen values only, so a prepared context is
    immutable and freely shared across exams of one session. Per-exam
    resolution rebuilds only the ID lookup map from ``entries``.

    Construction re-runs the full preparation boundary below, so any instance
    — however built, including ``dataclasses.replace`` copies — carries the
    invariants; resolution performs no validation of its own.
    """

    index: ProfileIndexes
    entries: tuple[IndexedProfile, ...]
    lead_kind: str

    def __repr__(self) -> str:
        return (
            f"PreparedCustomContext(profiles={len(self.entries)}, lead_kind={self.lead_kind!r})"
        )

    def __post_init__(self) -> None:
        """Re-run the full preparation boundary: construction guarantees invariants.

        Entry context/structure/hash validation, the compiler-derived claim-table
        comparison, the closed lead kind, and the capability gate all run here —
        so a forged instance fails closed at construction and resolution itself
        performs no validation. Idempotent with :func:`prepare_custom_context`.
        """
        entries = _validate_prepared_entries(self.entries, "custom")
        _validate_prepared_claims(self.index, entries, "custom")
        _validate_lead_kind(self.lead_kind)
        _gate_custom_entries(entries)


@dataclass(frozen=True, slots=True, repr=False)
class PreparedBundledContext:
    """Once-prepared bundled side, mirroring :class:`PreparedCustomContext`."""

    index: ProfileIndexes
    entries: tuple[IndexedProfile, ...]
    default: IndexedProfile | None
    lead_kind: str

    def __repr__(self) -> str:
        return (
            f"PreparedBundledContext(profiles={len(self.entries)}, "
            f"has_default={self.default is not None}, lead_kind={self.lead_kind!r})"
        )

    def __post_init__(self) -> None:
        """Re-run the full preparation boundary; see :class:`PreparedCustomContext`."""
        entries = _validate_prepared_entries(self.entries, "bundled")
        _validate_prepared_claims(self.index, entries, "bundled")
        if self.default is not None:
            _prepare_entry(self.default, "bundled")
        _validate_lead_kind(self.lead_kind)


def _validate_prepared_entries(entries: Any, owner: str) -> tuple[IndexedProfile, ...]:
    """Re-validate prepared entries: exact tuple, bound, and per-entry checks."""
    if type(entries) is not tuple:
        _reject_shape("memory", (owner, "profiles"))
    if len(entries) > MAX_PROFILES:
        _reject_shape("memory", (owner, "profiles"))
    prepared = tuple(_prepare_entry(entry, owner) for entry in entries)
    return build_profile_indexes(prepared).profiles


def _validate_prepared_claims(
    index: Any, entries: tuple[IndexedProfile, ...], owner: str
) -> None:
    """Re-validate a prepared claim table against prepared entries."""
    if not isinstance(index, ProfileIndexes):
        _reject_shape("memory", (owner,))
    by_id = {entry.profile.profile_id: entry for entry in entries}
    _prepare_claims(index.coordinates, by_id, owner)
    if index != build_profile_indexes(entries):
        _reject_shape("memory", (owner,))


def _validate_lead_kind(lead_kind: Any) -> None:
    """Lead kinds are closed: empty (nothing prepared) or a vocabulary member."""
    if type(lead_kind) is not str or (lead_kind != "" and lead_kind not in SOURCE_KINDS):
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_ENUM, source_kind="memory", field_path=("lead_kind",)
        )


def prepare_custom_context(custom: Any) -> PreparedCustomContext:
    """Validate a compiled custom index once for repeated per-exam resolution.

    Runs entry context/structure/hash validation and the claim-table check;
    raises closed errors for hand-built or corrupted inputs. The returned
    context is immutable and re-resolvable without recompiling.
    """
    if not isinstance(custom, ProfileIndexes):
        raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("custom",))
    entries = _prepare_profiles(custom.profiles, "custom")
    by_id = {entry.profile.profile_id: entry for entry in entries}
    _prepare_claims(custom.coordinates, by_id, "custom")
    return PreparedCustomContext(
        index=custom,
        entries=entries,
        lead_kind=entries[0].source_kind if entries else "",
    )


def prepare_bundled_context(bundled: Any) -> PreparedBundledContext:
    """Validate a compiled bundled set once for repeated per-exam resolution."""
    if not isinstance(bundled, BundledCoordinateSet):
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("bundled",)
        )
    if not isinstance(bundled.exact, ProfileIndexes):
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("bundled",)
        )
    entries = _prepare_profiles(bundled.exact.profiles, "bundled")
    default = _prepare_entry(bundled.default, "bundled") if bundled.default is not None else None
    by_id = {entry.profile.profile_id: entry for entry in entries}
    _prepare_claims(bundled.exact.coordinates, by_id, "bundled")
    if default is not None:
        lead_kind = entries[0].source_kind if entries else default.source_kind
    else:
        lead_kind = entries[0].source_kind if entries else ""
    return PreparedBundledContext(index=bundled.exact, entries=entries, default=default, lead_kind=lead_kind)
