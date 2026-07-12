# Documentation index

_Date: 2026-07-02_

Catalog of every file under `dev-docs/`. Start from [AGENTS.md](../AGENTS.md) for agent orientation, then [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md) for validation commands and the source-of-truth map.

---

## Harness

| File | Purpose |
|---|---|
| [AGENT_PLAYBOOK.md](AGENT_PLAYBOOK.md) | Shared workflow guidance for coding agents; tool-specific pointer files should refer here instead of duplicating rules. |
| [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md) | Repository harness principles, golden rules, **documentation conventions** (master vs execution plans), validation commands, CI expectations, doc-gardening cadence, and known gaps. |
| [LICENSE_COMPLIANCE.md](LICENSE_COMPLIANCE.md) | Third-party license policy, `scripts/check_licenses.py`, and `THIRD_PARTY_NOTICES.md` workflow. |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | **Canonical location** — generated license inventory (not repo root). |
| [../scripts/check_licenses.py](../scripts/check_licenses.py) | CI/local license audit: forbidden copyleft gate and notices inventory generator. |
| [../scripts/check_doc_freshness.py](../scripts/check_doc_freshness.py) | CI/local doc-freshness checker: broken links, stale path references, inventory contradictions (AGENTS + CHANGELOG), advisory stale-pattern scan. |
| [../scripts/check_help_registry.py](../scripts/check_help_registry.py) | Validates `dev-docs/help_registry.json`, source GUI help pages, mirrored bundled help files, GUI `HelpButton` references, and orphaned help files. |
| [../scripts/check_ui_copy.py](../scripts/check_ui_copy.py) | Validates `dev-docs/ui_copy.json` and `dev-docs/glossary.json`; checks `copy_text()` usage and terminology warnings. |
| [../scripts/check_feature_doc_matrix.py](../scripts/check_feature_doc_matrix.py) | Validates feature-to-code/test/doc/help traceability in `dev-docs/feature_doc_matrix.json`; can emit advisory doc-impact warnings from changed paths. |
| [../scripts/check_agent_guidance.py](../scripts/check_agent_guidance.py) | Advisory drift checker for agent pointer files, `TO_DO.md` size/history, and completed-looking active plans. |
| [../scripts/check_doc_pruning.py](../scripts/check_doc_pruning.py) | Advisory pruning review: reports old active execution plans and assessments after 30 days and 10 commits. |
| [../scripts/sync_gui_help.py](../scripts/sync_gui_help.py) | Mirrors `docs/source/gui_help/*.md` -> `src/mypyskindose/gui/help/*.md`; enforced by pre-commit + CI (`ci.yml` `static-analysis` job). |
| [../scripts/generate_ui_values.py](../scripts/generate_ui_values.py) | Regenerates `UI_values.md` from `MODERN_CSS` in `gui/styles.py`. |
| Bandit | `[tool.bandit]` in `pyproject.toml`; CI `bandit` job and pre-commit hook (medium+ severity on `src/mypyskindose` + `scripts`). |
| [TO_DO.md](TO_DO.md) | Short active backlog, deferred work, and open questions. Completed history lives in `CHANGELOG.md` and archived plans. |
| [index.md](index.md) | This catalog — one-line purpose for every file under `dev-docs/`. |
| [help_registry.json](help_registry.json) | Machine-readable map of GUI help ids to source markdown files, bundled mirror files, and GUI tabs/workflows. |
| [ui_copy.json](ui_copy.json) | Catalog of high-risk GUI tooltip/help/warning strings used through `copy_text()`. |
| [glossary.json](glossary.json) | Canonical glossary terms and aliases used by UI copy and help terminology checks. |
| [feature_doc_matrix.json](feature_doc_matrix.json) | Feature-to-code/test/doc/help traceability matrix for doc-impact review. |
| GUI smoke tests | `tests/gui/` (requires `pip install -e '.[gui]'`); see `tests/scripts/launch_gui_headless.py` |
| [references/](references/README.md) | Links to pydicom, NiceGUI, Plotly, and other dependency docs. |

---

## Architecture

| File | Purpose |
|---|---|
| [CODEBASE_OVERVIEW.md](CODEBASE_OVERVIEW.md) | Full architecture, data flow, **package layering rules**, settings, classes, functions, and repository layout. |
| [FEATURE_INVENTORY.md](FEATURE_INVENTORY.md) | Feature status ledger: calculations, rendering, settings, outputs, CLI, API, and **harness/CI §0**. |
| [MYPYSKINDOSE_MIGRATION_STATUS.md](MYPYSKINDOSE_MIGRATION_STATUS.md) | Fork vs upstream PySkinDose migration status and PyPI namespace rename progress. |

---

## Master plans (`dev-docs/plans/`)

Long-lived topic source-of-truth plans. Convention: [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md) § Documentation conventions.

| File | Purpose |
|---|---|
| [plans/GUI_PLAN.md](plans/GUI_PLAN.md) | **Source of truth** — current UI state (§0) and NiceGUI implementation plan. |
| [plans/RICH_EXPORT_PLAN.md](plans/RICH_EXPORT_PLAN.md) | **Source of truth** — rich report export scope, payload architecture, writer phases, GUI/browser/native save UX, and CLI rollout. |
| [plans/TABULAR_RDSR_INPUT_PLAN.md](plans/TABULAR_RDSR_INPUT_PLAN.md) | Staged plan for CSV/TSV/XLSX exported event-table inputs (Radimetrics, DoseTrack, etc.). Phases 1–5 shipped; Phase 5+ vendor stubs documented in-plan. |

---

## GUI

| File | Purpose |
|---|---|
| [plans/GUI_PLAN.md](plans/GUI_PLAN.md) | See **Master plans** above. |
| [UI_values.md](UI_values.md) | Auto-generated GUI design tokens from `MODERN_CSS` in `src/mypyskindose/gui/styles.py` (`scripts/generate_ui_values.py`). |
| [../DESIGN.md](../DESIGN.md) | Root GUI aesthetic spec (brutalist/modern design intent). |

---

## Input data

| File | Purpose |
|---|---|
| [INPUT_DATA_FLOW_AND_OFFSETS.md](INPUT_DATA_FLOW_AND_OFFSETS.md) | RDSR and JSON input flow, normalization settings, patient offsets, and internal DataFrame contract. |
| [INPUT_SCHEMA_DETECTION.md](INPUT_SCHEMA_DETECTION.md) | Tabular schema auto-detection (default `auto`, recall scoring, per-schema fingerprints) and the DAP-unit / manufacturer caveat. Machine-checked by `tests/unittests/test_input_schema_doc.py`. |
| [VENDOR_COORDINATE_SYSTEMS.md](VENDOR_COORDINATE_SYSTEMS.md) | Vendor-specific coordinate conventions, normalization mapping, and Mermaid coordinate-system diagrams. |
| [references/ge_coordinate_validation.md](references/ge_coordinate_validation.md) | GE coordinate convention record: confirmed table-travel directions, normalization-level `Tx`/`Tz` correction, and deferred matched DICOM/export fixture notes. |
| [plans/TABULAR_RDSR_INPUT_PLAN.md](plans/TABULAR_RDSR_INPUT_PLAN.md) | See **Master plans** above. |
| [COORD_TRANSFORM_COMPARISON.md](COORD_TRANSFORM_COMPARISON.md) | Side-by-side comparison of coordinate transforms and preprocessing across MyPySkinDose, dhen2714/PySkinDose, and PSDCalcReworkTemp. |

---

## Assessments (`assessments/`)

Diagnostics and assessments of code quality, refactoring, bug checks, or security.

| File | Purpose |
|---|---|
| [assessments/REFACTOR_ASSESSMENT.md](assessments/REFACTOR_ASSESSMENT.md) | Point-in-time diagnostic: largest files/functions, modularity/robustness/security findings. Execution plan archived in [plans/archive/refactor-execution.md](plans/archive/refactor-execution.md). |
| [assessments/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN_ASSESSMENT_20260624T162147.md](assessments/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN_ASSESSMENT_20260624T162147.md) | Round 7 gap review: Parts I–III verified shipped; IV-a critical path; Part V spec gaps; appendix T-item corrections. |
| [assessments/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN_ASSESSMENT_20260624T203736.md](assessments/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN_ASSESSMENT_20260624T203736.md) | Round 8 gap review: Parts I–IV verified shipped; Part V underspecs (formatters, N4 `refresh_per_exam` gap, C6 placement, docs list); 20-item execution order. |
| [assessments/NATIVE_WINDOW_GEOMETRY_PLAN_ASSESSMENT_20260625.md](assessments/NATIVE_WINDOW_GEOMETRY_PLAN_ASSESSMENT_20260625.md) | Round 1 API review: shutdown timing, multi-monitor validation; NiceGUI proxy/event APIs confirmed. |
| [assessments/GEO_TAB_SPINNING_WHEEL_20260625.md](assessments/GEO_TAB_SPINNING_WHEEL_20260625.md) | Geometry tab render-cycle root cause; review of the original fix (regression in 7 external `ctx.refresh_per_exam()` callers); revised fix uses an `_in_render_chain` flag. |
| [assessments/NATIVE_WINDOW_GEOMETRY_PLAN_ASSESSMENT_20260625T010005.md](assessments/NATIVE_WINDOW_GEOMETRY_PLAN_ASSESSMENT_20260625T010005.md) | Round 2 gap review: restore-from-maximize, title-bar validation, maximized event filtering, debounce lifecycle, CI-safe tests, `Path.replace`. |
| [assessments/YZ_AXIS_INCONSISTENCY_ASSESSMENT.md](assessments/YZ_AXIS_INCONSISTENCY_ASSESSMENT.md) | Audit of coordinate naming contradictions: physical geometry, DICOM attribute names, and historical PySkinDose plot aliases differ; current recommendation is documentation/comment cleanup plus fixture-backed validation before behavior changes. |
| [assessments/OWASP_SECURITY_TOOLS_ASSESSMENT.md](assessments/OWASP_SECURITY_TOOLS_ASSESSMENT.md) | OWASP Top 10 coverage audit of current SAST/dependency scanning; recommendations for semgrep, safety, gitleaks. |

---

## Execution plans (`plans/`)

Phased detail derived from diagnostics or master plans.

| File | Purpose |
|---|---|
| [plans/INTERACTIVE_TABLE_OFFSETS_PLAN.md](plans/INTERACTIVE_TABLE_OFFSETS_PLAN.md) | Single-exam Geometry offset sliders, Settings table-offset display, load-reset fixes (Phases 0–2b). |
| [plans/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md](plans/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md) | Multi-exam exam selector + Geometry sliders bound to `loaded_exam_meta[active]`; preview semantics. |
| [plans/gui-aesthetic-redesign.md](plans/gui-aesthetic-redesign.md) | Transition GUI from Aurora-Brutalist to Sleek Modern/Material aesthetic. |
| [plans/NATIVE_WINDOW_GEOMETRY_PLAN.md](plans/NATIVE_WINDOW_GEOMETRY_PLAN.md) | Native window geometry persistence: restore last size/position/maximized state on `--native` launch; first run maximized. |
| [plans/SECURITY_TOOLS_CI_PLAN.md](plans/SECURITY_TOOLS_CI_PLAN.md) | Phased plan to wire semgrep and safety into CI/pre-push; gitleaks already done. |
| [plans/DEPENDENCY_AUDIT_PLAN.md](plans/DEPENDENCY_AUDIT_PLAN.md) | Update pre-push hooks and CI to audit project lockfile (uv audit) with fallback to active environment (pip-audit). |
| [plans/GRYPE_RELEASE_SCAN_PLAN.md](plans/GRYPE_RELEASE_SCAN_PLAN.md) | Add grype artifact scanning to the release workflow; policy via `.grype.yaml`; artifact upload. |
| [plans/GEOMETRY_PER_EXAM_EVENT_SELECTION_PLAN.md](plans/GEOMETRY_PER_EXAM_EVENT_SELECTION_PLAN.md) | Geometry tab event-stepper UX (chevron prev/next + context caption) on the existing per-exam preview-slice foundation; trace-count guard documentation. |

## Archived plans (`plans/archive/`)

| File | Purpose |
|---|---|
| [plans/archive/DOSE_MAP_PER_EXAM_CHECKBOX_PLAN.md](plans/archive/DOSE_MAP_PER_EXAM_CHECKBOX_PLAN.md) | **Completed** — Multi-exam Results: inline per-exam dose map checkboxes + aggregate subset selector with live PSD recompute. |
| [plans/archive/README.md](plans/archive/README.md) | Index of completed or superseded execution plans. |
| [plans/archive/RICH_EXPORT_SPEC.md](plans/archive/RICH_EXPORT_SPEC.md) | **Superseded** — original Rich Report Export draft spec; folded into the master `plans/RICH_EXPORT_PLAN.md`. |
| [plans/archive/DOCUMENTATION_AND_HELP_INFRASTRUCTURE_BRAINSTORM.md](plans/archive/DOCUMENTATION_AND_HELP_INFRASTRUCTURE_BRAINSTORM.md) | **Superseded** — brainstorming and high-level ideas folded into [plans/archive/DOCUMENTATION_HELP_HARNESS_IMPLEMENTATION_PLAN.md](plans/archive/DOCUMENTATION_HELP_HARNESS_IMPLEMENTATION_PLAN.md) plus deferred `TO_DO.md` items. |
| [plans/archive/DOCUMENTATION_HELP_HARNESS_IMPLEMENTATION_PLAN.md](plans/archive/DOCUMENTATION_HELP_HARNESS_IMPLEMENTATION_PLAN.md) | **Completed** (2026-07-04) — documentation/help harness checks: stale paths, GUI help registry, UI copy catalog, glossary, feature-doc matrix, hooks, and CI. |
| [plans/archive/basedpyright-fix-plan.md](plans/archive/basedpyright-fix-plan.md) | **Completed** — strict basedpyright rollout (147 errors → 0). |
| [plans/archive/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](plans/archive/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md) | **Completed** — Phased roadmap to align the repository to agent-first harness standards (Phases 0–5 complete, Phase 6 closed, Phase 7 implemented/stubs tracked). |
| [plans/archive/recursion-to-iteration.md](plans/archive/recursion-to-iteration.md) | **Completed** — Replace per-event tail recursion with a loop; unblocks multi-exam + long procedures. |
| [plans/archive/hvl-invalid-event-crash.md](plans/archive/hvl-invalid-event-crash.md) | **Completed** — Fix HVL-lookup crash on out-of-grid kVp events; nearest-grid snap + GUI warning. |
| [plans/archive/multiple-exams.md](plans/archive/multiple-exams.md) | **Completed** — Multi-exam support: core, CLI, GUI Phases 1–2.5. GUI smoke check pending. |
| [plans/archive/multi-exam-data-table-and-settings.md](plans/archive/multi-exam-data-table-and-settings.md) | **Completed** — Data Table `Exam` tag column; per-exam corrections moved to the Settings tab. |
| [plans/archive/hvl-interpolation-and-below-floor-kvp.md](plans/archive/hvl-interpolation-and-below-floor-kvp.md) | **Completed** — HVL/`k_tab` interpolation + clamping with per-event flags; below-floor kVp policy (snap/skip/manual/exam-average) with Settings control + pre-calc prompt. |
| [plans/archive/refactor-execution.md](plans/archive/refactor-execution.md) | **Completed** — Phased refactor (Phases 0–3): logging, busy guard, adapter consolidation, GUI decomposition (`app.py` 1275→245 lines). |
| [plans/archive/gui-decomposition-design.md](plans/archive/gui-decomposition-design.md) | **Completed** — Wiring map and extraction design for GUI Phase 3 split. |
| [plans/archive/positioning-help.md](plans/archive/positioning-help.md) | **Completed** — In-app help for phantom positioning; integrated with main docs as single source of truth. |
| [plans/archive/phase-6-doc-integration.md](plans/archive/phase-6-doc-integration.md) | **Completed** — Sync mechanism for `docs/source/gui_help/` -> `src/mypyskindose/gui/help/` with pre-commit + CI enforcement. |
| [plans/archive/NO_PATIENT_INTERSECTION_WARNING_PLAN.md](plans/archive/NO_PATIENT_INTERSECTION_WARNING_PLAN.md) | **Completed** (2026-06-24) — Beam-miss warnings: per-event WARNING + all-miss sentinel + `beam_miss_warn` dial + GUI toast throttle + handler leak fix. |
| [plans/archive/PATIENT_SIZE_SCALING_PLAN.md](plans/archive/PATIENT_SIZE_SCALING_PLAN.md) | **Completed** (2026-06-25) — Human STL body-habitus scaling with `scale_lat`/`scale_ap`/`scale_lon`, recomputed normals, Settings sliders, and geometry/dose plumbing. |
| [plans/archive/GEO_TAB_SPINNING_WHEEL_PLAN.md](plans/archive/GEO_TAB_SPINNING_WHEEL_PLAN.md) | **Completed** (2026-06-25) — Geometry tab render loop: `_in_render_chain` flag, slider `.mark(...)` markers, parametrized regression tests (patient lon/ver/lat + table-origin X). |
| [plans/archive/FIRST_RUN_ONBOARDING_PLAN.md](plans/archive/FIRST_RUN_ONBOARDING_PLAN.md) | **Completed** (2026-06-25) — First-run GUI onboarding modal with local `gui.json` dismissal preference. |
| [plans/archive/GEOMETRY_TABLE_ORIGIN_SLIDER_VALUES_PLAN.md](plans/archive/GEOMETRY_TABLE_ORIGIN_SLIDER_VALUES_PLAN.md) | **Completed** (2026-06-25) — Geometry table-origin slider value labels mirror patient-offset labels. |
| [plans/archive/CROSS_TAB_SLIDER_SYNC_PLAN.md](plans/archive/CROSS_TAB_SLIDER_SYNC_PLAN.md) | **Completed** (2026-06-25) — Settings edits refresh Geometry sliders, labels, and preview on tab entry. |
| [plans/archive/BODY_HABITUS_CM_DISPLAY_PLAN.md](plans/archive/BODY_HABITUS_CM_DISPLAY_PLAN.md) | **Completed** (2026-06-26) — Body-habitus scaling sliders display scaled mesh dimensions in cm. |
| [plans/archive/SLIDER_LABEL_REPOSITION_PLAN.md](plans/archive/SLIDER_LABEL_REPOSITION_PLAN.md) | **Completed** (2026-06-26) — Geometry tab slider value labels repositioned adjacent to sliders (per-axis `ui.row` replacing outer column layout). |
| [plans/archive/ENABLE_SECURITY_HOOKS_DEFAULT_PLAN.md](plans/archive/ENABLE_SECURITY_HOOKS_DEFAULT_PLAN.md) | **Completed** (2026-06-27) — `setup-dev.sh`/`.bat` one-command hook installer; `pip-audit` added as pre-push hook; CI shellcheck expanded; `AGENTS.md` and `HARNESS_ENGINEERING.md` updated. |
| [plans/archive/VENDOR_XZ_CLARIFICATION_PLAN.md](plans/archive/VENDOR_XZ_CLARIFICATION_PLAN.md) | **Completed** (2026-06-28) — Vendor-invariant Geometry/Per-exam table-origin controls, explicit `X/LON/PT L-R` labels, plot annotations, Calculate/Geometry help, and vendor warnings. |
| [plans/archive/COORDINATE_CONVENTIONS_CLEANUP_PLAN.md](plans/archive/COORDINATE_CONVENTIONS_CLEANUP_PLAN.md) | **Completed** (2026-06-28) — Canonical coordinate reference in `VENDOR_COORDINATE_SYSTEMS.md`; DICOM attribute/display-alias distinction; GE convention confirmed; characterization tests; agent + GUI help updated. GE matched-fixture item tracked in TO_DO. |
| [plans/archive/MAC_NATIVE_WINDOW_MAXIMIZE_PLAN.md](plans/archive/MAC_NATIVE_WINDOW_MAXIMIZE_PLAN.md) | **Completed** (2026-07-03) — macOS native startup now normalizes saved `maximized=true` into a safe visible-desktop titled window, persists `maximized=false`, and keeps Windows/Linux maximize behavior unchanged. |

---

## Misc (`info/`)

| File | Purpose |
|---|---|
| [info/PACKAGE_INSTALL.md](info/PACKAGE_INSTALL.md) | Why and how to install MyPySkinDose as an editable package (`pip install -e .`). |
