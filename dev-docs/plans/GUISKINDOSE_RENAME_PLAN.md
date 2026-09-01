# GUISkinDose Rename Plan

**Scope:** In-repo rename of the Python package from `mypyskindose` to `guiskindose` and the
user-facing brand from "MyPySkinDose" to "GUISkinDose".

**Does not include:** GitHub repository rename, PyPI first publish, fixture sanitization, or
Trusted Publishing. Those stay in
[GUISKINDOSE_PRIVACY_REPUBLICATION_PLAN.md](GUISKINDOSE_PRIVACY_REPUBLICATION_PLAN.md)
(Phases 5B–7). This file is the mechanical-rename execution plan that republication Phase 5A
points at.

**Scale (re-count immediately before execution):** git-tracked files containing `mypyskindose`,
plus upstream `PySkinDose` attribution lines (intentionally preserved). Snapshot from plan
authoring was ~320 files / ~2,140 matching lines; that count drifts as other work lands.

---

## Ownership vs the republication plan

| Work | Owner |
|------|--------|
| `src/` directory rename, imports, tests, scripts, CI paths, docs brand strings, config migration, stale-brand check | **This plan** |
| `[project.scripts]` `guiskindose` console command (new; today only `python -m`) | **This plan** (identity) |
| Wheel/sdist clean-install verification, TestPyPI, version-line decision, Trusted Publishing | Republication Phase 5B |
| NOTICE/provenance, GitHub fork rename, fork-banner preservation | Republication Phases 5C and 7 |
| DICOM/tabular sanitization and scanner gates | Republication Phases 1–4, 6 |

Do not re-list replacement tables in the republication plan. If the two documents disagree,
this file wins for mechanical rename; republication wins for publication and GitHub rename.

---

## Naming conventions

| Context | Old | New |
|---------|-----|-----|
| Python package / import path | `mypyskindose` | `guiskindose` |
| PyPI distribution name | `mypyskindose` | `guiskindose` |
| User-facing brand / display | "MyPySkinDose" | "GUISkinDose" |
| CLI invocation | `python -m mypyskindose` | `python -m guiskindose` |
| Console script (new) | *(none)* | `guiskindose` via `[project.scripts]` |
| Logger root | `"mypyskindose"` | `"guiskindose"` |
| Config directory | `~/.mypyskindose/` | `~/.guiskindose/` (migrate; do not hard-cut) |
| Config file | `.mypyskindose.local.json` | `.guiskindose.local.json` (migrate) |
| Temp dir prefix | `mypyskindose-uploads` | `guiskindose-uploads` |
| Export temp prefix | `.mypyskindose-export-` | `.guiskindose-export-` |
| Semgrep / HoundDog temp prefixes | `mypyskindose-semgrep-`, `mypyskindose-hounddog-` | `guiskindose-semgrep-`, `guiskindose-hounddog-` |
| Default filenames | `mypyskindose_*.json` | `guiskindose_*.json` |
| HTML comment marker | `mypyskindose:tabular_input` | `guiskindose:tabular_input` |
| HTML meta tag | `mypyskindose_version` | `guiskindose_version` |
| Environment variable | `MYPYSKINDOSE_SHOW_DEMO_PHANTOMS` | `GUISKINDOSE_SHOW_DEMO_PHANTOMS` (keep reading the old name) |
| GitHub URLs / Sonar project key | `kgrizz-git/MyPySkinDose` | **Only after** the GitHub/SonarCloud projects are actually renamed |

### What stays as-is (upstream attribution and Semgrep IDs)

Preserve all references to upstream **PySkinDose** (`rvbCMTS`): `PySkinDoseOutput`, fork
attribution, historical `CHANGELOG.md` entries, `FORK_MAINTAINER_GUIDE.md`, upstream URLs,
normalization comments, and `dev-docs/references/dhen2714_*.py`.

**Semgrep rule IDs stay `mypyskindose-*`.** Rename the rules file to
`.semgrep/guiskindose-privacy.yml` and update `scripts/run_semgrep_privacy.py` plus
`tests/unittests/test_privacy_semgrep_rules.py` `_RULES`. Do **not** rewrite `# nosemgrep:
mypyskindose-*` comments or test assertions of those check IDs.

The YAML `paths.include` filters (not exclusions) must move with the package:

- `src/mypyskindose/gui/tabs/data.py`
- `src/mypyskindose/gui/tabs/export.py`
- `src/mypyskindose/export/writers/**`
- `src/mypyskindose/plotting/create_dose_map_plot.py`
- `src/mypyskindose/gui/tabs/**`
- `src/mypyskindose/gui/widgets/**`
- `src/mypyskindose/gui/upload_temp_files.py`

`test_privacy_semgrep_rules.py` writes fixtures at `src/mypyskindose/gui/tabs/export.py`
relative to a temp root so those includes match. Update that fixture path to
`src/guiskindose/...` in the same commit as the YAML includes.

Treat `dev-docs/COORD_TRANSFORM_COMPARISON.md` as historical: keep "MyPySkinDose" as the
name of this fork in that comparison. At execution time add one sentence that the current
product name is GUISkinDose; do not bulk-replace the table.

---

## Config and env migration (required)

`gui/window_prefs.py` persists window geometry, onboarding dismissal, and demo-mesh visibility
under `~/.mypyskindose/gui.json`. A hard cut to `~/.guiskindose/` would look like a first-run
reset.

Required behavior:

1. Prefer `~/.guiskindose/` and `.guiskindose.local.json` when they exist.
2. If the new dir/file is absent, read the old path privately (no raw-path logging) and write
   subsequent saves to the new path.
3. `show_demo_phantoms_enabled` must accept `GUISKINDOSE_SHOW_DEMO_PHANTOMS` first, then
   `MYPYSKINDOSE_SHOW_DEMO_PHANTOMS`, then `.env` / local JSON / `gui.json` as today.
4. Do not delete the old directory from the user's home as part of this change.

---

## Re-count before execution

If **any** other work lands on `main` (or this branch is rebased) before implementation, re-run
the inventories below and refresh the file lists in this plan. Do not trust the authoring-time
counts or line numbers.

```bash
rg -l mypyskindose --glob '!dev-docs/plans/archive/**' --glob '!dev-docs/assessments/**'
rg -l MyPySkinDose --glob '!dev-docs/plans/archive/**' --glob '!dev-docs/assessments/**'
rg MYPYSKINDOSE_ src tests scripts pyproject.toml .env.example
rg -l 'from mypyskindose|import mypyskindose|patch\("mypyskindose|import_module\("mypyskindose|__import__\("mypyskindose' tests
```

Also re-check:

- `git grep -n 'src/mypyskindose'` in `.github/`, `pyproject.toml`, `MANIFEST.in`,
  `.pre-commit-config.yaml`, `.phi-scanner.yml`, `.phi-scanbaseline`,
  `dev-docs/approved_asset_inventory.json`, `dev-docs/help_registry.json`,
  `dev-docs/feature_doc_matrix.json`, `dev-docs/privacy_admission_policy.json`
- New `# nosemgrep: mypyskindose-*` comments (keep IDs)
- New `patch("mypyskindose…")` / `importlib.import_module("mypyskindose…")` call sites
- Whether `guiskindose` is still free on PyPI and TestPyPI
- Whether hashed DICOM/STL paths in the approved-asset inventory still match HEAD (privacy
  admission may treat `git mv` of those binaries as new paths even when hashes are unchanged)
- `.phi-scanbaseline` expiry (currently 2026-10-14) — regenerate after path updates
- `docs/source/conf.py` `release` vs `pyproject.toml` version (already drifted to `25.1.1` vs
  `25.2.0`; bump both together with the rename version)
- Active plans under `dev-docs/plans/` that gained new `src/mypyskindose` paths

---

## Phases

### Phase 0 — Preparation (no code changes)

1. Create or update working branch (`rename/guiskindose`).
2. Verify CI is green on the merge base.
3. Re-count inventories (section above). Record `git log --oneline -5` and `git diff --stat main`.
4. Confirm `guiskindose` is available on PyPI/TestPyPI (this fork has **not** published
   `mypyskindose` yet — see [RELEASES_AND_DISTRIBUTION.md](../RELEASES_AND_DISTRIBUTION.md)).
5. Keep `PySkinDoseOutput` (public upstream API). A later rename is a separate PR.
6. Decide the first GUISkinDose version in `pyproject.toml` (breaking identity change; do not
   ship it as a silent patch). Record the choice in `CHANGELOG.md` Unreleased before merge.

### Phase 1 — Source directory rename

`git mv src/mypyskindose src/guiskindose`

This breaks imports until Phase 2. **Commit Phase 1 and Phase 2 together** so `main` never
contains an unbuildable tree. Later phases may be separate commits.

After Phase 2, smoke: `python -c "import guiskindose"` from an editable install.

### Phase 2 — Bulk import/require updates

Replace the exact string `mypyskindose` in `.py` files **except**:

- Upstream attribution mentioning "PySkinDose"
- Historical `CHANGELOG.md` entries (Unreleased/migration notes **are** updated)
- `dev-docs/plans/archive/` and `dev-docs/assessments/`
- `CITATION.cff` upstream reference (lines 26–27)
- **Semgrep rule IDs and `# nosemgrep: mypyskindose-*` comments**
- Test assertions of those rule IDs (`test_privacy_semgrep_rules.py`)
- `dev-docs/COORD_TRANSFORM_COMPARISON.md` historical table cells (add a current-name sentence)

A naive `sed` of every `mypyskindose` token **will break privacy suppressions**. Prefer
pattern-limited replacements (`from mypyskindose`, `import mypyskindose`, path prefixes,
logger names) plus a manual pass for leftovers.

| Old pattern | New pattern | Scope |
|-------------|-------------|-------|
| `from mypyskindose` | `from guiskindose` | All `.py` files |
| `import mypyskindose` | `import guiskindose` | All `.py` files |
| `"mypyskindose"` (logger, strings) | `"guiskindose"` | Logger names, string literals — not rule IDs |
| `prog="mypyskindose"` | `prog="guiskindose"` | `cli_args.py` |
| `version("mypyskindose")` | `version("guiskindose")` | `export/payload.py` |
| `python -m mypyskindose` | `python -m guiskindose` | Docstrings, comments |
| `__import__("mypyskindose` | `__import__("guiskindose` | Dynamic imports |
| `import_module("mypyskindose` | `import_module("guiskindose` | `test_multi_exam.py` |
| `patch("mypyskindose.` | `patch("guiskindose.` | Unit/GUI tests |
| `MYPYSKINDOSE_` | keep as fallback; add `GUISKINDOSE_` | `window_prefs.py` |

Non-Python: `src/mypyskindose` → `src/guiskindose` in `pyproject.toml` (including
`[tool.setuptools.packages.find] include = ["guiskindose*"]` — missing this ships an empty
wheel), `MANIFEST.in`, `.gitignore`, `.pre-commit-config.yaml`, scripts, launchers,
`build_documentation.bat`, `.phi-scanner.yml`, JSON metadata, `privacy_admission_policy.json`.

### Phase 3 — Documentation updates

#### 3a. Top-level Markdown

`AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`, `PUBLISHING.md`,
`GOVERNANCE.md`, **`CODE_OF_CONDUCT.md`** (GitHub advisory URL). Keep upstream fork credit.
Rewrite `github.com/kgrizz-git/MyPySkinDose` **only if** the GitHub repo has been renamed;
otherwise leave those URLs (GitHub will redirect later).

#### 3b. `dev-docs/` Markdown

Update current (non-archive, non-assessment) docs that reference the **package path or live
brand**, including: `CODEBASE_OVERVIEW.md`, `FEATURE_INVENTORY.md`, `VENDOR_COORDINATE_SYSTEMS.md`,
`ADDITIONAL_PHANTOMS.md`, `FORK_MAINTAINER_GUIDE.md`, `HARNESS_ENGINEERING.md`, `AGENT_PLAYBOOK.md`,
`TO_DO.md`, `index.md`, `INPUT_*.md`, `MYPYSKINDOSE_MIGRATION_STATUS.md` (rename the file to
`GUISKINDOSE_MIGRATION_STATUS.md`), `info/PACKAGE_INSTALL.md`, privacy/release/license docs,
non-archive `plans/`, `references/`, and JSON metadata (`approved_asset_inventory.*`,
`feature_doc_matrix.json`, `help_registry.json`, `privacy_admission_policy.json`).

**Do not bulk-update** `plans/archive/`, `assessments/`, or `backups/`.
**Do not bulk-replace** `COORD_TRANSFORM_COMPARISON.md` (historical comparison; add one
current-name sentence).

#### 3c–3e. GUI help, Sphinx, CITATION

Edit `docs/source/gui_help/*.md` then `scripts/sync_gui_help.py`.
Delete `docs/source/mypyskindose*.rst`, regenerate with `sphinx-apidoc -o docs/source src/guiskindose`.
Update `docs/source/conf.py` (`project = "GUISkinDose"` **and** `release` to match
`pyproject.toml`), `index.rst`, `modules.rst`, user install/guide, getting-started notebook.
`CITATION.cff` title/contributor name; keep upstream reference; GitHub URLs only if the repo
is renamed.

### Phase 4 — Tests (update existing)

Bulk-replace imports under `tests/`. Special cases:

- `test_architecture_layers.py` — `PACKAGE_ROOT` and forbidden-prefix strings
- `test_debug_logging.py`, `test_kerma_correction.py` — logger names
- `test_window_prefs.py` — `config_path().parent.name == ".mypyskindose"` plus migration tests
- `test_privacy.py` — logger names; assert `guiskindose/privacy.py` stripping; keep recognizing
  `mypyskindose` in `Path.parts` as a fallback
- `test_privacy_semgrep_rules.py` — rules **filename** and fixture **path**; **keep** check IDs
- `test_privacy_admission.py` — negative-control path `src/mypyskindose/beam_class.py`
- `test_multi_exam.py` — `importlib.import_module("mypyskindose.analyze_data")`
- `tests/gui/test_upload_builders_coverage.py` — `__import__("mypyskindose.gui.helpers", ...)`
- `tests/gui/test_multi_exam_gui.py` — `patch("mypyskindose.analyze_data…")`
- `tests/gui/test_rdsr_unit_error.py` — Path fragment and `MyPySkinDose` error text
- Brand assertions: `test_gui_smoke.py`, `test_export_docx.py`, `test_input_adapters.py`,
  `test_export_data.py` (`mypyskindose:tabular_input` bytes)
- Notebooks under `tests/manual_tests/notebook_tests/` (JSON-aware cell edits)

### Phase 4b — Tests to **add** (not only update)

1. **Stale-brand allowlist check** — pytest or `scripts/check_stale_brand.py` that fails if
   `mypyskindose` / `MyPySkinDose` / `MYPYSKINDOSE_` appear outside an explicit allowlist:
   historical changelog sections, `plans/archive/`, `assessments/`, Semgrep rule IDs,
   `# nosemgrep: mypyskindose-*`, upstream PySkinDose attribution, this plan, the
   republication plan, `COORD_TRANSFORM_COMPARISON.md`, and `GUISKINDOSE_MIGRATION_STATUS.md`
   migration examples. Wire it into pre-commit and CI. A one-shot `rg` in Phase 8 is not enough.
2. **Config migration** — old `gui.json` / env var still honored when the new path is absent;
   new path wins when both exist; saves go to the new path.
3. **Packaging smoke** — `importlib.metadata.version("guiskindose")`, `python -m guiskindose
   --help`, console script `guiskindose --help`, logger root, and load `settings_example.json`
   plus one phantom STL from a **wheel install** (not the editable checkout).
4. **User-facing literals** — `APP_NAME == "GUISkinDose"`, HTML meta `guiskindose_version`,
   HTML comment `guiskindose:tabular_input`.

### Phase 5 — Scripts

`sync_gui_help.py`, `generate_ui_values.py`, `check_ui_copy.py`, `check_doc_freshness.py`,
`check_licenses.py` (`PROJECT_NAME`), `run_hounddog_advisory.py`, `run_semgrep_privacy.py`
(rules path **and** `mypyskindose-semgrep-` temp prefix), `run_sonarqube_local.py`,
`phantom_gen/*`, `check_gui_test_placement.py`. Gitignored `scripts/scratch_*` need not be
edited.

### Phase 6 — Launcher, config, and CI

`run_gui.sh` / `run_gui.bat`, `build_documentation.bat`, `.env.example`, **`.envrc`** (comment
brand only), `.pre-commit-config.yaml`, `.gitignore`, `uv.lock` (`uv lock` after
`pyproject.toml`; do not `--upgrade` as part of the rename), `.phi-scanner.yml`, regenerate
`.phi-scanbaseline`, `.github/workflows/ci.yml` coverage/bandit/compileall paths.

**Do not** change `sonar.projectKey` / `sonar.projectName` until the SonarCloud project is
renamed to match; a key change without that UI rename breaks `sonar-scan`. GitHub issue
templates: update `import mypyskindose` instructions and brand strings; leave
`github.com/kgrizz-git/MyPySkinDose` links until the GitHub repo is renamed.

Add `[project.scripts] guiskindose = "guiskindose.__main__:cli"` (extract a `cli()` from
`__main__.py` if needed). Republication Phase 5B still verifies the wheel exposes it.

### Phase 7 — String literal audit

Manual pass of `APP_NAME`, export filenames, window title, config paths, temp prefixes,
`privacy.py` path detection (recognize **both** `guiskindose` and `mypyskindose` in
`Path.parts`), HTML meta, argparse `prog`, `_LOGGER_ROOT`, ReadTheDocs URL only if the RTD
project is renamed (`mypyskindose.readthedocs.io` otherwise). Brand strings listed in the
previous revision of this plan remain in scope (`cli_args.py`, `rdsr_normalizer.py`,
`radimetrics.py`, `export/payload.py`, GUI module docstrings).

### Phase 8 — Validation

Lint, basedpyright, unit/GUI/integration tests, import/`-m`/`version()`/logger smokes, Sphinx
if docs are in the PR, **plus** the new stale-brand check and a wheel install smoke.

Grep is **allowlisted**, not zero-hit:

```bash
rg mypyskindose src tests scripts pyproject.toml MANIFEST.in .github
```

Allowed leftovers: Semgrep rule IDs, `# nosemgrep: mypyskindose-*`, and (until GitHub/Sonar/RTD
rename) those hostnames. Everything else in `src/`, `tests/`, `scripts/` is a defect.

### Phase 9 — Pre-commit hooks

Bandit `files:` regex `^(src/guiskindose|scripts)/`, GUI help sync hook path, `commit-msg`
resolution, pre-push basedpyright/gui-test-placement against the new package.

### Phase 10 — Documentation freshness and release notes

```bash
python scripts/check_doc_freshness.py
python scripts/check_file_sizes.py
python scripts/check_help_registry.py
python scripts/check_ui_copy.py
python scripts/sync_gui_help.py
python scripts/check_doc_pruning.py
python scripts/generate_ui_values.py
```

Unreleased `CHANGELOG.md` must document the breaking rename, import/CLI substitutions, config
migration, absence of a `mypyskindose` shim, and that this fork had not published the old name
to PyPI. Rename `MYPYSKINDOSE_MIGRATION_STATUS.md` and add a short migration section to
`README.md`.

---

## Risk mitigation

### Backward compatibility

No `mypyskindose` alias package. Users update imports. Config/env migration (above) is the only
compatibility shim.

This fork has not published `mypyskindose` to PyPI. First publish should be `guiskindose`. If a
third party occupies that name, stop and re-decide before merging.

### Importlib.metadata and empty wheels

`export/payload.py` `version("guiskindose")` already has try/except for `PackageNotFoundError`.
`[tool.setuptools.packages.find] include` **must** be `guiskindose*` or the wheel contains no
package. Verify with a non-editable install, not `pip install -e .`.

### Sphinx autodoc

Delete `docs/source/mypyskindose*.rst` then regenerate. Update
`docs/source/getting_started/getting_started.ipynb`.

### Privacy admission of moved binaries

`git mv` of STL/DICOM changes inventory **paths** with unchanged hashes. Update
`approved_asset_inventory.json` in the same commit. If admission treats the new path as a new
asset, run the documented local DICOM/image review route rather than force-adding.

### Pre-commit and gitignore

Bandit files regex and `.gitignore` package paths as in Phase 6. Keep or drop
`*/pyskindose.egg*`. Regenerate `src/guiskindose.egg-info/` via `pip install -e .` rather than
renaming egg-info by hand.

---

## Execution order and commits

1. Phase 0 — inventories and version decision
2. Phases 1+2 — **one commit** (`git mv` + Python imports/strings except rule IDs)
3. Phase 4 + 4b — tests (existing updates + new checks)
4. Phase 5 — scripts
5. Phase 6 — config/launchers/CI (GitHub/Sonar URLs gated)
6. Phases 3, 7, 10 — docs, audit, freshness, changelog
7. Phases 8–9 — validation and hooks

Suggested commit subjects after the atomic directory+import commit: tests, scripts, config/CI,
docs/Sphinx, stale-brand check.

---

## Open questions

1. **`PySkinDoseOutput`?** Keep. Separate PR if ever renamed.
2. **GitHub repo rename?** Independent of this PR. Do not rewrite live
   `github.com/kgrizz-git/MyPySkinDose` links or the Sonar project key in the mechanical-rename
   PR. Republication Phase 7 owns the GitHub rename.
3. **PyPI `guiskindose` availability?** Confirm before starting Phase 1. This fork has not
   published `mypyskindose`.
4. **First GUISkinDose version?** Record in Phase 0. Prefer a documented breaking bump of the
   current `25.2.0` line over pretending this is a patch.
5. **Notebooks** under `tests/manual_tests/notebook_tests/` need JSON-aware edits and a
   post-rename execution check.
6. **`[project.scripts]`?** Yes — add `guiskindose` in this rename (new surface, not a
   publication-only concern). Republication 5B still smoke-tests the wheel.

---

## Timing

Prefer executing this plan **before the first PyPI publish** and **before more large features
land**. Every week of GUI/privacy work adds `mypyskindose` strings and mock targets. Waiting
for republication Phases 1–4 (fixture sanitization) is unnecessary: those can land before or
after the import rename. Waiting for the GitHub repository rename is also unnecessary and
would block the package rename on an unrelated operations step.

Downsides of doing it now: a ~300-file PR that conflicts with any parallel `src/` work;
privacy-admission friction on moved STL/DICOM paths; local scripts and worktree editable
installs break until reinstalled; users with `~/.mypyskindose/` depend on the migration code
being correct. Downsides of waiting: the same PR grows, and publishing `mypyskindose` first
would create a name we then have to deprecate.
