"""Upload tab — thin public entry point.

All layout, controller, and callback logic lives in
:mod:`~mypyskindose.gui.tabs.upload_builders`.  This module re-exports
:func:`build`, :data:`MAX_UPLOAD_BYTES`, and :func:`upload_exceeds_limit`
so existing import paths (tests, ``app.py``) continue to work.
"""

from __future__ import annotations

from .upload_builders import (  # noqa: F401  (re-exports)
    MAX_UPLOAD_BYTES,
    build,
    upload_exceeds_limit,
)

__all__ = ["MAX_UPLOAD_BYTES", "build", "upload_exceeds_limit"]
