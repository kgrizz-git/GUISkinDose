# AGENTS.md — GUISkinDose

This file provides orientation for AI agents (and new developers) working on this codebase.

## What this project is

GUISkinDose estimates **peak skin dose (PSD)** and generates **3D skin dose maps** for fluoroscopic X-ray procedures. It reads a DICOM RDSR file, reconstructs the 3D geometry of each irradiation event, places a computational patient phantom in that geometry, and accumulates dose to each skin cell using physics-based correction factors.

It is a fork of [PySkinDose](https://github.com/rvbCMTS/PySkinDose). The package name in code is `guiskindose` (formerly `mypyskindose`). First GUISkinDose version is **`1.0.0`**.

## Detailed documentation

- **[dev-docs/AGENT_PLAYBOOK.md](dev-docs/AGENT_PLAYBOOK.md)** — shared workflow rules for coding agents; `CLAUDE.md`, `GEMINI.md`, and `QWEN.md` are thin pointers to this guidance.
- **[dev-docs/CODEBASE_OVERVIEW.md](dev-docs/CODEBASE_OVERVIEW.md)** — full architecture, data flow, all settings, classes, and functions
- **[dev-docs/FEATURE_INVENTORY.md](dev-docs/FEATURE_INVENTORY.md)** — exhaustive list of every feature: calculations, rendering, settings, outputs, CLI, API
- **[dev-docs/plans/GUI_PLAN.md](dev-docs/plans/GUI_PLAN.md)** — GUI current state (§0) and NiceGUI implementation plan
- **[DESIGN.md](DESIGN.md)** — GUI aesthetic intent; **[dev-docs/UI_values.md](dev-docs/UI_values.md)** — auto-generated design tokens from `app.py`
- **[dev-docs/plans/TABULAR_RDSR_INPUT_PLAN.md](dev-docs/plans/TABULAR_RDSR_INPUT_PLAN.md)** — plan for CSV/TSV/XLSX exported event-table inputs
- **[dev-docs/INPUT_SCHEMA_DETECTION.md](dev-docs/INPUT_SCHEMA_DETECTION.md)** — tabular schema auto-detection (GUI/CLI default `auto`, how each source schema is recognized) and the DAP-unit / equipment-manufacturer caveat
- **[dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md](dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md)** — RDSR normalization, vendor offsets, and the internal DataFrame contract
- **[dev-docs/HARNESS_ENGINEERING.md](dev-docs/HARNESS_ENGINEERING.md)** — repository harness principles, source-of-truth map, and validation commands (includes `python scripts/check_doc_freshness.py`)
- **[dev-docs/PRIVACY_AND_SENSITIVE_ASSETS.md](dev-docs/PRIVACY_AND_SENSITIVE_ASSETS.md)** — public-repository PII/PHI safeguards, DICOM/image review policy, and approved-asset inventory
- **[dev-docs/PRIVACY_INCIDENT_RESPONSE.md](dev-docs/PRIVACY_INCIDENT_RESPONSE.md)** — private evidence handling, history/release audit, containment, remediation, and release checklist
- **[dev-docs/plans/PRIVACY_HARDENING_PLAN.md](dev-docs/plans/PRIVACY_HARDENING_PLAN.md)** — phased plan for runtime diagnostics, de-identified exports, test/write containment, scanner cadence, asset review, and release privacy gates
- **[dev-docs/plans/archive/GUISKINDOSE_RENAME_PLAN.md](dev-docs/plans/archive/GUISKINDOSE_RENAME_PLAN.md)** — in-repo rename to GUISkinDose / `guiskindose` (**complete**, PR #73). **First `guiskindose` version is `1.0.0`** (new identity, not a continuation of MyPySkinDose `25.2.0`). Its "Post-PR-1 retirement" section remains the lifecycle guidance for the dual-read/semgrep-ID shims.
- **[dev-docs/plans/archive/GUISKINDOSE_GITHUB_RENAME_PLAN.md](dev-docs/plans/archive/GUISKINDOSE_GITHUB_RENAME_PLAN.md)** — GitHub fork renamed to `GUISkinDose`, SonarCloud key flipped, live URLs retargeted (**complete**, 2026-09-04).
- **[dev-docs/plans/archive/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](dev-docs/plans/archive/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md)** — phased plan to close harness gaps (CI parity, doc-freshness, entropy cleanup)
- **[dev-docs/LICENSE_COMPLIANCE.md](dev-docs/LICENSE_COMPLIANCE.md)** — third-party license policy, audit commands, and notices workflow
- **[dev-docs/assessments/](dev-docs/assessments/)** — diagnostics and assessments of code quality, refactoring, bug checks, or security
- **[CHANGELOG.md](CHANGELOG.md)** — notable changes per version; version source of truth is `pyproject.toml`
- **[dev-docs/RELEASES_AND_DISTRIBUTION.md](dev-docs/RELEASES_AND_DISTRIBUTION.md)** — release/distribution hub (PyPI, GitHub notes vs changelog, deferred portable executables)

## Quick orientation

### Entry point
```python
from guiskindose.main import main
from guiskindose import PyskindoseSettings, load_settings_example_json

settings = PyskindoseSettings(settings=load_settings_example_json())
settings.mode = "calculate_dose"
settings.phantom.model = "human"
settings.phantom.human_mesh = "hudfrid"
output = main(file_path="path/to/file.dcm", settings=settings)
print(output["psd"])  # peak skin dose in mGy
```

### Key files

| File | Role |
|------|------|
| `src/guiskindose/main.py` | Entry point: `main()`, CLI dispatch; re-exports `get_argument_parser` |
| `src/guiskindose/__main__.py` | `python -m guiskindose` and `guiskindose` console script |
| `src/guiskindose/cli_args.py` | argparse construction (extracted from `main.py`); per-flag helpers |
| `src/guiskindose/analyze_data.py` | Core orchestration |
| `src/guiskindose/phantom_class.py` | Patient/table/pad phantom mesh |
| `src/guiskindose/beam_class.py` | X-ray beam geometry |
| `src/guiskindose/geom_calc.py` | Geometry calculations |
| `src/guiskindose/corrections.py` | Physics correction factors |
| `src/guiskindose/calculate_dose/` | Dose calculation pipeline |
| `src/guiskindose/settings/` | Settings dataclasses |
| `src/guiskindose/plotting/` | Plotly visualisation |
| `src/guiskindose/settings_example.json` | Template settings |
| `corrections.db` | SQLite correction-factor database |

### Run modes

| `settings.mode` | What it does |
|-----------------|-------------|
| `"plot_setup"` | Show phantom + table in starting position (no RDSR needed) |
| `"plot_event"` | Show geometry for one irradiation event |
| `"plot_procedure"` | Interactive slider through all events |
| `"calculate_dose"` | Full dose calculation + dose map |

### Output formats

Set `settings.output_format` to:
- `"html"` — renders interactive Plotly plot (default)
- `"dict"` — returns Python dict with `psd`, `dose_map`, `corrections`, etc.
- `"json"` — returns JSON string of the same

### Phantom models

| `settings.phantom.model` | Description |
|--------------------------|-------------|
| `"plane"` | 2D flat grid |
| `"cylinder"` | Elliptic cylinder |
| `"human"` | STL mesh (set `settings.phantom.human_mesh`) |

Available human meshes live under `src/guiskindose/phantom_data/` and are discovered
at runtime (Settings / CLI). The clinical library covers age bands (preschool through
senior), sex variants, habitus families (ecto / endo / bariatric series), and optional
`*_arms_down` twins for table-side posing. Exact stems may change as the catalog is
trimmed; prefer the in-app mesh list or `get_human_mesh_names()` over hard-coded
inventories. Legacy stems (e.g. `pediatric_5y_male`, `bariatric_class2_male`) still
resolve via aliases. Non-clinical demo STLs are **not** shipped (local stash only under
gitignored `tmp/phantom_data_demo_stash/` if retained on a developer machine).

Human meshes can be directionally scaled with `settings.phantom.scale_lat`, `scale_ap`, and
`scale_lon` (defaults `1.0`; clamped to `0.5–2.0`). The GUI exposes these in
**Settings → Phantom Settings → Body habitus scaling** and geometry/dose calculations use the
scaled STL vertices and recomputed normals. Settings also shows a live 3D human-mesh preview
(no RDSR; prefers `_reduced_3000t` when present, else `_reduced_1000t`) so users can confirm mesh, face-up pose,
habitus scales, and patient offsets before upload. GUI measurements use left-right width,
anterior-posterior thickness, and superior-inferior length; the width is measured
in a torso band below the arms while `scale_lat` still scales the full lateral mesh axis.

## Current development focus

**Goal: make the code easier to use and more user-friendly, including an intuitive GUI.**

Public contribution and support docs: [CONTRIBUTING.md](CONTRIBUTING.md), [SUPPORT.md](SUPPORT.md),
[SECURITY.md](SECURITY.md). Fork stewardship: [dev-docs/FORK_MAINTAINER_GUIDE.md](dev-docs/FORK_MAINTAINER_GUIDE.md).
Intended use is research / education / development / institutional QA — **not FDA-cleared**;
physicists and physicians remain responsible for reviewing results and patient-care decisions.
Unsolicited cold PRs are discouraged; ideas and submissions are welcome via Issues or Discussions.

See [dev-docs/plans/GUI_PLAN.md](dev-docs/plans/GUI_PLAN.md) for the full implementation plan. In-repo
rename to GUISkinDose / `guiskindose`: [dev-docs/plans/archive/GUISKINDOSE_RENAME_PLAN.md](dev-docs/plans/archive/GUISKINDOSE_RENAME_PLAN.md)
(**complete**; **first version `1.0.0`**). GitHub/Sonar/live URLs:
[dev-docs/plans/archive/GUISKINDOSE_GITHUB_RENAME_PLAN.md](dev-docs/plans/archive/GUISKINDOSE_GITHUB_RENAME_PLAN.md) (**complete**, 2026-09-04). The short version:

1. A NiceGUI app now exists in `src/guiskindose/gui/`. `app.py` (~470 lines) builds layout and `PageContext`; each tab lives under `gui/tabs/` (`upload`, `data`, `settings`, `geometry`, `calculate`, `results`, `export`); upload widgets under `gui/widgets/`.
2. The CLI supports `--mode gui` and optional `--native`; `python -m guiskindose --mode gui` (or the `guiskindose` console script) launches the GUI.
3. Current GUI focus: refine validation, exports, and user-facing help. **Multi-exam Geometry** (Parts I–V shipped): exam selector, per-active patient/table-origin sliders, composite preview, Calculate/Settings summaries, N4 Settings→Geometry refresh — see [dev-docs/plans/archive/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md](dev-docs/plans/archive/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md). Multi-exam support: the Data Table tags each row with an `Exam` column (`gui/helpers.rebuild_rdsr_df()`); editable per-exam controls live in **Settings → Per-exam corrections** (`gui/tabs/_per_exam.py`). Single-exam offsets plan: `dev-docs/plans/archive/INTERACTIVE_TABLE_OFFSETS_PLAN.md`.
4. Tabular input Phases 1–5 are **shipped**: `input_adapters/` handles `.csv`, `.tsv`, `.xlsx` via `normalized`, `generic_rdsr_like`, `radimetrics`, and `dosetrack` schemas. DoseTrack adapter: Equipment Name → Manufacturer inference (`MODEL2MANUF`), ffill, integer Plane Code normalization, unit conversions, CFA derivation from DAP formula, Siemens/Philips filter thickness, Philips lat/lon swap warning. GE lateral/longitudinal handling is now normalization-level via `swap_lateral_longitudinal`; GUI `Tx↔Tz` swap remains a manual expert override for site-specific exports. CLI flags `--input-schema`, `--sheet-name`, `--input-preview-only` are wired. GUI Phase 5: upload tab accepts all tabular formats; import preview panel; schema selector including DoseTrack; **individual coordinate correction toggles** (Tx↔Tz swap, Ap1×−1, Ap2×−1) applied live; **XLSX sheet picker** for multi-sheet workbooks with re-parse on change. Qaelum, DoseMonitor, and DoseWatch are Phase 5+ placeholders (stub adapters exist; need real export fixtures). See `dev-docs/plans/TABULAR_RDSR_INPUT_PLAN.md` and `dev-docs/references/`.
5. Robustness/physics: the HVL and `k_tab` lookups now **interpolate** off-grid filtration and **clamp** (never extrapolate) out-of-range queries, warning per event (`grid_interp.py`). Events below the 25 kV HVL floor are handled by a user-selectable policy — `below_floor_kvp_policy` ∈ `exam_average` (default) / `snap` / `skip` / `manual` (`geom_calc.apply_below_floor_kvp_policy()`), surfaced as a Physics setting + a pre-calc prompt. See `dev-docs/plans/archive/hvl-interpolation-and-below-floor-kvp.md`.
6. Harness focus: keep `AGENTS.md` and `dev-docs/` synchronized with behavior and use the checks in `dev-docs/HARNESS_ENGINEERING.md`. New or changed images, DICOM, and opaque binaries require an exact approved-inventory hash; extensionless files are scanned as text only when their complete contents are valid, NUL-free UTF-8. See `PRIVACY_AND_SENSITIVE_ASSETS.md`. OWASP Semgrep runs locally after `privacy-gates`; tokenized SonarCloud is now **enabled** — `main` is protected by a ruleset and `SONAR_PROTECTED_MAIN_ENABLED=true`, so the `sonar-scan` job runs on `main` pushes only (never on a PR head), still gated behind `privacy-gates` + `build` and skipped if `SONAR_TOKEN` is absent. CodeRabbit auto-review is off and CI requests it after `privacy-gates`, but a manual CodeRabbit command can bypass that ordering, so its filters are defense in depth rather than an admission boundary.
7. **Phantom library:** MPFB/Blender true-shape catalog Phases 0–4 are complete (23 base clinical meshes shipped, plus `*_arms_down` twins; runbook archived at [dev-docs/plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md](dev-docs/plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md)). Further phantoms and optional user-imported custom meshes remain open in `dev-docs/TO_DO.md` and [dev-docs/ADDITIONAL_PHANTOMS.md](dev-docs/ADDITIONAL_PHANTOMS.md).

## Development setup

```bash
pip install -e .
pip install -e ".[dev,gui]"   # ruff, pytest, basedpyright, bandit, pip-audit, semgrep, shellcheck-py, pre-commit + stubs (matches CI)
pip install -e ".[docs,notebooks]"   # Sphinx site + JupyterLab for the getting-started notebook
```

Extras live in `pyproject.toml` (`gui`, `gui-native`, `dev`, `docs`, `notebooks`) — the single
source of truth for dependencies; there are no `requirements*.txt` files. `uv.lock` pins exact
versions (`uv sync --all-extras`). Installing and using **`uv`** is recommended for package
management and local development (it runs dependency audits and environment syncing much faster).

Optional local git hooks (fast subset of CI):

```bash
# macOS / Linux
bash scripts/setup-dev.sh

# Windows
scripts\setup-dev.bat
```

To run hooks manually:

```bash
pre-commit run --all-files                           # pre-commit stage hooks
pre-commit run --hook-stage pre-push --all-files     # pre-push hooks (semgrep, audit_dependencies, basedpyright, changelog)
```

The **semgrep** pre-push hook fetches `p/owasp-top-ten` from the Semgrep registry, so it
needs network access (offline pushes will fail). On Windows, semgrep runs natively (beta)
but may need `PYTHONUTF8=1` in the environment; treat the local pre-push hook as
best-effort on Windows — CI runs semgrep on Ubuntu.

Run the getting-started notebook:
```bash
jupyter notebook docs/source/getting_started/getting_started.ipynb
```

Example RDSR files are in `src/guiskindose/example_data/RDSR/`.

Run the GUI locally:
```bash
python -m guiskindose --mode gui
```

## Conventions

- Python 3.11+

### Cross-platform (Windows, macOS, Linux)

- Target all three OSes for user-facing behavior; browser-mode GUI must work everywhere.
- Use `pathlib.Path` for file paths; never concatenate paths with `/` or `\`. For atomic config writes, use `Path.replace()`, not `os.rename`.
- Avoid `sys.platform` / `platform.system()` branches unless unavoidable; prefer portable libraries, try/except, and fallbacks (not platform-native APIs from the NiceGUI main process).
- Keep `gui` and `gui-native` as optional extras; CI unit tests must pass without `gui-native`.
- `run_gui.sh` and `run_gui.bat` may be OS-specific launchers; application logic under `src/` must not be.
- Native or OS-sensitive GUI work (pywebview, window geometry, file dialogs): note Windows manual smoke in the PR or test plan when behavior may differ by OS.

- Line length: 120 (ruff)
- All units in **cm** unless otherwise noted
- Settings always passed as `PyskindoseSettings` object internally; JSON/dict accepted at the boundary
- Correction factors are dimensionless floats in range 0–1 (or slightly above 1 for backscatter)
- Coordinate conventions are nuanced: physical world geometry uses X=lateral, Y=vertical/AP, Z=longitudinal for head-first supine positioning (unified +Y points down toward the floor; the `(0,0,0)` origin is the beam isocenter, which coincides with the table head-end when the table-position readout is zero), while PySkinDose plot labels show `X - LON / PT L-R`, `Y - VER / PT A-P`, `Z - LAT / PT S-I`. RDSRs use table-position names, not x/y/z; Siemens/Philips use the DICOM/operator table convention, while GE raw data uses patient-anatomy longitudinal/lateral naming and is normalized by swapping raw long/lat into the common plotted frame. See `dev-docs/VENDOR_COORDINATE_SYSTEMS.md` before changing normalization, plotting labels, or vendor coordinate handling.
- GUI dependencies are optional extras: `pip install guiskindose[gui]` — do not add them to core dependencies
- **Modularity:** Keep all Python source and Markdown documentation files under ~800 lines unless strictly unavoidable (checked in CI; outliers must be whitelisted in `scripts/check_file_sizes.py`).
- **Plan lifecycle:** Completed or superseded execution plans must be archived under `dev-docs/plans/archive/` (always update `dev-docs/index.md` in the same PR).
- **Doc paths:** Never commit absolute filesystem paths or `file://` URIs in repository docs. Use repo-relative Markdown links for tracked files and normal prose/backticks for commands or examples.
- **Privacy admission:** Do not commit PHI/PII, internal PACS endpoints, private-network addresses (IPv4 or IPv6), or diagnostic artifacts. Run the sensitive-content gate; the commit message is checked separately at `commit-msg`. Protected ignore rules/never-track roots and conditional scanner receipts are enforced by `scripts/privacy_admission.py`; run `python scripts/privacy_admission.py run --mode staged` when the route requires it. Images, DICOM, PDFs, supported archive/document containers, and opaque binary files require hash-pinned human clearance; extensionless configuration files are scanned as text only when their complete contents are valid, NUL-free UTF-8. See `dev-docs/PRIVACY_AND_SENSITIVE_ASSETS.md` before adding fixtures or handling findings.
- **Runtime privacy:** Never log, print, or write raw identifiers, source filenames, or absolute paths; blocking project privacy Semgrep and local HoundDog flag leaks, and every secondary finding must be triaged. See `dev-docs/AGENT_PLAYBOOK.md` → Privacy and sensitive data for scanner triggers and cadence.
- **GUI help files:** The canonical source for in-app help markdown is `docs/source/gui_help/`. These files are mirrored to `src/guiskindose/gui/help/` by `scripts/sync_gui_help.py` (enforced by pre-commit + CI). Edit the source under `docs/`, never the mirrored copies under `src/`.
- **GUI help registry / UI copy:** GUI help coverage and high-risk UI copy are checked by `scripts/check_help_registry.py` and `scripts/check_ui_copy.py`; update `dev-docs/help_registry.json`, `dev-docs/ui_copy.json`, `dev-docs/glossary.json`, and `dev-docs/feature_doc_matrix.json` when adding tabs, help pages, warnings, explanatory tooltips, or feature docs.
- **Assessments:** Place diagnostic reports or assessments (such as for refactoring, code quality, bug checks, etc.) under `dev-docs/assessments/` (always update `dev-docs/index.md` in the same PR).
- **Workspace cleanliness:** Temporary scratch scripts or local output files must be kept in explicitly gitignored paths (e.g. `tmp/`, `scripts/scratch_*`, `*.tmp`, `debug_*`) or deleted immediately unless they are intended for reuse. Run `python scripts/check_doc_pruning.py` during doc-gardening to review stale active plans/assessments (30 days + 10 commits by default).
- **Agent guidance:** Keep shared instructions in `AGENTS.md` and `dev-docs/AGENT_PLAYBOOK.md`. Tool-specific files (`CLAUDE.md`, `GEMINI.md`, `QWEN.md`) should stay short and point back to the shared guidance. Run `python scripts/check_agent_guidance.py` to review drift; it is advisory unless `--strict` is used.
- **Git hooks (pre-commit / pre-push):** Never bypass hooks with `--no-verify` or `-n` without explicit user permission. If a hook fails on changes you believe are unrelated to your work, stop and ask the user before proceeding. Hooks exist to enforce privacy, security, and harness invariants — bypassing them silently can introduce undetected violations.
