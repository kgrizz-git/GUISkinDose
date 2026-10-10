# Custom Equipment Profiles — Design Spec

Status: **Design spec**, reviewed 2026-10-09 (kiro/gpt-5.6-sol). Execution plan:
[CUSTOM_EQUIPMENT_PROFILES_EXECUTION_PLAN.md](CUSTOM_EQUIPMENT_PROFILES_EXECUTION_PLAN.md)
Created: 2026-09-08 · renamed from `CUSTOM_EQUIPMENT_PROFILES_PLAN.md` on 2026-10-09
Parent roadmap: [CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md](CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md)
Dependencies:
[archive/CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md](archive/CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md)
and [CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md](CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md)

## 1. Objective

Let users add validated, reusable equipment/model profiles for coordinate normalization and
patient-support transmission without editing bundled files or rebuilding/replacing the complete
correction database.

This spec does not implement a new path-length attenuation model. Custom transmission rows use the
validated lookup semantics established by the preceding plans.

## 2. Current state

- Coordinate normalization ships bundled manufacturer/model profiles in
  `src/guiskindose/normalization_settings.json` (Siemens AXIOM-Artis, Philips Allura Clarity, the GE
  wildcard, Default), read through `settings/normalization_settings.py`.
- Coordinate profile selection is **once per exam/frame, not per event**: `update_used_settings()`
  reads manufacturer and model from the first row, selects one profile, and the normalizer applies it
  to the whole frame. An input whose raw rows carry conflicting equipment identities must be split
  into exams or rejected before normalization; v1 does not redesign per-event transforms.
- Python callers can pass custom `NormalizationSettings`, but ordinary settings JSON, CLI, and GUI do
  not expose a persistent profile file. The GUI's hidden run-configuration route (`gui/run_state.py`,
  `gui/settings_builder.py`) imports a normalization-profile list and should be migrated onto the
  first-class profile loader.
- Normalized frames currently carry `model`; `manufacturer` is not part of the normalized contract.
  v1 adds a canonical manufacturer field (with a warned legacy compatibility path) plus a stable
  `profile_id` for reporting and exports.
- Custom `k_tab` is limited to one global estimated transmission (`k_tab_mode: estimate` /
  `k_tab_val`; the shipped default is `measured_with_fallback`) or a full replacement SQLite database
  (`corrections_db_path`, which also supplies HVL and `k_med` tables).
- Kerma-meter correction already supports validated user files keyed by individual equipment and
  tube; it is a loading/validation precedent but remains a distinct calibration concept (§4).
- `k_tab` baseline lookup matches on model (plus a de-spaced spelling) and the literal
  acquisition-plane string, scanning the table per event.

## 3. What a profile contains

A profile file is one user-owned, versioned JSON document describing **one or more equipment
models**. It has three parts: metadata/provenance, a coordinate-normalization block, and a
patient-support transmission block.

| Profile field | Engine hook (today) | Applied when |
|---------------|--------------------|--------------|
| `manufacturer`, `models[]`, `aliases[]` | `normalize_manufacturer_key` / `normalize_model_key` in `settings/normalization_settings.py` | Coordinate selection occurs **once per homogeneous exam/frame** using its canonical manufacturer/model identity; mixed coordinate identities are split or rejected before normalization |
| `translation_offset` (x/y/z, cm) + `translation_direction` (±) | `settings/translation_offset.py`, `rdsr_normalizer.py`, tabular adapters | Table-origin rebasing for every event of the frame; **re-bases the whole table geometry** |
| `rotation_direction` (Ap1..At3, ±) | `NormalizationSettings.update_used_settings` | Per-event angle sign convention |
| `swap_lateral_longitudinal` | `NormalizationSettings.swap_lateral_longitudinal` (GE) | Raw longitudinal/lateral readout mapping, per event |
| `field_size_mode` (`CFA`/`ASD`) | `geom_calc` field-area scaling | Changes beam extent (`FS_lat`/`FS_long`), hit selection, field area, `k_bs`, `k_med`, and which cells receive `k_isq` |
| `detector_side_length` | `beam_class` detector geometry | Detector visualization only — **not** dose-affecting; reported separately from dose-affecting fields |
| transmission rows: `device_model`, `acquisition_plane` (`Single Plane`/`Plane A`/`Plane B`), `kvp_kv`, `filtration_added_mmcu`, `filtration_added_mmal`, `k_patient_support` ∈ (0, 1], `comment` | `corrections.calculate_k_tab()` reading the `correction_table_and_pad_attenuation` table | Dose accumulation; the factor is applied only to hit cells classified by the current `check_table_hits()` table-surface intersection, and the scalar represents **combined table-and-pad** transmission (no pad-specific or path-length model) |

Transmission rows are the user-supplied counterpart of
`table_data/correction_table_and_pad_attenuation.csv`. Each row must carry a measured/estimated
status (`evidence_status: measured | estimated`) and a bounded source note; unmeasured guesses are
not accepted silently — the UI and exports label the status, the same way kerma-meter CFs do today.

The global estimated override (`k_tab_mode: estimate` / `k_tab_val`, which applies one value to every
table-intersected event) stays exactly where it is: a coarse session override that bypasses all
measured tables, not a profile concept.

Cut from v1 (reserved for a later schema version): `anode_angle_deg` (needs the angle-aware HVL
lookup backlog item first) and the individual-equipment transmission key (unresolved privacy and
precedence complexity).

## 4. What a profile deliberately does NOT contain

| Data | Where it lives | Why it is not a profile field |
|------|----------------|------------------------------|
| Kerma-meter correction factors | user calibration file (`kerma_correction.py`): `equipment`, `tube`, `correction_factor`, optional `valid_from`/`valid_to` | Equipment × tube **calibration** records with validity periods, not equipment design properties. Profiles may share generic safe file-reading utilities only — never CF identity or factor validation (kerma CFs need only be finite and positive and may exceed 1.0; support transmission must be in (0, 1]). |
| Backscatter `k_bs`, medium `k_med` | `correction_medium_and_backscatter` table, keyed by (field side length, kVp, HVL) | Keyed by beam/field geometry, not by equipment. An equipment key would be a category error. |
| HVL grid | `hvl_combined`, keyed by (kVp, filtration, anode angle) | Beam-quality keyed; only the anode angle is a device attribute, and that is deferred to a later schema version. |
| `k_isq`, inverse-square, below-floor kVp policy, phantom scaling | settings / geometry | Neither equipment-keyed nor vendor-convention data. |
| Per-case patient / table-origin nudges | Geometry tab per-exam sliders, Settings → Per-exam corrections | Session decisions for one study, applied **after** the reusable profile baseline. A profile supplies the per-equipment default; the session override still wins for that run. |
| Custom HVL / `k_med` tables | explicit `corrections_db_path` | Out of profile scope; see §8 on SQLite coexistence. |

## 5. Profile model and file format

- [ ] **v1 is one self-contained JSON document.** No CSV sidecar in v1: a sidecar complicates
  atomicity, path traversal, relocation, hashing, and provenance. Document shape:
  `schema_version`, bounded `profiles[]` each with a stable `profile_id`, an optional alias list,
  a coordinate block, inline transmission-row objects, and a provenance block (source/reference,
  `evidence_status` per row, dates, bounded notes).
- [ ] The coordinate block is backward-compatible with the bundled entry fields: `manufacturer`,
  `models`, `translation_offset`, `translation_direction`, `rotation_direction`, `field_size_mode`,
  `detector_side_length`, and optional `swap_lateral_longitudinal`. `profile_id`, aliases,
  provenance, and transmission rows are new profile-schema fields, not bundled normalization fields.
- [ ] Reject unknown fields in v1 (add them deliberately in later schema versions).
- [ ] Manufacturer/model matching with aliases, and an optional manufacturer wildcard only when
  deliberately declared (mirrors the bundled GE wildcard).
- [ ] Transmission rows keyed by the minimum scientifically justified identity: manufacturer/model,
  tube/plane when required, kVp, Cu, Al. "Support profile" as a separate key is **removed** from v1
  unless given a concrete definition.
- [ ] A complete valid example document and several invalid examples ship with the spec/plan evidence.

## 6. Loading, validation, and precedence

- [ ] Treat profile files as untrusted input: allowlisted extensions, bounded bytes/rows/text, strict
  schema, finite/ranged values, duplicate rejection, and no executable deserialization. Row/byte
  bounds mirror the kerma-file loader (`_MAX_TABLE_ROWS`).
- [ ] Reject non-finite, non-positive, and greater-than-one transmission values. Values above `1.0`
  are unphysical for a patient support and produce unsupported dose inflation, so they must not be
  accepted as a user override.
- [ ] Canonicalize manufacturer/model/tube identifiers without silently merging ambiguous aliases.
- [ ] Never mutate bundled data or the source profile during a run.
- [ ] Resolution uses **two independent ladders**, not one:
  - **Coordinates:** custom exact > bundled exact > custom wildcard > bundled wildcard > warned
    Default. A custom wildcard may replace a bundled exact only with an explicit override
    declaration and a pre-calculation acknowledgement.
  - **Transmission:** `k_tab_mode: estimate` ignores profile rows entirely; measured modes resolve
    eligible custom **measured** rows first, then the selected baseline provider (bundled table or
    explicit SQLite), then the existing interpolation/clamping/fallback chain. Custom **estimated**
    rows fill coverage gaps by default and never silently replace a measured row.
  - **Session transforms:** always applied after the reusable profile baseline, exactly once.
  - File order never silently resolves a duplicate claim; canonical duplicates fail at load, and GUI
    enable/disable or an explicit override declaration resolves them.
- [ ] Every active, dose-affecting custom value is reported before calculation and recorded in
  exports — not only shadows of bundled exact matches: translation offset/direction, rotation
  direction, axis swap, field-size mode, and custom `k_tab` rows. A custom profile replacing the
  Default profile is also dose-affecting. Loaded-but-unused profiles are listed separately, without
  a dose warning.
- [ ] Detect conflicts between multiple custom profiles (two profiles claiming the same
  manufacturer/model) before calculation and require explicit resolution — never a silent merge.
- [ ] Report matching through a **structured match record** (the runtime currently exposes only
  `Matched` / `Fallback`, which is not enough): `profile_id`, `source = custom | bundled | default`,
  `level = exact | wildcard | default`, `matched_input_key`, and `affected_event_count`, kept
  separate from `k_tab` statuses (exact / interpolated / clamped / fallback). Results are shown per
  exam before aggregate totals.
- [ ] Transmission resolution is served from an index compiled by canonical
  manufacturer/model/plane — not a per-event full-table scan, given the row bound.

## 7. API, CLI, and GUI

- [ ] One shared profile loader used by Python API, settings JSON, CLI, and GUI.
- [ ] CLI/settings options for one or more profile paths with deterministic precedence (for example
  a repeatable `--equipment-profile PATH` and an `equipment_profiles` settings key).
- [ ] GUI import, validation preview, enable/disable, and removal controls, in a dedicated
  discoverable Equipment Profiles card showing active / unused / conflict states.
- [ ] **Activation and staleness:** the first slice allows profile import only before data load. Any
  later post-load activation must atomically re-normalize every affected exam, rebuild the pristine
  baseline, recompute detected origins, reapply session overrides, clear results and preview caches,
  and refresh all tabs — or roll back. Activation and invalidation are one inseparable change.
- [ ] Before calculation, show:
  - actual manufacturer/model/tube identity;
  - matched profile and match level (structured record, per exam);
  - coordinate axis/sign/origin rules;
  - transmission source and measured/estimated status;
  - interpolation/clamping/fallback status.
- [ ] Allow users to save a session correction as a reusable profile only after supplying required
  identity and provenance fields, and only for equipment-design decisions (table origin, axis signs),
  never for patient-specific positioning.
- [ ] Provide export/reload of profiles and an audit summary.
- [ ] Privacy classification applies to every profile field: safe audit metadata, sensitive
  identifier, or never-exported source detail. Logs and errors carry error codes, row indices, field
  names, and counts only — never raw station/serial labels, source paths, or free-text notes.

## 8. Migration and compatibility

- [ ] Keep bundled profiles immutable and unchanged by user imports.
- [ ] Convert existing Python custom normalization input into the shared profile representation or
  provide a documented compatibility adapter, and migrate the hidden run-configuration profile route
  onto the same loader.
- [ ] Keep global estimated `k_tab` as an explicit coarse override, clearly labeled as applying to
  all table-intersected events.
- [ ] **Do not deprecate `corrections_db_path` in this feature.** An explicit SQLite source currently
  replaces HVL, `k_med`, and `k_tab` tables; profiles replace only the coordinate and transmission
  customization. Document coexistence and define the outcome when profile transmission rows and an
  explicit database claim the same key (recommended: reject the combination). Any migration utility
  extracts only `correction_table_and_pad_attenuation` and states plainly that it cannot migrate
  custom HVL or medium data.
- [ ] Default exports and run configurations record profile ID, schema version, content hash, match
  level, and active values — no profile paths, individual-unit identifiers, or unrestricted note
  text. Full profile export is a distinct, explicit user action.

## 9. Tests and acceptance criteria

- [ ] Unit tests: schema versions, aliases, precedence, duplicates, invalid factors, wildcard
  handling, conflict resolution, unknown fields, content hashing, privacy-safe errors, and
  compatibility adapters.
- [ ] API/CLI/GUI parity tests using synthetic, non-identifying profiles.
- [ ] Tests for new model, model alias, exact vs wildcard, A/B/single, unknown identity, profile
  conflict, and mixed matched/unmatched exams (including excluded/failed exams).
- [ ] Golden parity when no custom profile is active.
- [ ] Export round-trip and privacy-safe diagnostic tests, including API/CLI/GUI/rich-export parity
  for structured match records and content-hash provenance.
- [ ] Manual GUI smoke for import, preview, activation, correction source, save, and reload.

Acceptance:

1. Users can add a model without editing package files or SQLite.
2. The active coordinate origin and transmission source are visible before dose calculation, per exam.
3. Invalid or ambiguous profiles cannot silently alter dose.
4. API, CLI, GUI, and exports agree on match and precedence.
5. A run without custom profiles remains numerically unchanged.

## 10. Open questions

Resolved in the execution plan's Phase 0 decision log; the recommended answers below come from the
2026-10-09 review and still need maintainer sign-off:

1. Coordinate identity is once per homogeneous exam in v1 (per-event transforms redesign is out of
   scope).
2. `manufacturer` becomes a canonical normalized field, with a warned model-only compatibility path
   for legacy normalized tables.
3. `models[]` holds canonical exact keys; aliases are a separate, explicitly declared list.
4. "Support profile" is removed from v1 unless given a concrete definition.
5. Custom estimated rows fill missing measured coverage; they do not replace measured rows.
6. A custom manufacturer wildcard needs an explicit override declaration to replace a bundled exact.
7. Profile rows plus explicit SQLite claiming the same `k_tab` key: recommend rejecting the
   combination.
8. One JSON file may define several independent profiles; cross-file load order is never meaningful
   because duplicates are errors.
9. A row is "measured" only with a stated measurement source/date; otherwise it is "estimated".
10. Default exports/run configs carry profile ID, schema version, content hash, match level, active
    values, and row evidence status; paths, individual-unit keys, and free-text notes never appear.
11. v1 requires unload/reload rather than automatic source re-reading after load.
12. Comments are bounded, sanitized, local-only audit metadata.
13. "Save session correction as profile" covers equipment-design decisions only (table origin, axis
    signs), not field-size settings that the GUI session cannot express.
14. Custom HVL / `k_med` support is a separate future feature before any SQLite sunset is announced.

## 11. Execution plan

[CUSTOM_EQUIPMENT_PROFILES_EXECUTION_PLAN.md](CUSTOM_EQUIPMENT_PROFILES_EXECUTION_PLAN.md) carries
the phased implementation, exit criteria, progress log, and decision log. Expected SemVer impact is a
minor release; user docs, help/UI registries, `CHANGELOG.md`, maintenance log, feature inventory, and
privacy documentation are updated where profile ingestion/export changes require it.
