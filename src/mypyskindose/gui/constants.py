"""Shared UI constants for the GUI (refactor plan Phase 3.3).

Pure, dependency-light option lists and lookups used by more than one tab.
They live here — below both ``app.py`` and the ``tabs/*`` modules in the import
graph — so per-tab modules can import them without pulling in ``app`` (which
imports the tab modules), avoiding a circular import.
"""

from __future__ import annotations

from .helpers import get_example_rdsr_files, get_human_mesh_names

HUMAN_MESHES = get_human_mesh_names()
EXAMPLE_FILES = {p.name: p for p in get_example_rdsr_files()}
COLORSCALES = ["jet", "viridis", "plasma", "inferno", "magma", "turbo", "hot"]
PHANTOM_MODELS = ["human", "cylinder", "plane"]
ORIENTATIONS = ["head_first_supine", "feet_first_supine"]
