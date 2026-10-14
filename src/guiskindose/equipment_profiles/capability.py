"""The initial coordinate activation capability gate.

The parser represents the full v1 schema, including capability fields this slice cannot apply. Activation
checks capabilities separately and fails closed with a stable code and a closed-vocabulary capability token, so
nothing is silently dropped and nothing is partially applied. Enabled here: exact ``manufacturer``/``model``
coordinate identity and leaf-level inheritance within that exact match.
"""

from __future__ import annotations

from collections.abc import Sequence

from guiskindose.equipment_profiles.constants import (
    CAPABILITY_COORDINATE_WILDCARD_PROMOTION,
    CAPABILITY_MANUFACTURER_ALIAS,
    CAPABILITY_MODEL_ALIAS,
    CAPABILITY_MODEL_WILDCARD,
    CAPABILITY_TRANSMISSION_DOMAIN,
)
from guiskindose.equipment_profiles.errors import EquipmentProfileError, ProfileErrorCode
from guiskindose.equipment_profiles.keys import is_wildcard_model
from guiskindose.equipment_profiles.models import Profile

#: Capabilities rejected by the initial gate, checked in this order.
UNSUPPORTED_CAPABILITIES = (
    CAPABILITY_MANUFACTURER_ALIAS,
    CAPABILITY_MODEL_ALIAS,
    CAPABILITY_MODEL_WILDCARD,
    CAPABILITY_COORDINATE_WILDCARD_PROMOTION,
    CAPABILITY_TRANSMISSION_DOMAIN,
)

#: A profile's first rejected capability, or ``None`` when the initial gate accepts it.
def first_unsupported_capability(profile: Profile) -> str | None:
    """Return the closed-vocabulary capability token this profile needs but the gate refuses."""
    if profile.manufacturer_aliases:
        return CAPABILITY_MANUFACTURER_ALIAS
    if profile.model_aliases:
        return CAPABILITY_MODEL_ALIAS
    if any(is_wildcard_model(model) for model in profile.models):
        return CAPABILITY_MODEL_WILDCARD
    if profile.promote_coordinate_wildcard:
        return CAPABILITY_COORDINATE_WILDCARD_PROMOTION
    if profile.transmission:
        return CAPABILITY_TRANSMISSION_DOMAIN
    return None


def check_initial_capabilities(profiles: Sequence[Profile], *, source_kind: str) -> None:
    """Reject any profile needing a capability the initial coordinate slice cannot apply.

    Runs as a separate step from parsing and conflict validation, so a caller can load and inspect profiles
    that the gate will refuse. Raises :class:`EquipmentProfileError` with code
    ``unsupported_profile_capability`` and the capability token.
    """
    for profile in profiles:
        capability = first_unsupported_capability(profile)
        if capability is not None:
            raise EquipmentProfileError(
                ProfileErrorCode.UNSUPPORTED_PROFILE_CAPABILITY,
                source_kind=source_kind,
                capability=capability,
            )


def supported_profiles(profiles: Sequence[Profile]) -> tuple[Profile, ...]:
    """Return only the profiles the initial gate would accept (inspection helper)."""
    return tuple(profile for profile in profiles if first_unsupported_capability(profile) is None)
