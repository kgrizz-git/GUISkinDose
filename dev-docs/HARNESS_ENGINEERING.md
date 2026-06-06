# Harness engineering alignment

_Date: 2026-06-04_

This document turns the repository into a more reliable harness for AI agents and human maintainers. It is based on the OpenAI harness-engineering pattern: keep project knowledge in the repo, make `AGENTS.md` a concise map, encode recurring checks as commands, and prefer mechanical validation over tribal knowledge.

## Repository contract for agents

Agents working in this repository should be able to answer three questions quickly:

1. **What is this system?**
   MyPySkinDose estimates peak skin dose and 3D skin dose maps from fluoroscopic irradiation event data.
2. **Where is the authoritative context?**
   `AGENTS.md` is the short entry point. Detailed context lives in `dev-docs/`.
3. **How do I validate changes?**
   Use the checks listed below and add/extend tests when changing behavior.

## Source-of-truth map

| Topic | File |
|---|---|
| Agent quickstart, conventions, current development focus | `AGENTS.md` |
| Harness principles, validation commands, known gaps | `dev-docs/HARNESS_ENGINEERING.md` |
| Harness improvement plan and phased roadmap | `dev-docs/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md` |
| Documentation catalog | `dev-docs/index.md` |
| Architecture, data flow, and layering rules | `dev-docs/CODEBASE_OVERVIEW.md` |
| Feature inventory and known missing features | `dev-docs/FEATURE_INVENTORY.md` |
| RDSR normalization, offsets, DataFrame contract | `dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md` |
| Vendor coordinate systems | `dev-docs/VENDOR_COORDINATE_SYSTEMS.md` |
| GUI implementation status and plan | `dev-docs/GUI_PLAN.md` |
| GUI current-state analysis | `dev-docs/UI_ANALYSIS.md` |
| GUI aesthetic design spec (root) | `DESIGN.md` |
| In-app positioning help plan | `dev-docs/POSITIONING_HELP_PLAN.md` |
| Tabular CSV/TSV/XLSX input plan | `dev-docs/TABULAR_RDSR_INPUT_PLAN.md` |
| Fork vs upstream migration status | `dev-docs/MYPYSKINDOSE_MIGRATION_STATUS.md` |
| Short-term task list | `dev-docs/TO_DO.md` |
| Secondary plans | `dev-docs/plans/` |
| Package install and build | `dev-docs/info/PACKAGE_INSTALL.md` |
| Project packaging and tool configuration | `pyproject.toml` |
| Release history and semver notes | `CHANGELOG.md` |
| CI | `.github/workflows/ci.yml` |
| Release build | `.github/workflows/release.yml` |
| Dependency and Actions updates | `.github/dependabot.yml` |

## Golden rules

1. **Keep docs current with behavior.**
   If a change adds, removes, or wires a feature, update `AGENTS.md` and the relevant `dev-docs/` page in the same PR.
2. **Do not hide input transformations.**
   RDSR parsing, tabular imports, unit conversions, and normalization offsets must be documented and tested — see [INPUT_DATA_FLOW_AND_OFFSETS.md](INPUT_DATA_FLOW_AND_OFFSETS.md).
3. **One internal calculation contract.**
   All input sources should feed the same normalized DataFrame contract before dose calculation.
4. **Optional UX dependencies stay optional.**
   GUI and Excel-specific dependencies should remain extras unless maintainers intentionally promote them to core.
5. **Cross-platform by default.**
   Use `pathlib.Path`, avoid shell-specific path assumptions in Python code, and keep CI on Windows/macOS/Linux.
6. **Fail loudly on clinical-data ambiguity.**
   Unknown units, missing geometry, unsupported scanner models, or ambiguous tabular schemas should produce actionable errors or explicit warnings before calculation.

## Validation commands

Run the smallest relevant set locally before committing, and run the full set before changes that affect calculations, parsing, packaging, or CI.

### Fast checks

```bash
python -m compileall src/mypyskindose
python -m pytest tests/unittests
```

### Full checks

```bash
python -m pytest
python -m ruff check src tests
python -m build
```

### Documentation freshness check

Run the harness doc-freshness script before feature or status PRs:

```bash
python scripts/check_doc_freshness.py
```

The script scans `AGENTS.md`, `README.md`, optional `DESIGN.md`, and all markdown under `dev-docs/`:

- **CI-blocking:** broken relative markdown links; checkable contradictions against `FEATURE_INVENTORY.md` (e.g. tabular input marked planned but claimed implemented in `AGENTS.md`).
- **Advisory only:** stale-pattern hits (`not implemented`, `not wired`, `planned`) — printed as warnings; review and update text that is no longer true.

Maintainer cadence: run locally before feature/status changes; CI runs the same check on Ubuntu for every push/PR.

## CI expectations

CI should be treated as a blocking quality gate, not only as telemetry:

- syntax/lint checks should fail the workflow on errors
- tests should fail the workflow on errors
- cross-platform matrix should remain active
- docs-only changes may run a smaller check set, but should still pass basic syntax and markdown/link sanity when such tooling exists

**Current CI vs local checks:** `.github/workflows/ci.yml` matches the **Full checks** list above on CI:

| Check | Where in CI |
|---|---|
| `python -m compileall src/mypyskindose` | All matrix cells (`build` job) |
| `python -m pytest` | All matrix cells |
| `python -m ruff check src tests` | All matrix cells |
| `python -m build` | Ubuntu `package-build` job (Python 3.12) |
| `python scripts/check_doc_freshness.py` | Ubuntu `doc-freshness` job |

Release publishing still runs `python -m build` in `.github/workflows/release.yml` on tag creation.

**Lint policy:** `ruff` is the primary style linter (120-column, matches `pyproject.toml`). CI `flake8` runs only `E9,F63,F7,F82` (syntax errors and undefined names).

## PR checklist

Every PR should answer:

- What changed?
- Which user workflow is affected?
- Which files are the source of truth for this behavior?
- Which commands were run?
- Were docs updated with code behavior?
- Are there new clinical-data assumptions, unit conversions, or normalization rules?
- Are dependencies still correctly classified as core vs optional extras?

## Known alignment gaps

Tracked in `dev-docs/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md` with phased remediation:

- There are no automated GUI smoke tests yet (NiceGUI app exists under `src/mypyskindose/gui/`).
- Tabular input adapters are planned but not implemented (`FEATURE_INVENTORY.md`).
