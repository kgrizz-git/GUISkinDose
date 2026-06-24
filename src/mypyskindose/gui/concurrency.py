"""GUI concurrency helpers (refactor plan Phase 3.3f).

NiceGUI runs async handlers on a single event loop, but each handler awaits
``run.io_bound()``, yielding control while blocking work runs on a worker thread.
Two handlers can therefore be in flight at once and interleave their writes to
the shared ``state`` singleton. ``operation_guard`` makes the second operation
bail out with a notice instead. The check-and-set has no await between the read
and the write, so it is race-free under asyncio's cooperative scheduling.

Also holds the upload serialisation lock: ``ui.upload(multiple=True)`` fires
``on_upload`` once per selected file, and NiceGUI dispatches those handlers
concurrently. The lock queues them so additional files load one-by-one instead
of tripping the busy-guard.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Iterator

from nicegui import ui

from .state import state

# Serialises concurrent upload handlers (see module docstring).
upload_lock = asyncio.Lock()


@contextmanager
def operation_guard(label: str) -> Iterator[bool]:
    """Yield True if the operation may proceed, False if one is already running."""
    if state.busy:
        ui.notify(
            f"Busy — please wait for the current operation to finish before {label}.",
            type="warning",
        )
        yield False
        return
    state.busy = True
    try:
        yield True
    finally:
        state.busy = False
