# TO DO

Short-term task list for MyPySkinDose. Harness principles, validation commands, plan conventions, and the phased remediation roadmap live in:

- [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md) — includes **Documentation conventions** (master vs execution plans)
- [plans/archive/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](plans/archive/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md)

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
- [ ] **Optional doc-pruning release gate** — once the team is comfortable with the retention policy, run `python scripts/check_doc_pruning.py --strict` before release to require review of active execution plans and assessments older than 30 days and 10 commits.
- [ ] **Architecture follow-ups**
  - Evaluate `import-linter` if layer contracts grow beyond three pytest rules.
  - Refactor `phantom_class` → `plotting` coupling documented in `CODEBASE_OVERVIEW.md`.
- [ ] **GUI test depth** (beyond Phase 5 smoke)
  - Smoke test each main tab route (Upload, Settings, Geometry, etc.).
  - Optional Playwright/CDP tests only if user-simulation proves insufficient.
- [ ] Expand coordinate system diagrams in `VENDOR_COORDINATE_SYSTEMS.md` (initial mermaid diagrams added 2026-06-06; validate against vendor data).

### Documentation / plans (pending)

- [ ] **Audit wiki image deletions — confirm nothing was lost** — commit `e856ccd` (2026-06-24) removed 10 tracked `wiki/*.png` illustrations (`backscatter_*`, `beam_path_through_table_*`, `collimator_shutters_dark`, `distance_scaling_dark`, `human`, `isq_dark`, `mu_en_surface_dark`) when they were untracked via `.gitignore` (`*.png`, with only `docs/**/*.png` exempted). **Verify:** (1) each file still exists somewhere durable — e.g. `docs/source/` (preferred home for Sphinx), an external wiki/readthedocs asset path, or recoverable from git history (`git show e856ccd^:wiki/<file>`); (2) no broken image references in `docs/`, `dev-docs/`, or published help; (3) no other `wiki/` or `docs/` files were dropped in the same cleanup (`tmp/` assessments and `.basedpyright/README.md` were also removed). If the illustrations are still needed, restore from `e856ccd^` into `docs/source/user/figures/` (or another tracked path) and update any links; if obsolete, document that decision and delete local `wiki/` copies to avoid confusion.
- [ ] **Plan template** — shared header for execution plans: objective, acceptance criteria, progress log, decision log (see `plans/archive/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md` §6).
- [x] **Archive completed execution plans** — `refactor-execution.md` and `gui-decomposition-design.md` archived under `dev-docs/plans/archive/` (2026-06-23).
- [ ] **Optional `dev-docs/master-plans/` migration** — defer until a rename PR is worth the link churn; convention documented in `HARNESS_ENGINEERING.md` instead.
- [ ] **Phase 7 harness (Active / High Priority)**:
  - [x] **7.1 Enforce File Size CI Limits**: Implement `scripts/check_file_sizes.py` (fail if any Python source or Markdown file > 800 lines, except whitelist) and add to CI/pre-commit.
  - [x] **7.2 Establish Visible Guidance for Agents**: Update `AGENTS.md` and `HARNESS_ENGINEERING.md` with rules for keeping files under 800 lines, archiving plans, and gitignoring scratch/temp files (unless intended for reuse).
  - [x] **7.3 Local Cleanups and Gitignore Hardening**: Strengthen `.gitignore` for scratch formats and add pre-commit checks for untracked scratch files.
  - [x] **7.4 Doc pruning advisory check**: `scripts/check_doc_pruning.py` reports active execution plans and assessments older than 30 days and 10 commits; wired into pre-commit as advisory.
  - [ ] **Expand `dev-docs/references/` stubs** before next major dependency review.
  - [ ] **Recurring doc-gardening agent automation** (after stale-pattern rules are CI-blocking).
- [ ] **Full GUI observability stack** — defer until smoke/tab tests prove insufficient (`plans/archive/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md` “what not to build yet”).

- [x] **4.3 — `schema_version` on JSON/dict export** — **done** (2026-06-23): `EXPORT_SCHEMA_VERSION` in `format_export_data.py`; `PySkinDoseOutput.to_dict()` and `MultiExamResult.to_dict()` emit top-level `schema_version`. Tests in `test_export_data.py`.
- [x] **4.2 — Shared Plotly layout helper (`plotting/` only)** — **done** (2026-06-23): `plotting/plot_layout.py` (`default_geometry_layout`, `default_procedure_layout`, `default_dosemap_layout`); refactored `create_setup_and_event_plot.py`, `plot_procedure.py`, `create_layout_for_dose_map_plots.py`. Tests in `test_plot_layout.py`.

### Input data & calculation

- [ ] **Explore simplified calculation using only DICOM data** — investigate whether a reasonable dose estimate can be produced without the full phantom-mesh intersection pipeline, by reading key DICOM fields directly (kVp, mA, exposure time, SID, field size, DAP, fluoroscopy time, pulse rate, anode angle, beam rotation angles, etc.) and applying simplified geometry + correction factors. Could serve as a fast pre-scan estimate or a fallback when the mesh pipeline is too heavy or unavailable.
- [ ] Run examples in JupyterLab and compare.
- [x] **HVL-lookup crash on invalid / out-of-grid events** — **done** ([hvl-invalid-event-crash.md](plans/archive/hvl-invalid-event-crash.md)): crash fixed (nearest-grid snap + regression test), fail-soft, and snapped-event count surfaced in the GUI (calculate-tab status line + toast via `state.calc_warnings`). Decided 2026-06-13: invalid sub-floor-kVp events are **not** auto-dropped (interim = leave snapped); their handling moves to the interactive chooser below.
- [x] **User options for below-floor / unresolvable kVp events** — **done** ([hvl-interpolation-and-below-floor-kvp.md](plans/archive/hvl-interpolation-and-below-floor-kvp.md), Phase 2, 2026-06-19): events with **kVp < 25 kV** now honor a user-selectable policy `below_floor_kvp_policy ∈ {snap (default), skip, manual, exam_average}` (+ `below_floor_kvp_manual`), applied per exam in `geom_calc.apply_below_floor_kvp_policy` before the HVL lookup. `snap` keeps the status quo (clamp + flag); `skip` drops the events; `manual` substitutes a fixed kVp; `exam_average` substitutes that exam's mean in-floor kVp (falls back to `snap` + warns if all-below). Settings control under Physics + a pre-calc prompt (`gui/tabs/calculate.py`) that fires only when sub-floor events are detected; affected-count always reported via `state.calc_warnings`. Remaining: manual GUI smoke check (load a sub-floor export, exercise each policy).
- [x] **HVL interpolation/extrapolation for out-of-table filtration** — **done** ([hvl-interpolation-and-below-floor-kvp.md](plans/archive/hvl-interpolation-and-below-floor-kvp.md), Phase 1, 2026-06-19): `geom_calc.fetch_and_append_hvl` now 2-D bilinear-interpolates HVL over `(kVp, Cu)` on the selected `(inherent, Al)` grid slice and **clamps** (never extrapolates) at the table edges; `corrections.calculate_k_tab` similarly guarded (exact-match-first, fail-soft to `k_tab=1.0` for unknown devices, interpolate/clamp otherwise) — fixes the unguarded `c.fetchone()[0]` crash. Anode angle is selected (discrete tube property), not interpolated; kVp rounded to its dense 1-kV node so in-grid results/golden PSD are unchanged. Per-event `interpolated`/`clamped`/`no-device` warnings surface via `state.calc_warnings`. Shared helper `grid_interp.py`. `k_med` left nearest-tabulated (cannot crash; <1% field-size dependence). Subsumes the earlier nearest-snap from [hvl-invalid-event-crash.md](plans/archive/hvl-invalid-event-crash.md).
- [ ] **Anode-angle awareness in the HVL lookup** (future, accuracy not robustness) — the HVL table (`hvl_combined.csv`) carries two anode angles (8°/11°), but the runtime lookup in `geom_calc.fetch_and_append_hvl` **never reads the device's anode angle**; it keys only on `(kVp, inherent, Cu, Al)` and resolves the duplicate anode rows by first-occurrence (effectively 11°/Philips where present, else 8°/Siemens) regardless of the actual tube. Consequences: (a) a device whose anode angle isn't tabulated silently gets 8°/11°-derived HVL — no crash/warning, since anode angle isn't a lookup key; (b) a Siemens (8°) device can receive 11° HVL for beam qualities present in both slices (a pre-existing quirk preserved for parity). To make HVL anode-aware: extend the table via `table_data/generate_hvl_data.py` (already parameterizes `anode_angle_deg` through spekpy, so adding angles is cheap); derive the device's anode angle from a **per-device-model map** (it is not a standard RDSR event field, so don't expect to read it per-event); add anode angle as a real lookup dimension; and for an untabulated angle do **nearest-angle selection + warning** (selection, not interpolation — it's a discrete tube-target property), reusing the clamp-and-warn pattern from `grid_interp.py`. Context: [hvl-interpolation-and-below-floor-kvp.md](plans/archive/hvl-interpolation-and-below-floor-kvp.md) (Decisions → anode angle).
- [ ] Add debug/warning if any dose events have no intersection with patient.
- [ ] **More patient sizes / phantom body-habitus scaling** — the bundled human meshes (`phantom_data/*.stl`: adult/junior/senior male/female, hudfrid) cover a narrow size range with no obese/large-habitus option. Two complementary approaches: (a) **generate or source additional meshes** for under-represented body types (e.g. obese), keeping the existing full-res + `_reduced_1000t` pairing and wiring them into `get_human_mesh_names()`; and/or (b) **directional scaling of the current phantoms** — let the user stretch a mesh along lateral / AP / longitudinal axes (e.g. anthropometric sliders or a BMI/girth control) by scaling the STL vertices in `phantom_class.py` before dose mapping. Body size changes skin-to-source distance and beam intersection, so this materially affects PSD; surface it as a control in the Settings → Phantom section. Validate scaled geometry in the Geometry tab.
- [x] Add support for multiple exams — core data model, CLI multi-file, GUI Phases 1–2.5 complete ([plan archived](plans/archive/multiple-exams.md)).
- [x] **Convert the per-event recursion to a loop (RecursionError on long/multi-exam data)** (2026-06-16) — `calculate_irradiation_event_result` now iterates with `for ev in range(event, total_events)`; golden baseline + 1100-event stress tests in `test_calculate_dose.py`. [Plan](plans/archive/recursion-to-iteration.md).
- [ ] **Review rotational-acquisition handling** — confirm how rotational/spin acquisitions (rotational angiography, DSA spins, cone-beam CT runs) are modelled. Each is a single RDSR event but sweeps the gantry across a range of primary/secondary angles during the run, so treating it as one static `Ap1`/`Ap2` likely smears or mis-places the dose. Investigate whether per-frame angles (start/end + number of frames/pulses) are available and whether the dose should be distributed across the swept angles rather than deposited at one position. Affects PSD localization for cardiac/neuro spins.
- [ ] **Biplane (tube A / tube B) support and recognition** — current normalization collapses to a single plane (the Radimetrics adapter intentionally maps only the total/`kvp kv`, and per-plane `(A)`/`(B)` columns — `kVp (A/B)`, `DAP (A/B)`, `Reference Point Dose (A/B)`, `Fluoro time (A/B)` — are dropped). Biplane systems irradiate from two tubes with independent geometry and dose; detect biplane exports/RDSR (presence of A/B columns or two acquisition planes), model each plane's geometry and dose separately, and combine for total PSD. Touches the RDSR parser/normalizer, the adapters' plane handling (`AcquisitionPlane`), `geom_calc`, and the dose-map accumulation.
- [ ] **Tabular input Phase 5+** — Qaelum, DoseMonitor, DoseWatch adapters per [TABULAR_RDSR_INPUT_PLAN.md](plans/TABULAR_RDSR_INPUT_PLAN.md) (gated on real vendor export fixtures; stub adapters exist).
- [ ] **Column-pattern customization** (future, after Python-only implementation is stable): allow site-specific column name overrides via an editable JSON or YAML file so users with non-standard export templates can map columns without code changes. See `plans/TABULAR_RDSR_INPUT_PLAN.md` open questions.
- [ ] **Vendor coordinate normalization — lat/lon axis swap**: Confirmed for **GE equipment** (a hardware convention, not export-format specific; see `_should_swap_by_default` in `dev-docs/references/psdcalcrework_io_utils.py`). The GUI auto-enables the swap when GE is detected via `state.manufacturer` (RDSR loads) or import warnings (tabular loads). **Philips is NOT confirmed:** the bundled Philips RDSRs (`example_data/RDSR/philips_allura_clarity_*.dcm`) normalize correctly through `rdsr_normalizer()` with no swap, so `dhen2714/PySkinDose` `parse_philips()`'s swap is likely DoseTrack-export-specific and remains unverified — left as a manual toggle until a real Philips DoseTrack export can be compared against source. The `normalization_settings.json` offset/direction mechanism cannot fix an axis swap. See `VENDOR_COORDINATE_SYSTEMS.md` for details.
- [ ] **Vendor coordinate normalization — confirm per-vendor export frame** (Phase 5+ prerequisite): before writing Qaelum/DoseMonitor/DoseWatch adapters, compare a real export against its source RDSR to confirm whether values are in the raw DICOM frame (→ call `rdsr_normalizer()`) or pre-transformed (→ skip or adjust). See `VENDOR_COORDINATE_SYSTEMS.md` tabular input section and `plans/TABULAR_RDSR_INPUT_PLAN.md` open questions for risk table and details.
- [ ] **Vendor coordinate normalization — Philips double-correction risk**: Philips has large Y/Z offsets (~105 cm Y, ~173 cm Z). If a Philips export has already applied these offsets, calling `rdsr_normalizer()` doubles them. Confirm Radimetrics/DoseTrack Philips exports are in raw DICOM frame before writing Phase 5+ adapters.

### GUI / UX

- [ ] **Multi-exam manual smoke check** — run a multi-exam workflow end-to-end in the GUI: multi-file upload, per-exam overrides (coordinate transforms, patient offsets, convention flips), calculate, and verify results accordion. Verifies GUI Phases 2.1–2.5 before declaring multi-exam fully stable. See [archived plan](plans/archive/multiple-exams.md).
- [x] **Per-exam advanced table offsets and corrections → Settings tab** (2026-06-19) — per-exam offsets, coordinate corrections, and table-origin overrides moved from the Upload tab into a **Settings → Per-exam corrections** section (`gui/tabs/_per_exam.py`); each exam edited separately. Upload keeps a compact loaded-files summary. ([plan](plans/archive/multi-exam-data-table-and-settings.md)).
- [ ] **Geometry tab — per-exam event selection and stepping** — in multi-exam mode the Geometry tab should let the user pick which exam's events to display, selecting events from each exam clearly and separately. Also support "step through all" across exams. **Memory concern:** when many events are loaded, rendering all events simultaneously could strain memory/plot performance — consider lazy loading, event-range selection (e.g. show events 1–100 from exam A, then 1–50 from exam B), or a virtualised slider. Evaluate Plotly trace count limits and profile with large multi-exam datasets.
- [ ] **Dose map — per-exam checkbox controls** — allow the user to show the dose map for the cumulative/total dose across all exams, or toggle individual exams on/off to view subsets (e.g. only exam 1, or exams 1+3). Surface as checkboxes next to each exam name in the Geometry or a dedicated dose-display section. When exams are toggled, the dose map and PSD should update live to reflect the selected subset. Tie into multi-exam work ([plan](plans/archive/multiple-exams.md)).
- [ ] Show more irradiation-event detail after load, or add an expanded RDSR browser (table lateral position, table height, collimated field area, etc.).
- [x] **Data Table tab — exam-number column** (2026-06-19) — in multi-exam mode the data table now tags each row with a display-only `Exam` column (`"#<n> · <file>"`), pinned first. Centralized in `gui/helpers.rebuild_rdsr_df()`; single-exam frames stay untagged and the tag is dropped before the calculation. ([plan](plans/archive/multi-exam-data-table-and-settings.md)).
- [ ] Add sliders for patient offset parameters with real-time geometry preview in the Geometry tab.
  - Expose `max_events_for_patient_inclusion` as a control.
  - Consider presets (cardiac, head/neck, abdominal, etc.).
- [x] **Confirm the uploader-wedge fix and resolve** — **done** (confirmed 2026-06-13): dragging a file *out of the native file-open dialog* onto the drop zone wedged quasar in a phantom upload (`0.0B/0.00%`, `+` disabled); `uploader.reset()` did **not** recover it, so the "Reset upload" button / card X now **rebuild** the uploader element (commit `37019e1`). Manually verified the **Reset upload** button recovers a wedged uploader and the `+` works again.
- [ ] Fix download/export HTML button (verify other export paths).
- [ ] **Rich report exports (XLSX / DOCX / PDF)** — beyond the current JSON/HTML/PNG (export tab) and CSV/XLSX/TXT event dumps (data tab), add report-style exports that bundle: one or two **dose-plot images at different views/angles** (reuse `make_dosemap_png`, rendered from a couple of camera angles), **key input factors** (total air kerma, DAP, fluoro time, number of cine/rotational acquisitions, protocol/exam name, perhaps average SID, kVp range), and **key results** (PSD, perhaps average correction factors k_isq/k_bs/k_tab). XLSX via a summary sheet + embedded image; DOCX via python-docx; PDF via a headless render or reportlab. Keep the provenance embedding (`io_helpers._tabular_input_meta`) so reports record how the source was read. New optional deps — gate behind the `[gui]`/a `[report]` extra and license-check them.
- [ ] Add in-app help for settings and workflow; link to `VENDOR_COORDINATE_SYSTEMS.md` and related technical docs.
- [x] **Complete Phase 6 of `plans/POSITIONING_HELP_PLAN.md`** — **done** (2026-06-24): `docs/source/gui_help/` is now the single source of truth; `scripts/sync_gui_help.py` mirrors to `src/mypyskindose/gui/help/` (enforced by pre-commit + CI). `positioning_offsets.md` merged (Overview + 6-step workflow + Tips from GUI; Coordinate System, Troubleshooting, Getting More Help from docs; 4-row Quick Reference with MyST footnote). `geometry_workflow.md` and `below_floor_kvp.md` relocated unchanged. Plans archived.
- [ ] Allow manual interactive setting of table offsets in GUI.
- [ ] Collect typical offsets per system/model/table type for user reference.
- [ ] Settings tab: show Table Offsets (vendor-specific, read-only initially) and Patient Offsets (user-adjustable).
- [ ] Reduce spacing/padding in navigation section of left pane.
- [ ] Soften brutalist look; refine sleek/modern aesthetic per [DESIGN.md](../DESIGN.md).
- [x] Refactor `app.py` — **done** (2026-06-23); see [refactor-execution.md](plans/archive/refactor-execution.md) Phase 3 (`app.py` 245 lines, per-tab modules).
- [ ] Change fonts; add light mode; tune background color effects.
- [ ] Make native window larger on launch.
- [ ] Change default example RDSR in Upload tab (not `fake-scanner`).

### Backlog / research

- [ ] Call it GUISkinDose?

---

## Deferred

Items intentionally postponed — low ROI or high churn unless a concrete pain point appears. Full context in [plans/archive/refactor-execution.md](plans/archive/refactor-execution.md) Phase 4.

### Refactor Phase 4 — deferred

- [ ] **4.1 — Split `constants.py`** — `src/mypyskindose/constants.py` is ~270 lines (well under the 800-line CI limit) and mixes plot colors, DICOM tag keys, phantom dimension keys, physics floors (`HVL_KVP_FLOOR`), and output key strings. **Defer until** the file grows hard to navigate or you are already adding a large new constant block. **If undertaken:** split into `physics_constants.py` + `lookup_tables.py` (or `dicom_keys.py` + `plot_constants.py` — decide split axes first); add thin re-exports from `constants.py` for one release to avoid a mass import churn; grep the repo for `from mypyskindose.constants import` and migrate incrementally; run full `pytest` + `basedpyright`.

- [ ] **4.4 — Narrow broad `except Exception`** — ~17 `except Exception` sites repo-wide; many are appropriate at I/O boundaries (`gui/io_helpers._get_save_path`, upload temp-file cleanup, `tabular_loader` encoding fallbacks). **Do not** repo-wide sweep. **Cherry-pick when:** a broad catch masked a real bug, or you are editing the function anyway. **Keep broad catches at:** user-facing boundaries (GUI notify + fallback download), `atexit`/cleanup, and optional native dialog paths. **Prefer specific types in:** adapter transform internals, geometry math, and parser normalization — e.g. `ValueError`, `KeyError`, `pd.errors.ParserError`, `sqlite3.Error`. Add a test per narrowed site where feasible.

---

## Open questions

Unresolved investigations — not scheduled work until answered.

- **Original flow inputs** — Do examples need JSON sidecars (`beam_collimation`, `beam_rotations`, etc.), different normalization settings, or other repo files? Some example RDSRs project dose onto unexpected body regions; is an offset (setting or RDSR) missing?
- **K_IRP column** — Results table shows K_IRP as `-` in some runs. Are these meant to be correction factors rather than kerma (as they may have been originally)?

---

## Completed

Finished items kept for traceability. Harness phase tags reference [HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](plans/archive/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md).

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
- [x] **Unify split dependency declarations + license-notices baseline** (2026-06-19) — `pyproject.toml` extras are now the single source of truth: added `[docs]` (Sphinx/nbsphinx/pandoc, used by `.readthedocs.yml` `extra_requirements: [docs]`) and `[notebooks]` (JupyterLab) extras, fixed the `dev` extra to be a true superset of the CI toolchain (added `pytest`, `ruff`), and **deleted** the legacy `requirements.txt` / `requirements-dev.txt` / `docs/requirements.txt`. `scripts/check_licenses.py` now inventories the full declared extra set (`SELECTED_EXTRAS = dev,gui,gui-native,docs,notebooks`) and the notices are regenerated from `uv sync --all-extras` (pinned by `uv.lock`), so `THIRD_PARTY_NOTICES.md` is reproducible regardless of which extras a venv installed. `license-notices` pre-commit hook now also triggers on `uv.lock`.
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
