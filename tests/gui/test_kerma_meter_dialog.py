"""Kerma-meter correction-factor dialog: detection, pre-fill, Cancel/Confirm, guards."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest

pytest.importorskip("nicegui")

from nicegui.testing import User

from guiskindose.gui.state import state
from guiskindose.gui.tabs import _kerma_meter_dialog as dlg

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")


def _frame(stations: list[str | None], planes: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {"station_name": stations, "device_serial": [None] * len(stations), "acquisition_plane": planes}
    )


def _single_exam(stations=("Room-1", "Room-1"), planes=("Plane A", "Plane B")) -> None:
    state.rdsr_df = _frame(list(stations), list(planes))
    state.kerma_meter_enable = True


def _cf_file(tmp_path: Path, rows: str = "room-1,A,1.1\nroom-1,B,1.2\n") -> Path:
    path = tmp_path / "cf.csv"
    path.write_text("equipment,tube,correction_factor\n" + rows, encoding="utf-8")
    return path


def _two_exams() -> None:
    state.loaded_exams = [
        SimpleNamespace(normalized_data=_frame(["Room-1"], ["Plane A"])),
        SimpleNamespace(normalized_data=_frame([None], ["Single Plane"])),
    ]
    state.kerma_meter_enable = True


@pytest.fixture
def dialog_mock(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock()
    monkeypatch.setattr(dlg, "kerma_meter_dialog", mock)
    return mock


# ── load-time detection ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_miss_opens_dialog(dialog_mock: AsyncMock) -> None:
    _single_exam()
    assert await dlg.maybe_prompt_after_load() is True
    dialog_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_full_hit_from_manual_table_skips(dialog_mock: AsyncMock) -> None:
    _single_exam()
    state.kerma_meter_in_memory_table = {("room-1", "A"): 1.0, ("room-1", "B"): 1.0}
    assert await dlg.maybe_prompt_after_load() is False
    dialog_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_full_hit_from_file_skips(dialog_mock: AsyncMock, tmp_path: Path) -> None:
    _single_exam()
    state.kerma_meter_file = str(_cf_file(tmp_path))
    assert await dlg.maybe_prompt_after_load() is False
    dialog_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_partial_file_hit_still_prompts(dialog_mock: AsyncMock, tmp_path: Path) -> None:
    _single_exam()
    state.kerma_meter_file = str(_cf_file(tmp_path, "room-1,A,1.1\n"))
    assert await dlg.maybe_prompt_after_load() is True


@pytest.mark.asyncio
async def test_toggle_off_skips(dialog_mock: AsyncMock) -> None:
    _single_exam()
    state.kerma_meter_ask_for_missing = False
    assert await dlg.maybe_prompt_after_load() is False
    dialog_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_correction_disabled_skips(dialog_mock: AsyncMock) -> None:
    _single_exam()
    state.kerma_meter_enable = False
    assert await dlg.maybe_prompt_after_load() is False


@pytest.mark.asyncio
async def test_checked_once_per_revision_and_suppression(dialog_mock: AsyncMock) -> None:
    _single_exam()
    assert await dlg.maybe_prompt_after_load() is True
    assert await dlg.maybe_prompt_after_load() is False  # same revision: no nagging
    state.input_revision += 1
    state.kerma_meter_prompt_suppressed = True
    assert await dlg.maybe_prompt_after_load() is False


@pytest.mark.asyncio
async def test_multi_exam_miss_opens(dialog_mock: AsyncMock) -> None:
    _two_exams()
    assert await dlg.maybe_prompt_after_load() is True


# ── pre-fill: manual > file > default ───────────────────────────────────────


def test_rows_prefilled_manual_over_file_over_default(tmp_path: Path) -> None:
    _single_exam(stations=("Room-1", "Room-1", "Room-2"), planes=("Plane A", "Plane B", "Single Plane"))
    state.kerma_meter_file = str(_cf_file(tmp_path))
    state.kerma_meter_in_memory_table = {("room-1", "A"): 1.5}
    state.kerma_meter_default_factor = 0.95
    rows = {(r.equipment, r.tube): r for r in dlg.build_rows(state)}
    assert (rows[("room-1", "A")].value, rows[("room-1", "A")].source) == (1.5, dlg.SOURCE_ENTERED)
    assert (rows[("room-1", "B")].value, rows[("room-1", "B")].source) == (1.2, dlg.SOURCE_FILE)
    assert (rows[("room-2", "single")].value, rows[("room-2", "single")].source) == (0.95, dlg.SOURCE_DEFAULT)


def test_rows_grouped_by_exam_and_unknown_tube_visible() -> None:
    state.loaded_exams = [
        SimpleNamespace(normalized_data=_frame(["Room-1"], ["Plane A"])),
        SimpleNamespace(normalized_data=_frame(["Room-1"], ["not a plane"])),
    ]
    state.kerma_meter_enable = True
    rows = dlg.build_rows(state)
    assert [(r.exam, r.tube) for r in rows] == [("Exam 1", "A"), ("Exam 2", "unknown")]
    assert [r.editable for r in rows] == [True, False]


# ── Cancel / Confirm ─────────────────────────────────────────────────────────


def test_cancel_keeps_file_and_earlier_entries(tmp_path: Path) -> None:
    _single_exam()
    state.kerma_meter_file = str(_cf_file(tmp_path, "room-1,A,1.1\n"))
    state.kerma_meter_in_memory_table = {("other", "single"): 1.3}
    state.kerma_meter_unresolved_labels = {"Exam 1": "keep"}
    dlg.commit_cancel(state, dont_ask=False)
    assert state.kerma_meter_in_memory_table == {("other", "single"): 1.3}
    assert state.kerma_meter_file.endswith("cf.csv")
    assert state.kerma_meter_unresolved_labels == {"Exam 1": "keep"}
    # The unanswered pair stays missing; the engine then uses default_factor.
    assert dlg.missing_pairs(state) == [("room-1", "B")]
    dlg.commit_cancel(state, dont_ask=True)
    assert state.kerma_meter_prompt_suppressed is True


def test_confirm_writes_entered_and_defaults_but_not_unchanged_file_rows(tmp_path: Path) -> None:
    _single_exam()
    state.kerma_meter_file = str(_cf_file(tmp_path, "room-1,A,1.1\n"))
    state.kerma_meter_in_memory_table = {("earlier", "single"): 1.3}
    rows = dlg.build_rows(state)
    values = {(r.equipment, r.tube): r.value for r in rows}
    values[("room-1", "B")] = 1.25  # default row, confirmed with a new value
    dlg.commit_confirm(state, rows, values, {}, dont_ask=False)
    assert state.kerma_meter_in_memory_table == {("earlier", "single"): 1.3, ("room-1", "B"): 1.25}
    assert dlg.missing_pairs(state) == []


def test_confirm_changed_file_row_becomes_manual_entry(tmp_path: Path) -> None:
    _single_exam()
    state.kerma_meter_file = str(_cf_file(tmp_path))
    rows = dlg.build_rows(state)
    values = {(r.equipment, r.tube): r.value for r in rows}
    values[("room-1", "A")] = 1.4
    dlg.commit_confirm(state, rows, values, {}, dont_ask=False)
    assert state.kerma_meter_in_memory_table == {("room-1", "A"): 1.4}


# ── unresolved equipment ────────────────────────────────────────────────────


def test_unresolved_label_is_applied_and_rows_follow(tmp_path: Path) -> None:
    _two_exams()
    state.kerma_meter_file = str(_cf_file(tmp_path, "room-1,A,1.1\nroom-9,single,1.7\n"))
    assert ("unresolved", "single") in dlg.missing_pairs(state)
    assert "room-9" in dlg._unit_options(state)
    chosen = {"Exam 2": "Room-9"}
    rows = dlg.build_rows(state, chosen)
    exam2 = [r for r in rows if r.exam == "Exam 2"]
    assert [(r.equipment, r.value, r.source) for r in exam2] == [("room-9", 1.7, dlg.SOURCE_FILE)]
    dlg.commit_confirm(state, rows, {(r.equipment, r.tube): r.value for r in rows}, chosen, dont_ask=False)
    assert state.kerma_meter_unresolved_labels == {"Exam 2": "Room-9"}
    assert dlg.missing_pairs(state) == []


def test_blank_label_clears_override() -> None:
    _two_exams()
    state.kerma_meter_unresolved_labels = {"Exam 2": "old"}
    dlg.commit_confirm(state, [], {}, {"Exam 2": "  "}, dont_ask=False)
    assert state.kerma_meter_unresolved_labels == {}


# ── Calculate guard ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_calculate_guard_reopens_once(dialog_mock: AsyncMock) -> None:
    _single_exam()
    assert await dlg.prompt_at_calculate() is True
    assert await dlg.prompt_at_calculate() is False  # only once per loaded-data revision
    assert dialog_mock.await_count == 1


@pytest.mark.asyncio
async def test_calculate_guard_skips_when_everything_answered(dialog_mock: AsyncMock) -> None:
    _single_exam()
    state.kerma_meter_in_memory_table = {("room-1", "A"): 1.0, ("room-1", "B"): 1.0}
    assert await dlg.prompt_at_calculate() is False


def test_rebuild_resets_dialog_flags() -> None:
    from guiskindose.gui.exam_transforms import rebuild_rdsr_df

    state.kerma_meter_prompt_suppressed = True
    state.kerma_meter_calc_reprompted = True
    rebuild_rdsr_df(state)
    assert state.kerma_meter_prompt_suppressed is False
    assert state.kerma_meter_calc_reprompted is False


# ── rendered dialog ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rendered_dialog_confirm_stores_entries(user: User) -> None:
    await user.open("/")
    _single_exam()
    task = asyncio.create_task(_run_in_client(user))
    await user.should_see("Kerma-meter correction factors", retries=30)
    await user.should_see("default: review", retries=30)
    user.find("Confirm").click()
    await asyncio.wait_for(task, timeout=5)
    assert state.kerma_meter_in_memory_table == {("room-1", "A"): 1.0, ("room-1", "B"): 1.0}


async def _run_in_client(user: User) -> None:
    from nicegui import Client

    client = next(iter(Client.instances.values()))
    with client:
        await dlg.kerma_meter_dialog()
