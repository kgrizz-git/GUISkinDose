# Geometry Tab Spinning Wheel Fix Plan

> **Source assessment:** [assessments/GEO_TAB_SPINNING_WHEEL_20260625.md](../assessments/GEO_TAB_SPINNING_WHEEL_20260625.md)
> contains the full root-cause analysis and the review of the originally proposed
> fix. This plan implements the **revised** recommendation (§10.1 of the
> assessment): keep the re-schedule in `_refresh_geometry_sliders()` for external
> callers, and break the self-reinforcing cycle with an `_in_render_chain` flag.

## Objective

Stop the Geometry tab's Plotly plot from re-rendering on a 0.25 s timer loop
after any slider drag, exam-selection change, or external `ctx.refresh_per_exam()`
call, while preserving every existing refresh path that depends on
`_refresh_geometry_sliders()` to schedule the re-render.

## Scope

In scope:

- `src/mypyskindose/gui/tabs/geometry.py` — add `_in_render_chain` closure flag
  and guard the re-schedule at lines 592-594; remove the redundant
  `_schedule_debounced_render()` in `_on_exam_select_change()` at line 553.
- `tests/gui/` — add a regression test that asserts no second render is
  scheduled after the first debounced render settles.

Out of scope:

- Any change to the debounce timing (`GEOMETRY_DEBOUNCE_SEC`).
- The re-entrancy guard (`_render_in_progress`) from the assessment's tertiary
  fix — it is defensive only and does not address the bug.
- The large-figure rendering speed concern (§Contributing factor #4 in the
  assessment) — separate issue.

## Acceptance criteria

- [ ] After dragging a patient or table-origin slider, the Geometry plot
      re-renders at most once per 0.25 s burst (no continuous timer chain).
- [ ] After releasing the slider, the plot is stable long enough for the user
      to rotate/zoom it with the mouse (no Plotly spinning-wheel).
- [ ] The 3D `make_geometry_fig` is not invoked on a periodic timer; it is
      invoked only by user actions (slider drag, exam selection, composite
      toggle, preview button) or by an external `ctx.refresh_per_exam()` call.
- [ ] Loading a new file, removing an exam, switching the active exam, changing
      a per-exam correction in Settings, or changing a per-exam coordinate
      toggle in Settings all still cause the Geometry plot to redraw.
- [ ] Removing the manual `_schedule_debounced_render()` in
      `_on_exam_select_change()` does not regress the exam-selection render.
- [ ] A new or extended GUI smoke test in `tests/gui/` covers the regression
      ("sliding a patient offset does not produce a render loop").

## Phases

### Phase 1 — Break the render cycle in `geometry.py`

1. In `build()` (geometry.py:70), add `_in_render_chain = False` to the
   closure-local flags (next to `slider_timer`, `live_preview_requested`, etc.).
2. In `_do_debounced_render()` (geometry.py:387-400):
   - Add `_in_render_chain` to the `nonlocal` declaration.
   - Keep the existing `if table_origin_pending:` commit block **outside**
     the `try/finally` (it is synchronous and unrelated to the render chain).
   - Set `_in_render_chain = True` **only** around the synchronous
     `ctx.refresh_per_exam()` call. The `try/finally` must **not** wrap the
     `await _render_preview(...)` call — if it did, the flag would stay
     `True` while the await yields the event loop, and a user interaction
     (e.g., exam-selector change) that fires `ctx.refresh_per_exam()` during
     that window would be silently swallowed by the
     `not _in_render_chain` guard in `_refresh_geometry_sliders()`, leaving
     the plot stuck on the old state.
   - Final shape:
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
             ctx.refresh_per_exam()  # _refresh_geometry_sliders() sees the flag
         finally:
             _in_render_chain = False
         _update_preview_caption()
         if live_preview_requested and live_preview_allowed() and last_preview_mode:
             await _render_preview(last_preview_mode)
         live_preview_requested = False
         _update_paused_badge()
     ```
3. In `_refresh_geometry_sliders()` (geometry.py:568-594):
   - Add `_in_render_chain` to the `nonlocal` declaration alongside the
     other closure variables it reads. The variable is only read in this
     function (in the guard at step 3b), so `nonlocal` is not strictly
     required for read-only access, but declaring it explicitly documents
     the closure relationship and silences any linter warnings about
     implicit closure capture if a future edit adds an assignment.
   - Change the re-schedule block at lines 592-594 from:
     ```python
     if last_preview_mode:
         live_preview_requested = True
         _schedule_debounced_render()
     ```
     to:
     ```python
     if last_preview_mode and not _in_render_chain:
         live_preview_requested = True
         _schedule_debounced_render()
     ```
4. In `_on_exam_select_change()` (geometry.py:535-553):
   - Remove `live_preview_requested` from the `nonlocal` declaration at
     line 536 — after the next step it is no longer read or assigned in
     this function.
   - Remove the **entire** `if last_preview_mode:` block at lines 551-553.
     With the previous steps in place, `ctx.refresh_per_exam()` on line 550
     already reaches `_refresh_geometry_sliders()` (via the wrapped callback
     at lines 598-602), which sets `live_preview_requested = True` and
     calls `_schedule_debounced_render()` for us. The local block is fully
     redundant.
   - Final shape of the tail of `_on_exam_select_change`:
     ```python
     def _on_exam_select_change(_e) -> None:
         nonlocal last_table_origin_scrub, slider_timer, table_origin_pending
         if exam_selector_guard["suppress"]:
             return
         old_index = state.active_exam_index
         if slider_timer is not None:
             slider_timer.cancel()
             slider_timer = None
         if table_origin_pending and old_index is not None:
             commit_table_origin_transform(state, old_index)
             table_origin_pending = False
         new_index = int(exam_select.value or 0)
         state.active_exam_index = new_index
         last_table_origin_scrub = False
         _update_preview_caption()
         ctx.refresh_per_exam()
     ```

Files touched: `src/mypyskindose/gui/tabs/geometry.py`.

### Phase 2 — Regression test

Add a regression test to `tests/gui/test_gui_flows.py` (alongside the
existing example-load and tab-heading tests). The test uses NiceGUI's
`User` simulation harness — no manual server start, no
`launch_gui_headless.py` invocation. The test module already declares
`pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")`,
which the new test must inherit.

```python
@pytest.mark.asyncio
async def test_geometry_slider_no_render_loop(user: User, monkeypatch) -> None:
    """Moving a patient slider triggers exactly one debounced render, not an infinite loop."""
    import asyncio
    import mypyskindose.gui.tabs.geometry as geometry_tab
    from mypyskindose.gui.constants import GEOMETRY_DEBOUNCE_SEC, PATIENT_OFFSET_SLIDER_RANGE_CM

    # 1. Load a bundled example RDSR.
    await user.open("/")
    user.find(marker="example-select").click()
    await user.should_see("philips_allura_clarity_u104.dcm", retries=20)
    user.find("philips_allura_clarity_u104.dcm").click()
    await user.should_see("EVENTS", retries=50)

    # 2. Switch to the Geometry tab.
    user.find("4 · Geometry").click()

    # 3. Wrap make_geometry_fig with a counter that still runs the real figure.
    call_count = 0
    original_make_fig = geometry_tab.make_geometry_fig

    def mock_make_fig(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return original_make_fig(*args, **kwargs)

    monkeypatch.setattr(geometry_tab, "make_geometry_fig", mock_make_fig)

    # 4. Trigger an initial Setup view render so the plot is in a settled state.
    user.find("Setup view").click()
    await asyncio.sleep(GEOMETRY_DEBOUNCE_SEC + 0.5)
    assert call_count == 1, f"Initial render should run exactly once, got {call_count}"
    call_count = 0  # isolate the slider behavior.

    # 5. Locate a patient-offset slider (range ±PATIENT_OFFSET_SLIDER_RANGE_CM).
    sliders = [e for e in user.client.elements.values() if isinstance(e, ui.slider)]
    patient_sliders = [
        s for s in sliders
        if s._props.get("min") == -PATIENT_OFFSET_SLIDER_RANGE_CM
        and s._props.get("max") == PATIENT_OFFSET_SLIDER_RANGE_CM
    ]
    assert patient_sliders, "Could not find patient offset sliders on Geometry tab"
    slider = patient_sliders[0]

    # 6. Programmatically move the slider inside the NiceGUI client context.
    with user.client:
        slider.value = 5.0

    # 7. Wait for the debounce + render to settle, then assert exactly one render.
    await asyncio.sleep(GEOMETRY_DEBOUNCE_SEC + 0.5)
    assert call_count == 1, (
        f"Expected exactly 1 render after slider move, got {call_count} "
        f"(infinite render loop detected)"
    )

    # 8. Verify no further renders fire while idle.
    await asyncio.sleep(1.0)
    assert call_count == 1, f"Plot re-rendered while idle, count is {call_count}"
```

Notes:

- `ui` must be imported in the test module (`from nicegui import ui`).
- `User` is already imported in `test_gui_flows.py`.
- The slider range is `±150` (`PATIENT_OFFSET_SLIDER_RANGE_CM = 150` in
  `src/mypyskindose/gui/constants.py:30`) — do **not** hard-code `100`.
- The `user.client` context manager is the NiceGUI fixture for mutating
  widget state from a test (mirrors the pattern in `test_gui_security.py`).
- `tests/scripts/launch_gui_headless.py` is a developer-facing wrapper that
  runs `pytest tests/gui/`; the test itself does not call it.

### Phase 3 — Manual smoke

Run the GUI locally and verify the visual symptom is gone:

```bash
python -m mypyskindose --mode gui
```

Then in the browser:

- Drag a patient offset slider — plot updates after ~0.25 s, then stops.
- Drag a table-origin slider — same.
- Switch exams in the multi-exam selector — plot updates, then stops.
- Toggle the composite checkbox — plot updates, then stops.
- Load a new example RDSR — plot updates, then stops.
- Change a per-exam coordinate toggle in Settings → Per-exam corrections —
  Geometry plot updates, then stops.
- After release, rotate the 3D plot with the mouse for at least 5 s without
  the spinning wheel returning.

## Decision log

- **2026-06-25** — Original assessment proposed removing lines 592-594 of
  `_refresh_geometry_sliders()`. Review found this would break seven external
  `ctx.refresh_per_exam()` callers that rely on those lines to re-render the
  plot. Revised to the `_in_render_chain` flag approach.
- **2026-06-25** — Dropped the `_render_in_progress` re-entrancy guard: NiceGUI
  timers fire sequentially, not concurrently, so it never short-circuits the
  loop. The `_in_render_chain` flag breaks the loop instead.
- **2026-06-25** — Confirmed: removing the redundant
  `_schedule_debounced_render()` at `_on_exam_select_change()` line 553 is safe
  because `ctx.refresh_per_exam()` on line 550 reaches
  `_refresh_geometry_sliders()` which schedules the render.
- **2026-06-25 (review of plan)** — Plan-review found a race condition: the
  initial `try/finally` wrapped `await _render_preview()`, leaving
  `_in_render_chain = True` while the event loop yielded. A user interaction
  (e.g., exam-selector change) that fired `ctx.refresh_per_exam()` during
  that await would hit the `not _in_render_chain` guard in
  `_refresh_geometry_sliders()` and be silently dropped, leaving the plot
  stuck. Fix: scope the `try/finally` to the synchronous `ctx.refresh_per_exam()`
  call only; drop the flag to `False` **before** the await.
- **2026-06-25 (review of plan)** — Plan-review also noted that the
  `live_preview_requested = True` line in `_on_exam_select_change()` is
  redundant with the new `_refresh_geometry_sliders()` behavior. Drop the
  whole `if last_preview_mode:` block, not just the
  `_schedule_debounced_render()` call.
- **2026-06-25 (second review of plan)** — Plan-review found three minor
  refinements:
  1. After dropping the `if last_preview_mode:` block,
     `live_preview_requested` is no longer read or assigned in
     `_on_exam_select_change()`. Remove it from the `nonlocal`
     declaration at line 536 to keep the closure surface honest.
  2. Add `_in_render_chain` to the `nonlocal` declaration of
     `_refresh_geometry_sliders()`. The variable is only read there
     today, but explicit declaration documents the closure relationship
     and future-proofs the function against linter warnings if a future
     edit adds an assignment.
  3. Phase 2's regression test was written as if the test file invokes
     `tests/scripts/launch_gui_headless.py`. That script is a developer
     CLI wrapper around `pytest tests/gui/`; tests do not call it. The
     rewritten test uses NiceGUI's `user: User` fixture and the existing
     `pytestmark = pytest.mark.nicegui_main_file(...)` pattern, and
     uses the correct `±150` slider range from
     `PATIENT_OFFSET_SLIDER_RANGE_CM`.

## Progress log

(none yet — plan just created)
