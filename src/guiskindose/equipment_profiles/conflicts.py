"""Across-source duplicate and conflict validation for equipment profiles.

The rules are deliberately strict: identities, IDs, and transmission keys must be unique even when the
duplicated content is byte-identical. No ordering rule is used to break a tie, so input order can affect only
deterministic diagnostics. Profile IDs are compared exactly; coordinate identities are compared through the
normalized manufacturer/model key algorithms; transmission keys are compared on the normalized model key so
they are independent of manufacturer, case, and punctuation.

Two kinds of profile do not collide with each other. A profile with **no coordinate content** claims no
coordinate slot, so a transmission-only and a coordinate-only profile may share an identity safely. A profile
with **no transmission content** contributes no transmission key, so a coordinate-only and a
transmission-only profile may share an identity safely too. What cannot overlap is two profiles claiming the
*same* coordinate slot, or two profiles carrying the *same* transmission key.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from guiskindose.equipment_profiles.constants import MATCH_DOMAIN_COORDINATE
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.equipment_profiles.keys import normalize_manufacturer_key, normalize_model_key
from guiskindose.equipment_profiles.models import Profile


def coordinate_identity_claims(profile: Profile) -> tuple[tuple[str, str], ...]:
    """Normalized ``(manufacturer, model)`` slots this profile claims, or ``()`` for no coordinate content.

    A transmission-only profile claims no coordinate slot. Otherwise every canonical and alias spelling of
    both axes expands to a claim: each listed model, each mapped model alias, and the whole manufacturer list
    (canonical manufacturer plus every manufacturer alias).
    """
    if profile.coordinates is None or profile.coordinates.is_empty():
        return ()
    manufacturer_keys = [normalize_manufacturer_key(profile.manufacturer)]
    manufacturer_keys.extend(normalize_manufacturer_key(alias) for alias in profile.manufacturer_aliases)
    model_keys = {normalize_model_key(model) for model in profile.models}
    for alias, target in profile.model_aliases:
        if normalize_model_key(target) in model_keys:
            model_keys.add(normalize_model_key(alias))
        else:  # pragma: no cover - validation rejects an unresolvable alias target
            model_keys.add(normalize_model_key(target))
    manufacturers = tuple(dict.fromkeys(key for key in manufacturer_keys if key))
    models = tuple(sorted(key for key in model_keys if key))
    return tuple((manufacturer, model) for manufacturer in manufacturers for model in models)


def transmission_key_claims(profile: Profile) -> tuple[tuple[str, str, float, float, float], ...]:
    """Normalized transmission keys this profile contributes.

    The model component is the normalized model key, so a duplicate is detected regardless of manufacturer,
    case, or punctuation.
    """
    return tuple(
        (
            normalize_model_key(row.device_model),
            row.acquisition_plane,
            row.kvp_kv,
            row.filtration_added_mmcu,
            row.filtration_added_mmal,
        )
        for row in profile.transmission
    )


def validate_profile_set(profiles: Sequence[Profile], *, source_kind: str) -> None:
    """Reject duplicate IDs, duplicate coordinate claims, and duplicate transmission keys.

    Duplicates fail even when the duplicated content is identical, within a single document and across
    documents, because there is no ordering rule that could pick a winner.
    """
    identities: set[str] = set()
    coordinate_claims: dict[tuple[str, str], str] = {}
    transmission_keys: dict[tuple[str, str, float, float, float], str] = {}
    for profile in profiles:
        if profile.profile_id in identities:
            raise EquipmentProfileError(
                ProfileErrorCode.DUPLICATE_PROFILE_ID,
                source_kind=source_kind,
                field_path=("profile_id",),
            )
        identities.add(profile.profile_id)
        for claim in coordinate_identity_claims(profile):
            if claim in coordinate_claims:
                raise EquipmentProfileError(
                    ProfileErrorCode.DUPLICATE_COORDINATE_CLAIM,
                    source_kind=source_kind,
                    field_path=("manufacturer", "models"),
                )
            coordinate_claims[claim] = profile.profile_id
        for key in transmission_key_claims(profile):
            if key in transmission_keys:
                raise EquipmentProfileError(
                    ProfileErrorCode.DUPLICATE_TRANSMISSION_KEY,
                    source_kind=source_kind,
                    field_path=("transmission",),
                )
            transmission_keys[key] = profile.profile_id


def collect_identity_collisions(profiles: Iterable[Profile]) -> tuple[tuple[str, str], ...]:
    """Return the coordinate identities claimed by more than one profile (diagnostics helper)."""
    counts: dict[tuple[str, str], int] = {}
    for profile in profiles:
        for claim in coordinate_identity_claims(profile):
            counts[claim] = counts.get(claim, 0) + 1
    return tuple(sorted(claim for claim, total in counts.items() if total > 1))


def first_match_domain(profile: Profile) -> str | None:
    """Return the match domain this profile could contribute to, or ``None`` when it supplies neither."""
    if coordinate_identity_claims(profile):
        return MATCH_DOMAIN_COORDINATE
    if profile.transmission:
        return "transmission"
    return None


__all__ = [
    "collect_identity_collisions",
    "coordinate_identity_claims",
    "first_match_domain",
    "transmission_key_claims",
    "validate_profile_set",
]
