"""Built-in vendor manufacturer alias allowlist for equipment identity.

This is the single home of the bundled alias policy: the canonical settings
key maps to every accepted spelling of that maker. Both the runtime
normalization settings and the canonical bundled-profile adapter read this
module, so the two layers can never drift apart — and custom profiles can
never inherit these aliases, because aliases reach an index only as explicit
per-profile ``manufacturer_aliases``.

Stdlib-only, like the rest of the core: nothing here imports settings, GUI,
calculation, or any application layer.
"""

from __future__ import annotations

__all__ = [
    "GE_MANUFACTURER_ALIASES",
    "MANUFACTURER_ALIASES_BY_SETTINGS_KEY",
    "aliases_for_settings_key",
]

#: Accepted spellings of the GE maker family, keyed under ``"ge healthcare"``.
#: Membership is exact on the canonical key (not a substring check), so values
#: like ``"Surgery Equipment"`` are never treated as GE.
GE_MANUFACTURER_ALIASES = frozenset(
    {
        "ge",
        "gehealthcare",
        "ge healthcare",
        "ge medical systems",
        "general electric",
        "gems",
    }
)

#: Canonical settings key -> accepted canonical alias spellings (self included).
MANUFACTURER_ALIASES_BY_SETTINGS_KEY: dict[str, frozenset[str]] = {
    "ge healthcare": GE_MANUFACTURER_ALIASES,
    "siemens": frozenset(
        {
            "siemens",
            "siemens healthcare",
            "siemens healthineers",
            "siemens medical solutions",
            "siemens ag",
        }
    ),
    "philips": frozenset(
        {
            "philips",
            "philips healthcare",
            "philips medical systems",
            "philips medical systems nederland b v",
            "philips medical systems nederland bv",
        }
    ),
}


def aliases_for_settings_key(settings_key: str) -> tuple[str, ...]:
    """Sorted alias spellings for a canonical settings key, or ``()`` when unknown."""
    return tuple(sorted(MANUFACTURER_ALIASES_BY_SETTINGS_KEY.get(settings_key, frozenset())))
