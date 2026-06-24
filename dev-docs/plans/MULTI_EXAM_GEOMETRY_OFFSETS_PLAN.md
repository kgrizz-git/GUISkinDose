# Multi-Exam Geometry Offsets Plan

> **Prerequisite:** [INTERACTIVE_TABLE_OFFSETS_PLAN.md](INTERACTIVE_TABLE_OFFSETS_PLAN.md) Phases 0–2b (single-exam Geometry sliders shipped in WIP).

**Execution order:** **Part I (commit)** → **Part II (Phase 0)** → **Part III (Phase 1)** → **Part IV (Phase 2)** + **Part V (cross-cutting)**. Grep **Appendix A (T-items)** while coding. **Checklist** and **Appendix B (testing)** are exit gates. Part VI is optional polish.

---

## Goal

In multi-exam mode, show Geometry offset sliders bound to **`loaded_exam_meta[active]`** (not globals), with an **Editing exam** selector and honest preview captions.

| Control | Single-exam (today) | Multi-exam (this plan) |
|---------|---------------------|-------------------------|
| Patient offset sliders | `state.d_lon/ver/lat` + meta sync | `meta[active].d_*` only |
| Table-origin sliders | `meta[0].table_origin_override` | `meta[active].table_origin_override` |
| Dose calculation | `analyze_data` + global offset | `analyze_multiple_exams` + per-exam meta (unchanged) |
| Geometry preview | One phantom + all events | See **Preview semantics** |

### Preview semantics

Two independent axes — do not use one `composite` flag for both:

| Axis | Default | Render param |
|------|---------|--------------|
| **Events** | Patient: active exam only; table-origin: **all exams** always | Patient: `composite_preview` toggle (default off). Table-origin scrub: `last_table_origin_scrub = True` → `_resolve_composite_for_render()` is `True` |
| **Phantom** | `meta[active]` patient offset | Always active exam |

Closure vars in `geometry.build`: `composite_preview` (user toggle, persists across exam switches); `last_table_origin_scrub` (set `True` on table-origin tick, `False` on patient tick / after debounced render); derive render flag via `_resolve_composite_for_render()` → passed to `make_geometry_fig` (see T8, T12, T27):

```python
def _resolve_composite_for_render() -> bool:
    if last_table_origin_scrub:
        return True
    return composite_preview
```

---

## Part I — Prerequisite commit (blockers + module split) ✅

**Status:** Completed 2026-06-24. One commit before Part II. Fixes CI file-size, loader meta seeding, and test regressions. No multi-exam Geometry UI yet — infrastructure only.

### Blockers (fix first)

| # | Issue | Action |
|---|--------|--------|
| B1 | T20 — `test_loader_seeds_offset_defaults_from_global` **failing** | Capture `prev_d_lon/ver/lat` before `reset_global_offsets_on_new_load` in `load_rdsr` / `load_tabular` |
| B2 | T21 — `helpers.py` **803 → 235 lines** after Part I split; CI passing | Module split below *(done)* |
| B3 | T25 — `_on_exam_offset_change` missing `ctx.refresh_per_exam()` | One line in `_per_exam.py` |
| B4 | 2 `test_gui_offset_reset.py` failures on patch target | Patch `mypyskindose.gui.offset_handlers.state`, not `helpers.state` |

### Module split

| Module | Owns |
|--------|------|
| `gui/settings_builder.py` | `build_settings`, `fallback_normalization_exam_count` |
| `gui/exam_transforms.py` | `EXAM_COLUMN`, `EXAM_INDEX_COLUMN`, `rebuild_rdsr_df`, `apply_exam_transforms`, transform helpers, `clear_multi_exam_state` |
| `gui/exam_loaders.py` | `load_rdsr`, `load_tabular`, `get_excel_sheets`, `_drop_exams_for_path` (with B1 fix) |
| `gui/offset_handlers.py` | Global offset reset/sync, table-origin stage/commit (already in WIP) |
| `gui/geometry_preview.py` | **Stub only** — helpers added in Part II |
| `gui/helpers.py` | Thin facade re-exporting public API + `run_calculation` remainder |

**Import rules (T24):** `exam_loaders` → `settings_builder` (not `helpers`). `offset_handlers` → `exam_transforms.apply_exam_transforms` (not `helpers`). `helpers` facade keeps `from mypyskindose.gui.helpers import …` working in tests/tabs.

**Steps:** B1–B4 → create modules above → move code → `helpers.py` <800 lines → validate → **commit**. *(Optional: two commits — hotfixes then split — if review surface is a concern.)*

```bash
python scripts/check_file_sizes.py
pytest tests/unittests/test_gui_offset_reset.py -q
pytest tests/unittests/test_multi_exam.py::TestGuiPerExamOffsets::test_loader_seeds_offset_defaults_from_global -q
pytest tests/unittests/test_gui_rdsr_df.py tests/unittests/test_multi_exam.py -q
pre-commit run --all-files
```

---

## Part II — Phase 0: Active exam index + preview helpers ✅

**Status:** Completed 2026-06-24. Ship 0.1–0.3 together.

**Files:** `state.py`, `geometry_preview.py`, `helpers.py` (re-exports), `figures.py`, `geometry.py`, `upload.py`.

### 0.1 Lifecycle + preview helpers (`geometry_preview.py`)

```python
def clamp_active_exam_index(state: AppState) -> None:
    n = len(state.loaded_exams)
    state.is_multi_exam = n > 1
    if n == 0:
        state.active_exam_index = None
    elif state.active_exam_index is None:
        state.active_exam_index = 0
    else:
        state.active_exam_index = min(state.active_exam_index, n - 1)

def adjust_active_exam_index_after_remove(state: AppState, removed_index: int) -> None:
    n = len(state.loaded_exams)
    state.is_multi_exam = n > 1
    if n == 0:
        state.active_exam_index = None
        return
    active = state.active_exam_index
    if active is None:
        state.active_exam_index = 0
        return
    if removed_index < active:
        state.active_exam_index = active - 1
    elif removed_index == active:
        state.active_exam_index = max(0, active - 1)
    state.active_exam_index = min(state.active_exam_index, n - 1)
```

- After `load_rdsr` / `load_tabular`: `len==1` → `active_exam_index=0`; else `clamp_active_exam_index`. When `is_multi_exam` flips: reset `composite_preview = False` if flipping to single-exam (T28). Loaders already seed `meta[i].d_lon/ver/lat` from pre-reset globals (Part I B1, `exam_loaders.py`); slider edits update meta in-place; `run_calculation` reads per-exam meta.
- `_remove_exam`: `adjust_active_exam_index_after_remove`; when `n==1`, `restore_globals_from_exam_meta` (T23). Preserve chain: `_remove_exam` → `_refresh_exams_table` → `ctx.refresh_per_exam` → `_refresh_geometry_sliders` (table + patient sync).
- `reset_results()`: do **not** clear `active_exam_index` (T2).

Also implement in `geometry_preview.py` (re-export from `helpers`):

```python
def effective_patient_offset_for_preview(
    state: AppState, active_exam_index: int | None = None
) -> tuple[float, float, float]:
    idx = active_exam_index if active_exam_index is not None else state.active_exam_index
    if state.is_multi_exam and idx is not None and idx < len(state.loaded_exam_meta):
        m = state.loaded_exam_meta[idx]
        return (float(m.get("d_lon", 0.0)), float(m.get("d_ver", 0.0)), float(m.get("d_lat", 0.0)))
    return (state.d_lon, state.d_ver, state.d_lat)

def rdsr_df_for_geometry_preview(state, *, active_exam_index=None, composite=False):
  # slice by EXAM_INDEX_COLUMN (int, 0-based) — not string prefix on EXAM_COLUMN (T18, T30)
  # .reset_index(drop=True); drop EXAM_INDEX_COLUMN + EXAM_COLUMN before plot (T1, T11)
  # from .exam_transforms import EXAM_COLUMN, EXAM_INDEX_COLUMN

def preview_event_count(state, *, active_exam_index=None, composite=False) -> int:
    df = rdsr_df_for_geometry_preview(state, active_exam_index=active_exam_index, composite=composite)
    return len(df) if df is not None else 0
```

### 0.2 Exam selector + banner (`geometry.py`, multi-exam only)

- Replace existing multi-exam banner with **Appendix B C1** (ships here, not Part III). Banner + exam selector: `visible iff is_multi_exam` (same parent column; collapse when 0 or 1 exam). Put selector inside banner block or share `bind_visibility_from(state, "is_multi_exam")`.
- `ui.select` below banner; options `{i: f"#{i+1} · {file}"}`; rebuild under `exam_selector_guard` (T9 — same `{"suppress": False}` pattern as `table_guard`; add one-line comment cross-referencing other guards).
- Handler: capture `old_index`; cancel pending debounce; if `table_origin_pending` → `commit_table_origin_transform(state, old_index)` (T15); set index; clamp; `last_table_origin_scrub = False`; sync sliders; schedule render if `last_preview_mode` set.
- **Empty state:** with 0 exams (`rdsr_df` None), no selector, no sliders; plot area empty — manual 0h.

### 0.3 Preview wiring (`figures.py` + `geometry.py`)

- `make_geometry_fig(mode, event_index, *, active_exam_index=None, composite=False)` — optional kwargs default so CLI `main()` path unchanged (N1); uses `rdsr_df_for_geometry_preview` + `effective_patient_offset_for_preview`; clamp events (T7); clear plot on `None` (T13). Thread args through all three `run.io_bound(make_geometry_fig, …)` call sites in `geometry.py`.
- `live_preview_allowed` / spinner: only when `is_multi_exam and _resolve_composite_for_render()` apply `preview_event_count(..., composite=True) > 30` pause and `> 100` spinner (T8, T27, N11). Single-exam and multi-exam non-composite: unchanged (no new pause).
- `_refresh_geometry_sliders`: call **both** `_sync_table_sliders_from_meta()` and `_sync_patient_sliders_from_meta()` so Settings per-exam spinbox edits refresh Geometry slider positions (N5, N7).
- `rebuild_rdsr_df` (`exam_transforms.py`): in multi-exam mode insert `EXAM_INDEX_COLUMN` (int, 0-based) for slicing; keep `EXAM_COLUMN` display string `"#<n> · <file>"` for Data Table only (T30).
- Composite smoke: 2 exams, toggle on, no traceback (T26).

**Slider sync stubs** (used in Parts III–IV; T17, T19):

```python
def _sync_table_sliders_from_meta(active_index=None):
    idx = active_index if active_index is not None else (state.active_exam_index or 0)
    if idx >= len(state.loaded_exam_meta): return
    # per axis: _props min/max, update(), then set_value

def _sync_patient_sliders_from_meta(active_index=None):
    idx = active_index if active_index is not None else (state.active_exam_index or 0)
    if idx >= len(state.loaded_exam_meta): return
    # patient_guard; set_value + val_labels[attr].set_text
```

---

## Part III — Phase 1: Multi-exam table-origin sliders

**Files:** `geometry.py`. **Prerequisite:** Part II.

- Show `offset_controls` when `rdsr_df` loaded (drop `not is_multi_exam`).
- Table-origin card: `bind_visibility_from` → `exam_supports_table_origin(exam, meta)` for active exam (WIP `helpers.py`: `True` when `base_data` has `Tx`/`Ty`/`Tz`; tabular without those columns → card hidden).
- `_sync_table_sliders_from_meta`: skip when active exam does not support table-origin.
- Sliders → `meta[active]` via `stage_table_origin_axis` + debounced `commit_table_origin_transform(state, active_index)`.
- Table-origin tick: `last_table_origin_scrub = True`; preview uses `composite=True` via `_resolve_composite_for_render()`.
- `_reset_table_origin`: use `active_exam_index` when multi-exam (T5).

---

## Part IV — Phase 2: Multi-exam patient-offset sliders

**Files:** `geometry.py`. **Prerequisite:** Parts II–III.

Multi-exam sliders edit **`meta[active].d_*` only** (not globals). Same fields as Settings per-exam spinboxes (`bind_value` on meta there); Geometry uses explicit write-back `meta[active][attr] = float(slider.value)` on tick — no `bind_value` (T4, N10). B3/T25 + `_refresh_geometry_sliders` keep tabs in sync.

- No `bind_value` / `bind_text_from` on Geometry patient sliders (T4); `patient_guard`; `val_labels` dict.
- Multi-exam tick → `meta[active][attr] = float(value)`; `last_table_origin_scrub = False`; single-exam → globals + `sync_global_patient_offset_to_single_exam_meta`.
- `composite_preview` checkbox; `on_change` calls `_resolve_composite_for_render()` path immediately (T29).
- Preview buttons: pass `_resolve_composite_for_render()` before render (T16).
- `_reset_patient_offset`: use `active_exam_index` when multi-exam (T5); multi → `meta[idx]=0`; single → globals + `meta[0]`.
- Captions: **Appendix B** C2–C4.

---

## Part V — Cross-cutting (ship with Parts II–IV)

| Location | Fix |
|----------|-----|
| `calculate.py:78` | **Edit:** `"Per-exam patient offsets editable in Upload tab"` → `"…in Geometry and Settings tabs"` |
| `calculate.py` `_format_patient_offsets()` | `is_multi_exam` → **Per-exam (various)** (T10) |
| `settings.py` `_format_table_offset_line()` | Same branch (imported by Calculate) |
| `settings.py` Phantom offsets | Hide global spinboxes when multi-exam; caption C6 |
| `upload.py` | T23 chain: `load_example`, `clear_all_exams`, `_remove_exam` → `ctx.refresh_per_exam()` |
| **Settings → Geometry** | When `apply_exam_transforms` fires from Settings (`_per_exam.py`), `rebuild_rdsr_df` replaces `state.rdsr_df`; if Geometry tab is active, re-clamp event index and call `_refresh_geometry_sliders` (or schedule debounced re-render) so preview slice stays valid (N4) |
| **Docs** | `AGENTS.md`, `CHANGELOG.md`, `TO_DO.md`, `docs/source/gui_help/positioning_offsets.md` (+ `sync_gui_help.py`), `dev-docs/CODEBASE_OVERVIEW.md`, `dev-docs/FEATURE_INVENTORY.md`, `dev-docs/plans/GUI_PLAN.md` §0, `dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md` (multi-exam `meta[i].d_*` vs globals; `geometry_preview.py`) |

---

## Part VI — Cross-tab sync (optional)

- Upload exam card click → set active index, `refresh_per_exam`, switch to Geometry tab.
- Settings per-exam card highlight for `active_exam_index`.
- Disambiguate duplicate selector labels with `study_id` / `sheet`.

---

## Out of scope

Offset arrow (deferred [INTERACTIVE_TABLE_OFFSETS_PLAN.md](INTERACTIVE_TABLE_OFFSETS_PLAN.md) Phase 3 — after this plan); per-exam dose map toggles; persisting Geometry UI across reload (session-only); export `table_origin_override` in `data.py`; incremental table-origin preview; per-exam event stepping ([TO_DO.md](../TO_DO.md)).

**Performance:** Single-exam `plot_procedure` unchanged (no new pause). Multi-exam composite preview only (`is_multi_exam and _resolve_composite_for_render()`): pause when `preview_event_count(..., composite=True) > 30`; spinner when `> 100`.

---

## Checklist

| Part | Done when |
|------|-----------|
| **I** | ✅ B1–B4 fixed; module split; `helpers.py` <800; tests green; **committed** |
| **II** | ✅ `geometry_preview.py` helpers; `EXAM_INDEX_COLUMN`; C1 banner + exam selector; `make_geometry_fig` args; T2, T7, T13, T23, T26, T28, T30 |
| **III** | Table-origin bound to active exam; T5 reset |
| **IV** | Patient sliders T4; composite toggle T29; T5 reset; C2–C4 |
| **V** | T10 formatters; `calculate.py:78`; C5–C6; docs + `CHANGELOG.md` |
| **VI** | *(optional)* |

---

## Exit criteria

Part I committed; Parts II–V complete; Appendix B tests + manual matrix pass; `python scripts/check_doc_freshness.py`. Archive plan; update `dev-docs/index.md`, `plans/archive/README.md`, `TO_DO.md`.

## Related

- [INTERACTIVE_TABLE_OFFSETS_PLAN.md](INTERACTIVE_TABLE_OFFSETS_PLAN.md) · [INPUT_DATA_FLOW_AND_OFFSETS.md](../INPUT_DATA_FLOW_AND_OFFSETS.md) · [TO_DO.md](../TO_DO.md)

---

## Appendix A — Technical constraints (T1–T30)

Grep while implementing Parts II–V.

| # | Issue | Fix |
|---|--------|-----|
| T1 | Filtered preview keeps concat row indices | `.reset_index(drop=True)` after slice |
| T2 | `reset_results()` clears `active_exam_index` | Remove `state.py:118` line |
| T3 | Table-origin limits fixed at build | On exam switch: `_props["min"]`/`["max"]` + `update()` |
| T4 | `bind_value` leaks globals | `patient_guard`; no `bind_value`/`bind_text_from` in multi-exam |
| T5 | `_reset_*` hardcoded to `meta[0]` | Use `active_exam_index` when multi-exam |
| T6 | Preview frame invisible to `make_geometry_fig` | Optional kwargs `active_exam_index`, `composite` through `run.io_bound`; CLI defaults unchanged |
| T7 | Event index out of range | Clamp in UI and `make_geometry_fig` |
| T8 | PAUSED/spinner use full `event_count()` | `preview_event_count(...)` only when `is_multi_exam and composite` |
| T9 | Selector programmatic update re-fires | `exam_selector_guard["suppress"]` |
| T10 | Stale Calculate/Settings summaries | **Per-exam (various)** when `is_multi_exam` |
| T11 | Preview frame includes `EXAM_COLUMN` | Drop in `rdsr_df_for_geometry_preview` |
| T12 | Patient vs table-origin composite differ | `last_table_origin_scrub` + `_resolve_composite_for_render()` |
| T13 | `make_geometry_fig` returns `None` | `geom_plot.update_figure({})` |
| T14 | Worker reads mutable `active_exam_index` | Pass index into preview helpers |
| T15 | Exam switch while `table_origin_pending` | Commit `old_index` in selector handler |
| T16 | Preview buttons stale composite flag | Pass `_resolve_composite_for_render()` before render |
| T17 | `set_value` before limit update | Limits + `update()` first |
| T18 | Exam slice by display tag collides with filenames | **Superseded by T30** — do not slice on `EXAM_COLUMN` string prefix |
| T19 | Sync helpers IndexError | Guard `idx >= len(loaded_exam_meta)` |
| T20 | Loader zeros globals before meta | Capture `prev_d_*` before reset; seed meta (B1) |
| T21 | `helpers.py` >800 lines | Module split (B2) |
| T22 | `EXAM_COLUMN` circular import | `exam_transforms.py`; lazy in `geometry_preview` |
| T23 | Multi→single loses offsets | `restore_globals_from_exam_meta`; refresh chain |
| T24 | Import cycles | `settings_builder`; `exam_transforms` not `helpers` |
| T25 | Settings spinboxes don't refresh Geometry | `ctx.refresh_per_exam()` after `_invalidate()` (B3) |
| T26 | Composite untested | Manual 0c + unit test |
| T27 | Wrong count for PAUSED | `preview_event_count` sliced; thresholds only when `is_multi_exam and composite` |
| T28 | `composite_preview` sticks after multi→single | Reset `composite_preview = False` when `is_multi_exam` → `False` |
| T29 | Toggle change after slider tick | `composite_preview` `on_change` re-derives composite via `_resolve_composite_for_render()` |
| T30 | `EXAM_COLUMN` prefix slice fragile | Add `EXAM_INDEX_COLUMN` (int) in `rebuild_rdsr_df`; slice preview by index equality |

---

## Appendix B — Copy, testing, manual matrix

### User-facing copy (verbatim)

| ID | Context | Text |
|----|---------|------|
| C1 | Multi-exam banner | **Multiple exams loaded.** Sliders edit the **selected exam** below. **Calculate** uses each exam's own patient offset and table-origin settings. The 3D preview is for positioning only — it may not show every exam at once. Geometry and Settings → Per-exam corrections edit the **same per-exam data**; Geometry is the interactive 3D surface. |
| C2 | Exam selector | **Patient and table-origin sliders apply to this exam.** |
| C3 | Patient preview (default) | **Preview: exam #{n} events only, phantom at this exam's offset.** |
| C3 | Patient preview (all exams) | **Preview: all exams' events; phantom position is exam #{n} only — other exams use their own offsets at Calculate.** |
| C4 | Toggle | **Show all exams in preview** — *Shows every exam's beam/table geometry together. Patient phantom stays at the selected exam's offset.* |
| C4 | Table-origin | **Table shift applies to the selected exam. Preview shows all exams; you will see this exam's table move relative to the others.** |
| C5 | Help | **Multiple exams** subsection in `docs/source/gui_help/positioning_offsets.md` |
| C6 | Settings Phantom | **Patient offsets are managed per-exam in multi-exam mode. Adjust them in the Geometry tab or Per-exam corrections section below.** |
| — | PAUSED (composite) | *Live preview may pause for large multi-exam composite views.* |

### Unit tests

**New:** `tests/unittests/test_gui_multi_exam_geometry_offsets.py` — lifecycle, `rdsr_df_for_geometry_preview` (slice by `EXAM_INDEX_COLUMN`), `preview_event_count`, table-origin commit index, patient slider write-back to meta (N10).

**Also:** `test_format_patient_offsets_multi_exam`, `test_format_table_offset_line_multi_exam` (T10); `test_per_exam_offset_change_calls_refresh_per_exam` (T25); `test_remove_exam_invokes_refresh_per_exam` (T23).

**Regression (Part I):** `test_loader_seeds_offset_defaults_from_global`, `test_remove_exam_restores_global_patient_offset_from_meta`, offset-reset patch tests (B4).

### Manual matrix

| ID | Assert |
|----|--------|
| 0a | Selector default/clamp; slice by `EXAM_INDEX_COLUMN`; drop tag columns (T1, T11, T30, T19) |
| 0b | Event clamp + slider limits on exam switch (T3, T7, T17) |
| 0c | Composite preview smoke (T6, T14, T26) |
| 0h | 0 exams: no selector/sliders; empty plot |
| 0d | PAUSED/spinner composite-only (`is_multi_exam and composite`; T8, T27) |
| 0e | Selector guard; table-origin commit on switch (T9, T15) |
| 0f | None plot cleared (T13) |
| 0g | Remove exam → globals + slider chain (T23) |
| 0i | `adjust_active_exam_index_after_remove`: remove before / at / after active |
| 0j | Table slider limits + values after exam switch |
| 0k | Patient sliders sync from Settings spinbox edit (N5) |
| 0l | `composite_preview` toggle vs debounced render (T29, N3) |
| 0m | `composite_preview` reset on multi→single (T28) |
| 1a–1b | Table-origin per active exam |
| 2a–2e | Patient `meta[active]` write-back; toggle `on_change` (T29); preview modes (T4, T12, T16) |
| 10a–10d | T10 formatters; T25 sync |
| C1–C6 | Copy checklist |
