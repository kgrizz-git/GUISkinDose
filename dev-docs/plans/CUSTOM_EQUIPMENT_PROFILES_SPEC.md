# Custom Equipment Profiles — Design Spec

Status: **Design spec**, reviewed 2026-10-09 (kiro/gpt-5.6-sol). Execution plan:
[CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md](CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md)
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
  `schema_version`, bounded `profiles[]` each with a stable `profile_id`, alias lists, a coordinate
  block, inline transmission-row objects, and a provenance block (source/reference,
  `evidence_status` per row, dates, bounded notes).
- [ ] The **coordinate block and the transmission block are independently optional**, but every
  profile must carry at least one non-empty block. This is what lets the coordinate-only release
  ship before transmission support exists.
- [ ] The coordinate block is backward-compatible with the bundled entry fields: `manufacturer`,
  `models`, `translation_offset`, `translation_direction`, `rotation_direction`, `field_size_mode`,
  `detector_side_length`, and optional `swap_lateral_longitudinal`. `profile_id`, aliases,
  provenance, and transmission rows are new profile-schema fields, not bundled normalization fields.
- [ ] Reject unknown fields in v1 (add them deliberately in later schema versions).
- [ ] Matching: exact manufacturer plus exact or `"*"` model — the bundled convention is a
  **manufacturer-scoped model wildcard** (exact manufacturer `GE Healthcare`, model `"*"`), not a
  manufacturer wildcard. Aliases are two separate, explicitly declared lists,
  `manufacturer_aliases` and `model_aliases`; profile aliases never silently merge with the bundled
  hardcoded manufacturer aliases in `settings/normalization_settings.py`.
- [ ] `profile_id` is required, user-supplied, unique within a load, and stable across runs; content
  hashing is per profile, with a separate whole-document hash for run-state and export provenance.
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
  - **Coordinates:** custom exact > bundled exact > custom manufacturer-scoped model wildcard >
    bundled wildcard > warned Default. A custom wildcard may replace a bundled exact only with an
    explicit override declaration and a pre-calculation acknowledgement (and by a hard CLI error
    unless an opt-in flag is given).
  - **Transmission:** `k_tab_mode: estimate` ignores profile rows entirely; measured modes resolve
    eligible custom **measured** rows first, then the selected baseline provider (bundled table or
    explicit SQLite), then the existing interpolation/clamping/fallback chain. Custom **estimated**
    rows fill coverage gaps by default and never silently replace a measured row.
  - **Session transforms:** always applied after the reusable profile baseline, exactly once.
  - File order never silently resolves a duplicate claim; canonical duplicates fail at load, and GUI
    enable/disable or an explicit override declaration resolves them.
- [ ] Transmission grid composition: custom **measured** nodes overlay the baseline nodes at identical
  (manufacturer/model, plane, kVp, Cu, Al) coordinates before **one** interpolation pass, so a sparse
  custom row can never clamp across a region the baseline already supports. Custom nodes never extend
  the baseline's range; a query outside all measured coverage clamps at the nearest baseline node and
  is labelled as clamped. Custom **estimated** nodes only fill coordinates with no measured node from
  either source. Mixed grids resolve in one pass and are labelled `source: mixed`.
- [ ] Transmission status is reported as **two orthogonal dimensions** — source
  (`custom_measured` | `custom_estimated` | `baseline` | `mixed` | `fallback`) and numerical
  resolution (`exact` | `interpolated` | `clamped`) — because the existing `k_tab_statuses` carries
  only the resolution-style outcome.
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
- [ ] **Activation and staleness:** the coordinate-only slice allows profile import only before data
  load. The full feature supports post-load activation, which must atomically re-normalize every
  affected exam, rebuild the pristine baseline, recompute detected origins, reapply session
  overrides, clear results and preview caches, and refresh all tabs — or roll back. Activation and
  invalidation are one inseparable change, and an unavailable or unreadable source leaves profile
  state, normalized frames, overrides, and results exactly as they were.
- [ ] A run reads profile bytes **once**, hashes and parses those same bytes, and uses that immutable
  in-memory snapshot for the whole run. GUI mutation is blocked while a calculation is busy, profile
  identity (revision/hash) participates in the Calculate preview cache key, and any profile change
  invalidates cached previews.
- [ ] Profile paths in a settings file resolve relative to that settings file's directory; CLI paths
  resolve against the working directory. Profile paths are never written into settings exports, run
  configurations, or rich exports by default.
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

## 10. Decisions recorded for Phase 0 sign-off

These are the decisions the 2026-10-09 design and plan reviews converged on. They are treated as the
working answers unless the maintainer changes one; Phase 0 of the execution plan records the final
sign-off in its decision log.

1. Coordinate identity is once per homogeneous exam in v1 (per-event transforms redesign is out of
   scope).
2. `manufacturer` becomes a canonical normalized field — always emitted by raw normalization,
   optional-but-warned for legacy normalized tables.
3. `models[]` holds canonical exact keys; `manufacturer_aliases` and `model_aliases` are separate,
   explicitly declared lists that never silently merge with the bundled hardcoded aliases.
4. "Support profile" is removed from v1 unless given a concrete definition.
5. Custom estimated rows fill missing measured coverage; they do not replace measured rows.
6. A custom manufacturer-scoped model wildcard needs an explicit override declaration (and a CLI
   opt-in flag) to replace a bundled exact profile.
7. Profile rows plus explicit SQLite claiming the same `k_tab` key: reject the combination.
8. One JSON file may define several independent profiles; cross-file load order affects diagnostics
   and serialization only, never precedence, because duplicates are errors.
9. A row is "measured" only with a stated measurement source/date; otherwise it is "estimated".
10. Default exports/run configs carry profile ID, schema version, content hashes, match level, active
    values, and row evidence status; paths, individual-unit keys, and free-text notes never appear.
11. The coordinate-only slice is import-before-load only; the full v1 supports atomic post-load
    activation with rollback (not an unload/reload-only workflow).
12. Comments are bounded, sanitized, local-only audit metadata.
13. "Save session correction as profile" covers equipment-design decisions only (table origin, axis
    signs), not field-size settings that the GUI session cannot express.
14. Custom HVL / `k_med` support is a separate future feature before any SQLite sunset is announced.
15. The coordinate block and the transmission block are independently optional; every profile must
    carry at least one.
16. `profile_id` is required, user-supplied, unique, and stable; content hashing is per profile, with
    a separate whole-document hash for run-state and export provenance.
14. Custom HVL / `k_med` support is a separate future feature before any SQLite sunset is announced.
15. The coordinate block and the transmission block are independently optional; every profile must
    carry at least one.
16. `profile_id` is required, user-supplied, unique, and stable; content hashing is per profile, with
    a separate whole-document hash for run-state and export provenance.
17. Custom measured nodes overlay baseline nodes before one interpolation pass; custom nodes never
    extend the baseline range.
18. Profile paths resolve relative to the settings file's directory (CLI: working directory) and are
    never serialized into settings exports, run configurations, or rich exports by default.
19. Run state and rich export bump their schema versions when structured profile provenance is added;
    old normalization-profile documents keep a compatibility reader.
20. Per-exam match records are immutable snapshots with a `domain` field (coordinate vs transmission),
    not mutable fields on `NormalizationSettings`.

## 11. Execution plan

[CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md](CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md) carries
the phased implementation, exit criteria, progress log, and decision log. Expected SemVer impact is a
minor release; user docs, help/UI registries, `CHANGELOG.md`, maintenance log, feature inventory, and
privacy documentation are updated where profile ingestion/export changes require it.
