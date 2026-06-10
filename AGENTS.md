# AGENTS.md — MyPySkinDose

This file provides orientation for AI agents (and new developers) working on this codebase.

## What this project is

MyPySkinDose estimates **peak skin dose (PSD)** and generates **3D skin dose maps** for fluoroscopic X-ray procedures. It reads a DICOM RDSR file, reconstructs the 3D geometry of each irradiation event, places a computational patient phantom in that geometry, and accumulates dose to each skin cell using physics-based correction factors.

It is a fork of [PySkinDose](https://github.com/rvbCMTS/PySkinDose). The package name in code is `mypyskindose`.

## Detailed documentation

- **[dev-docs/CODEBASE_OVERVIEW.md](dev-docs/CODEBASE_OVERVIEW.md)** — full architecture, data flow, all settings, classes, and functions
- **[dev-docs/FEATURE_INVENTORY.md](dev-docs/FEATURE_INVENTORY.md)** — exhaustive list of every feature: calculations, rendering, settings, outputs, CLI, API
- **[dev-docs/GUI_PLAN.md](dev-docs/GUI_PLAN.md)** — GUI current state (§0) and NiceGUI implementation plan
- **[DESIGN.md](DESIGN.md)** — GUI aesthetic intent; **[dev-docs/UI_values.md](dev-docs/UI_values.md)** — auto-generated design tokens from `app.py`
- **[dev-docs/TABULAR_RDSR_INPUT_PLAN.md](dev-docs/TABULAR_RDSR_INPUT_PLAN.md)** — plan for CSV/TSV/XLSX exported event-table inputs
- **[dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md](dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md)** — RDSR normalization, vendor offsets, and the internal DataFrame contract
- **[dev-docs/HARNESS_ENGINEERING.md](dev-docs/HARNESS_ENGINEERING.md)** — repository harness principles, source-of-truth map, and validation commands (includes `python scripts/check_doc_freshness.py`)
- **[dev-docs/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](dev-docs/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md)** — phased plan to close harness gaps (CI parity, doc-freshness, entropy cleanup)
- **[dev-docs/LICENSE_COMPLIANCE.md](dev-docs/LICENSE_COMPLIANCE.md)** — third-party license policy, audit commands, and notices workflow
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

See [dev-docs/GUI_PLAN.md](dev-docs/GUI_PLAN.md) for the full implementation plan. The short version:

1. A NiceGUI app now exists in `src/mypyskindose/gui/`.
2. The CLI supports `--mode gui` and optional `--native`; `python -m mypyskindose --mode gui` launches the GUI.
3. Current GUI focus: refine the multi-tab workflow, validation, event-table previews, exports, and user-facing help.
4. Tabular input Phases 1–3 are **shipped**: `input_adapters/` handles `.csv`, `.tsv`, `.xlsx` via `normalized`, `generic_rdsr_like`, and `radimetrics` schemas (Radimetrics: unit conversions mGy→Gy, cm²→m², mAs→µAs; validated against AXIOM-Artis column names). CLI flags `--input-schema`, `--sheet-name`, `--input-preview-only` are wired. The GUI upload tab now accepts all tabular formats with an import preview panel, schema selector (including "Radimetrics CSV"), lat/lon swap toggle, and provenance preserved in JSON/HTML exports. Phase 5 GUI work is partially shipped. Phase 4 (DoseTrack) is gated on a real DoseTrack XLSX fixture. See `dev-docs/TABULAR_RDSR_INPUT_PLAN.md`, `dev-docs/references/`, and `dev-docs/COORD_TRANSFORM_COMPARISON.md`.
5. Harness focus: keep `AGENTS.md` and `dev-docs/` synchronized with behavior and use the checks in `dev-docs/HARNESS_ENGINEERING.md`.

## Development setup

```bash
pip install -e .
pip install -e ".[dev,gui]"   # basedpyright, bandit, pip-audit, pre-commit + stubs (matches CI typecheck)
pip install jupyter  # for the notebook
```

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
- Line length: 120 (ruff/black)
- All units in **cm** unless otherwise noted
- Settings always passed as `PyskindoseSettings` object internally; JSON/dict accepted at the boundary
- Correction factors are dimensionless floats in range 0–1 (or slightly above 1 for backscatter)
- The coordinate system: X = lateral, Y = longitudinal, Z = vertical
- GUI dependencies are optional extras: `pip install mypyskindose[gui]` — do not add them to core dependencies
