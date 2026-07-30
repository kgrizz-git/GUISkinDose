# Geometry Tab Per-Exam Event Selection Plan

> **TO_DO item:** *"Geometry tab per-exam event selection — let users select or step through events per exam; account for Plotly trace count and large datasets."*
>
> **Prerequisite context:** [MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md](MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md) Parts I–V shipped. The Geometry tab already has an exam selector (`geometry.py:188-192`), a bare `ui.number` event input (`geometry.py:395-397`), preview slicing (`geometry_preview.py:78-95`), event clamping (`geometry_preview.py:161-178`), three preview-mode buttons, a composite toggle (`geometry.py:198-201`), and a composite-only live-pause threshold (30 events pause / 100 spinner) at `geometry_preview.py:181-199` and `geometry.py:497-500`. **Single-exam and non-composite `plot_procedure` are currently unguarded** (see Part III). This plan is a UX/polish layer on that foundation — no new architecture, plus a small behavior extension to the trace-count guard.
>
> **Index-number convention:** Internal dataframe indexing and 0-based Python functions remain 0-based (`0 .. N-1`). The user-facing `geom_event_input` value and stepper caption are **1-based** (`1 .. N`, where `1` is the first event of `N`). Consumers feeding `make_geometry_fig` convert the 1-based input value to a 0-based internal index via `max(0, int(geom_event_input.value or 1) - 1)`.

**Plan status:** Draft — 2026-07-11. Revised 2026-07-12 (v5) incorporating Option A (1-based user input box), offset-slider reactive re-render clarification, and regression-fix CHANGELOG framing.

---

## Objective

Make per-exam event stepping in the Geometry tab feel natural and informative, without re-architecting the multi-exam plumbing that already works. Concretely:

1. Replace the bare number box with a **stepper row** showing context (`"Event 6 / 23 · Exam #2"`) and a labeled prev/next control.
2. Keep the event index usable only for the **Single event** preview mode (the input is meaningless in Setup/Full-procedure modes).
3. **Extend the existing trace-count live-pause guard** so single-exam and non-composite multi-exam `plot_procedure` also pause for large event counts, and document where the guard lives so future editors extend it rather than re-create it.
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
| Live-pause thresholds | `geometry_preview.py:181-199` + `geometry.py:497-500` | `composite_live_preview_paused` pauses `plot_procedure` above 30 **composite** events only; `geometry.py:498` (composite) and `geometry.py:500` (single-exam) show the spinner above 100. **Single-exam and non-composite multi-exam `plot_procedure` are NOT paused** — see Part III for the extension. |
| Auto-init middle event | `geometry.py:143-151, 684-692` | First time the tab is opened for a fresh load, default to the middle event of the active slice; one-time per load signature |

### Why the foundation is good enough

- The selector + slice + clamp chain already answers the per-exam question. When the user picks Exam #2, `preview_event_count(state, active_exam_index=1)` returns that exam's event count, `geom_event_input` is clamped, and `_render_preview("plot_event")` feeds the right slice into `make_geometry_fig`.
- `make_geometry_fig` already threads `active_exam_index` and `composite` through to `rdsr_df_for_geometry_preview` and `effective_patient_offset_for_preview`. No signature change needed.
- The existing 30/100 composite thresholds are **part of** the "Plotly trace count" guard the TO_DO calls out. They are composite-only today; Part III extends the 30-event live-pause to single-exam and non-composite multi-exam `plot_procedure` so large datasets are honored in all `plot_procedure` paths.

---

## Gaps this plan closes

| Gap | Current | Target |
|-----|---------|--------|
| **A. Context label** | `geom_event_input` shows a bare number; the user has to look elsewhere to know how many events are in the slice or which exam they're looking at. | A caption next to the input: `"Event <n> / <count> · Exam #<m>"` (or no exam suffix in single-exam mode; "(composite)" suffix when `Show all exams in preview` is on). |
| **B. Stepper buttons** |	User must type into the number box and press Enter; there's no prev/next affordance. | <kbd>Prev</kbd> / <kbd>Next</kbd> buttons (or chevron icons) that step by one, clamping at the ends (no error toast — just stop at 0 / count−1). |
| **C. Mode awareness** | `geom_event_input` is always enabled even though it only affects `plot_event` mode; in `plot_setup` / `plot_procedure` its value is ignored, which can confuse users. | Disable the stepper (input + prev/next) unless `last_preview_mode == "plot_event"`. Re-enable when the user clicks **Single event**. The existing buttons keep setting `last_preview_mode`; the stepper becomes a "focused" control for that mode. |
| **D. Trace-count guard extension + documentation** | The 30/100 thresholds at `geometry_preview.py:181-199` and `geometry.py:497-500` are composite-only. **Single-exam and non-composite multi-exam `plot_procedure` are unpaused**, even though `plot_procedure.py:65-84` builds one trace set per event regardless of composite flag. This is the "large datasets" gap the TO_DO calls out. | (1) Extend the live-pause guard so single-exam and non-composite multi-exam `plot_procedure` pause above the same 30-event threshold. (2) Add a comment block above `composite_live_preview_paused` (renamed `procedure_live_preview_paused`) calling out the guard's location and scope. (3) Leave `plot_event` mode unguarded — one event per render, so the trace set is small and fixed. |
| **E. Help-file wording** | `geometry_workflow.md:28` tells users to "Enter an event number"; no mention of prev/next or the context caption. | One or two lines updated to mention the stepper and the "disabled until Single event is clicked" behavior. |

---

## Part I — Event-context helper (pure logic)

**File:** `src/mypyskindose/gui/geometry_preview.py`

Add a small module-level helper (no NiceGUI dependency, unit-testable in isolation). The caption is **1-based** for display while `current_index` (the underlying `geom_event_input` value) stays 0-based — matches the convention documented in `NO_PATIENT_INTERSECTION_WARNING_PLAN.md` line 124.

```python
def event_context_caption(
    state: AppState,
    *,
    current_index: int,
    active_exam_index: int | None = None,
    composite: bool = False,
) -> str:
    """User-facing 1-based caption for the Geometry event stepper row.

    ``current_index`` is the 0-based internal value; the returned label adds 1
    so "Event 1 / N" means the first of N events. Matches the convention in
    NO_PATIENT_INTERSECTION_WARNING_PLAN.md line 124 (0-based storage, 1-based UX).
    Checks ``composite`` to choose between the "Exam #N" and "all exams" suffixes
    when ``state.is_multi_exam`` is true.

    Examples (current_index shown in parens, output in quotes):
      single-exam, 23 events, current_index 5   -> "Event 6 / 23"
      multi-exam exam #2 (idx 1), 7 events, current_index 3 -> "Event 4 / 7 · Exam #2"
      multi-exam composite, 51 events, current_index 9     -> "Event 10 / 51 · all exams"
      empty slice, current_index 0              -> "Event 0 / 0"
    """
    count = preview_event_count(
        state, active_exam_index=active_exam_index, composite=composite
    )
    safe_idx = clamp_geometry_event_index(
        state, current_index,
        active_exam_index=active_exam_index, composite=composite,
    )
    if count <= 0:
        return "Event 0 / 0"
    display_idx = safe_idx + 1
    if state.is_multi_exam:
        if composite:
            return f"Event {display_idx} / {count} · all exams"
        exam_num = (active_exam_index if active_exam_index is not None
                    else state.active_exam_index or 0) + 1
        return f"Event {display_idx} / {count} · Exam #{exam_num}"
    return f"Event {display_idx} / {count}"
```

**Why module-level:** mirrors `clamp_geometry_event_index` and `preview_event_count`, which are already module-level and tested via `test_gui_multi_exam_geometry_offsets.py` and `test_gui_part_v_formatters.py`.

**Edge cases:**
- `count == 0` (empty slice): caption returns `"Event 0 / 0"` as a placeholder. Note that at initial `build()` time the caption starts as `""`; the `"Event 0 / 0"` placeholder string is produced on the next refresh hook (`_update_event_context`) when `count <= 0` before data is loaded. The stepper is also disabled (Part II-B).
- `current_index` out of range: `clamp_geometry_event_index` clamps it to `[0, count-1]`; the caption displays the clamped-position-plus-one, never the raw input. The stepper's `_step` uses the same clamp.
- The `count <= 0` short-circuit returns early so we never render `"Event 1 / 0"` for an empty slice (which would look like a bug).

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
                current = int(geom_event_input.value or 1)
                new_idx = min(max(1, current + delta), max(1, count))
                geom_event_input.set_value(new_idx)
                # If NiceGUI fires on_value_change on programmatic set_value,
                # the handler below re-schedules a render. Either path is fine:
                # the debounce collapses duplicates (only the last schedule
                # in the GEOMETRY_DEBOUNCE_SEC window renders). See Part II-C.
                if not _value_change_fires_on_set_value:
                    _render_event_preview_debounced()

            prev_btn = ui.button(
                icon="chevron_left",
                on_click=lambda: _step(-1),
            ).props("flat dense round size=sm color=grey-5").mark("geom-event-prev")
            geom_event_input = ui.number(
                value=1, min=1, step=1
            ).classes("w-20 mono-text").props("dense flat").mark("geom-event-input")
            next_btn = ui.button(
                icon="chevron_right",
                on_click=lambda: _step(1),
            ).props("flat dense round size=sm color=grey-5").mark("geom-event-next")
        geom_event_context = ui.label("").classes(
            "text-caption text-grey-5 q-mt-xs"
        ).mark("geom-event-context")
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

**Closure scope & variable binding:** `prev_btn`, `next_btn`, `geom_event_input`, and `geom_event_context` are assigned to local variables inside `build()`. The helper closures (`_step`, `_set_stepper_enabled`, `_update_event_context`, `_render_event_preview_debounced`, `_preview_slice_count`) are also defined inside `build()` after the widgets are created so they can reference these elements directly along with `last_preview_mode`. Every element includes a `.mark(...)` annotation so automated GUI tests can select them by element identifier.

### II-B. Disable stepper when not in `plot_event` mode

Add a helper to toggle the three stepper widgets together. Use `set_enabled` on all three widgets cleanly (`ui.number` inherits `set_enabled` from the NiceGUI base element):

```python
def _set_stepper_enabled(enabled: bool) -> None:
    geom_event_input.set_enabled(enabled)
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
- `_refresh_geometry_sliders()` → call `_set_stepper_enabled(last_preview_mode == "plot_event")` and `_update_event_context()` after the existing `clamp_geometry_event_index` block. Note: because `_refresh_geometry_sliders()` auto-initializes `last_preview_mode = "plot_event"` on first Geometry tab open after data load (`geometry.py:684-692`), this automatically enables the stepper when the tab first renders single-event mode. It is disabled again if the user switches to Setup view or Full procedure.
- **At the very end of `build()`** (after `ctx.refresh_geometry_tab = _refresh_geometry_sliders` and `_update_preview_caption()` at `geometry.py:712`), add an explicit `_set_stepper_enabled(False)` call so the stepper starts disabled at initial empty-tab render before data is loaded.

### II-C. Render on step (debounced) and `on_value_change` handler

`_render_event_preview_debounced()` is a thin wrapper around `_schedule_debounced_render()` that also ensures `last_preview_mode = "plot_event"` (so a step while the preview was cleared re-arms it). Re-use the existing debounce; do **not** add a new timer.

```python
def _render_event_preview_debounced() -> None:
    nonlocal last_preview_mode
    if last_preview_mode != "plot_event":
        last_preview_mode = "plot_event"
    _update_event_context()
    _schedule_debounced_render()
```

Add the same `_update_event_context()` call to `_on_exam_select_change` and `_on_composite_toggle` so the caption re-labels when the user switches exam or toggles composite.

**New `on_value_change` handler:** the current `geom_event_input` at `geometry.py:395-397` has no `on_value_change`. We add a new handler so typing into the box re-displays the caption live (even before render) and schedules a debounced render. Wire the handler after the input element is created, in the same place as the other `on_value_change` wirings for `patient_sliders` (`geometry.py:534-535`) and `table_sliders` (`geometry.py:383`):

```python
def _on_event_input_change(_e) -> None:
    if last_preview_mode != "plot_event":
        return
    _update_event_context()
    _schedule_debounced_render()

geom_event_input.on_value_change(_on_event_input_change)
```

**`set_value` / `on_value_change` assumption:** NiceGUI's `on_value_change` typically fires only on user input, not on programmatic `set_value`. The `_step` closure in Part II-A guards with `_value_change_fires_on_set_value` so both code paths schedule a render exactly once. Note that `_value_change_fires_on_set_value` is a performance optimization (avoiding duplicate debounced schedule), not a correctness gate: because the debounce window collapses multiple schedules inside the same timer window, any duplicate schedule is safely masked.

```python
# Resolved once at import. NiceGUI's on_value_change for ui.number fires
# on user input by convention, not on programmatic set_value.
# Performance guard: if True, _step skips its own debounced render call so only
# on_value_change schedules the debounced render. Either path is safe under debounce.
_value_change_fires_on_set_value: bool = False
```

Place this module-level constant near the top of `geometry.py` (e.g., after the `_GE_WARNING_TOKEN` constant at `geometry.py:56`).

> **Implementation verification check:** Before starting Phase 2, empirically verify NiceGUI's `on_value_change` behavior on programmatic `set_value` and note that `_refresh_geometry_sliders` calls `set_value` twice during auto-init. Our debounce timer safely collapses any resulting schedules to a single render.

### II-D. File-size check and helper placement

- `geometry.py` is at **712 lines**. Cap is **800**, no whitelist (`scripts/check_file_sizes.py`).
- Net additions if all closures stay in `geometry.py`: ~78 lines added post-implementation, putting `geometry.py` around ~790 lines.
- **Primary architecture decision:** To keep `geometry.py` comfortably under the 800-line cap (~775 lines or fewer) and make helper functions independently unit-testable, extract `_preview_slice_count`, `_set_stepper_enabled`, `_update_event_context`, and `_render_event_preview_debounced` into `geometry_preview.py` accepting widget references if `geometry.py` exceeds 775 lines during drafting.

`geometry_preview.py` is at **199 lines**; adding `event_context_caption` puts it at ~219. Well within cap.

---

## Part III — Extend and document the trace-count guard

**File:** `src/mypyskindose/gui/geometry_preview.py` (rename `composite_live_preview_paused` → `procedure_live_preview_paused`), `src/mypyskindose/gui/tabs/geometry.py` (update one call site).

### The gap (assessment #2)

`composite_live_preview_paused` at `geometry_preview.py:181-199` returns `False` early in three cases:

```python
if last_preview_mode != "plot_procedure" or not state.is_multi_exam:
    return False
...
if not composite:
    return False
```

This means **single-exam `plot_procedure` and non-composite multi-exam `plot_procedure` are never paused**, even though `plot_procedure.py:65-84` iterates `range(len(data_norm))` and builds one mesh dict per event regardless of the composite flag. The trace set grows linearly with total event count in **all** `plot_procedure` paths, not just the composite one. The earlier draft of this plan claimed single-exam procedure "builds a small trace set (one trace-set per event but patient-inclusion is gated separately)" — **that claim was wrong.** The `include_patient` gate at `create_geometry_plot.py:77` only drops the patient mesh above `max_events_for_patient_inclusion` (default 10); table, pad, beam, and detector traces still scale with event count.

### The extension (option (a) from the assessment)

Rename and generalize the guard so single-exam and non-composite multi-exam `plot_procedure` also pause for large counts:

```python
def procedure_live_preview_paused(
    state: AppState,
    *,
    last_preview_mode: str | None,
    composite_preview: bool,
    last_table_origin_scrub: bool,
    pause_threshold: int = 30,
) -> bool:
    """True when plot_procedure live preview should show the PAUSED badge.

    Pause policy applies to ALL plot_procedure paths, not only composite:
    plot_procedure.py builds one trace set per event regardless of composite
    flag, so the figure grows linearly with total event count in every path.
    (Earlier `composite_live_preview_paused` was composite-only — see the
    comment block above this function.)
    """
    if last_preview_mode != "plot_procedure":
        return False
    if state.is_multi_exam:
        composite = resolve_composite_for_render(
            composite_preview=composite_preview,
            last_table_origin_scrub=last_table_origin_scrub,
        )
        active_idx = state.active_exam_index
        count = preview_event_count(
            state, active_exam_index=active_idx, composite=composite
        )
    else:
        # Single-exam branch: call preview_event_count(state), which lives in
        # this same module (geometry_preview.py:98) and returns len(state.rdsr_df)
        # for single-exam slices without introducing import cycles.
        count = preview_event_count(state)
    return count > pause_threshold
```

**Call-site update in `geometry.py`** (`live_preview_allowed` at lines 440-450):

```python
def live_preview_allowed() -> bool:
    if state.busy:
        return False
    if procedure_live_preview_paused(
        state,
        last_preview_mode=last_preview_mode,
        composite_preview=composite_preview,
        last_table_origin_scrub=last_table_origin_scrub,
    ):
        return False
    return True
```

**Also update the import in `geometry.py` inside the `from ..geometry_preview import` block (currently lines 19–27)** (replace `composite_live_preview_paused` → `procedure_live_preview_paused`).

### Rename blast radius

The definition lives in `geometry_preview.py:181`, but the name is re-exported through `helpers.py`:

| File | Line / Block | Change |
|------|--------------|--------|
| `src/mypyskindose/gui/geometry_preview.py` | 181 | rename definition |
| `src/mypyskindose/gui/tabs/geometry.py` | 19–27 (`from ..geometry_preview import` block) | update import |
| `src/mypyskindose/gui/tabs/geometry.py` | 443 | update call site in `live_preview_allowed` |
| `src/mypyskindose/gui/helpers.py` | 47 | update the `from .geometry_preview import … composite_live_preview_paused,` line |
| `src/mypyskindose/gui/helpers.py` | 79 | update the entry inside `__all__ = […]` |
| `tests/unittests/test_gui_multi_exam_geometry_offsets.py` | 15 | update import |
| `tests/unittests/test_gui_multi_exam_geometry_offsets.py` | 234 | rename test fn `test_composite_live_preview_paused_only_for_large_composite_procedure` → `test_procedure_live_preview_paused_only_for_large_composite_procedure` (or split into the new tests below) |
| `tests/unittests/test_gui_multi_exam_geometry_offsets.py` | 240, 246, 252 | update each call site |

`geometry.py:28`'s `from ..helpers import …` does not reference this name (it's imported directly from `geometry_preview` at lines 19–27). Note that `helpers.py:47` and `79` must be updated in lockstep so module-load does not fail with an `ImportError`. Run `grep -rn composite_live_preview_paused src tests` before committing the rename to confirm there are no remaining call sites.

### Why `preview_procedure()` must render even when paused (assessment v2 #2 — critical)

The current `preview_procedure()` at `geometry.py:602-612` gates the render on `live_preview_allowed()`:

```python
async def preview_procedure() -> None:
    ...
    last_preview_mode = "plot_procedure"
    live_preview_requested = True
    if live_preview_allowed():
        await _render_preview("plot_procedure")
    else:
        _update_paused_badge()
```

So for any paused procedure (composite > 30 today; single-exam > 30 after this plan, plus non-composite multi-exam > 30), clicking **Full procedure** shows only the PAUSED badge and renders **no figure** — meaning there is no Plotly procedure-mode slider to drag. Manual matrix row M2 ("drag the Plotly procedure-mode slider") and the Behavior change summary ("the once-per-click Full procedure render still works") **cannot both be true under the current gating**.

The plan's intent — *pause live reactive refresh, but let an explicit click render once* — requires a one-line behavior change so the explicit-click path renders regardless of pause. This also fixes a pre-existing *composite* limitation that quietly shipped (composite procedures with >30 events currently show only the badge and never render a figure; users would have to subdivide the slice to see anything).

### `preview_procedure()` — render on explicit click (option (a))

Change `preview_procedure()` so the explicit click still renders, while the *reactive* refresh paths (slider drag) continue to respect the pause:

```python
async def preview_procedure() -> None:
    nonlocal last_preview_mode, live_preview_requested
    if state.rdsr_df is None:
        ui.notify("Load data first", type="warning")
        return
    last_preview_mode = "plot_procedure"
    live_preview_requested = True
    # Always render the once-per-click figure; the embedded Plotly procedure-mode
    # slider lets the user scrub client-side without re-rendering. The live-pause
    # guard (procedure_live_preview_paused) only gates reactive update paths
    # (_schedule_debounced_render -> _render_preview) so offset-slider adjustments
    # on a >30-event procedure do not trigger expensive live re-renders. The badge
    # still shows so the user knows live-refresh is paused; the figure underneath
    # it is the cached click-render.
    await _render_preview("plot_procedure")
    _update_paused_badge()
```

`preview_setup()` and `preview_event()` keep their existing `if live_preview_allowed():` gate — only `preview_procedure()` is un-gated, because only `plot_procedure` has a Plotly-side slider that lets the user switch events without re-rendering.

### Updated Behavior change summary

| Mode | Before (today, composite-only pause) | After (this plan) |
|------|--------------------------------------|---------------------|
| `plot_setup` | No pause, click renders | No change — pause does not apply |
| `plot_event` | No pause, click renders | No change — pause does not apply |
| `plot_procedure`, ≤30 events | Click renders, no badge, offset-slider edits re-render live | No change |
| `plot_procedure`, >30 events, **composite** | Click renders **no figure** (only PAUSED badge) (today's quiet limitation) | **Regression fix & new behavior** — click renders the figure (with badge shown), offset-slider reactive refresh is paused; user navigates events via embedded client-side Plotly slider |
| `plot_procedure`, >30 events, **single-exam or non-composite multi-exam** | Never paused — click renders, offset-slider edits re-render live | **New pause** — click renders the figure (with badge shown), offset-slider reactive refresh paused; user navigates events via embedded client-side Plotly slider |

The "**only the reactive refresh is throttled**" promise now holds for every `plot_procedure` path, including the >30-event case. This fixes the quiet pre-existing composite limitation as a side effect of the plan's central goal.

> **Alternative (b)** considered and rejected — keeping the current gating and downgrading the user-facing text would extend a pre-existing composite limitation to **more** procedures rather than fixing it. Option (a) closes both the new gap and the existing one at the cost of one behavior tweak.

### Spinner at 100 events (already correct scope)

The spinner gate at `geometry.py:498` (`geom_spinner.visible = count > 100`, composite) and `geometry.py:500` (`geom_spinner.visible = event_count() > 100`, single-exam) is **already single-exam-aware** — both paths show the spinner independently of `live_preview_allowed()`. No change needed.

### Comment block (replaces the earlier "documentation only" version)

Add above `procedure_live_preview_paused`:

```python
# ────────────────────────────────────────────────────────────────────
# Performance guard: this is the "Plotly trace count" mitigation
# referenced in dev-docs/TO_DO.md ("account for Plotly trace count and
# large datasets").
#
# Scope: ALL plot_procedure live previews — single-exam, multi-exam
# non-composite, and multi-exam composite. In every one of these paths
# make_geometry_fig -> plot_procedure builds one trace set per event
# (plot_procedure.py:65-84), so the figure grows linearly with the
# active slice's event count.
#
# We pause live preview above 30 events so patient/table offset-slider
# adjustments while in Full-procedure mode do not trigger expensive
# reactive re-renders, and show the large-data spinner above 100
# (geometry.py:498 for composite count, geometry.py:500 for single-exam).
#
# plot_event mode does NOT need this guard — exactly one event per render,
# so the trace set is small and fixed regardless of slice size.
# plot_setup mode renders no events.
#
# If you add a new preview path that grows traces per event, extend
# `procedure_live_preview_paused` rather than adding a sibling guard.
# ────────────────────────────────────────────────────────────────────
```

### Tests

Add the following seven cases to `tests/unittests/test_gui_multi_exam_geometry_offsets.py` (or a new `test_gui_part_vi_procedure_pause.py` if the file grows past 800 lines):

- `test_procedure_pause_single_exam_large` — 1 exam, 50 events, `last_preview_mode="plot_procedure"` → `procedure_live_preview_paused(...)` returns `True`.
- `test_procedure_pause_single_exam_small` — 1 exam, 10 events → returns `False`.
- `test_procedure_pause_multi_exam_non_composite_large` — multi-exam, non-composite, active slice has 40 events → returns `True`.
- `test_procedure_pause_multi_exam_composite_large` — multi-exam, composite, 51 events → returns `True` (regression case for the pre-rename behavior).
- `test_procedure_pause_plot_event_never_pauses` — `last_preview_mode="plot_event"`, any count → returns `False`.
- `test_procedure_pause_plot_setup_never_pauses` — `last_preview_mode="plot_setup"`, 100 events → returns `False`.
- `test_procedure_pause_threshold_param` — passing `pause_threshold=15` overrides the default 30.

If the existing `test_composite_live_preview_paused_*` tests (in the same file, after the rename) refer to the old name, update them to call `procedure_live_preview_paused` and add a deprecation/redirect note if you prefer to keep the old function as a thin wrapper — but a clean rename is simpler given the small call-site count (only `geometry.py:live_preview_allowed` and a few tests).

---

## Part IV — Help file update

**File:** `docs/source/gui_help/geometry_workflow.md`

Replace "Step 1: Select an Event" (lines 27-29) and extend the Controls table (lines 63-67). New step wording (assessment #3 — the **caption is 1-based**; the number typed into the input box is still 0-based because the input controls internal indexing):

> ### Step 1: Select an Event
> 1. Click **Single event** under the geometry plot to enter single-event mode. The **Event selection** stepper (the number box with chevron buttons) becomes enabled; the small caption shows your position as `Event <n> / <count>` (single-exam) or `Event <n> / <count> · Exam #<m>` (multi-exam, or `· all exams` when **Show all exams in preview** is on). The caption is **1-based** — `Event 1 / 23` is the first of 23 events.
> 2. Use the chevron buttons to step forward or back, or type an event number into the box (the box accepts 0-based indices — `0` is the first event — to match the way PySkinDose labels events internally; the 1-based caption above the box is the user-facing label).
> 3. In **multi-exam** mode the default slice is the **selected exam** only unless **Show all exams in preview** is enabled. Use the exam selector above the preview controls to pick which exam you are stepping through.

> **Live-preview pause:** for large procedures, the plot may show a **PAUSED** badge while you drag the procedure-mode slider — this is the performance guard described in [Trace-count guard](#). It fires above 30 events in **any** `Full procedure` path (single-exam or multi-exam, composite or not); you can still click **Full procedure** once and use the Plotly slider to step through the cached figure.

Add to the Controls table:

> | **Event selection stepper** | Jump to a specific event within the current preview slice (prev / next or typed number). Disabled unless **Single event** mode is active. The caption is 1-based; the typed number is 0-based. |

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

**Tests** (pure logic, no NiceGUI; caption is 1-based):
- `test_event_context_caption_single_exam` — 1 exam, 23 events, `current_index=5` (0-based) → `"Event 6 / 23"` (1-based display of the 6th event).
- `test_event_context_caption_multi_exam_active` — 2 exams, active 1 (i.e. Exam #2), slice has 7 events, `current_index=3` → `"Event 4 / 7 · Exam #2"`.
- `test_event_context_caption_multi_exam_composite` — composite, 51 events, `current_index=9` → `"Event 10 / 51 · all exams"`.
- `test_event_context_caption_clamps_out_of_range_index` — `current_index=999`, 7-event slice → `"Event 7 / 7 · Exam #2"` (clamped to last valid index, displayed 1-based).
- `test_event_context_caption_empty_slice` — no events → `"Event 0 / 0"` (placeholder; stepper disabled, so this state is only visible before the user loads data).

Fixture pattern matches the existing tests in `test_gui_multi_exam_geometry_offsets.py:107` (which already builds a 2-exam `AppState` with `rdsr_df` mock + `EXAM_INDEX_COLUMN`). Reuse that fixture.

**Acceptance:** `pytest tests/unittests/test_gui_multi_exam_geometry_offsets.py -q` green; `basedpyright` clean.

### Phase 2 — Stepper row UI + enable/disable wiring

**File:** `src/mypyskindose/gui/tabs/geometry.py`.

**Acceptance (manual):**
- `python -m mypyskindose --mode gui`, load one example RDSR and open the Geometry tab.
- Confirm auto-init automatically sets single-event mode and enables the stepper; caption reads `"Event <middle> / <count>"`.
- Click <kbd>chevron_right</kbd> a handful of times → event index increments, plot re-renders (debounced).
- Click <kbd>chevron_left</kbd> down to 0 → stays at 0 (no error toast).
- Click **Full procedure** → stepper disables; caption persists.
- Click **Single event** → stepper re-enables, caption resets to the value's index/count.
- Load a second exam (multi-file upload) → selector appears; pick Exam #2 → caption re-labels to `"Event <n> / <count> · Exam #2"`.
- Toggle **Show all exams in preview** → caption suffix becomes `"· all exams"`.
- `geom_event_input` typing still debounces.

**Automated (optional but recommended):**
- Extend `tests/gui/test_gui_flows.py` or add `tests/gui/test_geometry_stepper.py` with the `user` fixture:
  - Load the example via `ctx.load_example` or by calling the upload handler directly.
  - Assert `geom_event_context` text contains `"/ <count>"` after clicking **Single event** or auto-init.
  - Assert the number input's `disable` prop toggles true/false across the three mode buttons.
  - Assert chevron clicks increment the number input's value (or the context label updates).
  - Add a focused unit/GUI assertion pinning `_value_change_fires_on_set_value` behavior against the installed NiceGUI version.

### Phase 3 — Extend and document the trace-count guard; render-on-click

**Files:**
- `src/mypyskindose/gui/geometry_preview.py` — rename `composite_live_preview_paused` → `procedure_live_preview_paused`, generalize to all `plot_procedure` paths, add the comment block (see Part III).
- `src/mypyskindose/gui/tabs/geometry.py` — update import inside the `from ..geometry_preview import` block and call site in `live_preview_allowed`; also un-gate `preview_procedure()` so the explicit click renders even when paused.
- `src/mypyskindose/gui/helpers.py` — update the import at line 47 and the `__all__` entry at line 79. Without this, `helpers.py` raises `ImportError` at module load and the GUI breaks.
- `tests/unittests/test_gui_multi_exam_geometry_offsets.py` — update the import at line 15, rename `test_composite_live_preview_paused_only_for_large_composite_procedure` → `test_procedure_live_preview_paused_*`, update call sites at lines 240/246/252, and add the seven new tests from Part III's Tests section.

This phase is a behavior change, not just documentation. See Part III for the full spec, call site, tests, and `preview_procedure()` change. Run `grep -rn composite_live_preview_paused src tests` before committing to confirm no remaining references.

**Acceptance:**
- Unit tests from Part III all green: single-exam large (>30) pauses; single-exam small (≤30) does not; multi-exam non-composite large pauses; multi-exam composite large pauses; `plot_event` mode never pauses; `plot_setup` mode never pauses; `pause_threshold` kwarg override works.
- Existing `test_composite_live_preview_paused_*` tests passed-through or split into the new tests; renaming is mechanical per the blast-radius table.
- `grep -rn composite_live_preview_paused src tests` returns zero hits (the rename is complete).
- `ruff check`; `basedpyright`; `python scripts/check_file_sizes.py` still under the 800 line cap for both `geometry_preview.py` and `geometry.py`.
- **Manual matrix row M2** (new): load a single exam with >30 events, click **Full procedure** — confirm the figure renders AND the PAUSED badge appears. Drag the embedded Plotly procedure-mode slider — confirm the slider steps through the cached figure (no re-render thrash; the figure has been rendered once on click, so a slider is available). Repeat with a ≤30-event RDSR — confirm the figure renders, no PAUSED badge, slider-drag re-renders live.
- `CHANGELOG.md` gets a user-visible behavior-change line under a feature heading.

### Phase 4 — Help sync + registry

**Files:** `docs/source/gui_help/geometry_workflow.md`, `src/mypyskindose/gui/help/geometry_workflow.md` (mirror via `sync_gui_help.py`), `dev-docs/feature_doc_matrix.json`. `CHANGELOG.md` gets the Part III behavior-change note plus a Part IV help-text note; `AGENTS.md` needs no edit (no new tab or workflow surface is added; the stepper is a polish on the existing Geometry tab).

**Acceptance:**
- `python scripts/sync_gui_help.py` updates the mirror (verify with `git status`).
- `python scripts/check_help_registry.py` green.
- `python scripts/check_ui_copy.py` green (chevron buttons don't need `copy_text` entries — they're icon buttons; any tooltip text would, but we're not adding tooltips here).
- `python scripts/check_feature_doc_matrix.py` green.
- `python scripts/check_doc_freshness.py` green.

---

## Out of scope

- Adding a second event-level **slider** control (the Plotly procedure plot already has one for `plot_procedure` mode; adding a NiceGUI slider for `plot_event` would duplicate the chevron stepper's purpose and add visual clutter).
- A trace-count guard for `plot_event` mode (not needed — exactly one event per render — see Part III comment block).
- Per-exam **statistics** in the stepper caption (event-level dose, kVp, DAP). That's a Results/Data-table feature, not a Geometry positioning tool.
- Persisting `geom_event_input` across reloads beyond the existing one-time auto-init (`last_load_signature` nudge re-fires on new load; the user's chosen event reverts to the middle of the new dataset, which is the correct behavior — pinning across completely different files would be confusing).
- Changes to `make_geometry_fig`, `create_geometry_plot`, `plot_procedure`, or the Plotly procedure-mode slider. No signature or behavioral change in the plotting layer.
- Tuning the 30-event pause threshold / 100-event spinner threshold per dataset or letting users configure them. The defaults match the existing composite-exam thresholds. If a user reports a real smoothness complaint, swap the constant for an `AppState` field in a follow-up.

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| `geometry.py` approaches 800-line cap | Estimated ~760 lines post-implementation. If review pushes over, extract the four stepper closures (`_step`, `_set_stepper_enabled`, `_update_event_context`, `_render_event_preview_debounced`) into `geometry_preview.py` (199 → ~240), passing widget refs through `AppState` or `PageContext`. Document the move in `dev-docs/CODEBASE_OVERVIEW.md`. |
| NiceGUI `user` fixture can't easily simulate typing in `ui.number` | The chevron buttons are clickable via `await user.click(...)`; the typing path is validated manually. Keep automated assertions on the chevron buttons + the caption text, not on typed input. |
| Caption flashes 0 / 0 before load | Existing auto-init already handles this (the caption only fires when `rdsr_df is not None`). `_update_event_context` guards are explicit: `count == 0` yields the empty-slice placeholder, and the stepper is disabled. |
| User toggles composite mid-step | `_on_composite_toggle` already calls `_update_preview_caption`; we add a `_update_event_context()` call there. The clamping logic in `_refresh_geometry_sliders` already re-clamps `geom_event_input` on a composite change (`clamp_geometry_event_index(..., composite=composite)`). Net effect: the index is clamped to the new slice's count and the caption relabels. |
| **Phase 3 behavior change surprises users** (single-exam Full-procedure slider now pauses above 30 events) | Document in `CHANGELOG.md` under a clear heading. The explicit **Full procedure** click still renders the figure (Phase 3 un-gates `preview_procedure()` — see Part III); only the slider-drag reactive refresh is throttled, and the user can scrub the cached figure via the embedded Plotly procedure-mode slider. Users with ≤30 events see no change. **Also fixes a pre-existing composite limitation** where >30-event composite procedures previously showed only the PAUSED badge. If a user reports a workflow regression, raise the single-exam threshold via an `AppState` field in a follow-up (see Out of scope). |
| Existing tests call `composite_live_preview_paused` by name | The rename to `procedure_live_preview_paused` is mechanical (one call site in `geometry.py:live_preview_allowed` + the `helpers.py:47/79` re-export + tests at `test_gui_multi_exam_geometry_offsets.py:15, 234-252`). Update in lockstep with the Phase 3 commit per the blast-radius table in Part III. Run `grep -rn composite_live_preview_paused src tests` before committing to confirm zero remaining hits. If you prefer to leave the old name as a thin wrapper, do so in the same file with a `# Deprecated, use procedure_live_preview_paused.` comment — but a clean rename is simpler. |
| **`preview_procedure()` un-gating breaks the pause contract** | No: `_render_preview("plot_procedure")` still invokes `make_geometry_fig`, which builds the cached figure with the embedded Plotly procedure-mode slider. The pause still gates **reactive** update paths (`_schedule_debounced_render -> _do_debounced_render -> live_preview_allowed`). The badge still shows; the user sees the figure underneath it. The composite-only behavior that the plan extends (and pre-existing limitation that the plan closes) both work under this model. |

---

## Exit criteria

- [ ] Phase 1 unit tests green; `event_context_caption` shipped (caption uses 1-based display, internal storage remains 0-based).
- [ ] Phase 2 stepper row shipped; manual matrix below passes; optional `test_geometry_stepper.py` green; stepper starts disabled at initial empty-tab build time.
- [ ] Phase 3 trace-count guard extended to all `plot_procedure` paths (renamed `procedure_live_preview_paused`); `helpers.py:47/79` and tests at `test_gui_multi_exam_geometry_offsets.py:15, 234-252` renamed in lockstep; `grep -rn composite_live_preview_paused src tests` returns zero hits; `preview_procedure()` un-gated so the explicit click renders the figure even when paused (assessment v2 #2); Phase 3 unit tests green; comment block shipped; manual matrix row M2 green; file-size check green.
- [ ] Phase 4 help + registry checks green; `CHANGELOG.md` user-visible behavior-change note added; `AGENTS.md` not edited (no new tab/workflow added — see Phase 4 spec rationale).
- [ ] `python scripts/check_doc_freshness.py` green.
- [ ] Archive this plan under `dev-docs/plans/archive/`; update `dev-docs/index.md` and `dev-docs/TO_DO.md` (check off the item).
- [ ] `TO_DO.md` other related items reviewed for accuracy: "Multi-exam manual smoke check" still separate; "Expanded RDSR browser" stays in backlog (still out of scope for this plan).

### Suggested `CHANGELOG.md` entry

> **Geometry tab per-exam event selection** — Added a stepper with chevron prev/next + 1-based `Event <n> / <count> · Exam #<m>` caption so users know which event they are inspecting; the stepper disables outside Single-event mode. **Extended the trace-count live-pause guard** from composite-only to **all** `plot_procedure` paths (single-exam, multi-exam non-composite, multi-exam composite), so large single-exam procedures (>30 events) now pause the live reactive slider-drag refresh. **Fixed a pre-existing limitation** where >30-event composite procedures showed only the PAUSED badge with no figure: clicking **Full procedure** now always renders the figure (with the Plotly procedure-mode slider), and only the slider-drag-triggered live refresh is throttled. Setup view and Single-event mode are unchanged.

---

## Manual matrix

| ID | Assert |
|----|--------|
| S1 | Single-exam load and open Geometry tab → auto-init sets Single-event mode automatically; caption shows `"Event <mid> / <count>"` (1-based `mid` of `count`) and stepper is enabled. Click **Setup view** or **Full procedure** → stepper disables. |
| S2 | Chevron right 5 times → the internal 0-based `geom_event_input.value` increments by 5, but the caption displays `+5` from the starting 1-based label (e.g. starts at `Event 6 / 23`, becomes `Event 11 / 23`). Chevron left down to the first event → label stays at `"Event 1 / <count>"` (no error, no toast). |
| S3 | Click **Setup view** → stepper disables; caption persists. Click **Single event** → re-enables, caption re-syncs. |
| S4 | Click **Full procedure** → stepper disables; Plotly procedure-mode slider remains usable. |
| S5 | Multi-exam: select Exam #2 → caption suffix becomes `"· Exam #2"`; slice count updates to that exam's events. |
| S6 | Toggle **Show all exams in preview** → caption suffix becomes `"· all exams"`; slice count becomes total. |
| S7 | Type a large number directly into `geom_event_input` → clamped to `count - 1` (0-based) on next refresh; caption displays `"Event <count> / <count>"` (1-based of the last event). |
| S8 | 0 events (e.g. clear the upload) → caption `"Event 0 / 0"` (placeholder), stepper disabled. |
| M2 (new) | Load a single exam with >30 events (e.g. a large example RDSR), click **Full procedure** — confirm **both** that the figure renders AND the PAUSED badge shows (the un-gated explicit-click path is the v2 #2 fix). Drag the embedded Plotly procedure-mode slider — confirm you can step through events (cached figure, no re-render thrash). Repeat with a ≤30-event single-exam RDSR — confirm the figure renders, no PAUSED badge, slider-drag re-renders live. (Phase 3 behavior change.) |

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
- [archive/DOSE_MAP_PER_EXAM_CHECKBOX_PLAN.md](DOSE_MAP_PER_EXAM_CHECKBOX_PLAN.md) — sibling TO_DO item (completed) that added per-exam dose-map controls in the Results tab.
- [TO_DO.md](../../TO_DO.md) — origin item.
- `docs/source/gui_help/geometry_workflow.md` — help file updated in Phase 4.
