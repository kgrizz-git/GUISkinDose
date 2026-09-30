"""Call-site coverage for peak-skin-dose severity banding.

Every banded PSD readout in the GUI routes through ``gui.dose_severity``, so
this file pins the six call sites from the plan's §3.3 — sidebar build, sidebar
success path, Results single-exam metric, Results aggregate metric (four
refresh sites), and the per-exam accordion — plus the four ``reset_psd_label``
paths. A future edit cannot quietly reintroduce a site-specific PSD colour or a
hard-coded ``0.00 mGy`` placeholder.

Two flavours of test, on purpose:

* Mock-ref tests cover the refresh logic (what band does this site choose).
* ``user``-fixture tests cover real NiceGUI elements, because only those can
  show that a repeated band change re-texts the one tooltip rather than stacking
  another, and that the pending band hides its icon instead of leaving an empty
  glyph box on screen.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import numpy as np
import pytest
from nicegui import ui
from nicegui.elements.row import Row
from nicegui.elements.tooltip import Tooltip
from nicegui.testing import User

from guiskindose.gui.dose_severity import (
    _ALL_TEXT_CLASSES,
    PSD_PENDING_TEXT,
    PsdReadout,
    apply_psd_presentation,
    build_psd_readout,
)
from guiskindose.gui.page_context import PageContext
from guiskindose.gui.state import state
from guiskindose.gui.tabs import _per_exam as pe
from guiskindose.gui.tabs import calculate as calc_tab
from guiskindose.gui.tabs import results_builders as rb
from guiskindose.gui.tabs import upload_builders as ub

pytest.importorskip("nicegui")

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")

_PENDING_TOOLTIP = "Not calculated yet"


def _mock_readout() -> PsdReadout:
    """A banded PSD readout built from mocks: row / icon / value / tooltip."""
    return PsdReadout(row=MagicMock(), icon=MagicMock(), value=MagicMock(), tooltip=MagicMock())


def _mock_exam(exam_id: str, psd: float, dose_pairs: list[tuple[int, float]], num_cells: int = 3) -> Any:
    patient = {"patient": {"patient_skin_cells": {"x": [0.0] * num_cells, "y": [0.0] * num_cells, "z": [0.0] * num_cells}}}
    return SimpleNamespace(
        exam_id=exam_id,
        event_count=3,
        output=SimpleNamespace(
            psd=psd,
            air_kerma=psd * 2,
            to_dict=MagicMock(return_value={"dose_map": dose_pairs, "patient": patient}),
        ),
    )


def _multi_result(exams: list[Any], aggregate_psd: float) -> Any:
    return SimpleNamespace(
        aggregate_psd=aggregate_psd,
        aggregate_dose_map=np.zeros(3),
        exams=exams,
        warnings=[],
        exams_attempted=len(exams),
        exams_excluded=0,
    )


def _ctx() -> PageContext:
    return PageContext(
        tabs=MagicMock(),
        file_label=MagicMock(),
        events_label=MagicMock(),
        psd_readout=MagicMock(),
        run_btn_drawer=MagicMock(),
        clear_offset_stale_caption=MagicMock(),
    )


def _results_ctrl() -> rb.ResultsTabController:
    ctrl = rb.ResultsTabController()
    ctrl.refs.psd_readout = _mock_readout()
    ctrl.refs.agg_psd_readout = _mock_readout()
    ctrl.refs.agg_events_metric = MagicMock()
    ctrl.refs.agg_totals_metric = MagicMock()
    ctrl.refs.agg_dosemap_plot = MagicMock()
    ctrl.refs.agg_dosemap_spinner = MagicMock(visible=False)
    ctrl.refs.run_warnings_label = MagicMock()
    ctrl.refs.rotational_badge = MagicMock(visible=False)
    ctrl.refs.agg_rotational_badge = MagicMock(visible=False)
    return ctrl


def _band_classes(readout: PsdReadout) -> set[str]:
    """Every severity class currently on the readout, value and icon together."""
    added = [
        call.kwargs.get("add")
        for element in (readout.value, readout.icon)
        for call in cast(MagicMock, element.classes).call_args_list
    ]
    return {name for add in added if add for name in add.split() if name.startswith("text-dose-")}


def _band_row_of(element: ui.element) -> Row | None:
    """The banded row wrapping ``element``, or None if it is not inside one.

    Needed because a Results metric card also holds plain metric labels whose
    parent happens to be a column, not one of these rows.
    """
    slot = element.parent_slot
    if slot is None:
        return None
    parent = slot.parent
    if not isinstance(parent, Row):
        return None
    icons = [c for c in parent.default_slot.children if isinstance(c, ui.icon)]
    tooltips = [c for c in parent.default_slot.children if isinstance(c, Tooltip)]
    return parent if len(icons) == 1 and len(tooltips) == 1 else None


def _row_of(element: ui.element) -> Row:
    """The banded row wrapping ``element`` (the tooltip's target)."""
    row = _band_row_of(element)
    assert row is not None, f"{element!r} is not inside a banded PSD row"
    return row


def _row_children(row: Row) -> tuple[ui.icon, ui.label, Tooltip]:
    icons = [c for c in row.default_slot.children if isinstance(c, ui.icon)]
    labels = [c for c in row.default_slot.children if isinstance(c, ui.label)]
    tooltips = [c for c in row.default_slot.children if isinstance(c, Tooltip)]
    assert len(icons) == 1, f"expected one band icon, got {icons}"
    assert len(labels) == 1, f"expected one value label, got {labels}"
    assert len(tooltips) == 1, f"expected one band tooltip, got {tooltips}"
    return icons[0], labels[0], tooltips[0]


# ── call site 1: sidebar construction ────────────────────────────────────────


@pytest.mark.asyncio
async def test_sidebar_starts_pending_in_grey_with_no_zero(user: User) -> None:
    """Before any run the drawer must read `PSD: —`, never a literal `0.00 mGy`."""
    await user.open("/")
    await user.should_see(PSD_PENDING_TEXT)
    await user.should_not_see("PSD: 0.00 mGy")

    label = next(el for el in user.find(PSD_PENDING_TEXT).elements if isinstance(el, ui.label))
    assert "text-dose-pending" in set(label.classes)
    assert not any(name.startswith("text-dose-") and name != "text-dose-pending" for name in label.classes)

    icon, _, tooltip = _row_children(_row_of(label))
    assert icon.name == ""
    assert icon.visible is False
    assert tooltip.text == _PENDING_TOOLTIP


@pytest.mark.asyncio
async def test_sidebar_readout_carries_icon_and_tooltip_from_the_start(user: User) -> None:
    """Colour is never the only carrier, so the pending sidebar needs them too."""
    await user.open("/")

    label = next(
        el
        for el in user.find(PSD_PENDING_TEXT).elements
        if isinstance(el, ui.label) and "text-h6" in set(el.classes)
    )
    row = _row_of(label)
    assert "items-center" in set(row.classes)


# ── call sites 3-6: the refresh paths, one per band decision ────────────────


def _calc_ctrl(readout: PsdReadout) -> calc_tab._CalculationController:
    ctrl = calc_tab._CalculationController(_ctx())
    ctrl.ctx.psd_readout = readout
    ctrl.controls = calc_tab._CalculationControls(MagicMock(), MagicMock(visible=False), MagicMock())
    return ctrl


def test_calculate_success_path_bands_the_sidebar_on_psd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Call site 3: the sidebar is a whole-run status readout, banded on state.psd."""
    monkeypatch.setattr(ui, "notify", lambda *a, **k: None)
    readout = _mock_readout()
    ctrl = _calc_ctrl(readout)
    state.psd = 12_345.0

    ctrl._show_success("calculation complete")

    cast(MagicMock, readout.value.set_text).assert_called_with("PSD: 12345.00 mGy")
    assert _band_classes(readout) == {"text-dose-high"}
    cast(MagicMock, readout.icon.set_name).assert_called_with("error")
    cast(MagicMock, readout.icon.set_visibility).assert_called_with(True)
    cast(MagicMock, readout.tooltip.set_text).assert_called_with("High — peak skin dose 10000 mGy or above")


def test_results_single_exam_metric_bands_on_psd() -> None:
    """Call site 4: the Results single-exam metric bands on the single-exam PSD."""
    ctrl = _results_ctrl()
    psd_readout = cast(PsdReadout, ctrl.refs.psd_readout)
    state.is_multi_exam = False
    state.calculation_done = True
    state.psd = 5_000.0
    state.air_kerma = 0.0
    state.rdsr_df = MagicMock(__len__=lambda s: 1)
    ctrl.refs.kerma_metric = MagicMock()
    ctrl.refs.events_metric = MagicMock()
    ctrl.refs.dap_metric = MagicMock()
    ctrl.refs.fluoro_metric = MagicMock()

    ctrl.refresh_metrics()

    # Exactly 5000 is Elevated, and the tooltip has to say so at that edge.
    cast(MagicMock, psd_readout.value.set_text).assert_called_with("5000.00 mGy")
    assert _band_classes(psd_readout) == {"text-dose-elevated"}
    cast(MagicMock, psd_readout.tooltip.set_text).assert_called_with(
        "Elevated — peak skin dose 5000 to just under 10000 mGy"
    )


def test_results_aggregate_metric_bands_on_aggregate_psd() -> None:
    """Call site 5a: `_set_multi_exam_summary` bands on the whole-run aggregate."""
    ctrl = _results_ctrl()
    agg_readout = cast(PsdReadout, ctrl.refs.agg_psd_readout)
    res = _multi_result([_mock_exam("A", 10.0, [(0, 5.0)])], aggregate_psd=10_000.0)

    ctrl._set_multi_exam_summary(res)

    cast(MagicMock, agg_readout.value.set_text).assert_called_with("10000.00 mGy")
    assert _band_classes(agg_readout) == {"text-dose-high"}
    cast(MagicMock, agg_readout.icon.set_name).assert_called_with("error")


def test_aggregate_all_exams_selected_bands_on_aggregate_psd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Call site 5b: every exam selected shows the run aggregate again."""
    ctrl = _results_ctrl()
    agg_readout = cast(PsdReadout, ctrl.refs.agg_psd_readout)
    res = _multi_result([_mock_exam("A", 10.0, [(0, 5.0)])], aggregate_psd=1_200.0)
    state.multi_exam_result = res
    state.aggregate_subset_exams = [True]
    state.calc_run_id = 1
    monkeypatch.setattr(rb, "make_dosemap_fig", lambda *a, **k: {"data": [], "layout": {}})
    monkeypatch.setattr(ctrl, "refresh_aggregate_dosemap", lambda _res: None)

    ctrl.refresh_aggregate_dosemap_subset()

    cast(MagicMock, agg_readout.value.set_text).assert_called_with("1200.00 mGy")
    assert _band_classes(agg_readout) == {"text-dose-low"}


def test_aggregate_no_exams_selected_bands_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    """Call site 5c: an empty subset has no peak to band, so it goes grey."""
    ctrl = _results_ctrl()
    agg_readout = cast(PsdReadout, ctrl.refs.agg_psd_readout)
    res = _multi_result([_mock_exam("A", 99_000.0, [(0, 5.0)])], aggregate_psd=99_000.0)
    state.multi_exam_result = res
    state.aggregate_subset_exams = [False]
    state.calc_run_id = 1
    monkeypatch.setattr(rb, "make_dosemap_fig", lambda *a, **k: {"data": [], "layout": {}})

    ctrl.refresh_aggregate_dosemap_subset()

    cast(MagicMock, agg_readout.value.set_text).assert_called_with("— mGy (no exams selected)")
    assert _band_classes(agg_readout) == {"text-dose-pending"}
    cast(MagicMock, agg_readout.icon.set_name).assert_called_with("")
    cast(MagicMock, agg_readout.icon.set_visibility).assert_called_with(False)
    cast(MagicMock, agg_readout.tooltip.set_text).assert_called_with(_PENDING_TOOLTIP)


def test_aggregate_subset_bands_on_subset_psd_not_the_aggregate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Call site 5d: a deselected subset bands on its OWN maximum.

    The whole-run aggregate here is 99 000 mGy (red); the selected subset peaks
    at 1 234 mGy (green). Banding on the aggregate would show a red number next
    to a green-ish subset figure, so this is the easy thing to get wrong.
    """
    ctrl = _results_ctrl()
    agg_readout = cast(PsdReadout, ctrl.refs.agg_psd_readout)
    exam0 = _mock_exam("A", 1_234.0, [(0, 1_234.0)])
    exam1 = _mock_exam("B", 99_000.0, [(1, 99_000.0)])
    res = _multi_result([exam0, exam1], aggregate_psd=99_000.0)
    state.multi_exam_result = res
    state.aggregate_subset_exams = [True, False]
    state.calc_run_id = 1
    monkeypatch.setattr(rb, "make_dosemap_fig", lambda *a, **k: {"data": [], "layout": {}})

    ctrl.refresh_aggregate_dosemap_subset()

    cast(MagicMock, agg_readout.value.set_text).assert_called_with("1234.00 mGy (subset)")
    assert _band_classes(agg_readout) == {"text-dose-low"}


def test_aggregate_subset_of_zero_bands_low_green_deliberately(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty-but-not-None combined map yields subset_psd == 0.0 → LOW, not pending.

    ``compute_subset_aggregate`` returns ``(None, 0.0)`` for nothing selected and
    ``(array, 0.0)`` when a subset is selected but every cell is zero. The
    second case bands green, because ``psd_band(0.0)`` is "low" — zero really is
    below 5000 mGy. Asserted on purpose so a later reader does not "fix" it into
    pending grey.
    """
    ctrl = _results_ctrl()
    agg_readout = cast(PsdReadout, ctrl.refs.agg_psd_readout)
    exam0 = _mock_exam("A", 0.0, [(0, 0.0)])
    exam1 = _mock_exam("B", 0.0, [(1, 0.0)])
    res = _multi_result([exam0, exam1], aggregate_psd=0.0)
    state.multi_exam_result = res
    state.aggregate_subset_exams = [True, False]
    state.calc_run_id = 1
    monkeypatch.setattr(rb, "make_dosemap_fig", lambda *a, **k: {"data": [], "layout": {}})

    ctrl.refresh_aggregate_dosemap_subset()

    cast(MagicMock, agg_readout.value.set_text).assert_called_with("0.00 mGy (subset)")
    assert _band_classes(agg_readout) == {"text-dose-low"}
    cast(MagicMock, agg_readout.icon.set_name).assert_called_with("check_circle")
    cast(MagicMock, agg_readout.tooltip.set_text).assert_called_with(
        "Low — peak skin dose below 5000 mGy"
    )


@pytest.mark.asyncio
async def test_per_exam_accordion_bands_each_exam_independently(user: User) -> None:
    """Call site 6: the accordion is the only place several bands show at once."""
    await user.open("/")
    assert user.client is not None
    ctrl = rb.ResultsTabController()
    exams = [
        _mock_exam("Low exam", 12.0, [(0, 12.0)]),
        _mock_exam("Elevated exam", 7_000.0, [(1, 7_000.0)]),
        _mock_exam("High exam", 25_000.0, [(2, 25_000.0)]),
    ]
    with user.client:
        container = ui.column()
    ctrl.refs.multi_exam_accordion_container = container

    ctrl._build_multi_exam_accordion(_multi_result(exams, aggregate_psd=25_000.0))

    found: dict[str, set[str]] = {}
    with user.client:
        for child in container.default_slot.children:
            for element in _descendants(child):
                if not isinstance(element, ui.label) or _band_row_of(element) is None:
                    continue
                _, _, tooltip = _row_children(_row_of(element))
                found[element.text] = set(element.classes) & set(_ALL_TEXT_CLASSES.split())
                assert tooltip.text != _PENDING_TOOLTIP, "a calculated exam must not read as pending"

    assert found == {
        "12.00 mGy": {"text-dose-low"},
        "7000.00 mGy": {"text-dose-elevated"},
        "25000.00 mGy": {"text-dose-high"},
    }


def _descendants(element: ui.element) -> list[ui.element]:
    """Every element under ``element``, depth first."""
    found: list[ui.element] = []
    for slot in element.slots.values():
        for child in slot.children:
            found.append(child)
            found.extend(_descendants(child))
    return found


# ── the four reset paths ─────────────────────────────────────────────────────


def _assert_pending(readout: PsdReadout) -> None:
    cast(MagicMock, readout.value.set_text).assert_called_with(PSD_PENDING_TEXT)
    assert cast(MagicMock, readout.value.classes).call_args.kwargs["add"] == "text-dose-pending"
    cast(MagicMock, readout.icon.set_visibility).assert_called_with(False)
    cast(MagicMock, readout.tooltip.set_text).assert_called_with(_PENDING_TOOLTIP)


def test_calculate_failure_resets_the_sidebar_to_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset path 1: a failed run must not leave the previous run's band on screen."""
    monkeypatch.setattr(ui, "notify", lambda *a, **k: None)
    readout = _mock_readout()
    ctrl = _calc_ctrl(readout)
    state.calculation_done = True
    state.psd = 12_000.0

    ctrl._finish_calculation(False, "synthetic failure")

    _assert_pending(readout)


def test_clear_all_exams_resets_the_sidebar_to_pending() -> None:
    """Reset path 2: clearing every loaded exam invalidates the result."""
    ctx = _ctx()
    tab = ub.UploadTabController(ctx)
    state.loaded_exams = []
    state.loaded_exam_meta = []
    tab.refs.import_preview = MagicMock()
    tab.refs.upload_status = MagicMock()
    tab.refs.example_select = MagicMock()
    tab.refs.event_table = MagicMock()
    tab.refresh_exams_table = MagicMock()
    tab.refs.import_preview.refresh = MagicMock()
    tab._build_uploader = MagicMock()

    tab.clear_all_exams()

    _assert_pending(ctx.psd_readout)


def test_remove_exam_resets_the_sidebar_to_pending() -> None:
    """Reset path 3: removing the last exam leaves no result behind."""
    ctx = _ctx()
    tab = ub.UploadTabController(ctx)
    state.loaded_exams = ["a"]
    state.loaded_exam_meta = [{"file_path": "ignored", "file_name": "ignored"}]
    state.rdsr_df = None
    tab.refs.event_table = MagicMock()
    tab.refresh_exams_table = MagicMock()
    tab.refs.import_preview = MagicMock()

    tab.remove_exam(0)

    _assert_pending(ctx.psd_readout)


def test_per_exam_invalidate_resets_the_sidebar_to_pending() -> None:
    """Reset path 4: a per-exam correction edit invalidates the result too."""
    ctx = _ctx()
    state.calculation_done = True
    state.psd = 12_000.0

    pe._invalidate(ctx)

    _assert_pending(ctx.psd_readout)


# ── the presentation helper on real elements ─────────────────────────────────


@pytest.mark.asyncio
async def test_rebanding_retexts_one_tooltip_instead_of_stacking(user: User) -> None:
    """nicegui's ``Element.tooltip()`` appends a new q-tooltip on every call.

    Re-attaching a tooltip per band change would therefore stack one tooltip per
    change and leave stale band names on screen. The readout holds its tooltip
    and re-texts it, so the row keeps exactly one no matter how often it re-bands.
    """
    await user.open("/")
    assert user.client is not None
    with user.client:
        readout = build_psd_readout("—", label_classes="text-4xl font-bold")

    row = readout.row
    expected = {
        0.0: "Low — peak skin dose below 5000 mGy",
        7_000.0: "Elevated — peak skin dose 5000 to just under 10000 mGy",
        25_000.0: "High — peak skin dose 10000 mGy or above",
        None: _PENDING_TOOLTIP,
    }
    for psd, text in expected.items():
        apply_psd_presentation(readout, psd)
        _, _, tooltip = _row_children(row)
        assert tooltip.text == text, f"tooltip not re-texted for {psd}"

    tooltips = [c for c in row.default_slot.children if isinstance(c, Tooltip)]
    assert len(tooltips) == 1
    assert tooltips[0].text == _PENDING_TOOLTIP
    assert tooltips[0].props["target"] == f"#{row.html_id}"


@pytest.mark.asyncio
async def test_pending_hides_the_icon_rather_than_leaving_an_empty_glyph(user: User) -> None:
    """``ui.icon("")`` renders an empty glyph box, so pending must hide the icon."""
    await user.open("/")
    assert user.client is not None
    with user.client:
        readout = build_psd_readout("—", label_classes="text-4xl font-bold")

    assert readout.icon.visible is False
    assert readout.icon.name == ""

    apply_psd_presentation(readout, 25_000.0)
    assert readout.icon.visible is True
    assert readout.icon.name == "error"

    apply_psd_presentation(readout, None)
    assert readout.icon.visible is False
    assert readout.icon.name == ""


@pytest.mark.asyncio
async def test_rebanding_leaves_exactly_one_severity_class(user: User) -> None:
    await user.open("/")
    assert user.client is not None
    with user.client:
        readout = build_psd_readout("—", label_classes="text-4xl font-bold")

    for psd in (0.0, 7_000.0, 25_000.0, 0.0):
        apply_psd_presentation(readout, psd)
        for element in (readout.value, readout.icon):
            severity = set(element.classes) & set(_ALL_TEXT_CLASSES.split())
            assert len(severity) == 1, f"{severity} left on {element}"
