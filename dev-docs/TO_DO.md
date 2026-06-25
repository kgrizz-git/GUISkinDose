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
- [ ] **Vendor coordinate validation** — confirm per-vendor export frames and Philips double-correction risk against
  source RDSRs before expanding vendor adapters. Plan: [VENDOR_XZ_CLARIFICATION_PLAN.md](plans/VENDOR_XZ_CLARIFICATION_PLAN.md) (Phase 2).

### GUI / UX

- [ ] **Clarify vendor-specific X/Z on Geometry plot** — either convert display axes to one semantic frame or add
  a clear in-app note and axis legend. Plan: [VENDOR_XZ_CLARIFICATION_PLAN.md](plans/VENDOR_XZ_CLARIFICATION_PLAN.md).
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

### Harness / Repo Hygiene

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
- [x] GUI help single source of truth — archived in
  [phase-6-doc-integration.md](plans/archive/phase-6-doc-integration.md).
- [x] GUI decomposition — archived in [refactor-execution.md](plans/archive/refactor-execution.md).
- [x] Tabular input Phases 1-5 — source plan:
  [TABULAR_RDSR_INPUT_PLAN.md](plans/TABULAR_RDSR_INPUT_PLAN.md).
- [x] Geometry plot spinning wheel / continuous reload — archived in
  [GEO_TAB_SPINNING_WHEEL_PLAN.md](plans/archive/GEO_TAB_SPINNING_WHEEL_PLAN.md).
- [x] Show Geometry table-origin slider values — source plan:
  [GEOMETRY_TABLE_ORIGIN_SLIDER_VALUES_PLAN.md](plans/archive/GEOMETRY_TABLE_ORIGIN_SLIDER_VALUES_PLAN.md).
- [x] Cross-tab offset/origin slider synchronization — source plan:
  [CROSS_TAB_SLIDER_SYNC_PLAN.md](plans/archive/CROSS_TAB_SLIDER_SYNC_PLAN.md).
