"""Testable host-platform seam for ``entry.py`` (stdlib only).

``entry.py`` imports ``host_platform`` so unit tests can patch ``_override`` without
changing ``sys.platform`` (which would alter asyncio's loop policy in xdist workers).
"""

from __future__ import annotations

import sys

_override: str | None = None


def host_platform() -> str:
    """Return ``_override`` when a test set it, else ``sys.platform``."""
    if _override is not None:
        return _override
    return sys.platform
