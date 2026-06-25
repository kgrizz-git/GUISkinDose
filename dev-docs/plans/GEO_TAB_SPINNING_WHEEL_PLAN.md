# Geometry Tab Spinning Wheel Fix Plan

> **Background:** [assessments/GEO_TAB_SPINNING_WHEEL_20260625.md](../assessments/GEO_TAB_SPINNING_WHEEL_20260625.md)
> — root cause, why deleting lines 592–594 regresses seven external callers, and
> the §10.1 `_in_render_chain` recommendation this plan implements.

## Objective

Stop the Geometry tab Plotly plot from re-rendering on a 0.25 s timer loop after
slider drags, exam-selection changes, or external `ctx.refresh_per_exam()` calls,
while preserving every refresh path that depends on `_refresh_geometry_sliders()`
to schedule a re-render.

## Scope

**In scope**

| Area | Change |
|------|--------|
| `geometry.py` | `_in_render_chain` flag; guard re-schedule at 592–594; remove redundant `if last_preview_mode:` block in `_on_exam_select_change`; add `.mark(...)` on patient and table-origin sliders (testability only) |
| `tests/gui/test_gui_flows.py` | Parametrized patient-slider test (lon/ver/lat) + table-origin X test; shared load helper |
| `CHANGELOG.md` | One-line Unreleased entry when shipped |

**Out of scope**

- Debounce timing (`GEOMETRY_DEBOUNCE_SEC`), `_render_in_progress` guard, large-figure render speed.
- Any other file (`figures.py`, `upload.py`, `_per_exam.py`, `offset_handlers.py`, `app.py`, …) — external `ctx.refresh_per_exam()` paths keep working because lines 592–594 remain, now guarded.

## Acceptance criteria

- [ ] Patient or table-origin slider drag: at most one render per 0.25 s burst; plot stable for mouse rotate/zoom after release.
- [ ] `make_geometry_fig` not invoked on a periodic timer — only user actions or external `ctx.refresh_per_exam()`.
- [ ] External refreshes still redraw: new file, remove exam, switch exam, per-exam correction/toggle in Settings.
- [ ] Exam-selector change still redraws after removing the redundant local schedule block.
- [ ] Settings → Phantom Settings → Body habitus scaling still refreshes Geometry (`ctx.refresh_geometry_preview()`).
- [ ] `test_geometry_patient_slider_no_render_loop` (parametrized lon/ver/lat) and
      `test_geometry_table_slider_no_render_loop` pass locally and on CI.
- [ ] `CHANGELOG.md` Unreleased entry added.

## Phase 1 — `geometry.py`

Add `_in_render_chain = False` in `build()` (line 70) alongside `slider_timer`, etc.

**`_do_debounced_render()` (387–400)** — add `_in_render_chain` to `nonlocal`. Keep
`if table_origin_pending:` **outside** the `try/finally`. Set the flag only around
the synchronous `ctx.refresh_per_exam()`; do **not** wrap `await _render_preview(...)`.
If the flag stayed `True` across the await, a concurrent `refresh_per_exam()` would
be swallowed by the guard and leave the plot stale.

```python
async def _do_debounced_render() -> None:
    nonlocal slider_timer, table_origin_pending, live_preview_requested
    nonlocal last_table_origin_scrub, _in_render_chain
    slider_timer = None
    if table_origin_pending:
        commit_table_origin_transform(state, _active_exam_index())
        table_origin_pending = False
        last_table_origin_scrub = False
        reset_results()
    _in_render_chain = True
    try:
        ctx.refresh_per_exam()
    finally:
        _in_render_chain = False
    _update_preview_caption()
    if live_preview_requested and live_preview_allowed() and last_preview_mode:
        await _render_preview(last_preview_mode)
    live_preview_requested = False
    _update_paused_badge()
```

**`_refresh_geometry_sliders()` (568–594)** — add `_in_render_chain` to `nonlocal`.
Guard the re-schedule:

```python
if last_preview_mode and not _in_render_chain:
    live_preview_requested = True
    _schedule_debounced_render()
```

**`_on_exam_select_change()` (535–553)** — remove `live_preview_requested` from
`nonlocal`; delete the entire `if last_preview_mode:` block (551–553). Wrapped
`ctx.refresh_per_exam()` already schedules via `_refresh_geometry_sliders()`.

**Patient sliders (158–177)** — add markers for the regression test:

```python
slider = ui.slider(
    min=-PATIENT_OFFSET_SLIDER_RANGE_CM,
    max=PATIENT_OFFSET_SLIDER_RANGE_CM,
    step=0.5,
    value=initial,
).classes("w-full").mark(f"patient-slider-{axis}")
```

Markers: `patient-slider-lon`, `patient-slider-ver`, `patient-slider-lat`.

## Phase 2 — Regression test

Add to `tests/gui/test_gui_flows.py` (inherits module `pytestmark`). Import
`GEOMETRY_DEBOUNCE_SEC` at the top of the test file with the other constants.

```python
from mypyskindose.gui.constants import GEOMETRY_DEBOUNCE_SEC


@pytest.mark.asyncio
async def test_geometry_slider_no_render_loop(user: User, monkeypatch) -> None:
    """One debounced render per patient-slider move; no timer loop while idle."""
    import asyncio
    import mypyskindose.gui.tabs.geometry as geometry_tab

    await user.open("/")
    user.find(marker="example-select").click()
    await user.should_see("philips_allura_clarity_u104.dcm", retries=20)
    user.find("philips_allura_clarity_u104.dcm").click()
    await user.should_see("EVENTS", retries=50)

    user.find("4 · Geometry").click()
    await user.should_see("Setup view", retries=20)

    call_count = 0
    original_make_fig = geometry_tab.make_geometry_fig

    def mock_make_fig(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original_make_fig(*args, **kwargs)

    monkeypatch.setattr(geometry_tab, "make_geometry_fig", mock_make_fig)

    user.find("Setup view").click()
    await asyncio.sleep(GEOMETRY_DEBOUNCE_SEC + 0.5)
    assert call_count == 1, f"Initial render should run once, got {call_count}"
    call_count = 0

    # trigger() runs inside user.client (see HARNESS_ENGINEERING.md User-test gotchas).
    # Requires Phase 1 markers — user.find(ui.slider) matches all six sliders.
    user.find(marker="patient-slider-lon").trigger("update:model-value", 5.0)

    await asyncio.sleep(GEOMETRY_DEBOUNCE_SEC + 0.5)
    assert call_count == 1, (
        f"Expected 1 render after slider move, got {call_count} (loop detected)"
    )

    await asyncio.sleep(1.0)
    assert call_count == 1, f"Plot re-rendered while idle, count={call_count}"
```

**Test constraints**

- Do **not** assign `slider.value` or call `slider.set_value()` — handlers run
  outside the client context and `ui.timer` / `run.io_bound` short-circuit.
- Validate with `pytest tests/gui/` locally before marking complete (not caught
  by type checkers).
- Optional follow-up: parameterized test for `patient-slider-ver` / `-lat`.

## Phase 3 — Validate and smoke

```bash
pytest tests/gui/test_gui_flows.py::test_geometry_slider_no_render_loop -v
pytest tests/gui/ -v
ruff check src/mypyskindose/gui/tabs/geometry.py tests/gui/test_gui_flows.py
basedpyright src/mypyskindose/gui/tabs/geometry.py tests/gui/test_gui_flows.py
```

Manual (`python -m mypyskindose --mode gui`): drag patient and table-origin
sliders; switch exams; toggle composite; load new example; change per-exam
toggle in Settings; change phantom scale in Settings; rotate plot 5 s without
spinning wheel returning.

**CHANGELOG** (Unreleased):

```markdown
- Fix Geometry tab plot re-rendering on a 0.25 s timer loop after slider drags,
  exam changes, or external data refresh (`_in_render_chain` closure flag).
```

## Decision log

| Date | Decision |
|------|----------|
| 2026-06-25 | Keep lines 592–594; guard with `_in_render_chain` instead of deleting (seven external `ctx.refresh_per_exam()` callers need the re-schedule). |
| 2026-06-25 | Drop `_render_in_progress` guard — sequential `ui.timer` does not break the loop. |
| 2026-06-25 | Scope `try/finally` to sync `ctx.refresh_per_exam()` only; drop flag before `await _render_preview`. |
| 2026-06-25 | Remove entire redundant `if last_preview_mode:` block in `_on_exam_select_change`. |
| 2026-06-25 | Regression test: `trigger("update:model-value", …)` + patient-slider `.mark()`; tab settle via `should_see("Setup view")`. |
| 2026-06-25 | Plan condensed; test import order fixed (`GEOMETRY_DEBOUNCE_SEC` before use). |

## Progress log

- 2026-06-25 — Plan written; reviewed against assessment and codebase (three review passes).
- (implementation not started)
