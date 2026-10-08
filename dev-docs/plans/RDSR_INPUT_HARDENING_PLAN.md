# RDSR input hardening plan (parser and normalizer)

Status: active (2026-10-08). Reviewed by Codex (gpt-6.1-sol, low) on 2026-10-08; findings folded in. Branch: `fix/rdsr-parser-input-hardening`.
Tracks the TO_DO item "RDSR parser input hardening (OpenREM upstream failures)".

## Problem

The parser-level guards shipped on 2026-09-22 (absent model tag, empty value sequences), and every upstream
OpenREM RF test file now parses. `RF-Pat-Orientation-Modifier-Missing` parses to 316 events, so the item's
last named parser failure is closed.

The gap has moved one step down. `rdsr_normalizer` crashes on 10 of the 11 upstream RF DICOM files, and the
user sees only `cli_run failed (error_type=AttributeError …)`. The survey (2026-10-08, gitignored read-only clone
in `tmp/openrem-upstream/`, geometry columns only, nothing vendored) found four failure classes:

| Class | Files | Today | Cause |
|-------|-------|-------|-------|
| A. Duplicate measured value | Philips Azurion | `TypeError` in `_normalize_table_parameters` | Each event carries two `TableHeightPosition` items. The nested path stores them as a list of strings (`['935', '935']`); the pairs are equal in all 89 events. |
| B. Scale-only unit variant | Canon Ultimaxi | clear `RdsrUnitError` (refused) | Reference-point dose is reported in `mGy`, not `Gy`. |
| C. Missing required concept | Pat-Orientation, Eurocolumbus, GE, GE OEC MiniView, No-kVp, Allura, Siemens Zee (+ `_adjusted`) | raw `KeyError` / `AttributeError` in the normalizer or `geom_calc` | Absent source-geometry concepts (`DistanceSourcetoIsocenter_mm`, `DistanceSourcetoDetector_mm`, table positions, `KVP_kV`, `CollimatedFieldArea_m2`). Pat-Orientation also hits a latent bug: the DSD NaN fill reads `FinalDistanceSourcetoDetector_mm` without checking that it exists. |
| D. No irradiation events | Siemens Varic (`RF-ESR-…`) | `KeyError` in `NormalizationSettings.update_used_settings` | The report has no X-ray irradiation events, so the parsed frame is empty and has no `Manufacturer` column. A present but empty `Manufacturer` already follows the unmatched/default profile path. |

## Goal

Every failure is either handled correctly or ends in one clear, value-free `RdsrInputError` that names the
missing or unsupported concepts. No raw pandas exceptions reach the user. Bundled example results do not change.

## Non-goals

- Inventing defaults for missing geometry (DSI, DSD, table position, field size). Defaults would silently change
  dose, so they need a separate, physics-reviewed decision.
- Vendoring any OpenREM file. All of them carry populated identifiers.

## Changes

1. **Duplicate scalar measurements (A).** Collapse duplicates only for an explicit allowlist of scalar concepts
   (distances, table positions, positioner and table angles, kVp, reference-point dose, field area, shutters). The
   collapse handles nested lists and tuples of any length and requires exact numerical equality; it never sums.
   When copies disagree, raise `RdsrInputError` naming the concept and the count of affected events. Filter
   material and thickness lists are never collapsed, because each entry belongs to one filter material.
   The parser's historical tuple/list output stays unchanged; the collapse is one normalizer helper.
2. **Scale-only units (B).** A fixed table maps each known variant unit to the canonical unit and factor:
   `mGy`→`Gy` for dose, and `cm`/`m`→`mm` for linear distances (DSD, Final DSD, DSI, table positions, shutters,
   filter thicknesses). Area units are not rescaled. Conversion merges per event: where the canonical and a variant
   column both exist, a populated canonical value wins, a populated variant fills a gap, and two populated values
   that disagree after conversion raise `RdsrInputError`. Log one value-free info line per converted concept.
   Any other unit still raises `RdsrUnitError`. That message must use fixed labels only and must stop echoing the
   raw unit suffix, which comes from the file.
   Background: DICOM TID 10003 specifies Gy for Dose (RP), but some vendors emit mGy, and most tabular exports use
   mGy (the tabular adapters already convert). Handling mGy here brings RDSR input in line.
3. **Required-concept contract (C).** Define the contract once, as a table of concept → plain-language label,
   derived from the columns the normalizer and `geom_calc` read unconditionally:
   - Always required (column present and value populated per event): `DistanceSourcetoIsocenter_mm`, the resolved
     DSD (below), the three table positions, both positioner angles, `KVP_kV`, `DoseRP_Gy`.
   - Required as columns, values may be blank: `IrradiationEventType`, `AcquisitionPlane`, `Manufacturer`,
     `ManufacturerModelName`, and the three filter columns (blank thicknesses already become 0; blank material
     already takes the no-filter path).
   - Field-size mode dependent: `CollimatedFieldArea_m2` for the collimated-area mode; all four shutter columns
     for the actual-shutter-distance mode.
   DSD resolves per event: `DistanceSourcetoDetector_mm` when populated, else `FinalDistanceSourcetoDetector_mm`
   when that column exists and is populated. An entirely absent primary DSD column with Final DSD present works.
   Order: units → duplicate collapse → profile resolution (`update_used_settings`, which fixes field-size mode) →
   DSD resolution → `_verify_required_concepts`. The check raises one `RdsrInputError` listing every missing
   concept by label with the number of events lacking it.
4. **No events (D).** `rdsr_normalizer` raises `RdsrInputError` ("no X-ray irradiation events") for an empty frame,
   before profile resolution. For callers that pass a frame without a `Manufacturer` or `ManufacturerModelName`
   column, treat the column as blank so the unmatched/default profile applies. The default profile cannot know
   vendor coordinate conventions (for example the GE lateral/longitudinal swap), so the existing value-free
   unmatched-profile notice must say the profile should be verified. Raise `RdsrInputError` if no default profile
   exists.
5. **Surface errors safely.** Add `UserFacingInputError(ValueError)` in `privacy.py`. Its subclasses build messages
   only from fixed label tables and integer counts, never from file-derived strings. `RdsrInputError` and
   `RdsrUnitError` subclass it. The CLI excepthook (`install_value_safe_excepthook`, used by both entry points)
   prints that message instead of the generic code. The GUI loader shows it for both RDSR and tabular paths. Other
   exceptions keep today's generic handling.

## Tests (synthetic only)

Before any behavior change, add a characterization test that snapshots the full normalized frame (all geometry,
filter, and dose columns, every row) for every bundled RDSR example, so "no change on bundled fixtures" is enforced
rather than assumed. Then, with minimal synthetic pydicom datasets or parsed frames:

- Equal duplicates (2 and 3+ copies, nested) collapse to one float; disagreeing duplicates raise `RdsrInputError`.
  Filter lists with equal thicknesses stay lists and keep their material alignment.
- `mGy` dose gives the same `K_IRP` as `Gy`; `cm` and `m` distances give the same geometry as `mm`. Mixed
  canonical + variant columns fill gaps; conflicting values raise. Unknown units raise `RdsrUnitError` without
  echoing the raw unit text.
- Each always-required concept, missing as a column or blank in some events, raises `RdsrInputError` naming it
  with the event count. Collimated-area and shutter modes each require their own columns.
- DSD: primary blank with Final present resolves; primary column absent with Final present resolves; both missing
  raises the clear error.
- Empty frame raises "no X-ray irradiation events". Frames without `Manufacturer`/model columns normalize through
  the default profile with the verification notice.
- CLI: a failing synthetic file prints the plain message through the excepthook. GUI loader returns the message.
- Privacy sentinels: a synthetic file with an identifier-like manufacturer, model, and unit string leaks none of
  them into the error message or into logs at DEBUG level.

Local acceptance (not in CI): rerun the survey script over `tmp/openrem-upstream/`. Azurion and Ultimaxi should
complete, and every other file should end in `RdsrInputError` with a readable message.

## Docs

- `dev-docs/INPUT_SCHEMA_DETECTION.md` "Unit handling": converted units and the new error.
- `dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md`: required-concept contract and the missing-manufacturer fallback.
- Canonical GUI help under `docs/source/gui_help/` (upload page): rejected inputs and default-profile verification.
- `CHANGELOG.md`, `TO_DO.md` (close the item), and the rotational assessment's Phase 0 note.
- Archive this plan and update `dev-docs/index.md` when done.
