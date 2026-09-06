"""Geometry tab public module — re-exports controller, refs, builders, and figure helper.

``geometry.py`` remains the thin entry point imported by ``app.py``.
"""

from __future__ import annotations

from ..figures import make_geometry_fig
from .geometry_controller import GeometryTabController
from .geometry_layout_builders import build, build_geometry_tab
from .geometry_view_refs import GeometryViewRefs

__all__ = [
    "GeometryTabController",
    "GeometryViewRefs",
    "build",
    "build_geometry_tab",
    "make_geometry_fig",
]
