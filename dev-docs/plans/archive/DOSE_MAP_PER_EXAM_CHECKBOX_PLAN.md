# Dose Map Per-Exam Checkbox Controls Plan

> **TO_DO item:** "Dose map per-exam checkbox controls — show cumulative dose or selected exam subsets and update PSD/dose map live."
>
> **Prerequisite context:** [MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md](../MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md) Parts I–V shipped. Multi-exam Results accordion + popup single-exam dose map dialog shipped (`results.py:176-316`). This plan adds inline per-exam dose map visibility controls.

**Plan status:** Completed — 2026-07-11.

---

## Objective

In multi-exam Results, let users toggle individual exam dose maps inline (via checkboxes in the per-exam accordion) and show either the **aggregate cumulative** dose map or a **selected-exam subset** dose map in the main aggregate plot area. PSD and dose map should update live to reflect the selected subset.

### What exists today

| Surface | Location | Behavior |
|---------|----------|----------|
| Cumulative dose map (single-exam) | `results.py:62-113` | One `ui.plotly` from `state.output` |
| Aggregate dose map (multi-exam) | `results.py:164-168` | One `ui.plotly` from `res.aggregate_dose_map` — always all exams, no subset |
| Per-exam popup dialog | `results.py:275-316` | Modal `ui.dialog` with one `ui.plotly` per call, `>10 exams` disables button |
| Per-exam accordion | `results.py:176-215` | `ui.expansion` per exam showing PSD/AirKerma/Events + "Show Dose Map" button |

### What this plan adds

1. A **checkbox** in each per-exam accordion expansion: "Show inline" (default unchecked).
2. When checked, an **inline `ui.plotly`** renders inside that expansion (500px height), populated by the same `make_dosemap_fig(explicit_dose_map, explicit_patient)` API already used by the popup.
3. A **"Visible exams" selector** above the aggregate dose map (checkboxes or a "Select all / none" toggle) that controls whether the aggregate plot shows **all exams** (default) or a **subset**. The subset is the sum of dose maps for the selected exams, with PSD recomputed live.
4. A **memory guard** capping simultaneously-visible inline maps (default 5; configurable in `AppState`).

### What this plan does NOT add

- Per-exam event stepping within dose maps (separate TO_DO item: "Geometry tab per-exam event selection").
- Changes to the calculation pipeline — the dose maps already exist in `MultiExamResult.exams[i].output`; this is pure UI layering.
- Changes to the export pipeline — export still uses the full aggregate. (Future: export selected subset.)

---

## Architecture

### Data flow

```
MultiExamResult (state.multi_exam_result)
  .exams[i].output.to_dict()      →  per-exam dose_map + patient dict
  .aggregate_dose_map             →  all-exams sum (existing)
  .aggregate_psd                   →  all-exams PSD (existing)

New: subset dose map = sum(exams[i].output.dose_map for i in selected_indices)
New: subset PSD = max(subset dose map)
```

Per-exam dose map extraction is already proven in `_show_exam_dosemap_dialog` (`results.py:284-292`): read `output.to_dict()["dose_map"]` (list of `[index, dose]` pairs), reconstruct into a zero array sized by `patient_skin_cells`. The same extraction will be factored into a reusable helper.

### State placement

Per the exploration findings, checkbox state should live in `AppState` (not closure locals) because the accordion is rebuilt by timer on each `calc_run_id` bump (`results.py:265-268`), which would discard closure-local state.

New `AppState` fields:

```python
# Per-exam dose map visibility (multi-exam Results)
visible_exam_dosemaps: list[bool] = field(default_factory=list)  # inline checkbox per exam
aggregate_subset_exams: list[bool] = field(default_factory=list)  # subset selector per exam
```

Both are re-seeded to `[False] * n_exams` / `[True] * n_exams` when a new `MultiExamResult` arrives (accordion rebuild). The `reset_results()` function should also clear them.

**Why two lists, not one:** Inline visibility ("show this exam's dose map in its expansion") and aggregate subset selection ("include this exam in the subset aggregate plot") are independent concerns. A user may want to see exam #2's dose map inline while keeping the aggregate plot showing all exams. Conflating them would force "deselect from aggregate" whenever they toggle inline visibility.

### Memory guard

| Threshold | Behavior |
|-----------|----------|
| `> 10 exams` | Existing popup "Show Dose Map" button disabled (already shipped) |
| `> MAX_INLINE_MAPS (5)` inline checkboxes checked | Disable remaining unchecked checkboxes + tooltip: "Close other inline maps to view more (max 5 simultaneously)" |
| Subset aggregate always available | No cap — it's a single plotly figure re-rendered on each toggle |

---

## Implementation context (read before coding)

> These notes pin conventions a less familiar implementer must follow to match the existing codebase.

### NiceGUI checkbox event API

This codebase uses **`on_value_change`** (not `.on("update:model-value", ...)`):

```python
# CORRECT (matches geometry.py:651, settings.py:216)
checkbox = ui.checkbox("label", value=False)
checkbox.on_value_change(handler)  # handler receives e with e.value: bool

# ALSO CORRECT — bind_value for state-driven checkboxes:
ui.checkbox("label", value=state.some_bool).bind_value(state, "some_bool")

# WRONG — this plan's earlier draft used .on("update:model-value", ...); do NOT use that
```

For reference, see `geometry.py:198-201` (creation) and `geometry.py:651` (handler wiring). The handler's `e.value` is `True`/`False`.

### Import conventions

- `results.py` currently imports `make_dosemap_fig` from `..figures` (line 14). After Phase 1, also import `extract_exam_dose_map` from the same module.
- New constant `MAX_INLINE_MAPS` goes in `src/mypyskindose/gui/constants.py` (after line 33, `GEOMETRY_DEBOUNCE_SEC`).
- `results.py` imports constants via `from ..constants import COLORSCALES` (line 12). Add `MAX_INLINE_MAPS` to this import.
- `copy_text` is imported from `..ui_copy` — see `_per_exam.py:196` for the pattern: `from ..ui_copy import copy_text`.
- **Do not** add `numpy` at module level in `results.py` or `figures.py` — the existing code imports it locally inside functions (e.g., `results.py:277` `import numpy as np`). Match this pattern.

### `ui_copy.json` and `check_ui_copy.py` constraints

The `check_ui_copy.py` script (run in CI) enforces:
1. Every `copy_text("key")` call in `src/mypyskindose/gui/**/*.py` must have a matching key in `dev-docs/ui_copy.json`.
2. The `owner` field must point to a real file (prefixed with `src/` or relative to `src/mypyskindose/`).
3. The catalog `text` value must **NOT** appear as a literal string in the owner file — use `copy_text("key")` to retrieve it programmatically, never hardcode the literal.

This means: when you add a checkbox label like "Show inline dose map", register it in `ui_copy.json` and in code write `copy_text("results.inline_dosemap.checkbox.label")`, **not** the literal string.

However: checkbox labels passed as the first positional arg to `ui.checkbox(...)` are currently NOT checked by `check_ui_copy.py` (it only scans for `copy_text()` calls). The existing codebase passes literal strings to `ui.checkbox` (see `settings.py:216`, `geometry.py:198`). **Follow the existing pattern: use literal strings for checkbox labels. Only use `copy_text()` for tooltips.**

### `results.py` structure — indentation and closure scope

All functions in `results.py` (`_refresh_metrics`, `_refresh_dosemap`, `_build_multi_exam_accordion`, `_show_exam_dosemap_dialog`, etc.) are **nested inside `build(ctx)`** — they are closures. UI-callback closures (`_render_inline_dosemap`, `_refresh_aggregate_dosemap_subset`, `_set_subset_all`) must be defined inside `build(ctx)` to access `agg_dosemap_plot`, `agg_psd_metric`, etc. via closure. **However, pure-logic functions (`compute_subset_aggregate`, `can_show_more_inline`) SHOULD be module-level** (outside `build()`) so they're unit-testable without the NiceGUI runtime. See "Module-level extraction for testability" in the Testing section.

### Accordion rebuild lifecycle

`_build_multi_exam_accordion(res)` is called from `_refresh_multi_exam_results()` (line 267) which runs on a `ui.timer(1.5, ...)` loop (line 273). The rebuild only fires when `multi_exam_results_ui_stale(last_rendered_run_id, state.calc_run_id)` returns True — i.e., on a new calculation. After rebuild, `last_rendered_run_id` is set to the current `calc_run_id`, so subsequent timer ticks are no-ops.

This means:
- Checkbox widgets are **created fresh** on each rebuild (state values persist in `AppState`, but the widget objects are new).
- The `value=state.visible_exam_dosemaps[i]` initialization on the checkbox ensures newly-created widgets reflect persisted state.
- The `subset_checkboxes` list (Phase 4) must be rebuilt in the same lifecycle — store references during `_build_multi_exam_accordion` or a parallel builder.

### Where to add the subset selector (Phase 4)

The subset selector card is not in the accordion — it's a **separate static card** placed in the multi-exam section of `results.py`, between the "Per-Exam Results" accordion (line 160) and the "Aggregate Dose Map" heading (line 164). Its per-exam checkboxes should be populated during `_refresh_multi_exam_results` (same lifecycle as the accordion) so exam count changes are reflected. Store the `subset_checkboxes: list` as a closure-local variable (like `last_rendered_run_id`) — repopulate it when the accordion rebuilds.

### `PySkinDoseOutput` — the per-exam output object

Each `res.exams[i].output` is a `PySkinDoseOutput` instance (see `format_export_data.py`). Its `.to_dict()` returns a dict with keys including:
- `"dose_map"`: list of `[index, dose]` pairs (only irradiated cells)
- `"patient"`: dict with key `"patient"` containing `{"patient_skin_cells": {"x": [...], "y": [...], "z": [...]}, "triangle_vertex_indices": {"i": [...], "j": [...], "k": [...]}}`
- `"corrections"`: dict of correction factor lists

The patient mesh (skin cells) is the **same mesh** for all exams in a multi-exam run — only the dose values differ. This is why the aggregate is a simple element-wise sum.

### Test fixture location

Multi-exam tabular fixture: `tests/fixtures/tabular_inputs/normalized_events_multistudy.csv` (used in `test_multi_exam_gui.py`). This is the existing 2-exam fixture. For dose-map computation tests, mock `PySkinDoseOutput` with `types.SimpleNamespace` + `MagicMock` (pattern from `test_multi_exam_gui.py:68-71`).

### Validation commands to run after each phase

```bash
# Lint + typecheck (from repo root)
ruff check src/mypyskindose/gui/tabs/results.py src/mypyskindose/gui/figures.py src/mypyskindose/gui/state.py src/mypyskindose/gui/constants.py
basedpyright src/mypyskindose/gui/

# File size check (results.py must stay under 800 lines)
python scripts/check_file_sizes.py

# UI copy validation (after Phase 5)
python scripts/check_ui_copy.py

# Help registry validation (after Phase 5)
python scripts/check_help_registry.py

# Feature doc matrix (after Phase 5)
python scripts/check_feature_doc_matrix.py

# GUI help sync (after Phase 5)
python scripts/sync_gui_help.py

# Tests (GUI tests require: pip install -e '.[gui]')
pytest tests/gui/test_gui_results_refresh.py -v
pytest tests/gui/ -k "dosemap or subset or inline" -v

# Full GUI test suite
pytest tests/gui/ -v
```

---

## Phases

> **Execution order:** Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5. Each phase is independently testable. Commit after each phase (Phase 1–4 can be separate commits, Phase 5 is a doc commit). Run `ruff check` + `basedpyright` + `python scripts/check_file_sizes.py` after every phase; run the full `pytest tests/gui/` suite after Phases 3 and 4.

### Phase 1: Reusable per-exam dose map extraction helper

**Goal:** Factor the dose-map array reconstruction out of `_show_exam_dosemap_dialog` into a reusable function.

**File:** `src/mypyskindose/gui/figures.py`

Add:

```python
def extract_exam_dose_map(exam_output) -> tuple[np.ndarray, dict]:
    """Extract (dose_map_array, patient_dict) from a PySkinDoseOutput.

    Returns the dose-map as a zero-padded ndarray sized to the patient skin
    cells, and the patient dict suitable for ``make_dosemap_fig``.
    """
    import numpy as np
    output_dict = exam_output.to_dict()
    patient_for_fig = output_dict["patient"]
    patient_data = patient_for_fig["patient"]
    num_cells = len(patient_data["patient_skin_cells"]["x"])
    dose_map = np.zeros(num_cells)
    for idx, dose in output_dict["dose_map"]:
        dose_map[int(idx)] = dose
    return dose_map, patient_for_fig
```

Refactor `_show_exam_dosemap_dialog` to call `extract_exam_dose_map` instead of inlining the same logic.

**Acceptance:** Existing popup behavior unchanged. `results.py:284-292` replaced with one call to `extract_exam_dose_map`.

### Phase 2: AppState fields + reset/clear

**File:** `src/mypyskindose/gui/state.py`

Add fields:

```python
visible_exam_dosemaps: list[bool] = field(default_factory=list)
aggregate_subset_exams: list[bool] = field(default_factory=list)
```

Update `reset_results()`:

```python
state.visible_exam_dosemaps = []
state.aggregate_subset_exams = []
```

**Seed on new calc result:** In `_refresh_multi_exam_results` (`results.py:238-272`), when `multi_exam_results_ui_stale` triggers an accordion rebuild, re-seed:

```python
n = len(res.exams)
if len(state.visible_exam_dosemaps) != n:
    state.visible_exam_dosemaps = [False] * n
if len(state.aggregate_subset_exams) != n:
    state.aggregate_subset_exams = [True] * n
```

**Acceptance:** Fields exist, are cleared on `reset_results()`, re-seeded on new `calc_run_id`. No visible behavior change yet.

### Phase 3: Inline per-exam dose map checkbox + plot

**File:** `src/mypyskindose/gui/tabs/results.py` — `_build_multi_exam_accordion`

Inside each `ui.expansion` (after the metrics row and the existing "Show Dose Map" popup button), add:

Use a closure-local `dict` (not `container.props`) to track whether a container has been rendered — NiceGUI element `.props` is a string, not a dict. The existing popup uses a plain `ui.timer(0.1, ..., once=True)` for deferred rendering — match that pattern.

```python
# Closure-local render-tracking dict: {exam_idx: True} once rendered
_inline_rendered: dict[int, bool] = {}
```

**Checkbox + container creation (inside each `ui.expansion`):**

```python
with ui.row().classes("w-full items-center gap-2 q-mt-sm"):
    inline_cb = ui.checkbox(
        "Show inline dose map",
        value=state.visible_exam_dosemaps[i] if i < len(state.visible_exam_dosemaps) else False,
    ).classes("text-sm")

# Inline plot slot (hidden until checkbox is on)
inline_plot_container = ui.column().classes("w-full")
inline_plot_container.visible = bool(inline_cb.value)
```

**Checkbox handler (use `on_value_change`, not `.on(...)`):**

```python
def _on_inline_toggle(e, idx=i, cb=inline_cb, container=inline_plot_container):
    is_on = bool(e.value)
    state.visible_exam_dosemaps[idx] = is_on
    container.visible = is_on

    if not is_on:
        # Uncheck: clear the plot to free memory, mark as needing re-render
        container.clear()
        _inline_rendered.pop(idx, None)
        return

    # Memory guard: cap simultaneously-visible inline maps
    visible_count = sum(state.visible_exam_dosemaps)
    if visible_count > MAX_INLINE_MAPS:
        cb.set_value(False)
        state.visible_exam_dosemaps[idx] = False
        container.visible = False
        ui.notify(
            f"Max {MAX_INLINE_MAPS} inline maps simultaneously. "
            "Close another first.",
            color="warning",
        )
        return

    # Render only if not already rendered in this accordion lifecycle
    if not _inline_rendered.get(idx):
        _render_inline_dosemap(idx, container)

inline_cb.on_value_change(_on_inline_toggle)
```

**Inline render function (deferred via `ui.timer(once=True)`, matching the popup at line 316):**

```python
def _render_inline_dosemap(exam_idx: int, container) -> None:
    res = state.multi_exam_result
    if res is None or exam_idx >= len(res.exams):
        return
    with container:
        spinner = ui.spinner(size="md", color="indigo").classes("absolute-center")
        plot = ui.plotly({}).classes("w-full").style("height:500px")
    _inline_rendered[exam_idx] = True

    async def _build(
        _idx=exam_idx, _plot=plot, _spinner=spinner
    ):
        from nicegui import run
        dose_map, patient_dict = extract_exam_dose_map(res.exams[_idx].output)
        fig = await run.io_bound(make_dosemap_fig, dose_map, patient_dict)
        _spinner.visible = False
        if fig:
            _plot.update_figure(fig)

    ui.timer(0.1, _build, once=True)
```

**Constant:** Add `MAX_INLINE_MAPS = 5` to `src/mypyskindose/gui/constants.py` (after line 33, `GEOMETRY_DEBOUNCE_SEC`). Import it in `results.py` alongside `COLORSCALES`.

**Acceptance:** In multi-exam Results, checking "Show inline dose map" on an exam expansion shows a 500px Plotly figure inline. Unchecking hides and clears it. Checking more than 5 simultaneously is blocked with a warning toast. Re-calc resets all checkboxes to unchecked.

### Phase 4: Aggregate subset selector

**File:** `src/mypyskindose/gui/tabs/results.py` — multi-exam section, above the aggregate dose map

> **Placement:** Insert this card between the per-exam accordion container (line 161) and the "Aggregate Dose Map" heading (line 164). It is a **static** widget — build it once in `build(ctx)`, not in `_build_multi_exam_accordion`.

Add a closure-local list for checkbox references (like `last_rendered_run_id`):

```python
subset_checkboxes: list = []  # closure-local; repopulated during accordion build
```

Add the subset selector card:

```python
with ui.card().classes("w-full modern-card q-pa-md"):
    ui.label("Visible exams in aggregate plot").classes("text-subtitle2 q-mb-sm")
    with ui.row().classes("w-full items-center gap-2"):
        ui.button("All", on_click=lambda: _set_subset_all(True)).classes("modern-btn size-sm")
        ui.button("None", on_click=lambda: _set_subset_all(False)).classes("modern-btn size-sm")
    subset_checkboxes_container = ui.column().classes("w-full gap-1")
```

> **Per-exam subset checkboxes** are populated inside `_build_multi_exam_accordion` (or a dedicated `_build_subset_checkboxes(res)` called right after `_build_multi_exam_accordion` in `_refresh_multi_exam_results`). They must be rebuilt on each `calc_run_id` change so the exam count stays in sync. After building, set each checkbox's value from `state.aggregate_subset_exams[i]` and wire `on_value_change`.

**Building subset checkboxes (call from `_refresh_multi_exam_results`, right after `_build_multi_exam_accordion(res)`):**

```python
def _build_subset_checkboxes(res) -> None:
    subset_checkboxes.clear()
    subset_checkboxes_container.clear()
    with subset_checkboxes_container:
        for i, exam_res in enumerate(res.exams):
            cb = ui.checkbox(
                f"Exam {i + 1}",
                value=state.aggregate_subset_exams[i] if i < len(state.aggregate_subset_exams) else True,
            ).classes("text-sm")
            cb.on_value_change(lambda e, idx=i: _on_subset_toggle(e, idx))
            subset_checkboxes.append(cb)
```

**Subset computation:** When `aggregate_subset_exams` changes, recompute the aggregate dose map from only the selected exams. > **Define `compute_subset_aggregate` as a module-level function** (outside `build()`) so it's unit-testable without the NiceGUI runtime — see "Module-level extraction for testability" in the Testing section. The closure inside `build()` calls it:

```python
# Module-level in results.py (outside build()) — testable without NiceGUI
def compute_subset_aggregate(res, selected_mask: list[bool]) -> tuple:
    """Sum dose maps for selected exams. Returns (combined_ndarray, subset_psd) or (None, 0.0)."""
    import numpy as np
    from ..figures import extract_exam_dose_map
    selected_indices = [i for i, s in enumerate(selected_mask) if s]
    if not selected_indices:
        return None, 0.0
    # All exams share the same patient mesh dimensions, so use the first selected
    first_output = res.exams[selected_indices[0]].output.to_dict()
    patient_data = first_output["patient"]["patient"]
    num_cells = len(patient_data["patient_skin_cells"]["x"])
    combined = np.zeros(num_cells)
    for idx in selected_indices:
        dose_map, _ = extract_exam_dose_map(res.exams[idx].output)
        combined += dose_map  # element-wise sum
    subset_psd = float(np.max(combined)) if combined.size else 0.0
    return combined, subset_psd
```

**Update aggregate plot on subset change:**

```python
def _refresh_aggregate_dosemap_subset():
    res = state.multi_exam_result
    if res is None:
        return
    if all(state.aggregate_subset_exams):
        # Full aggregate (existing path)
        _refresh_aggregate_dosemap(res)
        agg_psd_metric.set_text(f"{res.aggregate_psd:.2f} mGy")
    else:
        combined, subset_psd = compute_subset_aggregate(res, state.aggregate_subset_exams)
        if combined is None:
            agg_dosemap_plot.update_figure({})
            agg_psd_metric.set_text("— mGy (no exams selected)")
            return
        first_exam_patient = res.exams[0].output.to_dict()["patient"]
        fig = make_dosemap_fig(explicit_dose_map=combined, explicit_patient=first_exam_patient)
        if fig:
            agg_dosemap_plot.update_figure(fig)
        agg_psd_metric.set_text(f"{subset_psd:.2f} mGy (subset)")
```

**Per-exam subset checkbox handler:**

```python
def _on_subset_toggle(e, idx):
    state.aggregate_subset_exams[idx] = bool(e.value)
    _refresh_aggregate_dosemap_subset()
```

**"All"/"None" buttons:**

```python
def _set_subset_all(value: bool):
    n = len(state.aggregate_subset_exams)
    # Refill in-place (not reassign) so existing list references in state stay valid
    for i in range(n):
        state.aggregate_subset_exams[i] = value
    for cb in subset_checkboxes:
        cb.set_value(value)
    _refresh_aggregate_dosemap_subset()
```

> **Important:** `set_value()` on a checkbox whose value is already the target **fires `on_value_change`** in NiceGUI. To avoid a cascade of redundant `_refresh_aggregate_dosemap_subset()` calls when "All"/"None" iterates all checkboxes, either: (a) use a closure-local `_suppress_subset_refresh = False` flag that `_on_subset_toggle` checks and `_set_subset_all` sets True during iteration then calls `_refresh_aggregate_dosemap_subset()` once at the end, or (b) accept the redundancy (it's cheap — the subset computation is fast for typical exam counts). Option (b) is acceptable for simplicity.

**Acceptance:**
- Aggregate dose map plot shows all exams by default (unchanged behavior).
- Toggling per-exam subset checkboxes recomputes the aggregate plot to show only selected exams.
- PSD label updates to show subset PSD (labeled "(subset)") or reverts to aggregate PSD when all are selected.
- "All" / "None" buttons set all checkboxes and refresh.
- Re-calc resets subset to all-True.

### Phase 5: Results help, UI copy, and doc updates

**Files to update:**

1. `docs/source/gui_help/results_workflow.md` — add a section describing the per-exam checkbox controls, inline dose maps, and aggregate subset selector. Run `python scripts/sync_gui_help.py` to mirror to `src/mypyskindose/gui/help/`.

2. `dev-docs/ui_copy.json` — add new UI copy keys. **Note:** `check_ui_copy.py` validates that every `copy_text("key")` call in the GUI source has a matching key here, and that the catalog `text` does NOT appear as a literal string in the owner file. The existing codebase passes literal strings for checkbox labels (not via `copy_text`), so checkbox labels are NOT registered here. Only add entries for text you retrieve via `copy_text()` — see `_per_exam.py:196` for the pattern. For this feature, if you add tooltips (e.g., on the "All"/"None" buttons or a max-inline-maps warning tooltip), register those. The toast message text for the memory guard is passed as a literal to `ui.notify(...)` and does not need a `copy_text` entry (matching the existing `ui.notify` usage in `results.py:281` which also passes a literal).

```json
"results.subset.all.tooltip": {
  "text": "Include all exams in the aggregate dose map",
  "owner": "gui/tabs/results.py"
},
"results.subset.none.tooltip": {
  "text": "Clear all exams from the aggregate dose map",
  "owner": "gui/tabs/results.py"
}
```

> Only add these if you actually call `copy_text("results.subset.all.tooltip")` etc. in code. If you use literal strings for the tooltips (matching the existing `btn.tooltip(...)` pattern at `results.py:212`), do NOT register them — the validator only checks `copy_text()` calls.

3. `dev-docs/help_registry.json` — no new entry needed (`results` already covers `results.py`).

4. `dev-docs/feature_doc_matrix.json` — add a `dose_map_per_exam` feature entry:

```json
"dose_map_per_exam": {
  "status": "shipped",
  "code": ["src/mypyskindose/gui/tabs/results.py", "src/mypyskindose/gui/figures.py"],
  "tests": ["tests/gui/test_results_per_exam_dosemap.py"],
  "docs": ["dev-docs/FEATURE_INVENTORY.md", "AGENTS.md"],
  "help": ["docs/source/gui_help/results_workflow.md"]
}
```

5. `dev-docs/FEATURE_INVENTORY.md` — add entry under GUI/Results.

6. `AGENTS.md` — update the "Current development focus" §3 to note per-exam dose map checkboxes shipped.

---

## Testing

> **Test location:** All tests go in `tests/gui/` (they import `mypyskindose.gui.*` which requires the `gui` extra). The core CI matrix runs without `gui`, and `tests/gui/conftest.py` auto-skips when NiceGUI is absent. Follow the mocking patterns in `test_multi_exam_gui.py` (mock `PySkinDoseOutput` via `SimpleNamespace`/`MagicMock`) and `test_gui_results_refresh.py` (test pure-logic helpers without the NiceGUI runtime).

### Unit tests (`tests/gui/test_results_per_exam_dosemap.py`)

1. **`test_extract_exam_dose_map`** — create a mock `PySkinDoseOutput` (use `SimpleNamespace(to_dict=MagicMock(return_value={...}))` with a small `dose_map` list and `patient_skin_cells` dict), call `extract_exam_dose_map`, and verify the returned ndarray has the expected nonzero entries at the right indices and zeros elsewhere.

2. **`test_subset_aggregate_computation`** — create a mock `MultiExamResult` with 3 exams, each having a dose map with known values. Call `compute_subset_aggregate` (module-level function) with `[True, False, True]`. Verify the result equals the element-wise sum of exams 0 and 2 only.

3. **`test_subset_psd`** — same mock; verify `subset_psd` equals `max(combined_dose_map)`.

4. **`test_state_reset_clears_checkbox_state`** — create an `AppState`, set `visible_exam_dosemaps = [True, False]` and `aggregate_subset_exams = [False, True]`, call `reset_results()`, assert both lists are empty.

5. **`test_memory_guard_caps_inline_maps`** — this tests the guard logic (count of `visible_exam_dosemaps` > `MAX_INLINE_MAPS` blocks). Test the counting logic directly, not the NiceGUI widget interaction. Write a simple helper function `_can_show_more_inline(visible: list[bool]) -> bool` and test it: 5 True → False, 4 True → True.

6. **`test_subset_all_none_refills_in_place`** — create an `AppState` with `aggregate_subset_exams = [True, False, True]`. Simulate the `_set_subset_all(False)` logic (refill in place). Verify all entries are False and the list identity didn't change (same object reference).

### GUI smoke test (`tests/gui/`)

7. **`test_results_per_exam_dosemap_smoke`** — requires NiceGUI `user` fixture. Build a multi-exam Results page, verify the accordion has per-exam expansions with checkboxes. Click an inline checkbox and verify a `ui.plotly` element appears. Click a subset checkbox and verify the aggregate plot updates. > **Note:** The `user` fixture from NiceGUI is registered in `tests/conftest.py` (per `tests/gui/conftest.py:6-8`). Use `user = await ...

### Module-level extraction for testability

For the subset computation to be unit-testable without the NiceGUI runtime, define it as a **module-level function** in `results.py` (or a new `gui/tabs/_results_helpers.py`), not a closure:

```python
# Module-level (outside build()) — testable without NiceGUI
def compute_subset_aggregate(res, selected_mask: list[bool]) -> tuple:
    """Sum dose maps for selected exams. Returns (combined_ndarray, subset_psd) or (None, 0.0)."""
    import numpy as np
    from ..figures import extract_exam_dose_map
    selected_indices = [i for i, s in enumerate(selected_mask) if s]
    if not selected_indices:
        return None, 0.0
    first_output = res.exams[selected_indices[0]].output.to_dict()
    patient_data = first_output["patient"]["patient"]
    num_cells = len(patient_data["patient_skin_cells"]["x"])
    combined = np.zeros(num_cells)
    for idx in selected_indices:
        dose_map, _ = extract_exam_dose_map(res.exams[idx].output)
        combined += dose_map
    subset_psd = float(np.max(combined)) if combined.size else 0.0
    return combined, subset_psd
```

Then the closure inside `build()` calls `compute_subset_aggregate(res, state.aggregate_subset_exams)`. Do the same for any guard logic:

```python
# Module-level — testable
def can_show_more_inline(visible: list[bool]) -> bool:
    return sum(visible) < MAX_INLINE_MAPS
```

### Manual validation (not automated)

8. Verify inline dose maps render correctly for 2-exam and 3-exam multi-exam RDSR files.
9. Verify subset PSD is lower than aggregate PSD when a subset is selected.
10. Verify re-calc after changing offsets resets checkboxes and inline plots.

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Inline rendering of N dose maps blocks the event loop | Each render uses `run.io_bound(make_dosemap_fig, ...)` (already proven in popup). The memory guard caps at 5. |
| `results.py` grows past 800-line limit | Current: 316 lines. Estimated addition: ~150 lines. Total: ~466 — well under 800. If it approaches the limit, extract subset/inline helpers into `gui/tabs/_results_helpers.py`. |
| Subset dose map sum assumes all exams share the same patient mesh dimensions | This is already true for the existing aggregate (`res.aggregate_dose_map` is computed from the same mesh). Add an assertion in `compute_subset_aggregate` that selected exams have matching cell counts. |
| Checkbox state lost on accordion rebuild | State lives in `AppState`, re-seeded during rebuild. `_build_multi_exam_accordion` reads `state.visible_exam_dosemaps[i]` and `state.aggregate_subset_exams[i]` to initialize checkbox values. |
| Inline plot not cleared on uncheck, consuming memory | Uncheck handler calls `container.clear()` and removes from `_inline_rendered` dict. |

---

## Progress log

| Date | Phase | Status |
|------|-------|--------|
| 2026-07-11 | Draft | Plan written |

---

## Decision log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-07-11 | State in `AppState`, not closure locals | Accordion is rebuilt by timer on each `calc_run_id` bump; closure locals would be lost. |
| 2026-07-11 | Two separate lists (inline visibility vs subset selection) | Independent concerns — a user should be able to see exam #2 inline without removing it from the aggregate. |
| 2026-07-11 | Memory guard at 5 inline maps | Existing popup cap is 10 exams (one-at-a-time). Inline maps exist simultaneously, so 5 is a conservative default. |
| 2026-07-11 | Subset PSD = max of summed dose maps | Matches the existing aggregate PSD definition (`aggregate_psd` is the max of the combined dose map). |
| 2026-07-11 | Subset selector as separate card above aggregate plot | Keeps inline visibility and subset selection independent; avoids cluttering accordion rows. |
| 2026-07-11 | Inline dose maps show full phantom (no auto-zoom) | Matches existing popup behavior; consistency across views. |
| 2026-07-11 | Keep popup "Show Dose Map" button alongside inline checkbox | Popup offers a larger distraction-free view; inline is for quick side-by-side comparison. |

---

## Resolved questions

1. **Subset selector placement:** Separate card above the aggregate plot (avoids cluttering accordion rows; keeps inline visibility and subset selection as independent controls).
2. **Inline dose map zoom:** Full phantom view (matches the existing popup behavior).
3. **Popup button alongside inline checkbox:** Keep both — the popup offers a larger, distraction-free view; the inline checkbox is for quick side-by-side comparison.
