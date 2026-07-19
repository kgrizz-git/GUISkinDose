# TO DO

Short active backlog for MyPySkinDose. Keep this file focused on actionable work and open questions; use
`CHANGELOG.md`, archived plans, and `dev-docs/index.md` for historical traceability.

For harness rules, validation commands, and plan conventions, see [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md).

---

## Now / Next

Privacy hardening implementation is coordinated by
[PRIVACY_HARDENING_PLAN.md](plans/PRIVACY_HARDENING_PLAN.md); the individual privacy items below remain open until
their corresponding plan exit criteria pass.

- [ ] **Complete sensitive-asset baseline review** — manually clear every `pending` entry in
  `approved_asset_inventory.json`, including rendered-image and DICOM burned-in-text review. Record reviewer/date,
  then switch CI to `python scripts/check_sensitive_content.py --require-approved-assets`.
- [ ] **P0 — public-history PHI/PII exposure audit and response runbook** — before the next release, use an
  isolated local/private checkout to scan every reachable commit, tag, release branch, and relevant LFS/release
  artifact for the current value-suppressed PII/PHI/path rules and representative DICOM/image fixtures. Verify the
  process against synthetic known-positive history; never write matched values to a public log. Define triage,
  private evidence handling, disclosure, history rewrite, cache/clone limitations, secret rotation, maintainer
  notification, and re-scan/verification steps for a real finding.
- [ ] **Nested and unsupported container admission policy** — evaluate recursive inspection versus blocking for
  nested archives and unsupported container types (for example 7z/RAR); the current ZIP/TAR/GZIP and Office/iWork
  gate scans first-level text and requires manual embedded-file/image/DICOM clearance.
- [ ] **Local OCR evaluation for rendered assets** — evaluate conventional local OCR (for example Tesseract) and a
  local-only ML OCR option against synthetic image, PDF, Office/iWork preview, and DICOM burned-in-text fixtures.
  Keep source files, models, caches, intermediate images, and value-suppressed findings on an approved local machine;
  do not upload reports or add OCR to CI until false positives, misses, runtime, and report safety are documented.
- [ ] **Local PII/PHI detector evaluation** — use
  [LOCAL_PII_MODELS.md](references/LOCAL_PII_MODELS.md)'s synthetic-fixture protocol to benchmark the existing
  Presidio runner against Fastino GLiNER2. Record false positives/misses, thresholds, elapsed time, and peak memory
  without logging matched values; decide whether either is worth retaining as a scheduled advisory check.
- [ ] **NVIDIA GLiNER-PII macOS trial** — following
  [LOCAL_PII_MODELS.md](references/LOCAL_PII_MODELS.md), verify local Python/PyTorch execution, MPS/CPU behavior,
  model-license fit, download/cache location, throughput, and memory on the 128-GB Mac. Keep it local and advisory;
  do not add it to CI or use LM Studio as its runtime unless the trial establishes a supported path.
- [ ] **HoundDog local privacy-code-scanner proof of concept** — follow the isolated local-only procedure in
  [LOCAL_PII_MODELS.md](references/LOCAL_PII_MODELS.md): use a pinned standalone release with no API key, cloud,
  GitHub App, managed scans, PR comments, report upload, or optional AI analysis. Assess Python dataflow coverage,
  false positives, report safety, and license terms. It remains local-only until a maintainer explicitly changes the
  policy; do not add CI, cloud, GitHub App, managed scan, PR comments, report upload, or AI analysis.
- [ ] **DICOM pixel-PHI scanner evaluation** — source/dependency-review `dicom-phi-scan` and test it only against
  synthetic DICOM fixtures. Confirm its OCR/report output cannot leak findings before deciding on any local workflow;
  it must never replace human DICOM inventory clearance or run in public CI without a separate approval.
- [ ] **Check documentation completeness and accuracy** — verify `CODEBASE_OVERVIEW.md`, `FEATURE_INVENTORY.md`,
  `AGENTS.md`, and `HARNESS_ENGINEERING.md` against current code behavior.
- [ ] **Multi-exam manual smoke check** — exercise multi-file upload, per-exam overrides, calculate, and results
  accordion in the GUI.
- [x] **Geometry tab per-exam event selection** — let users select or step through events per exam; account for
  Plotly trace count and large datasets.
- [x] **Dose map per-exam checkbox controls** — show cumulative dose or selected exam subsets and update PSD/dose
  map live. See [DOSE_MAP_PER_EXAM_CHECKBOX_PLAN.md](plans/archive/DOSE_MAP_PER_EXAM_CHECKBOX_PLAN.md).
- [ ] **Fix download/export HTML button** — `require_io_result` conflates "callback returned None" with "task cancelled"; `make_dosemap_html`/`make_dosemap_png` swallow exceptions with no log (Results aggregate map can render while HTML export fails). Plan: [HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md](plans/HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md). Assessment: [HTML_EXPORT_BACKGROUND_TASK_ERROR_20260719T123241.md](assessments/HTML_EXPORT_BACKGROUND_TASK_ERROR_20260719T123241.md).

## Product Backlog

### Input Data And Calculation

- [ ] **Explore additional phantoms** — investigate and add support for new anthropomorphic phantoms. See [ADDITIONAL_PHANTOMS.md](ADDITIONAL_PHANTOMS.md) for potential sources.
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
- [ ] **Tabular input Phase 5+** — implement Qaelum, DoseMonitor, and DoseWatch adapters when real export fixtures
  are available; see [TABULAR_RDSR_INPUT_PLAN.md](plans/TABULAR_RDSR_INPUT_PLAN.md).
- [ ] **Column-pattern customization** — support site-specific column-name overrides after Python-only adapter
  behavior is stable.
- [ ] **Input field reference artifact** — check whether a clear list or table of fields expected/required by imported RDSR or tabular input (including fields mapped from those sources) already exists; if not, create a simple standalone file artifact that users can easily consult.
- [ ] **Fix raw_events_cleaned example RDSR parsing** — investigate and fix the parsing issue that led to the problematic `raw_events_cleaned example RDSR (old) csv export from mypyskindose.csv` in `test_data_gitignored/`.
- [ ] **GE coordinate fixture confirmation** — obtain one matched GE DICOM RDSR + tabular export from the same
  case to pin exact regression values. GE table-travel direction (positive lateral = patient left, longitudinal =
  cranial, height = down for HFS) and the normalizer-level `Tx`/`Tz` correction are already confirmed; this item
  is for pinning raw numeric fixture values only. See [references/ge_coordinate_validation.md](references/ge_coordinate_validation.md)
  and [plans/archive/COORDINATE_CONVENTIONS_CLEANUP_PLAN.md](plans/archive/COORDINATE_CONVENTIONS_CLEANUP_PLAN.md) Task 7.
- [ ] **Beam lateral/longitudinal position usage** — check whether beam lateral and longitudinal position fields (similar to those used for table position) are used elsewhere in the codebase, and document or fill any gaps.
- [ ] **Vendor coordinate validation** — confirm per-vendor export frames and Philips double-correction risk against
  source RDSRs before expanding vendor adapters. See [VENDOR_COORDINATE_SYSTEMS.md](VENDOR_COORDINATE_SYSTEMS.md).
- [ ] **Patient orientation support (head-first vs feet-first, prone vs supine)** — investigate whether the code and GUI allow choosing patient orientation (head-first / feet-first) and positioning (prone / supine). See [assessment](assessments/PATIENT_ORIENTATION_ASSESSMENT.md).
- [ ] **Add more normalizations and offsets for different models** — extend vendor/model-specific coordinate normalization and table-origin offsets to cover additional scanner models beyond current coverage.


### GUI / UX

- [ ] **GUI clutter cleanup** — simplify the interface and hide lower-priority or advanced info behind warning/info buttons, collapsible cards, or similar patterns; consider other UX ideas for reducing cognitive load.
- [ ] **Better export-failure messaging** — when an export fails due to a missing dependency, show clear user-facing info and actionable warnings (e.g. which package to install and how).
- [ ] **Export audit trail for `table_origin_override`** — record per-exam table-origin overrides in normalized
  export metadata.
- [ ] **Rich export phantom dimensions** — report phantom dimensions (anterior-posterior, left-right, superior-inferior) in cm using max values (thickest parts) rather than a scale factor.
- [ ] **Expanded RDSR browser** — expose more irradiation-event detail after load.
- [ ] **Rich export — manual browser/native save smoke** (Phase 4.3.x) — verify the Export-tab modal in a real
  browser (download filename + toast) and in native pywebview mode (Browse/save-path dialog focused on top).
- [ ] **Rich export — polish (Phase 7 leftovers)** — multi-exam image-cap GUI toggle (7.1); deeper tagged-PDF/DOCX
  accessibility + alt text, HTML already sets `alt` (7.2); extract user-visible strings to a localization module
  (7.3); align the Results tab correction table to include `k_med` as a small separate PR (7.4); add a per-tab
  GUI help page for the Export tab once a help loader exists.
- [ ] **Rich export — minor code deferrals** — set explicit `openpyxl` `cell.number_format` on numeric XLSX cells
  (values are pre-formatted strings today); add browser `showSaveFilePicker()` progressive enhancement (must never
  replace the baseline `ui.download()` fallback). (GUI native "Open file / Open folder" success actions — **done**
  2026-07-02; still needs Windows manual smoke.)
- [ ] **In-app settings/workflow help** — link to `VENDOR_COORDINATE_SYSTEMS.md` and related technical docs.
- [ ] **Visual refinement** — reduce left-nav spacing, soften the brutalist look, tune fonts/light mode/backgrounds
  per [DESIGN.md](../DESIGN.md).
- [ ] **Default example RDSR** — change the Upload tab default away from `fake-scanner`.
- [ ] **Central Help entry point** — add a Help menu/item accessible from the left navigation bar and/or as a dedicated GUI tab, linking to the in-app help files under `gui/help/` and the online docs.
- [ ] **Make offsets more visible and configurable for the user** — surface table-origin and coordinate offsets prominently in the GUI (e.g. per-exam offset summary, inline hints on the Geometry tab) and allow easy override without digging into nested settings.
- [ ] **Reproducible settings export** — export `PyskindoseSettings` or GUI state as JSON to easily reload and reproduce runs.
- [ ] **3D mesh export** — export the patient phantom mesh with vertex colors (e.g., PLY format) for use in external 3D tools.
- [ ] **DICOM export** — export a DICOM Secondary Capture of the dose map or a DICOM SR to push results back to PACS.

### Harness / Repo Hygiene

- [ ] **Adopt the fork-maintenance baseline** — work through the prioritized GitHub governance, attribution,
  privacy, upstream-sync, and release actions in [FORK_MAINTAINER_GUIDE.md](FORK_MAINTAINER_GUIDE.md).
- [ ] **Deferred documentation experience ideas** — after the documentation/help harness lands, evaluate the ideas
  intentionally left out of the implementation plan: screenshot-driven help regression tests, in-app "report
  inaccurate help" feedback, per-run processing-log narratives in exports, generated normalization-flow diagrams,
  and release documentation audit checklist generation. Original brainstorm:
  [DOCUMENTATION_AND_HELP_INFRASTRUCTURE_BRAINSTORM.md](plans/archive/DOCUMENTATION_AND_HELP_INFRASTRUCTURE_BRAINSTORM.md).
- [ ] **Re-check ignored dependency advisories** — quarterly (or before each release), run
  `python scripts/audit_dependencies.py` and review `[tool.uv.audit]` in `pyproject.toml`.
  (2026-07-09: bumped transitive dev-only `nltk` 3.9.4 → 3.10.0 and removed
  `GHSA-p4gq-832x-fm9v` / `PYSEC-2026-597` suppressions.
  2026-07-17: added mcp GHSA-jpw9-pfvf-9f58 / GHSA-hvrp-rf83-w775 / GHSA-vj7q-gjh5-988w
  suppressions while semgrep pins `mcp==1.23.3`; remove when semgrep bumps or relaxes the pin.)
  (2026-07-18: confirmed GitHub Dependabot still opens alerts for these GHSA IDs — alerts #2/#3/#4 on
  `kgrizz-git/MyPySkinDose` — because the `uv.lock`-level `dep_scope` reads as `runtime` to Dependabot and GitHub's
  advisory feed is independent of `[tool.uv.audit]` ignores. CI's `uv audit` is the gate that matters; the Dependabot
  alerts are informational and should stay open until semgrep bumps/relaxes its `mcp==1.23.3` pin
  (patched versions are `mcp >=1.27.2` / `>=1.28.1`). Context: `mcp` is transitive via the optional Semgrep MCP server
  path and is not imported or run by MyPySkinDose runtime code, so the CVEs are not exploitable in this repo.)
- [ ] **Scheduled inter-release grype scan** — add a weekly `grype-scheduled.yml` workflow that builds and scans without publishing, to catch CVEs disclosed between releases. Dependabot already covers Python dep bumps; this would catch supply-chain issues in the built artifact specifically.
- [ ] **Optional supply-chain hardening** — enable GitHub code scanning/security alerts, release SBOM upload, or
  Trufflehog only if needed beyond gitleaks.
- [ ] **Doc-freshness follow-ups** — add intentional stale-word excludes, extend inventory contradiction rules, and
  consider release-only strict stale-pattern checks.
- [ ] **Optional doc-pruning release gate** — run `python scripts/check_doc_pruning.py --strict` before releases
  once the team is comfortable with the advisory workflow.
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

## Research Ideas

- [ ] Call it GUISkinDose?
- [ ] **Safety API key** — get a free Safety API key ([safetycli.com](https://safetycli.com)) and wire it as
  `SAFETY_API_KEY` GitHub secret.

## Open Questions

- **Original flow inputs** — Do examples need JSON sidecars, different normalization settings, or other files to
  avoid unexpected body-region projections?
- **K_IRP column** — Results table shows K_IRP as `-` in some runs. Is this intended to represent correction
  factors rather than kerma?
