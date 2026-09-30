"""Peak-skin-dose severity bands and their presentation classes.

Single source of truth for how a PSD value is coloured and named. Every GUI
readout of PSD routes through here so the four call sites cannot drift apart.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:  # nicegui is an optional extra; the core CI matrix has no `gui`
    from nicegui import ui

# Band edges in mGy. The upper edge belongs to the higher band, so exactly
# 5000 mGy is "elevated" and exactly 10000 mGy is "high" — the conservative
# reading. See the SRDL note in the plan before changing these.
PSD_BAND_ELEVATED_MGY: Final = 5000.0
PSD_BAND_HIGH_MGY: Final = 10000.0

_BANDS: Final = ("pending", "low", "elevated", "high")
_TEXT_CLASSES: Final = {band: f"text-dose-{band}" for band in _BANDS}
_ALL_TEXT_CLASSES: Final = " ".join(_TEXT_CLASSES.values())
_ICONS: Final = {"pending": "", "low": "check_circle", "elevated": "warning", "high": "error"}
# Spelled out rather than built with an f-string so the keys are greppable, and so
# scripts/check_ui_copy.py can see them: these are reached via psd_band_copy_key(), never
# as a literal copy_text argument, so a generated key would read as unused forever.
_COPY_KEYS: Final = {
    "pending": "results.psd_band.pending",
    "low": "results.psd_band.low",
    "elevated": "results.psd_band.elevated",
    "high": "results.psd_band.high",
}

# Shown wherever a PSD has not been calculated, in place of a misleading "0.00 mGy".
PSD_PENDING_TEXT: Final = "PSD: —"


def psd_band(psd: float | None) -> str:
    """Severity band for a PSD in mGy: pending / low / elevated / high.

    ``None`` and any non-finite value are ``"pending"`` — nothing has been
    calculated, or what was calculated is not a number. A negative value
    cannot occur physically but maps to ``"low"`` rather than raising.
    """
    if psd is None:
        return "pending"
    try:
        value = float(psd)
    except (TypeError, ValueError):
        return "pending"
    if not math.isfinite(value):
        return "pending"
    if value >= PSD_BAND_HIGH_MGY:
        return "high"
    if value >= PSD_BAND_ELEVATED_MGY:
        return "elevated"
    return "low"


def psd_text_class(psd: float | None) -> str:
    """Tailwind-style text colour class for ``psd``'s band."""
    return _TEXT_CLASSES[psd_band(psd)]


def psd_band_icon(psd: float | None) -> str:
    """Material symbol name for ``psd``'s band; empty string when pending."""
    return _ICONS[psd_band(psd)]


def psd_band_copy_key(psd: float | None) -> str:
    """``dev-docs/ui_copy.json`` key naming ``psd``'s band and its range."""
    return _COPY_KEYS[psd_band(psd)]


def apply_psd_band(element: ui.element, psd: float | None) -> None:
    """Swap ``element``'s severity class to the one matching ``psd``.

    The whole class family is removed first: NiceGUI appends classes, so
    re-banding without a remove would leave two colours fighting.
    """
    element.classes(remove=_ALL_TEXT_CLASSES, add=psd_text_class(psd))


def reset_psd_label(label: ui.label) -> None:
    """Return the sidebar PSD readout to its not-calculated state."""
    label.set_text(PSD_PENDING_TEXT)
    apply_psd_band(label, None)
