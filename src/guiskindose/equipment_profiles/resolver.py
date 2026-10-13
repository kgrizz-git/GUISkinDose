"""Immutable custom-exact coordinate resolver over compiled indexes (initial slice).

Resolution ladder for one homogeneous exam (SPEC §5):

1. custom exact manufacturer/model;
2. bundled exact manufacturer/model (built-in vendor aliases apply here only);
3. bundled manufacturer-scoped model wildcard;
4. Default (unconditional last fallback, kept separate from the index).

Custom wildcards, aliases, promotion, and transmission custom profiles never
reach the ladder: the initial capability gate rejects them first with
``unsupported_profile_capability``. Later slices extend the ladder; this one
resolves custom exact matches with inheritance.

Every one of the 15 coordinate leaves resolves independently down the ladder:
the first candidate supplying the leaf wins, ``None`` never counts as
supplied, so explicit ``False`` and ``0.0`` survive. Missing maker identity —
blank, ``None``, or a ``"nan"``/``"nat"``/``"none"`` artifact of any case —
bypasses custom exact and both bundled steps for the legacy Default path, so a
custom profile literally named ``"none"`` or ``"nan"`` stays unreachable. A
leaf no candidate supplies fails closed (``missing_required_field``) rather
than reusing previous mutable settings.

Output is one immutable :class:`CoordinateMatchRecord` (existing types, all 15
leaves in canonical order with correct ``inherited`` flags against the
selected candidate), plus a structured resolution notice (``complete`` when
every leaf came from the selected candidate, else ``partial`` with one entry
per inherited leaf: field, source, level, profile ID, and display label).
Notice text names permitted labels only — fields, closed-vocabulary sources
and levels, maker/model/profile labels — never notes, source paths, or raw
source text. ``affected_event_count`` is fixed
per exam; ``matched_input_key`` uses canonical keys (empty when missing, never
``"none"``/``"nan"``).

Stdlib-only, like the rest of the core: no normalizer, settings, GUI, CLI, or
calculation imports. No application wiring reads this module yet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from guiskindose.equipment_profiles.bundled import BundledCoordinateSet
from guiskindose.equipment_profiles.capability import check_initial_capabilities
from guiskindose.equipment_profiles.constants import (
    AXIS_FIELDS,
    MATCH_DOMAIN_COORDINATE,
    MATCH_LEVEL_DEFAULT,
    MATCH_LEVEL_EXACT,
    MATCH_LEVEL_WILDCARD,
    MATCH_SOURCE_BUNDLED,
    MATCH_SOURCE_CUSTOM,
    MATCH_SOURCE_DEFAULT,
    MAX_ALIASES,
    MAX_MODELS,
    MAX_PROFILES,
    MAX_REVISION,
    MAX_TRANSMISSION_ROWS,
    RESOLUTION_COMPLETE,
    RESOLUTION_PARTIAL,
    ROTATION_LEAVES,
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
from guiskindose.equipment_profiles.keys import (
    clean_identity_text,
    normalize_manufacturer_key,
    normalize_model_key,
)
from guiskindose.equipment_profiles.matches import (
    CoordinateMatchRecord,
    LeafProvenance,
    MatchedInputKey,
    build_leaf_provenance,
)
from guiskindose.equipment_profiles.models import (
    Coordinates,
    LeafValue,
    Profile,
    Provenance,
    RotationDirection,
    TranslationDirection,
    TranslationOffset,
    TransmissionRow,
    coordinate_leaf_values,
)

__all__ = [
    "CoordinateResolution",
    "ExamCoordinateIdentity",
    "NoticeEntry",
    "ResolutionNotice",
    "resolve_coordinate_leaves",
]

#: The 15 coordinate leaves in canonical documentation order.
LEAF_ORDER: tuple[str, ...] = (
    tuple(f"translation_offset.{axis}" for axis in AXIS_FIELDS)
    + tuple(f"translation_direction.{axis}" for axis in AXIS_FIELDS)
    + tuple(f"rotation_direction.{json_name}" for _, json_name in ROTATION_LEAVES)
    + ("swap_lateral_longitudinal", "field_size_mode", "detector_side_length")
)


@dataclass(frozen=True, slots=True, repr=False)
class ExamCoordinateIdentity:
    """One exam's raw coordinate identity plus its fixed event count.

    Maker/model keep exact input spellings; canonical keys are derived
    properties. Blank, ``None``, and ``"nan"``/``"nat"``/``"none"`` artifacts
    (any case) all mean missing identity and yield empty keys, so they bypass
    custom matching for the fallback — a custom profile literally named
    ``"none"`` or ``"nan"`` can never be activated by a missing identity. The
    repr shows the event count only — never raw spellings or keys.
    """

    manufacturer: str | None
    model: str | None
    event_count: int

    @property
    def manufacturer_key(self) -> str:
        """Canonical maker key, or ``""`` when missing (never ``"none"``)."""
        cleaned = clean_identity_text(self.manufacturer) if isinstance(self.manufacturer, str) else None
        return normalize_manufacturer_key(cleaned) if cleaned is not None else ""

    @property
    def model_key(self) -> str:
        """Canonical model key, or ``""`` when missing."""
        cleaned = clean_identity_text(self.model) if isinstance(self.model, str) else None
        return normalize_model_key(cleaned) if cleaned is not None else ""

    def __repr__(self) -> str:
        return f"ExamCoordinateIdentity(event_count={self.event_count!r})"


@dataclass(frozen=True, slots=True, repr=False)
class NoticeEntry:
    """One inherited leaf for the resolution notice: field, source, and label.

    The repr shows the allowlisted field path and the closed-vocabulary source
    and level only — never the profile ID or display label, which may name
    equipment. Those stay in the user-facing notice text, not diagnostics.
    """

    field: str
    source: str
    level: str
    profile_id: str
    label: str

    def __repr__(self) -> str:
        return (
            f"NoticeEntry(field={self.field!r}, source={self.source!r}, level={self.level!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class ResolutionNotice:
    """Structured complete/partial notice with pre-rendered permitted-label text.

    The repr shows the notice kind and entry count only — never the rendered
    text, which may name equipment models and profiles for the user surface.
    """

    kind: str
    entries: tuple[NoticeEntry, ...]
    text: str

    def __repr__(self) -> str:
        return f"ResolutionNotice(kind={self.kind!r}, entries={len(self.entries)})"


@dataclass(frozen=True, slots=True, repr=False)
class CoordinateResolution:
    """One immutable per-exam coordinate resolution: record plus notice.

    The repr shows the closed-vocabulary source/level, the leaf count, and the
    notice kind only — never profile IDs, hashes, matched keys, or text. The
    full record (which may name profiles and models as permitted labels)
    stays out of diagnostics.
    """

    record: CoordinateMatchRecord
    notice: ResolutionNotice

    def __repr__(self) -> str:
        return (
            f"CoordinateResolution(source={self.record.source!r}, level={self.record.level!r}, "
            f"leaves={len(self.record.fields)}, notice={self.notice.kind!r})"
        )


@dataclass(frozen=True, slots=True)
class _Candidate:
    """One ladder rung: entry context plus its supplied leaves by dotted path."""

    entry: IndexedProfile
    source: str
    level: str
    leaves: tuple[tuple[str, LeafValue], ...]

    @property
    def profile(self) -> Profile:
        """The candidate's canonical profile."""
        return self.entry.profile

    def leaf_value(self, dotted_path: str) -> tuple[bool, LeafValue | None]:
        """``(supplied, value)`` for one leaf; only non-``None`` counts as supplied."""
        for path, value in self.leaves:
            if path == dotted_path:
                return True, value
        return False, None


def _check_identity(identity: Any) -> ExamCoordinateIdentity:
    """Reject malformed identities with closed errors before any resolution."""
    if not isinstance(identity, ExamCoordinateIdentity):
        raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=())
    for field_path in (("manufacturer",), ("model",)):
        value = getattr(identity, field_path[0])
        if value is not None and not isinstance(value, str):
            raise EquipmentProfileError(
                ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=field_path
            )
    if type(identity.event_count) is not int or identity.event_count < 0:
        raise EquipmentProfileError(
            ProfileErrorCode.VALUE_OUT_OF_RANGE, source_kind="memory", field_path=("event_count",)
        )
    return identity


def _check_inputs(
    custom: Any, bundled: Any
) -> tuple[ProfileIndexes, BundledCoordinateSet]:
    """Reject malformed resolver inputs with closed errors."""
    if not isinstance(custom, ProfileIndexes):
        raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("custom",))
    if not isinstance(bundled, BundledCoordinateSet):
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("bundled",)
        )
    return custom, bundled


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


def _gate_custom_profiles(custom: ProfileIndexes) -> None:
    """Run the initial capability gate over every custom profile with its own kind.

    Alias-, wildcard-, promotion-, and transmission-bearing custom profiles
    fail ``unsupported_profile_capability`` here — never silently ignored, and
    never partially applied. Bundled entries are not gated: built-in aliases
    and the wildcard ladder belong to the bundled layer.
    """
    for entry in custom.profiles:
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


@dataclass(frozen=True, slots=True)
class _ResolverContext:
    """Once-validated resolution inputs: entries by ID, default, and lead kind."""

    custom_by_id: dict[str, IndexedProfile]
    bundled_by_id: dict[str, IndexedProfile]
    default: IndexedProfile | None
    lead_kind: str


def _prepare_context(custom: ProfileIndexes, bundled: BundledCoordinateSet) -> _ResolverContext:
    """Validate both compiled inputs once — never per leaf or per event."""
    custom_entries = _prepare_profiles(custom.profiles, "custom")
    if not isinstance(bundled.exact, ProfileIndexes):
        _reject_shape("memory", ("bundled",))
    bundled_entries = _prepare_profiles(bundled.exact.profiles, "bundled")
    default = _prepare_entry(bundled.default, "bundled") if bundled.default is not None else None
    custom_by_id = {entry.profile.profile_id: entry for entry in custom_entries}
    bundled_by_id = {entry.profile.profile_id: entry for entry in bundled_entries}
    _prepare_claims(custom.coordinates, custom_by_id, "custom")
    _prepare_claims(bundled.exact.coordinates, bundled_by_id, "bundled")
    if default is not None:
        bundled_by_id[default.profile.profile_id] = default
    if custom_entries:
        lead_kind = custom_entries[0].source_kind
    elif bundled_entries:
        lead_kind = bundled_entries[0].source_kind
    elif default is not None:
        lead_kind = default.source_kind
    else:
        lead_kind = "memory"
    return _ResolverContext(
        custom_by_id=custom_by_id, bundled_by_id=bundled_by_id, default=default, lead_kind=lead_kind
    )


def _display_label(entry: IndexedProfile) -> str:
    """Notice label: the listed model, or manufacturer plus wildcard for wildcard profiles."""
    if entry.profile.models == ("*",):
        return f"{entry.profile.manufacturer} *"
    return entry.profile.models[0] if entry.profile.models else entry.profile.profile_id


def _custom_candidate(
    custom: ProfileIndexes, by_id: dict[str, IndexedProfile], identity: ExamCoordinateIdentity
) -> _Candidate | None:
    """The custom-exact candidate, or ``None`` without maker identity or match.

    Only exact canonical claims qualify; the gate already rejected every
    alias/wildcard custom profile, so a hit on the exact key is exact.
    """
    if not identity.manufacturer_key:
        return None
    claim = custom.coordinates.lookup_exact(identity.manufacturer_key, identity.model_key)
    if claim is None:
        return None
    entry = by_id[claim.profile_id]
    return _Candidate(
        entry=entry,
        source=MATCH_SOURCE_CUSTOM,
        level=MATCH_LEVEL_EXACT,
        leaves=entry.profile.coordinate_leaves(),
    )


def _bundled_candidates(
    bundled: BundledCoordinateSet,
    by_id: dict[str, IndexedProfile],
    identity: ExamCoordinateIdentity,
) -> tuple[_Candidate | None, _Candidate | None]:
    """Bundled exact and wildcard candidates (maker-scoped; skipped without maker)."""
    if not identity.manufacturer_key:
        return None, None
    exact_claim = bundled.exact.coordinates.lookup_exact(identity.manufacturer_key, identity.model_key)
    exact = (
        _candidate_for_claim(by_id, exact_claim, MATCH_SOURCE_BUNDLED, MATCH_LEVEL_EXACT)
        if exact_claim is not None
        else None
    )
    wildcard_claim = bundled.exact.coordinates.lookup_wildcard(identity.manufacturer_key)
    wildcard = (
        _candidate_for_claim(by_id, wildcard_claim, MATCH_SOURCE_BUNDLED, MATCH_LEVEL_WILDCARD)
        if wildcard_claim is not None
        else None
    )
    return exact, wildcard


def _candidate_for_claim(
    by_id: dict[str, IndexedProfile], claim: CoordinateClaim, source: str, level: str
) -> _Candidate:
    """Wrap a found index claim as a ladder candidate with its entry context."""
    entry = by_id[claim.profile_id]
    return _Candidate(entry=entry, source=source, level=level, leaves=entry.profile.coordinate_leaves())


def _default_candidate(default: IndexedProfile | None) -> _Candidate | None:
    """The Default fallback candidate, or ``None`` when the set has no Default."""
    if default is None:
        return None
    return _Candidate(
        entry=default,
        source=MATCH_SOURCE_DEFAULT,
        level=MATCH_LEVEL_DEFAULT,
        leaves=default.profile.coordinate_leaves(),
    )


def _resolve_leaf(
    dotted_path: str, ladder: tuple[_Candidate | None, ...], source_kind: str
) -> LeafProvenance:
    """Walk one leaf down the ladder; fail closed when no candidate supplies it."""
    selected = next(candidate for candidate in ladder if candidate is not None)
    for candidate in ladder:
        if candidate is None:
            continue
        supplied, value = candidate.leaf_value(dotted_path)
        if supplied and value is not None:
            entry = candidate.entry
            return build_leaf_provenance(
                dotted_path=dotted_path,
                value=value,
                profile_id=entry.profile.profile_id,
                source=candidate.source,
                level=candidate.level,
                source_kind=entry.source_kind,
                profile_hash=entry.profile_hash,
                is_selected_profile=candidate is selected,
                revision=entry.revision,
            )
    block, _, leaf = dotted_path.partition(".")
    raise EquipmentProfileError(
        ProfileErrorCode.MISSING_REQUIRED_FIELD, source_kind=source_kind, field_path=(block, leaf or block)
    )


def _notice_entries(
    fields: tuple[LeafProvenance, ...], by_id: dict[str, IndexedProfile]
) -> tuple[NoticeEntry, ...]:
    """One notice entry per inherited leaf, in canonical leaf order."""
    entries: list[NoticeEntry] = []
    for item in fields:
        if not item.inherited:
            continue
        entries.append(
            NoticeEntry(
                field=item.field,
                source=item.source,
                level=item.level,
                profile_id=item.profile_id,
                label=_display_label(by_id[item.profile_id]),
            )
        )
    return tuple(entries)


def _notice_text(
    kind: str,
    entries: tuple[NoticeEntry, ...],
    selected_label: str,
    selected_source: str,
    selected_level: str,
) -> str:
    """Render the value-free notice text (field/source names only)."""
    if kind == RESOLUTION_COMPLETE:
        return (
            f"Complete match — all {len(LEAF_ORDER)} leaves from "
            f"{selected_source} {selected_level} `{selected_label}`."
        )
    lines = "; ".join(
        f"`{item.field}` from {item.source} {item.level} `{item.label}`" for item in entries
    )
    return f"Partial match — fields inherited from bundled/Default: {lines}."


def resolve_coordinate_leaves(
    *,
    identity: ExamCoordinateIdentity,
    custom: ProfileIndexes,
    bundled: BundledCoordinateSet,
) -> CoordinateResolution:
    """Resolve all 15 coordinate leaves for one exam over the initial ladder.

    Validates both compiled inputs once up front (context, structure, hashes,
    claim references), runs the capability gate over the custom set, selects
    the highest-priority candidate with an exact custom claim (custom exact >
    bundled exact > bundled wildcard > Default), walks every leaf down the
    full ladder independently, and returns the immutable match record plus the
    structured notice. Raises value-free errors throughout.
    """
    checked_identity = _check_identity(identity)
    checked_custom, checked_bundled = _check_inputs(custom, bundled)
    context = _prepare_context(checked_custom, checked_bundled)
    _gate_custom_profiles(checked_custom)

    custom_candidate = _custom_candidate(checked_custom, context.custom_by_id, checked_identity)
    bundled_exact, bundled_wildcard = _bundled_candidates(
        checked_bundled, context.bundled_by_id, checked_identity
    )
    default_candidate = _default_candidate(context.default)
    ladder = (custom_candidate, bundled_exact, bundled_wildcard, default_candidate)
    if all(candidate is None for candidate in ladder):
        raise EquipmentProfileError(
            ProfileErrorCode.MISSING_REQUIRED_FIELD,
            source_kind=context.lead_kind,
            field_path=(),
        )
    selected = next(candidate for candidate in ladder if candidate is not None)
    leaves = tuple(_resolve_leaf(path, ladder, context.lead_kind) for path in LEAF_ORDER)

    selected_entry = selected.entry
    record = CoordinateMatchRecord(
        profile_id=selected_entry.profile.profile_id,
        source=selected.source,
        level=selected.level,
        source_kind=selected_entry.source_kind,
        profile_hash=selected_entry.profile_hash,
        matched_input_key=MatchedInputKey(
            manufacturer=checked_identity.manufacturer_key, model=checked_identity.model_key
        ),
        affected_event_count=checked_identity.event_count,
        fields=leaves,
        revision=selected_entry.revision,
        domain=MATCH_DOMAIN_COORDINATE,
    )
    notice_entries = _notice_entries(leaves, {**context.custom_by_id, **context.bundled_by_id})
    kind = RESOLUTION_COMPLETE if record.is_complete_match else RESOLUTION_PARTIAL
    notice = ResolutionNotice(
        kind=kind,
        entries=notice_entries,
        text=_notice_text(
            kind, notice_entries, _display_label(selected_entry), selected.source, selected.level
        ),
    )
    return CoordinateResolution(record=record, notice=notice)
