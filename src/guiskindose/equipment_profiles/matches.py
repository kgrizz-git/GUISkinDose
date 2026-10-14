"""Immutable per-exam match-record types for equipment profiles.

These types describe what a coordinate match resolved to, per leaf. They are snapshots: they hold tuples and
scalars, expose no mutable nested payload, and their ``repr`` is value-free for free-text fields. The
illustrative shape is pinned by ``dev-docs/EQUIPMENT_PROFILE_SCHEMA.md`` section 9.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from guiskindose.equipment_profiles.constants import (
    MATCH_DOMAIN_COORDINATE,
    MATCH_LEVEL_DEFAULT,
    MATCH_LEVEL_EXACT,
    MATCH_LEVEL_WILDCARD,
    MATCH_SOURCE_BUNDLED,
    MATCH_SOURCE_CUSTOM,
    MATCH_SOURCE_DEFAULT,
)
from guiskindose.equipment_profiles.keys import normalize_manufacturer_key, normalize_model_key
from guiskindose.equipment_profiles.models import LeafValue

MATCH_SOURCES = (MATCH_SOURCE_CUSTOM, MATCH_SOURCE_BUNDLED, MATCH_SOURCE_DEFAULT)
MATCH_LEVELS = (MATCH_LEVEL_EXACT, MATCH_LEVEL_WILDCARD, MATCH_LEVEL_DEFAULT)


@dataclass(frozen=True, slots=True)
class MatchedInputKey:
    """Canonical normalized identity that matched. Never a raw user spelling."""

    manufacturer: str
    model: str

    @classmethod
    def from_raw(cls, manufacturer: object, model: object) -> MatchedInputKey:
        """Build a canonical key from raw manufacturer/model values."""
        return cls(manufacturer=normalize_manufacturer_key(manufacturer), model=normalize_model_key(model))

    def as_mapping(self) -> dict[str, str]:
        """Return a fresh mapping; the record itself stays immutable."""
        return {"manufacturer": self.manufacturer, "model": self.model}


@dataclass(frozen=True, slots=True, repr=False)
class LeafProvenance:
    """Where one coordinate leaf's value came from.

    ``inherited`` is true whenever the value came from a candidate other than the selected **custom coordinate
    profile** — including a lower-priority custom wildcard.
    """

    field: str
    value: LeafValue
    source: str
    level: str
    profile_id: str
    source_kind: str
    profile_hash: str
    revision: int | None = None
    inherited: bool = False

    def __repr__(self) -> str:
        return (
            f"LeafProvenance(field={self.field!r}, value={self.value!r}, source={self.source!r}, "
            f"level={self.level!r}, profile_id={self.profile_id!r}, source_kind={self.source_kind!r}, "
            f"revision={self.revision!r}, inherited={self.inherited!r})"
        )


@dataclass(frozen=True, slots=True)
class CoordinateMatchRecord:
    """One immutable per-exam coordinate match record."""

    profile_id: str
    source: str
    level: str
    source_kind: str
    profile_hash: str
    matched_input_key: MatchedInputKey
    affected_event_count: int
    fields: tuple[LeafProvenance, ...] = ()
    revision: int | None = None
    domain: str = MATCH_DOMAIN_COORDINATE

    @property
    def inherited_fields(self) -> tuple[str, ...]:
        """Dotted paths of every leaf that was inherited rather than supplied by the selected profile."""
        return tuple(item.field for item in self.fields if item.inherited)

    @property
    def is_complete_match(self) -> bool:
        """True when no leaf was inherited."""
        return not any(item.inherited for item in self.fields)

    def leaf(self, dotted_path: str) -> LeafProvenance | None:
        """Return the provenance for one dotted leaf path, or ``None``."""
        for item in self.fields:
            if item.field == dotted_path:
                return item
        return None

    def __iter__(self) -> Iterator[LeafProvenance]:
        return iter(self.fields)

    def __len__(self) -> int:
        return len(self.fields)


def build_leaf_provenance(
    *,
    dotted_path: str,
    value: LeafValue,
    profile_id: str,
    source: str,
    level: str,
    source_kind: str,
    profile_hash: str,
    is_selected_profile: bool,
    revision: int | None = None,
) -> LeafProvenance:
    """Build one leaf-provenance entry, deriving ``inherited`` from the selected-profile test."""
    return LeafProvenance(
        field=dotted_path,
        value=value,
        source=source,
        level=level,
        profile_id=profile_id,
        source_kind=source_kind,
        profile_hash=profile_hash,
        revision=revision,
        inherited=not is_selected_profile,
    )


def order_leaf_provenance(records: tuple[LeafProvenance, ...], order: tuple[str, ...]) -> tuple[LeafProvenance, ...]:
    """Return ``records`` reordered to follow ``order``, appending any unknown paths last."""
    rank = {path: index for index, path in enumerate(order)}
    return tuple(sorted(records, key=lambda item: (rank.get(item.field, len(rank)), item.field)))
