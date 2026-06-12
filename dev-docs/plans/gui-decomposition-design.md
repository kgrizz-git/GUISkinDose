# Design: GUI `index()` decomposition (Phase 3.1a + 3.3a–g)

<!-- Scope note: this design covers the PageContext introduction (3.1a) and the per-tab
extractions (3.3a–g). Any 3.2/3.4 steps named in refactor-execution.md are out of scope here. -->


_Last updated: 2026-06-11_

> Companion to [refactor-execution.md](refactor-execution.md) §Phase 3. That file is the checklist; this is the wiring map and the safe-extraction design it depends on. Produced by mapping `src/mypyskindose/gui/app.py` after Phase 3.0 (figures/styles already extracted; `index()` ≈ lines 181–1216, ~1035 lines).

---

## 1. Why `index()` resists naive extraction

`index()` builds the whole page and defines ~21 nested handlers as closures. Two coupling mechanisms:

1. **Closure over widget references** — handlers call `widget.set_text(...)` / `.disable()` on locals defined elsewhere in `index()`.
2. **Cross-handler calls** — some handlers call other handlers directly.

You cannot move a handler to another module until *both* are broken: its widgets and its callees must be reachable without the enclosing scope. That is what `PageContext` is for.

---

## 2. The wiring map (measured, not guessed)

### 2.1 Refresh mechanism — the key finding

Most "refresh" handlers are **timer-driven**, not call-driven. They poll `state` on a `ui.timer` and update their own widgets. They have **no cross-handler dependencies** and read only `state` + their own tab's widgets:

| Handler | Wired by | Touches |
|---|---|---|
| `_refresh_metrics` | `ui.timer(1.0)` | `psd_metric`, `kerma_metric`, `events_metric` (results) |
| `_refresh_corr_table` | `ui.timer(2.0)` | `corr_table` (results — defined in the results panel, lines 1056/1078, **not** export) |
| `_refresh_raw_table` | `ui.timer(2.0)` + `view_toggle` | `raw_data_table` (data) |
| `_refresh_dosemap` | `ui.timer(1.5)` + select + button | `dosemap_plot`, `dosemap_spinner` (results) |

> `_refresh_metrics`, `_refresh_dosemap`, and `_refresh_corr_table` all live inside the **results** `tab_panel`; the export panel (line 1116+) contains only the download cards.

➡️ **These tabs are the easy wins** — self-contained, extract first.

### 2.2 The coupling cluster — the Upload tab

This is where all the cross-handler calls live:

```
handle_upload ─┬─► _refresh_event_table
               ├─► _refresh_import_preview
               └─► _set_transform_defaults ──► _is_ge
load_example ────► _refresh_event_table
_on_sheet_change ─┬─► _refresh_event_table
                  └─► _refresh_import_preview
_on_swap_toggle  ─┬─► _refresh_event_table       (also _on_flip_ap1/ap2_toggle)
                  └─► _refresh_import_preview
(restore tail) ────► _refresh_event_table
```

`_refresh_event_table` and `_refresh_import_preview` are the **shared spine** of this cluster — called from 6+ sites. They must become `ctx`-parameterized functions before any upload handler can move.

### 2.3 Cross-cutting widgets (referenced outside their defining section)

These are the **only** widgets that must live in `PageContext` as shared state; everything else is tab-local:

| Widget | Defined in | Written by (other scopes) |
|---|---|---|
| `file_label`, `events_label` | drawer | upload handlers, restore tail |
| `psd_label` | drawer | `do_calculate` |
| `run_btn_drawer` | drawer | `do_calculate` (disable/enable) + `.on("click", …)` wired in the **calculate** panel (line 965) |
| `tabs` | top | `do_calculate`, restore tail, `go()` |

> `upload_status` is **not** cross-cutting: it is written only by `handle_upload`, `load_example`, and `_on_sheet_change` — all inside the upload tab — so it stays tab-local in `tabs/upload.py` and does not belong in `PageContext`. (The §3 dataclass sample correctly omits it.)

Everything else (`upload_status`, `import_*` labels, `sheet_*`, `coord_auto_label`, `event_table`, `geom_*`, `calc_*`, `*_metric`, `dosemap_*`, `corr_table`, `raw_data_table`) is touched only within its own tab's handlers.

### 2.4 Tab-local widget inventory

- **drawer:** `file_label`, `events_label`, `psd_label`, `run_btn_drawer` (all cross-cutting)
- **upload:** `upload_status`, `example_select`, `import_schema_badge`, `import_encoding/delimiter/header/sheet_label`, `sheet_row`, `sheet_select`, `coord_auto_label`, `import_warnings_label`, `col_map_table`, `event_sample_table`, `event_table`
- **data:** `view_toggle`, `raw_data_table` — plus the `_local_export(fmt)` handler (lines 682–736) and its CSV/XLSX/TXT buttons; `_local_export` depends on module-level `_get_save_path` (see §6 circular-import note)
- **settings:** (binds to `state` directly; few named widgets) `mesh_select` + `_update_mesh_visibility` (its own `ui.timer(0.5)`)
- **geometry:** `geom_event_input`, `geom_spinner`, `geom_plot`
- **calculate:** `calc_btn`, `calc_progress`, `calc_status_label`
- **results:** `psd_metric`, `kerma_metric`, `events_metric`, `dosemap_plot`, `dosemap_spinner`, **`corr_table`** (with the colorscale `ui.select` at 1049 and the REGENERATE button at 1053)
- **export:** (download cards only — no named refresh widgets)

---

## 3. `PageContext` design

A **mutable** dataclass of widget handles, built in `index()` and passed to every extracted builder/handler. It is *not* `frozen=True`: the two refresher callables are not known when the context is first constructed (the upload tab defines them later), so they are given no-op defaults and reassigned once the upload tab is built. Minimum viable shape (only the cross-cutting + shared-spine members are strictly required; tab-local widgets can stay as parameters to each tab's `build()` or be added to the context for uniformity):

```python
def _noop() -> None: ...

@dataclass
class PageContext:
    # cross-cutting chrome (set at construction)
    tabs: ui.tabs
    file_label: ui.label
    events_label: ui.label
    psd_label: ui.label
    run_btn_drawer: ui.button
    # shared refresh callbacks — default to no-op, reassigned after the
    # upload tab is built; this breaks the call cycle without freezing.
    refresh_event_table: Callable[[], None] = _noop
    refresh_import_preview: Callable[[], None] = _noop
```

The two shared refreshers go in the context as **callables**, not as the widgets they touch — so an upload handler in `tabs/upload.py` calls `ctx.refresh_event_table()` without importing the function or its widgets. `index()` reassigns `ctx.refresh_event_table` / `ctx.refresh_import_preview` after building the upload tab. (In practice the only *cross-module* caller is the restore tail in `index()`; the other call sites are inside the upload tab and could call the local function directly — but routing them all through `ctx` keeps the upload module free of any back-reference.)

> Typing note: `ui.tabs`/`ui.label` etc. are concrete NiceGUI types — annotate with them so basedpyright catches a handler referencing a field that doesn't exist (`ctx.nonexistent` is a hard error). This is the main automated safety net for the mechanical rename.

---

## 4. Safe extraction order

> **Progress (2026-06-12):** 3.1a + 3.3a–3.3c done (first milestone). `gui/page_context.py`, `gui/constants.py`, `gui/io_helpers.py`, and `gui/tabs/{results,export,data}.py` exist; `app.py` ~940 lines. Remaining: 3.3d geometry, 3.3e settings, 3.3f calculate, 3.3g upload. The §6 import strategy is decided (relocate downward).

Strictly easiest → hardest, so the risky cluster is done last when the pattern is proven:

1. **3.1a — Introduce `PageContext` in place.** Add the dataclass; build it in `index()`; convert the **cross-cutting** widget references (drawer labels, `tabs`) and the two shared refreshers to go through `ctx`. No file split yet. Verify: flow + smoke tests green; basedpyright green (catches field typos).
2. **3.3a — Results tab** → `tabs/results.py`. All three results refreshers: `_refresh_metrics` (timer 1.0), `_refresh_dosemap` (timer 1.5 + colorscale select + REGENERATE button), and `_refresh_corr_table` (timer 2.0) — plus `corr_table`, the metric labels, the dosemap plot/spinner, and the visual-settings select. All read `state` only (and `make_dosemap_fig`, already extracted). Lowest risk. Note `_refresh_corr_table` lazy-imports `numpy`.
3. **3.3b — Export tab** → `tabs/export.py`. Only the export helpers: `_build_export_payload` (local) + `download_json/html/png`, which use `make_dosemap_*` and the module-level `_tabular_input_meta`/`_inject_html_tabular_meta`/`_get_save_path`. `download_*` need `ctx` only for notifications. **`corr_table` does not move here — it is a results widget** (see §2.1/§2.4). Resolve the helper imports per §6 before this step.
4. **3.3c — Data tab** → `tabs/data.py`. `_refresh_raw_table` (timer + `view_toggle`) **and `_local_export`** + its CSV/XLSX/TXT buttons (`_get_save_path` dependency — see §6).
5. **3.3d — Geometry tab** → `tabs/geometry.py`. `preview_setup/event/procedure` over the already-extracted `make_geometry_fig`. Imports `HelpButton`.
6. **3.3e — Settings tab** → `tabs/settings.py`. Mostly `state` binds; `mesh_select` visibility via its own `_update_mesh_visibility` timer. Imports `HelpButton`.
7. **3.3f — Calculate tab** → `tabs/calculate.py`. First **relocate `_operation_guard`** to a shared module (per §6) since both calculate and upload use it. `do_calculate` touches drawer (`psd_label`, `run_btn_drawer`) and `tabs` — all in `ctx`. **The `run_btn_drawer.on("click", do_calculate)` wiring must move into `calculate.build(ctx)`** even though the button is built in the drawer.
8. **3.3g — Upload tab (last)** → `tabs/upload.py` + `widgets/import_preview.py`. The coupling cluster. First **relocate the temp-file lifecycle** (`_register_temp_upload`, `_cleanup_temp_uploads`, `_uploaded_temp_files`, `atexit` hook) per §6. Move `_refresh_event_table`/`_refresh_import_preview` first (wire as `ctx` callables), then the handlers that call them. The cluster is now larger than §2.2 first recorded — handlers to move: `handle_upload` (NiceGUI 3.x `e.file` API), `load_example` (auto-loads via `on_value_change`, no button), `_on_schema_change` (schema auto-reparse), `_on_sheet_change`, `_on_swap_toggle`, `_on_flip_ap1/ap2_toggle`, plus `_set_transform_defaults`/`_is_ge`. Carry the `.mark("example-select")` on the example select — `test_gui_flows.py` finds it by that marker.

Commit per tab; run `pytest tests/gui/` between each.

---

## 5. Verification per step

- **Automated net:** `tests/gui/test_gui_flows.py` (all tab headings build; example-load runs) + `test_gui_smoke.py`. basedpyright on the typed `PageContext`.
- **Strengthen the net before 3.3g (still pending):** `test_gui_flows.py` now drives example auto-load (open the `example-select` dropdown, click an option) and asserts the drawer event count — but it stops there. Before 3.3g, extend it to navigate to the data tab and assert the event table populates, exercising `_refresh_event_table` through the upload cluster (the part with the most cross-calls). (NiceGUI `User` can click nav buttons and `should_see` table content.)
- **What the net does NOT cover:** real file *upload* (NiceGUI `User` can't easily simulate `ui.upload` drag-drop), and the live `ui.timer` refresh cadence. Treat those as manual-smoke items, or assert the refresher functions directly by calling them with a populated `state`.

---

## 6. Risks & gotchas

- **Circular imports — DECIDED: strategy (a), relocate downward.** The `tabs/*` modules are imported *by* `app.py`, so a top-level `from ..app import …` in a tab module would be circular. Resolved by moving shared symbols to non-`app` modules that both `app.py` and the tab modules import *downward* from. Already done and in use: `gui/constants.py` (UI option lists) and `gui/io_helpers.py` (`_get_save_path`, `_tabular_input_meta`, `_inject_html_tabular_meta`). **Still to relocate for the remaining tabs:** `_operation_guard` (calculate + upload) and the upload temp-file lifecycle — `_register_temp_upload`, `_cleanup_temp_uploads`, the `_uploaded_temp_files` list, and its `atexit` hook. Put the guard in `gui/io_helpers.py` (or a small `gui/concurrency.py`); keep the temp-file lifecycle together (its own module or `io_helpers`) since the `atexit` registration and module-global list must move as a unit. The rejected alternative was lazy-importing tab builders inside `index()` (the `HelpButton` precedent) — lower-friction but leaves `app.py` as a dependency hub; (a) is cleaner and is what the first milestone established.
- **Timer closures still need their widgets.** `ui.timer(1.0, _refresh_metrics)` is created in `index()`. When `_refresh_metrics` moves to `tabs/results.py`, the timer registration moves with it (inside `results.build(ctx)`), not left behind in `index()`.
- **The restore tail** (`if state.rdsr_df is not None: ... _refresh_event_table()`) runs at page build. It depends on the upload spine — keep it in `index()` but have it call `ctx.refresh_event_table()`.
- **`go()` / `_update_nav_classes`** mutate `nav_buttons` (drawer). Keep nav in `index()`/`layout`; expose `tabs` via `ctx`.
- **NiceGUI test reload:** `tests/gui/nicegui_main.py` does `importlib.reload(gui_app)`. New `gui/tabs/*` modules are imported *by* `app.py`, so they reload transitively — but confirm no module-level state in a tab module caches a stale `state` reference (import the singleton, don't copy it).
- **`HelpButton` import** is done lazily inside `index()` (`from .components import HelpButton`) — preserve that placement or move per-tab as needed.

---

## 7. Decision: stop point

3.1a (PageContext in place) + 3.3a–3.3c (results / export / data — the timer-driven, low-coupling tabs) is a natural **first milestone**: it proves the pattern on low-risk tabs and removes ~300 lines from `index()` without touching the upload cluster. Note that export and data still pull in the module-level `_get_save_path` (and export the provenance helpers), so the §6 circular-import decision must be made as part of this milestone — it is not entirely dependency-free. 3.3f–3.3g (calculate, upload) are the higher-risk remainder and can be a second milestone.
