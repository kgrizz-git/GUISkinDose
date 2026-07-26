"""Coverage for ``geometry_builders`` controller logic and preview wiring.

Exercises ``GeometryTabController`` with mocked UI refs (debounce, stepper,
table-origin flush) and one NiceGUI User path through Setup / Single-event
preview after loading the bundled Philips example.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from nicegui.testing import User

from mypyskindose import get_path_to_example_rdsr_files
from mypyskindose.gui.constants import GEOMETRY_DEBOUNCE_SEC
from mypyskindose.gui.helpers import load_rdsr
from mypyskindose.gui.page_context import PageContext
from mypyskindose.gui.state import state
from mypyskindose.gui.tabs import geometry_builders as gb

pytest.importorskip("nicegui")

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")

_PHILIPS = get_path_to_example_rdsr_files() / "philips_allura_clarity_u104.dcm"


def _minimal_ctx() -> PageContext:
    return PageContext(
        tabs=MagicMock(),
        file_label=MagicMock(),
        events_label=MagicMock(),
        psd_label=MagicMock(),
        run_btn_drawer=MagicMock(),
    )


def _controller() -> gb.GeometryTabController:
    return gb.GeometryTabController(_minimal_ctx())


def _load_philips_into_state() -> None:
    ok, _ = load_rdsr(_PHILIPS, state)
    assert ok


@pytest.fixture(autouse=True)
def _stub_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    from nicegui import ui

    monkeypatch.setattr(ui, "notify", lambda *a, **k: None)


def test_active_exam_index_single_exam_defaults_to_zero() -> None:
    ctrl = _controller()
    state.is_multi_exam = False
    state.active_exam_index = 3
    assert ctrl.active_exam_index == 0


def test_active_exam_index_multi_exam_uses_state() -> None:
    ctrl = _controller()
    state.is_multi_exam = True
    state.active_exam_index = 2
    assert ctrl.active_exam_index == 2


def test_current_load_signature_none_without_data() -> None:
    ctrl = _controller()
    state.rdsr_df = None
    state.loaded_exam_meta = []
    assert ctrl.current_load_signature() is None


def test_current_load_signature_reflects_loaded_exams() -> None:
    _load_philips_into_state()
    ctrl = _controller()
    sig = ctrl.current_load_signature()
    assert sig is not None
    assert sig[0] == len(state.loaded_exam_meta)


def test_live_preview_blocked_while_busy() -> None:
    ctrl = _controller()
    state.busy = True
    assert ctrl.live_preview_allowed() is False


def test_stale_caption_visible_after_offset_change() -> None:
    ctrl = _controller()
    state.calculation_done = True
    ctrl.offset_changed_since_calc = True
    assert ctrl.stale_caption_visible() is True


def test_step_advances_event_index_in_plot_event_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    ctrl.last_preview_mode = "plot_event"
    ctrl.refs.geom_event_select = MagicMock(value=2)
    monkeypatch.setattr(ctrl, "_preview_slice_count", lambda: 5)
    monkeypatch.setattr(ctrl, "render_event_preview_debounced", lambda: None)

    ctrl.step(1)

    ctrl.refs.geom_event_select.set_value.assert_called_with(3)


def test_step_noop_when_not_in_plot_event_mode() -> None:
    ctrl = _controller()
    ctrl.last_preview_mode = "plot_setup"
    ctrl.refs.geom_event_select = MagicMock(value=2)

    ctrl.step(1)

    ctrl.refs.geom_event_select.set_value.assert_not_called()


def test_flush_pending_table_origin_commits_and_cancels_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_philips_into_state()
    ctrl = _controller()
    ctrl.table_origin_pending = True
    timer = MagicMock()
    ctrl._slider_timer = timer
    committed: list[int] = []

    def _commit(st, idx: int) -> None:
        committed.append(idx)

    monkeypatch.setattr(gb, "commit_table_origin_transform", _commit)
    monkeypatch.setattr(gb, "reset_results", lambda: None)

    ctrl.flush_pending_table_origin()

    timer.cancel.assert_called_once()
    assert ctrl._slider_timer is None
    assert ctrl.table_origin_pending is False
    assert committed == [ctrl.active_exam_index]


@pytest.mark.asyncio
async def test_preview_setup_without_data_notifies(monkeypatch: pytest.MonkeyPatch) -> None:
    from nicegui import ui

    messages: list[str] = []
    monkeypatch.setattr(ui, "notify", lambda msg, **k: messages.append(str(msg)))
    state.rdsr_df = None
    ctrl = _controller()

    await ctrl.preview_setup()

    assert any("Load data first" in m for m in messages)


@pytest.mark.asyncio
async def test_render_preview_calls_make_geometry_fig(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_philips_into_state()
    ctrl = _controller()
    ctrl.refs.plot = MagicMock()
    ctrl.refs.spinner = MagicMock()
    ctrl.refs.geom_event_select = MagicMock(value=1)
    fake_fig = {"data": [], "layout": {}}

    async def _fake_io_bound(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(gb.run, "io_bound", _fake_io_bound)
    monkeypatch.setattr(gb, "make_geometry_fig", lambda *a, **k: fake_fig)

    await ctrl._render_preview("plot_setup")

    ctrl.refs.plot.update_figure.assert_called_once_with(fake_fig)
    assert ctrl.refs.spinner.visible is False


@pytest.mark.asyncio
async def test_geometry_setup_view_user_path(user: User, monkeypatch: pytest.MonkeyPatch) -> None:
    """User clicks Setup view after loading the Philips example."""
    rendered: list[str] = []

    def _track_render(mode, *args, **kwargs):
        rendered.append(mode)
        return {"data": [], "layout": {}}

    monkeypatch.setattr(gb, "make_geometry_fig", _track_render)

    await user.open("/")
    user.find(marker="example-select").click()
    await user.should_see("philips_allura_clarity_u104.dcm", retries=20)
    user.find("philips_allura_clarity_u104.dcm").click()
    await user.should_see("EVENTS", retries=50)

    user.find("4 · Geometry").click()
    await user.should_see("Setup view", retries=50)
    user.find("Setup view").click()
    await asyncio.sleep(GEOMETRY_DEBOUNCE_SEC + 0.5)

    assert "plot_setup" in rendered
