# TO DO

Short-term task list for MyPySkinDose. Harness principles, validation commands, plan conventions, and the phased remediation roadmap live in:

- [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md) — includes **Documentation conventions** (master vs execution plans)
- [HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md)

---

## Implementation tasks

Actionable work items only. Completed harness phases (0–5) and other finished items are in [Completed](#completed) below.

### Harness / CI (pending)

- [ ] **Optional SBOM scan (grype)** — scan built wheel/sdist from `package-build` job if broader coverage is needed beyond PyPI advisories.
- [ ] **Optional supply-chain hardening** (lower priority):
  - GitHub **code scanning** / Dependabot security alerts enabled in repo settings.
  - SBOM artifact upload on release (syft/grype) if distributing wheels publicly.
  - Trufflehog (redundant if gitleaks is sufficient).
- [ ] **Doc-freshness follow-ups**
  - Add exclude list for harness docs that intentionally mention stale-pattern words.
  - Extend `FEATURE_INVENTORY.md` contradiction rules beyond tabular input.
  - Make stale-pattern warnings CI-blocking before each release (see doc-gardening cadence in `HARNESS_ENGINEERING.md`).
- [ ] **Architecture follow-ups**
  - Evaluate `import-linter` if layer contracts grow beyond three pytest rules.
  - Refactor `phantom_class` → `plotting` coupling documented in `CODEBASE_OVERVIEW.md`.
- [ ] **GUI test depth** (beyond Phase 5 smoke)
  - Smoke test each main tab route (Upload, Settings, Geometry, etc.).
  - Optional Playwright/CDP tests only if user-simulation proves insufficient.
- [ ] Expand coordinate system diagrams in `VENDOR_COORDINATE_SYSTEMS.md` (initial mermaid diagrams added 2026-06-06; validate against vendor data).

### Documentation / plans (pending)

- [ ] **Plan template** — shared header for execution plans: objective, acceptance criteria, progress log, decision log (see `HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md` §6).
- [ ] **Archive completed execution plans** — when `refactor-execution.md` / `gui-decomposition-design.md` phases finish, move or mark complete under `dev-docs/plans/archive/`.
- [ ] **Optional `dev-docs/master-plans/` migration** — defer until a rename PR is worth the link churn; convention documented in `HARNESS_ENGINEERING.md` instead.
- [ ] **Phase 7 harness** (low priority, from improvement plan):
  - Expand `dev-docs/references/` before next major dependency review.
  - Recurring doc-gardening agent automation (after stale-pattern rules are CI-blocking).
  - Per-golden-rule custom linters (start with doc-freshness + import contracts only).
- [ ] **Full GUI observability stack** — defer until smoke/tab tests prove insufficient (`HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md` “what not to build yet”).

### Input data & calculation

- [ ] Run examples in JupyterLab and compare.
- [ ] **HVL interpolation/extrapolation for out-of-table filtration** — `geom_calc.fetch_and_append_hvl` selects each event's HVL with an **exact match** on added Cu filtration (and rounded Al), kVp, and inherent filtration against `table_data/hvl_tables/hvl_combined.csv`. If an export's filter value isn't a tabulated point, the lookup returns empty and `.iloc[0]` raises, failing the whole calculation. Replace exact match with nearest-neighbour or (bi)linear interpolation across the tabulated grid, with extrapolation guarded at the table edges. **Surface a user-facing warning/notification** whenever a value is interpolated or (especially) extrapolated — push it through the same import/calc warnings channel the GUI already shows (e.g. `state.normalization_warnings` / calc status), naming the event and the substituted HVL so the user knows the beam quality wasn't an exact table hit. Note filter thickness materially affects PSD: HVL drives backscatter `k_bs`, medium `k_med`, and (with Cu/Al directly) table transmission `k_tab` corrections.
- [ ] Add debug/warning if any dose events have no intersection with patient.
- [ ] Add support for multiple exams.
- [ ] **Tabular input Phase 5+** — Qaelum, DoseMonitor, DoseWatch adapters per [TABULAR_RDSR_INPUT_PLAN.md](TABULAR_RDSR_INPUT_PLAN.md) (gated on real vendor export fixtures; stub adapters exist).
- [ ] **Column-pattern customization** (future, after Python-only implementation is stable): allow site-specific column name overrides via an editable JSON or YAML file so users with non-standard export templates can map columns without code changes. See `TABULAR_RDSR_INPUT_PLAN.md` open questions.
- [ ] **Vendor coordinate normalization — lat/lon axis swap**: Confirmed for **GE equipment** (a hardware convention, not export-format specific; see `_should_swap_by_default` in `dev-docs/references/psdcalcrework_io_utils.py`). The GUI auto-enables the swap when GE is detected via `state.manufacturer` (RDSR loads) or import warnings (tabular loads). **Philips is NOT confirmed:** the bundled Philips RDSRs (`example_data/RDSR/philips_allura_clarity_*.dcm`) normalize correctly through `rdsr_normalizer()` with no swap, so `dhen2714/PySkinDose` `parse_philips()`'s swap is likely DoseTrack-export-specific and remains unverified — left as a manual toggle until a real Philips DoseTrack export can be compared against source. The `normalization_settings.json` offset/direction mechanism cannot fix an axis swap. See `VENDOR_COORDINATE_SYSTEMS.md` for details.
- [ ] **Vendor coordinate normalization — confirm per-vendor export frame** (Phase 5+ prerequisite): before writing Qaelum/DoseMonitor/DoseWatch adapters, compare a real export against its source RDSR to confirm whether values are in the raw DICOM frame (→ call `rdsr_normalizer()`) or pre-transformed (→ skip or adjust). See `VENDOR_COORDINATE_SYSTEMS.md` tabular input section and `TABULAR_RDSR_INPUT_PLAN.md` open questions for risk table and details.
- [ ] **Vendor coordinate normalization — Philips double-correction risk**: Philips has large Y/Z offsets (~105 cm Y, ~173 cm Z). If a Philips export has already applied these offsets, calling `rdsr_normalizer()` doubles them. Confirm Radimetrics/DoseTrack Philips exports are in raw DICOM frame before writing Phase 5+ adapters.

### GUI / UX

- [ ] Show more irradiation-event detail after load, or add an expanded RDSR browser (table lateral position, table height, collimated field area, etc.).
- [ ] Add sliders for patient offset parameters with real-time geometry preview in the Geometry tab.
  - Expose `max_events_for_patient_inclusion` as a control.
  - Consider presets (cardiac, head/neck, abdominal, etc.).
- [ ] Fix download/export HTML button (verify other export paths).
- [ ] Add in-app help for settings and workflow; link to `VENDOR_COORDINATE_SYSTEMS.md` and related technical docs.
- [ ] Complete Phase 6 of `POSITIONING_HELP_PLAN.md` — integrate positioning help with main documentation.
- [ ] Allow manual interactive setting of table offsets in GUI.
- [ ] Collect typical offsets per system/model/table type for user reference.
- [ ] Settings tab: show Table Offsets (vendor-specific, read-only initially) and Patient Offsets (user-adjustable).
- [ ] Reduce spacing/padding in navigation section of left pane.
- [ ] Soften brutalist look; refine sleek/modern aesthetic per [DESIGN.md](../DESIGN.md).
- [ ] Refactor `app.py`.
- [ ] Change fonts; add light mode; tune background color effects.
- [ ] Make native window larger on launch.
- [ ] Change default example RDSR in Upload tab (not `fake-scanner`).

### Backlog / research

- [ ] Call it GUISkinDose?

---

## Open questions

Unresolved investigations — not scheduled work until answered.

- **Original flow inputs** — Do examples need JSON sidecars (`beam_collimation`, `beam_rotations`, etc.), different normalization settings, or other repo files? Some example RDSRs project dose onto unexpected body regions; is an offset (setting or RDSR) missing?
- **K_IRP column** — Results table shows K_IRP as `-` in some runs. Are these meant to be correction factors rather than kerma (as they may have been originally)?

---

## Completed

Finished items kept for traceability. Harness phase tags reference [HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md).

### Harness Phases 0–5

- [x] Doc-freshness / link check — **Phase 1** — `python scripts/check_doc_freshness.py`
- [x] Semver and CI full-check parity — **Phases 2–3** — `CHANGELOG.md`, `compileall`, `package-build`, Actions v4/v5
- [x] Package layering rules + structural tests — **Phase 4** — `CODEBASE_OVERVIEW.md`, `test_architecture_layers.py`
- [x] GUI smoke tests — **Phase 5** — `tests/gui/`, `gui-smoke` CI job, `tests/scripts/launch_gui_headless.py`
- [x] Harness doc catalog — **Phase 0** — `dev-docs/index.md`, expanded source-of-truth map, `DESIGN.md` rename
- [x] **Documentation conventions** — master vs execution vs archive plans documented in `HARNESS_ENGINEERING.md`; `plans/archive/` for completed work (2026-06-12)

### CI, typing, and supply chain

- [x] **Basedpyright** — CI `typecheck` job (strict); optional baseline via `scripts/type_baseline.sh`. Plan archived at `dev-docs/plans/archive/basedpyright-fix-plan.md`.
- [x] **Gitleaks** — `.github/workflows/gitleaks.yml` on push/PR.
- [x] **pip-audit** — CI `dependency-audit` job (core + `[dev]` + `[gui]`).
- [x] **License compliance** — `scripts/check_licenses.py`; inventory at `dev-docs/THIRD_PARTY_NOTICES.md`.
- [x] **Dependabot** — weekly pip + GitHub Actions (`.github/dependabot.yml`).
- [x] **pre-commit** — ruff, gitleaks, doc-freshness on commit; basedpyright on pre-push.
- [x] **Repository hygiene** — untrack `dist/`, notebook checkpoints, `phantom_data/old/`, `.windsurf/`, local `debug.json`; expand `.gitignore` (2026-06-12).

### Docs and GUI milestones

- [x] TO_DO.md cleanup — separate open questions from implementation tasks.
- [x] RDSR data table shows **normalized** data (parsed, scaled, mm→cm, coordinate alignment) — not raw DICOM tags.
- [x] Redesign GUI per `DESIGN.md`.
- [x] Geometry tab at position 3.
- [x] Native window appears on top at launch.

### Tabular input (Phases 1–5)

- [x] **Phase 1** (2026-06-09): normalized schema adapter, shared loader/mapper/registry infrastructure, CLI flags, fixtures, unit tests.
- [x] **Phase 2** (2026-06-09): `generic_rdsr_like` adapter (column map → `rdsr_normalizer()`), `--input-schema auto` detection.
- [x] **Phase 3** (2026-06-10): Radimetrics adapter, unit conversions, synthetic fixture, GUI schema selector.
- [x] **Phase 4** (2026-06-10): DoseTrack adapter, manufacturer inference, Philips lat/lon swap warning, synthetic fixture.
- [x] **Phase 5** (2026-06-10): GUI tabular upload (`.csv`/`.tsv`/`.xlsx`), import preview, coordinate correction toggles, intelligent defaults, XLSX sheet picker.
