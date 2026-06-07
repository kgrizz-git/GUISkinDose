# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Version source of truth:** the package version in `pyproject.toml` (currently `25.1.1`).
This changelog tracks user- and maintainer-visible changes; bump `pyproject.toml` when releasing.

## [Unreleased]

### Added

- Harness CI: **basedpyright** `typecheck` job with `.basedpyright/baseline.json` (fails on new errors only); `[dev]` optional dependency.
- Harness CI: **gitleaks** secret scanning workflow on push/PR.
- Harness CI: **pip-audit** `dependency-audit` job (core + `[dev]` + `[gui]` extras; fails on known CVEs).
- Harness local hooks: **pre-commit** config (ruff, gitleaks, doc-freshness on `git commit`).
- Harness Phase 5: GUI smoke tests (`tests/gui/`) with NiceGUI user simulation; `gui-smoke` CI job; `tests/scripts/launch_gui_headless.py`.
- Harness Phase 4: package layering documented in `CODEBASE_OVERVIEW.md`; structural layer tests in `tests/unittests/test_architecture_layers.py`.
- Harness Phase 3: `python -m build` in CI (`package-build` job on Ubuntu, Python 3.12); local full checks now match CI.
- Harness Phase 2: root `CHANGELOG.md`; `python -m compileall src/mypyskindose` in CI; GitHub Actions upgraded to current majors.
- Harness Phase 1: `scripts/check_doc_freshness.py` and Ubuntu CI job for broken internal markdown links and checkable `FEATURE_INVENTORY.md` contradictions.
- Harness Phase 0: `dev-docs/index.md` documentation catalog; expanded source-of-truth map in `dev-docs/HARNESS_ENGINEERING.md`; `design.md` renamed to `DESIGN.md`.

### Changed

- Harness Phase 2: stop tracking generated `src/mypyskindose.egg-info/`; `.gitignore` covers egg-info and standard Python build artifacts.
- Harness Phase 2: CI `flake8` limited to syntax/fatal errors (`E9,F63,F7,F82`); style overlap with `ruff` (120-column) removed from CI.
- Harness Phase 2: `.github/workflows/ci.yml` and `release.yml` use `actions/checkout@v4` and `actions/setup-python@v5`.

## [25.1.1] - 2025-01-01

### Added

- MyPySkinDose fork baseline: peak skin dose estimation and 3D skin dose maps from fluoroscopic RDSR data.
- NiceGUI application (`python -m mypyskindose --mode gui`).

[Unreleased]: https://github.com/kgrizz-git/MyPySkinDose/compare/v25.1.1...HEAD
[25.1.1]: https://github.com/kgrizz-git/MyPySkinDose/releases/tag/v25.1.1
