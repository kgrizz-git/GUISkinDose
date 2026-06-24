# AGENTS.md — MyPySkinDose

This file provides orientation for AI agents (and new developers) working on this codebase.

## What this project is

MyPySkinDose estimates **peak skin dose (PSD)** and generates **3D skin dose maps** for fluoroscopic X-ray procedures. It reads a DICOM RDSR file, reconstructs the 3D geometry of each irradiation event, places a computational patient phantom in that geometry, and accumulates dose to each skin cell using physics-based correction factors.

It is a fork of [PySkinDose](https://github.com/rvbCMTS/PySkinDose). The package name in code is `mypyskindose`.

## Detailed documentation

- **[CLAUDE.md](CLAUDE.md)** — Claude Code auto-loaded quick-reference: plan lifecycle steps, doc update rule, and validation commands.
- **[dev-docs/CODEBASE_OVERVIEW.md](dev-docs/CODEBASE_OVERVIEW.md)** — full architecture, data flow, all settings, classes, and functions
- **[dev-docs/FEATURE_INVENTORY.md](dev-docs/FEATURE_INVENTORY.md)** — exhaustive list of every feature: calculations, rendering, settings, outputs, CLI, API
- **[dev-docs/plans/GUI_PLAN.md](dev-docs/plans/GUI_PLAN.md)** — GUI current state (§0) and NiceGUI implementation plan
- **[DESIGN.md](DESIGN.md)** — GUI aesthetic intent; **[dev-docs/UI_values.md](dev-docs/UI_values.md)** — auto-generated design tokens from `app.py`
- **[dev-docs/plans/TABULAR_RDSR_INPUT_PLAN.md](dev-docs/plans/TABULAR_RDSR_INPUT_PLAN.md)** — plan for CSV/TSV/XLSX exported event-table inputs
- **[dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md](dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md)** — RDSR normalization, vendor offsets, and the internal DataFrame contract
- **[dev-docs/HARNESS_ENGINEERING.md](dev-docs/HARNESS_ENGINEERING.md)** — repository harness principles, source-of-truth map, and validation commands (includes `python scripts/check_doc_freshness.py`)
- **[dev-docs/plans/archive/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](dev-docs/plans/archive/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md)** — phased plan to close harness gaps (CI parity, doc-freshness, entropy cleanup)
- **[dev-docs/LICENSE_COMPLIANCE.md](dev-docs/LICENSE_COMPLIANCE.md)** — third-party license policy, audit commands, and notices workflow
- **[dev-docs/assessments/](dev-docs/assessments/)** — diagnostics and assessments of code quality, refactoring, bug checks, or security
- **[CHANGELOG.md](CHANGELOG.md)** — release history; version source of truth is `pyproject.toml`

## Quick orientation

### Entry point
```python
from mypyskindose.main import main
from mypyskindose import PyskindoseSettings, load_settings_example_json

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
| `src/mypyskindose/main.py` | Entry point: `main()`, CLI |
| `src/mypyskindose/analyze_data.py` | Core orchestration |
| `src/mypyskindose/phantom_class.py` | Patient/table/pad phantom mesh |
| `src/mypyskindose/beam_class.py` | X-ray beam geometry |
| `src/mypyskindose/geom_calc.py` | Geometry calculations |
| `src/mypyskindose/corrections.py` | Physics correction factors |
| `src/mypyskindose/calculate_dose/` | Dose calculation pipeline |
| `src/mypyskindose/settings/` | Settings dataclasses |
| `src/mypyskindose/plotting/` | Plotly visualisation |
| `src/mypyskindose/settings_example.json` | Template settings |
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

Available human meshes: `hudfrid`, `adult_male`, `adult_female`, `junior_male`, `junior_female`

## Current development focus

**Goal: make the code easier to use and more user-friendly, including an intuitive GUI.**

See [dev-docs/plans/GUI_PLAN.md](dev-docs/plans/GUI_PLAN.md) for the full implementation plan. The short version:

1. A NiceGUI app now exists in `src/mypyskindose/gui/`. `app.py` (~245 lines) builds layout and `PageContext`; each tab lives under `gui/tabs/` (`upload`, `data`, `settings`, `geometry`, `calculate`, `results`, `export`); upload widgets under `gui/widgets/`.
2. The CLI supports `--mode gui` and optional `--native`; `python -m mypyskindose --mode gui` launches the GUI.
3. Current GUI focus: refine the multi-tab workflow, validation, event-table previews, exports, and user-facing help. **Multi-exam Geometry** (Parts II–IV shipped): exam selector + C1 banner, per-active-exam patient and table-origin sliders, composite preview toggle + captions, sliced/composite preview — see [dev-docs/plans/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md](dev-docs/plans/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md). **Part V** (formatters, docs) remains. Multi-exam support: the Data Table tags each row with an `Exam` column in multi-exam mode (`gui/helpers.rebuild_rdsr_df()`); editable per-exam controls (offsets, coordinate corrections, table-origin override) live in **Settings → Per-exam corrections** (`gui/tabs/_per_exam.py`), while the Upload tab shows a compact loaded-files summary. Single-exam offsets plan: `dev-docs/plans/INTERACTIVE_TABLE_OFFSETS_PLAN.md`.
4. Tabular input Phases 1–5 are **shipped**: `input_adapters/` handles `.csv`, `.tsv`, `.xlsx` via `normalized`, `generic_rdsr_like`, `radimetrics`, and `dosetrack` schemas. DoseTrack adapter: Equipment Name → Manufacturer inference (`MODEL2MANUF`), ffill, integer Plane Code normalization, unit conversions, CFA derivation from DAP formula, Siemens/Philips filter thickness, Philips lat/lon swap warning. CLI flags `--input-schema`, `--sheet-name`, `--input-preview-only` are wired. GUI Phase 5: upload tab accepts all tabular formats; import preview panel; schema selector including DoseTrack; **individual coordinate correction toggles** (Tx↔Tz swap, Ap1×−1, Ap2×−1) applied live; **intelligent defaults** auto-set from detected manufacturer (GE/Philips auto-enable lat/lon swap), user-overridable; **XLSX sheet picker** for multi-sheet workbooks with re-parse on change. Qaelum, DoseMonitor, and DoseWatch are Phase 5+ placeholders (stub adapters exist; need real export fixtures). See `dev-docs/plans/TABULAR_RDSR_INPUT_PLAN.md` and `dev-docs/references/`.
5. Robustness/physics: the HVL and `k_tab` lookups now **interpolate** off-grid filtration and **clamp** (never extrapolate) out-of-range queries, warning per event (`grid_interp.py`). Events below the 25 kV HVL floor are handled by a user-selectable policy — `below_floor_kvp_policy` ∈ `snap` (default) / `skip` / `manual` / `exam_average` (`geom_calc.apply_below_floor_kvp_policy()`), surfaced as a Physics setting + a pre-calc prompt. See `dev-docs/plans/archive/hvl-interpolation-and-below-floor-kvp.md`.
6. Harness focus: keep `AGENTS.md` and `dev-docs/` synchronized with behavior and use the checks in `dev-docs/HARNESS_ENGINEERING.md`.

## Development setup

```bash
pip install -e .
pip install -e ".[dev,gui]"   # ruff, pytest, basedpyright, bandit, pip-audit, pre-commit + stubs (matches CI)
pip install -e ".[docs,notebooks]"   # Sphinx site + JupyterLab for the getting-started notebook
```

Extras live in `pyproject.toml` (`gui`, `gui-native`, `dev`, `docs`, `notebooks`) — the single
source of truth for dependencies; there are no `requirements*.txt` files. `uv.lock` pins exact
versions (`uv sync --all-extras`).

Optional local git hooks (fast subset of CI):

```bash
pip install -e ".[dev,gui]"
pre-commit install
pre-commit install --hook-type pre-push
```

Run the getting-started notebook:
```bash
jupyter notebook docs/source/getting_started/getting_started.ipynb
```

Example RDSR files are in `src/mypyskindose/example_data/RDSR/`.

Run the GUI locally:
```bash
python -m mypyskindose --mode gui
```

## Conventions

- Python 3.10+
- **Cross-platform: Windows, macOS, Linux** — always use `pathlib.Path` for file paths, never string concatenation with `/` or `\`
- Line length: 120 (ruff)
- All units in **cm** unless otherwise noted
- Settings always passed as `PyskindoseSettings` object internally; JSON/dict accepted at the boundary
- Correction factors are dimensionless floats in range 0–1 (or slightly above 1 for backscatter)
- The coordinate system: X = lateral, Y = longitudinal, Z = vertical
- GUI dependencies are optional extras: `pip install mypyskindose[gui]` — do not add them to core dependencies
- **Modularity:** Keep all Python source and Markdown documentation files under ~800 lines unless strictly unavoidable (checked in CI; outliers must be whitelisted in `scripts/check_file_sizes.py`).
- **Plan lifecycle:** Completed or superseded execution plans must be archived under `dev-docs/plans/archive/` (always update `dev-docs/index.md` in the same PR).
- **GUI help files:** The canonical source for in-app help markdown is `docs/source/gui_help/`. These files are mirrored to `src/mypyskindose/gui/help/` by `scripts/sync_gui_help.py` (enforced by pre-commit + CI). Edit the source under `docs/`, never the mirrored copies under `src/`.
- **Assessments:** Place diagnostic reports or assessments (such as for refactoring, code quality, bug checks, etc.) under `dev-docs/assessments/` (always update `dev-docs/index.md` in the same PR).
- **Workspace cleanliness:** Temporary scratch scripts or local output files must be kept in explicitly gitignored paths (e.g. `tmp/`, `scripts/scratch_*`, `*.tmp`, `debug_*`) or deleted immediately unless they are intended for reuse. Run `python scripts/check_doc_pruning.py` during doc-gardening to review stale active plans/assessments (30 days + 10 commits by default).
