# Kerma-Meter CF Workflow Plan (file + prompt-on-miss, per-tube dose)

Status: Active execution plan — not started
Created: 2026-10-06
Owner: maintainer
Builds on: [archive/KERMA_METER_CORRECTION_FACTORS_PLAN.md](archive/KERMA_METER_CORRECTION_FACTORS_PLAN.md)
(shipped engine, file loader, identity resolution) and
[archive/CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md](archive/CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md).
Related: [TO_DO.md](../TO_DO.md) — *Biplane support and recognition*;
[CUSTOM_EQUIPMENT_PROFILES_PLAN.md](CUSTOM_EQUIPMENT_PROFILES_PLAN.md) (separate concept; do not merge).

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
- Radimetrics input reads the total reference-point dose and ignores its per-plane A/B columns
  (`input_adapters/radimetrics.py:81-90`). A Radimetrics export without a plane column defaults every
  event to `"Single Plane"` (`radimetrics.py:210-213`). DoseTrack raises an error for unmapped numeric
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
   Then compare the detected pairs with the selected file. Detection uses the `explicit_label` keys when
   a label is set, and the existing collapse confirmation still applies.
3. **Prompt on miss.** Open the dialog when a detected pair is missing from the file, or when no file is
   selected. The dialog lists every detected pair and groups the rows by exam. Rows from the file are
   pre-filled and labelled "from file". Missing rows are pre-filled with `default_factor` and flagged.
   A Settings toggle, "Ask for missing correction factors", controls this dialog and defaults to on.
   "Don't ask again this session" follows the existing suppression pattern of the rotational and
   below-floor prompts.
4. **Cancel semantics.** Cancel sets only the unanswered missing pairs to `default_factor`. File values
   and earlier manual entries are kept. At Calculate, the dialog re-opens once if pairs are still
   unconfirmed. The run never blocks.
5. **Unresolved equipment.** For events with no equipment identity, the dialog asks the user to choose
   a label for each exam. The label can be a detected unit, a file entry, or new text. The chosen label
   is stored as a per-exam identity override. Then the engine looks up the table for those events
   instead of skipping them.
6. **Tube identification.** Show tube `unknown` as a visible state in the dialog and in Results. The
   engine bookkeeping already exists. Fix the Radimetrics adapter so a biplane export maps its per-plane
   A/B dose columns to separate events or rows, instead of reading only the total. A biplane Radimetrics
   export with no plane column must give `unknown`, not `Single Plane`.
7. **Per-tube dose.** Accumulate one partial dose map for each tube (`single`, `A`, `B`, `unknown`) in
   addition to the combined map. Report, for each tube: reported kerma, corrected kerma, applied CF, and
   the peak of that tube's partial map. A tube that misses the phantom reports zero. The combined map is
   still the sum over all events from both tubes, and the headline PSD is still the peak of the
   combined map. Per-tube peaks do not, in general, sum to the headline PSD, and the UI must say so.
8. **CLI parity.** `--kerma-meter-correction-file` keeps working. Non-GUI runs never prompt. Each run logs
   one warning with the count of missing pairs, never the labels, and uses `default_factor`.

## Out of scope

- Beam-quality-dependent (kVp/filter) CF bands. These remain out of scope, as in the archived plan §11.
- Fully independent biplane geometry modelling. That stays in the *Biplane support* backlog item.
  Step 7 reuses the existing per-event geometry.
- Persisting manual entries back into the user's calibration file. Offer "Save as calibration file"
  as an explicit export only.

## Phases

| Phase | Deliverable | Acceptance |
|---|---|---|
| 0 | Audit tube identity per adapter, then fix the Radimetrics per-plane split and its missing-plane default. | An audit table exists. Passing tests show a synthetic biplane Radimetrics export yields A and B events, and that bundled fixtures are unchanged. |
| 1 | Settings: remove the exclusive mode and add the legacy `mode` / CLI shim. | Unit tests cover manual > file > default, the legacy round-trip, and the default factor. |
| 2 | Engine: a `missing_keys(detected, table)` helper and per-exam identity overrides for unresolved equipment. | Unit tests cover a file hit, a file miss, no file, an `unknown` tube, and an overridden unresolved unit that reaches the table. |
| 3 | GUI: load-time detection, the dialog with file pre-fill, the Settings toggle, session suppression, and the Calculate guard. | GUI tests in `tests/gui/` show that a miss opens the dialog, a full hit skips it, the toggle off skips it, and Cancel keeps file and earlier values. |
| 4 | Per-tube partial maps and totals in Results and in the HTML/XLSX/DOCX/PDF exports. | On a synthetic biplane fixture, A and B maps sum cell by cell to the combined map. Headline PSD equals the combined-map peak. A tube that misses reports zero. Single-plane goldens are unchanged. |
| 5 | CLI warning, docs, glossary, help registry, feature matrix, CHANGELOG. | `check_help_registry.py`, `check_ui_copy.py`, and the doc-freshness check pass. |

## Risks

- Station or serial labels can be site identifiers. Follow the archived plan §14: dialogs may show them,
  but logs report counts only, and per-event exports never carry the labels.
- A load-time dialog could annoy single-plane users who never calibrate. Scope step 3 handles this with
  the Settings toggle and session suppression.
- Per-tube partial maps add memory per run. Allocate a partial map only for tubes actually present.
- Multi-exam runs can detect many pairs. The dialog must scroll.
