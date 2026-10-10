# Custom Equipment Profiles — Design Spec

Status: **Design approved for Phase 0 contract lock; implementation sign-off pending.** Four contract decisions remain
unresolved and are recorded as blockers in
[CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md](CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md) (Phase 0). Reviewed 2026-10-10.
Execution plan: [CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md](CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md)
Created: 2026-09-08 · renamed from `CUSTOM_EQUIPMENT_PROFILES_PLAN.md` on 2026-10-09
Parent roadmap: [CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md](CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md)
Dependencies: [Correction safety and tube identity](archive/CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md) and
[correction data packaging and provenance](CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md)

## 1. Objective

Let physicists add validated, reusable equipment/model profiles for coordinate normalization and
patient-support transmission without editing bundled files or replacing the full correction database.
Profiles may come from JSON, CSV/TSV, XLSX, an in-app form, or a separate local user-owned database.

This feature does not introduce a path-length attenuation model. It composes custom transmission rows
with the existing validated lookup behavior.

## 2. Verified implementation baseline

- Bundled coordinate profiles contain Siemens and Philips exact matches, a GE manufacturer-scoped model
  wildcard, and Default (`src/guiskindose/normalization_settings.json:4-106`). Matching reads manufacturer
  and model from row 0, tries exact model then `"*"`, and finally Default
  (`src/guiskindose/settings/normalization_settings.py:137-172`); selection is therefore once per
  homogeneous exam/frame, not per event.
- The selected coordinate entry supplies translation offset/direction, rotation direction,
  `field_size_mode`, `detector_side_length`, and the optional lateral/longitudinal swap
  (`src/guiskindose/settings/normalization_settings.py:201-209`). `field_size_mode` selects the field-size
  calculation (`src/guiskindose/geom_calc.py:20-83`) and the resulting dimensions shape the beam and hit
  mask (`src/guiskindose/beam_class.py:249-272`, `src/guiskindose/beam_class.py:313-340`).
  `detector_side_length` only sizes the plotted detector cuboid
  (`src/guiskindose/beam_class.py:275-291`) and is visualization-only.
- The normalized-input contract currently requires `model`, not `manufacturer`
  (`src/guiskindose/input_adapters/normalized.py:26`). v1 adds canonical `manufacturer`, with a warned
  compatibility path for legacy normalized tables.
- Kerma-meter calibration is the file-loader precedent: it accepts `.csv`, `.tsv`, `.xlsx`, and `.json`,
  rejects unsupported suffixes, empty input, missing required columns, and inputs above 10,000 rows
  (`src/guiskindose/kerma_correction.py:42`, `src/guiskindose/kerma_correction.py:324-376`). It presents
  equipment/tube pairs to prompt/UI (`src/guiskindose/kerma_correction.py:205-212`) while warnings report
  counts rather than equipment labels (`src/guiskindose/kerma_correction.py:600-622`).
- `k_tab` matches model (including the de-spaced spelling) plus literal acquisition plane
  (`src/guiskindose/corrections.py:327-331`), then snaps Al and clamp-interpolates the kVp × Cu grid
  (`src/guiskindose/corrections.py:344-380`). The packaged attenuation header has model, plane, kVp, Cu,
  Al, and factor but no manufacturer (`src/guiskindose/table_data/correction_table_and_pad_attenuation.csv:1`).
  Its per-event statuses are `exact`, `interpolated`, `clamped`, `estimated`, `no_device`,
  `invalid_inherited`, and `fallback` (`src/guiskindose/corrections.py:54-66`). The factor is applied only
  to table-hit cells (`src/guiskindose/calculate_dose/add_correction_and_event_dose_to_output.py:99-102`).
- Run state currently gates manufacturer/model with identifiers (`src/guiskindose/gui/run_state.py:155-178`)
  and already provides snapshot/restore primitives for atomic rollback (`src/guiskindose/gui/run_state.py:400-427`).
  This spec deliberately narrows the former privacy rule (§9) while retaining the rollback principle.

## 3. Scope and profile model

A profile has a required stable `profile_id`, schema version, manufacturer, one or more canonical model
keys, optional explicit aliases, bounded provenance, and at least one non-empty domain:

| Domain | Optional fields | Effect |
|---|---|---|
| Coordinates | `translation_offset.{x,y,z}`, `translation_direction.{x,y,z}`, `rotation_direction.{Ap1,Ap2,Ap3,At1,At2,At3}`, `swap_lateral_longitudinal`, `field_size_mode`, `detector_side_length` | Reusable equipment baseline; every leaf is independently optional and resolved by §6 |
| Transmission | rows of `device_model`, literal `acquisition_plane`, `kvp_kv`, `filtration_added_mmcu`, `filtration_added_mmal`, `k_patient_support`, `evidence_status`, source/date, bounded comment | Sparse nodes overlaid by §7; factors are finite and in `(0, 1]` |

`manufacturer_aliases` and `model_aliases` are separate explicit lists. They never silently inherit the
bundled hardcoded alias sets. The only wildcard is model `"*"` under an exact manufacturer; there is no
manufacturer wildcard. Unknown fields are rejected.

`field_size_mode` is dose-affecting. `detector_side_length` is reported as visualization-only. Session
patient offsets and per-exam table-origin adjustments apply after the profile baseline and never become
patient-specific profile data.

Out of scope: kerma-meter CFs; `k_bs`; `k_med`; the HVL grid; `k_isq`; below-floor-kVp policy; phantom
scaling; custom HVL/medium tables; `anode_angle_deg`; and individual-equipment transmission keys.
Kerma calibration has different identity, validity-period, and factor rules. The global
`k_tab_mode=estimate`/`k_tab_val` remains a coarse session override that bypasses transmission profiles.

## 4. Input and persistence model

Every source adapter produces the same immutable canonical profile set before matching or calculation.
JSON is the canonical full-fidelity interchange form; the other paths are first-class authoring and load
paths, not lossy shortcuts.

| Source | v1 contract |
|---|---|
| JSON | One document with `schema_version` and bounded `profiles[]`; nested coordinate and transmission blocks preserve every field. |
| CSV/TSV, XLSX | **One flat tabular model, identical in both formats** (the kerma-loader precedent, `src/guiskindose/kerma_correction.py:345-362`): a strict `record_type` column (`profile`, `coordinate`, `transmission`) plus the allowlisted columns for each record type, one row per record. CSV/TSV is one table; XLSX is the same table on one sheet (first sheet by default, sheet selectable for multi-sheet workbooks). Metadata repeated for a `profile_id` must agree; blank cells mean omitted fields only where the schema allows. |
| GUI entry | The Equipment Profiles form authors coordinate leaves and transmission rows directly. Validation and preview occur before the entry can be activated or saved. No source file is required. |
| User profile store | A separate local SQLite database in GUISkinDose's user-owned application-data area stores canonical JSON payloads, `profile_id`, schema version, revision, hashes, and timestamps. Users can save, version, enable, export, and reload records. |

The store is not the bundled correction provider and never mutates package data. It is also not
`corrections_db_path`; that read-only legacy path remains an independent explicit source for HVL,
`k_med`, and baseline `k_tab` data.

### Packaged examples and templates

Users get the same starting experience as the kerma-meter example file
(`src/guiskindose/example_data/kerma_meter/` — packaged CSV plus README plus a GUI download button):

- a **filled example** and a **blank template** for each accepted source, packaged under
  `example_data/equipment_profiles/`: JSON, CSV/TSV, XLSX (tabular shapes identical, see §4), plus a
  short README with the column/field dictionary and the CLI/GUI usage;
- an Equipment Profiles card action to download the example and the template, in browser mode via
  `ui.download()` and in native mode via the OS save dialog (the mechanism already used by
  `gui/tabs/corrections.py:174-188`);
- in-app help mirroring that README;
- every packaged example loads through the real loader in tests, and each invalid example fails with
  its stable error code, so the shipped files cannot drift from the schema.

All packaged content is synthetic — fictional equipment labels, factors, and dates. No station names,
serial numbers, source paths, or site-identifying notes appear in any example or template.

### Shared ingestion safeguards

1. Allowlist `.json`, `.csv`, `.tsv`, and `.xlsx`; reject executable/native-object deserialization.
2. Read each file once into bounded bytes, hash those bytes, and parse that same snapshot. XLSX ZIP
   members, sheet count, aggregate rows, and text cells are bounded before materialization.
3. Apply a 10,000 aggregate-row ceiling (the kerma precedent), finite/ranged numeric validation,
   bounded profiles/aliases/text, strict fields and sheets, and canonical duplicate/conflict checks.
4. A GUI submission is copied into an immutable canonical snapshot before validation. A database load
   uses one read transaction and immutable selected revisions. Calculation never follows a mutable form
   or re-queries changing records.
5. Exact byte/text/profile limits and stable error codes are locked in Phase 0 and shared by all adapters;
   no adapter receives a weaker validation path.

### Hashes and provenance

Canonical serialization uses UTF-8 JSON, sorted keys, normalized finite numbers, and no insignificant
whitespace. Each profile has a SHA-256 canonical content hash; each activation has an active-set hash.
File inputs additionally retain a hash of the exact bytes parsed. JSON/tabular files have a source-document
hash; GUI entries use their canonical entry-snapshot hash; database loads use a selected-revision-set hash.
Exports record `source_kind`, schema version, profile/revision ID, profile hash, active-set hash, and the
applicable source hash—never a source path. Saving the same canonical profile to the store does not change
its profile hash.

## 5. Identity, matching, and conflicts

Coordinate identity is canonical manufacturer/model for one homogeneous exam. Raw normalization always
emits both; legacy normalized tables may omit manufacturer only through a warning-bearing compatibility
rule. Mixed coordinate identities in one frame are split before normalization or rejected.

Default coordinate candidate order is:

1. custom exact manufacturer/model;
2. bundled exact manufacturer/model;
3. custom manufacturer-scoped model wildcard;
4. bundled manufacturer-scoped model wildcard;
5. warned Default.

An explicitly declared custom wildcard may be promoted above a bundled exact only after pre-calculation
GUI acknowledgement or a CLI opt-in flag. File order never breaks ties. Canonically duplicate claims,
ambiguous aliases, and two enabled profiles claiming the same custom slot are load/activation errors unless
the user disables one or uses a schema-defined explicit override.

Every exam receives immutable structured match records, separate by `domain`, with `profile_id`, `source`
(`custom`, `bundled`, `default`), `level` (`exact`, `wildcard`, `default`), canonical
`matched_input_key`, affected event count, revision/hash, and field/row source detail.

## 6. Partial coordinate profiles and notification

Coordinate resolution is **per leaf field**, not all-or-nothing. For each leaf, walk the candidate ladder
independently and take the first supplied value. Thus a custom exact profile containing only
`swap_lateral_longitudinal` inherits offset, directions, rotations, field-size mode, and detector size from
the bundled exact match, then wildcard, then Default. Nested x/y/z and angle entries inherit independently.
The effective profile is materialized once per exam and records the source profile/level/hash for every leaf.

Missing content is valid inheritance, not an error. Before calculation, any custom match with inherited
leaves produces a per-exam notice:

> Partial match — fields inherited from bundled/Default: `translation_offset` from bundled exact
> `AXIOM-Artis`; `rotation_direction.Ap2` from Default.

The notice names every inherited field and source, appears in pre-calculation review and the Calculate and
Results summaries, and is recorded in dict/JSON/rich exports. It is warning/audit information, not a block.
A fully specified profile is labeled `complete match` and has no partial warning.

## 7. Partial transmission coverage and precedence

Transmission uses a separate ladder:

1. `k_tab_mode=estimate` ignores profile and measured-table rows.
2. Otherwise select the packaged baseline attenuation table or the table from an explicit
   `corrections_db_path`.
3. Overlay eligible custom nodes on the key **canonical model + literal acquisition plane + kVp + Cu +
   Al**. Manufacturer is match provenance, not a table join column.
4. Run one existing Al-snap plus kVp × Cu clamp-interpolator over the composite grid.
5. Preserve today's no-device/invalid/fallback behavior for models, planes, or queries without usable
   coverage.

A custom measured node replaces a packaged baseline node at the same key; a custom estimated node only
fills an in-extent key with no measured node from either source. Uncovered nodes remain baseline nodes, and
uncovered model/plane queries retain baseline interpolation, clamping, and fallback. A mixed interpolation
may use both custom and baseline nodes and is reported as source `mixed`.

Custom rows may not extend a baseline model/plane grid's kVp/Cu/Al extents. With explicit
`corrections_db_path`, any custom row colliding with that database's attenuation key is a load error;
non-overlapping in-extent rows may overlay it. Overlay never mutates either source.

Per-event status remains `exact`/`interpolated`/`clamped` or existing `estimated`/`no_device`/
`invalid_inherited`/`fallback`. A separate per-exam source dimension is `custom_measured`,
`custom_estimated`, `baseline`, or `mixed`. Sparse custom coverage produces a concrete partial-coverage
notice before calculation and in Calculate, Results, and exports, naming custom versus inherited row counts
and affected model/plane—not station/serial.

Missing rows fall back and notify. Unsupported capability, out-of-extent rows, invalid factors,
duplicate/conflicting claims, ambiguous aliases/wildcards, and explicit-SQLite same-key collisions fail
closed. A staged build must reject, not ignore, a valid field or domain it cannot yet apply.

## 8. API, CLI, GUI, and atomic lifecycle

One loader/resolver serves Python, settings JSON, CLI, GUI, and the user store. CLI/settings accept one or
more profile files plus stored profile IDs; CLI paths resolve from the working directory and settings paths
from the settings file's directory. Deterministic input order affects diagnostics/serialization only.

The GUI Equipment Profiles card supports file import, manual coordinate and transmission entry, validation
preview, stored-profile browsing, save/version/reload, enable/disable/remove, conflict resolution, and
explicit canonical JSON export. It shows active, unused, complete, partial, and conflicting profiles.

Post-load activation is one transaction for file, GUI-memory, and database sources: snapshot the candidate
source; validate and resolve all conflicts; re-normalize every affected exam; rebuild pristine baselines;
recompute detected origins; reapply session overrides exactly once; rebuild profile/transmission indexes;
clear results and previews; include active-set revision/hash in cache keys; and refresh all tabs. Any failure
rolls profile state, frames, origins, overrides, results, and caches back to the prior snapshot. Mutation is
blocked while calculation is busy. The Phase 2 thin slice may allow import-before-load only; full v1 must
ship atomic post-load activation.

## 9. Privacy and export policy

| Data | Default export/run config | Identifier opt-in | Logs |
|---|---|---|---|
| Manufacturer and model, including canonical `matched_input_key` | Included; equipment design data, not identifiers | Not required | May be shown |
| Station name and serial number | Excluded from per-event output | Included only as gated fields in per-event exports through the existing `include_identifiers` gate | Never — counts/event indices only, and the opt-in does not change that |
| Profile ID, schema/revision, hashes, match level, active values, inheritance/source summary | Included | Not required | IDs/status/counts allowed |
| Profile source path | Never included; replaced by provenance/hashes | Full profile export is separate, but run provenance still omits paths | Never |
| Bounded free-text notes/source detail | Excluded | Included only by explicit full-profile export | Never |

Manufacturer/model may appear by default in dialogs, exports, provenance, run configurations, and logs.
Station/serial remain potentially site-identifying. Errors use stable codes, row indices, field names, and
counts without paths, station/serial values, or notes.

## 10. Compatibility and acceptance

Bundled profiles remain immutable. Python custom `NormalizationSettings` and old run-state normalization
profiles receive a documented compatibility reader/adapter. Structured profile provenance bumps run-state
and rich-export schema versions with backward readers. Explicit SQLite is not deprecated; any future
migration utility can extract only its attenuation table and cannot migrate custom HVL or medium data.

Required tests include schema/adapters/bounds/hashes, aliases/wildcards/conflicts, privacy-safe diagnostics,
atomic rollback, API/CLI/GUI/store parity, and no-profile numerical goldens. At minimum, end-to-end tests
cover: (a) a coordinate-only partial profile and inherited-field notice, (b) a transmission-only partial
profile and baseline-row notice, and (c) a fully specified profile with no partial notice, each through
exports and reload. A/B/single planes, exact/interpolated/clamped and all existing non-grid statuses,
explicit SQLite coexistence, mixed exams, unused profiles, and table-hit-only dose changes are mandatory.

Acceptance:

1. Users can create/load profiles from every supported source and persist/reload them without editing package data.
2. Effective coordinate fields, transmission source, inherited fields/rows, and evidence are visible per exam before calculation.
3. Missing coverage inherits and notifies; invalid, unsupported, ambiguous, or conflicting content cannot alter dose.
4. API, CLI, GUI, stored records, run state, and exports agree on values, precedence, hashes, and provenance.
5. Runs without custom profiles remain numerically unchanged.

## 11. Decisions

1. 2026-10-09 — Coordinate identity and transforms remain once per homogeneous exam/frame in v1.
2. 2026-10-09 — Canonical `manufacturer` joins `model` in normalized data; legacy omissions warn.
3. 2026-10-09 — Exact aliases are explicit and separate; only manufacturer-scoped model wildcards exist.
4. 2026-10-10 — JSON is canonical, while CSV/TSV, XLSX, GUI entry, and a local user profile database are
   first-class sources; CSV/TSV and XLSX share one flat tabular model rather than two shapes.
5. 2026-10-10 — The user profile SQLite store is separate from immutable bundled data and `corrections_db_path`.
6. 2026-10-10 — Coordinate blocks are partial at leaf-field granularity and inherit through custom/bundled/wildcard/Default candidates with per-field provenance.
7. 2026-10-10 — Transmission rows are sparse overlays; uncovered nodes/queries retain baseline interpolation, clamping, and fallback with user notification.
8. 2026-10-09 — Measured rows require source/date; estimated rows fill only unmeasured in-extent nodes.
9. 2026-10-09 — A custom wildcard may outrank a bundled exact only by explicit declaration and acknowledgement/CLI opt-in.
10. 2026-10-09 — The transmission key is canonical model + literal plane + kVp + Cu + Al; explicit-SQLite key collisions and out-of-extent rows error.
11. 2026-10-09 — Overlay precedes one existing Al-snap/kVp × Cu interpolator; per-event status and per-exam source remain separate.
12. 2026-10-10 — Stable user-supplied profile IDs, canonical per-profile hashes, source hashes, revisions, and active-set hashes define provenance without paths.
13. 2026-10-10 — Manufacturer/model are not identifiers; station/serial keep the identifier gate and never enter logs.
14. 2026-10-09 — Full v1 post-load activation is atomic across profile state, normalization, overrides, results, and caches.
15. 2026-10-10 — Missing supported content inherits and notifies; bad, conflicting, ambiguous, or unsupported content fails closed.
16. 2026-10-10 — Notes stay bounded/local by default, and GUI profile saving excludes patient-specific positioning.
17. 2026-10-09 — Explicit `corrections_db_path` remains supported and is not the user profile store.
18. 2026-10-09 — Structured provenance bumps run-state/rich-export schemas; old normalization-profile documents retain a reader.
19. 2026-10-09 — Kerma CFs, backscatter/medium, HVL, `anode_angle_deg`, and individual-equipment profile keys remain out of scope.
20. 2026-10-09 — Per-exam coordinate/transmission match records are immutable snapshots, not mutable `NormalizationSettings` fields.
