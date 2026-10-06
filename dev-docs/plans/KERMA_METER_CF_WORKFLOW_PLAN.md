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

## Current state (verified 2026-10-06)

- `kerma_correction.py` already resolves one CF per event from `(equipment, tube)`. The tube comes
  from `acquisition_plane` (`single` / `A` / `B`). `load_correction_table()` reads CSV/TSV/XLSX/JSON
  with the columns `equipment`, `tube`, `correction_factor`. `merge_tables()` and
  `KermaMeterCorrectionSettings.in_memory_table` let a session table override file keys.
- The settings use `mode ∈ {file, prompt}`, and the two modes are exclusive. In `file` mode a missing key
  silently falls back to `default_factor`, with only a log warning. Nothing prompts the user.
- The GUI prompt (`gui/tabs/calculate.py::kerma_meter_prompt`) runs only at Calculate time. It lists
  every detected pair, pre-fills `default_factor`, and ignores any file values.
- Corrected kerma feeds dose, and the per-event CF column is exported. Results and exports do **not**
  break PSD, dose map, or kerma totals down by tube.
- Biplane recognition is still an open backlog item. Plane identity relies on CID 10003 / DoseTrack
  plane codes, and ambiguous codes resolve to `single`.

## Scope

1. **Unified source model.** Replace the exclusive `file` / `prompt` choice with one table built in
   precedence order: manual entry, then file rows, then `default_factor` (1.0). Keep reading the legacy
   `mode` key, map it onto the new model, and log a deprecation warning.
2. **Detect on load.** After inputs load or change (single or multi-exam), compute the detected pairs
   with `unique_equipment_tube_keys()`. Then compare them with the selected file.
3. **Prompt on miss.** If any detected pair is absent from the file, or if no file is selected, open a
   GUI dialog when inputs load. The dialog lists every detected pair. File-supplied rows are shown
   pre-filled and labelled "from file". Missing rows are pre-filled with `1.0` and marked as needing
   review. Users can still edit the values from Settings before Calculate.
4. **Calculate-time guard.** If pairs are still unconfirmed at Calculate, re-open the same dialog once.
   Cancel proceeds at `1.0`, which keeps the shipped "never block" behaviour.
5. **Per-tube identification.** Confirm that every adapter (RDSR, DoseTrack, Radimetrics, generic,
   normalized) emits `Plane A` / `Plane B` for biplane events. Add a visible "unresolved tube" state
   for events where a biplane unit has an ambiguous plane, rather than silently mapping them to `single`.
6. **Per-tube reporting.** Report cumulative reported kerma, corrected kerma, and applied CF per tube
   in Results and in the Rich Export. Report PSD per tube where both tubes hit the phantom. These are
   supplementary breakdowns only. The cumulative dose map is still summed over all events from both
   tubes on the phantom. The peak cumulative skin dose from that map is still the headline PSD.
7. **CLI parity.** `--kerma-meter-file` keeps working. Non-GUI runs never prompt. Each missing pair is
   listed once in a warning that names the pair count, and the run uses `1.0`.

## Out of scope

- Beam-quality-dependent (kVp/filter) CF bands. These remain out of scope, as in the archived plan §11.
- Fully independent biplane geometry modelling. That stays in the *Biplane support* backlog item.
  Step 6 reuses the existing per-event geometry.
- Persisting manual entries back into the user's calibration file. Offer "Save as calibration file"
  as an explicit export only.

## Phases

| Phase | Deliverable | Acceptance |
|---|---|---|
| 0 | Audit tube identity per adapter and fixture. Record the gaps in this plan. | There is a table of adapter × biplane emission, and the gaps have synthetic tests that are failing or xfail. |
| 1 | Settings model: drop exclusive mode, add precedence merge, add the `mode` shim. | Unit tests cover manual > file > default, legacy `mode` round-trip, and default `1.0`. |
| 2 | Engine: `missing_keys(detected, table)` helper and an "unresolved tube" status. | Unit tests cover a file hit, a file miss, no file, and an ambiguous plane. |
| 3 | GUI: load-time detection and a prompt with file pre-fill, plus the Calculate guard. | GUI tests in `tests/gui/` check that a miss opens the dialog, a full file hit skips it, and Cancel gives `1.0`. |
| 4 | Per-tube totals in Results and in HTML/XLSX/DOCX/PDF exports. | The biplane synthetic fixture shows A/B rows that sum to the combined totals. Single-plane output is unchanged. |
| 5 | CLI warning, docs, glossary, help registry, feature matrix, CHANGELOG. | `check_help_registry.py`, `check_ui_copy.py`, and doc freshness all pass. |

## Risks

- Station or serial labels can be site identifiers. Follow the archived plan §14: dialogs may show them,
  but logs report counts only, and per-event exports never carry the labels.
- A load-time dialog could annoy single-plane users who never calibrate. Add a Settings toggle "Ask for
  missing correction factors" (default on), and remember the choice for each session.
- Multi-exam runs can detect many pairs. The dialog must scroll and group its rows by exam.
