# Documentation index

_Date: 2026-06-12_

Catalog of every file under `dev-docs/`. Start from [AGENTS.md](../AGENTS.md) for agent orientation, then [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md) for validation commands and the source-of-truth map.

---

## Harness

| File | Purpose |
|---|---|
| [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md) | Repository harness principles, golden rules, **documentation conventions** (master vs execution plans), validation commands, CI expectations, doc-gardening cadence, and known gaps. |
| [LICENSE_COMPLIANCE.md](LICENSE_COMPLIANCE.md) | Third-party license policy, `scripts/check_licenses.py`, and `THIRD_PARTY_NOTICES.md` workflow. |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | **Canonical location** — generated license inventory (not repo root). |
| [../scripts/check_licenses.py](../scripts/check_licenses.py) | CI/local license audit: forbidden copyleft gate and notices inventory generator. |
| [../scripts/check_doc_freshness.py](../scripts/check_doc_freshness.py) | CI/local doc-freshness checker: broken links, inventory contradictions (AGENTS + CHANGELOG), advisory stale-pattern scan. |
| [../scripts/generate_ui_values.py](../scripts/generate_ui_values.py) | Regenerates `UI_values.md` from `MODERN_CSS` in `gui/styles.py`. |
| Bandit | `[tool.bandit]` in `pyproject.toml`; CI `bandit` job and pre-commit hook (medium+ severity on `src/mypyskindose` + `scripts`). |
| [HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md) | Phased roadmap; Phases 0–5 complete; Phase 6 closed; Phase 7 references stub. |
| [TO_DO.md](TO_DO.md) | Actionable tasks, open questions, and completed harness milestones. |
| [index.md](index.md) | This catalog — one-line purpose for every file under `dev-docs/`. |
| GUI smoke tests | `tests/gui/` (requires `pip install -e '.[gui]'`); see `tests/scripts/launch_gui_headless.py` |
| [references/](references/README.md) | Links to pydicom, NiceGUI, Plotly, and other dependency docs. |

---

## Architecture

| File | Purpose |
|---|---|
| [CODEBASE_OVERVIEW.md](CODEBASE_OVERVIEW.md) | Full architecture, data flow, **package layering rules**, settings, classes, functions, and repository layout. |
| [FEATURE_INVENTORY.md](FEATURE_INVENTORY.md) | Feature status ledger: calculations, rendering, settings, outputs, CLI, API, and **harness/CI §0**. |
| [MYPYSKINDOSE_MIGRATION_STATUS.md](MYPYSKINDOSE_MIGRATION_STATUS.md) | Fork vs upstream PySkinDose migration status and PyPI namespace rename progress. |
| [REFACTOR_ASSESSMENT.md](REFACTOR_ASSESSMENT.md) | Point-in-time diagnostic: largest files/functions, modularity/robustness/security findings. Plan in [plans/refactor-execution.md](plans/refactor-execution.md). |

---

## Master plans (`dev-docs/` root)

Long-lived topic source-of-truth plans. Convention: [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md) § Documentation conventions.

| File | Purpose |
|---|---|
| [GUI_PLAN.md](GUI_PLAN.md) | **Source of truth** — current UI state (§0) and NiceGUI implementation plan. |
| [POSITIONING_HELP_PLAN.md](POSITIONING_HELP_PLAN.md) | Plan for in-app help guiding users through phantom positioning offsets. |
| [TABULAR_RDSR_INPUT_PLAN.md](TABULAR_RDSR_INPUT_PLAN.md) | Staged plan for CSV/TSV/XLSX exported event-table inputs (Radimetrics, DoseTrack, etc.). Phases 1–5 shipped; Phase 5+ vendor stubs documented in-plan. |

---

## GUI

| File | Purpose |
|---|---|
| [GUI_PLAN.md](GUI_PLAN.md) | See **Master plans** above. |
| [UI_values.md](UI_values.md) | Auto-generated GUI design tokens from `src/mypyskindose/gui/app.py` (`scripts/generate_ui_values.py`). |
| [../DESIGN.md](../DESIGN.md) | Root GUI aesthetic spec (brutalist/modern design intent). |

---

## Input data

| File | Purpose |
|---|---|
| [INPUT_DATA_FLOW_AND_OFFSETS.md](INPUT_DATA_FLOW_AND_OFFSETS.md) | RDSR and JSON input flow, normalization settings, patient offsets, and internal DataFrame contract. |
| [VENDOR_COORDINATE_SYSTEMS.md](VENDOR_COORDINATE_SYSTEMS.md) | Vendor-specific coordinate conventions, normalization mapping, and Mermaid coordinate-system diagrams. |
| [TABULAR_RDSR_INPUT_PLAN.md](TABULAR_RDSR_INPUT_PLAN.md) | See **Master plans** above. |
| [COORD_TRANSFORM_COMPARISON.md](COORD_TRANSFORM_COMPARISON.md) | Side-by-side comparison of coordinate transforms and preprocessing across MyPySkinDose, dhen2714/PySkinDose, and PSDCalcReworkTemp. |

---

## Execution plans (`plans/`)

Phased detail derived from diagnostics or master plans.

| File | Purpose |
|---|---|
| [plans/gui-aesthetic-redesign.md](plans/gui-aesthetic-redesign.md) | Transition GUI from Aurora-Brutalist to Sleek Modern/Material aesthetic. |
| [plans/refactor-execution.md](plans/refactor-execution.md) | Phased execution for refactor work diagnosed in [REFACTOR_ASSESSMENT.md](REFACTOR_ASSESSMENT.md). |
| [plans/gui-decomposition-design.md](plans/gui-decomposition-design.md) | Wiring map and safe-extraction design for splitting `gui/app.py`'s `index()` (refactor plan Phase 3). |

## Archived plans (`plans/archive/`)

| File | Purpose |
|---|---|
| [plans/archive/README.md](plans/archive/README.md) | Index of completed or superseded execution plans. |
| [plans/archive/basedpyright-fix-plan.md](plans/archive/basedpyright-fix-plan.md) | **Completed** — strict basedpyright rollout (147 errors → 0). |

---

## Misc (`info/`)

| File | Purpose |
|---|---|
| [info/PACKAGE_INSTALL.md](info/PACKAGE_INSTALL.md) | Why and how to install MyPySkinDose as an editable package (`pip install -e .`). |
