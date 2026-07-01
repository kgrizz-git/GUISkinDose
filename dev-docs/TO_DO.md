# TO DO

Short active backlog for MyPySkinDose. Keep this file focused on actionable work and open questions; use
`CHANGELOG.md`, archived plans, and `dev-docs/index.md` for historical traceability.

For harness rules, validation commands, and plan conventions, see [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md).

---

## Now / Next

- [ ] **Check documentation completeness and accuracy** — verify `CODEBASE_OVERVIEW.md`, `FEATURE_INVENTORY.md`,
  `AGENTS.md`, and `HARNESS_ENGINEERING.md` against current code behavior.
- [ ] **Multi-exam manual smoke check** — exercise multi-file upload, per-exam overrides, calculate, and results
  accordion in the GUI.
- [ ] **Geometry tab per-exam event selection** — let users select or step through events per exam; account for
  Plotly trace count and large datasets.
- [ ] **Dose map per-exam checkbox controls** — show cumulative dose or selected exam subsets and update PSD/dose
  map live.
- [ ] **Fix download/export HTML button** — verify related export paths while touching this area.

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
- [ ] **Tabular input Phase 5+** — implement Qaelum, DoseMonitor, and DoseWatch adapters when real export fixtures
  are available; see [TABULAR_RDSR_INPUT_PLAN.md](plans/TABULAR_RDSR_INPUT_PLAN.md).
- [ ] **Column-pattern customization** — support site-specific column-name overrides after Python-only adapter
  behavior is stable.
- [ ] **GE coordinate fixture confirmation** — obtain one matched GE DICOM RDSR + tabular export from the same
  case to pin exact regression values. GE table-travel direction (positive lateral = patient left, longitudinal =
  cranial, height = down for HFS) and the normalizer-level `Tx`/`Tz` correction are already confirmed; this item
  is for pinning raw numeric fixture values only. See [references/ge_coordinate_validation.md](references/ge_coordinate_validation.md)
  and [plans/archive/COORDINATE_CONVENTIONS_CLEANUP_PLAN.md](plans/archive/COORDINATE_CONVENTIONS_CLEANUP_PLAN.md) Task 7.
- [ ] **Vendor coordinate validation** — confirm per-vendor export frames and Philips double-correction risk against
  source RDSRs before expanding vendor adapters. See [VENDOR_COORDINATE_SYSTEMS.md](VENDOR_COORDINATE_SYSTEMS.md).
- [ ] **Patient orientation support (head-first vs feet-first, prone vs supine)** — investigate whether the code and GUI allow choosing patient orientation (head-first / feet-first) and positioning (prone / supine). See [assessment](assessments/PATIENT_ORIENTATION_ASSESSMENT.md).
- [ ] **Add more normalizations and offsets for different models** — extend vendor/model-specific coordinate normalization and table-origin offsets to cover additional scanner models beyond current coverage.


### GUI / UX

- [ ] **Export audit trail for `table_origin_override`** — record per-exam table-origin overrides in normalized
  export metadata.
- [ ] **Expanded RDSR browser** — expose more irradiation-event detail after load.
- [ ] **Rich report exports** — add report-style XLSX/DOCX/PDF outputs with dose images, key inputs, key results,
  and provenance.
- [ ] **In-app settings/workflow help** — link to `VENDOR_COORDINATE_SYSTEMS.md` and related technical docs.
- [ ] **Visual refinement** — reduce left-nav spacing, soften the brutalist look, tune fonts/light mode/backgrounds
  per [DESIGN.md](../DESIGN.md).
- [ ] **Default example RDSR** — change the Upload tab default away from `fake-scanner`.
- [ ] **Central Help entry point** — add a Help menu/item accessible from the left navigation bar and/or as a dedicated GUI tab, linking to the in-app help files under `gui/help/` and the online docs.
- [ ] **Make offsets more visible and configurable for the user** — surface table-origin and coordinate offsets prominently in the GUI (e.g. per-exam offset summary, inline hints on the Geometry tab) and allow easy override without digging into nested settings.
- [ ] **Verify body habitus scaling correctness** — ensure scaling is applied only in the appropriate dimensions,
  visible on the geometry/dose plot, and factored into dose calculations.
- [ ] **Reproducible settings export** — export `PyskindoseSettings` or GUI state as JSON to easily reload and reproduce runs.
- [ ] **3D mesh export** — export the patient phantom mesh with vertex colors (e.g., PLY format) for use in external 3D tools.
- [ ] **DICOM export** — export a DICOM Secondary Capture of the dose map or a DICOM SR to push results back to PACS.

### Harness / Repo Hygiene

- [ ] **Re-check ignored dependency advisories** — quarterly (or before each release), run
  `python scripts/audit_dependencies.py` and review `[tool.uv.audit]` in `pyproject.toml`.
  Drop `GHSA-p4gq-832x-fm9v` once `nltk` ships a fix (currently dev-only via `safety`, no
  in-project use of `nltk.data.load()`). `ignore-until-fixed` should auto-fail the audit again
  when a patched `nltk` release appears in the lockfile.
- [ ] **Optional SBOM scan** — evaluate grype on built wheel/sdist if PyPI advisories are not enough.
- [ ] **Optional supply-chain hardening** — enable GitHub code scanning/security alerts, release SBOM upload, or
  Trufflehog only if needed beyond gitleaks.
- [ ] **Doc-freshness follow-ups** — add intentional stale-word excludes, extend inventory contradiction rules, and
  consider release-only strict stale-pattern checks.
- [ ] **Detect stale paths in backtick code spans and prose** — `scripts/check_doc_freshness.py` only inspects
  `\[text\]\(url\)` markdown links; backtick-wrapped paths (e.g. CHANGELOG entries like
  `` Plan: `dev-docs/plans/.../FOO.md` ``) and bare path mentions in prose are missed. Extend the
  checker (or add a sibling scan) to flag stale relative paths in any of these forms so that
  plan-archive moves don't leave dangling references. See `scripts/check_doc_freshness.py:31`
  (`MARKDOWN_LINK_RE`) and the 2026-06-25 Spinning-Wheel archive incident for the trigger case.
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
- [ ] **OWASP principles**
  - [x] Investigate and research OWASP Top 10 and relevant security principles for the project
  - [x] Assess security-analysis tools — see [OWASP_SECURITY_TOOLS_ASSESSMENT.md](assessments/OWASP_SECURITY_TOOLS_ASSESSMENT.md)
  - [x] Implement recommended tools in CI per [SECURITY_TOOLS_CI_PLAN.md](plans/SECURITY_TOOLS_CI_PLAN.md) (semgrep + conditional safety; gitleaks already wired)
    - [ ] Get free Safety API key ([safetycli.com](https://safetycli.com)) and wire it as `SAFETY_API_KEY` GitHub secret

## Open Questions

- **Original flow inputs** — Do examples need JSON sidecars, different normalization settings, or other files to
  avoid unexpected body-region projections?
- **K_IRP column** — Results table shows K_IRP as `-` in some runs. Is this intended to represent correction
  factors rather than kerma?

## Recently Completed

- [x] First-run onboarding popup — archived in
  [FIRST_RUN_ONBOARDING_PLAN.md](plans/archive/FIRST_RUN_ONBOARDING_PLAN.md).
- [x] Human phantom body-habitus scaling — archived in
  [PATIENT_SIZE_SCALING_PLAN.md](plans/archive/PATIENT_SIZE_SCALING_PLAN.md).
- [x] Beam-miss warnings — archived in
  [NO_PATIENT_INTERSECTION_WARNING_PLAN.md](plans/archive/NO_PATIENT_INTERSECTION_WARNING_PLAN.md).
- [x] Geometry plot spinning wheel / continuous reload — archived in
  [GEO_TAB_SPINNING_WHEEL_PLAN.md](plans/archive/GEO_TAB_SPINNING_WHEEL_PLAN.md).
- [x] Show Geometry table-origin slider values — source plan:
  [GEOMETRY_TABLE_ORIGIN_SLIDER_VALUES_PLAN.md](plans/archive/GEOMETRY_TABLE_ORIGIN_SLIDER_VALUES_PLAN.md).
- [x] Cross-tab offset/origin slider synchronization — source plan:
  [CROSS_TAB_SLIDER_SYNC_PLAN.md](plans/archive/CROSS_TAB_SLIDER_SYNC_PLAN.md).
