# Geometry Tab Per-Exam Event Selection Plan

> **TO_DO item:** *"Geometry tab per-exam event selection — let users select or step through events per exam; account for Plotly trace count and large datasets."*
>
> **Prerequisite context:** [MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md](MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md) Parts I–V shipped. The Geometry tab already has an exam selector (`geometry.py:188-192`), a bare `ui.number` event input (`geometry.py:395-397`), preview slicing (`geometry_preview.py:78-95`), event clamping (`geometry_preview.py:161-178`), three preview-mode buttons, a composite toggle (`geometry.py:198-201`), and composite-pause thresholds (30 events pause / 100 spinner). This plan is a UX/polish layer on that foundation — no new architecture.

**Plan status:** Draft — 2026-07-11.

---

## Objective

Make per-exam event stepping in the Geometry tab feel natural and informative, without re-architecting the multi-exam plumbing that already works. Concretely:

1. Replace the bare number box with a **stepper row** showing context ("Event 5 / 23 — Exam #2") and a labeled prev/next control.
2. Keep the event index usable only for the **Single event** preview mode (the input is meaningless in Setup/Full-procedure modes).
3. Reaffirm the existing performance guards; add a small trace-count clarification so future editors know where the guard line is.
4. No new modules — all changes are edits inside `geometry.py` and helpers inside `geometry_preview.py`.

---

## What exists today (do not rebuild)

| Surface | Location | Already does |
|---------|----------|--------------|
| Exam selector | `geometry.py:188-192` | `ui.select` → `state.active_exam_index`; multi-exam only; rebuild guard `exam_selector_guard` |
| Event number input | `geometry.py:395-397` | `geom_event_input` (`ui.number`, min 0, step 1); shared across modes |
| Preview slice | `geometry_preview.py:78-95` | `rdsr_df_for_geometry_preview` slices by `EXAM_INDEX_COLUMN` for the active exam, or all exams when `composite=True` |
| Event clamp | `geometry_preview.py:161-178` | `clamp_geometry_event_index` keeps `geom_event_input` in range on exam switch / composite toggle / new load |
| Three preview buttons | `geometry.py:399-407` | Setup / Single event / Full procedure |
| Composite toggle | `geometry.py:198-201` + `geometry_preview.py:113-121` | "Show all exams in preview" + `resolve_composite_for_render` (last-table-origin-scrub wins) |
| Live-pause thresholds | `geometry_preview.py:181-199` | `composite_live_preview_paused` pauses `plot_procedure` above 30 composite events; `geometry.py:499` shows spinner above 100 |
| Auto-init middle event | `geometry.py:143-151, 684-692` | First time the tab is opened for a fresh load, default to the middle event of the active slice; one-time per load signature |

### Why the foundation is good enough

- The selector + slice + clamp chain already answers the per-exam question. When the user picks Exam #2, `preview_event_count(state, active_exam_index=1)` returns that exam's event count, `geom_event_input` is clamped, and `_render_preview("plot_event")` feeds the right slice into `make_geometry_fig`.
- `make_geometry_fig` already threads `active_exam_index` and `composite` through to `rdsr_df_for_geometry_preview` and `effective_patient_offset_for_preview`. No signature change needed.
- The existing 30/100 composite thresholds are the **Plotly trace count guard** the TO_DO calls out for large datasets. This plan documents this rather than introducing a second guard.

---

## Gaps this plan closes

| Gap | Current | Target |
|-----|---------|--------|
| **A. Context label** | `geom_event_input` shows a bare number; the user has to look elsewhere to know how many events are in the slice or which exam they're looking at. | A caption next to the input: `"Event <n> / <count> · Exam #<m>"` (or no exam suffix in single-exam mode; "(composite)" suffix when `Show all exams in preview` is on). |
| **B. Stepper buttons** |	User must type into the number box and press Enter; there's no prev/next affordance. | <kbd>Prev</kbd> / <kbd>Next</kbd> buttons (or chevron icons) that step by one, clamping at the ends (no error toast — just stop at 0 / count−1). |
| **C. Mode awareness** | `geom_event_input` is always enabled even though it only affects `plot_event` mode; in `plot_setup` / `plot_procedure` its value is ignored, which can confuse users. | Disable the stepper (input + prev/next) unless `last_preview_mode == "plot_event"`. Re-enable when the user clicks **Single event**. The existing buttons keep setting `last_preview_mode`; the stepper becomes a "focused" control for that mode. |
| **D. Trace-count guard documentation** | The 30/100 thresholds are buried in `geometry_preview.py` and the `geometry.py:497` spinner check. Future editors will not realize this is the "Plotly trace count" guard. | A short comment block in `geometry_preview.py` calling out the guard's location, the composite-only scope, and why `plot_event` mode does **not** need a guard (one event → a small fixed trace set). |
| **E. Help-file wording** | `geometry_workflow.md:28` tells users to "Enter an event number"; no mention of prev/next or the context caption. | One or two lines updated to mention the stepper and the "disabled until Single event is clicked" behavior. |

---

## Part I — Event-context helper (pure logic)

**File:** `src/mypyskindose/gui/geometry_preview.py`

Add a small module-level helper (no NiceGUI dependency, unit-testable in isolation):

```python
def event_context_caption(
    state: AppState,
    *,
    current_index: int,
    active_exam_index: int | None = None,
    composite: bool = False,
) -> str:
    """User-facing caption for the Geometry event stepper row.

    Examples:
      single-exam, 23 events, idx 5 -> "Event 5 / 23"
      multi-exam exam #2 (idx 1), 7 events, idx 3 -> "Event 3 / 7 · Exam #2"
      multi-exam composite, 51 events, idx 9 -> "Event 9 / 51 · all exams"
    """
    count = preview_event_count(
        state, active_exam_index=active_exam_index, composite=composite
    )
    safe_idx = clamp_geometry_event_index(
        state, current_index,
        active_exam_index=active_exam_index, composite=composite,
    )
    if state.is_multi_exam:
        if composite:
            return f"Event {safe_idx} / {count} · all exams"
        exam_num = (active_exam_index if active_exam_index is not None
                    else state.active_exam_index or 0) + 1
        return f"Event {safe_idx} / {count} · Exam #{exam_num}"
    return f"Event {safe_idx} / {count}"
```

**Why module-level:** mirrors `clamp_geometry_event_index` and `preview_event_count`, which are already module-level and tested via `test_gui_multi_exam_geometry_offsets.py` and `test_gui_part_v_formatters.py`.

**Edge cases:**
- `count == 0` (empty slice): caption returns `"Event 0 / 0"` — the stepper is also disabled (Part II-C), so this is just a placeholder before the user loads data.
- `current_index` out of range: `clamp_geometry_event_index` clamps it; the caption shows the clamped value, not the raw input. The stepper's `_on_prev` / `_on_next` use the clamped value anyway.

---

## Part II — Stepper row UI (geometry.py)

**File:** `src/mypyskindose/gui/tabs/geometry.py` (712 lines today; cap 800; this adds ~25 net after removing the bare card header label).

### II-A. Replace the event-selection card

Current (`geometry.py:392-397`):

```python
with ui.row().classes("w-full items-end gap-4"):
    with ui.card().classes("modern-card w-48 p-2"):
        ui.label("Event selection").classes("text-xs uppercase opacity-70")
        geom_event_input = ui.number(value=0, min=0, step=1).classes(
            "w-full mono-text"
        ).props("dense flat")
    ui.button("Setup view", ...)  # unchanged
    ui.button("Single event", ...)
    ui.button("Full procedure", ...)
```

Replace with a stepper card that adds an inline context label and prev/next buttons:

```python
with ui.row().classes("w-full items-end gap-4"):
    with ui.card().classes("modern-card w-64 p-2"):
        ui.label("Event selection").classes("text-xs uppercase opacity-70")
        with ui.row().classes("w-full items-center gap-2"):
            def _step(delta: int) -> None:
                if last_preview_mode != "plot_event":
                    return
                count = _preview_slice_count()
                if count <= 0:
                    return
                current = int(geom_event_input.value or 0)
                new_idx = min(max(0, current + delta), count - 1)
                geom_event_input.set_value(new_idx)
                _render_event_preview_debounced()

            ui.button(icon="chevron_left", on_click=lambda: _step(-1)
                ).props("flat dense round size=sm color=grey-5"
                ).mark("geom-event-prev")
            geom_event_input = ui.number(
                value=0, min=0, step=1
            ).classes("w-20 mono-text").props("dense flat").mark("geom-event-input")
            ui.button(icon="chevron_right", on_click=lambda: _step(1)
                ).props("flat dense round size=sm color=grey-5"
                ).mark("geom-event-next")
        geom_event_context = ui.label("").classes("text-caption text-grey-5 q-mt-xs")
    ui.button("Setup view", ...)        # unchanged
    ui.button("Single event", ...)       # unchanged
    ui.button("Full procedure", ...)     # unchanged
```

`_preview_slice_count()` is a small inline closure that reuses the existing helpers:

```python
def _preview_slice_count() -> int:
    if state.is_multi_exam:
        return preview_event_count(
            state,
            active_exam_index=state.active_exam_index,
            composite=_resolve_composite_for_render(),
        )
    return event_count()
```

**Why chevron icons:** plotly already provides a slider for `plot_procedure` mode; we're not duplicating that. The stepper is for single-event mode only and is a light control — two icon buttons + the existing number input. Matches the icon-button pattern already used for the "Reset to auto-detected" / "Reset patient offset to 0" buttons (`geometry.py:258, 386`).

### II-B. Disable stepper when not in `plot_event` mode

Add a helper to toggle the three stepper widgets together:

```python
def _set_stepper_enabled(enabled: bool) -> None:
    geom_event_input._props["disable"] = not enabled
    geom_event_input.update()
    # prev / next are found by `.mark(...)` if needed; simpler to keep direct refs
    prev_btn.set_enabled(enabled)
    next_btn.set_enabled(enabled)

def _update_event_context() -> None:
    composite = _resolve_composite_for_render() if state.is_multi_exam else False
    geom_event_context.set_text(
        event_context_caption(
            state,
            current_index=int(geom_event_input.value or 0),
            active_exam_index=state.active_exam_index if state.is_multi_exam else None,
            composite=composite,
        )
    )
```

Wire the enable/disable into the three existing preview button handlers and `_refresh_geometry_sliders`:

- `preview_setup()` → `_set_stepper_enabled(False)` after setting `last_preview_mode = "plot_setup"`.
- `preview_event()` → `_set_stepper_enabled(True)` after setting `last_preview_mode = "plot_event"`.
- `preview_procedure()` → `_set_stepper_enabled(False)`.
- `_refresh_geometry_sliders()` → call `_set_stepper_enabled(last_preview_mode == "plot_event")` and `_update_event_context()` after the existing `clamp_geometry_event_index` block.

### II-C. Render on step (debounced)

`_render_event_preview_debounced()` is a thin wrapper around `_schedule_debounced_render()` that also ensures `last_preview_mode = "plot_event"` (so a step while the preview was cleared re-arms it). Re-use the existing debounce; do **not** add a new timer.

```python
def _render_event_preview_debounced() -> None:
    nonlocal last_preview_mode
    if last_preview_mode != "plot_event":
        last_preview_mode = "plot_event"
    _update_event_context()
    _schedule_debounced_render()
```

Add the same `_update_event_context()` call to `_on_exam_select_change` and `_on_composite_toggle` so the caption re-labels when the user switches exam or toggles composite. Also hook the existing `geom_event_input.on_value_change` to `_update_event_context` + debounce (so typing into the box still works).

### II-D. File-size check

- `geometry.py` is at **712 lines**. Cap is **800**, no whitelist (`scripts/check_file_sizes.py`).
- Net additions:
  - Stepper card body: +~15 lines (replaces 4-line card).
  - `_set_stepper_enabled`, `_update_event_context`, `_render_event_preview_debounced`, `_preview_slice_count`, `_step`: +~30 lines.
  - Enable/disable hooks inside the three preview_* handlers + `_refresh_geometry_sliders`: +~6 lines.
- Estimated total: **~760 lines**. Still under 800. If a reviewer is nervous, the four small closures can move to `geometry_preview.py` (which is 199 lines and has headroom); but doing so would require passing the closures' widget references in (PageContext field or similar), which is more churn than value for 30 lines. Prefer to keep them in `geometry.py` next to the other preview closures.

`geometry_preview.py` is at **199 lines**; adding `event_context_caption` puts it at ~219. Well within cap.

---

## Part III — Trace-count guard documentation

**File:** `src/mypyskindose/gui/geometry_preview.py`

Add a short comment block above `composite_live_preview_paused` (around line 181):

```python
# ────────────────────────────────────────────────────────────────────
# Performance guard: this is the single "Plotly trace count" mitigation
# referenced in dev-docs/plans/GEOMETRY_PER_EXAM_EVENT_SELECTION_PLAN.md.
#
# Scope: composite `plot_procedure` only (is_multi_exam AND _resolve_composite_for_render()
# is True). In that mode `make_geometry_fig` builds one trace set per event across all
# exams, so the figure grows linearly with total event count.
#
# We pause live preview above 30 composite events so a slider drag does not thrash the
# plot, and show the large-data spinner above 100 (geometry.py:499). Single-event mode
# and single-exam / non-composite `plot_procedure` build a small trace set (one event
# in plot_event; one trace-set per event but patient-inclusion is gated separately) and
# do not need a similar guard.
#
# If you add a new preview path that grows traces per event, extend `composite_live_preview_paused`
# rather than adding a second ad-hoc guard here.
# ────────────────────────────────────────────────────────────────────
```

No behavior change. This is the "account for Plotly trace count and large datasets" item from TO_DO — the guard already exists, this just makes it discoverable.

---

## Part IV — Help file update

**File:** `docs/source/gui_help/geometry_workflow.md`

Replace "Step 1: Select an Event" (lines 27-29) and extend the Controls table (lines 63-67). New step wording:

> ### Step 1: Select an Event
> 1. Click **Single event** under the geometry plot to enter single-event mode. The **Event selection** stepper (the number box with chevron buttons) becomes enabled; the small caption shows your position as `Event <n> / <count>` (single-exam) or `Event <n> / <count> · Exam #<m>` (multi-exam, or `· all exams` when **Show all exams in preview** is on).
> 2. Use the chevron buttons or type an event number (0-based) to step through events in the current preview slice.
> 3. In **multi-exam** mode the default slice is the **selected exam** only unless **Show all exams in preview** is enabled. Use the exam selector above the preview controls to pick which exam you are stepping through.

Add to the Controls table:

> | **Event selection stepper** | Jump to a specific event within the current preview slice (prev / next or typed number). Disabled unless **Single event** mode is active. |

Then:

```bash
python scripts/sync_gui_help.py
```

This mirrors the file to `src/mypyskindose/gui/help/geometry_workflow.md`. Do **not** edit the mirror directly (enforced by pre-commit + CI per `AGENTS.md`).

---

## Phases and validation

> **Execution order:** Part I → Part II → Part III → Part IV. Each phase is independently committable. Run `ruff check` + `basedpyright` + `python scripts/check_file_sizes.py` after every phase.

### Phase 1 — `event_context_caption` helper + unit tests

**Files:** `src/mypyskindose/gui/geometry_preview.py`, `tests/unittests/test_gui_multi_exam_geometry_offsets.py` (or `test_gui_part_v_formatters.py`).

**Tests** (pure logic, no NiceGUI):
- `test_event_context_caption_single_exam` — 1 exam, idx 5 / 23 → `"Event 5 / 23"`.
- `test_event_context_caption_multi_exam_active` — 2 exams, active 1 (i.e. Exam #2), slice has 7 events, idx 3 → `"Event 3 / 7 · Exam #2"`.
- `test_event_context_caption_multi_exam_composite` — composite, 51 events, idx 9 → `"Event 9 / 51 · all exams"`.
- `test_event_context_caption_clamps_out_of_range_index` — idx 999 in a 7-event slice → `"Event 6 / 7 · Exam #2"` (clamped).
- `test_event_context_caption_empty_slice` — no events → `"Event 0 / 0"`.

Fixture pattern matches the existing tests in `test_gui_multi_exam_geometry_offsets.py:107` (which already builds a 2-exam `AppState` with `rdsr_df` mock + `EXAM_INDEX_COLUMN`). Reuse that fixture.

**Acceptance:** `pytest tests/unittests/test_gui_multi_exam_geometry_offsets.py -q` green; `basedpyright` clean.

### Phase 2 — Stepper row UI + enable/disable wiring

**File:** `src/mypyskindose/gui/tabs/geometry.py`.

**Acceptance (manual; the `user` fixture can't easily drive `ui.number` typing, and the existing `tests/gui/test_gui_flows.py` focuses on tab headings):
- `python -m mypyskindose --mode gui`, load one example RDSR.
- Click **Single event** → the stepper enables; caption reads `"Event <middle> / <count>"`.
- Click <kbd>chevron_right</kbd> a handful of times → event index increments, plot re-renders (debounced).
- Click <kbd>chevron_left</kbd> down to 0 → stays at 0 (no error toast).
- Click **Full procedure** → stepper disables; caption persists.
- Click **Single event** → stepper re-enables, caption resets to the value's index/count.
- Load a second exam (multi-file upload) → selector appears; pick Exam #2 → caption re-labels to `"Event <n> / <count> · Exam #2"`.
- Toggle **Show all exams in preview** → caption suffix becomes `"· all exams"`.
- `geom_event_input` typing still debounces.

**Automated (optional but recommended):
- Extend `tests/gui/test_gui_flows.py` or add `tests/gui/test_geometry_stepper.py` with the `user` fixture:
  - Load the example via `ctx.load_example` or by calling the upload handler directly.
  - Assert `geom_event_context` text contains `"/ <count>"` after clicking **Single event**.
  - Assert the number input's `disable` prop toggles true/false across the three mode buttons.
  - Assert chevron clicks increment the number input's value (or the context label updates).

### Phase 3 — Trace-count guard documentation

**File:** `src/mypyskindose/gui/geometry_preview.py`. Pure comment additions, no tests.

**Acceptance:** `ruff check`; `basedpyright`; `python scripts/check_file_sizes.py` still under 800 line cap for both files.

### Phase 4 — Help sync + registry

**Files:** `docs/source/gui_help/geometry_workflow.md`, `src/mypyskindose/gui/help/geometry_workflow.md` (mirror), `dev-docs/help_registry.json`, `dev-docs/feature_doc_matrix.json`, `dev-docs/ui_copy.json`, `CHANGELOG.md`, `AGENTS.md`.

**Acceptance:**
- `python scripts/sync_gui_help.py` updates the mirror (verify with `git status`).
- `python scripts/check_help_registry.py` green.
- `python scripts/check_ui_copy.py` green (chevron buttons don't need `copy_text` entries — they're icon buttons; any tooltip text would, but we're not adding tooltips here).
- `python scripts/check_feature_doc_matrix.py` green.
- `python scripts/check_doc_freshness.py` green.

---

## Out of scope

- Adding a second event-level **slider** control (the Plotly procedure plot already has one for `plot_procedure` mode; adding a NiceGUI slider for `plot_event` would duplicate the chevron stepper's purpose and add visual clutter).
- A trace-count guard for `plot_event` mode (not needed — one event per render — see Part III doc).
- Per-exam **statistics** in the stepper caption (event-level dose, kVp, DAP). That's a Results/Data-table feature, not a Geometry positioning tool.
- Persisting `geom_event_input` across reloads beyond the existing one-time auto-init (`last_load_signature` nudge re-fires on new load; the user's chosen event reverts to the middle of the new dataset, which is the correct behavior — pinning across completely different files would be confusing).
- Changes to `make_geometry_fig`, `create_geometry_plot`, `plot_procedure`, or the Plotly procedure-mode slider. No signature or behavioral change in the plotting layer.

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| `geometry.py` approaches 800-line cap | Estimated ~760 lines post-implementation. If review pushes over, extract the four stepper closures (`_step`, `_set_stepper_enabled`, `_update_event_context`, `_render_event_preview_debounced`) into `geometry_preview.py` (199 → ~240), passing widget refs through `AppState` or `PageContext`. Document the move in `dev-docs/CODEBASE_OVERVIEW.md`. |
| NiceGUI `user` fixture can't easily simulate typing in `ui.number` | The chevron buttons are clickable via `await user.click(...)`; the typing path is validated manually. Keep automated assertions on the chevron buttons + the caption text, not on typed input. |
| Caption flashes 0 / 0 before load | Existing auto-init already handles this (the caption only fires when `rdsr_df is not None`). `_update_event_context` guards are explicit: `count == 0` yields the empty-slice placeholder, and the stepper is disabled. |
| User toggles composite mid-step | `_on_composite_toggle` already calls `_update_preview_caption`; we add a `_update_event_context()` call there. The clamping logic in `_refresh_geometry_sliders` already re-clamps `geom_event_input` on a composite change (`clamp_geometry_event_index(..., composite=composite)`). Net effect: the index is clamped to the new slice's count and the caption relabels. |

---

## Exit criteria

- [ ] Phase 1 unit tests green; `event_context_caption` shipped.
- [ ] Phase 2 stepper row shipped; manual matrix below passes; optional `test_geometry_stepper.py` green.
- [ ] Phase 3 comment block shipped; file-size check green.
- [ ] Phase 4 help + registry checks green; `CHANGELOG.md` and `AGENTS.md` updated.
- [ ] `python scripts/check_doc_freshness.py` green.
- [ ] Archive this plan under `dev-docs/plans/archive/`; update `dev-docs/index.md` and `dev-docs/TO_DO.md` (check off the item).
- [ ] `TO_DO.md` other related items reviewed for accuracy: "Multi-exam manual smoke check" still separate; "Expanded RDSR browser" stays in backlog (still out of scope for this plan).

---

## Manual matrix

| ID | Assert |
|----|--------|
| S1 | Single-exam load → stepper disabled initially; click **Single event** → caption shows `"Event <mid> / <count>"`; stepper enabled. |
| S2 | Chevron right 5 times → index +5, plot re-renders each step (debounced). Chevron left to 0, then again → stays 0 (no error). |
| S3 | Click **Setup view** → stepper disables; caption persists. Click **Single event** → re-enables, caption re-syncs. |
| S4 | Click **Full procedure** → stepper disables; Plotly slider remains usable. |
| S5 | Multi-exam: select Exam #2 → caption suffix becomes `"· Exam #2"`; slice count updates to that exam's events. |
| S6 | Toggle **Show all exams in preview** → caption suffix becomes `"· all exams"`; slice count becomes total. |
| S7 | Type a large number directly into `geom_event_input` → clamped to `count - 1` on next refresh; caption shows clamped value. |
| S8 | 0 events (e.g. clear the upload) → caption `"Event 0 / 0"`, stepper disabled. |

---

## Validation commands (run after each phase)

```bash
# Lint + typecheck (from repo root)
ruff check src/mypyskindose/gui/tabs/geometry.py src/mypyskindose/gui/geometry_preview.py
basedpyright src/mypyskindose/gui/

# File size (geometry.py must stay under 800)
python scripts/check_file_sizes.py

# Help sync + registry checks (after Phase 4)
python scripts/sync_gui_help.py
python scripts/check_help_registry.py
python scripts/check_ui_copy.py
python scripts/check_feature_doc_matrix.py
python scripts/check_doc_freshness.py

# Unit tests
pytest tests/unittests/test_gui_multi_exam_geometry_offsets.py -v
pytest tests/unittests/test_gui_part_v_formatters.py -v

# Optional GUI smoke (requires `pip install -e '.[gui]'`)
pytest tests/gui/ -v
```

---

## Related

- [MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md](MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md) — source of the per-exam foundation this plan builds on.
- [archive/DOSE_MAP_PER_EXAM_CHECKBOX_PLAN.md](archive/DOSE_MAP_PER_EXAM_CHECKBOX_PLAN.md) — sibling TO_DO item (completed) that added per-exam dose-map controls in the Results tab.
- [TO_DO.md](../TO_DO.md) — origin item.
- `docs/source/gui_help/geometry_workflow.md` — help file updated in Phase 4.
