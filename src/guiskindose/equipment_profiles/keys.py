"""Canonical identity key algorithms for equipment profiles.

These reproduce the existing normalization key algorithms so the profile core stays stdlib-only and free of
normalization/dose/GUI imports, while parity tests pin them to ``guiskindose.settings.normalization_settings``.
The algorithm is: casefold, replace every run of characters outside ``[0-9a-z]`` with a single space, strip,
and collapse internal whitespace.
"""

from __future__ import annotations

import re

from guiskindose.equipment_profiles.constants import PLANE_WILDCARD

_NON_KEY_RUN = re.compile(r"[^0-9a-z]+")


def normalize_manufacturer_key(manufacturer: object) -> str:
    """Canonical manufacturer key for equipment-profile identity and matching."""
    key = _NON_KEY_RUN.sub(" ", str(manufacturer).casefold()).strip()
    return " ".join(key.split())


def normalize_model_key(model: object) -> str:
    """Canonical model key for equipment-profile identity and matching.

    The exact string ``"*"`` is the model wildcard and is preserved verbatim rather than canonicalized.
    """
    if str(model).strip() == PLANE_WILDCARD:
        return PLANE_WILDCARD
    key = _NON_KEY_RUN.sub(" ", str(model).casefold()).strip()
    return " ".join(key.split())


def is_wildcard_model(model: object) -> bool:
    """True when ``model`` is the preserved model wildcard."""
    return str(model).strip() == PLANE_WILDCARD
