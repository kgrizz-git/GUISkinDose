"""Coverage for ``upload_builders`` load helpers and upload-tab controller paths."""

from __future__ import annotations

from typing import cast

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from nicegui.testing import User

from mypyskindose.gui.constants import EXAMPLE_FILES
from mypyskindose.gui.tabs.upload_builders import MAX_UPLOAD_BYTES
from mypyskindose.gui.helpers import load_tabular
from mypyskindose.gui.page_context import PageContext
from mypyskindose.gui.state import state
from mypyskindose.gui.tabs import upload_builders as ub

pytest.importorskip("nicegui")

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "tabular_inputs"
_PHILIPS_NAME = "philips_allura_clarity_u104.dcm"


def _minimal_ctx() -> PageContext:
    return PageContext(
        tabs=MagicMock(),
        file_label=MagicMock(),
        events_label=MagicMock(),
        psd_label=MagicMock(),
        run_btn_drawer=MagicMock(),
    )


def _upload_controller() -> ub.UploadTabController:
    ctrl = ub.UploadTabController(_minimal_ctx())
    ctrl.refs.upload_status = MagicMock()
    ctrl.refs.example_select = MagicMock()
    ctrl.refs.uploader = {"el": MagicMock()}
    ctrl.refs.event_table = MagicMock(refresh=MagicMock())
    ctrl.refs.import_preview = MagicMock(
        refresh=MagicMock(),
        set_transform_defaults=MagicMock(),
        sheet_row=MagicMock(set_visibility=MagicMock()),
        sheet_select=MagicMock(set_options=MagicMock()),
    )
    ctrl.refs.exams_section_label = MagicMock(set_visibility=MagicMock())
    ctrl.refs.exams_list = MagicMock(clear=MagicMock(), set_visibility=MagicMock())
    ctrl.refs.uploader_container = MagicMock(clear=MagicMock())
    ctrl.refs.schema_select = MagicMock()
    return ctrl


@pytest.fixture(autouse=True)
def _stub_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    from nicegui import ui

    monkeypatch.setattr(ui, "notify", lambda *a, **k: None)


def test_upload_exceeds_limit_boundary() -> None:
    assert ub.upload_exceeds_limit(MAX_UPLOAD_BYTES) is False
    assert ub.upload_exceeds_limit(MAX_UPLOAD_BYTES + 1) is True


def test_drawer_file_label_states() -> None:
    state.loaded_exams = []
    assert ub._drawer_file_label() == "No file loaded"

    state.loaded_exams = [SimpleNamespace()]
    assert ub._drawer_file_label() == "EXAM 1"

    state.loaded_exams = [SimpleNamespace(), SimpleNamespace()]
    assert ub._drawer_file_label() == "2 FILES"


def test_snapshot_and_restore_load_state_round_trip() -> None:
    state.rdsr_df = None
    state.file_name = "before.dcm"
    state.manufacturer = "Vendor"
    state.loaded_exam_meta = [{"file_name": "before.dcm", "d_lon": 1.0}]
    snap = ub._snapshot_load_state()

    state.file_name = "mutated.dcm"
    state.manufacturer = "Changed"
    state.loaded_exam_meta = [{"file_name": "mutated.dcm", "d_lon": 9.0}]

    ub._restore_load_state(snap)

    assert state.file_name == "before.dcm"
    assert state.manufacturer == "Vendor"
    assert state.loaded_exam_meta[0]["d_lon"] == 1.0


def test_clear_all_exams_resets_state_and_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _upload_controller()
    monkeypatch.setattr(ctrl, "_build_uploader", lambda: None)
    state.loaded_exams = [SimpleNamespace()]
    state.loaded_exam_meta = [{"file_name": "x.dcm"}]
    state.rdsr_df = MagicMock()
    state.file_name = "x.dcm"
    state.calculation_done = True

    ctrl.clear_all_exams()

    assert state.loaded_exams == []
    assert state.rdsr_df is None
    assert state.file_name == ""
    assert state.calculation_done is False
    cast(MagicMock, ctrl.ctx.file_label.set_text).assert_called_with("No file loaded")
    cast(MagicMock, ctrl.refs.event_table.refresh).assert_called()


def test_remove_last_exam_clears_drawer_labels() -> None:
    ctrl = _upload_controller()
    state.loaded_exams = [SimpleNamespace(normalized_data=MagicMock(__len__=lambda s: 1))]
    state.loaded_exam_meta = [{"file_name": "only.dcm", "file_path": Path("only.dcm")}]
    state.rdsr_df = MagicMock()
    state.is_multi_exam = False

    ctrl.remove_exam(0)

    assert state.loaded_exams == []
    cast(MagicMock, ctrl.ctx.file_label.set_text).assert_called_with("No file loaded")
    cast(MagicMock, ctrl.ctx.events_label.set_text).assert_called_with("0 events")


@pytest.mark.asyncio
async def test_load_example_success(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _upload_controller()
    ctrl.refs.example_select.value = _PHILIPS_NAME
    path = EXAMPLE_FILES[_PHILIPS_NAME]
    ok, msg = __import__("mypyskindose.gui.helpers", fromlist=["load_rdsr"]).load_rdsr(path, state)
    assert ok, msg
    state.file_name = ""
    state.rdsr_df = None
    state.loaded_exams = []
    state.loaded_exam_meta = []

    async def _fake_io_bound(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(ub.run, "io_bound", _fake_io_bound)
    monkeypatch.setattr(ub, "clear_all_temp_uploads", lambda: None)
    monkeypatch.setattr(ctrl, "refresh_exams_table", lambda: None)

    await ctrl.load_example()

    assert state.file_name == _PHILIPS_NAME
    assert state.rdsr_df is not None
    cast(MagicMock, ctrl.refs.upload_status.set_text).assert_called()
    cast(MagicMock, ctrl.refs.event_table.refresh).assert_called()


@pytest.mark.asyncio
async def test_handle_upload_rejects_unsupported_suffix() -> None:
    ctrl = _upload_controller()
    event = SimpleNamespace(file=SimpleNamespace(name="evil.exe", read=AsyncMock()))

    await ctrl.handle_upload(event)

    cast(MagicMock, ctrl.refs.upload_status.set_text).assert_called_with("Could not load — see message")
    cast(MagicMock, ctrl.refs.uploader["el"].reset).assert_called()


@pytest.mark.asyncio
async def test_handle_upload_rejects_oversized_file() -> None:
    ctrl = _upload_controller()
    big = b"x" * (MAX_UPLOAD_BYTES + 1)
    event = SimpleNamespace(file=SimpleNamespace(name="big.dcm", read=AsyncMock(return_value=big)))

    await ctrl.handle_upload(event)

    cast(MagicMock, ctrl.refs.upload_status.set_text).assert_called_with("Upload rejected — file too large")


@pytest.mark.asyncio
async def test_reparse_schema_on_tabular_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _upload_controller()
    state.input_schema = "auto"
    ok, _ = load_tabular(_FIXTURES / "normalized_events.csv", state)
    assert ok
    state.input_source_type = "csv"
    ctrl.refs.schema_select.value = "normalized"
    monkeypatch.setattr(ctrl, "refresh_exams_table", lambda: None)

    async def _fake_io_bound(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(ub.run, "io_bound", _fake_io_bound)

    await ctrl.reparse_schema()

    cast(MagicMock, ctrl.refs.upload_status.set_text).assert_called()
    assert "OK:" in str(cast(MagicMock, ctrl.refs.upload_status.set_text).call_args)


@pytest.mark.asyncio
async def test_upload_tabular_shows_import_preview(user: User) -> None:
    """Tabular load surfaces the import-preview card (non-DICOM path)."""
    await user.open("/")
    state.input_source_type = "csv"
    state.import_provenance = SimpleNamespace(
        schema_name="normalized",
        detected_encoding="utf-8",
        detected_delimiter=",",
        header_row_index=0,
        column_map={"kVp": "kVp"},
        unit_conversions={},
    )
    ok, _ = load_tabular(_FIXTURES / "normalized_events.csv", state)
    assert ok

    await user.should_see("Import preview", retries=30)
    await user.should_see("NORMALIZED", retries=30)


@pytest.mark.asyncio
async def test_handle_upload_success_dicom(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _upload_controller()
    data = b"dicom-bytes"
    event = SimpleNamespace(file=SimpleNamespace(name="case.dcm", read=AsyncMock(return_value=data)))
    tmp = Path("/tmp/fake_upload.dcm")
    success_calls: list[tuple] = []

    async def _fake_io_bound(fn, *args, **kwargs):
        return True, "loaded"

    async def _on_success(*args):
        success_calls.append(args)

    monkeypatch.setattr(ub, "create_temp_upload", lambda payload, suffix=".dcm": tmp)
    monkeypatch.setattr(ub.run, "io_bound", _fake_io_bound)
    monkeypatch.setattr(ub, "require_io_result", lambda x: x)
    monkeypatch.setattr(ctrl, "_on_load_success", _on_success)

    await ctrl.handle_upload(event)

    assert success_calls
    assert success_calls[0][0] == "case.dcm"
    cast(MagicMock, ctrl.refs.uploader["el"].reset).assert_called()


def test_select_exam_for_geometry_switches_tab() -> None:
    ctrl = _upload_controller()
    ctrl.ctx.refresh_per_exam = MagicMock()
    state.loaded_exams = [SimpleNamespace(), SimpleNamespace()]
    state.loaded_exam_meta = [{"file_name": "a.dcm"}, {"file_name": "b.dcm"}]
    ctrl.select_exam_for_geometry(1)
    assert state.active_exam_index == 1
    cast(MagicMock, ctrl.ctx.tabs.set_value).assert_called_with("geometry")
    cast(MagicMock, ctrl.ctx.refresh_per_exam).assert_called()


def test_remove_exam_keeps_remaining_single(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _upload_controller()
    state.loaded_exams = [
        SimpleNamespace(normalized_data=MagicMock(__len__=lambda s: 2)),
        SimpleNamespace(normalized_data=MagicMock(__len__=lambda s: 3)),
    ]
    state.loaded_exam_meta = [
        {"file_name": "a.dcm", "file_path": Path("a.dcm")},
        {"file_name": "b.dcm", "file_path": Path("b.dcm")},
    ]
    state.is_multi_exam = True
    state.rdsr_df = MagicMock(__len__=lambda s: 3)
    monkeypatch.setattr(ub, "rebuild_rdsr_df", lambda st: None)
    monkeypatch.setattr(ub, "remove_temp_upload", lambda p: None)
    monkeypatch.setattr(ub, "restore_globals_from_exam_meta", lambda st, meta: None)
    monkeypatch.setattr(ub, "adjust_active_exam_index_after_remove", lambda st, i: None)
    monkeypatch.setattr(ctrl, "refresh_exams_table", lambda: None)

    ctrl.remove_exam(0)

    assert len(state.loaded_exams) == 1
    assert state.file_name == "b.dcm"
    cast(MagicMock, ctrl.ctx.file_label.set_text).assert_called()
