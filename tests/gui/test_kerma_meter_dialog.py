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
from guiskindose.gui.tabs._kerma_meter_model import unit_options

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
    model = dlg.FactorModel(state)
    model.set_value("Exam 1", ("room-1", "B"), 1.25)  # default row, confirmed with a new value
    model.commit(dont_ask=False)
    assert state.kerma_meter_in_memory_table == {("earlier", "single"): 1.3, ("Exam 1", "room-1", "B"): 1.25}
    assert dlg.missing_pairs(state) == []


def test_confirm_changed_file_row_becomes_manual_entry(tmp_path: Path) -> None:
    _single_exam()
    state.kerma_meter_file = str(_cf_file(tmp_path))
    model = dlg.FactorModel(state)
    model.set_value("Exam 1", ("room-1", "A"), 1.4)
    model.commit(dont_ask=False)
    assert state.kerma_meter_in_memory_table == {("Exam 1", "room-1", "A"): 1.4}


# ── unresolved equipment ────────────────────────────────────────────────────


def test_unresolved_label_is_applied_and_rows_follow(tmp_path: Path) -> None:
    _two_exams()
    state.kerma_meter_file = str(_cf_file(tmp_path, "room-1,A,1.1\nroom-9,single,1.7\n"))
    assert ("unresolved", "single") in dlg.missing_pairs(state)
    assert "room-9" in unit_options(state)
    chosen = {"Exam 2": "Room-9"}
    model = dlg.FactorModel(state, chosen)
    exam2 = [r for r in model.rows() if r.exam == "Exam 2"]
    assert [(r.equipment, r.value, r.source) for r in exam2] == [("room-9", 1.7, dlg.SOURCE_FILE)]
    model.commit(dont_ask=False)
    assert state.kerma_meter_unresolved_labels == {"Exam 2": "Room-9"}
    assert dlg.missing_pairs(state) == []


def test_blank_label_clears_override() -> None:
    _two_exams()
    state.kerma_meter_unresolved_labels = {"Exam 2": "old"}
    dlg.FactorModel(state, {"Exam 2": "  "}).commit(dont_ask=False)
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
    assert state.kerma_meter_in_memory_table == {
        ("Exam 1", "room-1", "A"): 1.0,
        ("Exam 1", "room-1", "B"): 1.0,
    }


async def _run_in_client(user: User) -> None:
    from nicegui import Client

    client = next(iter(Client.instances.values()))
    with client:
        await dlg.kerma_meter_dialog()


# ── per-exam label drift ─────────────────────────────────────────────────────


def test_unresolved_labels_survive_append_and_transform_rebuild() -> None:
    from guiskindose.gui.exam_transforms import rebuild_rdsr_df

    first = SimpleNamespace(normalized_data=_frame([None], ["Plane A"]))
    state.loaded_exams = [first]
    rebuild_rdsr_df(state)
    state.kerma_meter_unresolved_labels = {"Exam 1": "Room-1"}
    rebuild_rdsr_df(state)  # e.g. an offset/transform rebuild: same exams
    assert state.kerma_meter_unresolved_labels == {"Exam 1": "Room-1"}
    state.loaded_exams.append(SimpleNamespace(normalized_data=_frame([None], ["Plane A"])))
    rebuild_rdsr_df(state)  # appended exam: positions unchanged
    assert state.kerma_meter_unresolved_labels == {"Exam 1": "Room-1"}


def test_unresolved_labels_cleared_on_removal_or_reorder() -> None:
    from guiskindose.gui.exam_transforms import rebuild_rdsr_df

    a = SimpleNamespace(normalized_data=_frame([None], ["Plane A"]))
    b = SimpleNamespace(normalized_data=_frame([None], ["Plane B"]))
    state.loaded_exams = [a, b]
    rebuild_rdsr_df(state)
    state.kerma_meter_unresolved_labels = {"Exam 2": "Room-2"}
    state.loaded_exams.pop(0)  # b is now Exam 1: the old "Exam 2" label is stale
    rebuild_rdsr_df(state)
    assert state.kerma_meter_unresolved_labels == {}
    state.loaded_exams = [a, b]
    rebuild_rdsr_df(state)
    state.kerma_meter_unresolved_labels = {"Exam 1": "Room-1"}
    state.loaded_exams = [b, a]  # reorder
    rebuild_rdsr_df(state)
    assert state.kerma_meter_unresolved_labels == {}


# ── review follow-ups: shared pairs, validation, stale results, re-check keys ─


def test_same_pair_in_two_exams_has_a_row_per_exam() -> None:
    state.loaded_exams = [
        SimpleNamespace(normalized_data=_frame(["Room-1"], ["Plane A"])),
        SimpleNamespace(normalized_data=_frame(["Room-1"], ["Plane A"])),
    ]
    state.kerma_meter_enable = True
    assert [(r.exam, r.equipment, r.tube) for r in dlg.build_rows(state)] == [
        ("Exam 1", "room-1", "A"),
        ("Exam 2", "room-1", "A"),
    ]


def test_invalid_rows_flag_blank_zero_negative_and_nan() -> None:
    _single_exam(stations=("Room-1",) * 4, planes=("Plane A", "Plane B", "Single Plane", "not a plane"))
    model = dlg.FactorModel(state)
    model.set_value("Exam 1", ("room-1", "A"), None)
    model.set_value("Exam 1", ("room-1", "B"), 0.0)
    model.set_value("Exam 1", ("room-1", "single"), float("nan"))
    assert [pair for _, pair in model.invalid()] == [("room-1", "A"), ("room-1", "B"), ("room-1", "single")]
    model.set_value("Exam 1", ("room-1", "A"), 1.0)
    model.set_value("Exam 1", ("room-1", "B"), 1.1)
    model.set_value("Exam 1", ("room-1", "single"), 0.9)
    assert model.invalid() == []


def test_commit_rejects_blank_factor_and_leaves_state_untouched() -> None:
    _single_exam()
    state.kerma_meter_in_memory_table = {("Exam 1", "room-1", "A"): 1.3}
    model = dlg.FactorModel(state)
    model.set_value("Exam 1", ("room-1", "A"), None)
    with pytest.raises(ValueError, match="above zero"):
        model.commit(dont_ask=False)
    assert state.kerma_meter_in_memory_table == {("Exam 1", "room-1", "A"): 1.3}


async def _wait_for_task(task: asyncio.Task, user: User) -> None:
    await asyncio.wait_for(task, timeout=5)


@pytest.mark.asyncio
async def test_rendered_dialog_blank_value_blocks_confirm(user: User) -> None:
    from nicegui import ui

    await user.open("/")
    _single_exam()
    task = asyncio.create_task(_run_in_client(user))
    await user.should_see("Kerma-meter correction factors", retries=30)
    assert user.client is not None
    field = next(
        el
        for el in user.client.elements.values()
        if isinstance(el, ui.number) and el._props.get("label") == "room-1 / A"
    )
    field.set_value(None)
    user.find("Confirm").click()
    await user.should_see("Enter a number greater than zero", retries=30)
    assert not task.done()
    assert state.kerma_meter_in_memory_table is None
    field.set_value(1.25)  # a valid entry unblocks Confirm
    user.find("Confirm").click()
    await _wait_for_task(task, user)
    assert state.kerma_meter_in_memory_table == {
        ("Exam 1", "room-1", "A"): 1.25,
        ("Exam 1", "room-1", "B"): 1.0,
    }


@pytest.mark.asyncio
async def test_stale_dialog_result_is_discarded(user: User) -> None:
    await user.open("/")
    _single_exam()
    task = asyncio.create_task(_run_in_client(user))
    await user.should_see("Kerma-meter correction factors", retries=30)
    state.input_revision += 1  # loaded data changed while the dialog was open
    user.find("Confirm").click()
    await _wait_for_task(task, user)
    assert state.kerma_meter_in_memory_table is None


@pytest.mark.asyncio
async def test_review_dialog_requires_enabled_correction_and_events(dialog_mock: AsyncMock, user: User) -> None:
    await user.open("/")
    assert user.client is not None
    with user.client:
        assert await dlg.open_review_dialog() is False
    dialog_mock.assert_not_awaited()
    _single_exam()
    state.kerma_meter_in_memory_table = {("room-1", "A"): 1.0, ("room-1", "B"): 1.0}  # nothing missing
    with user.client:
        assert await dlg.open_review_dialog() is True
    dialog_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_recheck_when_file_or_ask_toggle_changes(dialog_mock: AsyncMock, tmp_path: Path) -> None:
    _single_exam()
    state.kerma_meter_ask_for_missing = False
    assert await dlg.maybe_prompt_after_load() is False
    state.kerma_meter_ask_for_missing = True  # turning asking on re-checks
    assert await dlg.maybe_prompt_after_load() is True
    state.kerma_meter_file = str(_cf_file(tmp_path, "room-1,A,1.1\n"))  # selecting a file re-checks
    assert await dlg.maybe_prompt_after_load() is True
    assert dialog_mock.await_count == 2


# ── per-exam factors, follow-previous, calibration periods ──────────────────

_OLD = "2026-01-01|2026-06-30"
_NEW = "2026-07-01|"


def _three_exams() -> None:
    state.loaded_exams = [SimpleNamespace(normalized_data=_frame(["Room-1"], ["Plane A"])) for _ in range(3)]
    state.kerma_meter_enable = True


def _dated_file(tmp_path: Path) -> Path:
    path = tmp_path / "dated.csv"
    path.write_text(
        "equipment,tube,correction_factor,valid_from,valid_to\n"
        "room-1,A,1.10,2026-01-01,2026-06-30\n"
        "room-1,A,1.25,2026-07-01,\n",
        encoding="utf-8",
    )
    return path


def _row(model: dlg.FactorModel, exam: str):
    return next(r for r in model.rows() if r.exam == exam)


def test_exams_can_hold_different_values_for_the_same_pair() -> None:
    _three_exams()
    model = dlg.FactorModel(state)
    model.set_value("Exam 1", ("room-1", "A"), 1.1)
    model.set_value("Exam 2", ("room-1", "A"), 1.3)
    model.commit(dont_ask=False)
    table = state.kerma_meter_in_memory_table
    assert table is not None
    assert table[("Exam 1", "room-1", "A")] == pytest.approx(1.1)
    assert table[("Exam 2", "room-1", "A")] == pytest.approx(1.3)
    assert table[("Exam 3", "room-1", "A")] == pytest.approx(1.3)  # followed Exam 2


def test_later_exams_follow_the_previous_exam_and_say_so() -> None:
    _three_exams()
    state.kerma_meter_in_memory_table = {("Exam 1", "room-1", "A"): 1.4}
    model = dlg.FactorModel(state)
    row2, row3 = _row(model, "Exam 2"), _row(model, "Exam 3")
    assert (row2.value, row2.source, row2.follows) == (1.4, dlg.SOURCE_FOLLOWS, "Exam 1")
    assert (row3.value, row3.source, row3.follows) == (1.4, dlg.SOURCE_FOLLOWS, "Exam 2")


def test_default_rows_do_not_pretend_to_follow() -> None:
    _three_exams()
    model = dlg.FactorModel(state)
    assert [r.source for r in model.rows()] == [dlg.SOURCE_DEFAULT] * 3


def test_editing_exam_one_updates_followers_but_not_edited_exams() -> None:
    _three_exams()
    state.kerma_meter_in_memory_table = {("Exam 1", "room-1", "A"): 1.4}
    model = dlg.FactorModel(state)
    model.set_value("Exam 2", ("room-1", "A"), 1.9)  # the user edits Exam 2
    model.set_value("Exam 1", ("room-1", "A"), 1.5)
    assert _row(model, "Exam 2").value == pytest.approx(1.9)
    assert _row(model, "Exam 2").source == dlg.SOURCE_ENTERED
    assert _row(model, "Exam 3").value == pytest.approx(1.9)  # Exam 3 follows Exam 2, not Exam 1
    model.set_value("Exam 3", ("room-1", "A"), 1.6)
    model.set_value("Exam 2", ("room-1", "A"), 2.0)
    assert _row(model, "Exam 3").value == pytest.approx(1.6)


def test_period_selector_defaults_to_most_recent_then_follows_previous_exam(tmp_path: Path) -> None:
    _three_exams()
    state.kerma_meter_file = str(_dated_file(tmp_path))
    model = dlg.FactorModel(state)
    assert [model.period_of(e) for e in model.exams] == [_NEW, _NEW, _NEW]
    assert model.period_follows("Exam 1") is None
    assert model.period_follows("Exam 2") == "Exam 1"
    assert [r.value for r in model.rows()] == [pytest.approx(1.25)] * 3


def test_choosing_an_older_period_changes_that_exams_file_factor(tmp_path: Path) -> None:
    _three_exams()
    state.kerma_meter_file = str(_dated_file(tmp_path))
    model = dlg.FactorModel(state)
    model.set_period("Exam 2", _OLD)
    values = [r.value for r in model.rows()]
    assert values == [pytest.approx(1.25), pytest.approx(1.10), pytest.approx(1.10)]  # Exam 3 follows Exam 2
    assert model.period_of("Exam 3") == _OLD  # Exam 3 follows Exam 2's period
    assert _row(model, "Exam 2").source == dlg.SOURCE_FILE
    model.commit(dont_ask=False)
    assert state.kerma_meter_periods == {"Exam 1": _NEW, "Exam 2": _OLD, "Exam 3": _OLD}
    assert state.kerma_meter_in_memory_table is None  # file values are not copied into manual entries


def test_period_choice_selects_the_file_row_in_the_missing_check(tmp_path: Path) -> None:
    _two_exams()
    state.loaded_exams = [SimpleNamespace(normalized_data=_frame(["Room-1"], ["Plane A"])) for _ in range(2)]
    state.kerma_meter_file = str(_dated_file(tmp_path))
    assert dlg.missing_pairs(state) == []
    state.kerma_meter_periods = {"Exam 1": "2025-01-01|2025-12-31"}  # a period with no row for the pair
    assert dlg.missing_by_exam(state) == {"Exam 1": [("room-1", "A")]}


def test_missing_is_checked_per_exam() -> None:
    _three_exams()
    state.kerma_meter_in_memory_table = {("Exam 1", "room-1", "A"): 1.0}
    assert dlg.missing_by_exam(state) == {"Exam 2": [("room-1", "A")], "Exam 3": [("room-1", "A")]}
    assert dlg.needs_prompt(state) is True


def test_drift_clears_per_exam_state_but_keeps_legacy_global_entries() -> None:
    from guiskindose.gui.exam_transforms import rebuild_rdsr_df

    a = SimpleNamespace(normalized_data=_frame(["Room-1"], ["Plane A"]))
    b = SimpleNamespace(normalized_data=_frame(["Room-1"], ["Plane B"]))
    state.loaded_exams = [a, b]
    rebuild_rdsr_df(state)
    state.kerma_meter_periods = {"Exam 2": _OLD}
    state.kerma_meter_in_memory_table = {("room-1", "A"): 1.0, ("Exam 2", "room-1", "B"): 1.2}
    state.loaded_exams = [b, a]  # reorder
    rebuild_rdsr_df(state)
    assert state.kerma_meter_periods == {}
    assert state.kerma_meter_in_memory_table == {("room-1", "A"): 1.0}


@pytest.mark.asyncio
async def test_rendered_dialog_shows_follows_and_period_selector(user: User, tmp_path: Path) -> None:
    await user.open("/")
    _two_exams()
    state.loaded_exams = [SimpleNamespace(normalized_data=_frame(["Room-1"], ["Plane A"])) for _ in range(2)]
    state.kerma_meter_file = str(_dated_file(tmp_path))
    state.kerma_meter_in_memory_table = {("Exam 1", "room-1", "A"): 1.4}
    task = asyncio.create_task(_run_in_client(user))
    await user.should_see("Calibration period", retries=30)
    await user.should_see("↳ follows Exam 1", retries=30)
    user.find("Confirm").click()
    await asyncio.wait_for(task, timeout=5)
    table = state.kerma_meter_in_memory_table
    assert table is not None
    assert table[("Exam 2", "room-1", "A")] == pytest.approx(1.4)


@pytest.mark.asyncio
async def test_example_calibration_browser_branch_downloads(monkeypatch: pytest.MonkeyPatch) -> None:
    from guiskindose import get_path_to_example_kerma_meter_file
    from guiskindose.gui import io_helpers
    from guiskindose.gui.tabs import corrections as settings_tab
    from guiskindose.gui.tabs import export as export_tab

    async def _no_native(default_name: str, extension: str) -> None:
        return None

    calls: list[tuple[bytes, str]] = []
    monkeypatch.setattr(io_helpers, "_get_save_path", _no_native)
    monkeypatch.setattr(export_tab.ui, "download", lambda content, name: calls.append((content, name)))
    await settings_tab._download_example_calibration_file()
    assert calls == [(get_path_to_example_kerma_meter_file().read_bytes(), "calibration_factors_example.csv")]


@pytest.mark.asyncio
async def test_example_calibration_native_branch_saves_to_the_chosen_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from guiskindose import get_path_to_example_kerma_meter_file
    from guiskindose.gui import io_helpers
    from guiskindose.gui.tabs import corrections as settings_tab
    from guiskindose.gui.tabs import export as export_tab

    target = tmp_path / "chosen.csv"
    asked: list[tuple[str, str]] = []

    async def _native_save(default_name: str, extension: str) -> str:
        asked.append((default_name, extension))
        return str(target)

    downloads: list[object] = []
    monkeypatch.setattr(io_helpers, "_get_save_path", _native_save)
    monkeypatch.setattr(export_tab.ui, "download", lambda *args: downloads.append(args))
    monkeypatch.setattr(export_tab.ui, "notify", lambda *args, **kwargs: None)
    await settings_tab._download_example_calibration_file()
    assert asked == [("calibration_factors_example.csv", "csv")]
    assert target.read_bytes() == get_path_to_example_kerma_meter_file().read_bytes()
    assert downloads == []  # native save, no browser download


# ── review findings: stale results, unchosen periods, editable unit override ─


def test_commit_reports_whether_anything_changed() -> None:
    _single_exam()
    model = dlg.FactorModel(state)
    assert model.commit(dont_ask=False) is True  # first confirm stores the defaults
    assert dlg.FactorModel(state).commit(dont_ask=False) is False  # nothing differs the second time
    changed = dlg.FactorModel(state)
    changed.set_value("Exam 1", ("room-1", "A"), 1.7)
    assert changed.commit(dont_ask=False) is True


def _calculated_state() -> None:
    state.calculation_done = True
    state.psd = 12.0
    state.air_kerma = 3.0
    state.output = {"psd": 12.0}


@pytest.mark.asyncio
async def test_confirm_with_edits_invalidates_results(user: User) -> None:
    from nicegui import ui

    await user.open("/")
    _single_exam()
    state.kerma_meter_in_memory_table = {("Exam 1", "room-1", "A"): 1.0, ("Exam 1", "room-1", "B"): 1.0}
    _calculated_state()
    task = asyncio.create_task(_run_in_client(user))
    await user.should_see("Kerma-meter correction factors", retries=30)
    assert user.client is not None
    field = next(
        el
        for el in user.client.elements.values()
        if isinstance(el, ui.number) and el._props.get("label") == "room-1 / A"
    )
    field.set_value(1.5)
    user.find("Confirm").click()
    await _wait_for_task(task, user)
    assert state.calculation_done is False
    assert state.output is None


@pytest.mark.asyncio
async def test_unchanged_confirm_keeps_results(user: User) -> None:
    await user.open("/")
    _single_exam()
    state.kerma_meter_in_memory_table = {("Exam 1", "room-1", "A"): 1.0, ("Exam 1", "room-1", "B"): 1.0}
    _calculated_state()
    task = asyncio.create_task(_run_in_client(user))
    await user.should_see("Kerma-meter correction factors", retries=30)
    user.find("Confirm").click()
    await _wait_for_task(task, user)
    assert state.calculation_done is True
    assert state.output == {"psd": 12.0}


@pytest.mark.asyncio
async def test_dated_full_hit_prompts_once_until_a_period_is_chosen(dialog_mock: AsyncMock, tmp_path: Path) -> None:
    _single_exam(stations=("Room-1",), planes=("Plane A",))
    state.kerma_meter_file = str(_dated_file(tmp_path))  # every pair is covered by the file
    assert dlg.missing_pairs(state) == []
    assert dlg.needs_prompt(state) is True
    assert await dlg.maybe_prompt_after_load() is True
    assert await dlg.maybe_prompt_after_load() is False  # once per load
    dlg.FactorModel(state).commit(dont_ask=False)  # confirming records the period
    assert state.kerma_meter_periods == {"Exam 1": _NEW}
    assert dlg.needs_prompt(state) is False


def test_undated_file_full_hit_does_not_prompt(tmp_path: Path) -> None:
    _single_exam()
    state.kerma_meter_file = str(_cf_file(tmp_path))
    assert dlg.needs_prompt(state) is False


def test_unit_override_can_be_changed_and_cleared_after_it_resolves_the_exam(tmp_path: Path) -> None:
    _two_exams()
    state.kerma_meter_file = str(_cf_file(tmp_path, "room-1,A,1.1\nroom-9,single,1.7\nroom-8,single,1.2\n"))
    state.kerma_meter_unresolved_labels = {"Exam 2": "Room-9"}
    model = dlg.FactorModel(state)
    assert model.unresolved_exams() == ["Exam 2"]  # still offered although the override resolves it
    assert [(r.equipment, r.value) for r in model.rows() if r.exam == "Exam 2"] == [("room-9", 1.7)]
    model.set_labels({"Exam 2": "Room-8"})  # change
    assert [(r.equipment, r.value) for r in model.rows() if r.exam == "Exam 2"] == [("room-8", 1.2)]
    model.set_labels({"Exam 2": ""})  # clear
    assert [r.equipment for r in model.rows() if r.exam == "Exam 2"] == ["unresolved"]
    model.commit(dont_ask=False)
    assert state.kerma_meter_unresolved_labels == {}


@pytest.mark.asyncio
async def test_rendered_dialog_keeps_the_unit_chooser_for_a_resolved_exam(user: User) -> None:
    await user.open("/")
    _two_exams()
    state.kerma_meter_unresolved_labels = {"Exam 2": "Room-9"}
    task = asyncio.create_task(_run_in_client(user))
    await user.should_see("No equipment identity was found", retries=30)
    user.find("Confirm").click()
    await _wait_for_task(task, user)
