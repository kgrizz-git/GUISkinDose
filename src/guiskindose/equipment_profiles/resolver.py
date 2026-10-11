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

Sessions prepare each side once through :func:`prepare_custom_context` and
:func:`prepare_bundled_context` and resolve per exam through
:func:`resolve_with_prepared`, which rebuilds only lookup maps from the
prepared tuples — no recompilation, no revalidation, no file or store reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from guiskindose.equipment_profiles.bundled import BundledCoordinateSet
from guiskindose.equipment_profiles.constants import (
    AXIS_FIELDS,
    MATCH_DOMAIN_COORDINATE,
    MATCH_LEVEL_DEFAULT,
    MATCH_LEVEL_EXACT,
    MATCH_LEVEL_WILDCARD,
    MATCH_SOURCE_BUNDLED,
    MATCH_SOURCE_CUSTOM,
    MATCH_SOURCE_DEFAULT,
    RESOLUTION_COMPLETE,
    RESOLUTION_PARTIAL,
    ROTATION_LEAVES,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.equipment_profiles.indexes import (
    CoordinateClaim,
    IndexedProfile,
    ProfileIndexes,
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
from guiskindose.equipment_profiles.models import LeafValue, Profile
from guiskindose.equipment_profiles.preparation import (
    PreparedBundledContext,
    PreparedCustomContext,
    prepare_bundled_context,
    prepare_custom_context,
)

__all__ = [
    "CoordinateResolution",
    "ExamCoordinateIdentity",
    "NoticeEntry",
    "PreparedBundledContext",
    "PreparedCustomContext",
    "ResolutionNotice",
    "prepare_bundled_context",
    "prepare_custom_context",
    "resolve_coordinate_leaves",
    "resolve_with_prepared",
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




def _display_label(entry: IndexedProfile) -> str:
    """Notice label: the profile ID for custom profiles, the listed model otherwise."""
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
    index: ProfileIndexes,
    by_id: dict[str, IndexedProfile],
    identity: ExamCoordinateIdentity,
) -> tuple[_Candidate | None, _Candidate | None]:
    """Bundled exact and wildcard candidates (maker-scoped; skipped without maker)."""
    if not identity.manufacturer_key:
        return None, None
    exact_claim = index.coordinates.lookup_exact(identity.manufacturer_key, identity.model_key)
    exact = (
        _candidate_for_claim(by_id, exact_claim, MATCH_SOURCE_BUNDLED, MATCH_LEVEL_EXACT)
        if exact_claim is not None
        else None
    )
    wildcard_claim = index.coordinates.lookup_wildcard(identity.manufacturer_key)
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


def resolve_with_prepared(
    *,
    identity: ExamCoordinateIdentity,
    custom: PreparedCustomContext,
    bundled: PreparedBundledContext,
) -> CoordinateResolution:
    """Resolve one exam from prepared contexts without recompiling or revalidating.

    The ID lookup maps are rebuilt from the prepared immutable tuples — an
    allocation, not a validation — so per-exam resolution never recompiles
    indexes, re-reads files or stores, or shares mutable caches. Raises
    value-free errors throughout.
    """
    checked_identity = _check_identity(identity)
    if not isinstance(custom, PreparedCustomContext):
        raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("custom",))
    if not isinstance(bundled, PreparedBundledContext):
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind="memory", field_path=("bundled",)
        )
    custom_by_id = {entry.profile.profile_id: entry for entry in custom.entries}
    bundled_by_id = {entry.profile.profile_id: entry for entry in bundled.entries}
    if bundled.default is not None:
        bundled_by_id[bundled.default.profile.profile_id] = bundled.default

    custom_candidate = _custom_candidate(custom.index, custom_by_id, checked_identity)
    bundled_exact, bundled_wildcard = _bundled_candidates(
        bundled.index, bundled_by_id, checked_identity
    )
    default_candidate = _default_candidate(bundled.default)
    ladder = (custom_candidate, bundled_exact, bundled_wildcard, default_candidate)
    lead_kind = custom.lead_kind or bundled.lead_kind or "memory"
    if all(candidate is None for candidate in ladder):
        raise EquipmentProfileError(
            ProfileErrorCode.MISSING_REQUIRED_FIELD,
            source_kind=lead_kind,
            field_path=(),
        )
    selected = next(candidate for candidate in ladder if candidate is not None)
    leaves = tuple(_resolve_leaf(path, ladder, lead_kind) for path in LEAF_ORDER)

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
    notice_entries = _notice_entries(leaves, {**custom_by_id, **bundled_by_id})
    kind = RESOLUTION_COMPLETE if record.is_complete_match else RESOLUTION_PARTIAL
    notice = ResolutionNotice(
        kind=kind,
        entries=notice_entries,
        text=_notice_text(
            kind, notice_entries, _display_label(selected_entry), selected.source, selected.level
        ),
    )
    return CoordinateResolution(record=record, notice=notice)


def resolve_coordinate_leaves(
    *,
    identity: ExamCoordinateIdentity,
    custom: ProfileIndexes,
    bundled: BundledCoordinateSet,
) -> CoordinateResolution:
    """Resolve all 15 coordinate leaves for one exam over the initial ladder.

    Prepares both compiled inputs (validating them once), runs the capability
    gate over the custom set, and resolves through :func:`resolve_with_prepared`.
    Callers resolving many exams prepare once and reuse :func:`resolve_with_prepared`.
    """
    checked_identity = _check_identity(identity)
    checked_custom, checked_bundled = _check_inputs(custom, bundled)
    prepared_custom = prepare_custom_context(checked_custom)
    prepared_bundled = prepare_bundled_context(checked_bundled)
    return resolve_with_prepared(
        identity=checked_identity, custom=prepared_custom, bundled=prepared_bundled
    )
