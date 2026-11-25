"""Native save-dialog failure vs cancellation contract.

``_get_save_path`` keeps returning ``None`` both when the user cancels and when
the native dialog fails, but a failure must first tell the user (one ERROR log
event plus one notification) while a genuine cancel stays silent. The
per-caller pairs prove each of the seven call sites aborts without its
write/download/label seam on either path, and notifies only on failure.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("nicegui")

from nicegui import ui

from guiskindose.gui import io_helpers
from guiskindose.gui.state import state
from guiskindose.gui.ui_copy import copy_text

_FAILURE_SENTENCE = copy_text("native.save_dialog.failure")
_IO_HELPERS_LOGGER = "guiskindose.gui.io_helpers"


@pytest.fixture(autouse=True)
def _capture_notify(monkeypatch):
    calls: list[tuple[tuple, dict]] = []
    monkeypatch.setattr(ui, "notify", lambda *a, **k: calls.append((a, k)))
    return calls


def _failure_events(caplog: pytest.LogCaptureFixture) -> list:
    return [
        record
        for record in caplog.records
        if record.name == _IO_HELPERS_LOGGER
        and record.levelno >= logging.ERROR
        and record.getMessage().startswith("native_save_dialog")
    ]


def _check_failure_notice(calls: list[tuple[tuple, dict]]) -> None:
    assert len(calls) == 1, calls
    args, kwargs = calls[0]
    assert args[0] == _FAILURE_SENTENCE
    assert kwargs.get("type") == "negative"


async def _raise_dialog_error(_default_name: str, _extension: str):
    raise RuntimeError("synthetic dialog failure")


async def _cancel_dialog(_default_name: str, _extension: str):
    return None


def _patch_native_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(io_helpers, "_request_native_save_path", _raise_dialog_error)
    monkeypatch.setattr(io_helpers, "_is_native_mode", lambda: True)


def _patch_native_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(io_helpers, "_request_native_save_path", _cancel_dialog)
    monkeypatch.setattr(io_helpers, "_is_native_mode", lambda: True)


# ── wrapper contract ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_wrapper_reports_failure_once_and_returns_none(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, _capture_notify
) -> None:
    caplog.set_level(logging.INFO, logger=_IO_HELPERS_LOGGER)
    _patch_native_failure(monkeypatch)

    assert await io_helpers._get_save_path("out.json", "json") is None

    assert len(_failure_events(caplog)) == 1
    _check_failure_notice(_capture_notify)
    assert len(_failure_events(caplog)) == 1  # one log event per failure, at the wrapper only


@pytest.mark.asyncio
async def test_wrapper_passes_cancel_through_silently(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, _capture_notify
) -> None:
    caplog.set_level(logging.INFO, logger=_IO_HELPERS_LOGGER)
    _patch_native_cancel(monkeypatch)

    assert await io_helpers._get_save_path("out.json", "json") is None

    assert _failure_events(caplog) == []
    assert _capture_notify == []


@pytest.mark.asyncio
async def test_wrapper_passes_chosen_path_through(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, _capture_notify
) -> None:
    caplog.set_level(logging.INFO, logger=_IO_HELPERS_LOGGER)
    monkeypatch.setattr(io_helpers, "_request_native_save_path", AsyncMock(return_value="/tmp/out.json"))

    assert await io_helpers._get_save_path("out.json", "json") == "/tmp/out.json"

    assert _failure_events(caplog) == []
    assert _capture_notify == []


@pytest.mark.asyncio
async def test_wrapper_lets_cancellation_propagate(monkeypatch: pytest.MonkeyPatch, _capture_notify) -> None:
    async def _cancelled(_default_name: str, _extension: str):
        raise asyncio.CancelledError("The app has shut down.")

    monkeypatch.setattr(io_helpers, "_request_native_save_path", _cancelled)

    with pytest.raises(asyncio.CancelledError):
        await io_helpers._get_save_path("out.json", "json")
    assert _capture_notify == []


# ── per-caller pairs ──────────────────────────────────────────────────────


def _ready_export_state() -> None:
    state.calculation_done = True
    state.output = {"psd": 1.0}
    state.multi_exam_result = None
    state.import_provenance = None


def _native_caller(monkeypatch: pytest.MonkeyPatch, module) -> None:
    monkeypatch.setattr(module, "_is_native_mode", lambda: True)


@pytest.mark.asyncio
async def test_download_json_failure_notifies_and_skips_write(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, _capture_notify
) -> None:
    from guiskindose.gui.tabs import export as export_tab

    _ready_export_state()
    caplog.set_level(logging.INFO, logger=_IO_HELPERS_LOGGER)
    _patch_native_failure(monkeypatch)
    _native_caller(monkeypatch, export_tab)
    written: list = []
    monkeypatch.setattr(export_tab, "_write_or_download", lambda *a: written.append(a))

    await export_tab.ExportTabController().download_json()

    _check_failure_notice(_capture_notify)
    assert len(_failure_events(caplog)) == 1  # one log event per failure, at the wrapper only
    assert written == []


@pytest.mark.asyncio
async def test_download_json_cancel_stays_silent(monkeypatch: pytest.MonkeyPatch, _capture_notify) -> None:
    from guiskindose.gui.tabs import export as export_tab

    _ready_export_state()
    _patch_native_cancel(monkeypatch)
    _native_caller(monkeypatch, export_tab)
    written: list = []
    monkeypatch.setattr(export_tab, "_write_or_download", lambda *a: written.append(a))

    await export_tab.ExportTabController().download_json()

    assert _capture_notify == []
    assert written == []


@pytest.mark.asyncio
async def test_download_html_failure_notifies_and_skips_render(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, _capture_notify
) -> None:
    from guiskindose.gui.tabs import export as export_tab

    _ready_export_state()
    caplog.set_level(logging.INFO, logger=_IO_HELPERS_LOGGER)
    _patch_native_failure(monkeypatch)
    _native_caller(monkeypatch, export_tab)
    rendered: list = []
    monkeypatch.setattr(export_tab, "make_dosemap_html", lambda *a, **k: rendered.append((a, k)))

    await export_tab.ExportTabController().download_html()

    _check_failure_notice(_capture_notify)
    assert len(_failure_events(caplog)) == 1  # one log event per failure, at the wrapper only
    assert rendered == []


@pytest.mark.asyncio
async def test_download_html_cancel_stays_silent(monkeypatch: pytest.MonkeyPatch, _capture_notify) -> None:
    from guiskindose.gui.tabs import export as export_tab

    _ready_export_state()
    _patch_native_cancel(monkeypatch)
    _native_caller(monkeypatch, export_tab)
    rendered: list = []
    monkeypatch.setattr(export_tab, "make_dosemap_html", lambda *a, **k: rendered.append((a, k)))

    await export_tab.ExportTabController().download_html()

    assert _capture_notify == []
    assert rendered == []


@pytest.mark.asyncio
async def test_download_png_failure_notifies_and_skips_render(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, _capture_notify
) -> None:
    from guiskindose.gui.tabs import export as export_tab

    _ready_export_state()
    caplog.set_level(logging.INFO, logger=_IO_HELPERS_LOGGER)
    _patch_native_failure(monkeypatch)
    _native_caller(monkeypatch, export_tab)
    monkeypatch.setattr(export_tab, "png_export_available", lambda: True)
    rendered: list = []
    monkeypatch.setattr(export_tab, "make_dosemap_png", lambda *a, **k: rendered.append((a, k)))

    await export_tab.ExportTabController().download_png()

    _check_failure_notice(_capture_notify)
    assert len(_failure_events(caplog)) == 1  # one log event per failure, at the wrapper only
    assert rendered == []


@pytest.mark.asyncio
async def test_download_png_cancel_stays_silent(monkeypatch: pytest.MonkeyPatch, _capture_notify) -> None:
    from guiskindose.gui.tabs import export as export_tab

    _ready_export_state()
    _patch_native_cancel(monkeypatch)
    _native_caller(monkeypatch, export_tab)
    monkeypatch.setattr(export_tab, "png_export_available", lambda: True)
    rendered: list = []
    monkeypatch.setattr(export_tab, "make_dosemap_png", lambda *a, **k: rendered.append((a, k)))

    await export_tab.ExportTabController().download_png()

    assert _capture_notify == []
    assert rendered == []


def _rich_report_controller():
    from guiskindose.gui.tabs import export as export_tab

    ctrl = export_tab.ExportTabController()
    ctrl.include_identifiers = MagicMock(value=False)
    ctrl.fmt_select = MagicMock(value="pdf")
    ctrl.title_input = MagicMock(value="")
    ctrl.rich_report_dialog = MagicMock(close=MagicMock())
    return ctrl


@pytest.mark.asyncio
async def test_export_rich_report_failure_keeps_dialog_open(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, _capture_notify
) -> None:
    from guiskindose.gui.tabs import export as export_tab

    state.calculation_done = True
    caplog.set_level(logging.INFO, logger=_IO_HELPERS_LOGGER)
    _patch_native_failure(monkeypatch)
    _native_caller(monkeypatch, export_tab)
    ctrl = _rich_report_controller()
    monkeypatch.setattr(ctrl, "_render_rich_report", AsyncMock(side_effect=AssertionError("must not render")))

    await ctrl.export_rich_report()

    _check_failure_notice(_capture_notify)
    assert len(_failure_events(caplog)) == 1  # one log event per failure, at the wrapper only
    cast(MagicMock, ctrl.rich_report_dialog.close).assert_not_called()


@pytest.mark.asyncio
async def test_export_rich_report_cancel_stays_silent(monkeypatch: pytest.MonkeyPatch, _capture_notify) -> None:
    from guiskindose.gui.tabs import export as export_tab

    state.calculation_done = True
    _patch_native_cancel(monkeypatch)
    _native_caller(monkeypatch, export_tab)
    ctrl = _rich_report_controller()
    monkeypatch.setattr(ctrl, "_render_rich_report", AsyncMock(side_effect=AssertionError("must not render")))

    await ctrl.export_rich_report()

    assert _capture_notify == []
    cast(MagicMock, ctrl.rich_report_dialog.close).assert_not_called()


def _run_config_settings_stub() -> SimpleNamespace:
    return SimpleNamespace(normalization_settings=SimpleNamespace(to_profile_list=lambda: []))


@pytest.mark.asyncio
async def test_run_config_save_failure_notifies_and_keeps_label(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, _capture_notify
) -> None:
    from guiskindose.gui.tabs import _run_config as run_config_tab

    caplog.set_level(logging.INFO, logger=_IO_HELPERS_LOGGER)
    _patch_native_failure(monkeypatch)
    _native_caller(monkeypatch, run_config_tab)
    monkeypatch.setattr(run_config_tab, "_pending_blocks_export", lambda _s: False)
    monkeypatch.setattr(run_config_tab, "build_settings", lambda _s: _run_config_settings_stub())
    monkeypatch.setattr(run_config_tab, "serialize_run_state", lambda *a, **k: {"ok": True})
    written: list = []
    monkeypatch.setattr(run_config_tab, "_write_or_download", lambda *a: written.append(a))
    status_label = MagicMock()

    await run_config_tab._on_save(MagicMock(value=False), status_label)

    _check_failure_notice(_capture_notify)
    assert len(_failure_events(caplog)) == 1  # one log event per failure, at the wrapper only
    assert written == []
    status_label.set_text.assert_not_called()


@pytest.mark.asyncio
async def test_run_config_save_cancel_stays_silent(monkeypatch: pytest.MonkeyPatch, _capture_notify) -> None:
    from guiskindose.gui.tabs import _run_config as run_config_tab

    _patch_native_cancel(monkeypatch)
    _native_caller(monkeypatch, run_config_tab)
    monkeypatch.setattr(run_config_tab, "_pending_blocks_export", lambda _s: False)
    monkeypatch.setattr(run_config_tab, "build_settings", lambda _s: _run_config_settings_stub())
    monkeypatch.setattr(run_config_tab, "serialize_run_state", lambda *a, **k: {"ok": True})
    written: list = []
    monkeypatch.setattr(run_config_tab, "_write_or_download", lambda *a: written.append(a))
    status_label = MagicMock()

    await run_config_tab._on_save(MagicMock(value=False), status_label)

    assert _capture_notify == []
    assert written == []
    status_label.set_text.assert_not_called()


@pytest.mark.asyncio
async def test_example_calibration_failure_notifies_and_skips_write(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, _capture_notify
) -> None:
    from guiskindose.gui.tabs import corrections as corrections_tab
    from guiskindose.gui.tabs import export as export_tab

    caplog.set_level(logging.INFO, logger=_IO_HELPERS_LOGGER)
    _patch_native_failure(monkeypatch)
    written: list = []
    monkeypatch.setattr(export_tab, "_write_or_download", lambda *a: written.append(a))

    await corrections_tab._download_example_calibration_file()

    _check_failure_notice(_capture_notify)
    assert len(_failure_events(caplog)) == 1  # one log event per failure, at the wrapper only
    assert written == []


@pytest.mark.asyncio
async def test_example_calibration_cancel_stays_silent(monkeypatch: pytest.MonkeyPatch, _capture_notify) -> None:
    from guiskindose.gui.tabs import corrections as corrections_tab
    from guiskindose.gui.tabs import export as export_tab

    _patch_native_cancel(monkeypatch)
    written: list = []
    monkeypatch.setattr(export_tab, "_write_or_download", lambda *a: written.append(a))

    await corrections_tab._download_example_calibration_file()

    assert _capture_notify == []
    assert written == []


@pytest.mark.asyncio
async def test_data_export_failure_notifies_and_skips_write(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, _capture_notify
) -> None:
    import pandas as pd

    from guiskindose.gui.tabs import data as data_tab

    state.view_raw = False
    state.rdsr_df = pd.DataFrame({"Tx": [1.0]})
    caplog.set_level(logging.INFO, logger=_IO_HELPERS_LOGGER)
    _patch_native_failure(monkeypatch)
    _native_caller(monkeypatch, data_tab)
    monkeypatch.setattr(
        data_tab, "_export_content", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not build"))
    )
    downloaded: list = []
    monkeypatch.setattr(ui, "download", lambda *a: downloaded.append(a))

    await data_tab._local_export("csv")

    _check_failure_notice(_capture_notify)
    assert len(_failure_events(caplog)) == 1  # one log event per failure, at the wrapper only
    assert downloaded == []


@pytest.mark.asyncio
async def test_data_export_cancel_stays_silent(monkeypatch: pytest.MonkeyPatch, _capture_notify) -> None:
    import pandas as pd

    from guiskindose.gui.tabs import data as data_tab

    state.view_raw = False
    state.rdsr_df = pd.DataFrame({"Tx": [1.0]})
    _patch_native_cancel(monkeypatch)
    _native_caller(monkeypatch, data_tab)
    monkeypatch.setattr(
        data_tab, "_export_content", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not build"))
    )
    downloaded: list = []
    monkeypatch.setattr(ui, "download", lambda *a: downloaded.append(a))

    await data_tab._local_export("csv")

    assert _capture_notify == []
    assert downloaded == []
