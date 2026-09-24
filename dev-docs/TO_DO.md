# TO DO

Short active backlog for GUISkinDose. Keep this file focused on actionable work and open questions; use
`CHANGELOG.md`, archived plans, and `dev-docs/index.md` for historical traceability. Release/distribution
map (PyPI, GitHub notes vs changelog, deferred portable executables):
[RELEASES_AND_DISTRIBUTION.md](RELEASES_AND_DISTRIBUTION.md).

House rule: keep each item to a few lines — what, why, acceptance. Design detail, evidence, and
history belong in the linked plan, assessment, or maintenance log, not here. Keep this file near
250 lines (checked by `scripts/check_agent_guidance.py`).

For harness rules, validation commands, and plan conventions, see
[HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md). For backlog lifecycle rules, see
[AGENT_PLAYBOOK.md](AGENT_PLAYBOOK.md): completed items must be removed from this file after their user-facing or
maintenance impact is logged — in the same PR once the work lands (not post-merge) — and completed plans must
be archived.

---

## Next Up

- [ ] **GUI network-exposure hardening** — See "GUI network-exposure hardening" in
  the GUI/UX backlog section.
- [ ] **Manual Smokes** — See "Manual Smokes" in the Active Work section (includes
  confirming the Open Questions "Results — vs kerma" note, then deleting that Open Questions entry).
- [ ] **Reusable custom equipment profiles** — See "Correction-data modernization
  roadmap" in Active Work / [CUSTOM_EQUIPMENT_PROFILES_PLAN.md](plans/CUSTOM_EQUIPMENT_PROFILES_PLAN.md).
- [ ] **Rotational-acquisition handling** — See "Review rotational-acquisition
  handling" in the Product Backlog (Input Data And Calculation) section.

## Active Work

- [ ] **Correction-data modernization roadmap** — umbrella and current-state reference:
  [CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md](plans/CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md).
  Plan 1 (correction safety and tube identity) is archived; the packaging/runtime
  fix shipped (Phases A–D, 2026-09-19;
  [packaging/provenance master plan](plans/CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md)).
  Remaining delivery:
  1. **Separate future feature (see Next Up):** [reusable custom equipment/model profiles](plans/CUSTOM_EQUIPMENT_PROFILES_PLAN.md).
  2. **Separate research/physics work:** [closed-volume table/pad intersection and evidence-gated path-length transmission](plans/GEOMETRY_DRIVEN_SUPPORT_TRANSMISSION_PLAN.md).
- [ ] **Manual Smokes** — Compile and execute manual smokes for shipped features:
  - *Multi-exam*: multi-file upload, per-exam overrides, calculate, results accordion.
  - *Correction safety / tube identity*: run the scenarios in [CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md](plans/archive/CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md) Validation — unmatched model names the real scanner, GE-family unmatched claims no Tx/Tz auto-swap, ambiguous Plane B / DoseTrack map, valid Plane A, multi-exam mixed match/fallback.
  - *Settings phantom preview*: acceptance checklist in [SETTINGS_PHANTOM_PREVIEW_PLAN.md](plans/SETTINGS_PHANTOM_PREVIEW_PLAN.md), then archive the plan.
  - *Rich export*: Export-tab modal in browser + native pywebview; Windows native file dialogs.
  - *Results table*: confirm '—' vs kerma behavior (see Open Questions).

## Product Backlog

### Input Data And Calculation

- [ ] **Explore additional phantoms** — keep expanding anthropomorphic coverage beyond the shipped MPFB v1
  catalog (Phases 0–4 complete; see
  [archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md](plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md)). Survey and
  integration notes: [ADDITIONAL_PHANTOMS.md](ADDITIONAL_PHANTOMS.md). Fun/demo backlog:
  [FUN_DEMO_PHANTOMS_PLAN.md](plans/FUN_DEMO_PHANTOMS_PLAN.md). Demo v1 + QA/demo gate / thick bariatric are
  archived under `plans/archive/`.
- [ ] **Consider user-imported custom meshes** — GUI/CLI pipeline for user-supplied STL phantoms: orient/scale into the PSD frame, watertight/face-up validate, local non-committed cache, Settings selector + preview (prior art: `scripts/phantom_gen/ingest_fun_mesh.py`, `validate_phantom.py`). License/redistribution stays with the user (see [references/fun_phantom_provenance.md](references/fun_phantom_provenance.md)).
- [ ] **Simplified DICOM-only estimate** — investigate a fast pre-scan/fallback estimate from DICOM fields without
  the full phantom-mesh pipeline.
- [ ] **Run examples in JupyterLab and compare** — confirm notebook examples remain useful and current.
- [ ] **Anode-angle awareness in HVL lookup** — add device-model anode-angle mapping, angle-aware lookup, and
  nearest-angle warnings; see [hvl-interpolation-and-below-floor-kvp.md](plans/archive/hvl-interpolation-and-below-floor-kvp.md).
- [ ] **Rotational-acquisition handling (see Next Up)** — initial envelope implementation complete
  (classifier, normalizer contract, dose loop, prompt, exports, badge); source of truth:
  [coverage-envelope plan](plans/ROTATIONAL_COVERAGE_ENVELOPE_PLAN.md), with the historical/current-code
  [assessment](assessments/ROTATIONAL_ACQUISITION_ASSESSMENT.md). Remaining: per-event override UI,
  scenarios/nominal-arc selection UI, XA-header direction ingestion, film/array validation.
  Additional vendor fixtures improve profiles but do not block.
- [ ] **XA-header direction/trajectory ingestion (future input source)** — classic RDSR carries no rotation direction (69-concept survey), but XA image headers do: `Positioner Motion (0018,1500)`, signed angle increments `(0018,1520/1521)`, and the 3D-XA acquisition sequence (scan arc/start/increments + per-projection angles). **Goal:** parse direction/trajectory from same-case XA headers to resolve arc direction. **Constraint:** needs image-object ingestion (pipeline is RDSR + tabular only) + RDSR↔XA case matching; same privacy fixture rules. See assessment §4.
- [ ] **RDSR parser input hardening (OpenREM upstream failures)** — three upstream OpenREM RF files fail `rdsr_parser` (missing top-level `Manufacturer`/`ManufacturerModelName`; one structural `IndexError`). **Goal:** fail-soft or clear errors. **Constraint:** do not vendor identifier-bearing files; reproduce with synthetic/cleared fixtures. Survey: [assessment](assessments/ROTATIONAL_ACQUISITION_ASSESSMENT.md), Phase 0 lead inventory. **Acceptance:** unit tests per failure; no change on bundled fixtures. Progress 2026-09-22: Allura (absent model tag → None) and GE (empty value sequences → None) guards shipped with synthetic tests; `RF-Pat-Orientation-Modifier-Missing` still open.
- [ ] **Biplane support and recognition** — detect A/B plane exports or RDSR events, model independent geometry,
  and combine PSD/dose maps.
- [ ] **Radimetrics detection triggers** — examine when and why the GUI assumes a file is from Radimetrics; it seems too quick to classify as such and may misidentify other sources.
- [ ] **`TabularImportOptions` + CLI coordinate override flags** — GUI post-normalization corrections (`Tx ↔ Tz`, `Ap1×−1`, `Ap2×−1`) are live, but the `TabularImportOptions` dataclass and `--swap-lat-lon` / `--skip-transforms` CLI surface are not wired (`cli_args.py`, `input_adapters/registry.py`). **Goal:** API + CLI parity with the GUI. **Acceptance:** unit tests for both paths. See [TABULAR_RDSR_INPUT_PLAN.md](plans/TABULAR_RDSR_INPUT_PLAN.md) and [VENDOR_COORDINATE_SYSTEMS.md](VENDOR_COORDINATE_SYSTEMS.md).
- [ ] **Tabular input Phase 5+** — implement Qaelum, DoseMonitor, and DoseWatch adapters when real export fixtures
  are available; see [TABULAR_RDSR_INPUT_PLAN.md](plans/TABULAR_RDSR_INPUT_PLAN.md).
- [ ] **Column-pattern customization** — support site-specific column-name overrides after Python-only adapter
  behavior is stable.
- [ ] **GE coordinate fixture confirmation** — obtain one matched GE DICOM RDSR + tabular export from the same case to pin regression values (travel-direction conventions already confirmed). See [references/ge_coordinate_validation.md](references/ge_coordinate_validation.md) and [COORDINATE_CONVENTIONS_CLEANUP_PLAN.md](plans/archive/COORDINATE_CONVENTIONS_CLEANUP_PLAN.md) Task 7.
- [ ] **Vendor coordinate validation** — confirm per-vendor export frames (beam position-field usage, gaps) and Philips double-correction risk against source RDSRs before expanding adapters. Code-level validation once fixtures exist (distinct from the GE acquisition above). See [VENDOR_COORDINATE_SYSTEMS.md](VENDOR_COORDINATE_SYSTEMS.md).
- [ ] **Patient orientation support (prone / decubitus + auto-detect)** — HFS/FFS already exist in settings, GUI, and
  geometry. Remaining: prone/decubitus positions and optional DICOM `PatientPosition` auto-detection. See
  [assessment](assessments/PATIENT_ORIENTATION_ASSESSMENT.md).
- [ ] **Add more normalizations and offsets for different models** — extend vendor/model-specific coordinate normalization and table-origin offsets to cover additional scanner models beyond current coverage.

### GUI / UX

- [ ] **GUI network-exposure hardening** — non-loopback refused outright (`_resolve_bind_host()` raises; `--host`/`--allow-network` flags removed): threat model + recorded refusal decision: [  assessment](assessments/GUI_NETWORK_EXPOSURE_ASSESSMENT.md). Shipped: non-loopback refusal, bundled font, per-launch token + strict Host/Origin checks (browser; Host/Origin only in native), packaged UI-copy catalog, loopback-scope help page, `--port` with OS-assigned support. Remaining: per-client state + real auth on a demonstrated clinical-LAN need **or shared/multi-user workstation requirement** (deferred, not scheduled — and then with TLS, authorization, session lifecycle, isolation, and audit, not auth alone).
- [ ] **Native GUI optional file logging** — `run_gui()` / `__main__` never pass `log_file`, so there is one console sink only (stderr), including `--native`. **Goal:** pass a temp-path `log_file` in native/pywebview mode. Privacy model: value-free logging boundaries stay as-is; file defaults to INFO (DEBUG only with an explicit `dprint` category); rotation ~1 MiB × 4, session purge, POSIX `0o600` (`guiskindose.debug`). **Acceptance:** manual native smoke shows the file; README + `PRIVACY_AND_SENSITIVE_ASSETS.md` updated; unit test for handler registration; privacy review of the enabled path. **Optional follow-on:** settings/CLI toggle to disable file logging on shared machines.
- [ ] **GUI clutter cleanup** — simplify the interface and hide lower-priority or advanced info behind warning/info buttons, collapsible cards, or similar patterns; consider other UX ideas for reducing cognitive load.
- [ ] **Better export-failure messaging** — when an export fails due to a missing dependency, show clear user-facing info and actionable warnings (e.g. which package to install and how).
- [ ] **Export audit trail for `table_origin_override`** — record per-exam table-origin overrides in normalized
  export metadata.
- [ ] **Expanded RDSR browser** — expose more irradiation-event detail after load.
- [ ] **In-app settings/workflow help** — link to `VENDOR_COORDINATE_SYSTEMS.md` and related technical docs.
- [ ] **Visual refinement** — reduce left-nav spacing, soften the brutalist look, tune fonts/light mode/backgrounds
  per [DESIGN.md](../DESIGN.md).
- [ ] **Central Help entry point** — per-tab `HelpButton`s and the help harness already ship. Remaining: add a
  left-nav Help item and/or dedicated Help tab that indexes in-app help (`gui/help/`) and links to the online docs.
- [ ] **Offset UX polish** — Geometry patient/table-origin sliders and Settings → Per-exam corrections already
  support interactive overrides (single- and multi-exam). Remaining: clearer per-exam offset summary, inline
  Geometry hints, and less nesting for advanced coordinate fixes. Optional arrow graphic is deferred separately.
- [ ] **3D mesh export** — export the patient phantom mesh with vertex colors (e.g., PLY format) for use in external 3D tools.
- [ ] **DICOM export** — export a DICOM Secondary Capture of the dose map or a DICOM SR to push results back to PACS.

### Harness / Repo Hygiene

- [ ] **Worktree hook environment tracking** — `commit-msg` hook path resolution is worktree-aware (`resolve_commit_message_path` checks `--git-common-dir`/`--git-dir`). Pre-push hooks (basedpyright, gui-test-placement) still resolve `guiskindose` from whichever editable install is on `PATH` — document or detect venv resolution when running pre-push hooks from linked worktrees.
- [ ] **Retire the pre-rename compatibility shims** — three independent pieces with different
  triggers (semgrep rules-file rename and rule-ID rename: any time, atomic diff required, no
  migration dependency; legacy config-read/env shims: after the user-migration window).
  Full sequencing, file lists, and the migration-window criterion are documented in
  `plans/archive/GUISKINDOSE_RENAME_PLAN.md` § "Post-PR-1 retirement".
- [ ] **Stale-brand CHANGELOG Unreleased pattern audit** — `CHANGELOG_CURRENT_PATTERNS` in
  `scripts/check_stale_brand.py` allow rename-prose in Unreleased. If more patterns are added,
  re-check that they still cannot hide an unquoted import of the pre-rename package.
- [ ] **Deferred documentation experience ideas** — after the documentation/help harness lands, evaluate the ideas
  intentionally left out of the implementation plan: screenshot-driven help regression tests, in-app "report
  inaccurate help" feedback, per-run processing-log narratives in exports, generated normalization-flow diagrams,
  and release documentation audit checklist generation (fold into
  [RELEASES_AND_DISTRIBUTION.md](RELEASES_AND_DISTRIBUTION.md) if pursued). Original brainstorm:
  [DOCUMENTATION_AND_HELP_INFRASTRUCTURE_BRAINSTORM.md](plans/archive/DOCUMENTATION_AND_HELP_INFRASTRUCTURE_BRAINSTORM.md).
- [ ] **Re-check ignored dependency advisories** — quarterly or pre-release (see [RELEASES_AND_DISTRIBUTION.md](RELEASES_AND_DISTRIBUTION.md)): run
  `python scripts/audit_dependencies.py`, review `[tool.uv.audit]` in `pyproject.toml`. Current state: Dependabot alerts #2/#3/#4 stay open until semgrep relaxes its `mcp==1.23.3` pin (`mcp` is transitive dev-only, not exploitable here); `nltk` advisory resolved when `safety` was removed (2026-09-03). CI's `uv audit` is the gate that matters.
- [ ] **Scheduled inter-release grype scan** — add a weekly `grype-scheduled.yml` workflow that builds and scans without publishing, to catch CVEs disclosed between releases. Dependabot already covers Python dep bumps; this would catch supply-chain issues in the built artifact specifically. Fits the release/artifact map in [RELEASES_AND_DISTRIBUTION.md](RELEASES_AND_DISTRIBUTION.md); release-time grype already runs in `release.yml`.
- [ ] **Optional supply-chain hardening** — enable GitHub code scanning/security alerts, release SBOM upload, or
  Trufflehog only if needed beyond gitleaks. Coordinate with [RELEASES_AND_DISTRIBUTION.md](RELEASES_AND_DISTRIBUTION.md) / `PUBLISHING.md` so SBOM or extra scanners attach to the real publish path.
- [ ] **Doc-freshness follow-ups** — add intentional stale-word excludes, extend inventory contradiction rules, and
  consider release-only strict stale-pattern checks (candidate release gate; see
  [RELEASES_AND_DISTRIBUTION.md](RELEASES_AND_DISTRIBUTION.md)).
- [ ] **Optional doc-pruning release gate** — run `python scripts/check_doc_pruning.py --strict` before releases
  once the team is comfortable with the advisory workflow (add to the hub checklist when enabled).
- [ ] **Architecture follow-ups** — evaluate `import-linter` if layer contracts grow; revisit documented
  `phantom_class` -> `plotting` coupling.
- [ ] **Getting-started notebook execution failure in docs builds** — nbsphinx execution of the getting-started notebook fails on a plot/HTML regression (error record + fix plan archived at
  [NOTEBOOK_PLOT_HTML_FIX_PLAN.md](plans/archive/NOTEBOOK_PLOT_HTML_FIX_PLAN.md)).
  Remaining: confirm the docs build is green (watch for a second latent failure
  behind it — see archived plan for the secondary tqdm failure), then remove this item.
- [ ] **GUI test depth** — add per-tab smoke coverage if NiceGUI user simulation remains enough; consider
  Playwright/CDP only for browser-specific gaps.
- [ ] **Coordinate diagrams** — expand and validate `VENDOR_COORDINATE_SYSTEMS.md` diagrams against vendor data.
- [ ] **Plan template** — add shared headers for objective, acceptance criteria, progress log, and decision log.
- [ ] **Expand `dev-docs/references/` stubs** before the next major dependency review.

## Deferred Until Needed

- [ ] **Privacy hardening follow-ons (parked)** — Phases 0-9 done ([PRIVACY_HARDENING_PLAN.md](plans/PRIVACY_HARDENING_PLAN.md)); Phase 10 needs an approved private environment. Follow-ons below are parked evaluations, not a restart. Revisit only when privacy work is next prioritized:
  - *Nested/unsupported containers* — recursive inspection vs blocking for nested archives and exotic types (7z/RAR); current gate scans first-level text + requires manual clearance.
  - *Local OCR bake-off* — benchmark Tesseract vs local-only ML OCR on synthetic burned-in fixtures (accuracy, runtime, report safety); no CI/uploads until written up. See [LOCAL_PII_MODELS.md](references/LOCAL_PII_MODELS.md).
  - *Local PII detector evaluation* — benchmark the Presidio runner vs Fastino GLiNER2 on the synthetic-fixture protocol; keep only if worth a scheduled advisory check.
  - *NVIDIA GLiNER-PII macOS trial* — verify local execution, licensing, throughput, and memory on the Mac; advisory only, never CI.
  - *DICOM pixel-PHI scanner keep/drop* — decide whether the `dicom-phi-scan` wrapper stays as a local advisory step on synthetic fixtures; never replaces human clearance or runs in public CI.
- [ ] **HTML/PNG export root-cause fix (awaiting fresh repro)** — Phase 1 (raise +
  actionable errors) shipped; Phase 0 never captured the original multi-exam
  exception, so Phase 2 has no evidence to work from. Demoted from Next Up
  2026-09-11: no further action until a new incident reproduces it. Re-trigger:
  on the next real failure, capture the exception via the Phase 0 instrumentation,
  then run Phase 2 + Phase 3 closeout. Plan:
  [HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md](plans/HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md). Assessment:
  [HTML_EXPORT_BACKGROUND_TASK_ERROR_20260719T123241.md](assessments/HTML_EXPORT_BACKGROUND_TASK_ERROR_20260719T123241.md).
- [ ] **Split `constants.py`** — defer until the file grows hard to navigate or a large new constant block is added.
- [ ] **Narrow broad `except Exception` sites** — avoid repo-wide sweeps; tighten only where a broad catch masks a
  bug or when already editing that boundary.
- [ ] **Full GUI observability stack** — defer until smoke/tab tests show a concrete observability gap.
- [ ] **Geometry offset arrow (interactive offsets Phase 3)** — optional visual arrow for offsets; deferred when
  Phases 0–2b shipped. See
  [archive/INTERACTIVE_TABLE_OFFSETS_PLAN.md](plans/archive/INTERACTIVE_TABLE_OFFSETS_PLAN.md).
- [ ] **Rich export — phantom dimensions** — report AP / L-R / S-I phantom extents in cm (max/thickest) in rich
  reports rather than scale factors only. See [RICH_EXPORT_PLAN.md](plans/RICH_EXPORT_PLAN.md).
- [ ] **Rich export — polish (Phase 7 leftovers)** — multi-exam image-cap GUI toggle (7.1); deeper tagged-PDF/DOCX
  accessibility + alt text, HTML already sets `alt` (7.2); extract user-visible strings to a localization module
  (7.3); align the Results tab correction table to include `k_med` as a small separate PR (7.4); Export-tab help
  page if a central Help index lands.
- [ ] **Rich export — minor code deferrals** — set explicit `openpyxl` `cell.number_format` on numeric XLSX cells
  (values are pre-formatted strings today); add browser `showSaveFilePicker()` progressive enhancement (must never
  replace the baseline `ui.download()` fallback).
- [ ] **Portable GUI executable (PyInstaller / `nicegui-pack`)** — research:
  [references/PORTABLE_EXECUTABLE_PACKAGING.md](references/PORTABLE_EXECUTABLE_PACKAGING.md);
  release map: [RELEASES_AND_DISTRIBUTION.md](RELEASES_AND_DISTRIBUTION.md). Spike only when a
  non-Python distribution path is prioritized; expect large per-OS artifacts and bundle package data
  (phantoms, `corrections.db`, help). Not a Java wrap.
- [ ] **Fixture-DICOM identifier scrub** — the upstream-inherited serials/lab codes
  in `device_info.csv` are substituted with synthetic tokens (Phase A), but the same
  identifiers persist in 4 hash-pinned approved fixture DICOMs and 2 asserting test
  files (retained under the KG 2026-07-16 asset-inventory approval). A full binary
  scrub would invalidate clearance, force re-clearance, and risk golden tests for
  identifiers public upstream since 2018. Revisit only under a future privacy review
  with maintainer re-clearance. See
  [CORRECTION_DATA_PHASE_A_MANIFEST_VALIDATION_PLAN.md](plans/archive/CORRECTION_DATA_PHASE_A_MANIFEST_VALIDATION_PLAN.md).

## Open Questions

- **Original flow inputs** — Do examples need JSON sidecars, different normalization settings, or other files to
  avoid unexpected body-region projections?
- **Results “—” vs kerma (likely resolved)** — Older note: “Results table shows K_IRP as `-`.” Current GUI:
  Data Table has a real `K_IRP (mGy)` column from the normalized events; Results shows **Total Air Kerma**
  (sum of reported K_IRP) and a **Correction factors per event** table (`k_isq` / `k_bs` / `k_tab`) that uses
  `—` for missing/empty correction slots (e.g. zero-hit events), not as a stand-in for kerma. Metric cards also
  show `—` before a calculation finishes. See the Manual Smokes item in Next Up / Active Work to confirm and delete.
