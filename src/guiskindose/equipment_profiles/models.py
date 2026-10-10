"""Immutable typed canonical models for equipment profiles.

Every model is a frozen dataclass holding only tuples, scalars, and other frozen models: no list, dict, or
set is exposed, so a parsed profile cannot be mutated by a caller and no mutable payload leaks in. The
generated ``repr`` is suppressed wherever a field holds bounded free text (provenance ``source``/``notes``,
transmission ``source``/``comment``), because that text is local to the profile and must not reach logs or
diagnostics through a repr.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from guiskindose.equipment_profiles.constants import (
    AXIS_FIELDS,
    COORDINATE_BLOCKS,
    COORDINATE_LEAF_COUNT,
    ROTATION_LEAVES,
    TRANSLATION_DIRECTION,
    TRANSLATION_OFFSET,
)
from guiskindose.equipment_profiles.keys import normalize_manufacturer_key, normalize_model_key

#: A coordinate leaf value: a number, a sign string, or a boolean.
LeafValue = float | str | bool


@dataclass(frozen=True, slots=True, repr=False)
class Provenance:
    """Bounded provenance text. Repr is suppressed because the text is profile-local."""

    source: str | None = None
    notes: str | None = None

    def is_empty(self) -> bool:
        """True when no bounded text survives canonicalization."""
        return self.source is None and self.notes is None

    def __repr__(self) -> str:
        return "<Provenance suppressed>"


@dataclass(frozen=True, slots=True)
class TranslationOffset:
    """Optional per-axis translation offsets in cm."""

    x: float | None = None
    y: float | None = None
    z: float | None = None


@dataclass(frozen=True, slots=True)
class TranslationDirection:
    """Optional per-axis translation signs."""

    x: str | None = None
    y: str | None = None
    z: str | None = None


@dataclass(frozen=True, slots=True)
class RotationDirection:
    """Optional per-angle rotation signs."""

    ap1: str | None = None
    ap2: str | None = None
    ap3: str | None = None
    at1: str | None = None
    at2: str | None = None
    at3: str | None = None


@dataclass(frozen=True, slots=True)
class Coordinates:
    """Six optional coordinate blocks holding 15 individually optional leaves."""

    translation_offset: TranslationOffset | None = None
    translation_direction: TranslationDirection | None = None
    rotation_direction: RotationDirection | None = None
    swap_lateral_longitudinal: bool | None = None
    field_size_mode: str | None = None
    detector_side_length: float | None = None

    def is_empty(self) -> bool:
        """True when no coordinate leaf is supplied."""
        return not coordinate_leaf_values(self)


@dataclass(frozen=True, slots=True, repr=False)
class TransmissionRow:
    """One patient-support transmission row. Matching key is target model + plane + kVp + Cu + Al."""

    device_model: str
    acquisition_plane: str
    kvp_kv: float
    filtration_added_mmcu: float
    filtration_added_mmal: float
    k_patient_support: float
    evidence_status: str
    source: str | None = None
    date: str | None = None
    comment: str | None = None

    @property
    def key(self) -> tuple[str, str, float, float, float]:
        """Transmission matching key, independent of manufacturer."""
        return (
            self.device_model,
            self.acquisition_plane,
            self.kvp_kv,
            self.filtration_added_mmcu,
            self.filtration_added_mmal,
        )

    def __repr__(self) -> str:
        return (
            f"TransmissionRow(device_model={self.device_model!r}, "
            f"acquisition_plane={self.acquisition_plane!r}, kvp_kv={self.kvp_kv}, "
            f"filtration_added_mmcu={self.filtration_added_mmcu}, "
            f"filtration_added_mmal={self.filtration_added_mmal}, "
            f"k_patient_support={self.k_patient_support}, "
            f"evidence_status={self.evidence_status!r})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class Profile:
    """One immutable canonical equipment profile.

    ``repr`` shows only counts and identifiers. It never shows provenance text, transmission source or
    comment text, or any raw canonical payload.
    """

    profile_id: str
    manufacturer: str
    models: tuple[str, ...]
    manufacturer_aliases: tuple[str, ...] = ()
    model_aliases: tuple[tuple[str, str], ...] = ()
    provenance: Provenance | None = None
    coordinates: Coordinates | None = None
    transmission: tuple[TransmissionRow, ...] = ()
    promote_coordinate_wildcard: bool = False

    @property
    def identity_claims(self) -> tuple[tuple[str, str], ...]:
        """Normalized ``(manufacturer, model)`` coordinate-identity claims, wildcards included."""
        manufacturer_key = normalize_manufacturer_key(self.manufacturer)
        return tuple((manufacturer_key, normalize_model_key(model)) for model in self.models)

    @property
    def has_wildcard_model(self) -> bool:
        """True when ``models`` is exactly the single model wildcard."""
        return self.models == ("*",)

    def coordinate_leaves(self) -> tuple[tuple[str, LeafValue], ...]:
        """Every supplied coordinate leaf as ``(dotted_path, value)``."""
        return coordinate_leaf_values(self.coordinates)

    def canonical_dict(self) -> dict[str, object]:
        """The profile's canonical mapping (see ``canonical.canonical_profile_dict``).

        Imported lazily so this module keeps no dependency on the serializer.
        """
        from guiskindose.equipment_profiles.canonical import canonical_profile_dict

        return canonical_profile_dict(self)

    def logical_row_count(self) -> int:
        """Logical rows for the aggregate ceiling: profile + coordinate leaves + transmission rows."""
        return 1 + len(self.coordinate_leaves()) + len(self.transmission)

    def __repr__(self) -> str:
        return (
            f"Profile(profile_id={self.profile_id!r}, models={len(self.models)}, "
            f"manufacturer_aliases={len(self.manufacturer_aliases)}, "
            f"model_aliases={len(self.model_aliases)}, "
            f"coordinate_leaves={len(self.coordinate_leaves())}, "
            f"transmission_rows={len(self.transmission)}, "
            f"promote_coordinate_wildcard={self.promote_coordinate_wildcard})"
        )


@dataclass(frozen=True, slots=True)
class ProfileSet:
    """A validated, immutable set of profiles plus the load-level counters."""

    profiles: tuple[Profile, ...] = ()
    logical_rows: int = 0
    source_kinds: tuple[str, ...] = ()

    def __len__(self) -> int:
        return len(self.profiles)

    def __iter__(self) -> Iterator[Profile]:
        return iter(self.profiles)


def _axis_leaves(
    block_name: str, block: object | None, field_names: tuple[str, ...]
) -> tuple[tuple[str, LeafValue], ...]:
    """Yield ``(path, value)`` for each supplied leaf of an axis-shaped block."""
    if block is None:
        return ()
    leaves: list[tuple[str, LeafValue]] = []
    for name in field_names:
        value = getattr(block, name)
        if value is not None:
            leaves.append((f"{block_name}.{name}", value))
    return tuple(leaves)


def _rotation_leaves(block: RotationDirection | None) -> tuple[tuple[str, LeafValue], ...]:
    if block is None:
        return ()
    leaves: list[tuple[str, LeafValue]] = []
    for field_name, json_name in ROTATION_LEAVES:
        value = getattr(block, field_name)
        if value is not None:
            leaves.append((f"rotation_direction.{json_name}", value))
    return tuple(leaves)


def _scalar_leaves(coordinates: Coordinates) -> tuple[tuple[str, LeafValue], ...]:
    leaves: list[tuple[str, LeafValue]] = []
    if coordinates.swap_lateral_longitudinal is not None:
        leaves.append(("swap_lateral_longitudinal", coordinates.swap_lateral_longitudinal))
    if coordinates.field_size_mode is not None:
        leaves.append(("field_size_mode", coordinates.field_size_mode))
    if coordinates.detector_side_length is not None:
        leaves.append(("detector_side_length", coordinates.detector_side_length))
    return tuple(leaves)


def coordinate_leaf_values(coordinates: Coordinates | None) -> tuple[tuple[str, LeafValue], ...]:
    """Every supplied coordinate leaf as ``(dotted_path, value)``, in canonical documentation order."""
    if coordinates is None:
        return ()
    parts = (
        _axis_leaves(TRANSLATION_OFFSET, coordinates.translation_offset, AXIS_FIELDS),
        _axis_leaves(TRANSLATION_DIRECTION, coordinates.translation_direction, AXIS_FIELDS),
        _rotation_leaves(coordinates.rotation_direction),
        _scalar_leaves(coordinates),
    )
    return tuple(leaf for part in parts for leaf in part)


def supplied_coordinate_blocks(coordinates: Coordinates | None) -> tuple[str, ...]:
    """Names of the coordinate blocks that supply at least one leaf."""
    if coordinates is None:
        return ()
    return tuple(name for name in COORDINATE_BLOCKS if _block_is_supplied(coordinates, name))


def _block_is_supplied(coordinates: Coordinates, name: str) -> bool:
    return getattr(coordinates, name) is not None


def total_leaf_capacity() -> int:
    """Leaf capacity of a fully specified profile."""
    return COORDINATE_LEAF_COUNT
