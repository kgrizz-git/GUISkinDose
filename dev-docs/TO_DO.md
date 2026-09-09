# TO DO

Short active backlog for GUISkinDose. Keep this file focused on actionable work and open questions; use
`CHANGELOG.md`, archived plans, and `dev-docs/index.md` for historical traceability. Release/distribution
map (PyPI, GitHub notes vs changelog, deferred portable executables):
[RELEASES_AND_DISTRIBUTION.md](RELEASES_AND_DISTRIBUTION.md).

For harness rules, validation commands, and plan conventions, see
[HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md). For backlog lifecycle rules, see
[AGENT_PLAYBOOK.md](AGENT_PLAYBOOK.md): completed items must be removed from this file after their user-facing or
maintenance impact is logged, and completed plans must be archived.

---

## Next Up

- [ ] **Immediate Correction Work** — Land the safety PR for
  [correction safety and tube identity](plans/CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md)
  (transmission validation, tube identity, unmatched-scanner GUI, terminology),
  then finish that plan’s **Remaining before Plan 1 archive** section (plane-identity
  audit/export parity; structured `k_tab` invalid-source status / pre-calc match
  preview). After Plan 1 is archived, continue with
  [correction packaging and provenance](plans/CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md).

  **Conscious sign-offs (keep fail-loud unless product asks otherwise):**
  - Kerma CF tables with an unrecognized tube label abort the whole table at
    load (no silent per-row skip).
  - Measured `k_tab` with `k_tab_val=0` / invalid transmission fails at dose
    calculation (not at settings construction); inherited AlluraClarity Plane B
    zeros are already neutralized to warned `1.0` on the measured path.

  **Review follow-ups (soon / with Plan 1 archive leftovers):**
  - Tabular raw-code → `acquisition_plane_canonical` without a DCM designator
    can over-claim code-backed identity (audit trail only; dose path unchanged).
    Close with plan remaining item #1 (`acquisition_plane_source_kind` /
    `acquisition_plane_resolution`). Comment lives in `rdsr_normalizer.py`.
  - Optional hardening: assert uniqueness of measured `k_tab` DB rows on
    `(model, plane, kVp, Cu, Al)` so exact-match `iloc[0]` cannot silently
    choose among duplicates (`corrections.py`).
  - DoseTrack mixed CID `{Single Plane, Plane A/B}` now warns on import; watch
    for noisy false positives on unusual site exports.
- [ ] **PSD calculation algorithm doc + harness** — After Plan 1 PR merge (or in
  parallel on a separate branch once review is idle), write a canonical PSD
  calculation algorithm page under `dev-docs/` (proposed filename
  `PSD_CALCULATION_ALGORITHM.md` — create the file when starting this item) and
  wire light doc-maintenance hooks.
  Parked so CodeRabbit / Plan 1 closure is not blocked. Outline to cover:

  **Algorithm stages (user-requested):**
  1. Read irradiation events (RDSR DICOM and/or tabular imports).
  2. Identify and apply correct vendor/unit/coordinate transformations and
     patient/table offsets into the internal normalized frame.
  3. Identify and apply correction factors (`k_meter` when enabled, then
     `k_isq`, `k_bs`, `k_med`, patient-support `k_tab`, plus HVL / below-floor
     kVp policy as prerequisites for backscatter/medium).
  4. Project X-ray fields from the source per exposure (angles, SID/IRP
     distances, collimated field size / field-size mode).
  5. Determine intersections with table/pad and patient phantom (table
     coordinates, phantom size/contours/normals; `Beam.check_hit`,
     `check_table_hits`).
  6. Accumulate dose cumulatively over exposures and exams (per-exam maps;
     multi-exam aggregate = sum of aligned dose maps; PSD = max of map).
  7. Report peak skin dose and supporting outputs (dose map, corrections,
     warnings).

  **Also document (easy to overlook):** phantom placement / habitus scales;
  geometry-change reuse; beam-miss diagnostics; kerma CF keyed by equipment ×
  tube without special-casing A/B geometry; measured `k_tab` table keyed by
  device × plane string (lookup identity only — projection math stays
  plane-agnostic); invalid-row / out-of-range transmission handling;
  Implementation-deviations section vs live code.

  **Harness work (do with the doc, not a separate forgotten PR):** register in
  `dev-docs/index.md`, `HARNESS_ENGINEERING.md` source-of-truth map, and
  `AGENTS.md`; add a `psd_calculation` (or equivalent) row in
  `feature_doc_matrix.json` covering `calculate_dose/`, `geom_calc.py`,
  `beam_class.py`, `corrections.py`, `kerma_correction.py`, normalizer/adapters;
  optional invariant tests in the style of `test_input_schema_doc.py`; use
  matrix `--against-ref` / impact review when dose-path code changes; keep a
  short Sphinx/user pointer rather than duplicating the full narrative.
- [ ] **PSD algorithm flow diagram** — Add a sequence diagram and/or Mermaid
  flowchart of input → normalize → position → per-event loop (field projection,
  intersections, corrections, accumulate) → per-exam / multi-exam aggregate →
  PSD, with links to the real modules. Host under `dev-docs/` (e.g. beside or
  embedded in `PSD_CALCULATION_ALGORITHM.md`) and **link it from the algorithm
  doc** when that page is written. Update the diagram when dose-pipeline code
  changes (same harness/matrix watch as the algorithm doc).
- [ ] **Settings/Calculate Fallback badge visibility** — Upload alert now binds to
  non-empty `normalization_warnings`. Settings and Calculate still bind badges to
  global `normalization_method == "Fallback"` (`settings.py`, `calculate.py`);
  `restore_globals_from_exam_meta` does not restore that field, so multi-exam
  remove can leave stale badges. Align those tabs with the warning-list binding
  (or restore `normalization_method` from remaining exam meta) in a small follow-up.
- [ ] **User-Facing Docs Tooling Evaluation** — See "User-Facing Documentation Tooling Evaluation" in the Active Work section.
- [ ] **Privacy Hardening** — See [PRIVACY_HARDENING_PLAN.md](plans/PRIVACY_HARDENING_PLAN.md).
- [ ] **HTML/PNG Export Fix** — See [HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md](plans/HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md).
- [ ] **Manual Smokes** — See "Manual Smokes" in the Active Work section.

## Active Work

Privacy hardening is implemented through Phase 9
([PRIVACY_HARDENING_PLAN.md](plans/PRIVACY_HARDENING_PLAN.md)); Phase 10 (private history/release-object audit)
still needs an approved private environment. Remaining privacy bullets below are follow-on evaluations or
policy decisions, not a restart of Phases 0-9.

- [ ] **Correction-data modernization roadmap** — umbrella and current-state reference:
  [CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md](plans/CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md).
  Delivery is deliberately split:
  1. **Immediate bug fix:** [Plane B safety, tube identity, unmatched-model alerts, and transmission terminology](plans/CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md)
     — safety core is implemented on `fix/correction-safety-tube-identity`; remaining
     closure items are listed in that plan’s **Remaining before Plan 1 archive**
     section (do not archive until those are done or relocated).
  2. **Packaging/runtime fix:** [correction provenance, package resources, and removal of the CWD database default](plans/CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md).
  3. **Separate future feature:** [reusable custom equipment/model profiles](plans/CUSTOM_EQUIPMENT_PROFILES_PLAN.md).
  4. **Separate research/physics work:** [closed-volume table/pad intersection and evidence-gated path-length transmission](plans/GEOMETRY_DRIVEN_SUPPORT_TRANSMISSION_PLAN.md).
- [ ] **Nested and unsupported container admission policy** — evaluate recursive inspection versus blocking for
  nested archives and unsupported container types (for example 7z/RAR); the current ZIP/TAR/GZIP and Office/iWork
  gate scans first-level text and requires manual embedded-file/image/DICOM clearance.
- [ ] **Local OCR quality bake-off** — `scripts/run_image_privacy_advisory.py` already runs local Tesseract OCR
  (value-suppressed) for admission of rendered assets. Remaining: benchmark Tesseract vs a local-only ML OCR option
  on synthetic image/PDF/Office/iWork/DICOM burned-in fixtures; record false positives/misses, runtime, and report
  safety; decide whether to keep Tesseract-only, add ML OCR, or change admission gating. Do not upload reports or
  add OCR to CI until that write-up exists. See [LOCAL_PII_MODELS.md](references/LOCAL_PII_MODELS.md).
- [ ] **Local PII/PHI detector evaluation** — use
  [LOCAL_PII_MODELS.md](references/LOCAL_PII_MODELS.md)'s synthetic-fixture protocol to benchmark the existing
  Presidio runner against Fastino GLiNER2. Record false positives/misses, thresholds, elapsed time, and peak memory
  without logging matched values; decide whether either is worth retaining as a scheduled advisory check.
- [ ] **NVIDIA GLiNER-PII macOS trial** — following
  [LOCAL_PII_MODELS.md](references/LOCAL_PII_MODELS.md), verify local Python/PyTorch execution, MPS/CPU behavior,
  model-license fit, download/cache location, throughput, and memory on the 128-GB Mac. Keep it local and advisory;
  do not add it to CI or use LM Studio as its runtime unless the trial establishes a supported path.
- [ ] **DICOM pixel-PHI scanner keep/drop** — `scripts/run_dicom_phi_advisory.py` already wraps `dicom-phi-scan`
  (CPU, ephemeral raw report, count-only summary) for conditional admission. Remaining: run it only on synthetic
  DICOM fixtures, confirm report output cannot leak findings, and decide whether to keep it as a local advisory
  step. It must never replace human DICOM inventory clearance or run in public CI without a separate approval.
- [ ] **User-Facing Documentation Tooling Evaluation** — time-boxed spike to decide whether to keep Sphinx or adopt
  a more polished end-user docs site. Candidates, dual-agent findings (2026-09-06), shortlist, and open verification
  items: [assessment](assessments/DOCUMENTATION_TOOLING_EVALUATION_2026-09-06.md). Record the outcome in a decision log.
- [ ] **Manual Smokes (Next Up)** — Compile and execute manual smokes for shipped features:
  - *Multi-exam*: exercise multi-file upload, per-exam overrides, calculate, and results accordion in the GUI.
  - *Correction safety / tube identity*: unmatched model → Default warning names real scanner; GE-family unmatched does **not** claim Tx/Tz auto-swap applied; valid Plane A; ambiguous Plane B / DoseTrack map; multi-exam mixed match/fallback (see [CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md](plans/CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md) Validation).
  - *Settings phantom preview*: run the acceptance checklist in [SETTINGS_PHANTOM_PREVIEW_PLAN.md](plans/SETTINGS_PHANTOM_PREVIEW_PLAN.md), then archive the plan.
  - *Rich export browser/native save*: verify Export-tab modal in real browser and native pywebview mode.
  - *Rich export native file dialogs*: run Windows manual smoke for native 'Open file / Open folder'.
  - *Results table*: run a manual Results smoke to confirm '—' vs kerma behavior (see Open Questions).
- [ ] **Finish HTML/PNG export fix** — Phase 1 (raise + actionable errors) shipped; Phase 0 did not capture the
  original multi-exam exception, so Phase 2 root-cause fix + Phase 3 closeout remain. Plan:
  [HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md](plans/HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md). Assessment:
  [HTML_EXPORT_BACKGROUND_TASK_ERROR_20260719T123241.md](assessments/HTML_EXPORT_BACKGROUND_TASK_ERROR_20260719T123241.md).

## Product Backlog

### Input Data And Calculation

- [ ] **Explore additional phantoms** — keep expanding anthropomorphic coverage beyond the shipped MPFB v1
  catalog (Phases 0–4 complete; see
  [archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md](plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md)). Survey and
  integration notes: [ADDITIONAL_PHANTOMS.md](ADDITIONAL_PHANTOMS.md). Fun/demo backlog:
  [FUN_DEMO_PHANTOMS_PLAN.md](plans/FUN_DEMO_PHANTOMS_PLAN.md). Demo v1 + QA/demo gate / thick bariatric are
  archived under `plans/archive/`.
- [ ] **Consider user-imported custom meshes** — explore a GUI/CLI pipeline so users can bring their own STL (or similar) meshes as patient phantoms: upload → unit/orientation/scale into the PSD frame → watertight/face-up validate → local (non-committed) cache → Settings selector + preview. Reuse ideas from `scripts/phantom_gen/ingest_fun_mesh.py` / `validate_phantom.py`; keep license/redistribution responsibility with the user (see [references/fun_phantom_provenance.md](references/fun_phantom_provenance.md) for shippable vs local-only mesh policy).
- [ ] **Simplified DICOM-only estimate** — investigate a fast pre-scan/fallback estimate from DICOM fields without
  the full phantom-mesh pipeline.
- [ ] **Run examples in JupyterLab and compare** — confirm notebook examples remain useful and current.
- [ ] **Anode-angle awareness in HVL lookup** — add device-model anode-angle mapping, angle-aware lookup, and
  nearest-angle warnings; see [hvl-interpolation-and-below-floor-kvp.md](plans/archive/hvl-interpolation-and-below-floor-kvp.md).
- [ ] **Review rotational-acquisition handling** — determine whether spin/rotational acquisitions need dose spread
  across per-frame or start/end angles.
- [ ] **Biplane support and recognition** — detect A/B plane exports or RDSR events, model independent geometry,
  and combine PSD/dose maps.
- [ ] **Radimetrics detection triggers** — examine when and why the GUI assumes a file is from Radimetrics; it seems too quick to classify as such and may misidentify other sources.
- [ ] **`TabularImportOptions` + CLI coordinate override flags** — Phase 3 §5 audit found
  `VENDOR_COORDINATE_SYSTEMS.md` previously described a future `TabularImportOptions` dataclass and
  `--swap-lat-lon` / `--skip-transforms` CLI flags as if they shipped with the GUI toggles. GUI
  post-normalization corrections (`Tx ↔ Tz`, `Ap1×−1`, `Ap2×−1`) are live via `AppState` /
  `exam_transforms.py`; the dataclass, `skip_manufacturer_transforms`, `custom_translation_offset`,
  and CLI flags are not wired in `cli_args.py` or `input_adapters/registry.py`. **Goal:** expose the
  same override surface on `read_and_normalize_input()` and headless CLI. **Acceptance:** unit tests
  for API + CLI paths; docs describe shipped GUI vs API/CLI parity. See
  `TABULAR_RDSR_INPUT_PLAN.md` and `VENDOR_COORDINATE_SYSTEMS.md`.
- [ ] **Tabular input Phase 5+** — implement Qaelum, DoseMonitor, and DoseWatch adapters when real export fixtures
  are available; see [TABULAR_RDSR_INPUT_PLAN.md](plans/TABULAR_RDSR_INPUT_PLAN.md).
- [ ] **Column-pattern customization** — support site-specific column-name overrides after Python-only adapter
  behavior is stable.
- [ ] **Fix raw_events_cleaned example RDSR parsing** — investigate and fix the parsing issue that led to the problematic `raw_events_cleaned example RDSR (old) csv export from guiskindose.csv` in `test_data_gitignored/`.
- [ ] **GE coordinate fixture confirmation** — obtain one matched GE DICOM RDSR + tabular export from the same
  case to pin exact regression values. GE table-travel direction (positive lateral = patient left, longitudinal =
  cranial, height = down for HFS) and the normalizer-level `Tx`/`Tz` correction are already confirmed; this item
  is for pinning raw numeric fixture values only. See [references/ge_coordinate_validation.md](references/ge_coordinate_validation.md)
  and [plans/archive/COORDINATE_CONVENTIONS_CLEANUP_PLAN.md](plans/archive/COORDINATE_CONVENTIONS_CLEANUP_PLAN.md) Task 7.
- [ ] **Beam lateral/longitudinal position usage** — check whether beam lateral and longitudinal position fields (similar to those used for table position) are used elsewhere in the codebase, and document or fill any gaps.
- [ ] **Vendor coordinate validation** — confirm per-vendor export frames and Philips double-correction risk against
  source RDSRs before expanding vendor adapters. See [VENDOR_COORDINATE_SYSTEMS.md](VENDOR_COORDINATE_SYSTEMS.md).
- [ ] **Patient orientation support (prone / decubitus + auto-detect)** — HFS/FFS already exist in settings, GUI, and
  geometry. Remaining: prone/decubitus positions and optional DICOM `PatientPosition` auto-detection. See
  [assessment](assessments/PATIENT_ORIENTATION_ASSESSMENT.md).
- [ ] **Add more normalizations and offsets for different models** — extend vendor/model-specific coordinate normalization and table-origin offsets to cover additional scanner models beyond current coverage.

### GUI / UX

- [ ] **Native GUI optional file logging** — Phase 3 §4 audit found README/PRIVACY previously claimed
  `<tempdir>/guiskindose-gui.log`, but `run_gui()` and `__main__` call `configure_logging()` **without**
  `log_file` (`gui/app.py`, `__main__.py`). **Today:** one console sink only (stderr via
  `logging.StreamHandler` in `guiskindose.debug`); no log file in any mode, including `--native`.
  **Redaction / privacy model (stderr today; same rules would apply to a file sink):**
  - **Not a blanket redaction filter** on every log line — console and file share the same logger tree,
    formatters, and call sites. Privacy is enforced by **what we log**, plus **handler levels**.
  - **Value-free error paths (stderr today):** GUI/CLI boundaries use `safe_error_event()` /
    `safe_user_error()` (`guiskindose.privacy`) — operation code + exception **class** only on the
    one-line summary; optional value-free traceback at DEBUG (package-relative `path:lineno in func`,
    no exception message, no absolute paths, no locals). CLI uncaught exceptions go through
    `install_value_safe_excepthook()` (generic stderr message, no raw traceback). GUI load failures
    use the same pattern (`gui/exam_loaders.py` → `_record_load_failure`).
  - **Routine INFO/WARNING (stderr today):** convention avoids patient identifiers and source paths
    (e.g. upload logs suffix + byte count, RDSR read logs extension only). Prefer `safe_warning()`
    for coded metrics; avoid string metrics that could become filenames.
  - **Opt-in DEBUG (`debug.json` → `dprint` categories):** when a category is enabled, DEBUG lines
    go to **stderr** (and would also go to a file once wired). These are developer toggles, not
    clinical-safe by default — review before sharing captures. Do not assume “debug on ⇒ fully
    redacted”; review output for PHI before pasting or attaching logs.
  - **File handler level gate (when `log_file=` is used):** `_file_handler_level()` keeps the file at
    **INFO** unless a `dprint` category is explicitly enabled, then **DEBUG** — so module DEBUG
    records (which *could* include paths if a call site regresses) are excluded from the file by
    default. Same records as stderr that pass the file handler’s level; **no separate redaction pass**
    on write. Rotation: ~1 MiB × 4, session purge, POSIX `0o600` (`debug.py`).
  **Goal:** when `--native` / pywebview mode is active, pass a temp-path `log_file` into
  `configure_logging()` so diagnostics are visible without a terminal. **Acceptance:** manual native
  smoke shows the log file; README + `PRIVACY_AND_SENSITIVE_ASSETS.md` describe console + optional
  file sinks and the redaction/level model accurately; unit test that native startup registers a file
  handler (mock temp dir); privacy review confirms no new path/identifier logging on the enabled path.
  **Optional follow-on:** settings/CLI toggle to disable file logging on shared machines.
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
- [ ] **Reproducible settings export** — export `PyskindoseSettings` or GUI state as JSON to easily reload and reproduce runs.
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
- [ ] **Re-check ignored dependency advisories** — quarterly (or before each release; see release checklist in
  [RELEASES_AND_DISTRIBUTION.md](RELEASES_AND_DISTRIBUTION.md)), run
  `python scripts/audit_dependencies.py` and review `[tool.uv.audit]` in `pyproject.toml`.
  (2026-07-09: bumped transitive dev-only `nltk` 3.9.4 → 3.10.0 and removed
  `GHSA-p4gq-832x-fm9v` / `PYSEC-2026-597` suppressions.
  2026-07-17: added mcp GHSA-jpw9-pfvf-9f58 / GHSA-hvrp-rf83-w775 / GHSA-vj7q-gjh5-988w
  suppressions while semgrep pins `mcp==1.23.3`; remove when semgrep bumps or relaxes the pin.)
  (2026-07-18: confirmed GitHub Dependabot still opens alerts for these GHSA IDs — alerts #2/#3/#4 on
  `kgrizz-git/GUISkinDose` — because the `uv.lock`-level `dep_scope` reads as `runtime` to Dependabot and GitHub's
  advisory feed is independent of `[tool.uv.audit]` ignores. CI's `uv audit` is the gate that matters; the Dependabot
  alerts are informational and should stay open until semgrep bumps/relaxes its `mcp==1.23.3` pin
  (patched versions are `mcp >=1.27.2` / `>=1.28.1`). Context: `mcp` is transitive via the optional Semgrep MCP server
  path and is not imported or run by GUISkinDose runtime code, so the CVEs are not exploitable in this repo.
  2026-09-03: removed the `safety` dev dependency (and its main-only CI scan job), which removes
  transitive `nltk` entirely — the `GHSA-8mgp-746c-j5xp` / CVE-2026-81726 `ignore-until-fixed`
  entry and the `nltk` pin were deleted in the same change.)
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
- [ ] **GUI test depth** — add per-tab smoke coverage if NiceGUI user simulation remains enough; consider
  Playwright/CDP only for browser-specific gaps.
- [ ] **Coordinate diagrams** — expand and validate `VENDOR_COORDINATE_SYSTEMS.md` diagrams against vendor data.
- [ ] **Plan template** — add shared headers for objective, acceptance criteria, progress log, and decision log.
- [ ] **Expand `dev-docs/references/` stubs** before the next major dependency review.

## Deferred Until Needed

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

## Open Questions

- **Original flow inputs** — Do examples need JSON sidecars, different normalization settings, or other files to
  avoid unexpected body-region projections?
- **Results “—” vs kerma (likely resolved)** — Older note: “Results table shows K_IRP as `-`.” Current GUI:
  Data Table has a real `K_IRP (mGy)` column from the normalized events; Results shows **Total Air Kerma**
  (sum of reported K_IRP) and a **Correction factors per event** table (`k_isq` / `k_bs` / `k_tab`) that uses
  `—` for missing/empty correction slots (e.g. zero-hit events), not as a stand-in for kerma. Metric cards also
  show `—` before a calculation finishes. See the Manual Smokes item in Now / Next to confirm and delete.
