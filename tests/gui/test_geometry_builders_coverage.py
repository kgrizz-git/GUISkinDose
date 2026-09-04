"""Coverage for ``geometry_builders`` controller logic and preview wiring.

Exercises ``GeometryTabController`` with mocked UI refs (debounce, stepper,
table-origin flush) and one NiceGUI User path through Setup / Single-event
preview after loading the bundled Philips example.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
from nicegui.testing import User

from guiskindose import get_path_to_example_rdsr_files
from guiskindose.gui.constants import GEOMETRY_DEBOUNCE_SEC
from guiskindose.gui.helpers import load_rdsr
from guiskindose.gui.page_context import PageContext
from guiskindose.gui.state import state
from guiskindose.gui.tabs import geometry_builders as gb

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


def _wire_geometry_refs(ctrl: gb.GeometryTabController) -> None:
    ctrl.refs.preview_caption = MagicMock()
    ctrl.refs.vendor_notice = MagicMock()
    ctrl.refs.stale_caption = MagicMock()
    ctrl.refs.paused_badge = MagicMock()
    ctrl.refs.geom_event_select = MagicMock(value=1)
    ctrl.refs.geom_event_context = MagicMock()
    ctrl.refs.prev_btn = MagicMock()
    ctrl.refs.next_btn = MagicMock()
    ctrl.refs.exam_select = MagicMock(value=0)
    ctrl.refs.geom_exam_select = MagicMock(value=0)
    ctrl.refs.composite_checkbox = MagicMock()
    ctrl.refs.plot = MagicMock()
    ctrl.refs.spinner = MagicMock(visible=False)
    ctrl.refs.patient_sliders = {
        "d_patient_x": MagicMock(value=0.0),
        "d_patient_y": MagicMock(value=0.0),
        "d_patient_z": MagicMock(value=0.0),
    }
    ctrl.refs.patient_val_labels = {k: MagicMock() for k in ctrl.refs.patient_sliders}
    ctrl.refs.table_sliders = {"Tx": MagicMock(value=0.0), "Ty": MagicMock(value=0.0), "Tz": MagicMock(value=0.0)}
    ctrl.refs.table_val_labels = {k: MagicMock() for k in ctrl.refs.table_sliders}


def test_middle_event_index_and_preview_caption() -> None:
    _load_philips_into_state()
    ctrl = _controller()
    _wire_geometry_refs(ctrl)
    assert ctrl.middle_event_index(0, composite=False) >= 0
    ctrl.update_preview_caption()
    cast(MagicMock, ctrl.refs.preview_caption.set_text).assert_called()
    cast(MagicMock, ctrl.refs.vendor_notice.set_text).assert_called()


def test_override_active_and_stale_caption_update() -> None:
    _load_philips_into_state()
    ctrl = _controller()
    _wire_geometry_refs(ctrl)
    state.loaded_exam_meta[0]["table_origin_override"] = {"Tx": 1.0, "Ty": 0.0, "Tz": 0.0}
    assert ctrl.override_active_for_active_exam() is True
    state.calculation_done = True
    ctrl.offset_changed_since_calc = True
    ctrl.update_stale_caption()
    cast(MagicMock, ctrl.refs.stale_caption.set_visibility).assert_called_with(True)


def test_set_stepper_and_event_select_change(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    _wire_geometry_refs(ctrl)
    ctrl.last_preview_mode = "plot_event"
    scheduled: list[bool] = []
    monkeypatch.setattr(ctrl, "schedule_debounced_render", lambda: scheduled.append(True))
    monkeypatch.setattr(ctrl, "update_event_context", lambda: None)

    ctrl.set_stepper_enabled(True)
    cast(MagicMock, ctrl.refs.geom_event_select.set_enabled).assert_called_with(True)
    ctrl.on_event_select_change(None)
    assert scheduled == [True]


def test_handle_patient_slider_change_schedules_render(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_philips_into_state()
    ctrl = _controller()
    _wire_geometry_refs(ctrl)
    scheduled: list[bool] = []
    monkeypatch.setattr(ctrl, "schedule_debounced_render", lambda: scheduled.append(True))
    monkeypatch.setattr(gb, "apply_patient_offset_slider_tick", lambda *a, **k: None)
    ctrl.ctx.refresh_phantom_preview = MagicMock()

    slider = MagicMock(value=3.5)
    ctrl.handle_patient_slider_change("d_patient_x", slider)

    cast(MagicMock, ctrl.refs.patient_val_labels["d_patient_x"].set_text).assert_called_with("3.5 cm")
    assert ctrl.offset_changed_since_calc is True
    assert scheduled == [True]


def test_reset_patient_offset_single_exam(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_philips_into_state()
    ctrl = _controller()
    _wire_geometry_refs(ctrl)
    monkeypatch.setattr(gb, "reset_patient_offset_for_active", lambda st: None)
    monkeypatch.setattr(gb, "on_global_patient_offset_change", lambda ctx: None)
    monkeypatch.setattr(ctrl, "sync_patient_sliders_from_meta", lambda: None)

    ctrl.reset_patient_offset()

    assert ctrl.offset_changed_since_calc is True
    cast(MagicMock, ctrl.refs.plot.update_figure).assert_called_with({})


def test_clear_offset_and_register_hooks() -> None:
    ctrl = _controller()
    _wire_geometry_refs(ctrl)
    ctrl.offset_changed_since_calc = True
    ctrl.register_context_hooks()
    # Bound methods are not identity-stable across attribute access; call via ctx.
    ctrl.ctx.clear_offset_stale_caption()
    assert ctrl.offset_changed_since_calc is False
    assert callable(ctrl.ctx.flush_geometry_pending)
    assert callable(ctrl.ctx.refresh_geometry_preview)


@pytest.mark.asyncio
async def test_preview_event_and_procedure_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_philips_into_state()
    ctrl = _controller()
    _wire_geometry_refs(ctrl)
    rendered: list[str] = []

    async def _fake_render(mode: str) -> None:
        rendered.append(mode)

    monkeypatch.setattr(ctrl, "_render_preview", _fake_render)
    monkeypatch.setattr(ctrl, "live_preview_allowed", lambda: True)

    await ctrl.preview_event()
    await ctrl.preview_procedure()

    assert rendered == ["plot_event", "plot_procedure"]
    assert ctrl.last_preview_mode == "plot_procedure"


def test_on_exam_select_change_updates_active_index(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_philips_into_state()
    ctrl = _controller()
    _wire_geometry_refs(ctrl)
    state.is_multi_exam = True
    state.active_exam_index = 0
    state.loaded_exam_meta = [{"file_name": "a.dcm"}, {"file_name": "b.dcm"}]
    monkeypatch.setattr(ctrl, "update_preview_caption", lambda: None)
    monkeypatch.setattr(ctrl, "update_event_context", lambda: None)
    ctrl.ctx.refresh_per_exam = MagicMock()

    event = SimpleNamespace(value=1)
    ctrl.on_exam_select_change(event)

    assert state.active_exam_index == 1
    cast(MagicMock, ctrl.ctx.refresh_per_exam).assert_called()


def test_on_composite_toggle_schedules_render(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    _wire_geometry_refs(ctrl)
    ctrl.last_preview_mode = "plot_event"
    scheduled: list[bool] = []
    monkeypatch.setattr(ctrl, "schedule_debounced_render", lambda: scheduled.append(True))
    monkeypatch.setattr(ctrl, "update_preview_caption", lambda: None)
    monkeypatch.setattr(ctrl, "update_event_context", lambda: None)
    monkeypatch.setattr(ctrl, "_update_paused_badge", lambda: None)

    ctrl.on_composite_toggle(SimpleNamespace(value=True))

    assert ctrl.composite_preview is True
    assert scheduled == [True]


def test_handle_table_slider_change_stages_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_philips_into_state()
    ctrl = _controller()
    _wire_geometry_refs(ctrl)
    scheduled: list[bool] = []
    monkeypatch.setattr(ctrl, "schedule_debounced_render", lambda: scheduled.append(True))
    monkeypatch.setattr(gb, "stage_table_origin_axis", lambda meta, key, val: None)

    ctrl.handle_table_slider_change("Tx", MagicMock(value=12.0))

    assert ctrl.table_origin_pending is True
    assert ctrl.last_table_origin_scrub is True
    cast(MagicMock, ctrl.refs.table_val_labels["Tx"].set_text).assert_called_with("12.0 cm")
    assert scheduled == [True]
