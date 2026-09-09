# Correction Safety and Tube Identity Plan

Status: Active — immediate priority
Created: 2026-09-08
Parent roadmap:
[CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md](CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md)

## Objective

Prevent inherited invalid patient-support transmission data from silently zeroing
dose, make transmission semantics unambiguous, validate how Tube A/B/single-plane
identity is obtained, and show users the actual unmatched scanner identity when
coordinate normalization falls back.

This is a focused bug-fix plan. It does not redesign database packaging, add custom
equipment profiles, or change the table/pad intersection model.

## Verified Problems

1. `k_tab` directly multiplies dose and is therefore a **transmission factor**:
   `1.0` means no attenuation; `0.0` removes all dose for an intersected cell.
2. All inherited Allura Clarity Plane B support rows contain `0.0`. Their
   `estimated` comments do not establish that zero is a valid physical value.
   **This plan classifies those inherited zeros as invalid for this lookup** because
   no provenance supports complete blocking by the patient support. The runtime
   safeguard will deliberately change an affected AlluraClarity Plane B table-hit
   transmission from `0.0` to warned neutral `1.0` before dose multiplication.
   This does not conflict with "valid existing results unchanged": the affected
   values are unsupported invalid inputs, not established valid results.
3. DICOM RDSR uses CID 10003 (`113620` A, `113621` B, `113622` single), but
   `rdsr_parser.py` stores only `CodeMeaning`; the code and coding scheme are lost.
4. DoseTrack infers one observed integer code as single-plane, or sorts two codes
   into A/B. A one-tube subset of a biplane export can therefore be mislabeled.
5. `kerma_correction.normalize_tube()` maps unrecognized plane text to `single`,
   which can silently apply a real single-tube calibration to ambiguous input.
6. The GUI does alert on fallback coordinate normalization, but it stores the
   matched fallback profile (`Default`) as the displayed manufacturer/model. The
   warning can identify “Default,” not the actual unmatched scanner.
7. `k_tab` is selected by model + acquisition plane + kVp + Cu + Al. It is not
   manufacturer- or individual-unit-specific, and its match is not previewed before
   calculation.

## Scope

### 1. Characterize and pin current behavior

- [ ] Add focused tests for valid single-plane/A/B DICOM CID values, free-form or
  unknown values, DoseTrack one-code/two-code subsets, and normalized input.
- [ ] Add a current-behavior characterization test proving that inherited
  AlluraClarity Plane B zero `k_tab` currently zeroes intersected-cell dose, and
  that a non-zero fallback produces a higher, conservative PSD-side estimate.
- [ ] Pin existing valid Siemens and Philips Plane A numerical behavior.
- [ ] Confirm how plane identity appears in calculation output and every rich export;
  record missing audit fields before changing output.

### 2. Add a conservative zero-transmission safeguard

- [ ] Validate database/profile-derived patient-support transmission before use.
- [ ] Treat non-finite or non-positive lookup values as invalid/missing, emit a
  prominent privacy-safe warning, and use neutral transmission `1.0`.
- [ ] Preserve the inherited Plane B rows unchanged for provenance until a verified
  source or measurement justifies editing them.
- [ ] Keep intentional user-entered estimated transmission separate and label its
  source. Review whether explicit zero should remain allowed; do not silently change
  that user contract.
- [ ] Include invalid-source/fallback status in calculation warnings and exports.
- [ ] Add a dedicated fixture/test pinning the observable contract: AlluraClarity
  Plane B events must produce warned-neutral transmission `1.0`, must not silently
  zero intersected dose, and must show a dose regression relative to the pre-fix
  characterization baseline. Do not edit an existing golden fixture if a dedicated
  test is cleaner.
- [ ] Record a clear CHANGELOG note under the patch release explaining that
  inherited Plane B zero-transmission rows no longer silently zero dose and that
  affected PSD values will increase to the warned-neutral fallback.

### 3. Canonicalize tube identity

- [ ] Preserve DICOM acquisition-plane code, coding scheme, and meaning during parse
  and normalization.
- [ ] Canonicalize only recognized CID 10003 values to `single`, `A`, or `B`.
- [ ] Unknown or ambiguous values must remain unknown and use neutral correction
  behavior; they must not silently become `single`.
- [ ] Replace DoseTrack ordering inference with a documented explicit mapping or a
  required user choice when the source mapping is unknown.
- [ ] Before closure, define a raw plane-identity audit/export schema preserving:
  - source kind/schema (DICOM, DoseTrack, Radimetrics, generic, normalized);
  - raw code value (when present, e.g., DICOM CodeValue or DoseTrack integer);
  - coding scheme (when applicable, e.g., DCM, DoseTrack internal);
  - raw meaning/label (e.g., "Plane A", "Plane B", "Single Plane");
  - canonical identity (`single`, `A`, `B`, or `unknown`);
  - resolution/confidence/status (`code-backed`, `inferred`, `ambiguous`,
    `unknown`).
  Require API/GUI/export parity on this schema with additive fields so no existing
  output shape is broken. Privacy-safe handling: never log raw identifiers; emit
  only counts and event-index lists for warnings.

### 4. Fix unmatched-model GUI reporting

- [ ] Retain actual input manufacturer/model separately from the matched
  normalization profile.
- [ ] Make Upload and Geometry warnings name the actual unmatched model and state
  that the Default profile is active.
- [ ] Attribute fallback warnings per exam in multi-exam mode.
- [ ] Show the selected normalization profile, X/Y/Z origin shift, axis rules, and
  `k_tab` match/fallback status before calculation.
- [ ] Add GUI simulation tests for single- and multi-exam fallback reporting.

### 5. Terminology audit

- [ ] Use “patient-support transmission factor” for `k_tab` in GUI labels, help,
  notebook, glossary, API docs, exports, warnings, feature inventory, and active
  plans.
- [ ] Use “attenuation” only for the physical reduction or explicitly say
  “transmission correction for attenuation.”
- [ ] Define `attenuation fraction = 1 - transmission factor`.
- [ ] Update the UI-copy/help registries required by the documentation harness.

## Acceptance Criteria

1. No bundled/custom lookup can silently multiply intersected dose by a non-finite
   or non-positive transmission.
2. Valid existing correction results remain unchanged.
3. An inherited AlluraClarity Plane B zero produces warned-neutral `1.0`, explicit
   invalid-source status, and the characterized dose delta instead of silent zeroing.
4. DICOM tube A/B/single identity is code-backed and auditable.
5. Ambiguous DoseTrack or free-form tube identity cannot silently select a real
   correction/calibration.
6. GUI fallback alerts show actual scanner identity and affected exam.
7. Every user-facing description makes transmission semantics explicit.

## Validation

- Targeted parser, adapter, correction, dose, GUI, and export tests.
- A pre-fix characterization and post-fix golden contract for the Plane B
  transmission value, warning/status, and intersected-cell dose behavior.
- Golden correction and PSD tests for all unaffected valid cases.
- Help/UI-copy, doc-freshness, file-size, type, lint, privacy, and full test checks
  appropriate to changed files.
- Manual GUI smoke: unmatched model, valid Plane A, ambiguous Plane B, multi-exam
  mixed match/fallback.

## Delivery

Expected SemVer impact: patch-level bug fix, unless preserving DICOM plane metadata
requires a breaking public-output change. Record user-visible behavior in
`CHANGELOG.md` and internal characterization in `dev-docs/MAINTENANCE_LOG.md`.
