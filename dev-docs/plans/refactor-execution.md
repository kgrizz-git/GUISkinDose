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

- [ ] **0.3 Add a `_busy` operation guard.** A single boolean on `AppState` (or a module-level `asyncio.Lock`) that `handle_upload`, `load_example`, `_on_sheet_change`, and `do_calculate` check/set, so a second operation can't interleave with one in flight. This is the cheap mitigation for the shared-state concern (§5 of the assessment) without a full state redesign.
  - **Verify:** trigger two uploads in quick succession; confirm the second is rejected/queued rather than interleaving.

**Phase 0 exit:** `pytest tests/` green, GUI launches, manual upload + example load both work.

---

## Phase 1 — Test backfill for silent-correctness modules

These modules produce numbers, not errors — a regression is invisible. Pin their current behavior **before** any later phase touches them.

- [ ] **1.1 `rdsr_normalizer.py` characterization tests.** Use the bundled RDSRs (`example_data/RDSR/`). For each of `siemens_axiom_artis.dcm`, `philips_allura_clarity_u104.dcm`, `philips_allura_clarity_u601.dcm`: parse → normalize → assert exact `Tx`, `Ty`, `Tz`, `Ap1`, `Ap2` for the first N events against values captured from current output. (We already verified Philips u104 gives Tx≈8.1, Tz≈-20.9 earlier — reuse that as a known-good anchor.)
  - **Verify:** tests pass against current code; deliberately flip a `trans_dir` sign locally and confirm a test fails.

- [ ] **1.2 `format_export_data.py` tests.** Cover JSON export structure, NaN handling, and the tabular-provenance embedding in both JSON (`tabular_input` key) and HTML (`<head>` comment). Assert round-trip: export → re-read → key fields match.
  - **Verify:** tests pass; corrupt the HTML head-injection locally and confirm a test catches it.

- [ ] **1.3 (optional) `rdsr_parser.py` tests.** Assert the parser extracts the expected table-position columns from each bundled RDSR. Lower priority — parser bugs tend to surface as missing-column errors rather than silent wrong numbers.

**Phase 1 exit:** new tests committed and green. These become the safety net for everything below.

---

## Phase 2 — Adapter consolidation

All four real adapters share steps 1–3 and 7 (assessment §3). Migrate incrementally so adapters are never collectively broken.

- [ ] **2.1 Extract the shared pipeline.** Create `input_adapters/base.py` with `run_pipeline(loaded, known_names, patterns, transform_fn, original_filename, settings)` that owns: header detection, column mapping, duplicate-mapping check, and provenance/result construction. `transform_fn` is the per-adapter callback that does numeric coercion + unit conversion + vendor specifics.

- [ ] **2.2 Migrate one adapter (`radimetrics`) onto `base`.** Leave the other three untouched.
  - **Verify:** `pytest tests/unittests/test_input_adapters.py` green (the Radimetrics tests now exercise the shared pipeline).

- [ ] **2.3 Migrate `dosetrack`, `generic_rdsr`, `normalized`** one commit each, running the adapter test suite after each.

- [ ] **2.4 Collapse the three stubs.** Replace `qaelum.py`, `dosemonitor.py`, `dosewatch.py` bodies with a single `_stub_adapter(vendor_name)` factory (in `base.py` or a `stubs.py`) that raises `NotImplementedError` with the implementation instructions. Registry wiring stays the same.
  - **Verify:** selecting each stub schema still raises the instructive `NotImplementedError`; the existing stub tests pass.

- [ ] **2.5 Move per-vendor column sets out of `column_mapper.py`.** Relocate `NORMALIZED_COLUMN_NAMES`, `GENERIC_RDSR_COLUMN_NAMES`, `RADIMETRICS_COLUMN_NAMES`, `DOSETRACK_COLUMN_NAMES` (and their `*_PATTERNS`) into their adapter modules. `column_mapper.py` keeps only the generic engine (`_normalize_str`, `_score_row`, `detect_header_row`, `map_columns`, `check_duplicate_mappings`). Update `registry.py`'s `_SCHEMA_KNOWN_NAMES` imports.
  - **Verify:** auto-detection still resolves each fixture to the right schema; full adapter suite green.

**Phase 2 exit:** `column_mapper.py` is the generic engine only; each adapter is its own column knowledge + a thin transform fn; stubs are one file. Net line reduction expected.

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
