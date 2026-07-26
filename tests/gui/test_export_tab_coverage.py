"""Additional Export tab coverage beyond download error semantics."""

from __future__ import annotations

from typing import cast

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("nicegui")

from nicegui import ui  # noqa: E402

from mypyskindose.gui.state import state  # noqa: E402
from mypyskindose.gui.tabs import export as export_tab  # noqa: E402


@pytest.fixture(autouse=True)
def _capture_notify(monkeypatch):
    calls: list[tuple[tuple, dict]] = []
    monkeypatch.setattr(ui, "notify", lambda *a, **k: calls.append((a, k)))
    return calls


def _controller() -> export_tab.ExportTabController:
    ctrl = export_tab.ExportTabController()
    ctrl.include_identifiers = MagicMock(value=False)
    ctrl.fmt_select = MagicMock(value="pdf")
    ctrl.title_input = MagicMock(value="")
    ctrl.rich_report_dialog = MagicMock(close=MagicMock())
    return ctrl


@pytest.mark.asyncio
async def test_download_json_warns_without_results(_capture_notify) -> None:
    state.calculation_done = False
    state.output = None
    state.multi_exam_result = None
    ctrl = _controller()

    await ctrl.download_json()

    messages = [str(a[0]) if a else "" for a, _ in _capture_notify]
    assert any("No data to export" in m for m in messages)


@pytest.mark.asyncio
async def test_download_json_browser_mode(_capture_notify, monkeypatch) -> None:
    state.calculation_done = True
    state.output = {"psd": 1.23, "corrections": {}}
    state.multi_exam_result = None
    ctrl = _controller()
    downloaded: list[tuple] = []

    monkeypatch.setattr(export_tab, "_is_native_mode", lambda: False)
    monkeypatch.setattr(export_tab, "_get_save_path", AsyncMock(return_value=None))
    monkeypatch.setattr(ui, "download", lambda content, name: downloaded.append((content, name)))

    await ctrl.download_json()

    assert downloaded
    payload = json.loads(downloaded[0][0].decode("utf-8"))
    assert payload["psd"] == 1.23


def test_build_export_payload_includes_tabular_meta() -> None:
    ctrl = _controller()
    state.calculation_done = True
    state.output = {"psd": 2.0}
    state.multi_exam_result = None
    state.import_provenance = SimpleNamespace(schema_name="normalized")
    state.file_name = "events.csv"
    state.swap_lat_lon = False
    state.import_warnings = []

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        export_tab,
        "_tabular_input_meta",
        lambda *a, **k: {"schema": "normalized"},
    )
    try:
        payload = ctrl._build_export_payload()
    finally:
        monkeypatch.undo()

    assert payload["psd"] == 2.0
    assert payload["tabular_input"]["schema"] == "normalized"


@pytest.mark.asyncio
async def test_export_rich_report_requires_calculation(_capture_notify) -> None:
    state.calculation_done = False
    ctrl = _controller()

    await ctrl.export_rich_report()

    messages = [str(a[0]) if a else "" for a, _ in _capture_notify]
    assert any("calculation" in m.lower() for m in messages)


@pytest.mark.asyncio
async def test_export_rich_report_multi_exam_payload(monkeypatch, _capture_notify) -> None:
    state.calculation_done = True
    state.output = None
    state.multi_exam_result = SimpleNamespace(
        to_dict=MagicMock(return_value={"aggregate_psd": 3.0, "exams": []})
    )
    ctrl = _controller()
    rendered = b"%PDF-mock"

    monkeypatch.setattr(export_tab, "_is_native_mode", lambda: False)
    monkeypatch.setattr(export_tab, "_get_save_path", AsyncMock(return_value=None))
    monkeypatch.setattr(ctrl, "_render_rich_report", AsyncMock(return_value=rendered))
    monkeypatch.setattr(ui, "download", lambda *a, **k: None)

    await ctrl.export_rich_report()

    cast(MagicMock, ctrl._render_rich_report).assert_awaited_once_with("pdf", None)
