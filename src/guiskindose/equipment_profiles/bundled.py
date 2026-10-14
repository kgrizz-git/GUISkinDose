"""Boundary adapter: legacy normalization-settings entries to canonical bundled profiles.

The legacy source (``normalization_settings.json``) lives outside the canonical
core. This narrow adapter converts its entries — mappings with ``manufacturer``,
``models``, and the six coordinate blocks — into validated canonical profiles,
compiles the non-Default entries into a conflict-checked coordinate index, and
keeps the ``Default`` entry as a separate last fallback.

Determinism: profile IDs derive from the canonical maker/model keys
(``bundled-<maker>-<model>``, wildcard models as ``wildcard``), so the same
entries always compile to the same IDs, canonical payloads, and content
hashes. The bundled source kind is ``json``, matching the match-record
contract (schema §9): the entries originate from a JSON document.

Built-in vendor maker aliases attach ONLY here, as explicit per-profile
``manufacturer_aliases`` drawn from the shared allowlist
(:mod:`vendor_aliases`) — the same sets runtime matching has always used, so
``GE Medical Systems`` still reaches the ``GE Healthcare`` wildcard. Custom
profiles can never inherit these aliases. ``Default`` stays unaliased and out
of the index: it is an unconditional fallback, not a claimable slot.

Omitted ``swap_lateral_longitudinal`` materializes as ``False`` on every entry,
preserving the runtime default (which applies it to each chosen bundled entry)
with honest provenance. No transmission rows
are converted: bundled transmission stays out of this slice.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from guiskindose.equipment_profiles.canonical import profile_hash
from guiskindose.equipment_profiles.constants import (
    MAX_MODELS,
    MAX_PROFILES,
    SCHEMA_VERSION,
    SOURCE_KIND_JSON,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.equipment_profiles.indexes import IndexedProfile, ProfileIndexes, build_profile_indexes
from guiskindose.equipment_profiles.keys import normalize_manufacturer_key, normalize_model_key
from guiskindose.equipment_profiles.validation import validate_document
from guiskindose.equipment_profiles.vendor_aliases import aliases_for_settings_key

__all__ = [
    "BundledCoordinateSet",
    "bundled_coordinate_set",
    "bundled_profile_id",
]

#: Profile-ID safe spelling: runs outside the accepted set collapse to one dash.
_ID_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True, repr=False)
class BundledCoordinateSet:
    """Compiled bundled coordinates: exact/wildcard index plus separate Default.

    The repr shows counts only — never profile IDs, hashes, or entry context.
    """

    exact: ProfileIndexes
    default: IndexedProfile | None
    profiles: tuple[IndexedProfile, ...]

    def __repr__(self) -> str:
        return f"BundledCoordinateSet(profiles={len(self.profiles)}, has_default={self.default is not None})"


def _sanitize_id_part(text: str) -> str:
    """Collapse one key to profile-ID spelling (pattern ``[A-Za-z0-9._-]+``)."""
    return _ID_SANITIZE_RE.sub("-", text).strip("-") or "unknown"


def bundled_profile_id(manufacturer: str, models: Sequence[object]) -> str:
    """Deterministic bundled profile ID from canonical maker/model keys.

    ``bundled-<maker>-<model>`` with ID-safe spelling, where ``<model>`` is
    the first key of the canonically sorted model keys (``wildcard`` for the
    model wildcard) — so reordered model lists compile to identical IDs,
    payloads, and hashes. Never echoes raw spellings beyond their normalized
    keys.
    """
    maker_part = _sanitize_id_part(normalize_manufacturer_key(manufacturer))
    keys = sorted(
        {normalize_model_key(model) for model in models if isinstance(model, (str, int, float))}
    )
    if not keys:
        keys = [normalize_model_key(models[0])] if models else ["unknown"]
    first = keys[0]
    model_part = "wildcard" if first.strip() == "*" else _sanitize_id_part(first)
    return f"bundled-{maker_part}-{model_part}"


def _materialize_entries(entries: Any) -> list[Any]:
    """Copy the input under ``MAX_PROFILES`` before any conversion or validation.

    A declared length above the cap fails before anything is copied, and
    materialization re-checks the cap item by item so an inaccurate length
    cannot force unbounded work (same pattern as the index layer).
    """
    if isinstance(entries, (str, bytes, bytearray)) or not isinstance(entries, Sequence):
        raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind=SOURCE_KIND_JSON, field_path=())
    try:
        declared = len(entries)
    except TypeError:
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind=SOURCE_KIND_JSON, field_path=()
        ) from None
    if declared > MAX_PROFILES:
        raise EquipmentProfileError(
            ProfileErrorCode.PROFILE_LIMIT_EXCEEDED,
            source_kind=SOURCE_KIND_JSON,
            field_path=(),
            count=declared,
        )
    raw: list[Any] = []
    for item in entries:
        raw.append(item)
        if len(raw) > MAX_PROFILES:
            raise EquipmentProfileError(
                ProfileErrorCode.PROFILE_LIMIT_EXCEEDED,
                source_kind=SOURCE_KIND_JSON,
                field_path=(),
                count=len(raw),
            )
    return raw


def _require_models(models: Any) -> Sequence[Any]:
    """Bound the model list before the profile ID reads it.

    The full shape/range validation still runs later through the existing
    boundary; this only caps how much is converted up front.
    """
    if isinstance(models, (str, bytes)) or not isinstance(models, Sequence):
        raise EquipmentProfileError(
            ProfileErrorCode.INVALID_TYPE, source_kind=SOURCE_KIND_JSON, field_path=("models",)
        )
    if len(models) > MAX_MODELS:
        raise EquipmentProfileError(
            ProfileErrorCode.MODEL_LIMIT_EXCEEDED,
            source_kind=SOURCE_KIND_JSON,
            field_path=("models",),
            count=len(models),
        )
    return models


def _require_entry_mapping(entry: Any) -> Mapping[str, Any]:
    """Reject non-mapping entries with a closed error before any key is read."""
    if not isinstance(entry, Mapping):
        raise EquipmentProfileError(ProfileErrorCode.INVALID_TYPE, source_kind=SOURCE_KIND_JSON, field_path=())
    return entry


def _entry_manufacturer(entry: Mapping[str, Any]) -> str:
    """The entry's maker spelling, or a closed error when absent/blank."""
    maker = entry.get("manufacturer")
    if not isinstance(maker, str) or not maker.strip():
        raise EquipmentProfileError(
            ProfileErrorCode.MISSING_REQUIRED_FIELD, source_kind=SOURCE_KIND_JSON, field_path=("manufacturer",)
        )
    return maker


def _is_default_entry(maker: str) -> bool:
    """True for the ``Default`` fallback entry (same rule as runtime matching)."""
    return maker.strip().casefold() == "default"


def _coordinate_mapping(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Project the six coordinate blocks, materializing the legacy swap default.

    Runtime selection applies ``bool(setting.get("swap_lateral_longitudinal",
    False))`` to EVERY chosen bundled entry, so an omitted switch behaves as
    ``False`` — including on exact entries. Materializing it here preserves
    those exact semantics with honest provenance (an exact entry lacking swap
    must not inherit a wildcard entry's ``True``) and makes every shipped
    bundled entry complete.
    """
    coordinates: dict[str, Any] = {}
    for block in (
        "translation_offset",
        "translation_direction",
        "rotation_direction",
        "field_size_mode",
        "detector_side_length",
    ):
        if block in entry:
            coordinates[block] = entry[block]
    coordinates["swap_lateral_longitudinal"] = entry.get("swap_lateral_longitudinal", False)
    return coordinates


def _profile_mapping(entry: Mapping[str, Any], models: Sequence[Any]) -> dict[str, Any]:
    """Raw v1 profile mapping for one bundled entry; validated by the caller."""
    maker = _entry_manufacturer(entry)
    mapping: dict[str, Any] = {
        "profile_id": bundled_profile_id(maker, models),
        "manufacturer": maker,
        "models": list(models),
        "coordinates": _coordinate_mapping(entry),
    }
    if not _is_default_entry(maker):
        # Built-in vendor aliases attach ONLY to bundled profiles, drawn from
        # the shared allowlist — never inherited by custom claims.
        mapping["manufacturer_aliases"] = list(
            aliases_for_settings_key(normalize_manufacturer_key(maker))
        )
    return mapping


def _validate_bundled(mapping: dict[str, Any]) -> IndexedProfile:
    """Validate one bundled mapping through the existing boundary and hash it."""
    profiles = validate_document(
        {"schema_version": SCHEMA_VERSION, "profiles": [mapping]}, source_kind=SOURCE_KIND_JSON
    )
    profile = profiles[0]
    return IndexedProfile(
        profile=profile, source_kind=SOURCE_KIND_JSON, revision=None, profile_hash=profile_hash(profile)
    )


def bundled_coordinate_set(entries: Sequence[Mapping[str, Any]]) -> BundledCoordinateSet:
    """Compile legacy settings entries into a bundled coordinate set.

    Bounds run before any conversion: at most ``MAX_PROFILES`` entries
    (Default included) are materialized, and each model list is capped before
    its profile ID is derived. Non-Default entries are then validated, hashed,
    and compiled into a conflict-checked index; the ``Default`` entry (when
    present) is validated and kept separate as the unconditional last
    fallback. A second ``Default`` entry fails closed as a duplicate profile
    ID. Raises value-free errors.
    """
    exact: list[IndexedProfile] = []
    default: IndexedProfile | None = None
    for raw in _materialize_entries(entries):
        entry = _require_entry_mapping(raw)
        maker = _entry_manufacturer(entry)
        models = _require_models(entry.get("models"))
        compiled = _validate_bundled(_profile_mapping(entry, models))
        if _is_default_entry(maker):
            if default is not None:
                raise EquipmentProfileError(
                    ProfileErrorCode.DUPLICATE_PROFILE_ID,
                    source_kind=SOURCE_KIND_JSON,
                    field_path=("profile_id",),
                )
            default = compiled
        else:
            exact.append(compiled)
    return BundledCoordinateSet(
        exact=build_profile_indexes(exact),
        default=default,
        profiles=tuple(sorted(exact, key=lambda item: item.profile.profile_id)),
    )
