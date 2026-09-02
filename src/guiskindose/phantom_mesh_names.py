"""Canonical human-mesh stem names, legacy aliases, labels, and sort order.

Shipped STL basenames under ``phantom_data/`` are the canonical stems. Legacy
stems from before the 2026-07-23 naming convention resolve via
``resolve_human_mesh_stem`` so Settings / CLI values keep working. Aliases
persist until a future SemVer **major** drop.

Arms-down variants append ``_arms_down`` and sort immediately after their
A-pose sibling. See ``dev-docs/plans/archive/PHANTOM_MESH_NAMING_CONVENTION_PLAN.md``
and ``dev-docs/plans/ARMS_DOWN_PHANTOM_VARIANTS_PLAN.md``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

# Stems are package-relative basenames only (no separators, dots, or parent refs).
_SAFE_HUMAN_MESH_STEM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

# Content-preserving renames (old stem → canonical on-disk stem).
HUMAN_MESH_ALIASES: dict[str, str] = {
    "pediatric_preschool_male": "ped_preschool_male",
    "pediatric_preschool_female": "ped_preschool_female",
    "pediatric_5y_male": "ped_5y_male",
    "pediatric_5y_female": "ped_5y_female",
    "pediatric_10y_male": "ped_10y_male",
    "pediatric_10y_female": "ped_10y_female",
    "adult_ectomorph_male": "adult_ecto_male",
    "adult_ectomorph_female": "adult_ecto_female",
    "adult_endomorph_male": "adult_endo_male",
    "adult_endomorph_female": "adult_endo_female",
    "bariatric_class2_male": "adult_bariatric_male_1",
    "bariatric_class2_female": "adult_bariatric_female_1",
    "bariatric_class2_male_thick_extremities": "adult_bariatric_male_2",
    "bariatric_class2_female_thick_extremities": "adult_bariatric_female_2",
    "bariatric_class2_male_extra_thick_extremities": "adult_bariatric_male_3",
    "bariatric_class2_female_extra_thick_extremities": "adult_bariatric_female_3",
    "cosmic_buddha": "demo_cosmic_buddha",
    "steamboat_willie": "demo_steamboat_willie",
    "ramesses_ii": "demo_ramesses_ii",
}

_REDUCED_SUFFIX = "_reduced_3000t"
_LEGACY_REDUCED_SUFFIXES = ("_reduced_1000t",)
# Prefer higher-detail previews when several companions exist.
_PREVIEW_REDUCED_SUFFIXES = (_REDUCED_SUFFIX, *_LEGACY_REDUCED_SUFFIXES)
_ARMS_DOWN_SUFFIX = "_arms_down"

# Demo / non-clinical (Settings only when show_demo_phantoms is on).
# Not currently shipped under phantom_data/; stems retained so a future re-add
# stays gated and aliases keep resolving. See tmp/phantom_data_demo_stash/README.md.
DEMO_HUMAN_MESHES: frozenset[str] = frozenset(
    {
        "demo_cosmic_buddha",
        "demo_steamboat_willie",
    }
)

# On disk but never listed in Settings (even with demos on).
# Retained for the same future-restore / alias reasons as DEMO_HUMAN_MESHES.
GUI_HIDDEN_HUMAN_MESHES: frozenset[str] = frozenset(
    {
        "demo_ramesses_ii",
    }
)

DEMO_MESH_SECTION_KEY = "__demo_section__"
DEMO_MESH_SECTION_LABEL = "── Demo ──"

_DEMO_DISPLAY_LABELS: dict[str, str] = {
    "demo_cosmic_buddha": "Cosmic Buddha (demo, headless)",
    "demo_ramesses_ii": "Ramesses II (demo)",
    "demo_steamboat_willie": "Steamboat Willie (demo)",
    "demo_petite_herculanaise": "Petite Herculanaise (demo)",
    # Legacy alias keys (if ever shown before canonicalize):
    "cosmic_buddha": "Cosmic Buddha (demo, headless)",
    "ramesses_ii": "Ramesses II (demo)",
    "steamboat_willie": "Steamboat Willie (demo)",
    "petite_herculanaise": "Petite Herculanaise (demo)",
}

# Human-readable Settings labels (canonical stems).
_CLINICAL_DISPLAY_LABELS: dict[str, str] = {
    "ped_preschool_male": "Pediatric Preschool Male",
    "ped_preschool_female": "Pediatric Preschool Female",
    "ped_5y_male": "Pediatric 5y Male",
    "ped_5y_female": "Pediatric 5y Female",
    "ped_10y_male": "Pediatric 10y Male",
    "ped_10y_female": "Pediatric 10y Female",
    "junior_male": "Junior Male",
    "junior_female": "Junior Female",
    "adult_male": "Adult Male",
    "adult_female": "Adult Female",
    "adult_ecto_male": "Adult Ectomorph Male",
    "adult_ecto_female": "Adult Ectomorph Female",
    "adult_endo_male": "Adult Endomorph Male",
    "adult_endo_female": "Adult Endomorph Female",
    "adult_bariatric_male_1": "Adult Bariatric Male (1 — abdomen)",
    "adult_bariatric_female_1": "Adult Bariatric Female (1 — abdomen)",
    "adult_bariatric_male_2": "Adult Bariatric Male (2 — thick extremities)",
    "adult_bariatric_female_2": "Adult Bariatric Female (2 — thick extremities)",
    "adult_bariatric_male_3": "Adult Bariatric Male (3 — extra-thick extremities)",
    "adult_bariatric_female_3": "Adult Bariatric Female (3 — extra-thick extremities)",
    "senior_male": "Senior Male",
    "senior_female": "Senior Female",
    "hudfrid": "Hudfrid",
}

# Explicit GUI clinical order (not alphabetical). Each ``_arms_down`` follows its sibling.
_CLINICAL_SORT_ORDER: tuple[str, ...] = (
    "ped_preschool_male",
    "ped_preschool_male_arms_down",
    "ped_preschool_female",
    "ped_preschool_female_arms_down",
    "ped_5y_male",
    "ped_5y_male_arms_down",
    "ped_5y_female",
    "ped_5y_female_arms_down",
    "ped_10y_male",
    "ped_10y_male_arms_down",
    "ped_10y_female",
    "ped_10y_female_arms_down",
    "junior_male",
    "junior_male_arms_down",
    "junior_female",
    "junior_female_arms_down",
    "adult_male",
    "adult_male_arms_down",
    "adult_female",
    "adult_female_arms_down",
    "adult_ecto_male",
    "adult_ecto_male_arms_down",
    "adult_ecto_female",
    "adult_ecto_female_arms_down",
    "adult_endo_male",
    "adult_endo_male_arms_down",
    "adult_endo_female",
    "adult_endo_female_arms_down",
    "adult_bariatric_male_1",
    "adult_bariatric_male_1_arms_down",
    "adult_bariatric_female_1",
    "adult_bariatric_female_1_arms_down",
    "adult_bariatric_male_2",
    "adult_bariatric_male_2_arms_down",
    "adult_bariatric_female_2",
    "adult_bariatric_female_2_arms_down",
    "adult_bariatric_male_3",
    "adult_bariatric_male_3_arms_down",
    "adult_bariatric_female_3",
    "adult_bariatric_female_3_arms_down",
    "senior_male",
    "senior_male_arms_down",
    "senior_female",
    "senior_female_arms_down",
    "hudfrid",
    "hudfrid_arms_down",
)


def package_phantom_data_dir() -> Path:
    """Return the resolved package ``phantom_data/`` directory."""
    return Path(__file__).resolve().parent / "phantom_data"


def assert_safe_human_mesh_stem(stem: str) -> str:
    """Return *stem* when it is a safe phantom basename; otherwise raise ``ValueError``.

    Rejects empty values, path separators, parent-directory references, and any
    characters outside the allow-listed stem alphabet so callers never join
    attacker-controlled path fragments under ``phantom_data/``.
    """
    if not isinstance(stem, str) or not stem:
        raise ValueError("human_mesh stem must be a non-empty string.")
    if Path(stem).name != stem or not _SAFE_HUMAN_MESH_STEM.fullmatch(stem):
        raise ValueError("human_mesh stem must be a simple phantom basename.")
    return stem


def resolve_human_mesh_stem(stem: str) -> str:
    """Return the canonical full-res or reduced stem for ``stem``.

    Legacy aliases map to new basenames. ``_reduced_3000t`` and legacy
    ``_reduced_1000t`` suffixes are preserved on the canonical base (both may
    ship). Unknown stems pass through unchanged after safety validation.
    """
    if not stem:
        return stem
    assert_safe_human_mesh_stem(stem)
    for suffix in _PREVIEW_REDUCED_SUFFIXES:
        if stem.endswith(suffix):
            base = stem[: -len(suffix)]
            assert_safe_human_mesh_stem(base)
            canonical = HUMAN_MESH_ALIASES.get(base, base)
            return f"{canonical}{suffix}"
    canonical = HUMAN_MESH_ALIASES.get(stem, stem)
    return canonical


def resolve_human_mesh_stl_path(stem: str, *, phantom_data_dir: Path | None = None) -> Path:
    """Resolve *stem* to an STL path confined under package ``phantom_data/``.

    Raises
    ------
    ValueError
        If *stem* contains path separators / parent references, resolves outside
        ``phantom_data/``, or does not name an existing ``.stl`` file.
    """
    resolved = resolve_human_mesh_stem(stem)
    assert_safe_human_mesh_stem(resolved)
    data_dir = (phantom_data_dir or package_phantom_data_dir()).resolve()
    candidate = (data_dir / f"{resolved}.stl").resolve()
    if not candidate.is_relative_to(data_dir):
        raise ValueError("human_mesh path escaped phantom_data/.")
    if not candidate.is_file():
        raise ValueError("Unknown human mesh stem.")
    return candidate


def prefer_reduced_preview_stem(stem: str, *, phantom_data_dir: Path | None = None) -> str:
    """Return the best available reduced companion for ``stem``, else the stem.

    Prefers ``_reduced_3000t`` over ``_reduced_1000t`` when both exist under
    package ``phantom_data/``. Existence checks stay confined under that root.
    """
    if not stem:
        return stem
    stem = resolve_human_mesh_stem(stem)
    for suffix in _PREVIEW_REDUCED_SUFFIXES:
        if stem.endswith(suffix):
            return stem
    data_dir = (phantom_data_dir or package_phantom_data_dir()).resolve()
    for suffix in _PREVIEW_REDUCED_SUFFIXES:
        candidate = f"{stem}{suffix}"
        try:
            assert_safe_human_mesh_stem(candidate)
        except ValueError:
            continue
        path = (data_dir / f"{candidate}.stl").resolve()
        if path.is_relative_to(data_dir) and path.is_file():
            return candidate
    return stem


def human_mesh_display_label(stem: str) -> str:
    """Settings-facing label for a canonical (or legacy) stem."""
    canonical = resolve_human_mesh_stem(stem)
    if canonical in _DEMO_DISPLAY_LABELS:
        return _DEMO_DISPLAY_LABELS[canonical]
    if canonical.endswith(_ARMS_DOWN_SUFFIX):
        base = canonical[: -len(_ARMS_DOWN_SUFFIX)]
        base_label = _CLINICAL_DISPLAY_LABELS.get(base, base.replace("_", " ").title())
        return f"{base_label} (arms down)"
    if canonical in _CLINICAL_DISPLAY_LABELS:
        return _CLINICAL_DISPLAY_LABELS[canonical]
    return canonical.replace("_", " ").title()


def sort_clinical_mesh_stems(stems: Iterable[str]) -> list[str]:
    """Order clinical stems by the naming-plan sort key; unknowns last (alpha)."""
    order = {name: i for i, name in enumerate(_CLINICAL_SORT_ORDER)}
    known: list[str] = []
    unknown: list[str] = []
    for stem in stems:
        if stem in order:
            known.append(stem)
        else:
            unknown.append(stem)
    known.sort(key=lambda s: order[s])
    unknown.sort()
    return known + unknown
