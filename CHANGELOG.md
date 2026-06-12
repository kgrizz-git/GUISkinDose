# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Version source of truth:** the package version in `pyproject.toml` (currently `25.1.1`).
This changelog tracks user- and maintainer-visible changes; bump `pyproject.toml` when releasing.

## [Unreleased]

### Added

- **Tabular input Phase 1** (2026-06-09): `src/mypyskindose/input_adapters/` package — shared loader, column mapper, registry, `normalized` schema adapter; handles CSV/TSV/XLSX with encoding fallback (UTF-8/BOM/cp1252), delimiter sniffing, decimal-comma normalization, and offset header detection. CLI flags `--input-schema`, `--sheet-name`, `--input-preview-only`. Python API `analyze_input_file()` and `preview_input_file()`. Architecture layer tests. Full unit test suite with six fixture variants.
- **Tabular input Phase 2** (2026-06-09): `generic_rdsr_like` schema adapter — maps `rdsr_parser()`-style columns to `rdsr_normalizer()` input and produces the normalized DataFrame; `--input-schema auto` with ≥0.20 margin scoring. `GENERIC_RDSR_PATTERNS` and `GENERIC_RDSR_COLUMN_NAMES` in `column_mapper.py`; `NORMALIZED_COLUMN_CANONICAL` for proper-case output matching `rdsr_normalizer()`. Test fixture `generic_rdsr_events.csv` (21-event Siemens AXIOM-Artis).
- **Tabular input Phase 3** (2026-06-10): `radimetrics` schema adapter in `input_adapters/radimetrics.py`; `RADIMETRICS_PATTERNS` and `RADIMETRICS_COLUMN_NAMES` in `column_mapper.py`; unit conversions (reference dose mGy→Gy, field area cm²→m², exposure mAs→µAs) with provenance tracking; unknown model warning (non-blocking); auto-detection support; synthetic fixture `radimetrics_events.csv` (5-event Siemens AXIOM-Artis); 8 new tests (46 total for input_adapters). GUI schema selector updated to include "Radimetrics CSV".
- **Tabular input Phase 4** (2026-06-10): `dosetrack` schema adapter in `input_adapters/dosetrack.py`; `DOSETRACK_PATTERNS` and `DOSETRACK_COLUMN_NAMES` in `column_mapper.py`; Equipment Name → Manufacturer/ModelName inference via `MODEL2MANUF` (`AXIOM-Artis`→Siemens, `Azurion`/`Allura Clarity`→Philips); `ffill()` for hierarchical DoseTrack row format; integer Plane Code → "Single Plane"/"Plane A"/"Plane B"; unit conversions (Air Kerma mGy→Gy, DAP Gy·cm²→Gy·m², Tube Current µA→mA); `CollimatedFieldArea_m2` derived from `DAP / (DoseRP * ((DSI-150)/DSD)²)` formula; Siemens filter thickness max=min; Philips semicolon-split Al;Cu filter thickness; Philips lat/lon swap warning; registered in registry with auto-detection support; synthetic fixture `dosetrack_events.csv` (5-event AXIOM-Artis); 10 new tests (56 total for input_adapters).
- **Vendor adapter stubs** (2026-06-10): `qaelum.py`, `dosemonitor.py`, `dosewatch.py` — each has empty `VENDOR_COLUMN_NAMES`/`VENDOR_PATTERNS` with `TODO` notes and an `adapt()` that raises `NotImplementedError` with step-by-step implementation instructions. Wired into registry for explicit `--input-schema` selection; excluded from auto-detection until column maps are populated. Qaelum, DoseMonitor, and DoseWatch documented as Phase 5+ placeholders in `TABULAR_RDSR_INPUT_PLAN.md` and `FEATURE_INVENTORY.md`.
- **Header-row detection fix** (2026-06-10): `detect_header_row` threshold changed from fraction-based (`matched/total_cells ≥ 0.05`) to absolute hit count (`matched_columns ≥ 5`). Fixes false-negative on exports with 100+ columns where few columns are in the known set. `_score_row` now also normalizes `known_names` before comparison so underscore-containing entries in `GENERIC_RDSR_COLUMN_NAMES` (e.g. `"distancesourcetodetector_mm"`) correctly match normalized cell values (`"distancesourcetodetector mm"`). `_score_schema` (auto-detection) is unaffected — it uses its own `.lower()`-only normalization.
- **Tabular input Phase 5** (2026-06-10): GUI upload tab now accepts `.csv`, `.tsv`, `.xlsx`, `.xlsm` in addition to `.dcm`; routes to `load_tabular()` helper; schema selector dropdown (Auto-detect / Normalized / Raw RDSR-like / Radimetrics CSV / DoseTrack XLSX/CSV); import preview panel showing schema, encoding, delimiter, header row index, column mapping table, warnings, and first 5 normalized events; **individual coordinate correction toggles** (Swap lateral ↔ longitudinal `Tx↔Tz`, Flip primary angle `Ap1×−1`, Flip secondary angle `Ap2×−1`) with tooltips, each its own inverse applied live to `state.rdsr_df`; **intelligent transform defaults** auto-set from detected manufacturer (GE Radimetrics and Philips DoseTrack auto-enable lat/lon swap) with override hint label; **XLSX sheet picker** shown only for multi-sheet files, re-parses on change without overwriting user transform choices; Calculate tab blocked on import errors; Data Table tab shows source filename and schema. Tabular provenance now preserved in JSON exports (`tabular_input` key) and HTML exports (HTML comment in `<head>`).
- **Vendor coordinate documentation**: new "Tabular input coordinate handling" section in `VENDOR_COORDINATE_SYSTEMS.md`; `TabularImportOptions` plan (Phase 3+) documented in `TABULAR_RDSR_INPUT_PLAN.md`; DoseTrack Philips lat/lon swap finding added.
- **Reference implementations saved**: `dev-docs/references/` now contains `dhen2714_radimetrics.py`, `dhen2714_dosetrack.py` (from `github.com/dhen2714/PySkinDose`), and `psdcalcrework_io_utils.py` (from private repo) with findings summary.

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

- Harness docs: document master vs execution vs archive plan conventions in `HARNESS_ENGINEERING.md`; add `dev-docs/plans/archive/` (basedpyright plan); sync `TO_DO.md` with shipped tabular Phases 3–5; update `dev-docs/index.md` catalog.
- Repository hygiene: stop tracking build artifacts (`dist/`), Jupyter checkpoint notebooks, legacy `phantom_data/old/` meshes, local `debug.json`, ad-hoc `_test_gui_import.py`, and duplicate `.windsurf/` rules; expand `.gitignore` for `PlotOutputs/`, coverage output, and local agent config.
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
