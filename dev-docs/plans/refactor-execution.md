# Plan: refactor execution

_Last updated: 2026-06-11_

> Companion to [REFACTOR_ASSESSMENT.md](../REFACTOR_ASSESSMENT.md) (the diagnostic). This file is the executable plan — the assessment says *what* is wrong; this says *how* to fix it, in what order, and how to verify each step.

> See also: [CODEBASE_OVERVIEW.md](../CODEBASE_OVERVIEW.md) | [GUI_PLAN.md](../GUI_PLAN.md) | [HARNESS_ENGINEERING.md](../HARNESS_ENGINEERING.md)

**Status: not started.**

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

- [ ] **3.1 Introduce `PageContext`.** A dataclass holding the widget references that handlers currently close over (e.g. `sheet_row`, `sheet_select`, `coord_auto_label`, `event_table`, `upload_status`, plot handles, label handles). Built inside `index()`, passed explicitly to handlers. No file split yet — just stop relying on closure scope. This is a mechanical, behavior-preserving change done **in place** in `app.py`.
  - **Verify:** GUI smoke test (`tests/gui/`) green; manual click-through of all tabs.

- [ ] **3.2 Extract widget components.** Move the import-preview card (preview + sheet picker + coordinate toggles) into `gui/widgets/import_preview.py` as a builder taking `(state, ctx)`. Move the event table into `gui/widgets/event_table.py`.
  - **Verify:** smoke test green after each extraction.

- [ ] **3.3 Extract tabs one at a time** into `gui/tabs/{upload,data,settings,geometry,calculate,results,export}.py`. Each exports a `build(state, ctx)` function called from a slimmed `index()`. Order: start with the most self-contained (`settings`, `data`) before the most entangled (`geometry`, `export`). Commit per tab, smoke test between.

- [ ] **3.4 Final `app.py` shape:** `index()` builds layout + `PageContext`, then calls each tab's `build()`. `run_gui()` and `ui.run()` stay. Target < 250 lines.

**Phase 3 exit:** `app.py` < 250 lines; each tab is an independently readable module; GUI smoke test green.

---

## Phase 4 — Lower-priority cleanups (opportunistic)

Not scheduled; pick up when touching the relevant area.

- [ ] **4.1** Split `constants.py` into `physics_constants.py` + `lookup_tables.py`.
- [ ] **4.2** Add a shared figure-style helper for the `plotting/` modules (colors, fonts, layout defaults) so style changes touch one file.
- [ ] **4.3** Add a `schema_version` field to JSON export output for downstream consumers.
- [ ] **4.4** Replace lower-level broad `except Exception` in adapter/geometry internals with specific exception types (keep broad catches only at I/O boundaries).

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
