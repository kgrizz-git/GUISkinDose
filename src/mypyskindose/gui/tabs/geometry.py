"""Geometry preview tab — thin public entry point.

All layout, controller, and callback logic lives in
:mod:`~mypyskindose.gui.tabs.geometry_builders`.  This module re-exports
:func:`build` and the ``geometry_vendor_notice`` helper so existing
import paths (``app.py``, tests) continue to work.
"""

from __future__ import annotations

from ..geometry_preview import geometry_vendor_notice  # noqa: F401  (re-export)
from .geometry_builders import build  # noqa: F401  (re-export)

__all__ = ["build", "geometry_vendor_notice"]
