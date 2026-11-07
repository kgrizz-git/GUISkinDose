"""In-memory mesh measurement caches shared by GUI helpers and pack install."""

from __future__ import annotations

from collections.abc import Iterable

_MESH_EXTENT_CACHE: dict[str, tuple[float, float, float]] = {}
_MESH_TORSO_WIDTH_CACHE: dict[str, float] = {}


def clear_mesh_measurement_caches_for_stems(stems: Iterable[str]) -> None:
    """Drop cached extents/torso width after a mesh is installed or replaced."""
    for stem in stems:
        _MESH_EXTENT_CACHE.pop(stem, None)
        _MESH_TORSO_WIDTH_CACHE.pop(stem, None)
