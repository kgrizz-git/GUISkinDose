"""Immutable compiled coordinate/transmission lookup indexes.

An index is compiled once from validated entries and then answers per-event lookups without scanning
profiles: coordinate slots resolve by bisecting a sorted key table (logarithmic), and transmission rows
resolve by bisecting a sorted per-plane table. Everything stored is a tuple, so nothing can be mutated after
construction and nothing mutable is ever exposed.

Entries are never trusted on construction. The input must be a real sequence bounded by ``MAX_PROFILES``,
each entry's source context is strictly checked (exact ``str`` source kind, exact ``int`` revision in range,
lowercase hex content hash), and each profile — however it was built — is structurally pre-checked and then
re-run through the existing document validation boundary at compile time. The recompiled canonical hash must
equal the claimed hash. Re-parsing is validation only; nothing is activated here.

What an index is *not*: it performs no matching precedence, no inheritance, no interpolation, no overlay, and
no evidence eligibility. It stores every claim the schema allows — exact identities, explicit aliases, and
manufacturer-scoped model wildcards — exactly as claimed, and leaves all capability and precedence decisions
to activation. The initial activation gate is unchanged by this module.
"""

from __future__ import annotations

import math
import re
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, NoReturn

from guiskindose.equipment_profiles.canonical import (
    canonical_profile_dict,
)
from guiskindose.equipment_profiles.canonical import (
    profile_hash as _canonical_profile_hash,
)
from guiskindose.equipment_profiles.conflicts import coordinate_identity_claims, validate_profile_set
from guiskindose.equipment_profiles.constants import (
    AXIS_FIELDS,
    MAX_AGGREGATE_ROWS,
    MAX_ALIASES,
    MAX_MODELS,
    MAX_PROFILES,
    MAX_REVISION,
    MAX_TRANSMISSION_ROWS,
    PLANE_WILDCARD,
    ROTATION_LEAVES,
    SCHEMA_VERSION,
    SOURCE_KINDS,
    TRANSLATION_DIRECTION,
    TRANSLATION_OFFSET,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.equipment_profiles.keys import normalize_manufacturer_key, normalize_model_key
from guiskindose.equipment_profiles.models import (
    Coordinates,
    Profile,
    Provenance,
    RotationDirection,
    TranslationDirection,
    TranslationOffset,
    TransmissionRow,
)
from guiskindose.equipment_profiles.validation import validate_document

#: A coordinate lookup key: ``(canonical manufacturer key, canonical model key)``. The model component may
#: be the ``"*"`` wildcard; there is no manufacturer wildcard.
CoordinateKey = tuple[str, str]

#: A transmission lookup key: ``(canonical model key, literal acquisition plane)``. The plane is literal and
#: is never normalized.
TransmissionKey = tuple[str, str]

#: Claimed content hashes are lowercase SHA-256 hex digests, exactly like every other hash in this package.
_HEX_64_RE = re.compile(r"\A[0-9a-f]{64}\Z")

#: Transmission row fields holding required short text.
_TRANSMISSION_TEXT_FIELDS = ("device_model", "acquisition_plane", "evidence_status")

#: Transmission row fields holding required finite numbers.
_TRANSMISSION_NUMBER_FIELDS = (
    "kvp_kv",
    "filtration_added_mmcu",
    "filtration_added_mmal",
    "k_patient_support",
)

#: Transmission row fields holding optional bounded free text.
_TRANSMISSION_OPTIONAL_TEXT_FIELDS = ("source", "date", "comment")


@dataclass(frozen=True, slots=True, repr=False)
class IndexedProfile:
    """One validated profile with the source context it was compiled from.

    ``source_kind`` names where the profile came from, ``revision`` carries a store revision when there is
    one (``None`` otherwise), and ``profile_hash`` is the verified canonical content hash. The repr shows
    only the source-kind token, the revision, and the hash — never identifiers or content.
    """

    profile: Profile
    source_kind: str
    revision: int | None
    profile_hash: str

    def __repr__(self) -> str:
        return (
            f"IndexedProfile(source_kind={self.source_kind!r}, revision={self.revision!r}, "
            f"profile_hash={self.profile_hash!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class CoordinateClaim:
    """One coordinate slot claimed by one profile, with how the slot was reached.

    ``manufacturer_key`` and ``model_key`` are the canonical keys this slot answers to. ``is_wildcard`` marks
    a manufacturer-scoped ``"*"`` model claim; ``via_alias`` marks a slot reached through an alias spelling
    rather than a canonical one (an alias that spells exactly like its canonical target is not "via" anything
    special). ``promote_wildcard`` records the declared promotion flag without applying it. The repr shows
    only the source-kind token, the revision, the flags, and the content hash — never key text.
    """

    profile_id: str
    source_kind: str
    revision: int | None
    profile_hash: str
    manufacturer_key: str
    model_key: str
    is_wildcard: bool
    via_alias: bool
    promote_wildcard: bool

    def __repr__(self) -> str:
        return (
            f"CoordinateClaim(source_kind={self.source_kind!r}, revision={self.revision!r}, "
            f"is_wildcard={self.is_wildcard!r}, via_alias={self.via_alias!r}, "
            f"promote_wildcard={self.promote_wildcard!r}, profile_hash={self.profile_hash!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class CoordinateIndex:
    """Immutable coordinate lookup table: sorted ``(key, claim)`` pairs plus the compiled profiles.

    ``keys`` and ``claims`` are parallel tuples in the same order; lookups bisect ``keys`` and never scan.
    Global duplicate claims are rejected at build time, so every key resolves to at most one claim.
    """

    keys: tuple[CoordinateKey, ...]
    claims: tuple[CoordinateClaim, ...]
    profiles: tuple[IndexedProfile, ...]

    def __len__(self) -> int:
        return len(self.profiles)

    def lookup_exact(self, manufacturer_key: str, model_key: str) -> CoordinateClaim | None:
        """Return the claim for an exact ``(manufacturer, model)`` slot, or ``None`` when unclaimed.

        Keys are normalized on entry, so raw RDSR spellings may be passed directly. A ``"*"`` model looks
        up the wildcard slot itself; see :meth:`lookup_wildcard` for the usual wildcard query.
        """
        key = (normalize_manufacturer_key(manufacturer_key), normalize_model_key(model_key))
        position = bisect_left(self.keys, key)
        if position < len(self.keys) and self.keys[position] == key:
            return self.claims[position]
        return None

    def lookup_wildcard(self, manufacturer_key: str) -> CoordinateClaim | None:
        """Return the manufacturer-scoped wildcard claim for a manufacturer, or ``None`` when absent."""
        return self.lookup_exact(manufacturer_key, PLANE_WILDCARD)

    def __repr__(self) -> str:
        return f"CoordinateIndex(slots={len(self.keys)}, profiles={len(self.profiles)})"


@dataclass(frozen=True, slots=True, repr=False)
class TransmissionNode:
    """One transmission row as stored in the index, with the source context it was compiled from.

    ``row`` is the canonical immutable row; the plane inside it is literal and the numeric triple is the
    original row key, preserved exactly for the later composition step. The repr shows only the source-kind
    token, the revision, and the content hash — never the row itself.
    """

    profile_id: str
    source_kind: str
    revision: int | None
    profile_hash: str
    row: TransmissionRow

    def __repr__(self) -> str:
        return (
            f"TransmissionNode(source_kind={self.source_kind!r}, revision={self.revision!r}, "
            f"profile_hash={self.profile_hash!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class TransmissionIndex:
    """Immutable transmission lookup table: sorted ``(key, node-group)`` pairs plus the profiles.

    Each key is ``(canonical model key, literal plane)`` and each group holds that plane's nodes ordered by
    their ``(kVp, Cu, Al)`` numeric key. Lookups bisect ``keys`` and never scan.
    """

    keys: tuple[TransmissionKey, ...]
    node_groups: tuple[tuple[TransmissionNode, ...], ...]
    profiles: tuple[IndexedProfile, ...]

    def __len__(self) -> int:
        return len(self.profiles)

    def nodes_for(self, model_key: str, acquisition_plane: str) -> tuple[TransmissionNode, ...]:
        """Return the nodes stored for one ``(model, literal plane)`` pair, or ``()`` when uncovered.

        The model key is normalized on entry; the plane is literal and is compared exactly.
        """
        key = (normalize_model_key(model_key), acquisition_plane)
        position = bisect_left(self.keys, key)
        if position < len(self.keys) and self.keys[position] == key:
            return self.node_groups[position]
        return ()

    def __repr__(self) -> str:
        return f"TransmissionIndex(planes={len(self.keys)}, profiles={len(self.profiles)})"


@dataclass(frozen=True, slots=True, repr=False)
class ProfileIndexes:
    """One immutable compilation of both lookup indexes over the same profile set."""

    coordinates: CoordinateIndex
    transmission: TransmissionIndex
    profiles: tuple[IndexedProfile, ...]

    def __len__(self) -> int:
        return len(self.profiles)

    def __repr__(self) -> str:
        return (
            f"ProfileIndexes(coordinates={len(self.coordinates.keys)}, "
            f"transmission={len(self.transmission.keys)}, profiles={len(self.profiles)})"
        )


def _reject(code: ProfileErrorCode, source_kind: str, field_path: tuple[str, ...]) -> NoReturn:
    """Raise a value-free index failure; every structural rejection funnels through here."""
    raise EquipmentProfileError(code, source_kind=source_kind, field_path=field_path)


def _check_context(entry: Any) -> tuple[str, int | None, str]:
    """Validate one entry's source context with closed errors, never echoing values.

    The source kind must be exactly ``str`` (a subclass, or any object with a permissive equality, is
    rejected) and a member of the vocabulary; the revision must be exactly ``int`` — booleans rejected —
    in ``1..MAX_REVISION``; the claimed hash must be 64 lowercase hex characters.
    """
    if not isinstance(entry, IndexedProfile):
        _reject(ProfileErrorCode.INVALID_TYPE, "memory", ())
    kind = entry.source_kind
    if type(kind) is not str or kind not in SOURCE_KINDS:
        _reject(ProfileErrorCode.INVALID_ENUM, "memory", ("source_kind",))
    revision = entry.revision
    if revision is not None and (type(revision) is not int or not 1 <= revision <= MAX_REVISION):
        _reject(ProfileErrorCode.VALUE_OUT_OF_RANGE, kind, ("revision",))
    claimed = entry.profile_hash
    if type(claimed) is not str or _HEX_64_RE.match(claimed) is None:
        _reject(ProfileErrorCode.INVALID_TYPE, kind, ("profile_hash",))
    if not isinstance(entry.profile, Profile):
        _reject(ProfileErrorCode.INVALID_TYPE, kind, ("profile",))
    return kind, revision, claimed


def _check_number(value: Any, field_path: tuple[str, ...], source_kind: str) -> None:
    """Gate a hand-built numeric leaf before serialization: no booleans, no coercion, no overflow.

    Mirrors the document boundary's number rule so a value that cannot survive ``float()`` — including a
    Python integer too large for a double — fails ``invalid_number`` here instead of raising raw text from
    the serializer.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _reject(ProfileErrorCode.INVALID_NUMBER, source_kind, field_path)
    try:
        result = float(value)
    except (OverflowError, ValueError):
        _reject(ProfileErrorCode.INVALID_NUMBER, source_kind, field_path)
    if math.isnan(result) or result in (float("inf"), float("-inf")):
        _reject(ProfileErrorCode.INVALID_NUMBER, source_kind, field_path)


def _check_text(value: Any, field_path: tuple[str, ...], source_kind: str) -> None:
    """Gate a hand-built required string: exactly ``str``, never a lookalike."""
    if not isinstance(value, str):
        _reject(ProfileErrorCode.INVALID_TYPE, source_kind, field_path)


def _check_flag(value: Any, field_path: tuple[str, ...], source_kind: str) -> None:
    """Gate a hand-built boolean: exactly ``bool``, so ``1`` cannot coerce to ``True``."""
    if type(value) is not bool:
        _reject(ProfileErrorCode.INVALID_TYPE, source_kind, field_path)


def _check_str_tuple(values: Any, field_path: tuple[str, ...], source_kind: str) -> None:
    """Gate a hand-built string collection: a tuple of strings, never a list or mixed content."""
    if not isinstance(values, tuple):
        _reject(ProfileErrorCode.INVALID_TYPE, source_kind, field_path)
    ceiling = MAX_MODELS if field_path == ("models",) else MAX_ALIASES
    if len(values) > ceiling:
        _reject(ProfileErrorCode.VALUE_OUT_OF_RANGE, source_kind, field_path)
    for item in values:
        if not isinstance(item, str):
            _reject(ProfileErrorCode.INVALID_TYPE, source_kind, field_path)


def _check_alias_pairs(pairs: Any, source_kind: str) -> None:
    """Gate hand-built model aliases: a tuple of ``(alias, target)`` string pairs."""
    field_path = ("model_aliases",)
    if not isinstance(pairs, tuple):
        _reject(ProfileErrorCode.INVALID_TYPE, source_kind, field_path)
    if len(pairs) > MAX_ALIASES:
        _reject(ProfileErrorCode.VALUE_OUT_OF_RANGE, source_kind, field_path)
    seen: set[str] = set()
    for pair in pairs:
        if (
            not isinstance(pair, tuple)
            or len(pair) != 2
            or not isinstance(pair[0], str)
            or not isinstance(pair[1], str)
        ):
            _reject(ProfileErrorCode.INVALID_TYPE, source_kind, field_path)
        if pair[0] in seen:
            _reject(ProfileErrorCode.DUPLICATE_JSON_KEY, source_kind, field_path)
        seen.add(pair[0])


def _check_provenance_structure(provenance: Any, source_kind: str) -> None:
    """Gate hand-built provenance: absent, or a ``Provenance`` holding strings or ``None``."""
    if provenance is None:
        return
    if not isinstance(provenance, Provenance):
        _reject(ProfileErrorCode.INVALID_TYPE, source_kind, ("provenance",))
    for key in ("source", "notes"):
        value = getattr(provenance, key)
        if value is not None and not isinstance(value, str):
            _reject(ProfileErrorCode.INVALID_TYPE, source_kind, ("provenance", key))


def _check_axis_numbers(block: TranslationOffset, base_path: tuple[str, ...], source_kind: str) -> None:
    """Gate hand-built offset leaves."""
    for axis in AXIS_FIELDS:
        value = getattr(block, axis)
        if value is not None:
            _check_number(value, (*base_path, axis), source_kind)


def _check_axis_signs(block: TranslationDirection, base_path: tuple[str, ...], source_kind: str) -> None:
    """Gate hand-built direction leaves."""
    for axis in AXIS_FIELDS:
        value = getattr(block, axis)
        if value is not None and not isinstance(value, str):
            _reject(ProfileErrorCode.INVALID_TYPE, source_kind, (*base_path, axis))


def _check_rotation_signs(block: RotationDirection, base_path: tuple[str, ...], source_kind: str) -> None:
    """Gate hand-built rotation leaves."""
    for field_name, json_name in ROTATION_LEAVES:
        value = getattr(block, field_name)
        if value is not None and not isinstance(value, str):
            _reject(ProfileErrorCode.INVALID_TYPE, source_kind, (*base_path, json_name))


def _check_offset_block(block: Any, source_kind: str) -> None:
    if block is None:
        return
    if not isinstance(block, TranslationOffset):
        _reject(ProfileErrorCode.INVALID_TYPE, source_kind, ("coordinates", TRANSLATION_OFFSET))
    _check_axis_numbers(block, ("coordinates", TRANSLATION_OFFSET), source_kind)


def _check_direction_block(block: Any, source_kind: str) -> None:
    if block is None:
        return
    if not isinstance(block, TranslationDirection):
        _reject(ProfileErrorCode.INVALID_TYPE, source_kind, ("coordinates", TRANSLATION_DIRECTION))
    _check_axis_signs(block, ("coordinates", TRANSLATION_DIRECTION), source_kind)


def _check_rotation_block(block: Any, source_kind: str) -> None:
    if block is None:
        return
    if not isinstance(block, RotationDirection):
        _reject(ProfileErrorCode.INVALID_TYPE, source_kind, ("coordinates", "rotation_direction"))
    _check_rotation_signs(block, ("coordinates", "rotation_direction"), source_kind)


def _check_coordinates_structure(coordinates: Any, source_kind: str) -> None:
    """Gate hand-built coordinates: exact block types with gated leaves, so serialization is total."""
    if coordinates is None:
        return
    if not isinstance(coordinates, Coordinates):
        _reject(ProfileErrorCode.INVALID_TYPE, source_kind, ("coordinates",))
    _check_offset_block(coordinates.translation_offset, source_kind)
    _check_direction_block(coordinates.translation_direction, source_kind)
    _check_rotation_block(coordinates.rotation_direction, source_kind)
    swap = coordinates.swap_lateral_longitudinal
    if swap is not None:
        _check_flag(swap, ("coordinates", "swap_lateral_longitudinal"), source_kind)
    mode = coordinates.field_size_mode
    if mode is not None:
        _check_text(mode, ("coordinates", "field_size_mode"), source_kind)
    side = coordinates.detector_side_length
    if side is not None:
        _check_number(side, ("coordinates", "detector_side_length"), source_kind)


def _check_row_structure(row: Any, source_kind: str) -> None:
    """Gate a hand-built transmission row: a ``TransmissionRow`` of well-typed scalars."""
    if not isinstance(row, TransmissionRow):
        _reject(ProfileErrorCode.INVALID_TYPE, source_kind, ("transmission",))
    for key in _TRANSMISSION_TEXT_FIELDS:
        _check_text(getattr(row, key), ("transmission", key), source_kind)
    for key in _TRANSMISSION_NUMBER_FIELDS:
        _check_number(getattr(row, key), ("transmission", key), source_kind)
    for key in _TRANSMISSION_OPTIONAL_TEXT_FIELDS:
        value = getattr(row, key)
        if value is not None and not isinstance(value, str):
            _reject(ProfileErrorCode.INVALID_TYPE, source_kind, ("transmission", key))


def _check_profile_structure(profile: Profile, source_kind: str) -> None:
    """Gate a hand-built profile's shape before serialization, so no raw error can escape it.

    Mutable containers (lists where tuples belong), wrong-typed scalars (``1`` where ``bool`` belongs),
    and non-model nested objects are rejected here; every range, vocabulary, and alias-target rule is then
    enforced by the re-parse through the existing validation boundary.
    """
    _check_text(profile.profile_id, ("profile_id",), source_kind)
    _check_text(profile.manufacturer, ("manufacturer",), source_kind)
    _check_str_tuple(profile.models, ("models",), source_kind)
    _check_str_tuple(profile.manufacturer_aliases, ("manufacturer_aliases",), source_kind)
    _check_alias_pairs(profile.model_aliases, source_kind)
    _check_provenance_structure(profile.provenance, source_kind)
    _check_coordinates_structure(profile.coordinates, source_kind)
    rows = profile.transmission
    if not isinstance(rows, tuple):
        _reject(ProfileErrorCode.INVALID_TYPE, source_kind, ("transmission",))
    if len(rows) > MAX_TRANSMISSION_ROWS:
        _reject(ProfileErrorCode.ROW_LIMIT_EXCEEDED, source_kind, ("transmission",))
    for row in rows:
        _check_row_structure(row, source_kind)
    _check_flag(profile.promote_coordinate_wildcard, ("promote_coordinate_wildcard",), source_kind)


def _revalidate_profile(profile: Profile, source_kind: str, claimed_hash: str) -> Profile:
    """Re-run a profile through the existing validation boundary and verify its claimed hash.

    The structurally gated profile is serialized to its canonical mapping and validated as a single-profile
    document, so every range, vocabulary, and alias rule the adapters enforce applies here too. The
    recompiled canonical hash must equal the entry's claimed hash, or the entry's context disagrees with its
    content and compilation fails ``conflicting_profile_metadata``. Returns the recompiled canonical
    profile, whose types are guaranteed by validation rather than by the caller's constructor. This is
    compile-time validation only; nothing is activated.
    """
    _check_profile_structure(profile, source_kind)
    canonical = canonical_profile_dict(profile)
    fresh = validate_document(
        {"schema_version": SCHEMA_VERSION, "profiles": [canonical]}, source_kind=source_kind
    )
    recompiled = fresh[0]
    if _canonical_profile_hash(recompiled) != claimed_hash:
        _reject(ProfileErrorCode.CONFLICTING_PROFILE_METADATA, source_kind, ("profile_hash",))
    return recompiled


def _revalidate_entry(entry: Any) -> IndexedProfile:
    """Validate one entry's context and revalidate its profile, returning the canonical entry."""
    kind, revision, claimed = _check_context(entry)
    fresh = _revalidate_profile(entry.profile, kind, claimed)
    return IndexedProfile(profile=fresh, source_kind=kind, revision=revision, profile_hash=claimed)


def _canonical_slots(profile: Profile) -> set[CoordinateKey]:
    """The slots a profile claims through canonical spellings alone (aliases excluded)."""
    manufacturer = normalize_manufacturer_key(profile.manufacturer)
    return {(manufacturer, normalize_model_key(model)) for model in profile.models}


def _coordinate_claims(entry: IndexedProfile) -> tuple[CoordinateClaim, ...]:
    """Expand one entry's full claim set: canonical spellings, explicit aliases, and wildcards."""
    canonical = _canonical_slots(entry.profile)
    claims: list[CoordinateClaim] = []
    for manufacturer_key, model_key in coordinate_identity_claims(entry.profile):
        claims.append(
            CoordinateClaim(
                profile_id=entry.profile.profile_id,
                source_kind=entry.source_kind,
                revision=entry.revision,
                profile_hash=entry.profile_hash,
                manufacturer_key=manufacturer_key,
                model_key=model_key,
                is_wildcard=model_key == PLANE_WILDCARD,
                via_alias=(manufacturer_key, model_key) not in canonical,
                promote_wildcard=entry.profile.promote_coordinate_wildcard,
            )
        )
    return tuple(sorted(claims, key=lambda claim: (claim.manufacturer_key, claim.model_key)))


def _transmission_nodes(entry: IndexedProfile) -> tuple[tuple[TransmissionKey, TransmissionNode], ...]:
    """Expand one entry's transmission rows into keyed nodes ordered by their numeric key."""
    nodes: list[tuple[TransmissionKey, TransmissionNode]] = []
    for row in entry.profile.transmission:
        nodes.append(
            (
                (normalize_model_key(row.device_model), row.acquisition_plane),
                TransmissionNode(
                    profile_id=entry.profile.profile_id,
                    source_kind=entry.source_kind,
                    revision=entry.revision,
                    profile_hash=entry.profile_hash,
                    row=row,
                ),
            )
        )
    nodes.sort(
        key=lambda item: (
            item[0],
            item[1].row.kvp_kv,
            item[1].row.filtration_added_mmcu,
            item[1].row.filtration_added_mmal,
        )
    )
    return tuple(nodes)


def _materialize_entries(entries: Sequence[IndexedProfile]) -> list[Any]:
    """Copy the input to a list under the profile cap, rejecting non-sequences and lying lengths.

    A declared length above ``MAX_PROFILES`` fails before anything is copied; materialization then
    re-checks the cap item by item, so a sequence whose length under-reports cannot force unbounded work.
    """
    if isinstance(entries, (str, bytes, bytearray)) or not isinstance(entries, Sequence):
        raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=())
    try:
        declared = len(entries)
    except TypeError:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=()
        ) from None
    if declared > MAX_PROFILES:
        raise EquipmentProfileError(
            ProfileErrorCode.PROFILE_LIMIT_EXCEEDED, source_kind="memory", field_path=(), count=declared
        )
    raw: list[Any] = []
    for item in entries:
        raw.append(item)
        if len(raw) > MAX_PROFILES:
            raise EquipmentProfileError(
                ProfileErrorCode.PROFILE_LIMIT_EXCEEDED, source_kind="memory", field_path=(), count=len(raw)
            )
    return raw


def _publish(ordered: tuple[IndexedProfile, ...]) -> ProfileIndexes:
    """Expand claims and transmission nodes from conflict-free entries and publish the indexes."""
    claims: list[tuple[CoordinateKey, CoordinateClaim]] = []
    for entry in ordered:
        for claim in _coordinate_claims(entry):
            claims.append(((claim.manufacturer_key, claim.model_key), claim))
    claims.sort(key=lambda item: item[0])

    groups: dict[TransmissionKey, list[TransmissionNode]] = {}
    for entry in ordered:
        for key, node in _transmission_nodes(entry):
            groups.setdefault(key, []).append(node)
    ordered_keys = tuple(sorted(groups))
    node_groups = tuple(
        tuple(sorted(group, key=lambda node: (node.row.kvp_kv, node.row.filtration_added_mmcu, node.row.filtration_added_mmal)))
        for group in (groups[key] for key in ordered_keys)
    )

    return ProfileIndexes(
        coordinates=CoordinateIndex(
            keys=tuple(key for key, _claim in claims),
            claims=tuple(claim for _key, claim in claims),
            profiles=ordered,
        ),
        transmission=TransmissionIndex(
            keys=ordered_keys,
            node_groups=node_groups,
            profiles=ordered,
        ),
        profiles=ordered,
    )


def build_profile_indexes(entries: Sequence[IndexedProfile]) -> ProfileIndexes:
    """Compile immutable coordinate and transmission indexes from validated entries.

    Bounds run before any copying: the input must be a real sequence (strings, bytes, and one-shot
    iterables are rejected), a declared length above ``MAX_PROFILES`` fails immediately, and
    materialization re-checks the cap so a lying length cannot force unbounded work. Every entry is then
    context-checked, structurally gated, and revalidated through the existing document boundary with its
    claimed hash verified; the aggregate logical-row ceiling is enforced on the recompiled profiles before
    any claim is expanded.

    Global conflicts are detected *before* anything is published: profiles are ordered by exact
    ``profile_id`` and run through the canonical conflict check, so duplicate IDs, coordinate claims
    (including alias and wildcard collisions), and transmission keys all fail closed with their stable
    codes. Successful compilation is therefore identical for every source order; only a conflict
    diagnostic's ``source_kind`` follows the lead (first) entry.
    """
    raw = _materialize_entries(entries)
    checked = tuple(_revalidate_entry(item) for item in raw)
    lead_kind = checked[0].source_kind if checked else "memory"
    total_rows = sum(entry.profile.logical_row_count() for entry in checked)
    if total_rows > MAX_AGGREGATE_ROWS:
        raise EquipmentProfileError(
            ProfileErrorCode.ROW_LIMIT_EXCEEDED, source_kind=lead_kind, field_path=(), count=total_rows
        )
    ordered = tuple(sorted(checked, key=lambda entry: entry.profile.profile_id))
    validate_profile_set(tuple(entry.profile for entry in ordered), source_kind=lead_kind)
    return _publish(ordered)


__all__ = [
    "CoordinateClaim",
    "CoordinateIndex",
    "CoordinateKey",
    "IndexedProfile",
    "ProfileIndexes",
    "TransmissionIndex",
    "TransmissionKey",
    "TransmissionNode",
    "build_profile_indexes",
]
