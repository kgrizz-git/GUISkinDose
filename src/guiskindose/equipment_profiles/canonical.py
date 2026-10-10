"""Deterministic canonical serialization and SHA-256 hashing for equipment profiles.

Canonical form is UTF-8 JSON with recursively sorted keys, compact separators, and no insignificant
whitespace. Numeric *value* fields are normalized to IEEE-754 doubles and serialized as floats; negative zero
normalizes to ``+0.0``. ``schema_version`` stays an integer. Empty optional texts, empty alias arrays and
objects, empty coordinate blocks, an empty ``transmission`` array, and ``promote_coordinate_wildcard: false``
are omitted entirely, so they contribute nothing to a hash.

Two wrappers are defined: the profile hash covers ``{"schema_version": 1, "profile": ...}`` and the active-set
hash covers ``{"schema_version": 1, "profiles": [...]}`` with profiles ordered by exact ``profile_id``.
Provenance is inside the profile hash; source context (source kind, source bytes, store revision) never is.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Sequence
from typing import Any

from guiskindose.equipment_profiles.constants import (
    ACQUISITION_PLANES,
    AXIS_FIELDS,
    DETECTOR_SIDE_LENGTH,
    FIELD_SIZE_MODE,
    ROTATION_LEAVES,
    SCHEMA_VERSION,
    SWAP_LATERAL_LONGITUDINAL,
    TRANSLATION_DIRECTION,
    TRANSLATION_OFFSET,
)
from guiskindose.equipment_profiles.models import (
    Coordinates,
    Profile,
    Provenance,
    TransmissionRow,
)

_HEX_DIGEST_LENGTH = 64


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize ``value`` to the canonical UTF-8 JSON byte form."""
    text = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return text.encode("utf-8")


def _normalized_float(value: float) -> float:
    """Return ``value`` as a finite float with negative zero normalized to ``+0.0``."""
    result = float(value)
    if result == 0.0:
        return 0.0
    return result


def _axis_numbers(block: object) -> dict[str, float]:
    return {
        name: _normalized_float(getattr(block, name)) for name in AXIS_FIELDS if getattr(block, name) is not None
    }


def _axis_signs(block: object) -> dict[str, str]:
    return {name: getattr(block, name) for name in AXIS_FIELDS if getattr(block, name) is not None}


def _rotation_signs(block: object) -> dict[str, str]:
    return {
        json_name: getattr(block, field_name)
        for field_name, json_name in ROTATION_LEAVES
        if getattr(block, field_name) is not None
    }


def coordinates_dict(coordinates: Coordinates | None) -> dict[str, Any]:
    """Canonical mapping for a coordinate domain, or an empty mapping when absent."""
    if coordinates is None:
        return {}
    result: dict[str, Any] = {}
    if coordinates.translation_offset is not None:
        result[TRANSLATION_OFFSET] = _axis_numbers(coordinates.translation_offset)
    if coordinates.translation_direction is not None:
        result[TRANSLATION_DIRECTION] = _axis_signs(coordinates.translation_direction)
    if coordinates.rotation_direction is not None:
        result["rotation_direction"] = _rotation_signs(coordinates.rotation_direction)
    if coordinates.swap_lateral_longitudinal is not None:
        result[SWAP_LATERAL_LONGITUDINAL] = bool(coordinates.swap_lateral_longitudinal)
    if coordinates.field_size_mode is not None:
        result[FIELD_SIZE_MODE] = coordinates.field_size_mode
    if coordinates.detector_side_length is not None:
        result[DETECTOR_SIDE_LENGTH] = _normalized_float(coordinates.detector_side_length)
    return result


def transmission_row_dict(row: TransmissionRow) -> dict[str, Any]:
    """Canonical mapping for one transmission row."""
    result: dict[str, Any] = {
        "device_model": row.device_model,
        "acquisition_plane": row.acquisition_plane,
        "kvp_kv": _normalized_float(row.kvp_kv),
        "filtration_added_mmcu": _normalized_float(row.filtration_added_mmcu),
        "filtration_added_mmal": _normalized_float(row.filtration_added_mmal),
        "k_patient_support": _normalized_float(row.k_patient_support),
        "evidence_status": row.evidence_status,
    }
    if row.source is not None:
        result["source"] = row.source
    if row.date is not None:
        result["date"] = row.date
    if row.comment is not None:
        result["comment"] = row.comment
    return result


def _transmission_key(row: TransmissionRow) -> tuple[str, int, float, float, float]:
    """Sort key for transmission rows: target model, plane order, then the numeric part of the key."""
    plane = row.acquisition_plane
    plane_rank = ACQUISITION_PLANES.index(plane) if plane in ACQUISITION_PLANES else len(ACQUISITION_PLANES)
    return (row.device_model, plane_rank, row.kvp_kv, row.filtration_added_mmcu, row.filtration_added_mmal)


def canonical_aliases(pairs: tuple[tuple[str, str], ...]) -> dict[str, str]:
    """Canonical alias map: alias spelling -> listed canonical model spelling.

    This is a JSON object, the shape the parser accepts for an explicit alias map, so canonical output
    round-trips through the parser to an identical profile hash. Pairs are emitted in sorted alias order;
    JSON key sorting makes the written form sorted too.
    """
    return dict(sorted(pairs))


def canonical_transmission_rows(rows: Iterable[TransmissionRow]) -> list[dict[str, Any]]:
    """Canonical, canonically ordered list of transmission rows."""
    return [transmission_row_dict(row) for row in sorted(rows, key=_transmission_key)]


def provenance_dict(provenance: Provenance | None) -> dict[str, Any]:
    """Canonical mapping for provenance; empty when absent or fully blank."""
    if provenance is None:
        return {}
    result: dict[str, Any] = {}
    if provenance.source is not None:
        result["source"] = provenance.source
    if provenance.notes is not None:
        result["notes"] = provenance.notes
    return result


def canonical_profile_dict(profile: Profile) -> dict[str, Any]:
    """Canonical mapping for one profile, with empty optional values omitted."""
    result: dict[str, Any] = {
        "profile_id": profile.profile_id,
        "manufacturer": profile.manufacturer,
        "models": sorted(profile.models),
    }
    if profile.manufacturer_aliases:
        result["manufacturer_aliases"] = sorted(profile.manufacturer_aliases)
    if profile.model_aliases:
        result["model_aliases"] = canonical_aliases(profile.model_aliases)
    provenance = provenance_dict(profile.provenance)
    if provenance:
        result["provenance"] = provenance
    coordinates = coordinates_dict(profile.coordinates)
    if coordinates:
        result["coordinates"] = coordinates
    if profile.transmission:
        result["transmission"] = canonical_transmission_rows(profile.transmission)
    if profile.promote_coordinate_wildcard:
        result["promote_coordinate_wildcard"] = True
    return result


def profile_wrapper(profile: Profile) -> dict[str, Any]:
    """Wrapper for a single-profile hash."""
    return {"schema_version": SCHEMA_VERSION, "profile": canonical_profile_dict(profile)}


def active_set_wrapper(profiles: Sequence[Profile]) -> dict[str, Any]:
    """Wrapper for an active-set hash, profiles ordered by exact ``profile_id``."""
    ordered = sorted(profiles, key=lambda item: item.profile_id)
    return {"schema_version": SCHEMA_VERSION, "profiles": [canonical_profile_dict(item) for item in ordered]}


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def profile_hash(profile: Profile) -> str:
    """SHA-256 over the canonical bytes of the single-profile wrapper."""
    return _sha256_hex(canonical_json_bytes(profile_wrapper(profile)))


def active_set_hash(profiles: Sequence[Profile]) -> str:
    """SHA-256 over the canonical bytes of the active-set wrapper."""
    return _sha256_hex(canonical_json_bytes(active_set_wrapper(profiles)))


def source_bytes_hash(raw_bytes: bytes) -> str:
    """SHA-256 over the exact bytes read from a file source, before any decoding."""
    return _sha256_hex(raw_bytes)
