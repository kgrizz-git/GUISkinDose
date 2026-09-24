"""GUI round-trip tests for run-configuration export/import (Phase 3 chunk F).

Style follows the live-widget criterion: the import path runs against the
real page (NiceGUI `user` fixture) with stub refresh callbacks, asserting
restored state, invoked refreshes, surfaced notifications, and rendered
widget values — not just `AppState`.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from nicegui import ui
from nicegui.testing import User

pytest.importorskip("nicegui")

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")

from guiskindose import load_settings_example_json  # noqa: E402
from guiskindose.gui.page_context import PageContext  # noqa: E402
from guiskindose.gui.run_state import serialize_run_state  # noqa: E402
from guiskindose.gui.state import AppState, state  # noqa: E402
from guiskindose.gui.tabs import _run_config as run_config_mod  # noqa: E402
from guiskindose.settings import PyskindoseSettings  # noqa: E402


def _example_settings() -> PyskindoseSettings:
    base = load_settings_example_json()
    base["kerma_meter_correction"] = {
        "enable": True,
        "mode": "file",
        "file": "/data/cf/corrections.xlsx",
        "file_sheet": "CF",
        "default_factor": 1.02,
        "explicit_label": "Lab-1",
        "prompt_at_calc": False,
    }
    base["phantom"]["patient_offset"] = {"d_lon": 1.0, "d_ver": 2.0, "d_lat": 3.0}
    return PyskindoseSettings(settings=base)


def _seed_single_exam() -> None:
    """Load one synthetic exam into the singleton (the import prerequisite)."""
    state.kerma_meter_file = "/data/cf/corrections.xlsx"
    state.file_path = Path("/data/inbox/export.xlsx")
    state.input_source_type = "xlsx"
    state.loaded_exam_meta = [
        {
            "file_name": "export.xlsx",
            "file_path": Path("/data/inbox/export.xlsx"),
            "study_id": "STUDY-1",
            "input_manufacturer": "Acme",
            "input_model": "X1000",
            "source_type": "xlsx",
            "schema": "dosetrack",
            "sheet": "Events",
            "normalization_method": "Matched",
            "table_origin_detected": {"x": 1.0, "y": 2.0, "z": 3.0},
            "d_lon": 0.0,
            "d_ver": 0.0,
            "d_lat": 0.0,
        }
    ]


def _make_document() -> dict:
    populated = AppState()
    populated.input_schema = "dosetrack"
    populated.input_source_type = "xlsx"
    populated.input_sheet_name = "Events"
    populated.swap_lat_lon = True
    populated.d_lon, populated.d_ver, populated.d_lat = 1.0, 2.0, 3.0
    populated.kerma_meter_in_memory_table = {("Acme", "TubeA"): 1.02}
    populated.loaded_exam_meta = [
        {
            "d_lon": 1.0,
            "d_ver": 2.0,
            "d_lat": 3.0,
            "table_origin_override": {"x": 0.0, "y": 0.0, "z": 0.0},
            "table_origin_detected": {"x": 1.0, "y": 2.0, "z": 3.0},
            "swap_lat_lon": True,
            "flip_tx": True,
            "source_type": "xlsx",
            "schema": "dosetrack",
            "sheet": "Events",
            "normalization_method": "Matched",
            "study_id": "STUDY-1",
            "file_name": "export.xlsx",
            "file_path": Path("/data/inbox/export.xlsx"),
            "input_manufacturer": "Acme",
            "input_model": "X1000",
        }
    ]
    return serialize_run_state(
        _example_settings(),
        populated,
        include_identifiers=True,
        app_version="1.0.0",
        created="2026-09-24T00:00:00+00:00",
    )


def _upload_event(document: dict) -> SimpleNamespace:
    payload = json.dumps(document).encode("utf-8")

    async def _read() -> bytes:
        return payload

    return SimpleNamespace(file=SimpleNamespace(read=_read))


def _stub_ctx(calls: list[str]) -> PageContext:
    ctx = PageContext(
        tabs=MagicMock(),
        file_label=MagicMock(),
        events_label=MagicMock(),
        psd_label=MagicMock(),
        run_btn_drawer=MagicMock(),
    )
    ctx.refresh_event_table = lambda: calls.append("event_table")
    ctx.refresh_exams_table = lambda: calls.append("exams_table")
    ctx.refresh_import_preview = lambda: calls.append("import_preview")
    ctx.refresh_per_exam = lambda: calls.append("per_exam")
    ctx.refresh_geometry_tab = lambda: calls.append("geometry_tab")
    return ctx


def _client(user: User) -> Any:
    assert user.client is not None
    return user.client


def _number_by_label(user: User, label: str) -> Any:
    for el in _client(user).elements.values():
        if isinstance(el, ui.number) and el._props.get("label") == label:
            return el
    raise AssertionError(f"ui.number with label {label!r} not found")


@pytest.mark.asyncio
async def test_run_config_card_renders(user: User) -> None:
    """Settings tab shows the run-configuration card (chunk-E wiring)."""
    await user.open("/")
    user.find("3 · Settings").click()
    await user.should_see("Run configuration")
    await user.should_see("Save run configuration")


@pytest.mark.asyncio
async def test_import_restores_state_invokes_refresh_and_clears_results(user: User) -> None:
    """Full `_do_load` path: state restored, every refresh fired, results reset."""
    await user.open("/")
    _seed_single_exam()
    state.calculation_done = True
    state.output = {"psd": 1.0}
    calls: list[str] = []
    with _client(user):
        status = ui.label("")
    await run_config_mod._do_load(_upload_event(_make_document()), _stub_ctx(calls), status)
    assert state.d_lon == 1.0
    assert state.input_schema == "dosetrack"
    assert state.loaded_exam_meta[0]["flip_tx"] is True
    assert state.kerma_meter_in_memory_table == {("Acme", "TubeA"): 1.02}
    assert calls == ["event_table", "exams_table", "import_preview", "per_exam", "geometry_tab"]
    assert state.calculation_done is False
    assert state.output is None
    assert "1 exam" in status.text


@pytest.mark.asyncio
async def test_import_updates_rendered_widget_values(user: User) -> None:
    """Bound settings widgets reflect imported values on the live page."""
    await user.open("/")
    user.find("3 · Settings").click()
    await user.should_see("Run configuration")
    lon = _number_by_label(user, "Longitudinal")
    assert lon.value == 0
    _seed_single_exam()
    calls: list[str] = []
    with _client(user):
        status = ui.label("")
    await run_config_mod._do_load(_upload_event(_make_document()), _stub_ctx(calls), status)
    # Reactive binding propagates on the next client round-trips: poll
    # instead of sleeping a fixed span (flaky under load).
    for _ in range(50):
        if _number_by_label(user, "Longitudinal").value == 1.0:
            break
        await asyncio.sleep(0.1)
    assert _number_by_label(user, "Longitudinal").value == 1.0


@pytest.mark.asyncio
async def test_import_mismatch_warning_surfaces_live_untouched(user: User) -> None:
    """File-handle divergence notifies loudly and never overwrites the path.

    Notifications are captured by the harness `user.notify` recorder
    (NiceGUI reinstalls it on every `user.*` interaction, so manual
    monkeypatching of `ui.notify` cannot stick — use the recorder).
    """
    await user.open("/")
    _seed_single_exam()
    state.kerma_meter_file = "/other/place/custom.xlsx"
    with _client(user):
        status = ui.label("")
    await run_config_mod._do_load(_upload_event(_make_document()), _stub_ctx([]), status)
    assert state.kerma_meter_file == "/other/place/custom.xlsx"
    assert user.notify.contains("kerma correction file")
    assert user.notify.contains("mismatch")


@pytest.mark.asyncio
async def test_import_refuses_while_busy(user: User) -> None:
    """An in-flight operation blocks import before anything is applied."""
    await user.open("/")
    _seed_single_exam()
    state.busy = True
    try:
        with _client(user):
            status = ui.label("")
        await run_config_mod._do_load(_upload_event(_make_document()), _stub_ctx([]), status)
    finally:
        state.busy = False
    assert state.input_schema == "auto"  # nothing applied
    assert state.d_lon == 0.0
    assert user.notify.contains("Busy")


@pytest.mark.asyncio
async def test_import_rereparses_before_restoring_offsets(user: User, monkeypatch: pytest.MonkeyPatch) -> None:
    """Schema change triggers re-parse; offsets land on the rebuilt metas."""
    await user.open("/")
    _seed_single_exam()
    reparse_calls: list[str] = []

    def _fake_load_tabular(file_path: Path, app_state: AppState, _force: bool = True) -> tuple[bool, str]:
        reparse_calls.append(str(file_path))
        # Simulate the rebuild wiping per-exam offsets/toggles AND landing on
        # a different sheet than the document: only the post-rebuild re-apply
        # can restore the documented values (a self-fulfilling fake would
        # write "Other" itself and prove nothing).
        app_state.loaded_exam_meta = [
            {
                "file_name": "export.xlsx",
                "file_path": Path("/data/inbox/export.xlsx"),
                "study_id": "STUDY-1",
                "input_manufacturer": "Acme",
                "input_model": "X1000",
                "source_type": "xlsx",
                "schema": "dosetrack",
                "sheet": "WrongSheet",
                "normalization_method": "Matched",
                "table_origin_detected": {"x": 1.0, "y": 2.0, "z": 3.0},
            }
        ]
        return True, "ok"

    monkeypatch.setattr(run_config_mod, "load_tabular", _fake_load_tabular)
    with _client(user):
        status = ui.label("")
    document = _make_document()
    document["gui_state"]["input_sheet_name"] = "Other"
    document["gui_state"]["exams"][0]["sheet"] = "Other"
    await run_config_mod._do_load(_upload_event(document), _stub_ctx([]), status)
    assert reparse_calls == [str(Path("/data/inbox/export.xlsx"))]
    meta = state.loaded_exam_meta[0]
    assert (meta["d_lon"], meta["d_ver"], meta["d_lat"]) == (1.0, 2.0, 3.0)
    assert meta["sheet"] == "Other"
