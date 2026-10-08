# Tabular Import Options — CLI/API Parity Plan

Status: Active execution plan
Created: 2026-10-08
Branch: `feat/tabular-import-options-cli`
Parent: [TABULAR_RDSR_INPUT_PLAN.md](TABULAR_RDSR_INPUT_PLAN.md)
Related: [VENDOR_COORDINATE_SYSTEMS.md](../VENDOR_COORDINATE_SYSTEMS.md),
[TO_DO.md](../TO_DO.md)

Reviewed 2026-10-08 (Composer vs current code): architecture kept; contracts below
are the review edits (copy-based apply, full API threading, non-tabular rejection
before the RDSR branch, mixed-batch rule).

## Objective

Give the Python API and headless CLI the same **expert post-normalization**
coordinate overrides the GUI already has: `Tx ↔ Tz`, `Ap1×−1`, and `Ap2×−1`.

This is not a new physics path. It applies the same involutions the GUI applies
in `gui/exam_transforms.py` after the adapter and `rdsr_normalizer()` have
produced the internal DataFrame.

## Why a separate execution plan

The 2026-06 `TabularImportOptions` sketch in the parent plan does **not** match
the shipped GUI:

| Sketch (parent plan) | Shipped GUI |
|---|---|
| `swap_lateral_longitudinal` | `swap_lat_lon` (`Tx ↔ Tz` after normalize) |
| `skip_manufacturer_transforms` | not a GUI toggle |
| `custom_translation_offset` | table-origin sliders, not an import dataclass |

`swap_lateral_longitudinal` on a manufacturer profile is a **different** switch:
it runs inside `rdsr_normalizer()` (GE wildcard). The GUI expert `Tx ↔ Tz`
toggle is a manual post-normalization override and defaults **off**, including
for GE (`import_preview.set_transform_defaults`; label "GE lat/lon handled in
normalization").

This plan implements GUI parity. It does not revive `--skip-transforms`.

## Verified current state

- GUI applies flags via `_apply_transform_flags()` in this order on a
  `base.copy()`: `flip_tx/ty/tz` (skipped for `normalized`) →
  `table_origin_override` → `swap_lat_lon` (skipped for `normalized`) →
  `Ap1`/`Ap2` negation whenever those columns exist. Each of the three CLI
  flags is an involution from pristine `base_data`.
- GUI also has `flip_tx`/`flip_ty`/`flip_tz` and `table_origin_override`. Those
  stay GUI-only in this delivery.
- `_apply_transform_flags` lives under `gui/` (optional extra). Core and CLI
  must not import it. GUI *may* import core `input_adapters`.
- CLI already has `--input-schema`, `--sheet-name`, `--input-preview-only`.
  `read_and_normalize_input()` has no import-options argument.
- DICOM RDSR / JSON never go through the tabular adapter.
  `_read_input_for_analysis` (`main.py`) branches to
  `read_and_normalise_rdsr_data` when the suffix is not tabular. Rejection of
  flags on those paths **must** happen before that branch, or flags silently
  no-op — the opposite of fail-loudly.
- `read_and_normalize_input` call sites in `main.py`: `_read_input_for_analysis`,
  `analyze_multiple_input_files`, `preview_input_file`, `build_cli_export_source`
  (probe + single-exam load), `_load_inputs_for_export`. Six sites. CLI
  dispatch also exists in `__main__.py` (must stay in lockstep with `main.py`
  `__main__` block).
- GUI `exam_loaders._parse_tabular` calls `read_and_normalize_input` **without**
  options, then applies GUI flags from pristine `base_data`. Do **not** pass
  `import_options` from the GUI (that would double-apply).

## Decisions

1. **Three flags, GUI names.** `swap_lat_lon`, `flip_ap1`, `flip_ap2`. Do not
   reuse `swap_lateral_longitudinal` (that name belongs to manufacturer
   normalization).
2. **Defaults all false.** No manufacturer auto-enable on CLI/API.
3. **Same apply rules as the GUI** for those three flags, including "swap is a
   no-op on the `normalized` schema; angle flips still apply if columns exist."
4. **Extract, don't duplicate.** New core module
   `src/guiskindose/input_adapters/import_options.py` holds the dataclass,
   `any_set()`, and the three-flag apply helper (plus the Tx/Tz swap primitive).
   Do not bloat `models.py`. GUI `_apply_transform_flags` still applies
   `flip_tx/ty/tz` and `table_origin_override` **first** (existing order), then
   calls the helper for swap + angle flips. Fix the `_apply_transform_flags`
   docstring while touching it: only swap and `flip_t*` are schema-gated;
   angle flips are not.
5. **Copy, then assign.** The apply helper always starts from `df.copy()` and
   returns a new frame. `read_and_normalize_input` assigns
   `result.normalized_data = apply_...(result.normalized_data, schema, options)`
   for each result (including each element of a list). Do **not** mutate
   adapter frames in place. All-false / `None` is a numeric identity (values
   match; object identity need not).
6. **Non-tabular rejection.** If any flag is true and any resolved path is not
   tabular (suffix not in `.csv`/`.tsv`/`.xlsx`/`.xlsm`), raise
   `UserFacingInputError` with a **fixed** message (no paths, filenames, or
   values). Call this **before** I/O / before `_read_input_for_analysis`
   branches to RDSR. Mixed multi-file runs: global flags + any non-tabular
   path → reject the whole batch. CLI `__main__.py` and `main.py` `__main__`
   catch it like export-flag validation: print
   `exc.user_message()` (or `safe_user_error("invalid_import_options")` if not
   already a `UserFacingInputError`) and `SystemExit` / `sys.exit(1)` so no
   calculation runs.
7. **Full Python API, not only the registry.** Optional
   `import_options: TabularImportOptions | None = None` on:
   - `read_and_normalize_input` (all four `@overload`s + implementation)
   - `analyze_input_file`
   - `analyze_multiple_input_files`
   - `preview_input_file`
   - `build_cli_export_source`
   - `run_cli_export`
   - `_read_input_for_analysis` / `_load_inputs_for_export` (internal)
   `None` equals all-false. Public re-export `TabularImportOptions` from
   `guiskindose.input_adapters`.
8. **Multi-exam tabular:** the same options apply to every split result, using
   each result's `provenance.schema_name`. Per-exam CLI flags are out of scope.
9. **`--input-preview-only`:** print a count-only line that overrides were
   applied (which flags, not values or filenames). Use `print`, matching
   `_print_input_preview` (value-safe; no logging of identifiers).
10. **One CLI constructor.** `import_options_from_args(args) -> TabularImportOptions`
    in `import_options.py` (or `cli_args.py` if that avoids a core→argparse
    dependency — prefer no argparse in `input_adapters`; a tiny helper in
    `cli_args.py` or `main.py` is fine). Every CLI branch that loads tabular
    input uses that one object.

## CLI

```
--swap-lat-lon    post-normalization Tx ↔ Tz (expert override; default off)
--flip-ap1        negate Ap1 (primary angle)
--flip-ap2        negate Ap2 (secondary angle)
```

`store_true`. Help text must say these are post-normalization expert overrides,
not the GE manufacturer `swap_lateral_longitudinal` rule.

Add the flags in `cli_args._add_input_args`.

## API

```python
@dataclass(frozen=True)
class TabularImportOptions:
    swap_lat_lon: bool = False
    flip_ap1: bool = False
    flip_ap2: bool = False

    def any_set(self) -> bool:
        return self.swap_lat_lon or self.flip_ap1 or self.flip_ap2
```

Apply helper (core, no `gui` import):

```python
def apply_tabular_import_coordinate_options(
    df: pd.DataFrame,
    schema_name: str,
    options: TabularImportOptions | None,
) -> pd.DataFrame:
    """Return a copy of ``df`` with the three expert flags applied.

    Swap is a no-op when ``schema_name == "normalized"``. Angle negation runs
    whenever the column exists. ``None`` / all-false is a numeric identity.
    """
```

Fixed rejection message (code-owned labels only):

```
Coordinate import flags (--swap-lat-lon, --flip-ap1, --flip-ap2) apply only to
tabular inputs (.csv, .tsv, .xlsx, .xlsm).
```

## Out of scope

- `--skip-transforms` / bypassing `rdsr_normalizer()` coordinate steps
- `custom_translation_offset` (custom equipment profiles)
- CLI for `flip_tx`/`ty`/`tz` or table-origin override
- Changing GUI defaults or layout
- Passing `import_options` from GUI loaders
- Radimetrics schema-detection scoring

Those remain on `TO_DO.md` if still wanted after this ships. Drop
`--skip-transforms` from the TabularImportOptions backlog wording so it does
not keep advertising an unimplemented flag.

## Phases

### 0 — Extract core helper (no CLI, no registry argument yet)

- [ ] Add `src/guiskindose/input_adapters/import_options.py` with
      `TabularImportOptions`, `any_set()`, `apply_tabular_import_coordinate_options`,
      and the Tx/Tz swap primitive.
- [ ] Re-export `TabularImportOptions` from `input_adapters/__init__.py`.
- [ ] `exam_transforms._apply_transform_flags` keeps origin/`flip_t*` locally,
      then delegates swap + Ap1/Ap2 to the helper. Fix the docstring (angle
      flips are not skipped for `normalized`).
- [ ] Unit tests in `tests/unittests/` (must not import `guiskindose.gui`):
      each flag, combined, `normalized` swap no-op, angle flip on `normalized`
      if columns exist, all-false numeric identity, missing Ap columns are
      skipped, copy (input frame unchanged).
- [ ] Existing GUI transform tests stay green (`tests/gui/test_multi_exam_gui.py`
      and related). No CLI flags yet.

### 1 — Registry API

- [ ] `read_and_normalize_input(..., import_options=None)` on every overload
      and the implementation. After adapter dispatch, apply options to each
      result's `normalized_data` using that result's `provenance.schema_name`.
- [ ] Unit tests through `read_and_normalize_input` on a small in-memory or
      existing tabular fixture: same matrix as Phase 0 plus a multi-study
      list (same options on each exam). All-false / `None` leaves values
      unchanged vs today's behavior.

### 2 — CLI + `main`

- [ ] Three `store_true` flags on `_add_input_args`; `import_options_from_args`.
- [ ] Thread `import_options` through `analyze_input_file`,
      `analyze_multiple_input_files`, `preview_input_file`,
      `build_cli_export_source`, `run_cli_export`, `_read_input_for_analysis`,
      `_load_inputs_for_export`. Probe + load in `build_cli_export_source`
      must use the **same** options object.
- [ ] `reject_import_options_for_non_tabular(paths, options)` before I/O.
      Mixed batch: any flag + any non-tabular path → `UserFacingInputError`.
- [ ] Wire CLI in **both** `__main__.py` and `main.py` `__main__` so preview,
      single-file analyze, multi-file analyze, and export all pass options.
      Map rejection to a usage-level exit (no calc).
- [ ] Preview prints a count-only override note (flag names only).
- [ ] Tests: CLI parse of the three flags; DICOM/JSON + any flag → usage
      error (no calc); mixed tabular+`.dcm` + flag → reject; tabular fixture
      `--swap-lat-lon` actually swaps `Tx`/`Tz`; `normalized` swap no-op +
      angle flags still negate. Core tests without the `gui` extra.

### 3 — Docs

- [ ] `VENDOR_COORDINATE_SYSTEMS.md`: replace the backlog sketch and
      `--skip-transforms` with the three shipped flags / dataclass. Point at
      this plan until archived, then the archive path.
- [ ] Parent `TABULAR_RDSR_INPUT_PLAN.md`: keep the "implemented against GUI
      names" pointer; drop `--skip-transforms` from advertised CLI.
- [ ] `FEATURE_INVENTORY.md`, `AGENTS.md` CLI list, `CODEBASE_OVERVIEW.md`
      flag table, CLI `--help` text.
- [ ] `CHANGELOG.md` Unreleased (user-facing CLI/API).
- [ ] `dev-docs/feature_doc_matrix.json` / help registry only if those
      checkers require an entry for new CLI flags.
- [ ] Remove this item from `TO_DO.md` when Phases 0–2 are done. Archive
      this plan under `dev-docs/plans/archive/` and update `dev-docs/index.md`
      in the same change.

## Acceptance

- Headless run of a non-`normalized` tabular fixture with `--swap-lat-lon`
  swaps `Tx`/`Tz` vs the same run without the flag; PSD may change.
- `--flip-ap1` / `--flip-ap2` negate those columns.
- `normalized` schema: `--swap-lat-lon` does not swap; angle flags still negate.
- `.dcm` or `.json` plus any of the flags exits with a usage-level error (no
  calc). Mixed multi-file with a non-tabular path and any flag set does the same.
- `analyze_input_file(..., import_options=...)` and `run_cli_export(..., import_options=...)`
  honor the flags.
- Core tests pass without the `gui` extra.
- GUI transform tests still pass (shared helper, same numeric result).
- GUI loaders still do not pass `import_options`.

## File map

| File | Role |
|---|---|
| `src/guiskindose/input_adapters/import_options.py` | Dataclass + apply helper + (optional) reject helper |
| `src/guiskindose/input_adapters/__init__.py` | Re-export `TabularImportOptions` |
| `src/guiskindose/input_adapters/registry.py` | `import_options` argument; copy-assign after dispatch |
| `src/guiskindose/gui/exam_transforms.py` | Delegate swap + angles; keep origin/`flip_t*` |
| `src/guiskindose/cli_args.py` | Three `store_true` flags; ctor helper if kept here |
| `src/guiskindose/main.py` | Thread options; reject non-tabular; preview note |
| `src/guiskindose/__main__.py` | Pass options on every load path |
| `tests/unittests/` | Apply matrix + registry + CLI parse/load (no `gui`) |
| `tests/gui/` | Existing transform tests remain the GUI regression |

C901 ≤ 10; no `gui` import from `input_adapters` or `main`. Never log or print
filenames, paths, or event values for these flags.
