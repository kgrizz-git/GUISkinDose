# Documentation index

_Date: 2026-07-16_

Catalog of every file under `dev-docs/`. Start from [AGENTS.md](../AGENTS.md) for agent orientation, then [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md) for validation commands and the source-of-truth map.

---

## Harness

| File | Purpose |
|---|---|
| [AGENT_PLAYBOOK.md](AGENT_PLAYBOOK.md) | Shared workflow guidance for coding agents; tool-specific pointer files should refer here instead of duplicating rules. |
| [FORK_MAINTAINER_GUIDE.md](FORK_MAINTAINER_GUIDE.md) | Practical upstream-attribution, GitHub governance, privacy, release, and worktree guidance for maintaining this PySkinDose fork. |
| [RELEASES_AND_DISTRIBUTION.md](RELEASES_AND_DISTRIBUTION.md) | **Hub** — distribution channels, changelog vs GitHub Release notes, SemVer, release checklist; links PyPI and deferred portable executables. |
| [../PUBLISHING.md](../PUBLISHING.md) | PyPI Trusted Publishing detail (`release.yml`); inert until a GitHub Release is created. |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Contributor setup, PR workflow, privacy rules, and pointers to agent playbooks. |
| [../SUPPORT.md](../SUPPORT.md) | Support channels, intended-use boundary, and no-PHI rules. |
| [../SECURITY.md](../SECURITY.md) | Private vulnerability reporting and supported-version policy. |
| [../GOVERNANCE.md](../GOVERNANCE.md) | Solo-maintainer decisions and release ownership. |
| [../CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | Contributor Covenant 2.1 community standards. |
| [../CITATION.cff](../CITATION.cff) | Machine-readable citation; credits upstream PySkinDose. |
| [GUISKINDOSE_MIGRATION_STATUS.md](GUISKINDOSE_MIGRATION_STATUS.md) | Historical namespace rename notes; corrected for extras/`uv.lock` packaging. |
| [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md) | Repository harness principles, golden rules, **documentation conventions** (master vs execution plans), validation commands, CI expectations, doc-gardening cadence, and known gaps. |
| [LICENSE_COMPLIANCE.md](LICENSE_COMPLIANCE.md) | Third-party license policy, `scripts/check_licenses.py`, and `THIRD_PARTY_NOTICES.md` workflow. |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | **Canonical location** — generated license inventory (not repo root). |
| [../scripts/check_licenses.py](../scripts/check_licenses.py) | CI/local license audit: forbidden copyleft gate and notices inventory generator. |
| [../scripts/check_doc_freshness.py](../scripts/check_doc_freshness.py) | CI/local doc-freshness checker: broken links, stale path references, inventory contradictions (AGENTS + CHANGELOG), advisory stale-pattern scan. |
| [../scripts/check_sensitive_content.py](../scripts/check_sensitive_content.py) | CI/local PII/absolute-path scanner and hash-pinned sensitive-asset admission gate (policy/CLI). |
| [../scripts/check_sensitive_helpers.py](../scripts/check_sensitive_helpers.py) | Notebook/PDF/container reader helpers for the sensitive-content gate. |
| [../scripts/git_identity_trailers.py](../scripts/git_identity_trailers.py) | Allowlisted Dependabot / GitHub noreply identity trailers for commit-message privacy scans. |
| [privacy_admission_policy.json](privacy_admission_policy.json) | Machine-enforced protected-ignore, never-track, conditional scanner, receipt-expiry, and scanner-configuration policy. |
| [../scripts/privacy_admission.py](../scripts/privacy_admission.py) | Staged/range privacy router, protected-path gate, scanner runner, and content-bound private receipt verifier. |
| [../scripts/check_commit_message.py](../scripts/check_commit_message.py) | Local `commit-msg` gate for value-free sensitive-content checks before the message enters history. |
| [../scripts/render_asset_inventory.py](../scripts/render_asset_inventory.py) | Generates/checks the linked Markdown view of the machine-enforced sensitive-asset inventory. |
| [approved_asset_inventory.md](approved_asset_inventory.md) | Generated reviewer-friendly linked view of all approved/pending sensitive assets; must match the JSON source. |
| [privacy_tool_inventory.json](privacy_tool_inventory.json) | Machine-readable versions, roles, execution boundaries, and output policies for direct privacy tools and runtimes. |
| [privacy_tool_inventory.md](privacy_tool_inventory.md) | Generated reviewer-friendly privacy-tool inventory; active scanner references are checked in hooks and CI. |
| [../scripts/render_privacy_tool_inventory.py](../scripts/render_privacy_tool_inventory.py) | Validates scanner-to-tool coverage and generates the privacy-tool inventory Markdown. |
| [../scripts/run_presidio_advisory.py](../scripts/run_presidio_advisory.py) | Optional local Presidio text scan; advisory only and safe to log. |
| [PRIVACY_AND_SENSITIVE_ASSETS.md](PRIVACY_AND_SENSITIVE_ASSETS.md) | Public-repository privacy policy, DICOM/image review requirements, approved-asset inventory, and scanner use. |
| [PRIVACY_INCIDENT_RESPONSE.md](PRIVACY_INCIDENT_RESPONSE.md) | Private evidence, historical audit, containment, rewrite/notification, verification, and privacy release checklist runbook. |
| [references/LOCAL_PII_MODELS.md](references/LOCAL_PII_MODELS.md) | Local advisory PII/PHI model comparison, macOS/LM Studio boundaries, and synthetic-fixture evaluation protocol. |
| [references/PORTABLE_EXECUTABLE_PACKAGING.md](references/PORTABLE_EXECUTABLE_PACKAGING.md) | Research note: NiceGUI/`nicegui-pack` portable GUI executables; Java-wrap non-goals; deferred spike criteria. |
| [SONARQUBE_LOCAL.md](SONARQUBE_LOCAL.md) | Optional loopback-only SonarQube Community Build runner, private result tracking, and local quality-gate workflow. |
| [../scripts/check_help_registry.py](../scripts/check_help_registry.py) | Validates `dev-docs/help_registry.json`, source GUI help pages, mirrored bundled help files, GUI `HelpButton` references, and orphaned help files. |
| [../scripts/check_ui_copy.py](../scripts/check_ui_copy.py) | Validates `dev-docs/ui_copy.json` and `dev-docs/glossary.json`; checks `copy_text()` usage and terminology warnings. |
| [../scripts/check_feature_doc_matrix.py](../scripts/check_feature_doc_matrix.py) | Validates feature-to-code/test/doc/help traceability in `dev-docs/feature_doc_matrix.json`; can emit advisory doc-impact warnings from changed paths. |
| [../scripts/check_agent_guidance.py](../scripts/check_agent_guidance.py) | Advisory drift checker for agent pointer files, `TO_DO.md` size/history, and completed-looking active plans. |
| [../scripts/check_doc_pruning.py](../scripts/check_doc_pruning.py) | Advisory pruning review: reports old active execution plans and assessments after 30 days and 10 commits. |
| [../scripts/check_docstring_inventory.py](../scripts/check_docstring_inventory.py) | Advisory inventory: reports public symbols under `src/` missing docstrings (stdlib AST, never imports the package). |
| [../scripts/sync_gui_help.py](../scripts/sync_gui_help.py) | Mirrors `docs/source/gui_help/*.md` -> `src/guiskindose/gui/help/*.md`; enforced by pre-commit + CI (`ci.yml` `static-analysis` job). |
| [../scripts/generate_ui_values.py](../scripts/generate_ui_values.py) | Regenerates `UI_values.md` from `MODERN_CSS` in `gui/styles.py`. |
| Bandit | `[tool.bandit]` in `pyproject.toml`; CI `bandit` job and pre-commit hook (medium+ severity on `src/guiskindose` + `scripts`). |
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
| [GUISKINDOSE_MIGRATION_STATUS.md](GUISKINDOSE_MIGRATION_STATUS.md) | Fork vs upstream PySkinDose migration status and PyPI namespace rename progress. |
| [ADDITIONAL_PHANTOMS.md](ADDITIONAL_PHANTOMS.md) | Shipped human-mesh inventory, preferred MPFB generation path, external phantom sources, fun/stylized/historical summary, and STL integration checklist (normals, frame, triangle budget, license/privacy). |
| [references/CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md](references/CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md) | Free/open-license candidate meshes for stylized characters, parametric humans, and public-domain classical/historical figures (license tiers for shipping). |
| [references/fun_phantom_provenance.md](references/fun_phantom_provenance.md) | Source, license, retrieval date, locked ingest transform, repair notes, and validate/smoke results for shipped **demo / non-clinical** phantoms; also blocked candidates (Petite Herculanaise, Louvre Cults/STW NC batch). |

---

## Master plans (`dev-docs/plans/`)

Long-lived topic source-of-truth plans. Convention: [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md) § Documentation conventions.

| File | Purpose |
|---|---|
| [plans/GUI_PLAN.md](plans/GUI_PLAN.md) | **Source of truth** — current UI state (§0) and NiceGUI implementation plan. |
| [plans/PRIVACY_HARDENING_PLAN.md](plans/PRIVACY_HARDENING_PLAN.md) | **Source of truth** — phased runtime, export, test, asset, scanner, GUI-network, history-audit, and release privacy hardening plan. |
| [plans/GUISKINDOSE_PRIVACY_REPUBLICATION_PLAN.md](plans/GUISKINDOSE_PRIVACY_REPUBLICATION_PLAN.md) | **Follow-on source of truth** — sanitize public fixtures, enforce conditional OCR/Presidio/DICOM checks, publish GUISkinDose, and retain the GitHub fork history. First `guiskindose` version is **`1.0.0`**. Mechanical rename: [plans/archive/GUISKINDOSE_RENAME_PLAN.md](plans/archive/GUISKINDOSE_RENAME_PLAN.md) (**complete**, PR #73). GitHub/Sonar/URLs: [plans/archive/GUISKINDOSE_GITHUB_RENAME_PLAN.md](plans/archive/GUISKINDOSE_GITHUB_RENAME_PLAN.md) (**complete**, 2026-09-04). |
| [plans/RICH_EXPORT_PLAN.md](plans/RICH_EXPORT_PLAN.md) | **Source of truth** — rich report export scope, payload architecture, writer phases, GUI/browser/native save UX, and CLI rollout. |
| [plans/TABULAR_RDSR_INPUT_PLAN.md](plans/TABULAR_RDSR_INPUT_PLAN.md) | Staged plan for CSV/TSV/XLSX exported event-table inputs (Radimetrics, DoseTrack, etc.). Phases 1–5 shipped; Phase 5+ vendor stubs documented in-plan. |

---

## GUI

| File | Purpose |
|---|---|
| [plans/GUI_PLAN.md](plans/GUI_PLAN.md) | See **Master plans** above. |
| [UI_values.md](UI_values.md) | Auto-generated GUI design tokens from `MODERN_CSS` in `src/guiskindose/gui/styles.py` (`scripts/generate_ui_values.py`). |
| [../DESIGN.md](../DESIGN.md) | Root GUI aesthetic spec (brutalist/modern design intent). |

---

## Input data

| File | Purpose |
|---|---|
| [INPUT_DATA_FLOW_AND_OFFSETS.md](INPUT_DATA_FLOW_AND_OFFSETS.md) | RDSR and JSON input flow, normalization settings, patient offsets, and internal DataFrame contract. |
| [INPUT_FIELD_REFERENCE.md](INPUT_FIELD_REFERENCE.md) | Standalone cheat sheet: required normalized columns, optional identity fields, and where each input schema maps from. |
| [INPUT_SCHEMA_DETECTION.md](INPUT_SCHEMA_DETECTION.md) | Tabular schema auto-detection (default `auto`, recall scoring, per-schema fingerprints) and the DAP-unit / manufacturer caveat. Machine-checked by `tests/unittests/test_input_schema_doc.py`. |
| [VENDOR_COORDINATE_SYSTEMS.md](VENDOR_COORDINATE_SYSTEMS.md) | Vendor-specific coordinate conventions, normalization mapping, and Mermaid coordinate-system diagrams. |
| [references/ge_coordinate_validation.md](references/ge_coordinate_validation.md) | GE coordinate convention record: confirmed table-travel directions, normalization-level `Tx`/`Tz` correction, and deferred matched DICOM/export fixture notes. |
| [plans/TABULAR_RDSR_INPUT_PLAN.md](plans/TABULAR_RDSR_INPUT_PLAN.md) | See **Master plans** above. |
| [COORD_TRANSFORM_COMPARISON.md](COORD_TRANSFORM_COMPARISON.md) | Side-by-side comparison of coordinate transforms and preprocessing across GUISkinDose, dhen2714/PySkinDose, and PSDCalcReworkTemp. |

---

## Assessments (`assessments/`)

Diagnostics and assessments of code quality, refactoring, bug checks, or security.

| File | Purpose |
|---|---|
| [assessments/MPFB_HEADLESS_SPIKE_2026-07-21.md](assessments/MPFB_HEADLESS_SPIKE_2026-07-21.md) | **PASS** — Phase 0 headless MPFB/Blender phantom spike: adult/pediatric/heavy meshes + anti-balloon shape gates. |
| [assessments/P0_PHANTOM_GENERATION_2026-07-21.md](assessments/P0_PHANTOM_GENERATION_2026-07-21.md) | **PASS** — Phase 2 P0 catalog meshes (pediatric + ectomorph/endomorph) with ordering and shape gates. |
| [assessments/PEDIATRIC_5Y_MALE_ORIENTATION_FIX_2026-07-22.md](assessments/PEDIATRIC_5Y_MALE_ORIENTATION_FIX_2026-07-22.md) | Drifted shipped pediatric 5y male reinstalled face-up; clinical `face_up_ok` gate in `run_catalog`. |
| [assessments/PEDIATRIC_PHANTOM_STATURE_REVIEW_2026-07-23.md](assessments/PEDIATRIC_PHANTOM_STATURE_REVIEW_2026-07-23.md) | Stature review + option-2 relabel (preschool / 5y / new ~138 cm 10y). |
| [assessments/ARMS_DOWN_SPIKE_PED_5Y_MALE_2026-07-23.md](assessments/ARMS_DOWN_SPIKE_PED_5Y_MALE_2026-07-23.md) | Arms-down spike metrics vs A-pose `ped_5y_male` (waist wx 68→22 cm). |
| [assessments/BARIATRIC_THICK_EXTREMITIES_2026-07-22.md](assessments/BARIATRIC_THICK_EXTREMITIES_2026-07-22.md) | Class-II thick-extremities variants; abdomen-vs-affine skipped for limb-bulk rows. |
| [assessments/BARIATRIC_EXTRA_THICK_EXTREMITIES_2026-07-23.md](assessments/BARIATRIC_EXTRA_THICK_EXTREMITIES_2026-07-23.md) | Class-II extra-thick neck/extremities variants (additive; base + thick unchanged). |
| [assessments/P1_BARIATRIC_PHANTOM_GENERATION_2026-07-21.md](assessments/P1_BARIATRIC_PHANTOM_GENERATION_2026-07-21.md) | **PASS** — Phase 3 class-II bariatric male/female meshes; abdomen anti-balloon gates. |
| [assessments/REFACTOR_ASSESSMENT.md](assessments/REFACTOR_ASSESSMENT.md) | Point-in-time diagnostic: largest files/functions, modularity/robustness/security findings. Execution plan archived in [plans/archive/refactor-execution.md](plans/archive/refactor-execution.md). |
| [assessments/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN_ASSESSMENT_20260624T162147.md](assessments/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN_ASSESSMENT_20260624T162147.md) | **Historical** — Round 7 mid-plan review (Parts I–III verified; IV/V then open). Plan since completed and archived. |
| [assessments/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN_ASSESSMENT_20260624T203736.md](assessments/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN_ASSESSMENT_20260624T203736.md) | **Historical** — Round 8 mid-plan review (Parts I–IV verified; Part V then open). Plan since completed and archived. |
| [assessments/NATIVE_WINDOW_GEOMETRY_PLAN_ASSESSMENT_20260625.md](assessments/NATIVE_WINDOW_GEOMETRY_PLAN_ASSESSMENT_20260625.md) | Round 1 API review: shutdown timing, multi-monitor validation; NiceGUI proxy/event APIs confirmed. |
| [assessments/GEO_TAB_SPINNING_WHEEL_20260625.md](assessments/GEO_TAB_SPINNING_WHEEL_20260625.md) | Geometry tab render-cycle root cause; review of the original fix (regression in 7 external `ctx.refresh_per_exam()` callers); revised fix uses an `_in_render_chain` flag. |
| [assessments/NATIVE_WINDOW_GEOMETRY_PLAN_ASSESSMENT_20260625T010005.md](assessments/NATIVE_WINDOW_GEOMETRY_PLAN_ASSESSMENT_20260625T010005.md) | Round 2 gap review: restore-from-maximize, title-bar validation, maximized event filtering, debounce lifecycle, CI-safe tests, `Path.replace`. |
| [assessments/YZ_AXIS_INCONSISTENCY_ASSESSMENT.md](assessments/YZ_AXIS_INCONSISTENCY_ASSESSMENT.md) | Audit of coordinate naming contradictions: physical geometry, DICOM attribute names, and historical PySkinDose plot aliases differ; current recommendation is documentation/comment cleanup plus fixture-backed validation before behavior changes. |
| [assessments/OWASP_SECURITY_TOOLS_ASSESSMENT.md](assessments/OWASP_SECURITY_TOOLS_ASSESSMENT.md) | OWASP Top 10 coverage audit of current SAST/dependency scanning; recommendations for semgrep, safety, gitleaks. |
| [assessments/APPSEC_MEDIUM_FINDINGS_2026-08-03.md](assessments/APPSEC_MEDIUM_FINDINGS_2026-08-03.md) | Remediation note for three medium findings: export header formula injection, `human_mesh` path traversal, XLSX zip-bomb budgets. |
| [assessments/privacy-admission-enforcement/hardening.md](assessments/privacy-admission-enforcement/hardening.md) | Design review of protected ignore/never-track rules and conditional scanner enforcement; recommends staged-content-bound local receipts plus independent CI. |
| [assessments/HTML_EXPORT_BACKGROUND_TASK_ERROR_20260719T123241.md](assessments/HTML_EXPORT_BACKGROUND_TASK_ERROR_20260719T123241.md) | HTML export fake “background task cancelled” error; Results aggregate can render while export fails. Fix plan: [plans/HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md](plans/HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md). |
| [assessments/DOCUMENTATION_TOOLING_EVALUATION_2026-09-06.md](assessments/DOCUMENTATION_TOOLING_EVALUATION_2026-09-06.md) | Dual-agent spike: Mintlify free-tier/OSS terms, end-user docs tooling survey, ranked shortlist; single-sourced claims verified against primary sources 2026-09-06. Linked from `TO_DO.md`. |

---

## Execution plans (`plans/`)

Phased detail derived from diagnostics or master plans.

| File | Purpose |
|---|---|
| [plans/SETTINGS_PHANTOM_PREVIEW_PLAN.md](plans/SETTINGS_PHANTOM_PREVIEW_PLAN.md) | Settings-tab live 3D human preview (no RDSR); habitus scales + active-exam offsets; `PreviewSnapshot` + cross-tab refresh; face-up / back-on-support QA. Manual smoke then archive. |
| [plans/archive/ARMS_DOWN_PHANTOM_VARIANTS_PLAN.md](plans/archive/ARMS_DOWN_PHANTOM_VARIANTS_PLAN.md) | **Complete** — additive `_arms_down` for all clinical stems (23 twins; legacy via MPFB approx). |
| [plans/FUN_DEMO_PHANTOMS_PLAN.md](plans/FUN_DEMO_PHANTOMS_PLAN.md) | Broader fun-demo survey: nude classical (Venus/David, D1-gated), Phase 2 cartoons, bust fallbacks. v1 clothed+Steamboat execution archived (see archive entry). |
| [plans/gui-aesthetic-redesign.md](plans/gui-aesthetic-redesign.md) | Transition GUI from Aurora-Brutalist to Sleek Modern/Material aesthetic. |
| [plans/NATIVE_WINDOW_GEOMETRY_PLAN.md](plans/NATIVE_WINDOW_GEOMETRY_PLAN.md) | Native window geometry persistence: restore last size/position/maximized state on `--native` launch; first run maximized. |
| [plans/DEPENDENCY_AUDIT_PLAN.md](plans/DEPENDENCY_AUDIT_PLAN.md) | Update pre-push hooks and CI to audit project lockfile (uv audit) with fallback to active environment (pip-audit). |
| [plans/GRYPE_RELEASE_SCAN_PLAN.md](plans/GRYPE_RELEASE_SCAN_PLAN.md) | Add grype artifact scanning to the release workflow; policy via `.grype.yaml`; artifact upload. |
| [plans/2026-07-12-GEOMETRY_PREVIEW_CONTROLS_AND_COMPOSITE_PLAN.md](plans/2026-07-12-GEOMETRY_PREVIEW_CONTROLS_AND_COMPOSITE_PLAN.md) | Move Show all exams checkbox next to Full procedure, fix composite state leakage, upgrade event selection to searchable select with exam context. |
| [plans/GUISKINDOSE_PRIVACY_REPUBLICATION_PLAN.md](plans/GUISKINDOSE_PRIVACY_REPUBLICATION_PLAN.md) | Ordered execution plan for DICOM/tabular sanitization, enforceable privacy scanners, fork-preserving publication, and cautious PyPI publication. First `guiskindose` version is **`1.0.0`**. Mechanical rename: [plans/archive/GUISKINDOSE_RENAME_PLAN.md](plans/archive/GUISKINDOSE_RENAME_PLAN.md) (**complete**, PR #73). GitHub/Sonar/URLs: [plans/archive/GUISKINDOSE_GITHUB_RENAME_PLAN.md](plans/archive/GUISKINDOSE_GITHUB_RENAME_PLAN.md) (**complete**, 2026-09-04). |
| [plans/sonarqube_remediation_plan.md](plans/sonarqube_remediation_plan.md) | Phased remediation plan to address the 292 open SonarQube issues in the GUISkinDose codebase, prioritizing bug fixes and core complexity reduction. |
| [plans/HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md](plans/HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md) | HTML/PNG export: Phase 0 capture real exception; Phase 1 stop fake cancel errors; Phase 2 evidence-driven render fix; Phase 3 docs/tests. |
| [plans/PR22_NITPICKS_AND_WORKTREE_HOOKS_PLAN.md](plans/PR22_NITPICKS_AND_WORKTREE_HOOKS_PLAN.md) | PR 22 review nitpicks (code block tags & fixture reuse) + worktree-aware commit message git hook. |
| [plans/PR_CODE_REVIEW_FIXES_PLAN.md](plans/PR_CODE_REVIEW_FIXES_PLAN.md) | **Active** — Resolve open CodeRabbit PR review comments on branch refactor/sonar-lizard-fixes. |
| [plans/documentation-assessment.md](plans/documentation-assessment.md) | **Active** — Documentation & docstrings accuracy sweep (hub docs, `src/` docstrings, user-facing docs) plus standing matrix record and re-assessment triggers. Linked from `TO_DO.md`. |

## Archived plans (`plans/archive/`)

| File | Purpose |
|---|---|
| [plans/archive/SECURITY_TOOLS_CI_PLAN.md](plans/archive/SECURITY_TOOLS_CI_PLAN.md) | **Superseded** (2026-09-03) — semgrep/gitleaks wiring was completed; the `safety` scanner path was dropped when the `safety` dev dependency (and its main-only CI job) was removed in 1.0.0 — `uv audit` + `pip-audit` remain the dependency auditors. |
| [plans/archive/SONAR_PRIVACY_GATED_SCANS_PLAN.md](plans/archive/SONAR_PRIVACY_GATED_SCANS_PLAN.md) | **Complete** (PR #32) — Sonar security + GUI coverage tests; privacy-gated Semgrep/Sonar/CodeRabbit. Archived 2026-09-03: its `cloud-scans-main` job design was retired with the 1.0.0 `safety` removal. |
| [plans/archive/GUISKINDOSE_RENAME_PLAN.md](plans/archive/GUISKINDOSE_RENAME_PLAN.md) | **Complete** (PR #73, 2026-09-04) — in-repo rename to GUISkinDose / `guiskindose` at `1.0.0` (imports, CLI, config migration, tests, stale-brand gate). Its "Post-PR-1 retirement" section remains the lifecycle guidance for the dual-read/semgrep-ID shims (tracked in `TO_DO.md`). |
| [plans/archive/GUISKINDOSE_GITHUB_RENAME_PLAN.md](plans/archive/GUISKINDOSE_GITHUB_RENAME_PLAN.md) | **Complete** (2026-09-04) — GitHub fork renamed to `GUISkinDose`, SonarCloud key flipped, live URLs + `sonar-project.properties` retargeted (PR #74); fresh-clone/redirect check and `main` CI verified. |
| [plans/archive/KERMA_METER_CORRECTION_FACTORS_PLAN.md](plans/archive/KERMA_METER_CORRECTION_FACTORS_PLAN.md) | **Shipped** (2026-07-26) — per-(unit×tube) kerma-meter CF; reported kerma additive-compatible; file/GUI prompt. |
| [plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md](plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md) | **Completed** (2026-07-21) — headless MPFB/Blender true-shape phantom library Phases 0–4; 10 new meshes shipped in 25.2.0. Further phantoms: [ADDITIONAL_PHANTOMS.md](ADDITIONAL_PHANTOMS.md) + `TO_DO.md`. |
| [plans/archive/PHANTOM_QA_DEMO_GATE_AND_BARIATRIC_EXTREMITIES_PLAN.md](plans/archive/PHANTOM_QA_DEMO_GATE_AND_BARIATRIC_EXTREMITIES_PLAN.md) | **Completed** (2026-07-22) — Demo gate (`gui.json`), Steamboat supine, pediatric 5y male fix, bariatric thick-extremities variants. |
| [plans/archive/PHANTOM_MESH_NAMING_CONVENTION_PLAN.md](plans/archive/PHANTOM_MESH_NAMING_CONVENTION_PLAN.md) | **Completed** (2026-07-23) — `ped_*` / `adult_ecto|endo_*` / `adult_bariatric_{sex}_{1,2,3}` / `demo_*` + aliases. |
| [plans/archive/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md](plans/archive/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md) | **Completed** (2026-06-24) — Parts I–V: multi-exam Geometry selector, per-active patient/table-origin sliders, composite preview, Calculate/Settings summaries. Manual smoke remains in `TO_DO.md`. |
| [plans/archive/INTERACTIVE_TABLE_OFFSETS_PLAN.md](plans/archive/INTERACTIVE_TABLE_OFFSETS_PLAN.md) | **Completed** (2026-06-24) — Phases 0–2b single-exam Geometry patient/table-origin sliders. Phase 3 offset arrow deferred in `TO_DO.md`. |
| [plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md](plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md) | **Completed** (2026-07-22) — Demo phantoms v1: Cosmic Buddha, Ramesses II, Steamboat Willie shipped; Petite Herculanaise blocked (login/NC). Fun ingest + face-up `flip_y` gate + GUI `(demo)` labels. |
| [plans/archive/MAKEHUMAN_PHANTOM_GENERATION_MASTER_PLAN.md](plans/archive/MAKEHUMAN_PHANTOM_GENERATION_MASTER_PLAN.md) | **Superseded** (2026-07-21) — MakeHuman GUI master plan; replaced by [plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md](plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md). Phase sub-plans `MAKEHUMAN_PHASE1_*` … `MAKEHUMAN_PHASE5_*` archived alongside. |
| [plans/archive/refactor_check_sensitive_content_plan.md](plans/archive/refactor_check_sensitive_content_plan.md) | **Completed** (2026-07-18) — Privacy scan script complexity split into `check_sensitive_content.py` + `check_sensitive_helpers.py`. |
| [plans/archive/refactor_geometry_tab_complexity.md](plans/archive/refactor_geometry_tab_complexity.md) | **Completed** (2026-07-18) — Geometry tab complexity split into `geometry.py` + `geometry_builders.py`. |
| [plans/archive/refactor_results_tab_complexity.md](plans/archive/refactor_results_tab_complexity.md) | **Completed** (2026-07-18) — Results tab complexity split into `results.py` + `results_builders.py`. |
| [plans/archive/refactor_upload_tab_complexity.md](plans/archive/refactor_upload_tab_complexity.md) | **Completed** (2026-07-18) — Upload tab complexity split into `upload.py` + `upload_builders.py`. |
| [plans/archive/refactor_other_gui_tabs_complexity.md](plans/archive/refactor_other_gui_tabs_complexity.md) | **Completed** (2026-07-18) — Remaining GUI complexity (export, per-exam, calculate, data, geometry preview, import preview). |
| [plans/archive/GEOMETRY_PER_EXAM_EVENT_SELECTION_PLAN.md](plans/archive/GEOMETRY_PER_EXAM_EVENT_SELECTION_PLAN.md) | **Completed** (2026-07-12) — Geometry tab event-stepper UX (chevron prev/next + context caption) on the existing per-exam preview-slice foundation; trace-count guard documentation. |
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
| [plans/archive/phase-6-doc-integration.md](plans/archive/phase-6-doc-integration.md) | **Completed** — Sync mechanism for `docs/source/gui_help/` -> `src/guiskindose/gui/help/` with pre-commit + CI enforcement. |
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
| [info/PACKAGE_INSTALL.md](info/PACKAGE_INSTALL.md) | Why and how to install GUISkinDose as an editable package (`pip install -e .`). |
