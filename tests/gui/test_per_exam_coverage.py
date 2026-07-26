"""Coverage for Settings per-exam correction helpers."""

from __future__ import annotations

from typing import cast
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

pytest.importorskip("nicegui")

from nicegui import ui  # noqa: E402

from mypyskindose.gui.page_context import PageContext  # noqa: E402
from mypyskindose.gui.state import state  # noqa: E402
from mypyskindose.gui.tabs import _per_exam as pe  # noqa: E402


def _ctx() -> PageContext:
    return PageContext(
        tabs=MagicMock(),
        file_label=MagicMock(),
        events_label=MagicMock(),
        psd_label=MagicMock(),
        run_btn_drawer=MagicMock(),
        refresh_per_exam=MagicMock(),
        refresh_geometry_preview=MagicMock(),
        refresh_phantom_preview=MagicMock(),
        refresh_event_table=MagicMock(),
        refresh_import_preview=MagicMock(),
        refresh_geometry_tab=MagicMock(),
    )


@pytest.fixture(autouse=True)
def _stub_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ui, "notify", lambda *a, **k: None)


def test_invalidate_resets_psd_label() -> None:
    ctx = _ctx()
    state.calculation_done = True
    state.psd = 12.0
    pe._invalidate(ctx)
    assert state.calculation_done is False
    cast(MagicMock, ctx.psd_label.set_text).assert_called_with("PSD: 0.00 mGy")


def test_apply_global_offset_to_all_exams() -> None:
    ctx = _ctx()
    state.d_lon, state.d_ver, state.d_lat = 1.0, 2.0, 3.0
    state.loaded_exam_meta = [
        {"d_lon": 0.0, "d_ver": 0.0, "d_lat": 0.0},
        {"d_lon": 9.0, "d_ver": 9.0, "d_lat": 9.0},
    ]
    pe._apply_global_offset_to_all(ctx)
    assert all(m["d_lon"] == 1.0 and m["d_ver"] == 2.0 and m["d_lat"] == 3.0 for m in state.loaded_exam_meta)
    cast(MagicMock, ctx.refresh_per_exam).assert_called()


def test_on_exam_offset_change_refreshes_previews() -> None:
    ctx = _ctx()
    pe._on_exam_offset_change(ctx)
    cast(MagicMock, ctx.refresh_per_exam).assert_called()
    cast(MagicMock, ctx.refresh_geometry_preview).assert_called()
    cast(MagicMock, ctx.refresh_phantom_preview).assert_called()


def test_on_exam_transform_change_applies_and_refreshes(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx()
    state.loaded_exam_meta = [{"swap_lat_lon": False, "flip_ap1": False, "flip_ap2": False}]
    applied: list[int] = []
    monkeypatch.setattr(pe, "apply_exam_transforms", lambda st, idx: applied.append(idx))

    pe._on_exam_transform_change(ctx, 0, "swap_lat_lon", True)

    assert state.loaded_exam_meta[0]["swap_lat_lon"] is True
    assert applied == [0]
    cast(MagicMock, ctx.refresh_event_table).assert_called()
    cast(MagicMock, ctx.refresh_import_preview).assert_called()
    cast(MagicMock, ctx.refresh_geometry_tab).assert_called()


def test_on_exam_transform_change_ignores_bad_index() -> None:
    ctx = _ctx()
    state.loaded_exam_meta = [{"swap_lat_lon": False}]
    pe._on_exam_transform_change(ctx, 5, "swap_lat_lon", True)
    assert state.loaded_exam_meta[0]["swap_lat_lon"] is False
    cast(MagicMock, ctx.refresh_event_table).assert_not_called()


def test_refresh_per_exam_empty_and_populated(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx()
    empty_hint = MagicMock()
    exams_list = MagicMock()
    state.loaded_exams = []
    state.loaded_exam_meta = []

    pe._refresh_per_exam(ctx, empty_hint, exams_list)

    empty_hint.set_visibility.assert_called_with(True)
    exams_list.clear.assert_called()

    state.loaded_exams = [SimpleNamespace()]
    state.loaded_exam_meta = [{"file_name": "a.dcm"}]
    built: list[int] = []
    monkeypatch.setattr(pe, "_build_exam_card", lambda c, i, e, m: built.append(i))
    pe._refresh_per_exam(ctx, empty_hint, exams_list)

    empty_hint.set_visibility.assert_called_with(False)
    assert built == [0]
