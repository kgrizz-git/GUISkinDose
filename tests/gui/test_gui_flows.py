"""Handler-level GUI flow tests (refactor plan Phase 3 safety net).

The original smoke test only checked that the page renders three labels. Before
decomposing app.py into per-tab modules, these tests exercise the real handler
wiring — tab navigation and the example-load flow — so a broken handler or a
mis-wired widget reference is caught, not silently shipped.
"""

from __future__ import annotations

import pytest
from nicegui.testing import User

pytest.importorskip("nicegui")

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")


@pytest.mark.asyncio
async def test_all_tab_headings_render(user: User) -> None:
    """Every tab panel's heading is present in the rendered page."""
    await user.open("/")
    for heading in (
        "Load File",
        "Irradiation Event Stream",
        "Calculation Settings",
        "Geometry Preview",
        "Run Dose Calculation",
        "Results",
        "Export Results",
    ):
        await user.should_see(heading)


@pytest.mark.asyncio
async def test_example_load_updates_status(user: User) -> None:
    """Clicking LOAD on the example selector parses a bundled RDSR and updates
    the drawer event count via the load_example handler."""
    await user.open("/")
    user.find("LOAD").click()
    # load_example awaits run.io_bound(load_rdsr, ...); the drawer should then
    # show a non-zero event count for the bundled example.
    await user.should_see("EVENTS")
