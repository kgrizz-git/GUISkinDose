# Geometry Tab Spinning Wheel / Continuous Plot Reload

**Date:** 2026-06-25 (initial); 2026-06-25 (review of recommended fix)
**File:** `src/mypyskindose/gui/tabs/geometry.py`
**Status:** Root-cause analysis confirmed; primary fix has a regression; see §10 for revised recommendation.

---

## Problem

On the Geometry tab, the Plotly plot shows a continuous spinning wheel (loading indicator), the plot appears to reload constantly, and the user cannot effectively rotate or interact with the 3D plot because it resets before the interaction completes.

## Root Cause

The geometry tab has **two layers of debouncing** intended to throttle plot updates during slider dragging:

1. **Debounced slider rendering** (`geometry.py:373-384`) — `GEOMETRY_DEBOUNCE_SEC = 0.25` second one-shot timer.
2. **Composite preview pause** (`geometry.py:357-367`) — blocks live preview when busy or composite mode has >30 events.

The debounce is **broken** because `_refresh_geometry_sliders()` unconditionally calls `_schedule_debounced_render()` at the end of its execution (line 592-594), regardless of whether a render is already pending. This creates a self-reinforcing reactive cycle:

```
_user drags slider
  → _on_patient_slider_change() or _on_table_slider()
    → _schedule_debounced_render()      [timer T1 created]
      → (0.25s later) _do_debounced_render()
        → ctx.refresh_per_exam()
          → _refresh_geometry_sliders()
            → _schedule_debounced_render()   [timer T2 created]
              → (0.25s later) _do_debounced_render()
                → ctx.refresh_per_exam()
                  → _refresh_geometry_sliders()
                    → _schedule_debounced_render()   [timer T3 created]
                      → ... infinite loop ...
```

The `live_preview_requested` flag is set to `True` in `_schedule_debounced_render()` and cleared in `_do_debounced_render()`, but `_refresh_geometry_sliders()` unconditionally resets it to `True` and schedules another render before the previous one can settle.

## Contributing Factors

### 1. Table sliders fire on every drag tick

`_on_table_slider()` (`geometry.py:286-308`) calls `_schedule_debounced_render()` on every slider tick during drag. If the `_refresh_geometry_sliders()` debounce cycle is already running, these rapid ticks keep restarting the timer, preventing it from ever settling.

### 2. Exam selector double-schedules

`_on_exam_select_change()` (`geometry.py:535-553`) calls `ctx.refresh_per_exam()` (which triggers `_refresh_geometry_sliders()` which schedules another render) AND then manually calls `_schedule_debounced_render()`. This is double-scheduling — two renders per selection change.

### 3. Composite toggle re-schedules

`_on_composite_toggle()` (`geometry.py:557-566`) calls `_schedule_debounced_render()` after toggling composite mode. Unlike the exam selector, it does not call `ctx.refresh_per_exam()`, so it doesn't create the infinite loop itself, but it adds unnecessary renders.

### 4. Large 3D figures cause slow browser rendering

`figures.py:20-93` — `make_geometry_fig()` builds a Plotly figure dict containing human phantom STL mesh + table + pad + beam cone + detector rectangle + source points. This is a large figure. While Plotly.js renders it in the browser, the spinning wheel indicator is visible. If another `update_figure()` call arrives before the previous render completes, Plotly.js aborts the previous render and starts a new one — making the spinning wheel appear continuous.

## Affected Code Locations

| Entry point | File:Line | Trigger | Issue |
|---|---|---|---|
| `_refresh_geometry_sliders()` | `geometry.py:592-594` | Always runs after `ctx.refresh_per_exam()` | **Always schedules new render** — creates infinite loop |
| `_do_debounced_render()` | `geometry.py:395` | Fires after debounce delay | Calls `ctx.refresh_per_exam()` which re-triggers render |
| `_on_table_slider()` | `geometry.py:286-308` | Every slider drag tick | Keeps restarting timer during drag |
| `_on_exam_select_change()` | `geometry.py:550, 553` | Exam selection change | Double-schedules render |
| `_on_patient_slider_change()` | `geometry.py:434-444` | Patient offset slider tick | Calls `_schedule_debounced_render()` — OK in isolation but feeds the loop |
| `make_geometry_fig()` | `figures.py:20-93` | Every render | Large figure = slow browser render = spinning wheel visible longer |

## Recommended Fix

### Primary fix: Remove unconditional re-schedule from `_refresh_geometry_sliders()`

The `_refresh_geometry_sliders()` function (line 568-594) should only update slider UI values without triggering a new render. The render is already being triggered by the original slider/exam/composite event that caused `ctx.refresh_per_exam()` to be called.

Remove lines 592-594 from `_refresh_geometry_sliders()`:

```python
# REMOVE these lines from _refresh_geometry_sliders():
if last_preview_mode:
    live_preview_requested = True
    _schedule_debounced_render()
```

### Secondary fix: Remove double-schedule from `_on_exam_select_change()`

Remove the manual `_schedule_debounced_render()` call from `_on_exam_select_change()` since `ctx.refresh_per_exam()` already triggers the render chain:

```python
# REMOVE this line from _on_exam_select_change():
_schedule_debounced_render()
```

### Tertiary improvement: Guard `_do_debounced_render()` against re-entrancy

Add a guard to prevent `_do_debounced_render()` from re-scheduling itself via `ctx.refresh_per_exam()`:

```python
async def _do_debounced_render() -> None:
    nonlocal slider_timer, table_origin_pending, live_preview_requested, last_table_origin_scrub, _render_in_progress
    if _render_in_progress:
        return  # Guard against re-entrancy
    _render_in_progress = True
    try:
        slider_timer = None
        if table_origin_pending:
            commit_table_origin_transform(state, _active_exam_index())
            table_origin_pending = False
            last_table_origin_scrub = False
            reset_results()
        ctx.refresh_per_exam()
        _update_preview_caption()
        if live_preview_requested and live_preview_allowed() and last_preview_mode:
            await _render_preview(last_preview_mode)
        live_preview_requested = False
        _update_paused_badge()
    finally:
        _render_in_progress = False
```

## Impact

- **User experience:** Plot will stabilize during slider dragging, allowing effective 3D rotation and interaction.
- **Performance:** Fewer unnecessary plot updates (potentially dozens per second during slider drag → at most 1 per 0.25s).
- **Risk:** Low. The debounce pattern is existing behavior; removing the re-schedule calls preserves the intended throttling while fixing the infinite loop.

---

## 10. Review of the recommended fix (2026-06-25)

The cycle analysis (§Root cause) and the secondary fix (removing the redundant
`_schedule_debounced_render()` in `_on_exam_select_change()`) are **correct**.

The primary fix (removing lines 592-594 from `_refresh_geometry_sliders()`) is
**too aggressive** and would break external refresh paths that have no companion
render trigger of their own. The claim that "the render is already being
triggered by the original slider/exam/composite event that caused
`ctx.refresh_per_exam()` to be called" is **false** for the following callers:

| File:Line | Caller | Why it needs the re-schedule in `_refresh_geometry_sliders()` |
|---|---|---|
| `upload.py:224` | File unload | Empty state must clear/redraw the plot |
| `upload.py:263` | `load_example()` | New file must redraw the plot |
| `upload.py:315` | `_select_exam_for_geometry()` | Switching exam must redraw |
| `upload.py:379` | `_refresh_exams_table()` | Adding/removing exams must redraw |
| `_per_exam.py:61` | Per-exam offset spinbox | Sliders sync, plot must redraw |
| `_per_exam.py:73` | Coordinate-correction toggle | Plot must reflect new transform |
| `offset_handlers.py:103` | `on_global_patient_offset_change()` | Global slider → redraw |

In every row above, there is no "original slider/exam/composite event" — the
caller is a different tab or a structural change (add/remove exam). The plot
re-render is driven **only** by lines 592-594 of `_refresh_geometry_sliders()`.
Removing them would cause: upload a new file, change a per-exam correction, or
remove an exam → sliders update, but the plot stays stale. That is a worse
regression than the spinning wheel.

The tertiary fix (re-entrancy guard) does not break the loop on its own. The
`ui.timer` fires **sequentially**, not concurrently, so the guard never returns
early. The loop is broken by the primary fix; if the primary fix is replaced
with the guard alone, the loop continues.

### 10.1 Revised recommendation

Keep lines 592-594 but make them a **no-op when called from inside
`_do_debounced_render()`**. Add a closure flag `_in_render_chain` and guard
the re-schedule:

```python
# In build()'s closure, near the other flags
_in_render_chain = False

# In _do_debounced_render():
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
        ctx.refresh_per_exam()  # _refresh_geometry_sliders() will see the flag
    finally:
        _in_render_chain = False
    _update_preview_caption()
    if live_preview_requested and live_preview_allowed() and last_preview_mode:
        await _render_preview(last_preview_mode)
    live_preview_requested = False
    _update_paused_badge()

# In _refresh_geometry_sliders():
#   - add `_in_render_chain` to the nonlocal declaration (line 569)
#   - change lines 592-594 to:
if last_preview_mode and not _in_render_chain:
    live_preview_requested = True
    _schedule_debounced_render()

# In _on_exam_select_change():
#   - remove `live_preview_requested` from the nonlocal declaration (line 536)
#   - drop the entire `if last_preview_mode:` block (lines 551-553);
#     ctx.refresh_per_exam() now handles it downstream.
```

The `try/finally` is scoped to the **synchronous** `ctx.refresh_per_exam()`
call only — it must not wrap the `await _render_preview(...)`. If the flag
stayed `True` across the await, a user interaction (e.g., exam-selector
change) that fires `ctx.refresh_per_exam()` during the await would be
silently swallowed by the `not _in_render_chain` guard, leaving the plot
stuck on the old state. Keeping the flag set only for the synchronous
re-schedule path is what breaks the loop while preserving responsiveness.

### 10.2 Impact on interactive offset sliders

- **Patient sliders** (`_on_patient_slider_change`, geometry.py:434-444):
  unchanged. The handler calls `_schedule_debounced_render()` directly at
  line 444, which fires the timer. When the timer fires, the flag is set
  before `ctx.refresh_per_exam()` is called; `_refresh_geometry_sliders()`
  sees the flag and skips the re-schedule. One render per 0.25 s burst.
- **Table-origin sliders** (`_on_table_slider`, geometry.py:291-308):
  unchanged. Same direct `_schedule_debounced_render()` call at line 308.
- **External `ctx.refresh_per_exam()` callers** (upload, per-exam, offset
  handlers): unchanged. The flag is `False` for them, so the re-schedule
  fires and the plot redraws.

### 10.3 What to skip from the original recommendation

- Do **not** apply the primary fix as written.
- The tertiary fix (`_render_in_progress` guard) is not needed for correctness
  once the `_in_render_chain` flag is in place. It can be kept as defensive
  code if desired, but it does not address the actual bug.
- Do **not** wrap `await _render_preview(...)` inside the `try/finally`. The
  flag must drop to `False` before the await yields the event loop, or
  user interactions during the await will be silently swallowed.

A full implementation plan is at
[plans/GEO_TAB_SPINNING_WHEEL_PLAN.md](../plans/GEO_TAB_SPINNING_WHEEL_PLAN.md).
