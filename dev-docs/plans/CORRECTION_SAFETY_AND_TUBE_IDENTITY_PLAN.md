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
2. The bundled table is not the default path. `settings_example.json` and the GUI
   default to `estimate_k_tab: true` / `k_tab_val: 0.8`, and `calculate_k_tab()`
   returns `[k_tab_val] * n` **unvalidated** in that mode, never reading the table.
   So the Plane B hazard reaches only users who opt out of the estimate, while the
   default path can be driven to `0.0` by the user: the GUI slider allows `0.0`
   (`min=0.0`) and the getting-started notebook documents "`k_tab_val` from 0 to 1",
   yet the `calculate_k_tab()` docstring states "must be in range (0, 1)". That
   inconsistency is an existing, unresolved user contract, and both paths must be
   covered by the safeguard.
3. All inherited Allura Clarity Plane B support rows contain `0.0` (304 rows, all
   commented `estimated`; the matching Plane A rows are all `0.8`). Their
   `estimated` comments do not establish that zero is a valid physical value.
   **This plan classifies those inherited zeros as invalid for this lookup** because
   no provenance supports complete blocking by the patient support. The runtime
   safeguard will deliberately change an affected AlluraClarity Plane B table-hit
   transmission from `0.0` to warned neutral `1.0` before dose multiplication.
   This does not conflict with "valid existing results unchanged": the affected
   values are unsupported invalid inputs, not established valid results.
4. DICOM RDSR uses CID 10003 (`113620` A, `113621` B, `113622` single), but
   `rdsr_parser.py` stores only `CodeMeaning`; the code and coding scheme are lost.
5. DoseTrack infers one observed integer code as single-plane, or sorts two codes
   into A/B. A one-tube subset of a biplane export can therefore be mislabeled.
6. `kerma_correction.normalize_tube()` maps unrecognized plane text to `single`,
   which can silently apply a real single-tube calibration to ambiguous input.
7. The GUI does alert on fallback coordinate normalization, but it stores the
   matched fallback profile (`Default`) as the displayed manufacturer/model. The
   warning can identify “Default,” not the actual unmatched scanner.
8. `k_tab` is selected by model + acquisition plane + kVp + Cu + Al. It is not
   manufacturer- or individual-unit-specific, and its match is not previewed before
   calculation.

## Scope

### 1. Characterize and pin current behavior

- [ ] Add focused tests for valid single-plane/A/B DICOM CID values, free-form or
  unknown values, DoseTrack one-code/two-code subsets, and normalized input.
- [x] Add a current-behavior characterization test proving that inherited
  AlluraClarity Plane B zero `k_tab` currently zeroes intersected-cell dose, and
  that a non-zero fallback produces a higher, conservative PSD-side estimate.
  *(Completed in Chunk 1: `tests/unittests/test_k_tab_transmission_characterization.py`)*
- [x] Pin existing valid Siemens and Philips Plane A numerical behavior.
  *(Completed in Chunk 1: exact-match pins in the new characterization module)*
- [x] Characterize the default `estimate_k_tab` path separately from the table
  lookup, including `k_tab_val = 0.0` and `k_tab_val > 1.0`.
  *(Completed in Chunk 1: `TestEstimateKTabNoValidation` in the new module)*
- [ ] Add DoseTrack cases for a plane-code column with three or more distinct
  integers (currently a hard `ValueError`) and for a file whose codes span more than
  one scanner, since `_normalize_plane_code()` infers one mapping per file.
- [ ] Confirm how plane identity appears in calculation output and every rich export;
  record missing audit fields before changing output.

### 2. Add a conservative zero-transmission safeguard

- [ ] Validate database/profile-derived patient-support transmission before use.
- [ ] Treat non-finite or non-positive lookup values as invalid/missing, emit a
  prominent privacy-safe warning, and use neutral transmission `1.0`.
- [ ] Reject or warn on transmission values greater than `1.0`. These are
  unphysical for a patient support and produce unsupported dose inflation, so they
  must not pass validation silently.
- [ ] Define the explicit estimated-factor contract as finite `0 < k_tab_val <= 1`.
  Align the `calculate_k_tab()` docstring, GUI control and validation, notebook,
  settings docs, and API/CLI boundaries in the same change.
- [ ] Apply that contract to the **default** `estimate_k_tab` path, which currently
  returns `k_tab_val` for every event with no range check. Reject an invalid explicit
  value with an actionable error before calculation rather than silently replacing
  the user's input. Share range-validation logic with the lookup path where practical,
  while retaining the warned-neutral fallback for invalid inherited lookup data.
- [ ] Preserve the inherited Plane B rows unchanged for provenance until a verified
  source or measurement justifies editing them.
- [ ] Keep intentional user-entered estimated transmission separate, label its
  source, and document the user-visible correction that explicit zero is no longer
  accepted.
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
- [ ] Canonicalize only recognized CID 10003 values to `single`, `A`, or `B`, in a
  **new additive field**. Do not rewrite the normalized `acquisition_plane` column
  in place: `corrections._match_device_rows()` compares it verbatim against the
  CSV's literal `"Single Plane"` / `"Plane A"` / `"Plane B"` strings, so replacing
  those values with `single`/`A`/`B` would make every `k_tab` lookup miss and
  fail soft to `1.0` — a silent, global dose change. Add a regression test that
  fails if canonicalization changes any `k_tab` value.
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
- [ ] When renaming the `dev-docs/glossary.json` `k_tab` preferred term (currently
  "table transmission correction"), keep the previous term and "table transmission"
  as aliases so existing copy and searches still resolve.

## Acceptance Criteria

1. No transmission value — bundled lookup, custom lookup, or the default
   `estimate_k_tab` scalar — can silently multiply intersected dose by a
   non-finite, non-positive, or greater-than-one factor.
2. Valid existing correction results remain unchanged.
3. An inherited AlluraClarity Plane B zero produces warned-neutral `1.0`, explicit
   invalid-source status, and the characterized dose delta instead of silent zeroing.
4. DICOM tube A/B/single identity is code-backed and auditable, and canonical
   identity is exposed additively without changing any `k_tab` lookup result.
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
