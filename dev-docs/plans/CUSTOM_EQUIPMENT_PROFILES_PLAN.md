# Custom Equipment Profiles Plan

Status: Active design plan — implement on a separate future branch/PR
Created: 2026-09-08
Parent roadmap:
[CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md](CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md)
Dependencies:
[CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md](CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md) and
[CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md](CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md)

## Objective

Let users add validated, reusable equipment/model profiles for coordinate
normalization and patient-support transmission without editing bundled files or
rebuilding/replacing the complete correction database.

This plan does not implement a new path-length attenuation model. Custom
transmission rows use the validated lookup semantics established by the preceding
plans.

## Current Capability Gaps

- Coordinate normalization supports bundled manufacturer/model profiles.
- Python callers can pass custom `NormalizationSettings`, but ordinary settings
  JSON, CLI, and GUI do not expose a persistent profile file.
- GUI table-origin controls are per-exam session overrides, not reusable
  manufacturer/model definitions.
- Custom `k_tab` is limited to one global estimated transmission (which is the
  shipped default, `estimate_k_tab: true` / `k_tab_val: 0.8`) or an undocumented
  full replacement SQLite database.
- Kerma-meter correction already supports validated user files keyed by individual
  equipment and tube; it is a useful loader/validation precedent but remains a
  distinct calibration concept.
- `k_tab` baseline lookup is model/plane-specific, not manufacturer- or
  individual-unit-specific.

## Profile Model

- [ ] Define a versioned, user-owned profile format with explicit schema and
  provenance. Prefer JSON metadata plus tabular transmission rows, or one bounded
  JSON document if it remains easy to inspect and validate.
- [ ] Support manufacturer/model matching, aliases, and optional manufacturer
  wildcard only when deliberately declared.
- [ ] Support coordinate fields:
  - lateral/longitudinal source mapping;
  - per-axis direction signs;
  - X/Y/Z coordinate-origin shifts in centimetres;
  - rotation signs;
  - field-size mode and detector dimensions.
- [ ] Support patient-support transmission rows keyed by the minimum scientifically
  justified identity: manufacturer/model/support profile, tube/plane when required,
  kVp, Cu, and Al.
- [ ] Evaluate an optional individual-equipment key for measured site-specific
  support transmission. Keep it distinct from kerma-meter CF identity.
- [ ] Require measurement/source notes and measured/estimated status for custom
  transmission data.

## Loading, Validation, and Precedence

- [ ] Treat profile files as untrusted input: allowlisted formats, bounded bytes and
  rows, strict schema, finite/ranged values, duplicate rejection, and no executable
  deserialization.
- [ ] Reject non-finite, non-positive, and greater-than-one transmission values.
  Values above `1.0` are unphysical for a patient support and produce unsupported
  dose inflation, so they must not be accepted as a user override.
- [ ] Canonicalize manufacturer/model/tube identifiers without silently merging
  ambiguous aliases.
- [ ] Define and test precedence:
  1. explicit individual-equipment/tube override, when supported;
  2. custom exact manufacturer/model profile;
  3. custom manufacturer wildcard;
  4. bundled exact profile;
  5. bundled wildcard;
  6. warned neutral/default fallback.
- [ ] Never mutate bundled data or the source profile during a run.
- [ ] Treat a custom profile that shadows a bundled exact match (Siemens
  AXIOM-Artis, Philips Allura Clarity, the GE wildcard) as a dose-affecting change:
  require it to be reported before calculation and recorded in exports, since a
  changed `translation_offset` re-bases the whole table geometry.
- [ ] Detect conflicts between multiple custom profiles before calculation and
  require explicit resolution.

## API, CLI, and GUI

- [ ] Add one shared profile loader used by Python API, settings JSON, CLI, and GUI.
- [ ] Add CLI/settings options for one or more profile paths with deterministic
  precedence.
- [ ] Add GUI import, validation preview, enable/disable, and removal controls.
- [ ] Before calculation, show:
  - actual manufacturer/model/tube identity;
  - matched profile and match level;
  - coordinate axis/sign/origin rules;
  - transmission source and measured/estimated status;
  - interpolation/clamping/fallback status.
- [ ] Allow users to save a session correction as a reusable profile only after
  supplying required identity and provenance fields.
- [ ] Provide export/reload of profiles and an audit summary.
- [ ] Do not log raw station/serial identifiers or source paths.

## Migration and Compatibility

- [ ] Keep bundled profiles immutable and unchanged by user imports.
- [ ] Convert existing Python custom normalization input into the shared profile
  representation or provide a documented compatibility adapter.
- [ ] Keep global estimated `k_tab` as an explicit coarse override, clearly labeled
  as applying to all table-intersected events.
- [ ] Retain read-only legacy custom SQLite support through its announced
  deprecation window.
- [ ] Export enough provenance to reproduce which profile and values were active.

## Tests and Acceptance Criteria

- [ ] Unit tests: schema, aliases, precedence, duplicates, invalid factors, wildcard
  handling, and compatibility adapters.
- [ ] API/CLI/GUI parity tests using synthetic, non-identifying profiles.
- [ ] Tests for new model, model alias, exact vs wildcard, A/B/single, individual
  equipment override, unknown identity, and profile conflict.
- [ ] Golden parity when no custom profile is active.
- [ ] Export round-trip and privacy-safe diagnostic tests.
- [ ] Manual GUI smoke for import, preview, activation, correction source, save, and
  reload.

Acceptance:

1. Users can add a model without editing package files or SQLite.
2. The active coordinate origin and transmission source are visible before dose
   calculation.
3. Invalid or ambiguous profiles cannot silently alter dose.
4. API, CLI, GUI, and exports agree on match and precedence.
5. A run without custom profiles remains numerically unchanged.

## Delivery

Implement on a separate feature branch after the safety and packaging plans.
Expected SemVer impact: minor release. Update user docs, help/UI registries,
`CHANGELOG.md`, maintenance log, feature inventory, and privacy documentation where
profile ingestion/export changes require it.
