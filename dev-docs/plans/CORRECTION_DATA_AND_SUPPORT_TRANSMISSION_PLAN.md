# Correction Data, Equipment Profiles, and Patient-Support Transmission Roadmap

Status: Active umbrella — child plans are independently executable
Created: 2026-09-08
Branch: `fix/package-corrections-db`

## Objective

Make every dose correction and coordinate transform traceable, accurately named,
discoverable, and safely extensible. Correct the inherited Philips Plane B zero-
transmission hazard without inventing provenance, then establish a validated path
for custom equipment data and geometry-driven table/pad transmission.

This work must preserve a strict terminology distinction:

- **Transmission factor** is the fraction that remains after the beam passes through
  the patient support. `k_tab` multiplies dose directly: `1.0` means 100% transmitted
  (no attenuation), `0.8` means 80% transmitted, and `0.0` means no transmitted dose.
- **Attenuation fraction** is the removed fraction, `1 - transmission`.
- **Coordinate transform** changes the interpretation, sign, or origin of table
  coordinates. It is not a dose correction factor.

## Verified Current State

### Where correction data and formulas live

| Quantity | Source | Runtime use | User control today |
|---|---|---|---|
| `k_isq` | Formula in `src/guiskindose/corrections.py` | Per-hit-cell inverse-square scaling | None; geometry-derived |
| `k_bs` | Polynomial coefficients in `corrections.py`, attributed to Benmakhlouf et al. | Per-hit-cell backscatter spline by field size | None |
| `k_med` | `table_data/correction_medium_and_backscatter.csv` (only the `kvp_kv`, `hvl_mmal`, `field_side_length_cm`, and `mu_en_quotient` columns are read; the file's `backscatter` and `h` columns have no runtime consumer because `k_bs` uses in-code coefficients) | Nearest field size, kVp, and HVL lookup | Undocumented replacement SQLite DB only |
| HVL | `table_data/hvl_tables/hvl_combined.csv` (built from the two vendor CSVs by the in-package dev script `table_data/build_hvl_table.py`) | Package table; interpolated over kVp/Cu after inherent-Al and added-Al slice selection | Inherent filtration setting; undocumented replacement DB |
| `k_tab` | `table_data/correction_table_and_pad_attenuation.csv` | Per-event patient-support transmission, applied only to table-intersected cells | One global estimated value (**the shipped default**), or undocumented replacement DB |
| `k_meter` | User CSV/TSV/XLSX/JSON or GUI prompt | Per-equipment/tube kerma calibration before physics corrections | Fully user-configurable |
| Machine coordinate transform | `src/guiskindose/normalization_settings.json` | Converts raw vendor table coordinates/angles to the common frame | Python API custom config; GUI session overrides |

The authoritative baseline correction data are packaged CSVs. A root
`corrections.db` may exist locally, but it is a gitignored derived artifact. The
default setting is the relative string `"corrections.db"`, so a missing database
is currently created in the process working directory from the packaged CSVs.

**Which `k_tab` path a default run takes.** `settings_example.json` ships
`estimate_k_tab: true` with `k_tab_val: 0.8`, and the GUI default state matches
(`gui/state.py`). `calculate_k_tab()` returns `[k_tab_val] * len(data_norm)`
without consulting the bundled table whenever `estimate_k_tab` is set. The bundled
`correction_table_and_pad_attenuation` lookup — and therefore the inherited Plane B
zeros — is reached only when a user deliberately opts out of the estimate. This
bounds who is exposed to the Plane B hazard, but it does not reduce its severity for
those users, and it means the *default* path is an unvalidated user-supplied scalar.

### How tube A/B/single-plane identity is obtained

1. **DICOM RDSR:** `rdsr_parser.py` converts each content item's
   `ConceptNameCodeSequence.CodeMeaning` into a column name. For the DICOM
   `Acquisition Plane` concept, it stores
   `ConceptCodeSequence.CodeMeaning` as `AcquisitionPlane`.
2. DICOM CID 10003 defines:
   - `113620` = Plane A
   - `113621` = Plane B
   - `113622` = Single Plane
3. `rdsr_normalizer.py` copies the string unchanged to normalized
   `acquisition_plane`. It does not currently preserve or validate the DICOM code.
4. **DoseTrack:** `_normalize_plane_code()` infers one distinct integer as
   `Single Plane`; for two values, the lower value becomes A and the higher becomes
   B. This ordering assumption is not tied to a documented DoseTrack code mapping
   and can misidentify a one-plane subset of a biplane system.
5. **Radimetrics/generic inputs:** map an acquisition-plane column when present;
   Radimetrics supplies `Single Plane` when absent.
6. **Normalized input:** trusts the caller's `acquisition_plane` value.

The normalized plane string is used in two correction paths:

- `calculate_k_tab()` keys bundled support transmission by
  `(device model, acquisition plane, kVp, Cu, Al)`.
- `kerma_correction.py` maps it to `single`, `A`, or `B` for per-equipment/tube
  kerma-meter calibration.

It does not choose the beam position or angulation; beam geometry comes from the
normalized source/detector angles and distances. Tube identity is also not clearly
surfaced as correction-selection provenance in results and rich exports.

### What table coordinate transforms do

`normalization_settings.json` entries can define three independent operations:

1. `swap_lateral_longitudinal` changes which raw table field feeds the internal
   lateral/longitudinal axis.
2. `translation_direction` changes the sign of table travel on each axis.
3. `translation_offset` adds a constant origin shift in centimetres.

Therefore, the transforms are not only about axis names and directions. They also
represent where a vendor/model's table-coordinate zero lies relative to the
GUISkinDose origin:

```text
normalized coordinate = configured origin shift
                      + configured direction × raw position
```

The bundled profiles are matched first by normalized manufacturer and exact model,
then by a manufacturer wildcard:

- Siemens + AXIOM-Artis: exact model, zero origin shift.
- Philips + Allura Clarity: exact model, nonzero X/Y/Z origin shift plus sign rules.
- GE Healthcare + any model: manufacturer wildcard, zero origin shift plus a
  lateral/longitudinal swap.
- Unknown equipment: Default profile.

For DICOM GUI loads, the matched `translation_offset` becomes
`table_origin_detected`. Users can apply a per-exam `table_origin_override`, which
re-bases `Tx/Ty/Tz`; this is session-specific, not a reusable equipment profile.
Tabular imports currently seed detected origin to zero. Python callers can construct
`PyskindoseSettings(..., normalization_settings=Path|dict|NormalizationSettings)`,
but ordinary settings JSON, CLI, and GUI do not provide an easy persistent custom
manufacturer/model profile.

### Current patient-support geometry

`check_table_hits()` already performs a vendor-independent source-to-skin
ray/triangle test and applies `k_tab` only to cells whose rays cross one face of the
positioned table. It also short-circuits in two ways: an over-table dot-product test
returns all-miss, and if all four beam vertices hit the table face it returns all-hit
without testing any individual cell ray. The table phantom itself is a cuboid, but
the current test does not use its closed volume. It does not intersect the pad,
calculate path length, or adjust transmission for obliquity.

All inherited Allura Clarity Plane B rows contain transmission `0.0`. If any Plane B
ray is classified as crossing the table, the dose for that cell is silently
multiplied by zero. The plausible lateral-tube explanation is not established
provenance and cannot make zero a safe transmission value.

## Execution Plan Split

This document is an umbrella roadmap and current-state reference. It is not an
execution checklist. Work is divided into four independently reviewable plans:

### 1. Immediate safety and identity

[archive/CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md](archive/CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md)

- Plane B zero-transmission safeguard.
- DICOM/DoseTrack tube identity validation and auditability.
- Actual unmatched-model GUI alerting.
- Transmission terminology across user-facing surfaces.
- Scope: bug fix; expected patch release.

### 2. Data packaging and provenance

[CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md](CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md)

- Correction-data inventory and provenance manifest.
- Package-resource data provider.
- Removal of the CWD-created default database.
- Wheel/runtime and numerical-parity verification.
- Scope: packaging/runtime fix; expected patch release.

Plans 1 and 2 are the intended scope of `fix/package-corrections-db`. They should
remain separate commits or PRs if review size or risk warrants it.

### 3. Custom equipment profiles

[CUSTOM_EQUIPMENT_PROFILES_PLAN.md](CUSTOM_EQUIPMENT_PROFILES_PLAN.md)

- Reusable manufacturer/model coordinate-origin profiles.
- Validated custom patient-support transmission data.
- Shared API, CLI/settings, GUI, and export behavior.
- Scope: separate future feature branch/PR; expected minor release.

### 4. Geometry-driven support transmission

[GEOMETRY_DRIVEN_SUPPORT_TRANSMISSION_PLAN.md](GEOMETRY_DRIVEN_SUPPORT_TRANSMISSION_PLAN.md)

- Characterization of current table intersection.
- Closed-volume table and pad intersections.
- Evidence-gated path-length attenuation model.
- Scope: separate future research/physics branch and scientific review.

## Dependency Order

```text
Safety and tube identity ──────────┬─> Custom equipment profiles
                                   └─> Geometry-driven support transmission
Packaging and provenance ─────────┬─> Custom equipment profiles
                                   └─> Geometry-driven support transmission
```

The two immediate plans can proceed independently where their files do not overlap,
but both must finish before custom profiles. Geometry characterization may begin
earlier, but no attenuation-model change should ship until correction semantics,
provenance, and invalid-value handling are stable.

## Roadmap Completion

Archive this umbrella only when all four child plans are complete or superseded.
Archive each child independently when its own acceptance criteria are met. Keep
`TO_DO.md` pointers aligned with active child plans rather than copying their full
checklists.

## Security and Privacy

Correction/profile inputs contain data, not executable configuration. Use strict
schema validation and never deserialize native objects. Do not log source paths or
raw station/serial identifiers. No credentials, private keys, certificates, or
cryptographic algorithms are introduced by this plan.
