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
| Shared coding-agent playbook | `dev-docs/AGENT_PLAYBOOK.md` |
| Claude Code pointer file | `CLAUDE.md` |
| Gemini CLI pointer file | `GEMINI.md` |
| Qwen Code pointer file | `QWEN.md` |
| Harness principles, validation commands, known gaps | `dev-docs/HARNESS_ENGINEERING.md` |
| Harness improvement plan and phased roadmap | `dev-docs/plans/archive/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md` |
| Documentation catalog | `dev-docs/index.md` |
| Architecture, data flow, and layering rules | `dev-docs/CODEBASE_OVERVIEW.md` |
| Feature inventory and known missing features | `dev-docs/FEATURE_INVENTORY.md` |
| RDSR normalization, offsets, DataFrame contract | `dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md` |
| Vendor coordinate systems | `dev-docs/VENDOR_COORDINATE_SYSTEMS.md` |
| GUI current state + implementation plan | `dev-docs/plans/GUI_PLAN.md` (§0 current state) |
| GUI design tokens (auto-generated) | `dev-docs/UI_values.md` via `scripts/generate_ui_values.py` |
| GUI aesthetic design spec (root) | `DESIGN.md` |
| Third-party license inventory | `dev-docs/THIRD_PARTY_NOTICES.md` (generated; do not move to repo root) |
| External library reference links | `dev-docs/references/` |
| In-app positioning help plan | `dev-docs/plans/POSITIONING_HELP_PLAN.md` |
| Tabular CSV/TSV/XLSX input plan | `dev-docs/plans/TABULAR_RDSR_INPUT_PLAN.md` |
| Fork vs upstream migration status | `dev-docs/MYPYSKINDOSE_MIGRATION_STATUS.md` |
| Short-term task list | `dev-docs/TO_DO.md` |
| Diagnostics and assessments (refactoring, code quality, etc.) | `dev-docs/assessments/` |
| Active plans folder | `dev-docs/plans/` |
| Archived completed plans | `dev-docs/plans/archive/` |
| Package install and build | `dev-docs/info/PACKAGE_INSTALL.md` |
| Project packaging and tool configuration | `pyproject.toml` |
| Release history and semver notes | `CHANGELOG.md` |
| CI | `.github/workflows/ci.yml` |
| Local git hooks | `.pre-commit-config.yaml` |
| Changelog enforcement (CI on PRs + pre-push) | `scripts/check_changelog.py` |
| Agent guidance drift check (advisory) | `scripts/check_agent_guidance.py` |
| Doc pruning candidates (advisory) | `scripts/check_doc_pruning.py` |
| Secret scanning | `.github/workflows/gitleaks.yml` |
| Python SAST (Bandit) | `[tool.bandit]` in `pyproject.toml`; CI `bandit` job |
| OWASP SAST (Semgrep) | `p/owasp-top-ten`; CI `static-analysis` job + pre-push hook |
| Shell-script lint (ShellCheck) | `shellcheck-py` pre-commit hook + CI `static-analysis` job |
| Type-check helpers | `scripts/type_baseline.sh`, `.basedpyright/README.md` |
| Release build | `.github/workflows/release.yml` |
| Dependency and Actions updates | `.github/dependabot.yml` |

## Documentation conventions

Plans and backlog are split on purpose (Phase 6 closed `exec-plans/` as unnecessary at current team size). Use this map before adding or moving plan files:

| Tier | Location | When to use | Examples |
|---|---|---|---|
| **Master plan** | `dev-docs/plans/*_PLAN.md` | Long-lived topic source of truth; link from `AGENTS.md` | `GUI_PLAN.md`, `TABULAR_RDSR_INPUT_PLAN.md`, `POSITIONING_HELP_PLAN.md` |
| **Harness meta-plan** | `dev-docs/plans/archive/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md` | Repository/process improvement only — not product features | Phases 0–7 roadmap |
| **Execution plan** | `dev-docs/plans/*.md` | Phased work derived from a diagnostic or master plan | `refactor-execution.md`, `gui-decomposition-design.md` |
| **Archive** | `dev-docs/plans/archive/` | Completed or superseded execution plans | `basedpyright-fix-plan.md` |
| **Scratch backlog** | `dev-docs/TO_DO.md` | Short-term actionable items; link out to plans above | Harness CI tasks, open investigations |
| **Assessment** | `dev-docs/assessments/*.md` | Diagnostics and assessments of code quality, refactoring, bug checks, or security | `REFACTOR_ASSESSMENT.md` |

**Naming:** keep `Topic_PLAN.md` for master plans under `dev-docs/plans/`. Do not add new docs under `src/` — all maintainer docs live under `dev-docs/`.

**Catalog:** every new or retired doc must update `dev-docs/index.md` in the same PR.

**Archive rules:** Once work in an execution plan is complete or superseded, move the plan file into `dev-docs/plans/archive/` and update its path in the catalog to keep the active plans directory uncluttered.

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
   Target Windows, macOS, and Linux for user-facing behavior. Use `pathlib.Path` and `Path.replace()` for paths and
   atomic writes; avoid `sys.platform` branches unless unavoidable with fallbacks. Keep `gui` / `gui-native` optional
   and CI unit tests passing without `gui-native`. See `AGENTS.md` → Conventions → Cross-platform.
6. **Fail loudly on clinical-data ambiguity.**
   Unknown units, missing geometry, unsupported scanner models, or ambiguous tabular schemas should produce actionable errors or explicit warnings before calculation.
7. **Keep files to a reasonable size (Modularity).**
   Keep all Python source files and Markdown documentation files under ~800 lines to ensure maintainability and agent legibility. Outliers must be explicitly whitelisted in `scripts/check_file_sizes.py` and scheduled for refactoring.
8. **Archive completed or superseded plans.**
   Always move completed or superseded execution plans from `dev-docs/plans/` to `dev-docs/plans/archive/` and update `dev-docs/index.md` catalog references.
9. **Store diagnostics and assessments in the designated folder.**
   Place diagnostic reports or assessments (such as for refactoring, code quality, bug checks, etc.) under `dev-docs/assessments/` and register them in `dev-docs/index.md`.
10. **Maintain workspace cleanliness.**
    Scratch scripts, temporary code, and local output files must be kept in explicitly gitignored paths (e.g. `scripts/scratch_*`, `*.tmp`, `debug_*`) or deleted immediately unless they are intended for reuse. Do not check temp or experimental scrap into the repository.
11. **Review stale docs before deleting them.**
    `scripts/check_doc_pruning.py` reports active execution plans and assessments that have not been touched for at least 30 days and 10 commits. Treat this as a review queue: archive completed/superseded plans, keep still-useful assessments, and delete only when intentionally obsolete.
12. **Keep agent guidance shared and short.**
    `AGENTS.md` is the project entry point and `dev-docs/AGENT_PLAYBOOK.md` holds shared workflow rules. Tool-specific files such as `CLAUDE.md`, `GEMINI.md`, and `QWEN.md` should be short pointers unless the tool needs a documented local override.



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
python scripts/check_changelog.py   # requires origin/main to be fetched
```

### Repository hygiene checks

```bash
python scripts/check_untracked_scratch.py
python scripts/check_ignored_asset_files.py
python scripts/check_ignored_asset_files.py --strict   # optional release/maintenance gate
python scripts/check_agent_guidance.py
python scripts/check_agent_guidance.py --strict   # optional release/maintenance gate
python scripts/check_doc_pruning.py
python scripts/check_doc_pruning.py --strict   # optional release/maintenance gate
```

`check_untracked_scratch.py` blocks untracked scratch/temp files, including anything under `tmp/`.
`check_ignored_asset_files.py` is advisory by default. It warns when `.png` or `.html` files
outside `PlotOutputs/` (and other build/output trees) are untracked or gitignored — including
tracked-but-ignored assets that can be dropped by `git rm --cached` while `*.png` / `*.html`
remain in `.gitignore` (only `!docs/**/*.png` is exempted today).
`check_doc_pruning.py` is advisory by default. It reports direct active execution plans under
`dev-docs/plans/*.md` (excluding master `*_PLAN.md` files) and assessments under
`dev-docs/assessments/*.md` once both thresholds are met: **30 days** and **10 commits** since
last git touch. It does not auto-delete documentation.
`check_agent_guidance.py` is advisory by default. It warns when tool-specific agent files do not
point back to `AGENTS.md`, when `TO_DO.md` is drifting back into a historical ledger, or when
active execution plans appear complete but have not been archived.

### Documentation freshness check

Run the harness doc-freshness script before feature or status PRs:

```bash
python scripts/check_doc_freshness.py
```

The script scans `AGENTS.md`, `README.md`, `CHANGELOG.md`, optional `DESIGN.md`, and all markdown under `dev-docs/`:

- **CI-blocking:** broken relative markdown links; checkable contradictions against `FEATURE_INVENTORY.md` (e.g. one document says a feature is roadmap-only while another says it has shipped).
- **Advisory only:** stale-keyword hits — printed as warnings; review and update text that is no longer true.

### Doc-gardening cadence

| When | Action |
|------|--------|
| Every feature/status PR | Run `python scripts/check_doc_freshness.py`; update `FEATURE_INVENTORY.md` if behavior changed |
| After GUI CSS changes | Run `python scripts/generate_ui_values.py` (or `--check` in CI later) |
| After dependency changes | Run `python scripts/check_licenses.py --write-notices` and commit `dev-docs/THIRD_PARTY_NOTICES.md` |
| Monthly / before release | Run `python scripts/check_doc_pruning.py`; archive or intentionally keep stale candidates |
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
python scripts/audit_dependencies.py
```

Auditing is orchestrated by a wrapper script [scripts/audit_dependencies.py](../scripts/audit_dependencies.py) which checks locked dependencies using `uv audit` when `uv` (>= 0.11.19) is installed and a `uv.lock` is present. Locally the wrapper passes `--frozen` (audit the committed lockfile without relocking or downloading an interpreter); in CI it passes `--locked` so a stale `uv.lock` fails loudly. Otherwise, it falls back to auditing the active environment using `pip-audit --desc on`.

CI runs the same audit (Ubuntu, Python 3.12, with `uv` installed).

**Policy:**

- **Scope:** PyPI-resolved packages for core dependencies plus `[dev]` and `[gui]` extras (widest maintained install surface).
- **Gate:** CI **fails** on any known vulnerability in the OSV/PyPI advisory data (via `uv audit` when `uv` is available, otherwise `pip-audit`).
- **Local editable install:** `mypyskindose` itself is skipped (not published on PyPI); this is expected.
- **Remediation:** bump the affected dependency in `pyproject.toml`, or add a documented entry under
  `[tool.uv.audit]` in `pyproject.toml` only after maintainer review (avoid silent ignores). Use
  `ignore-until-fixed` when no patched release exists yet so the audit re-fails automatically once
  upstream ships a fix. The wrapper mirrors those IDs to `pip-audit --ignore-vuln` on its fallback
  path. Revisit suppressions quarterly or before releases (see `dev-docs/TO_DO.md`).

**Release artifact scanning (grype):** The release workflow (`release.yml`) scans the built wheel and sdist with [grype](https://github.com/anchore/grype) before publishing. Policy is set in `.grype.yaml` at the repository root (`fail-on: high`, `only-fixed: true`). See [`dev-docs/plans/GRYPE_RELEASE_SCAN_PLAN.md`](plans/GRYPE_RELEASE_SCAN_PLAN.md).

To scan locally before tagging a release:

```bash
rm -rf dist/ build/
python -m build
# macOS:
brew install grype
# Linux/macOS curl installer:
# curl -sSfL https://get.anchore.io/grype | sudo sh -s -- -b /usr/local/bin
grype dist/*.whl dist/*.tar.gz --fail-on high --only-fixed
```

### License compliance

Policy and workflow: [`dev-docs/LICENSE_COMPLIANCE.md`](LICENSE_COMPLIANCE.md).

```bash
pip install -e ".[dev,gui]"
python scripts/check_licenses.py
python scripts/check_licenses.py --write-notices   # after dependency changes
python scripts/check_licenses.py --check-notices   # verify tracked inventory
```

A pre-commit hook (`license-notices`) runs `--check-notices` automatically on every commit, blocking if `THIRD_PARTY_NOTICES.md` is stale. This prevents forgetting to update the file after dependency changes. CI runs the same check (plus `python scripts/audit_dependencies.py`) in the `static-analysis` job.

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
# macOS / Linux
bash scripts/setup-dev.sh

# Windows
scripts\setup-dev.bat

# Manual runs
pre-commit run --all-files                       # commit-stage hooks
pre-commit run --hook-stage pre-push --all-files # pre-push hooks (semgrep, pip-audit, basedpyright, changelog)
```

**Commit hooks** (`.pre-commit-config.yaml`):

| Hook | What it runs |
|---|---|
| **ruff** | `ruff check --fix` on `src/` and `tests/` |
| **gitleaks** | Secret scan on staged changes |
| **shellcheck** | Shell-script lint (auto-detects `*.sh` + shell shebangs) |
| **bandit** | Python SAST on `src/mypyskindose/` + `scripts/` (medium+ severity) |
| **doc-freshness** | `python scripts/check_doc_freshness.py` (broken links; stale-pattern warnings only) |
| **check-ignored-assets** | `python scripts/check_ignored_asset_files.py` (advisory: PNG/HTML outside `PlotOutputs/`) |
| **cleanup-old-backups** | `python scripts/cleanup_old_backups.py` (delete `backups/*.bak` older than 5 commits) |
| **license-notices** | `python scripts/check_licenses.py --check-notices` (blocks commit if `THIRD_PARTY_NOTICES.md` is stale) |

**Pre-push hook:**

| Hook | What it runs |
|---|---|
| **basedpyright** | Full-project type check (matches CI `typecheck` job; requires `.[dev,gui]`) |
| **semgrep** | OWASP Top 10 SAST (`p/owasp-top-ten`; needs network to fetch rules; `--metrics=off`) |
| **pip-audit** | Dependency vulnerability scan (`python scripts/audit_dependencies.py`; `uv audit` on `uv.lock` when `uv` >= 0.11.19 is available) |
| **check-changelog** | `python scripts/check_changelog.py` when `src/` or `tests/` change |

**Not in local hooks** (CI-only or manual): full pytest matrix, safety (CI when `SAFETY_API_KEY` set), license compliance (`--write-notices`), GUI smoke, `compileall`, `python -m build`.

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
| `bandit -c pyproject.toml -r src/mypyskindose scripts --severity-level medium` | Ubuntu `static-analysis` job (requires `.[dev]`) |
| `shellcheck run_gui.sh scripts/type_baseline.sh` | Ubuntu `static-analysis` job (requires `.[dev]`) |
| `semgrep --config=p/owasp-top-ten --error --metrics=off src scripts .github/workflows docs/source/conf.py` | Ubuntu `static-analysis` job (requires `.[dev]`) |
| `python scripts/audit_dependencies.py` | Ubuntu `static-analysis` job (requires `.[dev,gui]`) |
| `safety scan --detailed-output` | Ubuntu `static-analysis` job when `SAFETY_API_KEY` secret is set (skipped otherwise) |
| `python scripts/check_licenses.py` | Ubuntu `static-analysis` job (forbidden licenses; `--check-notices`) |
| pre-commit (local) | `.pre-commit-config.yaml` — commit: ruff, gitleaks, shellcheck, bandit, doc-freshness, backup cleanup; pre-push: basedpyright, semgrep, check-changelog |

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

Tracked in `dev-docs/plans/archive/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md` and `dev-docs/TO_DO.md`:

- Tabular input Phases 1–5 shipped; Qaelum/DoseMonitor/DoseWatch adapters remain stubs pending real export fixtures (`TABULAR_RDSR_INPUT_PLAN.md`, `FEATURE_INVENTORY.md`).
- Stale-pattern doc-freshness scan is advisory only (not yet CI-blocking before release).
- Execution plan template and lifecycle partially documented; see `TO_DO.md` § Documentation / plans.
