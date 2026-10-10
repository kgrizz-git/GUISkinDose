# Custom Equipment Profiles — Design Spec

Status: **Design spec.** The phased execution plan is a separate document, written after this spec is
reviewed.
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
- Python callers can pass custom `NormalizationSettings`, but ordinary settings JSON, CLI, and GUI do
  not expose a persistent profile file.
- GUI table-origin controls are per-exam session overrides, not reusable manufacturer/model
  definitions.
- Custom `k_tab` is limited to one global estimated transmission (`k_tab_mode: estimate` /
  `k_tab_val`; the shipped default is `measured_with_fallback`) or an undocumented full replacement
  SQLite database.
- Kerma-meter correction already supports validated user files keyed by individual equipment and
  tube; it is a loading/validation precedent but remains a distinct calibration concept (§4).
- `k_tab` baseline lookup is model/plane-specific, not manufacturer- or individual-unit-specific.

## 3. What a profile contains

A profile is one user-owned, versioned file that describes **one or more equipment models**. It has
three parts: metadata/provenance, a coordinate-normalization block, and a patient-support
transmission block.

| Profile field | Engine hook (today) | Applied when |
|---------------|--------------------|--------------|
| `manufacturer`, `models[]`, `aliases[]` | `normalize_manufacturer_key` / `normalize_model_key` in `settings/normalization_settings.py` | Input normalization, per event identity matching |
| `translation_offset` (x/y/z, cm) + `translation_direction` (±) | `settings/translation_offset.py`, `rdsr_normalizer.py`, tabular adapters | Table-origin rebasing when each event's geometry is built; **re-bases the whole table geometry** |
| `rotation_direction` (Ap1..At3, ±) | `NormalizationSettings.update_used_settings` | Per-event angle sign convention |
| `swap_lateral_longitudinal` | `NormalizationSettings.swap_lateral_longitudinal` (GE) | Raw longitudinal/lateral readout mapping, per event |
| `field_size_mode` (`CFA`/`ASD`), `detector_side_length` | `geom_calc` field-area scaling | Field area → `k_isq` / `k_bs` / `k_med`, per event |
| `anode_angle_deg` (optional) | future anode-angle-aware HVL lookup (`hvl_combined.anode_angle_deg`) | HVL resolution, when that backlog item lands |
| transmission rows: `device_model`, `acquisition_plane` (`Single Plane`/`Plane A`/`Plane B`), `kvp_kv`, `filtration_added_mmcu`, `filtration_added_mmal`, `k_patient_support` ∈ (0, 1], `comment` | `corrections.calculate_k_tab()` reading the `correction_table_and_pad_attenuation` table | Dose accumulation, only on cells whose hit path crosses the table/pad |

Transmission rows are the user-supplied counterpart of
`table_data/correction_table_and_pad_attenuation.csv`. Each row must carry a measured/estimated
status and a source note; unmeasured guesses are not accepted silently — the UI and exports label the
status, the same way kerma-meter CFs do today.

The global estimated override (`k_tab_mode: estimate` / `k_tab_val`, which applies one value to every
table-intersected event) stays exactly where it is: a coarse session override, not a profile concept.

## 4. What a profile deliberately does NOT contain

| Data | Where it lives | Why it is not a profile field |
|------|----------------|------------------------------|
| Kerma-meter correction factors | user calibration file (`kerma_correction.py`): `equipment`, `tube`, `correction_factor`, optional `valid_from`/`valid_to` | Already a first-class user file with its own identity (equipment × tube) and calibration periods. Calibration is a distinct concept from equipment design; the two file types may share the loader/validation framework but must not be merged into one format. |
| Backscatter `k_bs`, medium `k_med` | `correction_medium_and_backscatter` table, keyed by (field side length, kVp, HVL) | Keyed by beam/field geometry, not by equipment. An equipment key would be a category error. |
| HVL grid | `hvl_combined`, keyed by (kVp, filtration, anode angle) | Beam-keyed; only the anode angle is a device attribute, and that is the one optional field in §3. |
| `k_isq`, inverse-square, below-floor kVp policy, phantom scaling | settings / geometry | Neither equipment-keyed nor vendor-convention data. |
| Per-case patient / table-origin nudges | Geometry tab per-exam sliders, Settings → Per-exam corrections | Session decisions for one study. A profile supplies the reusable per-equipment baseline; the session override still wins for that run. |

## 5. Profile model and file format

- [ ] One versioned JSON document, with an explicit `schema_version` and a provenance block
  (source/reference, measured-vs-estimated per row, dates, notes). Bounded enough to stay human
  inspectable; evaluated alternative: JSON metadata plus a CSV sidecar for transmission rows.
- [ ] Manufacturer/model matching with aliases, and an optional manufacturer wildcard only when
  deliberately declared (mirrors the bundled GE wildcard).
- [ ] Coordinate fields exactly as listed in §3, with the same names and units as the bundled
  `normalization_settings.json` so the bundled profiles remain valid examples of the format.
- [ ] Transmission rows keyed by the minimum scientifically justified identity:
  manufacturer/model/support profile, tube/plane when required, kVp, Cu, Al.
- [ ] Optional individual-equipment key for measured site-specific support transmission. Keep it
  distinct from kerma-meter CF identity; the identifier must be privacy-safe to display.

## 6. Loading, validation, and precedence

- [ ] Treat profile files as untrusted input: allowlisted extensions, bounded bytes and rows, strict
  schema, finite/ranged values, duplicate rejection, and no executable deserialization. Row/byte
  bounds should mirror the kerma-file loader (`_MAX_TABLE_ROWS`).
- [ ] Reject non-finite, non-positive, and greater-than-one transmission values. Values above `1.0`
  are unphysical for a patient support and produce unsupported dose inflation, so they must not be
  accepted as a user override.
- [ ] Canonicalize manufacturer/model/tube identifiers without silently merging ambiguous aliases.
- [ ] Define and test precedence:
  1. explicit individual-equipment/tube override, when supported;
  2. custom exact manufacturer/model profile;
  3. custom manufacturer wildcard;
  4. bundled exact profile;
  5. bundled wildcard;
  6. warned neutral/default fallback.
- [ ] Never mutate bundled data or the source profile during a run.
- [ ] Treat a custom profile that shadows a bundled exact match (Siemens AXIOM-Artis, Philips Allura
  Clarity, the GE wildcard) as a dose-affecting change: require it to be reported before calculation
  and recorded in exports, since a changed `translation_offset` re-bases the whole table geometry.
  The same rule applies to `field_size_mode` / `detector_side_length`, which move field area and
  therefore `k_isq` / `k_bs` / `k_med`.
- [ ] Detect conflicts between multiple custom profiles (two profiles claiming the same
  manufacturer/model) before calculation and require explicit resolution — never a silent merge.
- [ ] Reuse the shipped identity-matching levels (exact / wildcard / default fallback) so a matched
  profile reports the same match level and fallback counts the Corrections and Calculate surfaces
  already show.

## 7. API, CLI, and GUI

- [ ] One shared profile loader used by Python API, settings JSON, CLI, and GUI.
- [ ] CLI/settings options for one or more profile paths with deterministic precedence (for example
  a repeatable `--equipment-profile PATH` and an `equipment_profiles` settings key).
- [ ] GUI import, validation preview, enable/disable, and removal controls.
- [ ] Before calculation, show:
  - actual manufacturer/model/tube identity;
  - matched profile and match level;
  - coordinate axis/sign/origin rules;
  - transmission source and measured/estimated status;
  - interpolation/clamping/fallback status.
- [ ] Allow users to save a session correction as a reusable profile only after supplying required
  identity and provenance fields.
- [ ] Provide export/reload of profiles and an audit summary.
- [ ] Do not log raw station/serial identifiers or source paths.

## 8. Migration and compatibility

- [ ] Keep bundled profiles immutable and unchanged by user imports.
- [ ] Convert existing Python custom normalization input into the shared profile representation or
  provide a documented compatibility adapter.
- [ ] Keep global estimated `k_tab` as an explicit coarse override, clearly labeled as applying to
  all table-intersected events.
- [ ] Retain read-only legacy custom SQLite support through its announced deprecation window.
- [ ] Export enough provenance to reproduce which profile and values were active.

## 9. Tests and acceptance criteria

- [ ] Unit tests: schema, aliases, precedence, duplicates, invalid factors, wildcard handling,
  conflict resolution, and compatibility adapters.
- [ ] API/CLI/GUI parity tests using synthetic, non-identifying profiles.
- [ ] Tests for new model, model alias, exact vs wildcard, A/B/single, individual equipment
  override, unknown identity, and profile conflict.
- [ ] Golden parity when no custom profile is active.
- [ ] Export round-trip and privacy-safe diagnostic tests.
- [ ] Manual GUI smoke for import, preview, activation, correction source, save, and reload.

Acceptance:

1. Users can add a model without editing package files or SQLite.
2. The active coordinate origin and transmission source are visible before dose calculation.
3. Invalid or ambiguous profiles cannot silently alter dose.
4. API, CLI, GUI, and exports agree on match and precedence.
5. A run without custom profiles remains numerically unchanged.

## 10. Open questions

- One file per equipment, or one file defining several models? (Leaning: one file may define several
  models; CLI/GUI accept multiple files in a deterministic order.)
- Transmission rows inline in the JSON, or a CSV sidecar (the kerma loader allows CSV)?
- Deprecation path for full-replacement custom SQLite databases once profiles ship.
- What identifier backs the optional individual-equipment key, given the logging/display privacy
  rules?

## 11. Execution plan

Not yet written. Deliver on a separate feature branch after the safety and packaging plans; expected
SemVer impact is a minor release. The phased execution plan (phases, exit criteria, progress log,
file-by-file changes, checklists) is its own document, to be drafted from this spec.
