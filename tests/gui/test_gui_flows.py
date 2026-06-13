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
    """Selecting a bundled example auto-loads it (no LOAD button) and updates the
    drawer event count via the load_example handler."""
    await user.open("/")
    # Open the example dropdown and click an option, the way a user would; the
    # select auto-loads on selection (no LOAD button). Clicking (not set_value)
    # runs the handler inside the NiceGUI client context, so its run.io_bound
    # load actually executes. Wait for the menu option to render before clicking
    # — clicking immediately races the dropdown open and no-ops on slower CI.
    user.find(marker="example-select").click()
    await user.should_see("philips_allura_clarity_u104.dcm", retries=20)
    user.find("philips_allura_clarity_u104.dcm").click()
    # load_example awaits run.io_bound(load_rdsr, ...); the drawer then shows a
    # non-zero event count. should_see defaults to only 3 retries (~0.3s), which
    # the async load can outlast on slower CI runners, so allow generous retries.
    await user.should_see("EVENTS", retries=50)
