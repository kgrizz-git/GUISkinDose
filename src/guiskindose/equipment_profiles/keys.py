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

#: Raw texts that are missing-value artifacts, never a real maker or model.
#: Shared stdlib-only convention: blank, ``None``-stringified, and NaN/NaT
#: artifacts all mean missing identity and must never become matchable keys.
MISSING_IDENTITY_TEXTS = frozenset({"", "nan", "nat", "none"})


def clean_identity_text(value: str | None) -> str | None:
    """Strip one identity text, or ``None`` when it carries no identity.

    ``None``, blank strings, and case-insensitive ``"nan"``/``"nat"``/``"none"``
    artifacts all map to ``None``. Anything else keeps its exact spelling (no
    case folding); key normalization happens later, separately.
    """
    if value is None:
        return None
    text = value.strip()
    if not text or text.casefold() in MISSING_IDENTITY_TEXTS:
        return None
    return text


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
