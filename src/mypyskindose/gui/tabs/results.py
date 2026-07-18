"""Results tab — thin public entry point.

All layout, controller, and callback logic lives in
:mod:`~mypyskindose.gui.tabs.results_builders`.  This module re-exports
:func:`build` and the pure helper functions so existing import paths
(tests, ``app.py``) continue to work.
"""

from __future__ import annotations

from .results_builders import (  # noqa: F401  (re-exports)
    build,
    can_show_more_inline,
    compute_subset_aggregate,
    multi_exam_results_ui_stale,
)

__all__ = [
    "build",
    "can_show_more_inline",
    "compute_subset_aggregate",
    "multi_exam_results_ui_stale",
]
