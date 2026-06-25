"""Shared per-page widget context for the decomposed GUI (refactor plan Phase 3.1a).

`index()` in app.py builds the whole page and ~21 nested handlers as closures.
To split those handlers into per-tab modules, the handlers must reach the
*cross-cutting* widgets (drawer status labels, the run button, the tab strip)
and the two shared upload refreshers without closing over `index()`'s scope.

`PageContext` is that hand-off: a small mutable dataclass of widget handles,
constructed in `index()` once the cross-cutting chrome exists and passed to every
extracted builder/handler. It is intentionally **not** ``frozen=True`` — the two
refresher callables are not known when the context is first built (the upload tab
defines them later), so they default to no-ops and are reassigned once the upload
tab is built. That breaks the handler call-cycle without freezing.

Annotated with concrete NiceGUI types so basedpyright flags any handler that
references a field that does not exist — the main automated safety net for the
mechanical rename.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from nicegui import ui


def _noop() -> None:
    """Default refresher before the upload tab wires the real callables."""


@dataclass
class PageContext:
    # cross-cutting chrome (set at construction)
    tabs: ui.tabs
    file_label: ui.label
    events_label: ui.label
    psd_label: ui.label
    run_btn_drawer: ui.button
    # shared refresh callbacks — default to no-op, reassigned by index() after
    # the upload tab is built; this breaks the cross-handler call cycle.
    refresh_event_table: Callable[[], None] = field(default=_noop)
    refresh_import_preview: Callable[[], None] = field(default=_noop)
    # per-exam corrections section lives under the Settings tab; the upload tab's
    # loaded-files summary calls this so loading/removing an exam re-renders the
    # editable controls. Default no-op until the settings tab is built.
    refresh_per_exam: Callable[[], None] = field(default=_noop)
    # loaded-files summary card in the upload tab; restore tail calls this too.
    refresh_exams_table: Callable[[], None] = field(default=_noop)
    # Geometry tab registers this to clear the stale-dose caption after a successful calc.
    clear_offset_stale_caption: Callable[[], None] = field(default=_noop)
    # Geometry tab registers this so Settings changes that affect phantom geometry
    # can request the same debounced preview refresh used by Geometry controls.
    refresh_geometry_preview: Callable[[], None] = field(default=_noop)
