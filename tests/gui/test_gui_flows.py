"""Handler-level GUI flow tests (refactor plan Phase 3 safety net).

The original smoke test only checked that the page renders three labels. Before
decomposing app.py into per-tab modules, these tests exercise the real handler
wiring — tab navigation and the example-load flow — so a broken handler or a
mis-wired widget reference is caught, not silently shipped.

NiceGUI `User`-test gotchas (trigger via .click() not set_value; wait for lazy
elements; generous should_see retries for awaited background work) are documented
in dev-docs/HARNESS_ENGINEERING.md → "Writing NiceGUI User tests — gotchas".
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from nicegui import ui
from nicegui.testing import User

import mypyskindose.gui.tabs.geometry as geometry_tab
from mypyskindose.gui.constants import GEOMETRY_DEBOUNCE_SEC
from mypyskindose.gui.state import state

pytest.importorskip("nicegui")

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")

PHILIPS_EXAMPLE = "philips_allura_clarity_u104.dcm"


async def _load_philips_example(user: User) -> None:
    await user.open("/")
    user.find(marker="example-select").click()
    await user.should_see(PHILIPS_EXAMPLE, retries=20)
    user.find(PHILIPS_EXAMPLE).click()
    await user.should_see("EVENTS", retries=50)


async def _open_geometry_tab(user: User) -> None:
    user.find("4 · Geometry").click()
    await user.should_see("Setup view", retries=50)


def _install_make_fig_counter(monkeypatch: pytest.MonkeyPatch) -> Callable[[], int]:
    """Monkeypatch make_geometry_fig; return a getter for the call count."""
    count = 0
    original = geometry_tab.make_geometry_fig

    def mock_make_fig(*args, **kwargs):
        nonlocal count
        count += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(geometry_tab, "make_geometry_fig", mock_make_fig)
    return lambda: count


def _slider_by_marker(user: User, marker: str) -> ui.slider:
    """Find a marked slider even when an ancestor bind hides it from ``user.find``."""
    assert user.client is not None
    for el in user.client.elements.values():
        if marker in el._markers and isinstance(el, ui.slider):
            return el
    raise AssertionError(f"Slider with marker {marker!r} not found")


def _set_slider_value(user: User, marker: str, value: float) -> None:
    """Set a slider inside the NiceGUI client context (see HARNESS_ENGINEERING.md)."""
    assert user.client is not None
    with user.client:
        _slider_by_marker(user, marker).set_value(value)


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
async def test_phantom_scale_controls_render_for_default_human_model(user: User) -> None:
    old_model = state.phantom_model
    old_mesh = state.human_mesh
    try:
        state.phantom_model = "human"
        state.human_mesh = "hudfrid"
        await user.open("/")
        await user.should_see("Body habitus scaling")
        await user.should_see("Lateral / width")
        await user.should_see("AP / vertical thickness")
        await user.should_see("Longitudinal / head-foot")
        await user.should_see("cm")
    finally:
        state.phantom_model = old_model
        state.human_mesh = old_mesh


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
    await user.should_see(PHILIPS_EXAMPLE, retries=20)
    user.find(PHILIPS_EXAMPLE).click()
    # load_example awaits run.io_bound(load_rdsr, ...); the drawer then shows a
    # non-zero event count. should_see defaults to only 3 retries (~0.3s), which
    # the async load can outlast on slower CI runners, so allow generous retries.
    await user.should_see("EVENTS", retries=50)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "slider_marker",
    ["patient-slider-lon", "patient-slider-ver", "patient-slider-lat"],
)
async def test_geometry_patient_slider_no_render_loop(
    user: User,
    monkeypatch: pytest.MonkeyPatch,
    slider_marker: str,
) -> None:
    """One debounced render per patient-slider move; no timer loop while idle."""
    await _load_philips_example(user)
    await _open_geometry_tab(user)
    get_calls = _install_make_fig_counter(monkeypatch)
    user.find("Setup view").click()
    await asyncio.sleep(GEOMETRY_DEBOUNCE_SEC + 0.5)
    assert get_calls() == 1, f"Initial render should run once, got {get_calls()}"

    _set_slider_value(user, slider_marker, 5.0)
    await asyncio.sleep(GEOMETRY_DEBOUNCE_SEC + 0.5)
    assert get_calls() == 2, f"Expected 2 total renders after {slider_marker}, got {get_calls()}"
    await asyncio.sleep(1.0)
    assert get_calls() == 2, f"Plot re-rendered while idle, count={get_calls()}"


@pytest.mark.asyncio
async def test_geometry_table_slider_no_render_loop(
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Table-origin slider uses the same debounce path without a render loop."""
    await _load_philips_example(user)
    await _open_geometry_tab(user)
    await user.should_see("Table origin override", retries=50)

    get_calls = _install_make_fig_counter(monkeypatch)
    user.find("Setup view").click()
    await asyncio.sleep(GEOMETRY_DEBOUNCE_SEC + 0.5)
    assert get_calls() == 1, f"Initial render should run once, got {get_calls()}"

    _set_slider_value(user, "table-slider-x", 5.0)
    await asyncio.sleep(GEOMETRY_DEBOUNCE_SEC + 0.5)
    assert get_calls() == 2, f"Expected 2 total renders after table-slider-x, got {get_calls()}"
    await asyncio.sleep(1.0)
    assert get_calls() == 2, f"Plot re-rendered while idle, count={get_calls()}"
