"""Coverage for ``import_preview`` controller refresh and transform defaults."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from mypyskindose.gui.helpers import load_tabular
from mypyskindose.gui.page_context import PageContext
from mypyskindose.gui.state import state
from mypyskindose.gui.widgets import import_preview as ip

pytest.importorskip("nicegui")

_FIXTURES = __import__("pathlib").Path(__file__).resolve().parent.parent / "fixtures" / "tabular_inputs"


def _minimal_ctx() -> PageContext:
    return PageContext(
        tabs=MagicMock(),
        file_label=MagicMock(),
        events_label=MagicMock(),
        psd_label=MagicMock(),
        run_btn_drawer=MagicMock(),
    )


def _controller() -> ip.ImportPreviewController:
    ctrl = ip.ImportPreviewController(_minimal_ctx(), MagicMock())
    ctrl.schema_badge = MagicMock()
    ctrl.encoding_label = MagicMock()
    ctrl.delimiter_label = MagicMock()
    ctrl.header_label = MagicMock()
    ctrl.sheet_label = MagicMock()
    ctrl.warnings_label = MagicMock()
    ctrl.col_map_table = MagicMock(rows=[], update=MagicMock())
    ctrl.unit_conv_row = MagicMock(set_visibility=MagicMock())
    ctrl.unit_conv_table = MagicMock(rows=[], update=MagicMock())
    ctrl.event_sample_table = MagicMock(columns=[], rows=[], update=MagicMock())
    ctrl.coord_card = MagicMock(set_visibility=MagicMock())
    ctrl.coord_auto_label = MagicMock()
    ctrl.sheet_select = MagicMock(value=0)
    return ctrl


@pytest.fixture(autouse=True)
def _stub_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    from nicegui import ui

    monkeypatch.setattr(ui, "notify", lambda *a, **k: None)


def test_is_ge_from_manufacturer() -> None:
    ctrl = _controller()
    state.manufacturer = "GE Healthcare"
    state.import_warnings = []
    assert ctrl._is_ge() is True


def test_is_ge_from_import_warning() -> None:
    ctrl = _controller()
    state.manufacturer = ""
    state.import_warnings = ["GE manufacturer detected in export."]
    assert ctrl._is_ge() is True


def test_set_transform_defaults_clears_flags_for_non_ge() -> None:
    ctrl = _controller()
    state.import_provenance = SimpleNamespace(schema_name="radimetrics")
    state.is_multi_exam = False
    state.swap_lat_lon = True
    state.flip_ap1 = True
    state.loaded_exam_meta = [{"swap_lat_lon": True, "flip_ap1": True, "flip_ap2": False}]
    state.manufacturer = "Philips"

    ctrl.set_transform_defaults()

    assert state.swap_lat_lon is False
    assert state.flip_ap1 is False
    assert state.loaded_exam_meta[0]["swap_lat_lon"] is False
    ctrl.coord_auto_label.set_text.assert_called_with("")


def test_set_transform_defaults_ge_shows_normalization_hint() -> None:
    ctrl = _controller()
    state.import_provenance = SimpleNamespace(schema_name="radimetrics")
    state.is_multi_exam = False
    state.loaded_exam_meta = [{"swap_lat_lon": False, "flip_ap1": False, "flip_ap2": False}]
    state.manufacturer = "GE Medical Systems"

    ctrl.set_transform_defaults()

    ctrl.coord_auto_label.set_text.assert_called_with("· GE lat/lon handled in normalization")


def test_refresh_populates_metadata_and_sample() -> None:
    ctrl = _controller()
    ok, _ = load_tabular(_FIXTURES / "normalized_events.csv", state)
    assert ok
    state.input_source_type = "csv"
    prov = state.import_provenance
    assert prov is not None

    ctrl.refresh()

    ctrl.schema_badge.set_text.assert_called_with(prov.schema_name.upper().replace("_", " "))
    ctrl.col_map_table.update.assert_called()
    ctrl.event_sample_table.update.assert_called()
    assert len(ctrl.event_sample_table.rows) <= 5


def test_refresh_hides_coord_card_for_normalized_schema() -> None:
    ctrl = _controller()
    ok, _ = load_tabular(_FIXTURES / "normalized_events.csv", state)
    assert ok
    state.input_source_type = "csv"

    ctrl.refresh()

    ctrl.coord_card.set_visibility.assert_called_with(False)


def test_on_swap_toggle_ignored_for_normalized_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    ok, _ = load_tabular(_FIXTURES / "normalized_events.csv", state)
    assert ok
    state.input_source_type = "csv"
    state.import_provenance = SimpleNamespace(schema_name="normalized")
    state.loaded_exam_meta = [{"swap_lat_lon": False, "flip_ap1": False, "flip_ap2": False}]
    committed = {"n": 0}
    monkeypatch.setattr(ctrl, "_commit_single_exam_transform", lambda: committed.__setitem__("n", committed["n"] + 1))

    ctrl.on_swap_toggle()

    assert committed["n"] == 0


@pytest.mark.asyncio
async def test_on_sheet_change_reparses_file(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = _controller()
    ok, _ = load_tabular(_FIXTURES / "normalized_events.csv", state)
    assert ok
    state.input_source_type = "csv"
    ctrl.sheet_select.value = 0
    refreshed = {"n": 0}
    ctrl.refresh = lambda: refreshed.__setitem__("n", refreshed["n"] + 1)

    async def _passthrough_io(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(ip.run, "io_bound", _passthrough_io)

    await ctrl.on_sheet_change()

    assert refreshed["n"] == 1
    ctrl.upload_status.set_text.assert_called()
