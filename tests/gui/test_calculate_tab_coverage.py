"""Coverage for the Calculate tab controller and below-floor kVp prompt."""

from __future__ import annotations

from typing import cast

from unittest.mock import AsyncMock, MagicMock

import pytest
from nicegui.testing import User

from mypyskindose.gui.helpers import load_tabular
from mypyskindose.gui.page_context import PageContext
from mypyskindose.gui.state import state
from mypyskindose.gui.tabs import calculate as calc_tab

pytest.importorskip("nicegui")

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")

_FIXTURES = __import__("pathlib").Path(__file__).resolve().parent.parent / "fixtures" / "tabular_inputs"


def _minimal_ctx() -> PageContext:
    return PageContext(
        tabs=MagicMock(),
        file_label=MagicMock(),
        events_label=MagicMock(),
        psd_label=MagicMock(),
        run_btn_drawer=MagicMock(),
        flush_geometry_pending=MagicMock(),
        clear_offset_stale_caption=MagicMock(),
    )


def _controller() -> calc_tab._CalculationController:
    ctrl = calc_tab._CalculationController(_minimal_ctx())
    button = MagicMock()
    progress = MagicMock(visible=False)
    status = MagicMock()
    ctrl.controls = calc_tab._CalculationControls(button, progress, status)
    return ctrl


@pytest.fixture(autouse=True)
def _stub_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    from nicegui import ui

    monkeypatch.setattr(ui, "notify", lambda *a, **k: None)


@pytest.mark.asyncio
async def test_do_calculate_warns_without_loaded_data(monkeypatch: pytest.MonkeyPatch) -> None:
    from nicegui import ui

    messages: list[str] = []
    monkeypatch.setattr(ui, "notify", lambda msg, **k: messages.append(str(msg)))
    state.rdsr_df = None
    ctrl = _controller()

    await ctrl.do_calculate()

    assert any("Load a file first" in m for m in messages)


@pytest.mark.asyncio
async def test_do_calculate_blocks_on_import_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    from nicegui import ui

    messages: list[str] = []
    monkeypatch.setattr(ui, "notify", lambda msg, **k: messages.append(str(msg)))
    state.rdsr_df = MagicMock()
    state.import_has_errors = True
    ctrl = _controller()

    await ctrl.do_calculate()

    assert any("import errors" in m.lower() for m in messages)


@pytest.mark.asyncio
async def test_do_calculate_success_updates_drawer_and_tabs(monkeypatch: pytest.MonkeyPatch) -> None:
    ok, _ = load_tabular(_FIXTURES / "normalized_events.csv", state)
    assert ok
    state.below_floor_prompt_suppressed = True
    state.psd = 9.5
    ctrl = _controller()

    async def _fake_run(*args, **kwargs):
        return (True, "calculation complete")

    monkeypatch.setattr(calc_tab.run, "io_bound", _fake_run)

    await ctrl.do_calculate()

    cast(MagicMock, ctrl.ctx.psd_label.set_text).assert_called_with("PSD: 9.50 mGy")
    cast(MagicMock, ctrl.ctx.tabs.set_value).assert_called_with("results")
    assert ctrl.controls is not None
    cast(MagicMock, ctrl.controls.status_label.set_text).assert_called()


@pytest.mark.asyncio
async def test_do_calculate_failure_clears_results(monkeypatch: pytest.MonkeyPatch) -> None:
    ok, _ = load_tabular(_FIXTURES / "normalized_events.csv", state)
    assert ok
    state.below_floor_prompt_suppressed = True
    state.calculation_done = True
    state.output = {"psd": 1.0}
    state.psd = 1.0
    ctrl = _controller()

    async def _fake_run(*args, **kwargs):
        return (False, "synthetic failure")

    monkeypatch.setattr(calc_tab.run, "io_bound", _fake_run)

    await ctrl.do_calculate()

    assert state.calculation_done is False
    assert state.output is None
    assert state.psd is None
    cast(MagicMock, ctrl.ctx.psd_label.set_text).assert_called_with("PSD: 0.00 mGy")


@pytest.mark.asyncio
async def test_below_floor_policy_skipped_when_suppressed(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    state.below_floor_prompt_suppressed = True
    monkeypatch.setattr(calc_tab, "below_floor_event_count", lambda _s: 5)

    ready = await ctrl._below_floor_policy_is_ready()

    assert ready is True


@pytest.mark.asyncio
async def test_below_floor_policy_prompt_cancel_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    state.below_floor_prompt_suppressed = False
    monkeypatch.setattr(calc_tab, "below_floor_event_count", lambda _s: 2)
    monkeypatch.setattr(calc_tab, "below_floor_prompt", AsyncMock(return_value=False))

    ready = await ctrl._below_floor_policy_is_ready()

    assert ready is False


@pytest.mark.asyncio
async def test_calculate_tab_renders_summary(user: User) -> None:
    """Calculate tab shows settings summary after tabular load."""
    ok, _ = load_tabular(_FIXTURES / "normalized_events.csv", state)
    assert ok

    await user.open("/")
    user.find("5 · Calculate").click()
    await user.should_see("Run Dose Calculation", retries=30)
    await user.should_see("Current settings", retries=30)
    await user.should_see("INPUT DATA", retries=30)
