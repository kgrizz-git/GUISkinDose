"""Shared UI constants for the GUI (refactor plan Phase 3.3).

Pure, dependency-light option lists and lookups used by more than one tab.
They live here — below both ``app.py`` and the ``tabs/*`` modules in the import
graph — so per-tab modules can import them without pulling in ``app`` (which
imports the tab modules), avoiding a circular import.
"""

from __future__ import annotations

from .helpers import get_example_rdsr_files, get_human_mesh_names

HUMAN_MESHES = get_human_mesh_names()

# Bundled example RDSR files, keyed by filename. The synthetic "fake_scanner.dcm"
# is demoted to last so a real scanner is the default selection (dict insertion
# order drives the select's default value).
EXAMPLE_FILES = {
    p.name: p
    for p in sorted(
        get_example_rdsr_files(),
        key=lambda p: (p.name == "fake_scanner.dcm", p.name),
    )
}
COLORSCALES = ["jet", "viridis", "plasma", "inferno", "magma", "turbo", "hot"]
PHANTOM_MODELS = ["human", "cylinder", "plane"]
ORIENTATIONS = ["head_first_supine", "feet_first_supine"]

# Geometry offset sliders (interactive table offsets plan Phase 2 / 2b)
PATIENT_OFFSET_SLIDER_RANGE_CM = 150
TABLE_ORIGIN_SLIDER_MIN = -250
TABLE_ORIGIN_SLIDER_MAX = 250
GEOMETRY_DEBOUNCE_SEC = 0.25
MAX_INLINE_MAPS = 5
