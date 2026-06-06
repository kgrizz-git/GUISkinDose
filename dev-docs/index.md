# Documentation index

_Date: 2026-06-06_

Catalog of every file under `dev-docs/`. Start from [AGENTS.md](../AGENTS.md) for agent orientation, then [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md) for validation commands and the source-of-truth map.

---

## Harness

| File | Purpose |
|---|---|
| [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md) | Repository harness principles, golden rules, validation commands, CI expectations, and known gaps. |
| [../scripts/check_doc_freshness.py](../scripts/check_doc_freshness.py) | CI/local doc-freshness checker: broken relative links, inventory contradictions, advisory stale-pattern scan. |
| [HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md) | Phased roadmap to close harness gaps (CI parity, doc-freshness, entropy cleanup). |
| [TO_DO.md](TO_DO.md) | Short-term maintainer task list (GUI polish, tabular input, doc-freshness automation). |
| [index.md](index.md) | This catalog — one-line purpose for every file under `dev-docs/`. |
| GUI smoke tests | `tests/gui/` (requires `pip install -e '.[gui]'`); see `tests/scripts/launch_gui_headless.py` |

---

## Architecture

| File | Purpose |
|---|---|
| [CODEBASE_OVERVIEW.md](CODEBASE_OVERVIEW.md) | Full architecture, data flow, **package layering rules**, settings, classes, functions, and repository layout. |
| [FEATURE_INVENTORY.md](FEATURE_INVENTORY.md) | Exhaustive feature status ledger: calculations, rendering, settings, outputs, CLI, and API. |
| [MYPYSKINDOSE_MIGRATION_STATUS.md](MYPYSKINDOSE_MIGRATION_STATUS.md) | Fork vs upstream PySkinDose migration status and PyPI namespace rename progress. |

---

## GUI

| File | Purpose |
|---|---|
| [GUI_PLAN.md](GUI_PLAN.md) | Comprehensive NiceGUI implementation plan: phases, screen designs, and workflow. |
| [UI_ANALYSIS.md](UI_ANALYSIS.md) | Current UI state — Plotly plots, CLI, and gaps before/alongside the NiceGUI app. |
| [UI_values.md](UI_values.md) | GUI design tokens (colors, gradients, effects) mapped from `src/mypyskindose/gui/app.py`. |
| [../DESIGN.md](../DESIGN.md) | Root GUI aesthetic spec (brutalist/modern design system used for the NiceGUI app). |
| [POSITIONING_HELP_PLAN.md](POSITIONING_HELP_PLAN.md) | Plan for in-app help guiding users through phantom positioning offsets. |

---

## Input data

| File | Purpose |
|---|---|
| [INPUT_DATA_FLOW_AND_OFFSETS.md](INPUT_DATA_FLOW_AND_OFFSETS.md) | RDSR and JSON input flow, normalization settings, patient offsets, and internal DataFrame contract. |
| [VENDOR_COORDINATE_SYSTEMS.md](VENDOR_COORDINATE_SYSTEMS.md) | Vendor-specific coordinate conventions, normalization mapping, and Mermaid coordinate-system diagrams. |
| [TABULAR_RDSR_INPUT_PLAN.md](TABULAR_RDSR_INPUT_PLAN.md) | Staged plan for CSV/TSV/XLSX exported event-table inputs (Radimetrics, DoseTrack, etc.). |

---

## Plans (`plans/`)

| File | Purpose |
|---|---|
| [plans/gui-aesthetic-redesign.md](plans/gui-aesthetic-redesign.md) | Secondary plan: transition GUI from Aurora-Brutalist to Sleek Modern/Material aesthetic. |

---

## Misc (`info/`)

| File | Purpose |
|---|---|
| [info/PACKAGE_INSTALL.md](info/PACKAGE_INSTALL.md) | Why and how to install MyPySkinDose as an editable package (`pip install -e .`). |
