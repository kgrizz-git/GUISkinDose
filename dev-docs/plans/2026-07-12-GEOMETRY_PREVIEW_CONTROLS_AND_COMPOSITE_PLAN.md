# Geometry Preview Controls & Composite Layout Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relocate the "Show all exams in preview" checkbox and its caption above the plot next to the "Full procedure" button, prevent `last_table_origin_scrub` from leaking into procedure preview mode, and replace the event number box with searchable/typable dropdowns (`ui.select(with_input=True)`).

**Architecture:**
- Relocate `_GE_WARNING_TOKEN` and `geometry_vendor_notice` (`geometry.py:57, 66-98`, ~34 lines) to `src/mypyskindose/gui/geometry_preview.py` and keep a 1-line re-export alias in `geometry.py` so existing tests in `test_gui_offset_reset.py` remain green. Net drop in `geometry.py`: ~33 lines down to ~763 lines.
- Move `composite_checkbox` and `preview_caption` from `preview_controls` into the top control bar (`ui.row()`) immediately to the right of the `Full procedure` button wrapped in a column bound to `state.is_multi_exam`. Remove the now-empty `preview_controls` sidebar container.
- In `preview_procedure()` (`geometry.py:675`), add `last_table_origin_scrub` to line 676's `nonlocal` statement (`nonlocal last_preview_mode, live_preview_requested, last_table_origin_scrub`). Assigning `last_table_origin_scrub = False` prevents previous table-slider scrubbing from unintentionally forcing composite mode during Full procedure rendering.
- Define `event_select_guard = {"suppress": False}` alongside `exam_selector_guard` (`geometry.py:125`).
- Replace `geom_event_input` (`ui.number`) with two searchable `ui.select(with_input=True)` controls arranged left-to-right inside the Event selection card (`geom_exam_select` | `prev_btn` | `geom_event_select` | `next_btn`):
  1. `geom_exam_select`: Selects exam (`Exam #1`, `Exam #2`, ...). Bidirectionally synced with `exam_select`: when `geom_exam_select` changes, its handler updates `state.active_exam_index` and calls `exam_select.set_value()` guarded by `exam_selector_guard["suppress"]`. Remains enabled in procedure mode so users can switch exams.
  2. `geom_event_select`: Selects event number (`1`, `2`, ... `N`), where `N` is generated from `_preview_slice_count()` (composite-aware) and rebuilt in `_refresh_geometry_sliders()`, `_on_composite_toggle()`, and `_on_exam_select_change()`.
- Retain existing `event_context_caption` exam/composite suffixes (`"Event X / N · Exam #2"` / `"Event X / N · all exams"`) so users retain visual context.
- Keep all option builder helpers in `geometry_preview.py` to guarantee `geometry.py` stays strictly `<= 800` lines (extracting slider-limit helpers if additional headroom is needed).

**Tech Stack:** Python 3.10+, NiceGUI (`ui.select`, `ui.checkbox`, `ui.row`), pytest.

## Global Constraints

- Follow line length 120 (ruff).
- Keep all Python source and Markdown files under ~800 lines (`geometry.py` must remain strictly <= 800 lines).
- Target cross-platform compatibility (macOS, Linux, Windows).
- Maintain existing tests passing and add unit/GUI helper tests for new selection formatting.

---

### Task 1: Headroom Extraction, Composite Checkbox Relocation & Nonlocal Reset Fix

**Files:**
- Modify: `src/mypyskindose/gui/geometry_preview.py`
- Modify: `src/mypyskindose/gui/tabs/geometry.py`
- Test: `tests/unittests/test_gui_multi_exam_geometry_offsets.py`
- Test: `tests/unittests/test_gui_offset_reset.py`

**Interfaces:**
- Consumes: `state.is_multi_exam`, `resolve_composite_for_render`
- Produces: `geometry_vendor_notice` and `_GE_WARNING_TOKEN` exported from `geometry_preview.py`; top-bar composite checkbox; cleared `last_table_origin_scrub` when running `preview_procedure()`.

- [ ] **Step 1: Write failing test in `test_gui_multi_exam_geometry_offsets.py`**

Add unit test verifying `from mypyskindose.gui.geometry_preview import geometry_vendor_notice`.

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unittests/test_gui_multi_exam_geometry_offsets.py -v`

- [ ] **Step 3: Relocate `geometry_vendor_notice` and modify `geometry.py` layout**
  - Move `_GE_WARNING_TOKEN` and `geometry_vendor_notice` (`geometry.py:57, 66-98`) into `geometry_preview.py` and keep a 1-line re-export alias `from mypyskindose.gui.geometry_preview import geometry_vendor_notice` in `geometry.py`.
  - Move `composite_checkbox` and `preview_caption` into the top bar next to `Full procedure` bound to `state.is_multi_exam`. Delete the empty `preview_controls` sidebar definition.
  - In `preview_procedure()` (`geometry.py:675`), add `last_table_origin_scrub` to line 676's `nonlocal` statement: `nonlocal last_preview_mode, live_preview_requested, last_table_origin_scrub` and assign `last_table_origin_scrub = False` before calling `_render_preview("plot_procedure")`.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unittests/test_gui_multi_exam_geometry_offsets.py tests/unittests/test_gui_offset_reset.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/mypyskindose/gui/geometry_preview.py src/mypyskindose/gui/tabs/geometry.py tests/unittests/test_gui_multi_exam_geometry_offsets.py
git commit -m "feat(gui): relocate composite checkbox above plot, extract vendor notice, and fix nonlocal scrub reset"
```

---

### Task 2: Implement Searchable Exam & Event Dropdowns (`ui.select(with_input=True)`)

**Files:**
- Modify: `src/mypyskindose/gui/tabs/geometry.py`
- Modify: `src/mypyskindose/gui/geometry_preview.py`
- Test: `tests/unittests/test_gui_multi_exam_geometry_offsets.py`

**Interfaces:**
- Consumes: `_preview_slice_count()`, `state.active_exam_index`
- Produces: Searchable dropdown selectors for Exam (`geom_exam_select`) and Event (`geom_event_select`) arranged (`geom_exam_select` | `prev_btn` | `geom_event_select` | `next_btn`) with suppression guards.

- [ ] **Step 1: Write failing test for event select options helper in `test_gui_multi_exam_geometry_offsets.py`**

Write unit tests verifying:
- Option dictionary generated for `slice_count`: `{1: "1", 2: "2", ..., N: "N"}`.
- Verify `event_context_caption` retains existing suffix (`"Event X / N · Exam #2"` or `"Event X / N · all exams"`).

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/unittests/test_gui_multi_exam_geometry_offsets.py -v`

- [ ] **Step 3: Implement select controls and suppression guards in `geometry.py`**
  - Implement option helper in `geometry_preview.py`.
  - Define `event_select_guard = {"suppress": False}` alongside `exam_selector_guard` (`geometry.py:125`).
  - In `geometry.py`, replace `geom_event_input = ui.number(...)` with two `ui.select(with_input=True)` controls in the Event selection card row (`geom_exam_select` | `prev_btn` | `geom_event_select` | `next_btn`) using `.on_value_change(...)`.
  - Bidirectionally sync `geom_exam_select` with `exam_select` where both handlers check `exam_selector_guard["suppress"]`. Keep `geom_exam_select` enabled in procedure mode.
  - Update control-wiring sites: line 456 (`_set_stepper_enabled`) enables/disables `geom_event_select`; line 484 wires `on_value_change`; lines 772/780 wrap `.set_value()`/`.set_options()` in `event_select_guard["suppress"] = True`.
  - Update value-read sites (`449, 451, 465, 572, 776`) to `int(geom_event_select.value or 1)`.
  - Rebuild `geom_event_select` options inside `_refresh_geometry_sliders()`, `_on_composite_toggle()`, and `_on_exam_select_change()`.
  - Verify total lines in `geometry.py` remain `<= 800`.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/unittests/test_gui_multi_exam_geometry_offsets.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/mypyskindose/gui/geometry_preview.py src/mypyskindose/gui/tabs/geometry.py tests/unittests/test_gui_multi_exam_geometry_offsets.py
git commit -m "feat(gui): replace event number box with searchable Exam and Event dropdowns with guarded sync"
```
