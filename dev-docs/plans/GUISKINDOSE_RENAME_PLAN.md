# GUISkinDose Rename Plan

**Scope:** Rename the Python package from `mypyskindose` to `guiskindose` and the user-facing
brand from "MyPySkinDose" to "GUISkinDose".

**Scale:** ~250 files, ~2,400 `mypyskindose` occurrences, plus ~2,850 total variant occurrences
(including upstream `PySkinDose` attribution, which is intentionally preserved).

---

## Naming conventions

| Context | Old | New |
|---------|-----|-----|
| Python package / import path | `mypyskindose` | `guiskindose` |
| PyPI distribution name | `mypyskindose` | `guiskindose` |
| User-facing brand / display | "MyPySkinDose" | "GUISkinDose" |
| CLI invocation | `python -m mypyskindose` | `python -m guiskindose` |
| Logger root | `"mypyskindose"` | `"guiskindose"` |
| Config directory | `~/.mypyskindose/` | `~/.guiskindose/` |
| Config file | `.mypyskindose.local.json` | `.guiskindose.local.json` |
| Temp dir prefix | `mypyskindose-uploads` | `guiskindose-uploads` |
| Export temp prefix | `.mypyskindose-export-` | `.guiskindose-export-` |
| Default filenames | `mypyskindose_*.json` | `guiskindose_*.json` |
| HTML meta tag | `mypyskindose_version` | `guiskindose_version` |
| Environment variable | `MYPYSKINDOSE_SHOW_DEMO_PHANTOMS` | `GUISKINDOSE_SHOW_DEMO_PHANTOMS` |

### What stays as-is (upstream attribution)

All references to the upstream **PySkinDose** project (by `rvbCMTS`) are preserved:
- `PySkinDoseOutput` class name (it is the upstream's public API name)
- Fork attribution in `pyproject.toml`, `README.md`, `CONTRIBUTING.md`, `CITATION.cff`
- Historical `CHANGELOG.md` entries
- `dev-docs/FORK_MAINTAINER_GUIDE.md` references
- Upstream URLs (`github.com/rvbCMTS/PySkinDose`)
- `geom_calc.py` / `calculate_dose.py` normalization comments ("normalized for compliance with PySkinDose")
- `dev-docs/references/dhen2714_*.py` reference implementations

---

## Phases

### Phase 0 — Preparation (no code changes)

1. **Create a working branch** (`rename/guiskindose`).
2. **Verify CI is green** on `main` before branching.
3. **Snapshot the current state** — record the full `git log --oneline -5` and a `git diff --stat main` baseline.
4. **Decide on `PySkinDoseOutput`** — keep the upstream class name (recommended; it is a public API and the class is used pervasively in `format_export_data.py`, `analyze_data.py`, `export/`). If a rename is desired later, it should be a separate PR.

### Phase 1 — Source directory rename

**Single atomic step:**

1. `git mv src/mypyskindose src/guiskindose`

This immediately breaks all imports, which is expected. All subsequent phases fix the fallout.

### Phase 2 — Bulk import/require updates

Use `sed` or a scripted find-and-replace across the entire repo. Every occurrence of the
exact string `mypyskindose` in Python files (`.py`) must become `guiskindose` **except**:

- Upstream attribution comments mentioning "PySkinDose" (the upstream project name).
- `CHANGELOG.md` historical entries (these describe what happened under the old name).
- `dev-docs/plans/archive/` files (historical plans).
- `dev-docs/assessments/` files (historical assessments).
- `CITATION.cff` upstream reference entry (lines 26-27).

**Replacement patterns (Python files):**

| Old pattern | New pattern | Scope |
|-------------|-------------|-------|
| `from mypyskindose` | `from guiskindose` | All `.py` files |
| `import mypyskindose` | `import guiskindose` | All `.py` files |
| `"mypyskindose"` (logger, strings) | `"guiskindose"` | Logger names, string literals |
| `mypyskindose` in f-strings | `guiskindose` | Default filenames, error messages |
| `prog="mypyskindose"` | `prog="guiskindose"` | `cli_args.py` |
| `version("mypyskindose")` | `version("guiskindose")` | `export/payload.py` |
| `python -m mypyskindose` | `python -m guiskindose` | Docstrings, comments |
| `pip install mypyskindose` | `pip install guiskindose` | User-facing hints |
| `MYPYSKINDOSE_` | `GUISKINDOSE_` | Environment variables |

**Replacement patterns (non-Python files):**

| Old pattern | New pattern | Files |
|-------------|-------------|-------|
| `src/mypyskindose` | `src/guiskindose` | `pyproject.toml`, `MANIFEST.in`, `.gitignore`, `.pre-commit-config.yaml`, `scripts/*.py`, `run_gui.sh`, `run_gui.bat`, `build_documentation.bat` |
| `mypyskindose` in `pyproject.toml` | `guiskindose` | Package name, include/exclude, ruff per-file-ignores, basedpyright paths, bandit exclude |
| `"MyPySkinDose"` (display name) | `"GUISkinDose"` | `export/models.py:APP_NAME`, `gui/app.py`, `docs/source/conf.py`, `CITATION.cff:2,10`, `README.md` (selective) |
| `.mypyskindose` | `.guiskindose` | `.env.example`, `gui/window_prefs.py` |
| `mypyskindose_version` | `guiskindose_version` | `export/writers/html.py` HTML meta tag |

### Phase 3 — Documentation updates

#### 3a. Top-level Markdown

Update all `.md` files under the repo root that reference `mypyskindose`:

- `AGENTS.md` — package name, import examples, key file paths
- `README.md` — install command, import examples, description (keep upstream fork attribution)
- `CONTRIBUTING.md` — import examples
- `SECURITY.md` — package description
- `SUPPORT.md` — fork reference
- `PUBLISHING.md` — repository name
- `GOVERNANCE.md` — upstream credit stays

#### 3b. `dev-docs/` Markdown

Update all files under `dev-docs/` that reference `mypyskindose`:

- `CODEBASE_OVERVIEW.md` — import paths, file paths, class references
- `FEATURE_INVENTORY.md` — feature descriptions
- `VENDOR_COORDINATE_SYSTEMS.md` — import paths
- `ADDITIONAL_PHANTOMS.md` — import paths
- `FORK_MAINTAINER_GUIDE.md` — import paths (keep upstream attribution)
- `HARNESS_ENGINEERING.md` — validation commands, paths
- `AGENT_PLAYBOOK.md` — import paths
- `TO_DO.md` — current item references
- `INPUT_FIELD_REFERENCE.md` — source file paths
- `INPUT_SCHEMA_DETECTION.md` — source file paths
- `INPUT_DATA_FLOW_AND_OFFSETS.md` — source file paths
- `MYPYSKINDOSE_MIGRATION_STATUS.md` — rename title and references
- `info/PACKAGE_INSTALL.md` — install command, import paths
- `PRIVACY_AND_SENSITIVE_ASSETS.md` — path references
- `PRIVACY_INCIDENT_RESPONSE.md` — path references
- `RELEASES_AND_DISTRIBUTION.md` — path references
- `LICENSE_COMPLIANCE.md` — path references
- `PRIVACY_AND_SENSITIVE_ASSETS.md` — path references
- All files under `plans/` (non-archive) — import paths, file paths
- All files under `references/` — import paths
- All JSON metadata files:
  - `approved_asset_inventory.json` — ~143 phantom data paths
  - `approved_asset_inventory.md` — ~143 phantom data paths
  - `feature_doc_matrix.json` — ~32 source paths
  - `help_registry.json` — ~12 GUI file paths
  - `privacy_admission_policy.json` — path reference
  - `ui_copy.json` — if any paths referenced
  - `glossary.json` — if any references

**Do NOT update** files under `plans/archive/` or `assessments/` — these are historical.

#### 3c. GUI help files

Update `docs/source/gui_help/*.md` (5 source files). The mirrored copies under
`src/guiskindose/gui/help/` will be updated by the `scripts/sync_gui_help.py` script after the
source files are edited.

#### 3d. Sphinx docs

The RST files under `docs/source/` are autogenerated and named after the package:

- `docs/source/mypyskindose.rst` → `docs/source/guiskindose.rst`
- `docs/source/mypyskindose.calculate_dose.rst` → `docs/source/guiskindose.calculate_dose.rst`
- `docs/source/mypyskindose.helpers.rst` → `docs/source/guiskindose.helpers.rst`
- `docs/source/mypyskindose.plotting.rst` → `docs/source/guiskindose.plotting.rst`
- `docs/source/mypyskindose.settings.rst` → `docs/source/guiskindose.settings.rst`

After the source directory rename, regenerate with:
```bash
python -m sphinx.ext.apidoc -o docs/source src/guiskindose
```

Update `docs/source/conf.py`: `project = "GUISkinDose"`.
Update `docs/source/index.rst` if it references the old module name.
Update `docs/source/modules.rst` if it references the old module name.
Update `docs/source/user/install.md` and `docs/source/user/user_guide.md`.

#### 3e. `CITATION.cff`

- Line 2: `title: GUISkinDose`
- Line 10: `name: "GUISkinDose contributors"`
- Lines 11-12: Update repository URLs if the repo is renamed
- Keep lines 26-27 (upstream PySkinDose reference) unchanged

### Phase 4 — Tests

All test files under `tests/` use `from mypyskindose.X import Y` imports. Bulk-replace:

- `tests/unittests/` (~70 files, ~500 imports)
- `tests/gui/` (~20 files)
- `tests/integrationtests/` (5 files)
- `tests/manual_tests/` (9 .py files + 6 .ipynb notebooks)
- `tests/scripts/` (1 file)
- `tests/calculate_dose_recursion_helpers.py`

For `.ipynb` notebooks, the replacement must target cell source strings containing
`mypyskindose`. Use a JSON-aware tool or script to edit notebook cells.

**Special test considerations:**

- `test_architecture_layers.py` — contains module name strings in layer rules; update those strings.
- `test_debug_logging.py` — logger name assertions; update `"mypyskindose"` → `"guiskindose"`.
- `test_kerma_correction.py` — logger name assertions.
- `test_check_doc_freshness.py` — path strings in test data.
- `test_check_file_sizes.py` — path string.
- `test_check_ignored_asset_files.py` — path strings.
- `test_check_ui_copy.py` — path string.
- `test_sync_gui_help.py` — path strings.

### Phase 5 — Scripts

Update all scripts under `scripts/`:

- `scripts/sync_gui_help.py` — path constants (`"src/mypyskindose/gui/help"` → `"src/guiskindose/gui/help"`)
- `scripts/generate_ui_values.py` — path constant (`"src/mypyskindose/gui/styles.py"`)
- `scripts/check_gui_test_placement.py` — docstring references
- `scripts/check_ui_copy.py` — path constant
- `scripts/check_doc_freshness.py` — any path references
- `scripts/check_licenses.py` — any path references
- `scripts/run_hounddog_advisory.py` — temp dir prefix
- `scripts/run_semgrep_privacy.py` — any references
- `scripts/phantom_gen/validate_phantom.py` — import + instantiation
- Other `scripts/phantom_gen/*.py` files — imports

### Phase 6 — Launcher and config files

- `run_gui.sh` — all `mypyskindose` references (12 occurrences)
- `run_gui.bat` — all `mypyskindose` references (12 occurrences)
- `build_documentation.bat` — apidoc output path
- `.env.example` — env var names and config path references
- `.pre-commit-config.yaml` — bandit hook `files` regex, help sync hook name
- `.gitignore` — path patterns
- `sonar-project.properties` — project key/name (if repo is renamed)

### Phase 7 — String literal audit

Beyond bulk find-and-replace, audit these user-facing string literals individually:

1. **`export/models.py:34`** — `APP_NAME = "GUISkinDose"`
2. **`gui/tabs/export.py`** — default filenames, pip install hint
3. **`gui/tabs/data.py`** — default export filename
4. **`gui/app.py`** — window title, welcome message
5. **`gui/window_prefs.py`** — env var name, config paths
6. **`gui/upload_temp_files.py`** — temp dir name
7. **`gui/io_helpers.py`** — HTML comment marker
8. **`safe_output.py`** — temp file prefix
9. **`privacy.py`** — path detection string (`"mypyskindose" in parts`)
10. **`export/writers/html.py`** — HTML meta tag name
11. **`__init__.py`** — print message
12. **`__main__.py`** — module docstring
13. **`cli_args.py`** — argparse `prog` and description
14. **`debug.py`** — `_LOGGER_ROOT` constant
15. **All `logging.getLogger("mypyskindose...")` calls** — update root and sub-loggers

### Phase 8 — Validation

1. **Lint:** `pre-commit run --all-files`
2. **Type check:** `pre-commit run --hook-stage pre-push --all-files` (basedpyright)
3. **Unit tests:** `pytest tests/unittests/ -x -q`
4. **GUI tests:** `pytest tests/gui/ -x -q`
5. **Integration tests:** `pytest tests/integrationtests/ -x -q`
6. **Import smoke:** `python -c "from guiskindose import PyskindoseSettings; print('OK')"`
7. **Module invocation:** `python -m guiskindose --help`
8. **Version check:** `python -c "from importlib.metadata import version; print(version('guiskindose'))"`
9. **Logger check:** `python -c "import logging; print(logging.getLogger('guiskindose').name)"`
10. **Sphinx build:** `python -m sphinx -b html docs/source docs/_build/html` (if docs are in scope)
11. **Grep audit:** `rg -c mypyskindose src/ tests/ scripts/` — should return zero hits
12. **Grep audit (non-historical):** `rg mypyskindose --type py` — should return zero hits outside `CHANGELOG.md`, `plans/archive/`, `assessments/`

### Phase 9 — Pre-commit hooks

After the rename, verify that pre-commit hooks still work:

- **bandit** hook `files` regex in `.pre-commit-config.yaml` must match `src/guiskindose`
- **GUI help sync** hook name must reference the new path
- **`commit-msg`** hook — verify it resolves correctly (uses `resolve_commit_message_path`)
- **`pre-push`** hooks (basedpyright, gui-test-placement) — verify they find the correct package

### Phase 10 — Documentation freshness

Run the doc-freshness checks:

```bash
python scripts/check_doc_freshness.py
python scripts/check_file_sizes.py
python scripts/check_help_registry.py
python scripts/check_ui_copy.py
python scripts/sync_gui_help.py  # re-mirror GUI help files
python scripts/check_doc_pruning.py
```

Update `dev-docs/index.md` to reference the new plan name.

---

## Risk mitigation

### Backward compatibility

- **No `mypyskindose` alias package** — this is a hard rename. Users must update their imports.
  A compatibility shim (`mypyskindose` that re-exports `guiskindose`) is not planned; it would
  add maintenance burden and confuse the namespace. If backward compat is later deemed
  necessary, it can be added as a separate small package or a `__init__.py` re-export hack.

- **PyPI `mypyskindose` name** — the old PyPI name will remain with whatever version was last
  published. The new package publishes as `guiskindose`. Users must `pip install guiskindose`
  instead of `pip install mypyskindose`.

### Importlib.metadata

`export/payload.py:40` calls `version("mypyskindose")`. After rename, this must call
`version("guiskindose")`. If the package is not installed (e.g. running from source), this
raises `PackageNotFoundError`. The existing try/except around this call handles that; verify
it still works.

### Sphinx autodoc

The RST files are generated by `sphinx-apidoc` and named after the package. After renaming the
source directory, the old RST files become stale. Delete them and regenerate. The
`build_documentation.bat` script runs apidoc — update its output path.

### Pre-commit hook scope

The bandit hook in `.pre-commit-config.yaml` uses a `files:` regex scoped to
`^(src/mypyskindose|scripts)/`. This must become `^(src/guiskindose|scripts)/`.

### `.gitignore` patterns

Patterns like `src/mypyskindose/.ipynb_checkpoints/` must become
`src/guiskindose/.ipynb_checkpoints/`. The legacy `*/pyskindose.egg*` pattern can be kept or
dropped (it excludes the old upstream egg-info).

### Temporary backward-compat notes

If there is a transition period where users may have both old and new installed, add a note
in `CHANGELOG.md` and `README.md` documenting the rename and migration steps.

---

## Execution order

The recommended execution order minimizes broken intermediate states:

1. Phase 0 — Branch and snapshot
2. Phase 1 — `git mv src/mypyskindose src/guiskindose`
3. Phase 2 — Bulk Python import/string replace (all `.py` files)
4. Phase 4 — Bulk test file replace (all `tests/**/*.py`)
5. Phase 5 — Scripts replace
6. Phase 6 — Config/launcher replace
7. Phase 3 — Documentation updates
8. Phase 7 — String literal audit (manual review)
9. Phase 8 — Validation (run all checks)
10. Phase 9 — Pre-commit hook verification
11. Phase 10 — Documentation freshness

Each phase should be a separate commit for clean `git bisect` if something breaks.

### Suggested commit sequence

1. `refactor: rename src/mypyskindose → src/guiskindose (directory only)`
2. `refactor: update all Python imports mypyskindose → guiskindose`
3. `refactor: update logger names and string literals`
4. `refactor: update test imports and assertions`
5. `refactor: update scripts paths and references`
6. `refactor: update config files, launchers, .gitignore`
7. `docs: update all documentation for guiskindose rename`
8. `docs: regenerate Sphinx autodoc RST files`
9. `chore: final audit — zero mypyskindose hits outside historical files`

---

## Open questions

1. **`PySkinDoseOutput` class rename?** — The upstream class name is used in ~50 places. Renaming
   it to `GUISkinDoseOutput` would be a larger change and break the public API. Recommendation:
   defer to a separate PR if desired.

2. **Repository rename on GitHub?** — If the GitHub repo is renamed from `MyPySkinDose` to
   `GUISkinDose`, update `sonar-project.properties`, `CITATION.cff` URLs, and all GitHub links
   in docs. This can happen independently of the package rename.

3. **PyPI name reservation** — Confirm `guiskindose` is available on PyPI before starting.

4. **Notebook execution** — The 6 `.ipynb` files under `tests/manual_tests/` contain
   `mypyskindose` imports in cell source. These need JSON-level editing. Verify notebooks
   still execute after the rename.

5. **`dev-docs/MYPYSKINDOSE_MIGRATION_STATUS.md`** — This file tracks migration status. It
   should be renamed to `dev-docs/GUISKINDOSE_MIGRATION_STATUS.md` and its content updated.
