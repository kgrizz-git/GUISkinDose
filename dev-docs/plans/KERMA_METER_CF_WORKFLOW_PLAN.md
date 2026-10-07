# Kerma-Meter CF Workflow Plan (file + prompt-on-miss, per-tube dose)

Status: Active — Phases 0–6 implemented and reviewed on branch `docs/todo-trim-dose-meter-plan` (2026-10-06); closeout pending
Created: 2026-10-06
Owner: maintainer
Builds on: [archive/KERMA_METER_CORRECTION_FACTORS_PLAN.md](archive/KERMA_METER_CORRECTION_FACTORS_PLAN.md)
(shipped engine, file loader, identity resolution) and
[archive/CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md](archive/CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md).
Related: [TO_DO.md](../TO_DO.md) — *Biplane support and recognition*;
[CUSTOM_EQUIPMENT_PROFILES_PLAN.md](CUSTOM_EQUIPMENT_PROFILES_PLAN.md) (separate concept; do not merge).

## Progress (2026-10-06)

Done:
- Phases 0–6 are implemented, reviewed by two outside reviewers, and fixed after review.
- The calibration file and manual entries are unified. Manual entry for an exam wins, then the file row for the
  exam's calibration period, then `default_factor`.
- A load-time dialog asks for missing factors and unchosen calibration periods. Exams can hold different
  factors, and later exams follow the previous exam's entries until edited.
- Per-tube partial dose maps and summaries are in Results and all exports. Exports show the applied CF per exam
  and tube, without equipment labels or calibration dates.
- An example calibration file ships as package data with placeholder dates, and the tests use it.

Smoke tests (2026-10-07):
- Manual, done by the user: (1) the load-time dialog is OK. (2) The example calibration download failed in the
  native window, was fixed (native Save As), and passed on re-test.
- CLI, run through `python -m guiskindose` with the bundled examples (now automated in
  `tests/unittests/test_cli_end_to_end.py`), all passed:
  - Siemens example with the example file and explicit label DEMO-ROOM-1: single tube, CF 1.02 from the file.
  - Older Radimetrics biplane example with the example file and DEMO-ROOM-2: calibration date 1901-06-01 gives
    A 0.98, 1902-06-01 gives A 1.03, B 1.01 from the file either way. With no date the current period applies and
    one count-only warning is logged.
  - No file: one count-only warning, factors `default`, PSD equal to the uncorrected 1.1773 mGy.
  - Both Radimetrics examples: older biplane gives tubes A and B with 4 events each, newer gives one single tube
    with 5 events.
  - `--output-format json` prints `tube_summary` with applied CF, range, and source.
  - `k_tab_mode` through the settings file: `measured_with_fallback` and `measured_only` PSD 1.1773 (all
    `exact`), `estimate` 1.3020; the legacy `estimate_k_tab: true` key maps to `estimate` with the deprecation
    warning.
  - Logs and stderr contain no equipment labels, file names, or paths.
- The CLI smokes found three CLI bugs, fixed in the same change: `--settings` was ignored (the path was never
  read), `python -m guiskindose` never applied the kerma-meter flags or `--plane-code-map`, and a single-file
  run never printed its JSON result (new `--output-format json`).

Browser GUI smokes (2026-10-07, headless Playwright), all passed unless noted:
- The splash lists the Corrections tab, and the Corrections tab layout and the transmission info icon text are right.
- The bundled examples drop-down lists both Radimetrics examples.
- The Review dialog with the example file and explicit label DEMO-ROOM-2 shows the period selector (1902 current,
  1901) and "from file" rows. Switching to the 1901 period changes tube A to 0.98.
- A blank factor blocks Confirm with an inline error. Cancel keeps the file values and earlier entries.
- A second exam (the same biplane example) shows "↳ follows Exam 1" for the manual row, and its period follows.
- The Calculate-time guard re-opens for the unchosen Exam 2 period.
- The per-exam × tube Results block is correct (A 0.98 from the file, B manual).
- A Review edit clears Results; the sidebar PSD stayed stale, which was a bug, fixed 2026-10-07 by a central
  sidebar sync (`sync_sidebar_psd`) that follows every `reset_results()` path. Covered by GUI tests.
- The rich report (HTML and XLSX) has the Dose by tube table with no labels or paths.
- The k_tab mode select: the default falls back to the estimate on this model, and `measured_only` is ×1.25
  (24.36 to 30.45 mGy).
- Cosmetic fix: the dialog now shows equipment labels in their original spelling (matching stays casefolded).

Remaining:
- Manual passes still to do: the new Corrections tab and dialog in the native (pywebview) window, the Windows
  native save dialog, and a visual check of the DOCX and PDF reports.
- Then archive this plan, update `dev-docs/index.md`, and remove the TO_DO item.

Answered (2026-10-07): the Radimetrics `(A)`/`(B)` columns are per-event values, and each real row sits on one
plane. In the older export exactly one of the two cells is filled and equals the total. In the newer export the
sample has plane B empty on every row and A equal to the total. The split therefore produces one event per row
for real files. The adapter and fixtures were updated to match (see the Phase 0 decisions).

## Objective

Let the user supply dose-meter correction factors per individual equipment unit and tube
(`CF = measured dose / reported dose`) either from a selected calibration file or by manual entry for
the equipment detected when inputs load. Any detected `(equipment, tube)` pair missing from the file
prompts for a value. Every unanswered value defaults to `1.0`. Dose from tubes A and B is identified
and reported separately whenever a biplane study is present.

## Current state (verified 2026-10-06, after two plan reviews)

- `kerma_correction.py` resolves one CF per event from `(equipment, tube)`. The tube identity comes from
  `acquisition_plane_canonical` (CID 10003) first, then from `normalize_tube()`. It takes one of four
  values: `single`, `A`, `B`, or `unknown`. Unknown equipment or tube records the event in
  `unresolved_event_indices`. A missing table row records the event in `table_miss_event_indices`. Both
  cases fall back to `default_factor`.
- `load_correction_table()` reads CSV/TSV/XLSX/JSON with the columns `equipment`, `tube`, and
  `correction_factor`. `calculate_dose` already loads the file and merges it with the session
  `in_memory_table` through `merge_tables()`, and the manual entries win.
- The settings still declare `mode ∈ {file, prompt}`. Prompt mode without a confirmed table falls back
  to the default. File mode can open the prompt only through `prompt_at_calc`.
- The GUI prompt (`gui/tabs/calculate.py::kerma_meter_prompt`) runs only at Calculate time. It
  pre-fills every row with `default_factor`, ignores any file values, and Cancel discards all manual
  entries.
- The prompt lists events with no equipment identity under the label `"unresolved"`. The engine passes
  `None` for those events and never consults the table. Any factor typed for them is silently ignored.
- The dose loop accumulates one combined map. The per-event CF column is exported. Nothing reports dose
  by tube.
- Before Phase 0, Radimetrics input read the total reference-point dose and ignored its per-plane A/B
  columns, and a Radimetrics export without a plane column defaulted every event to `"Single Plane"`.
  Phase 0 fixed both (see the audit below). DoseTrack raises an error for unmapped numeric
  plane codes unless the user supplies a mapping. That safeguard stays.
- The CLI flags are `--kerma-meter-correction`, `--kerma-meter-correction-file`,
  `--kerma-meter-correction-mode`, and `--kerma-meter-explicit-label`.

## Scope

1. **Unified source model.** Remove the exclusive `file` / `prompt` mode. The merge engine already
   exists. The order stays: manual entry, then file rows, then `default_factor` (1.0 by default). Keep
   reading the legacy `mode` key and the `--kerma-meter-correction-mode` flag, map them onto the new
   model, and log a deprecation warning.
2. **Detect on load.** When inputs finish loading or change, call `unique_equipment_tube_keys()`. That
   covers single-file and multi-exam loads, and the hook is the point after `gui/helpers.rebuild_rdsr_df()`.
   Then compare the detected pairs with the merged table of session entries and file rows. Detection uses the `explicit_label` keys when
   a label is set, and the existing collapse confirmation still applies.
3. **Prompt on miss.** Open the dialog when a detected pair is missing from the merged table. The dialog
   lists every detected pair and groups the rows by exam. Each row is pre-filled in precedence order:
   an earlier manual entry, then the file value, then `default_factor`. Each row is labelled with its
   source ("entered", "from file", or "default"). Default rows are flagged for review.
   A Settings toggle, "Ask for missing correction factors", controls this dialog and defaults to on.
   "Don't ask again this session" follows the existing suppression pattern of the rotational and
   below-floor prompts.
4. **Cancel semantics.** Cancel sets only the unanswered missing pairs to `default_factor`. File values
   and earlier manual entries are kept. At Calculate, the dialog re-opens once if pairs are still
   unconfirmed. The run never blocks.
5. **Unresolved equipment.** For events with no equipment identity, the dialog asks the user to choose
   a label for each exam. The label can be a detected unit, a file entry, or new text. The chosen label
   is stored as a per-exam identity override. Then the engine looks up the table for those events
   instead of skipping them. The override lives in GUI session state beside the other per-exam
   overrides. It round-trips through `run_state` and settings export with the same privacy handling as
   `explicit_label`, so labels never reach logs or per-event exports.
6. **Tube identification.** Show tube `unknown` as a visible state in the dialog and in Results. The
   engine bookkeeping already exists. Fix the Radimetrics adapter so a biplane export maps its per-plane
   A/B dose columns to separate events, instead of reading only the total. The split replaces the
   total row and is never added to it, so A + B must equal the original total. A biplane Radimetrics
   export with no plane column must give `unknown`, not `Single Plane`. Any gap that the Phase 0 audit
   finds in another adapter must be fixed, or that adapter must be documented as not supporting biplane.
7. **Per-tube dose.** Accumulate one partial dose map for each tube (`single`, `A`, `B`, `unknown`) in
   addition to the combined map. Report, for each tube: reported kerma, corrected kerma, applied CF, and
   the peak of that tube's partial map. A tube that misses the phantom reports zero. The combined map is
   still the sum over all events from both tubes, and the headline PSD is still the peak of the
   combined map. Per-tube peaks do not, in general, sum to the headline PSD, and the UI must say so.
8. **CLI parity.** `--kerma-meter-correction-file` keeps working. Non-GUI runs never prompt. Each exam logs
   one warning with the count of missing pairs, never the labels, and uses `default_factor`.

9. **Per-exam factors and calibration periods.** A dose meter can be recalibrated between exams, so the same
   `(equipment, tube)` may need different factors in different exams. Manual entries are keyed by
   `(exam label, equipment, tube)`, and the engine resolves per exam: manual entry for that exam, then the
   file row for that exam's calibration period, then `default_factor`. The dialog shows rows per exam again.
   Exam 2 and later pre-fill with the value the same pair has in the previous exam and keep following it
   (the row says "follows Exam N") until the user edits that row. The calibration file may carry optional
   `valid_from` / `valid_to` columns (ISO dates, either blank for open-ended). Rows without dates behave as
   before. Overlapping periods for the same pair are a load error. GUISkinDose never reads dates from the
   input data (they are PHI). When the file has dated rows for a detected pair, the dialog shows a
   per-exam "Calibration period" selector listing the file's periods. It defaults to the previous exam's
   choice, and Exam 1 defaults to the most recent period. The choice is stored per exam in the GUI session,
   with the same drift-clearing and run-state privacy handling as the unresolved-equipment labels, and
   never reaches logs or per-event exports. Non-GUI runs have no chooser: `--kerma-meter-calibration-date
   YYYY-MM-DD` picks the period containing that date for every exam. Without it the period with no
   `valid_to` (current) is used, otherwise the most recent, with a count-only warning. A fictional example
   calibration CSV with a README ships as package data and is offered from Settings as a download.

## Out of scope

- Beam-quality-dependent (kVp/filter) CF bands. These remain out of scope, as in the archived plan §11.
- Fully independent biplane geometry modelling. That stays in the *Biplane support* backlog item.
  Step 7 reuses the existing per-event geometry.
- Persisting manual entries back into the user's calibration file. Offer "Save as calibration file"
  as an explicit export only.

## Phase 0 audit: tube identity per adapter

Tube identity is `acquisition_plane_canonical` (CID 10003 code, `single`/`A`/`B`/`unknown`) first, then
`normalize_tube(acquisition_plane)` on the meaning text. Audited 2026-10-06; tests in
`tests/unittests/test_radimetrics_biplane.py` and `tests/unittests/test_input_adapters.py`.

| Adapter | Biplane emission | Gap found | Resolution |
|---|---|---|---|
| DICOM RDSR (`rdsr_parser` + `rdsr_normalizer`) | Yes. CodeValue + `DCM` scheme gives a code-backed canonical `A`/`B`/`single`. Meaning text is kept. | None. A CodeValue without a `DCM` scheme gives `unknown` canonical, then meaning fallback. | No change. |
| DoseTrack | Yes, via CID 10003 integer codes (113620 / 113621 / 113622) in `Plane Code`, canonical resolution `inferred`. | None. Non-CID codes raise unless the user maps them (`dosetrack_plane_code_map`). A missing `Plane Code` column is a required-column error. | No change. The raise-unless-mapped safeguard stays. Tests added for A/B emission. |
| Radimetrics | Before: no. Only the whole-event total was read, so one event stood for both tubes. | (1) Per-plane `Reference Point Dose (A)`/`(B)` (and older `Reference_Point_Dose_(A/B)_mGy`) ignored. (2) A missing plane column silently became `Single Plane`. | Fixed. Rows are split into A and B events that replace the total (kerma conserved). With per-plane evidence, a missing plane column or an unsplittable row gives `unknown`. Without per-plane evidence the `Single Plane` default is kept so single-plane exports and bundled fixtures are unchanged. |
| `generic_rdsr_like` | Yes, by meaning text only (`Plane A`/`Plane B`/`Single Plane`). No code column, so canonical is `unknown` and the engine falls back to the meaning. | The `AcquisitionPlane` column is required, so a file without it errors instead of defaulting. Unrecognized text resolves to `unknown`. | No change. Test added that `Plane A`/`Plane B` resolve to A and B. |
| `normalized` | Yes, by meaning text in `acquisition_plane` (required column). The canonical column is not carried through; the adapter keeps only the mapped columns. | Unrecognized or blank text resolves to `unknown`. A round-tripped canonical column is dropped, but the meaning column carries the same identity. | No change. Documented here. |
| Qaelum / DoseMonitor / DoseWatch stubs | Stub adapters only; they emit no events. | No export fixtures. | Out of scope. Document as single-plane-only until a real adapter lands. |

Decisions for Radimetrics:

- **Evidence rule.** The file is treated as biplane only when both per-plane dose columns exist and at least
  one row has non-zero plane B kerma (A-only and B-only rows then become single-plane events). A file with
  per-plane columns where plane B is all zero or empty is single-plane and stays on the old path. The default `Single Plane` is applied only without that evidence.
- **Conservation.** Per-plane kerma is rescaled to the exported total (accepted when A + B is within 1 % of
  the total, to absorb export rounding). Rows that fail the check, or have missing per-plane values, stay as
  one total row. It keeps a valid plane code from the export, otherwise its plane is unknown.
- **DAP and fluoro time.** Per-plane DAP columns are used when present, otherwise the total DAP is split in
  proportion to kerma. Fluoro time stays on the first event of each row, so procedure totals do not double.
- **Known limitation.** Both split events reuse the single `(RF)` angle, kVp and table columns. Independent
  per-plane geometry stays in the *Biplane support* backlog item.
- **What real exports look like.** Exports seen so far put each event on one plane. In the older underscored
  export exactly one of `Reference_Point_Dose_(A)_mGy` / `(B)_mGy` is filled and equals the total, and rows
  alternate irregularly between A and B. In the newer export plane B is empty and A equals the total (some
  values carry long float noise such as `6.1000000000000000`). The both-planes-filled split is kept as
  defensive handling only; no real export has been seen with both cells filled on one row.
- **Bundled fixtures.** `radimetrics_events_legacy.csv` now follows the older pattern (8 rows, A-only or B-only,
  one event per row, kerma unchanged). `radimetrics_events_a_only.csv` follows the newer pattern (B blank, A =
  Total, noisy floats) and is not split. `radimetrics_events.csv` (no per-plane columns) is unchanged. The
  fixture values are invented.

## Phases

| Phase | Deliverable | Acceptance |
|---|---|---|
| 0 | Audit tube identity per adapter. Fix the Radimetrics per-plane split, its missing-plane default, and every other gap found, or document the adapter as single-plane only. | An audit table exists. Passing tests show that a synthetic biplane Radimetrics export yields A and B events whose kerma sums to the original total, that each fixed adapter emits A and B, and that bundled fixtures are unchanged. |
| 1 | Settings: remove the exclusive mode and add the legacy `mode` / CLI shim. | Unit tests cover manual > file > default, the legacy round-trip, and the default factor. |
| 2 | Engine: a `missing_keys(detected, table)` helper and per-exam identity overrides for unresolved equipment, including their session state and `run_state` round-trip. | Unit tests cover a file hit, a file miss, no file, an `unknown` tube, an overridden unresolved unit that reaches the table, and the override round-trip. |
| 3 | GUI: load-time detection, the dialog with manual > file > default pre-fill, the Settings toggle, session suppression, and the Calculate guard. | GUI tests in `tests/gui/` show that a miss opens the dialog, a full hit skips it, the toggle off skips it, earlier manual values are pre-filled rather than reset, and Cancel keeps file and earlier values. |
| 4 | Per-tube partial maps and totals in Results and in the HTML/XLSX/DOCX/PDF exports. | On a synthetic biplane fixture, the partial maps of all present tubes sum cell by cell to the combined map. Per-tube reported and corrected kerma sum to the combined totals. Headline PSD equals the combined-map peak. A tube that misses reports zero. Single-plane goldens are unchanged. |
| 5 | CLI warning and the documentation checklist below. | Every checklist item is done. `check_help_registry.py`, `check_ui_copy.py`, `sync_gui_help.py`, `sync_ui_copy.py`, `check_feature_doc_matrix.py`, `check_doc_freshness.py`, and `test_psd_algorithm_doc.py` pass. `check_docstring_inventory.py` shows no new gaps. It checks only that docstrings exist, so review NumPy style by hand. |
| 6 | Per-exam manual factors, `valid_from` / `valid_to` calibration periods with overlap validation, the per-exam period selector and follow-previous-exam pre-fill in the dialog, `--kerma-meter-calibration-date`, per-exam missing detection, and `run_state` round-trip of per-exam entries and periods. | Unit tests cover period loading, overlap errors, undated rows unchanged, period selection by date, per-exam manual > file > default, and the CLI date. GUI tests show different values per exam, follow-previous pre-fill, edit propagation that spares edited rows, the period selector default and a choice that changes the factor, and drift clearing. |

Every phase also updates the tests, docs, and docstrings for the code it touches, in the same PR. Do not
defer them to Phase 5. New or changed public functions, classes, and settings fields get NumPy-style
docstrings. Examples are `missing_keys()`, the per-exam identity override, the per-tube map fields, and
the reworked `KermaMeterCorrectionSettings`. Each phase's tests land with that phase. Phase 1 also
updates the argparse help text for `--kerma-meter-correction-mode` to say it is deprecated.

### Documentation checklist

- [x] `dev-docs/PSD_CALCULATION_ALGORITHM.md` describes the per-tube partial maps, and the CF step says
  where the table comes from (Phase 4). A test checks this document against the code.
- [x] `docs/source/gui_help/` covers the load-time dialog, the toggle, Cancel semantics, unresolved
  equipment, and the per-tube Results. Edit only the `docs/source/` copy, never the mirror under `src/guiskindose/gui/help/`. Run
  `scripts/sync_gui_help.py` afterwards (Phases 3–4).
- [x] `dev-docs/ui_copy.json` holds the new dialog, toggle, and warning text. Edit only this canonical copy. Run `scripts/sync_ui_copy.py`
  afterwards (Phase 3).
- [x] `src/guiskindose/settings_example.json` and the settings docstrings show the new settings model and
  the legacy `mode` shim (Phase 1).
- [x] `dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md` describes the Radimetrics per-plane split and the
  `unknown` default (Phase 0).
- [x] `dev-docs/FEATURE_INVENTORY.md`, `dev-docs/CODEBASE_OVERVIEW.md`, `dev-docs/glossary.json`,
  `dev-docs/help_registry.json`, and `dev-docs/feature_doc_matrix.json` list the new settings and outputs.
- [x] `AGENTS.md` reflects the new input and GUI behaviour where it describes kerma-meter CFs,
  Radimetrics, or per-tube outputs.
- [x] `CHANGELOG.md` notes the per-tube outputs, the settings change, the `mode` deprecation, and the
  Radimetrics behaviour change.
- [x] Phase 6: `kerma_meter_correction.md` help, `ui_copy.json`, `INPUT_DATA_FLOW_AND_OFFSETS.md` (file columns), `FEATURE_INVENTORY.md`, `CODEBASE_OVERVIEW.md` (CLI flag), `glossary.json` (calibration period), `AGENTS.md`, and `CHANGELOG.md` describe per-exam factors, calibration periods, the CLI date, and the example calibration file.
- [x] Exports and Results show the applied kerma-meter factor and its source per tube and exam (single-plane too when correction is on), with a range and the kerma-weighted value when a tube's events used several factors, and no equipment labels. Documented in the Results help, `CHANGELOG.md`, and `PSD_CALCULATION_ALGORITHM.md` stage 7.
- [ ] On completion, archive this plan under `plans/archive/`, update `dev-docs/index.md`, and remove the
  TO_DO item.

## Risks

- Station or serial labels can be site identifiers. Follow the archived plan §14: dialogs may show them,
  but logs report counts only, and per-event exports never carry the labels.
- A load-time dialog could annoy single-plane users who never calibrate. Scope step 3 handles this with
  the Settings toggle and session suppression.
- Per-tube partial maps add memory per run. Allocate a partial map only for tubes actually present.
- Multi-exam runs can detect many pairs. The dialog must scroll.
