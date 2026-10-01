"""Peak-skin-dose severity bands and their presentation classes.

Single source of truth for how a PSD value is coloured and named. Every GUI
readout of PSD routes through here so the four call sites cannot drift apart.
Colour is never the only carrier: a banded readout is an icon + value + tooltip
trio (:class:`PsdReadout`), and all three move together.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final, NamedTuple

from .ui_copy import copy_text

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

# Default row classes for a readout that sits in a centred metric card.
_CENTERED_ROW_CLASSES: Final = "items-center justify-center gap-2"


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


class PsdReadout(NamedTuple):
    """The element handles that make up one banded PSD readout.

    A readout is never a bare number. Colour alone is unreadable for the most
    common colour-vision deficiencies, so the value always travels with a band
    icon and a band-name tooltip; bundling the three is what stops one of them
    being left behind when the band changes.
    """

    row: ui.row
    icon: ui.icon
    value: ui.label
    tooltip: ui.tooltip


def build_psd_readout(
    text: str, *, label_classes: str, row_classes: str = _CENTERED_ROW_CLASSES
) -> PsdReadout:
    """Build the icon + value + tooltip trio of a banded PSD readout, pending.

    ``text`` is whatever the site shows before any dose exists ("—" on Results,
    ``PSD: —`` in the sidebar). The tooltip is created here and targeted at the
    row rather than attached per update: nicegui's ``Element.tooltip()``
    constructs a brand-new ``q-tooltip`` element on every call, so re-calling it
    would stack one more tooltip on each band change instead of updating it.
    """
    from nicegui import ui  # local import on purpose: nicegui is an optional extra
    # and this is the only function here that needs it at run time. The band
    # logic stays importable (and unit-testable) in the core CI matrix, which is
    # why the module-level import is TYPE_CHECKING-only.

    with ui.row().classes(row_classes) as row:
        icon = ui.icon("").classes(f"icon-outlined {psd_text_class(None)}")
        # ui.icon("") still renders an empty glyph box, so the pending band
        # hides the icon rather than naming an empty symbol.
        icon.set_visibility(False)
        value = ui.label(text).classes(f"{label_classes} {psd_text_class(None)}")
        tooltip = ui.tooltip(copy_text(psd_band_copy_key(None)))
        tooltip.props(f"target=#{row.html_id}")
    return PsdReadout(row=row, icon=icon, value=value, tooltip=tooltip)


def apply_psd_presentation(readout: PsdReadout, psd: float | None) -> None:
    """Move colour, icon, and tooltip of ``readout`` to ``psd``'s band at once.

    The three carriers move together because any one of them left behind would
    contradict the other two, and because colour must never be the only carrier.
    """
    apply_psd_band(readout.value, psd)
    apply_psd_band(readout.icon, psd)
    icon_name = psd_band_icon(psd)
    readout.icon.set_name(icon_name)
    readout.icon.set_visibility(bool(icon_name))
    readout.tooltip.set_text(copy_text(psd_band_copy_key(psd)))


def reset_psd_label(readout: PsdReadout) -> None:
    """Return a PSD readout to its not-calculated state."""
    readout.value.set_text(PSD_PENDING_TEXT)
    apply_psd_presentation(readout, None)
