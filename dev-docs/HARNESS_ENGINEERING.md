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
| GUI current state + implementation plan | `dev-docs/GUI_PLAN.md` (§0 current state) |
| GUI design tokens (auto-generated) | `dev-docs/UI_values.md` via `scripts/generate_ui_values.py` |
| GUI aesthetic design spec (root) | `DESIGN.md` |
| Third-party license inventory | `dev-docs/THIRD_PARTY_NOTICES.md` (generated; do not move to repo root) |
| External library reference links | `dev-docs/references/` |
| In-app positioning help plan | `dev-docs/POSITIONING_HELP_PLAN.md` |
| Tabular CSV/TSV/XLSX input plan | `dev-docs/TABULAR_RDSR_INPUT_PLAN.md` |
| Fork vs upstream migration status | `dev-docs/MYPYSKINDOSE_MIGRATION_STATUS.md` |
| Short-term task list | `dev-docs/TO_DO.md` |
| Execution plans (phased detail) | `dev-docs/plans/` |
| Archived completed plans | `dev-docs/plans/archive/` |
| Package install and build | `dev-docs/info/PACKAGE_INSTALL.md` |
| Project packaging and tool configuration | `pyproject.toml` |
| Release history and semver notes | `CHANGELOG.md` |
| CI | `.github/workflows/ci.yml` |
| Local git hooks | `.pre-commit-config.yaml` |
| Secret scanning | `.github/workflows/gitleaks.yml` |
| Python SAST (Bandit) | `[tool.bandit]` in `pyproject.toml`; CI `bandit` job |
| Type-check helpers | `scripts/type_baseline.sh`, `.basedpyright/README.md` |
| Release build | `.github/workflows/release.yml` |
| Dependency and Actions updates | `.github/dependabot.yml` |

## Documentation conventions

Plans and backlog are split on purpose (Phase 6 closed `exec-plans/` as unnecessary at current team size). Use this map before adding or moving plan files:

| Tier | Location | When to use | Examples |
|---|---|---|---|
| **Master plan** | `dev-docs/*_PLAN.md` at catalog root | Long-lived topic source of truth; link from `AGENTS.md` | `GUI_PLAN.md`, `TABULAR_RDSR_INPUT_PLAN.md`, `POSITIONING_HELP_PLAN.md` |
| **Harness meta-plan** | `dev-docs/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md` | Repository/process improvement only — not product features | Phases 0–7 roadmap |
| **Execution plan** | `dev-docs/plans/*.md` | Phased work derived from a diagnostic or master plan | `refactor-execution.md`, `gui-decomposition-design.md` |
| **Archive** | `dev-docs/plans/archive/` | Completed or superseded execution plans | `basedpyright-fix-plan.md` |
| **Scratch backlog** | `dev-docs/TO_DO.md` | Short-term actionable items; link out to plans above | Harness CI tasks, open investigations |

**Naming:** keep `Topic_PLAN.md` for master plans at `dev-docs/` root. Do not add new docs under `src/` — all maintainer docs live under `dev-docs/`.

**Catalog:** every new or retired doc must update `dev-docs/index.md` in the same PR.

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

Unit tests include structural layer checks in `tests/unittests/test_architecture_layers.py` (settings independence, GUI → orchestration, dose pipeline isolation). See **Package layering** in `dev-docs/CODEBASE_OVERVIEW.md`.

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

The script scans `AGENTS.md`, `README.md`, `CHANGELOG.md`, optional `DESIGN.md`, and all markdown under `dev-docs/`:

- **CI-blocking:** broken relative markdown links; checkable contradictions against `FEATURE_INVENTORY.md` (e.g. tabular input marked planned but claimed implemented in `AGENTS.md` or `CHANGELOG.md`).
- **Advisory only:** stale-pattern hits (`not implemented`, `not wired`, `planned`) — printed as warnings; review and update text that is no longer true.

### Doc-gardening cadence

| When | Action |
|------|--------|
| Every feature/status PR | Run `python scripts/check_doc_freshness.py`; update `FEATURE_INVENTORY.md` if behavior changed |
| After GUI CSS changes | Run `python scripts/generate_ui_values.py` (or `--check` in CI later) |
| After dependency changes | Run `python scripts/check_licenses.py --write-notices` and commit `dev-docs/THIRD_PARTY_NOTICES.md` |
| **Before each release** | Re-run full doc-freshness; resolve stale-pattern warnings; bump `pyproject.toml` and `CHANGELOG.md`; verify harness rows in `FEATURE_INVENTORY.md` §0 match `[Unreleased]` |

**Release gate (target):** stale-pattern advisory warnings should become CI-blocking in the release workflow before the semver tag is cut. Until wired, maintainers clear warnings manually as part of release prep.

CI runs doc-freshness on Ubuntu for every push/PR (links and inventory contradictions only).

### GUI smoke tests (optional `[gui]` extra)

```bash
pip install -e ".[gui]"
python -m pytest tests/gui/
# or
python tests/scripts/launch_gui_headless.py
```

Uses NiceGUI user simulation (no browser). CI runs `tests/gui/` on Ubuntu in the `gui-smoke` job. Core matrix tests exclude `tests/gui/` (see `--ignore=tests/gui` in CI).

#### Writing NiceGUI `User` tests — gotchas (learned the hard way)

These pass locally but fail on CI if you get them wrong; `basedpyright` and the pre-push hook **cannot** catch them (they're runtime/environment behavior, not types), so a GUI test must be validated with an actual `pytest tests/gui/` run — and ideally a CI run, since CI runners are slower than local.

- **Trigger handlers via `.click()` / `.trigger()`, not `element.set_value(...)`.** A direct `set_value` fires `on_value_change` *outside* the NiceGUI client context, where `nicegui.run.io_bound` short-circuits to `None` (`core.app.is_stopping` / pool down). A handler that does `ok, msg = await run.io_bound(...)` then raises `TypeError: cannot unpack non-iterable NoneType`. `UserInteraction.click()` runs the handler inside `with user.client:`, so the I/O-bound work actually executes.
- **Wait before interacting with elements that render lazily.** Clicking a `ui.select` option immediately after opening the dropdown races the menu render and silently no-ops on slower runners. `await user.should_see("<option label>")` first, then click it.
- **`should_see` defaults to `retries=3` (~0.3s).** An async `run.io_bound` load (e.g. parsing an RDSR) can outlast that on CI, so the assertion times out a beat before the UI updates. Pass `retries=` generously (e.g. 50) when asserting on a result that follows an awaited background task.
- **`should_see(content=...)` is a case-sensitive substring match**, and the simulation treats the whole page as visible (no scrolling). `"EVENTS"` matches `"25 EVENTS"`; `"Events"` does not.

### Type checking (optional `[dev]` extra)

```bash
pip install -e ".[dev,gui]"
basedpyright
```

CI runs plain `basedpyright` in the `typecheck` job — **any type error fails**. Configuration lives in `[tool.basedpyright]` in `pyproject.toml`.

**Optional baseline (incremental typing only):** when temporarily accepting known errors, see `.basedpyright/README.md`.

| Action | Command |
|--------|---------|
| Shrink baseline after fixes | `./scripts/type_baseline.sh shrink` (auto-removes fixed diagnostics; **do not** use `--writebaseline`) |
| Add current errors to baseline | `./scripts/type_baseline.sh write` |
| Re-enable baseline in CI | `basedpyright --baselinefile .basedpyright/baseline.json` (lock mode in CI; commit baseline updates with fix PRs) |

Locally, `basedpyright --baselinefile .basedpyright/baseline.json` uses **auto** mode and updates the file when errors decrease. CI defaults to **lock** mode when a baseline file is used — never delete the baseline to shrink it; run `shrink` locally and commit the result.

`table_data/` offline scripts are excluded from analysis (optional `spekpy` dependency).

### Secret scanning

Gitleaks runs on every push/PR via `.github/workflows/gitleaks.yml` (full repository history). Do not commit credentials; see CodeGuard hardcoded-credentials rules in `.cursor/rules/`.

### Dependency vulnerability scan (optional `[dev]` extra)

```bash
pip install -e ".[dev,gui]"
pip-audit --desc on
```

CI runs the same audit in the `dependency-audit` job (Ubuntu, Python 3.12).

**Policy:**

- **Scope:** PyPI-resolved packages for core dependencies plus `[dev]` and `[gui]` extras (widest maintained install surface).
- **Gate:** CI **fails** on any known vulnerability in the OSV/PyPI advisory data (`pip-audit` default).
- **Local editable install:** `mypyskindose` itself is skipped (not published on PyPI); this is expected.
- **Remediation:** bump the affected dependency in `pyproject.toml`, or add a documented `--ignore-vuln` entry only after maintainer review (avoid silent ignores).

Broader SBOM-style scanning (e.g. **grype** on built wheels) remains optional; see `dev-docs/TO_DO.md`.

### License compliance

Policy and workflow: [`dev-docs/LICENSE_COMPLIANCE.md`](LICENSE_COMPLIANCE.md).

```bash
pip install -e ".[dev,gui]"
python scripts/check_licenses.py
python scripts/check_licenses.py --write-notices   # after dependency changes
python scripts/check_licenses.py --check-notices   # verify tracked inventory
```

A pre-commit hook (`license-notices`) runs `--check-notices` automatically on every commit, blocking if `THIRD_PARTY_NOTICES.md` is stale. This prevents forgetting to update the file after dependency changes. CI runs the same check (plus `pip-audit`) in the `dependency-audit` job.

**Policy:**

- **Scope:** Same install surface as vulnerability audit (core + `[dev]` + `[gui]`).
- **Gate:** CI **fails** on forbidden strong-copyleft licenses (GPL/AGPL family).
- **Inventory:** `dev-docs/THIRD_PARTY_NOTICES.md` is generated from the installed environment; commit updates when dependencies change.
- **Remediation:** Replace or avoid forbidden packages; for unknown metadata, improve normalization in `scripts/check_licenses.py` or escalate for legal review.

### Bandit (Python SAST, optional `[dev]` extra)

```bash
pip install -e ".[dev]"
bandit -c pyproject.toml -r src/mypyskindose scripts --severity-level medium
```

CI runs the same command in the Ubuntu `bandit` job (Python 3.12).

**Policy:**

- **Scope:** Application code under `src/mypyskindose/` and `scripts/` (not `tests/`).
- **Config:** `[tool.bandit]` in `pyproject.toml` (excludes `table_data/`, venvs, backups).
- **Gate:** CI **fails** on **medium or high** severity findings. Low-severity items (e.g. `B110` try/except/pass in GUI helpers) are visible with `--severity-level low` but do not block CI.
- **Overlap:** Complements gitleaks (secrets in git) and pip-audit (dependency CVEs); does not replace either.

### Local git hooks (optional `[dev]` extra)

Fast checks run via [pre-commit](https://pre-commit.com/) (subset of CI — not a replacement):

```bash
pip install -e ".[dev,gui]"
pre-commit install                    # commit hooks (once per clone)
pre-commit install --hook-type pre-push   # basedpyright before push
pre-commit run --all-files            # manual full run (commit stage)
pre-commit run --hook-stage pre-push basedpyright --all-files
```

**Commit hooks** (`.pre-commit-config.yaml`):

| Hook | What it runs |
|---|---|
| **ruff** | `ruff check --fix` on `src/` and `tests/` |
| **gitleaks** | Secret scan on staged changes |
| **bandit** | Python SAST on `src/mypyskindose/` + `scripts/` (medium+ severity) |
| **doc-freshness** | `python scripts/check_doc_freshness.py` (broken links; stale-pattern warnings only) |
| **cleanup-old-backups** | `python scripts/cleanup_old_backups.py` (delete `backups/*.bak` older than 5 commits) |
| **license-notices** | `python scripts/check_licenses.py --check-notices` (blocks commit if `THIRD_PARTY_NOTICES.md` is stale) |

**Pre-push hook:**

| Hook | What it runs |
|---|---|
| **basedpyright** | Full-project type check (matches CI `typecheck` job; requires `.[dev,gui]`) |

**Not in local hooks** (CI-only or manual): full pytest matrix, pip-audit, license compliance (`--write-notices`), GUI smoke, `compileall`, `python -m build`.

Hooks can be skipped with `SKIP=gitleaks git commit ...`, `git commit --no-verify`, or `git push --no-verify` (CI remains the blocking gate on push/PR).

## CI expectations

CI should be treated as a blocking quality gate, not only as telemetry:

- syntax/lint checks should fail the workflow on errors
- tests should fail the workflow on errors
- full cross-platform matrix runs on **`main` pushes and pull requests**; other branch pushes use a quick Ubuntu + Python 3.12 cell only
- docs-only changes may run a smaller check set, but should still pass basic syntax and markdown/link sanity when such tooling exists

### Test matrix policy (`build` job)

| Trigger | Matrix |
|---------|--------|
| Pull request | 12 cells — Ubuntu/macOS/Windows × Python 3.10–3.13 |
| Push to `main` | Same full matrix |
| Push to other branches (e.g. `WIP`) | 1 cell — Ubuntu + Python 3.12 |

Other CI jobs (typecheck, bandit, pip-audit, GUI smoke, package build, doc-freshness) still run on every push/PR. Workflow concurrency cancels superseded runs on the same branch/PR.

**Current CI vs local checks:** `.github/workflows/ci.yml` matches the **Full checks** list above on CI:

| Check | Where in CI |
|---|---|
| `python -m compileall src/mypyskindose` | `build` job (full matrix on PR/`main`; quick cell otherwise) |
| `python -m pytest` | `build` job (same matrix policy) |
| `python -m ruff check src tests` | `build` job (same matrix policy) |
| `python -m build` | Ubuntu `package-build` job (Python 3.12) |
| `python scripts/check_doc_freshness.py` | Ubuntu `doc-freshness` job |
| GUI smoke tests | `python -m pytest tests/gui/` | Ubuntu `gui-smoke` job (requires `.[gui]`) |
| `basedpyright` | Ubuntu `typecheck` job (requires `.[dev,gui]`) |
| gitleaks secret scan | `.github/workflows/gitleaks.yml` on push/PR |
| `bandit -c pyproject.toml -r src/mypyskindose scripts --severity-level medium` | Ubuntu `bandit` job (requires `.[dev]`) |
| `pip-audit --desc on` | Ubuntu `dependency-audit` job (requires `.[dev,gui]`) |
| `python scripts/check_licenses.py` | Ubuntu `dependency-audit` job (forbidden licenses; `--check-notices`) |
| pre-commit (local) | `.pre-commit-config.yaml` — commit: ruff, gitleaks, bandit, doc-freshness, backup cleanup; pre-push: basedpyright |

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

Tracked in `dev-docs/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md` and `dev-docs/TO_DO.md`:

- Tabular input Phases 1–5 shipped; Qaelum/DoseMonitor/DoseWatch adapters remain stubs pending real export fixtures (`TABULAR_RDSR_INPUT_PLAN.md`, `FEATURE_INVENTORY.md`).
- Stale-pattern doc-freshness scan is advisory only (not yet CI-blocking before release).
- Execution plan template and lifecycle partially documented; see `TO_DO.md` § Documentation / plans.
