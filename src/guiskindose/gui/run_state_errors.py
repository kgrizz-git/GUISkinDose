"""Run-state reader errors (moved unchanged from ``gui.run_state``).

``RunStateError`` lives here so the equipment-envelope boundary and future
run-state readers share one error identity without importing the full
document assembly module. ``gui.run_state`` re-exports the name, so existing
``from guiskindose.gui.run_state import RunStateError`` imports — and the
class identity, codes, and messages — are unchanged.
"""

from __future__ import annotations

__all__ = ["RunStateError"]


class RunStateError(ValueError):
    """Raised when a run-state document cannot be applied.

    Carries a stable machine-readable `code` so callers can map failures to
    fixed user-facing messages without exposing document text (privacy).
    Every raise site passes an explicit code; structural problems use
    "malformed_document" via `_malformed()`.
    """

    def __init__(self, message: str, code: str = "malformed_document") -> None:
        super().__init__(message)
        self.code = code
