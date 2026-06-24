# Plan: refactor execution

_Last updated: 2026-06-11_

> Companion to [REFACTOR_ASSESSMENT.md](../../assessments/REFACTOR_ASSESSMENT.md) (the diagnostic). This file is the executable plan — the assessment says *what* is wrong; this says *how* to fix it, in what order, and how to verify each step.

> See also: [CODEBASE_OVERVIEW.md](../../CODEBASE_OVERVIEW.md) | [GUI_PLAN.md](../GUI_PLAN.md) | [HARNESS_ENGINEERING.md](../../HARNESS_ENGINEERING.md)

**Status: Phases 0–3 complete (2026-06-23).** Phase 4 remains opportunistic.

---

## Principles

- **Each phase ends green.** Tests pass, the GUI launches, before moving on.
- **One concern per commit.** Small reversible commits, not big-bang rewrites.
- **Backfill tests before refactoring the thing they cover.** You cannot safely restructure `rdsr_normalizer.py` without a test that pins its current numeric output.
- **No behavior change in a refactor commit.** If a refactor commit also fixes a bug, split it.

---

## Phase 0 — Quick wins (low risk, high value)

Independent one-commit fixes. Do these first; none block the others.

- [x] **0.1 Fix the temp file leak.** `gui/app.py` wrote uploads with `delete=False` and never removed them. Added a module-level registry (`_register_temp_upload` / `_cleanup_temp_uploads` / `_uploaded_temp_files`): each new upload deletes the previous upload's temp file, and an `atexit` sweep removes whatever remains. The current upload is intentionally kept alive for the session because the XLSX sheet picker re-reads `state.file_path` on every sheet change (the plan's "delete immediately after load" alternative would have broken multi-sheet XLSX). Bundled example files are never registered, so they are never deleted. Covered by `tests/unittests/test_gui_temp_uploads.py` (5 tests).
  - **Verify:** ✅ unit tests pin the contract (new upload deletes prior, atexit sweeps, tolerant of already-deleted files); full suite (106) + GUI smoke (2) green.

- [x] **0.2 Introduce `logging`.** Reimplemented `dprint()` on top of the stdlib `logging` framework instead of changing 37 call sites (kept the category system, which `getLogger(__name__)` would have lost). Each category maps to a child logger `mypyskindose.<category>`; `dprint` emits at DEBUG there, gated by the category's level. `debug.py` now exposes `configure_logging(log_file=None)` which sets up the `mypyskindose` logger tree (console + optional file). This also lights up the ~25 modules that already called `getLogger(__name__)`/`getLogger("mypyskindose")` but had **no handler configured** — their logs previously went nowhere. Native GUI mode writes to `<tempdir>/mypyskindose-gui.log` (no console there). Wired into `run_gui` and the `__main__` CLI dispatch. Covered by `tests/unittests/test_debug_logging.py` (8 tests).
  - **Verify:** ✅ tests pin gating (disabled category suppressed, enabled emits with name visible), file sink writes, handler de-dup, debug.json load + malformed-tolerance, lazy config. Full suite (116) + GUI smoke green; basedpyright clean.

- [x] **0.3 Add a `busy` operation guard.** Added `state.busy` plus a module-level `_operation_guard(label)` context manager. `handle_upload`, `load_example`, `_on_sheet_change`, and `do_calculate` now wrap their body in `with _operation_guard(...) as proceed:` and bail (with a "please wait" notification) if another operation is in flight. The check-and-set has no `await` between read and write, so it is race-free under asyncio's cooperative scheduling — no lock needed. `do_calculate` additionally got a `try/finally` so its buttons re-enable even if the calculation raises. This is the cheap mitigation for the shared-state concern (§5 of the assessment) without a full state redesign. Covered by `tests/unittests/test_gui_operation_guard.py` (5 tests).
  - **Verify:** ✅ tests pin first-entry-proceeds, re-entrant-denied, busy-cleared-on-exception, denied-entry-leaves-outer-busy-intact, sequential-ops. Full suite (121) + GUI smoke green; basedpyright clean.

**Phase 0 exit:** ✅ `pytest tests/` green (121 unit + 2 smoke), GUI launches, manual upload + example load both work.

---

## Phase 1 — Test backfill for silent-correctness modules

These modules produce numbers, not errors — a regression is invisible. Pin their current behavior **before** any later phase touches them.

- [x] **1.1 `rdsr_normalizer.py` characterization tests.** `tests/unittests/test_rdsr_normalizer_characterization.py` parses + normalizes all three bundled RDSRs and asserts exact `Tx/Ty/Tz/Ap1/Ap2` (+ `kVp/K_IRP`) for the first 3 rows against golden values captured 2026-06-11, plus matched model/method/row-count. Includes a dedicated `test_philips_table_positions_need_no_swap` pinning the lat/lon-swap investigation finding. Tolerance 0.01 — tight enough to catch a sign flip.
  - **Verify:** ✅ 7 tests pass against current code. Locally flipping the `Tz` `trans_dir` sign produced 4 failures (incl. the Philips swap test); restored clean.

- [x] **1.2 `format_export_data.py` + export-embedding tests.** `tests/unittests/test_export_data.py` runs a real end-to-end calc (cylinder phantom, 0.1 s) and asserts the dict/JSON export has the 8 expected top-level keys, is JSON-serializable, and contains **no NaN**; plus dose-map sparsity. The GUI provenance embedding was **extracted** from the export closures into module-level pure helpers `_tabular_input_meta()` and `_inject_html_tabular_meta()` (removing the dict duplication between JSON and HTML paths that the assessment §9 flagged), and unit-tested: meta shape/serializability, head-comment insertion position, no-op without `<head>`, only-first-`<head>` annotated.
  - **Verify:** ✅ 8 tests pass. After strengthening the position assertion, corrupting the injection anchor (`<head>`→`</head>`) is caught; restored clean. basedpyright clean.

- [ ] **1.3 (optional) `rdsr_parser.py` tests.** Assert the parser extracts the expected table-position columns from each bundled RDSR. Lower priority — parser bugs tend to surface as missing-column errors rather than silent wrong numbers. _Deferred — not blocking Phase 2._

**Phase 1 exit:** ✅ characterization + export tests committed and green (136 unit + 2 smoke). These are the safety net for the Phase 2/3 refactors.

---

## Phase 2 — Adapter consolidation

All four real adapters share steps 1–3 and 7 (assessment §3). Migrate incrementally so adapters are never collectively broken.

- [x] **2.1 Extract the shared pipeline.** `input_adapters/base.py` provides `run_normalizer_pipeline(loaded, *, schema_name, known_names, patterns, required_columns, transform, original_filename, settings)` owning header detection → `extract_table` → map → dup-check → rename → transform → required-check → `rdsr_normalizer` → provenance/result. The per-adapter `transform(data_df, ctx)` does numeric coercion + unit conversion + vendor specifics; `AdapterContext` carries the mutable `warnings`/`unit_conversions`. Shared helpers `extract_table` and `coerce_numeric_columns` also extracted. The sentinel `_dt_*` exclusion from the public column map is now uniform in the base.

- [x] **2.2 Migrate `radimetrics` onto `base`.** Transform = numeric coercion + unit conversions + model/GE warnings + fallbacks. Required-columns check moved from "after rename" to "after transform" (safe: the transform guards every column access and adds nothing required).
  - **Verify:** ✅ 57 adapter tests green.

- [x] **2.3 Migrate `dosetrack`, `generic_rdsr`, `normalized`.** `generic_rdsr` transform is just numeric coercion; `dosetrack` transform keeps ffill/manufacturer-inference/plane-code/units/filter/CFA. `normalized` is structurally different (case-insensitive exact match, multi-procedure check, no `rdsr_normalizer`) so it does **not** use the pipeline — it shares only `extract_table`.
  - **Verify:** ✅ 57 adapter tests green after each migration.

- [x] **2.4 Collapse the three stubs.** Deleted `qaelum.py`/`dosemonitor.py`/`dosewatch.py`; replaced with `stubs.py` (`STUB_VENDORS` map + `raise_not_implemented(schema) -> NoReturn`). Registry routes `schema in stubs.STUB_VENDORS` to it; the `NoReturn` annotation let the old `AssertionError` "unreachable" guard be removed (pyright now sees `result` is always bound).
  - **Verify:** ✅ all three stub schemas raise the instructive `NotImplementedError`; pyright clean.

- [x] **2.5 Move per-vendor column sets out of `column_mapper.py`.** Relocated each `*_COLUMN_NAMES`/`*_PATTERNS` (and `NORMALIZED_COLUMN_CANONICAL`/`NORMALIZED_REQUIRED_COLUMNS`) into its adapter module; `registry._SCHEMA_KNOWN_NAMES` now imports them from the adapters. `column_mapper.py` keeps only the engine + `COLUMN_PATTERNS` (a generic fixture exercised by the engine's collision tests). **547 → 226 lines.** Two test imports updated.
  - **Verify:** ✅ auto-detection tests still resolve each fixture; 64 adapter+characterization tests green.

**Phase 2 exit:** ✅ `column_mapper.py` is the engine only (547→226); each adapter owns its column knowledge + a thin transform; stubs are one file. Full suite (136) + GUI smoke green; basedpyright clean.

---

## Phase 3 — GUI decomposition

The largest and least urgent item. Do it only after Phases 0–2 settle. Prerequisite is the `PageContext` change — without it the tab functions can't be extracted because they close over widget references.

> **Detailed design:** [gui-decomposition-design.md](gui-decomposition-design.md) — the measured wiring map of `index()` (cross-cutting widgets, handler call graph, the timer-driven vs call-driven distinction), the `PageContext` shape, and the easiest→hardest extraction order.

> **Safety net first (done):** `tests/gui/test_gui_flows.py` now exercises real handler wiring (all seven tab panels build their headings; the example-load flow runs end to end). The original smoke test only checked three labels — too thin to refactor handlers against.

- [x] **3.0 Extract self-contained, closure-free units.** These don't touch `index()` scope, so they move out with near-zero risk ahead of the harder `index()` split:
  - `gui/figures.py` — the four Plotly builders (`make_geometry_fig`, `make_dosemap_fig`, `make_dosemap_html`, `make_dosemap_png`), renamed public and imported back into `app.py`.
  - `gui/styles.py` — the `MODERN_CSS` constant (~230 lines). `scripts/generate_ui_values.py` updated to read `styles.py`; `UI_values.md` and `index.md` path labels updated.
  - **Result:** `app.py` 1646 → 1281 lines. GUI tests (4) green; basedpyright clean; `generate_ui_values.py --check` consistent.

- [x] **3.1 Introduce `PageContext`.** `gui/page_context.py` holds cross-cutting chrome (`tabs`, drawer labels, `run_btn_drawer`) plus shared refresh callbacks (`refresh_event_table`, `refresh_import_preview`, `refresh_per_exam`, `refresh_exams_table`) wired after the upload/settings tabs build. Tab-local widgets stay in their tab modules.
  - **Verify:** ✅ GUI flow + smoke tests green; basedpyright catches missing `ctx` fields.

- [x] **3.2 Extract widget components.** `gui/widgets/import_preview.py` (preview card, sheet picker, coordinate toggles, `_refresh_import_preview` / `_set_transform_defaults`) and `gui/widgets/event_table.py` (irradiation-event summary table + refresh).
  - **Verify:** ✅ smoke + flow tests green.

- [x] **3.3 Extract tabs one at a time** into `gui/tabs/{upload,data,settings,geometry,calculate,results,export}.py`. Shared helpers relocated downward: `gui/concurrency.py` (`operation_guard`, `upload_lock`), `gui/upload_temp_files.py` (temp-file registry + atexit), `gui/io_helpers.py` and `gui/constants.py` (already in place). Upload tab extracted last (3.3g coupling cluster).
  - **Verify:** ✅ full suite (255) + GUI smoke green; basedpyright clean.

- [x] **3.4 Final `app.py` shape:** `index()` builds header/drawer/tabs + `PageContext`, then calls each tab's `build(ctx)`. `run_gui()` and `ui.run()` stay. **`app.py` 1275 → 245 lines.** `scripts/check_file_sizes.py` whitelist removed.

**Phase 3 exit:** ✅ `app.py` 245 lines; each tab is an independently readable module; GUI smoke test green.

---

## Phase 4 — Lower-priority cleanups (opportunistic)

Not scheduled as a batch. **4.2** and **4.3** have detailed checklists below (also tracked in [TO_DO.md](../../TO_DO.md)). **4.1** and **4.4** are deferred — see TO_DO **Deferred** section.

---

### 4.2 — Shared figure-style helper (`plotting/` only)

**Goal:** One place to change fonts, margins, axis styling, and dark/light canvas defaults for **CLI / notebook / HTML** Plotly outputs. Do **not** merge with `gui/figures.py` or `gui/styles.py` in the first pass — those serve the NiceGUI app and already diverge intentionally.

**Current state (2026-06-23):**

| Module | What it duplicates |
|---|---|
| `plotting/plot_settings.py` | `fetch_plot_colors`, `fetch_slider_colors`, `fetch_plot_size` — color/size only |
| `plotting/plot_procedure.py` | `_create_procedure_layout()` — full `go.Layout` + slider styling |
| `plotting/create_setup_and_event_plot.py` | Inline `go.Layout` for setup/event geometry plots |
| `plotting/create_layout_for_dose_map_plots.py` | Dose-map-specific `go.Layout` (scene axes hidden) |
| `gui/figures.py` | Separate Plotly builders for the GUI — **out of scope for 4.2** |

**Design decisions (lock before coding):**

- [ ] **D1 — Module location:** Add `plotting/plot_layout.py` (or extend `plot_settings.py` if it stays under ~200 lines). Prefer a new file if `plot_settings.py` would mix “fetch tuples” with “build Layout objects”.
- [ ] **D2 — API shape:** Expose builders, not a single mega-function:
  - `default_geometry_layout(*, dark_mode, notebook_mode, title=None, show_slider=False) -> go.Layout`
  - `default_dosemap_layout(*, dark_mode, notebook_mode) -> go.Layout` (may wrap/refactor existing `create_layout_for_dose_map_plots`)
  - Optional: `default_slider_step(*, dark_mode) -> dict` for procedure slider dict fragments
- [ ] **D3 — Parameters:** All builders take `dark_mode: bool` and `notebook_mode: bool`; sizes/margins come from existing `fetch_plot_size` / `fetch_plot_margins` in `plot_settings.py`.
- [ ] **D4 — Non-goals:** No change to trace colors (`COLOR_BEAM`, mesh colors in `constants.py`), camera presets (`get_camera_view.py`), or GUI figure code.

**Implementation checklist:**

- [ ] **4.2.1 Inventory** — List every `go.Layout(` call site under `src/mypyskindose/plotting/`; note per-plot overrides (title text, slider presence, scene `aspectmode`).
- [ ] **4.2.2 Implement `default_geometry_layout`** — Consolidate shared fields from `create_setup_and_event_plot.py` and `plot_procedure._create_procedure_layout` (font family/size, `paper_bgcolor`, hoverlabel, scene axis grid/zeroline colors). Keep plot-specific title strings at the call site via `title=` kwarg.
- [ ] **4.2.3 Refactor `create_setup_and_event_plot.py`** — Replace inline layout with `default_geometry_layout(...)`; behavior-preserving (visual diff optional: save one HTML before/after from `plot_setup` mode).
- [ ] **4.2.4 Refactor `plot_procedure.py`** — Use `default_geometry_layout` + extracted slider helper; delete duplicated font/margin blocks.
- [ ] **4.2.5 Refactor dose-map layout** — Either move `create_layout_for_dose_map_plots` into `plot_layout.py` as `default_dosemap_layout`, or make it a thin wrapper that calls the shared helper for font/margin/canvas and only adds dose-map scene overrides.
- [ ] **4.2.6 Tests** — Add `tests/unittests/test_plot_layout.py`: assert returned objects are `go.Layout`, key fields match current constants (`PLOT_FONT_FAMILY`, margins), dark vs light `paper_bgcolor` differs. No pixel/visual regression required.
- [ ] **4.2.7 Docs** — One paragraph in `dev-docs/CODEBASE_OVERVIEW.md` under plotting: “layout defaults live in `plotting/plot_layout.py`”.

**Verify:** `python -m pytest tests/unittests/test_plot_layout.py tests/unittests/test_export_data.py -q` (export untouched but quick sanity); `basedpyright`; manual `settings.mode = plot_setup` / `plot_procedure` smoke on one bundled RDSR.

**Exit:** All `go.Layout` construction in `plotting/` goes through ≤2 public helpers; `gui/figures.py` unchanged.

---

### 4.3 — `schema_version` on JSON / dict export

**Goal:** Downstream consumers (scripts, archival tools, future report exporters) can detect export format changes without parsing package version from the environment. **Additive only** — existing keys unchanged.

**Current state:**

- Core payload: `PySkinDoseOutput.to_dict()` in `format_export_data.py` (8 top-level keys pinned by `tests/unittests/test_export_data.py`).
- GUI export: `gui/tabs/export.py` `_build_export_payload()` copies `state.output` and may add `tabular_input`.
- Multi-exam GUI path stores `state.multi_exam_result` — confirm whether JSON export covers multi-exam yet; if not, scope `schema_version` to the single-exam dict path first and note multi-exam in D4.

**Design decisions:**

- [ ] **D1 — Version value:** Use an integer **export schema version** (start at `1`), **not** the package semver from `pyproject.toml`. Bump only when the export JSON shape changes incompatibly (field removed/renamed/type changed). Document in a module constant `EXPORT_SCHEMA_VERSION = 1` in `format_export_data.py`.
- [ ] **D2 — Field placement:** Top-level sibling of `psd`, `events`, etc.: `"schema_version": 1`. Same for GUI payload after `_build_export_payload`.
- [ ] **D3 — `tabular_input`:** Leave as optional sibling; it is provenance metadata, not part of the core schema version bump unless its shape changes (track separately if needed later).
- [ ] **D4 — Multi-exam:** If GUI JSON export does not yet serialize `multi_exam_result`, add `schema_version` only where `to_dict()` is used today; file a follow-up in TO_DO if multi-exam export is missing.

**Implementation checklist:**

- [ ] **4.3.1 Constant** — `EXPORT_SCHEMA_VERSION = 1` in `format_export_data.py` (module docstring: when to increment).
- [ ] **4.3.2 Core export** — Add `"schema_version": EXPORT_SCHEMA_VERSION` as the **first** key in `PySkinDoseOutput.to_dict()` (stable ordering helps human diffing).
- [ ] **4.3.3 GUI export** — Ensure `state.output` already includes `schema_version` via step 4.3.2 (preferred: single source in `to_dict()`, not duplicated in `export.py`). If multi-exam builds a dict manually, add the field there too.
- [ ] **4.3.4 Tests** — Update `_EXPECTED_TOP_KEYS` in `test_export_data.py` to include `schema_version`; assert `out["schema_version"] == 1` and JSON round-trip preserves it. Add test that `schema_version` is an `int`.
- [ ] **4.3.5 Docs** — `FEATURE_INVENTORY.md` export row; `dev-docs/plans/TABULAR_RDSR_INPUT_PLAN.md` export section (one line: core export includes `schema_version`); `CHANGELOG.md` under `[Unreleased]`.
- [ ] **4.3.6 Consumer note** — Short comment in `format_export_data.py` and `gui/io_helpers._tabular_input_meta` docstrings: consumers should check `schema_version` before reading nested fields.

**Verify:** `python -m pytest tests/unittests/test_export_data.py -q`; `basedpyright`; GUI manual: run calc → Export JSON → confirm `"schema_version": 1` at top level.

**Exit:** Every programmatic JSON/dict export path includes `schema_version`; tests pin value `1`.

---

### 4.1 — Split `constants.py` (deferred)

See [TO_DO.md § Deferred](../../TO_DO.md#deferred).

### 4.4 — Narrow broad `except Exception` (deferred)

See [TO_DO.md § Deferred](../../TO_DO.md#deferred).

---

## Verification reference

| Gate | Command |
|---|---|
| Unit tests | `python -m pytest tests/unittests/ -q` |
| Adapter tests | `python -m pytest tests/unittests/test_input_adapters.py -q` |
| GUI smoke | `python -m pytest tests/gui/ -q` |
| Type check | `basedpyright` (runs on pre-push) |
| Full suite | `python -m pytest tests/ -q` |

Run the relevant gate after each checklist item; run the full suite at each **Phase exit**.
