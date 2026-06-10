# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Version source of truth:** the package version in `pyproject.toml` (currently `25.1.1`).
This changelog tracks user- and maintainer-visible changes; bump `pyproject.toml` when releasing.

## [Unreleased]

### Added

- Harness docs: `TO_DO.md` cleanup (pending vs open questions vs completed); `FEATURE_INVENTORY.md` §0 harness/CI shipped features; GUI doc consolidation (`GUI_PLAN.md` §0 supersedes `UI_ANALYSIS.md`); `scripts/generate_ui_values.py` for auto-generated `UI_values.md`; `dev-docs/references/` stub; Phase 6 plan lifecycle closed.
- Harness docs: `check_doc_freshness.py` now scans `CHANGELOG.md` for `FEATURE_INVENTORY` contradictions; doc-gardening cadence documented in `HARNESS_ENGINEERING.md`.
- Harness CI: **basedpyright** `typecheck` job (strict — any type error fails); optional baseline helpers in `scripts/type_baseline.sh`; `[dev]` optional dependency.
- Harness CI: **gitleaks** secret scanning workflow on push/PR.
- Harness CI: **bandit** `bandit` job (Python SAST on `src/mypyskindose` + `scripts`; medium+ severity gate).
- Harness CI: **pip-audit** `dependency-audit` job (core + `[dev]` + `[gui]` extras; fails on known CVEs).
- Harness CI: **license compliance** — `scripts/check_licenses.py` in `dependency-audit` job; policy in `dev-docs/LICENSE_COMPLIANCE.md`; inventory in `dev-docs/THIRD_PARTY_NOTICES.md`.
- Harness local hooks: **pre-commit** config (commit: ruff, gitleaks, bandit, doc-freshness; pre-push: basedpyright).
- Harness Phase 5: GUI smoke tests (`tests/gui/`) with NiceGUI user simulation; `gui-smoke` CI job; `tests/scripts/launch_gui_headless.py`.
- Harness Phase 4: package layering documented in `CODEBASE_OVERVIEW.md`; structural layer tests in `tests/unittests/test_architecture_layers.py`.
- Harness Phase 3: `python -m build` in CI (`package-build` job on Ubuntu, Python 3.12); local full checks now match CI.
- Harness Phase 2: root `CHANGELOG.md`; `python -m compileall src/mypyskindose` in CI; GitHub Actions upgraded to current majors.
- Harness Phase 1: `scripts/check_doc_freshness.py` and Ubuntu CI job for broken internal markdown links and checkable `FEATURE_INVENTORY.md` contradictions.
- Harness Phase 0: `dev-docs/index.md` documentation catalog; expanded source-of-truth map in `dev-docs/HARNESS_ENGINEERING.md`; `design.md` renamed to `DESIGN.md`.

### Changed

- Type checking: resolved all 147 basedpyright errors; CI now runs strict `basedpyright` (no baseline). Optional incremental baseline workflow documented in `.basedpyright/README.md` with `scripts/type_baseline.sh`.
- Pre-commit: `cleanup-old-backups` hook removes `backups/*.bak` files last touched more than 5 commits ago; `backups/` added to `.gitignore`.
- Harness Phase 2: stop tracking generated `src/mypyskindose.egg-info/`; `.gitignore` covers egg-info and standard Python build artifacts.
- Harness Phase 2: CI `flake8` limited to syntax/fatal errors (`E9,F63,F7,F82`); style overlap with `ruff` (120-column) removed from CI.
- Harness Phase 2: `.github/workflows/ci.yml` and `release.yml` use `actions/checkout@v4` and `actions/setup-python@v5`.
- CI test matrix: full 3 OS × 4 Python on pull requests and `main` pushes only; other branch pushes run a single Ubuntu + Python 3.12 `build` cell (other jobs unchanged).
- Local hooks: **basedpyright** moved to pre-push only via pre-commit (`pre-commit install --hook-type pre-push`); removed manual `scripts/pre-push.sh`.

### Fixed

- Normalization settings: `update_translation_offset` and `update_rotation_direction` now apply vendor overrides from JSON/settings (previously no-ops when values were already initialized).
- Phantom: cylinder mesh resolution assertions run after resolution is assigned (basedpyright refactor had broken cylinder phantom creation).

## [25.1.1] - 2025-01-01

### Added

- MyPySkinDose fork baseline: peak skin dose estimation and 3D skin dose maps from fluoroscopic RDSR data.
- NiceGUI application (`python -m mypyskindose --mode gui`).

[Unreleased]: https://github.com/kgrizz-git/MyPySkinDose/compare/v25.1.1...HEAD
[25.1.1]: https://github.com/kgrizz-git/MyPySkinDose/releases/tag/v25.1.1
