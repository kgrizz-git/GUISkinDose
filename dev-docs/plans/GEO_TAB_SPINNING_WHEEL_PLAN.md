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
| `tests/gui/test_gui_flows.py` | Parametrized patient-slider test (lon/ver/lat) + table-origin X test; shared load helpers |
| `CHANGELOG.md` | One-line Unreleased entry under `### Fixed` when shipped |

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
- [ ] `CHANGELOG.md` Unreleased entry added under `### Fixed`.
- [ ] Pre-commit: `git diff --stat` shows only `geometry.py`, `test_gui_flows.py`, and `CHANGELOG.md`.

## Phase 1 — `geometry.py`

**Step 1.** Add `_in_render_chain = False` in `build()` (line 70) alongside `slider_timer`, etc.

**Step 2.** `_do_debounced_render()` (387–400) — add `_in_render_chain` to `nonlocal`. Keep
`if table_origin_pending:` **outside** the `try/finally`. Set the flag only around the
synchronous `ctx.refresh_per_exam()`; do **not** wrap `await _render_preview(...)`.
If the flag stayed `True` across the await, a concurrent `refresh_per_exam()` would be
swallowed by the guard and leave the plot stale.

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

**Step 3.** `_refresh_geometry_sliders()` (568–594) — add `_in_render_chain` to `nonlocal`.
Guard the re-schedule:

```python
if last_preview_mode and not _in_render_chain:
    live_preview_requested = True
    _schedule_debounced_render()
```

**Step 4.** `_on_exam_select_change()` (535–553) — remove `live_preview_requested` from
`nonlocal`; delete the entire `if last_preview_mode:` block (551–553). Wrapped
`ctx.refresh_per_exam()` already schedules via `_refresh_geometry_sliders()`.

**Step 5.** Patient sliders (158–177) — add markers for the regression tests:

```python
slider = ui.slider(
    min=-PATIENT_OFFSET_SLIDER_RANGE_CM,
    max=PATIENT_OFFSET_SLIDER_RANGE_CM,
    step=0.5,
    value=initial,
).classes("w-full").mark(f"patient-slider-{axis}")
```

Markers: `patient-slider-lon`, `patient-slider-ver`, `patient-slider-lat`.

**Step 6.** Table-origin sliders (279–311) — same pattern:

```python
slider = ui.slider(
    min=lo,
    max=hi,
    step=0.5,
    value=initial,
).classes("w-full").mark(f"table-slider-{key}")
```

Markers: `table-slider-x`, `table-slider-y`, `table-slider-z`.

**Table test fixture:** `philips_allura_clarity_u104.dcm` is valid for the table-origin
test because `load_rdsr` stores `"base_data": df.copy()` (`exam_loaders.py:93`) and
`exam_supports_table_origin()` returns True when `base_data` has Tx/Ty/Tz columns
(`exam_transforms.py:137–148`). The Geometry card label is `"Table origin override (cm)"`
at `geometry.py:205` — assert substring `"Table origin override"` in Test 2 only.

## Phase 2 — Regression tests

Add to `tests/gui/test_gui_flows.py` at **module level** (below existing imports,
above test functions; inherits module `pytestmark`).

**Top-of-file imports** (single block — no inline imports in test bodies):

```python
import asyncio
from collections.abc import Callable

import mypyskindose.gui.tabs.geometry as geometry_tab
from mypyskindose.gui.constants import GEOMETRY_DEBOUNCE_SEC
```

**Constants and helpers** (module level, above tests):

```python
PHILIPS_EXAMPLE = "philips_allura_clarity_u104.dcm"


async def _load_philips_example(user: User) -> None:
    await user.open("/")
    user.find(marker="example-select").click()
    await user.should_see(PHILIPS_EXAMPLE, retries=20)
    user.find(PHILIPS_EXAMPLE).click()
    await user.should_see("EVENTS", retries=50)


async def _open_geometry_tab(user: User) -> None:
    user.find("4 · Geometry").click()
    await user.should_see("Setup view", retries=50)


def _install_make_fig_counter(monkeypatch) -> Callable[[], int]:
    """Monkeypatch make_geometry_fig; return a getter for the call count."""
    count = 0
    original = geometry_tab.make_geometry_fig

    def mock_make_fig(*args, **kwargs):
        nonlocal count
        count += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(geometry_tab, "make_geometry_fig", mock_make_fig)
    return lambda: count
```

Split load vs Geometry navigation so the patient test is not coupled to the
table-origin card. Use `retries=50` on `should_see` (same as the existing
`EVENTS` assertion) to reduce CI flake.

**Trigger value `5.0`:** within patient range `±150` (`constants.py:30`) and table
range `±250` (`constants.py:31–32`). NiceGUI's `update:model-value` handler calls
`set_value`, so `_on_patient_slider_change` / `_on_table_slider` read the updated
`slider.value`.

**Test 1 — patient sliders (parametrized):**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "slider_marker",
    ["patient-slider-lon", "patient-slider-ver", "patient-slider-lat"],
)
async def test_geometry_patient_slider_no_render_loop(
    user: User, monkeypatch, slider_marker: str,
) -> None:
    await _load_philips_example(user)
    await _open_geometry_tab(user)
    get_calls = _install_make_fig_counter(monkeypatch)
    user.find("Setup view").click()
    await asyncio.sleep(GEOMETRY_DEBOUNCE_SEC + 0.5)
    assert get_calls() == 1, f"Initial render should run once, got {get_calls()}"

    user.find(marker=slider_marker).trigger("update:model-value", 5.0)
    await asyncio.sleep(GEOMETRY_DEBOUNCE_SEC + 0.5)
    assert get_calls() == 2, f"Expected 2 total renders after {slider_marker}, got {get_calls()}"
    await asyncio.sleep(1.0)
    assert get_calls() == 2, f"Plot re-rendered while idle, count={get_calls()}"
```

Count total renders (initial + slider) instead of resetting — avoids mutable-state
reset mistakes.

**Test 2 — table-origin X:**

```python
@pytest.mark.asyncio
async def test_geometry_table_slider_no_render_loop(user: User, monkeypatch) -> None:
    await _load_philips_example(user)
    await _open_geometry_tab(user)
    await user.should_see("Table origin override", retries=50)

    get_calls = _install_make_fig_counter(monkeypatch)
    user.find("Setup view").click()
    await asyncio.sleep(GEOMETRY_DEBOUNCE_SEC + 0.5)
    assert get_calls() == 1, f"Initial render should run once, got {get_calls()}"

    user.find(marker="table-slider-x").trigger("update:model-value", 5.0)
    await asyncio.sleep(GEOMETRY_DEBOUNCE_SEC + 0.5)
    assert get_calls() == 2, f"Expected 2 total renders after table-slider-x, got {get_calls()}"
    await asyncio.sleep(1.0)
    assert get_calls() == 2, f"Plot re-rendered while idle, count={get_calls()}"
```

**Test constraints**

- Use `_set_slider_value()` (`set_value` inside `user.client`) — not bare `slider.value`
  or `user.find(marker=...).trigger(...)`. `user.find` uses `only_visible=True` and
  misses sliders under bind-hidden ancestors; see HARNESS_ENGINEERING.md.
- Phase 1 Steps 5–6 markers required for `_slider_by_marker()`.
- If a test flakes on CI, check which `should_see` timed out; bump `retries` or
  inspect `user.client.elements` — type checkers cannot catch harness timing issues.
- Run `pytest tests/gui/` locally before marking complete.

## Phase 3 — Validate and smoke

```bash
pytest tests/gui/test_gui_flows.py::test_geometry_patient_slider_no_render_loop -v
pytest tests/gui/test_gui_flows.py::test_geometry_table_slider_no_render_loop -v
pytest tests/gui/ -v
ruff check src/mypyskindose/gui/tabs/geometry.py tests/gui/test_gui_flows.py
basedpyright src/mypyskindose/gui/tabs/geometry.py tests/gui/test_gui_flows.py
git diff --stat   # expect only geometry.py, test_gui_flows.py, CHANGELOG.md
```

Pre-commit / pre-push hooks run ruff, basedpyright, file-size, and doc-freshness
checks automatically; the explicit `pytest` commands above are the additional gate.

Manual (`python -m mypyskindose --mode gui`): drag patient and table-origin
sliders; switch exams; toggle composite; load new example; change per-exam
toggle in Settings; change phantom scale in Settings; rotate plot 5 s without
spinning wheel returning.

**CHANGELOG** — under `## [Unreleased]` → `### Fixed` (match existing bullet style):

```markdown
- **Geometry tab render loop** (2026-06-25) — stop Plotly re-rendering on a 0.25 s timer after slider drags or external refresh; break the cycle with an `_in_render_chain` closure flag. Plan: `dev-docs/plans/GEO_TAB_SPINNING_WHEEL_PLAN.md`.
```

## Decision log

| Date | Decision |
|------|----------|
| 2026-06-25 | Keep lines 592–594; guard with `_in_render_chain` instead of deleting (seven external `ctx.refresh_per_exam()` callers need the re-schedule). |
| 2026-06-25 | Drop `_render_in_progress` guard — sequential `ui.timer` does not break the loop. |
| 2026-06-25 | Scope `try/finally` to sync `ctx.refresh_per_exam()` only; drop flag before `await _render_preview`. |
| 2026-06-25 | Remove entire redundant `if last_preview_mode:` block in `_on_exam_select_change`. |
| 2026-06-25 | Regression tests: `trigger("update:model-value", …)` + slider `.mark()`; tab settle via `should_see("Setup view")`. |
| 2026-06-25 | Phase 2 expanded: parametrized patient sliders + `table-slider-x` test. |
| 2026-06-25 | Fourth review (`tmp/GEO_TAB_SPINNING_WHEEL_PLAN_ASSESSMENT_20260625T061048Z.md`): top-of-file imports only; numbered Phase 1 steps; split load helpers; `PHILIPS_EXAMPLE` constant; table-origin evidence cited; `retries=50`; total-render assertions; Phase 3 `git diff --stat` + pre-commit note. |
| 2026-06-25 | Implemented. GUI tests use `_slider_by_marker` + `set_value` in `user.client` because `user.find(marker=…)` skips bind-hidden sliders. |

## Progress log

- 2026-06-25 — Plan written; reviewed against assessment and codebase.
- 2026-06-25 — Phase 2 expanded; fourth review feedback incorporated.
- 2026-06-25 — Implemented: `_in_render_chain` fix, slider markers, regression tests, CHANGELOG.
