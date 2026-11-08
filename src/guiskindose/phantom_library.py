"""Per-user phantom library paths and two-root STL resolution.

Shipped meshes under package ``phantom_data/`` take precedence over the optional
user library. Resolution order is defined only in :func:`resolve_mesh_stl_path`.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

from guiskindose.phantom_mesh_names import (
    _PREVIEW_REDUCED_SUFFIXES,
    _REDUCED_SUFFIX,
    DEMO_HUMAN_MESHES,
    GUI_HIDDEN_HUMAN_MESHES,
    assert_safe_human_mesh_stem,
    is_clinical_catalog_stem,
    resolve_human_mesh_stem,
)
from guiskindose.privacy import UserFacingInputError

_WINDOWS_LIBRARY_UNAVAILABLE = (
    "The phantom library cannot be used because the local application data folder is not configured."
)


class PhantomLibraryUnavailableError(UserFacingInputError):
    """The per-OS user mesh library path cannot be resolved on this host."""


def _win32_file_attributes(path: Path) -> int:
    import ctypes

    return int(ctypes.windll.kernel32.GetFileAttributesW(str(path)))  # type: ignore[attr-defined]


def _win32_has_reparse_point(path: Path) -> bool:
    """True when Windows reports a reparse point (a junction or symlink) at *path*; False off Windows or on error."""
    try:
        attrs = _win32_file_attributes(path)
    except (AttributeError, OSError):
        return False
    if attrs == 0xFFFFFFFF:
        return False
    return bool(attrs & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT


def _path_is_library_link(path: Path, platform: str | None = None) -> bool:
    """True when *path* must not be used as a writable library root."""
    if path.is_symlink():
        return True
    plat = platform or sys.platform
    if plat != "win32" or not path.exists():
        return False
    is_junction = getattr(os.path, "isjunction", None)
    if plat == "win32" and callable(is_junction):
        return bool(is_junction(path))
    if plat == "win32":
        return _win32_has_reparse_point(path)
    return False

_DARWIN_PHANTOM_SUBPATH = ("Library", "Application Support", "GUISkinDose", "phantoms")
_WIN32_PHANTOM_PARTS = ("GUISkinDose", "phantoms")
_LINUX_DATA_HOME_DEFAULT = (".local", "share", "guiskindose", "phantoms")


def user_library_dir_for_platform(
    platform: str,
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the per-OS phantom library directory (may not exist yet).

    Raises
    ------
    PhantomLibraryUnavailableError
        On Windows when ``LOCALAPPDATA`` is unset (fixed sentence only).
    """
    env = dict(os.environ if environ is None else environ)
    home_path = home if home is not None else Path.home()
    if platform == "darwin":
        return home_path.joinpath(*_DARWIN_PHANTOM_SUBPATH)
    if platform == "win32":
        local = env.get("LOCALAPPDATA")
        if not local:
            raise PhantomLibraryUnavailableError(_WINDOWS_LIBRARY_UNAVAILABLE)
        return Path(local).joinpath(*_WIN32_PHANTOM_PARTS)
    data_home = env.get("XDG_DATA_HOME")
    if data_home:
        return Path(data_home).joinpath("guiskindose", "phantoms")
    return home_path.joinpath(*_LINUX_DATA_HOME_DEFAULT)


def default_user_library_dir() -> Path | None:
    """Return the user library path, or ``None`` when the OS location is undefined."""
    try:
        return user_library_dir_for_platform(sys.platform)
    except PhantomLibraryUnavailableError:
        return None


def _clinical_base_stem(stem: str) -> str:
    """Strip preview reduced suffixes so demo/hidden rules apply to companions."""
    for suffix in _PREVIEW_REDUCED_SUFFIXES:
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def _regular_stl_in_root(root: Path, stem: str) -> Path | None:
    """Return root/<stem>.stl when it is a regular, non-link file inside *root*, else None. Filesystem errors count as missing."""
    try:
        assert_safe_human_mesh_stem(stem)
    except ValueError:
        return None
    path = root / f"{stem}.stl"
    if path.is_symlink():
        return None
    try:
        root_resolved = root.resolve()
        candidate = path.resolve()
        if not candidate.is_relative_to(root_resolved):
            return None
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    except OSError:
        return None
    return None


def shipped_mesh_stl_path(stem: str, *, shipped_dir: Path) -> Path | None:
    """Return the shipped STL path when present as a regular file, else ``None``."""
    return _regular_stl_in_root(shipped_dir, stem)


def user_library_mesh_stl_path(stem: str, *, user_library_dir: Path | None) -> Path | None:
    """Return the user-library STL when present; ``None`` if the root is unavailable."""
    if user_library_dir is None:
        return None
    return _regular_stl_in_root(user_library_dir, stem)


def resolve_mesh_stl_path(
    stem: str,
    *,
    shipped_dir: Path,
    user_library_dir: Path | None = None,
    show_demo_phantoms: bool = False,
) -> Path:
    """Resolve *stem* using shipped-first, then user-library rules.

    Callers must pass stems through :func:`resolve_human_mesh_stem` first.
    """
    resolved = resolve_human_mesh_stem(stem)
    assert_safe_human_mesh_stem(resolved)
    base_stem = _clinical_base_stem(resolved)

    is_demo_or_hidden = base_stem in DEMO_HUMAN_MESHES or base_stem in GUI_HIDDEN_HUMAN_MESHES
    if not is_demo_or_hidden:
        shipped = shipped_mesh_stl_path(resolved, shipped_dir=shipped_dir)
        if shipped is not None:
            return shipped

    if is_demo_or_hidden:
        if resolved in DEMO_HUMAN_MESHES and show_demo_phantoms:
            demo_shipped = shipped_mesh_stl_path(resolved, shipped_dir=shipped_dir)
            if demo_shipped is not None:
                return demo_shipped
        raise ValueError("Unknown human mesh stem.")

    if is_clinical_catalog_stem(resolved):
        user_path = user_library_mesh_stl_path(resolved, user_library_dir=user_library_dir)
        if user_path is not None:
            return user_path
        raise _MissingClinicalMesh(resolved)

    raise ValueError("Unknown human mesh stem.")


class _MissingClinicalMesh(Exception):
    """Internal signal that a clinical stem has no STL in either root."""

    def __init__(self, stem: str) -> None:
        self.stem = stem


def prefer_reduced_stem_for_preview(
    stem: str,
    *,
    shipped_dir: Path,
    user_library_dir: Path | None = None,
) -> str:
    """Prefer ``_reduced_3000t`` then legacy ``_reduced_1000t`` from either root (shipped first)."""
    if not stem:
        return stem
    stem = resolve_human_mesh_stem(stem)
    for suffix in _PREVIEW_REDUCED_SUFFIXES:
        if stem.endswith(suffix):
            return stem
    for suffix in _PREVIEW_REDUCED_SUFFIXES:
        candidate = f"{stem}{suffix}"
        if shipped_mesh_stl_path(candidate, shipped_dir=shipped_dir) is not None:
            return candidate
        in_library = user_library_mesh_stl_path(candidate, user_library_dir=user_library_dir) is not None
        if in_library and is_clinical_catalog_stem(_clinical_base_stem(candidate)):
            return candidate
    return stem


def installed_full_clinical_stems(
    *,
    shipped_dir: Path,
    user_library_dir: Path | None = None,
) -> list[str]:
    """Return canonical full-resolution clinical stems present in either root."""
    from guiskindose.phantom_mesh_names import _CLINICAL_SORT_ORDER, sort_clinical_mesh_stems

    installed: list[str] = []
    for catalog_stem in _CLINICAL_SORT_ORDER:
        if any(catalog_stem.endswith(s) for s in _PREVIEW_REDUCED_SUFFIXES):
            continue
        try:
            resolve_mesh_stl_path(
                catalog_stem,
                shipped_dir=shipped_dir,
                user_library_dir=user_library_dir,
            )
        except (ValueError, _MissingClinicalMesh):
            continue
        installed.append(catalog_stem)
    return sort_clinical_mesh_stems(installed)


def is_reduced_preview_suffix_stem(stem: str) -> bool:
    """True when *stem* ends with a known reduced preview suffix."""
    return any(stem.endswith(suffix) for suffix in _PREVIEW_REDUCED_SUFFIXES)


def pack_allowed_reduced_suffix(stem: str) -> bool:
    """True when *stem* is a ``_reduced_3000t`` companion allowed in packs."""
    return stem.endswith(_REDUCED_SUFFIX)
