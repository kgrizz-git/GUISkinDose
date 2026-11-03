"""Light and Full editions of the portable app (``dev-docs/plans/PORTABLE_APP_PLAN.md``).

Both editions run the same code. They differ in two ways:

- **Light** ships a starter set of clinical phantoms and no browser, so PNG dose-map
  export is off. The PNG render functions check :func:`png_export_available` before
  they build a figure, so Kaleido never looks for a browser.
- **Full** ships every clinical phantom and, in the frozen app, a bundled Chromium.

Neither app edition ships the legacy ``_reduced_1000t`` previews. The pip wheel keeps
its full ``phantom_data/`` tree and reports the ``full`` edition.

The include lists here drive the freeze spec, so the spec and the runtime agree on
what Light contains.
"""

from __future__ import annotations

from collections.abc import Iterable

EDITION_LIGHT = "light"
EDITION_FULL = "full"
EDITIONS = (EDITION_LIGHT, EDITION_FULL)

# Proposed Light set (PORTABLE_APP_PLAN.md -> "Proposed Light set"): an adult, a
# pediatric, and a larger-habitus case, with both poses and the preferred preview.
LIGHT_BASE_MESHES: tuple[str, ...] = (
    "hudfrid",
    "adult_male",
    "adult_female",
    "ped_5y_male",
    "ped_5y_female",
    "adult_bariatric_male_1",
    "adult_bariatric_female_1",
)
_POSES = ("", "_arms_down")
_LIGHT_SUFFIXES = ("", "_reduced_3000t")
EXCLUDED_PREVIEW_SUFFIX = "_reduced_1000t"

PNG_UNAVAILABLE_MESSAGE = "PNG dose-map images are not available in GUISkinDose Light."


class PngExportUnavailableError(RuntimeError):
    """Raised by PNG render helpers that must fail loudly in the Light edition."""

    def __init__(self) -> None:
        super().__init__(PNG_UNAVAILABLE_MESSAGE)


def current_edition() -> str:
    """Return ``"light"`` or ``"full"``. Any other value fails closed as ``"light"``."""
    from guiskindose import _edition

    value = getattr(_edition, "EDITION", None)
    return value if value in EDITIONS else EDITION_LIGHT


def is_light() -> bool:
    """True when this copy is the Light edition."""
    return current_edition() == EDITION_LIGHT


def png_export_available() -> bool:
    """True when PNG dose-map rendering may start a browser."""
    return not is_light()


def light_phantom_stl_names() -> list[str]:
    """Every STL file name in the Light payload, sorted."""
    return sorted(
        f"{base}{pose}{suffix}.stl" for base in LIGHT_BASE_MESHES for pose in _POSES for suffix in _LIGHT_SUFFIXES
    )


def full_phantom_stl_names(available: Iterable[str]) -> list[str]:
    """Every STL name in *available* except the legacy ``_reduced_1000t`` previews."""
    return sorted(name for name in available if not name.endswith(f"{EXCLUDED_PREVIEW_SUFFIX}.stl"))


def edition_phantom_stl_names(edition: str, available: Iterable[str]) -> list[str]:
    """STL names a frozen *edition* ships, picked from the *available* package files.

    Raises ``ValueError`` for an unknown edition, or when a Light file is missing, so a
    freeze never ships a partial starter set.
    """
    names = sorted(available)
    if edition == EDITION_FULL:
        return full_phantom_stl_names(names)
    if edition != EDITION_LIGHT:
        raise ValueError(f"unknown edition {edition!r}")
    wanted = light_phantom_stl_names()
    missing = sorted(set(wanted).difference(names))
    if missing:
        raise ValueError(f"Light phantom files missing: {missing}")
    return wanted
