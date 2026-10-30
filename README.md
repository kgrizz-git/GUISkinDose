<p align="center">
  <img src="https://raw.githubusercontent.com/kgrizz-git/GUISkinDose/main/src/guiskindose/gui/static/guiskindose_icon.svg" alt="GUISkinDose icon" width="96" height="96">
</p>

<h1 align="center">GUISkinDose</h1>

<p align="center">
  Peak skin dose and 3D skin dose maps for fluoroscopic X-ray procedures.
</p>

<p align="center">
  <a href="https://github.com/kgrizz-git/GUISkinDose/actions/workflows/ci.yml"><img src="https://github.com/kgrizz-git/GUISkinDose/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI"></a>
  <a href="https://github.com/kgrizz-git/GUISkinDose/actions/workflows/dependency-audit.yml"><img src="https://github.com/kgrizz-git/GUISkinDose/actions/workflows/dependency-audit.yml/badge.svg?branch=main" alt="Dependency audit"></a>
  <a href="https://sonarcloud.io/summary/new_code?id=kgrizz-git_GUISkinDose"><img src="https://sonarcloud.io/api/project_badges/measure?project=kgrizz-git_GUISkinDose&amp;metric=alert_status" alt="SonarCloud quality gate"></a>
  <br>
  <img src="https://img.shields.io/python/required-version-toml?tomlFilePath=https%3A%2F%2Fraw.githubusercontent.com%2Fkgrizz-git%2FGUISkinDose%2Fmain%2Fpyproject.toml&amp;logo=python&amp;logoColor=white&amp;color=3776AB" alt="Supported Python versions (from pyproject.toml)">
  <a href="https://github.com/kgrizz-git/GUISkinDose/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-0D9488" alt="MIT license"></a>
  <a href="https://nicegui.io"><img src="https://img.shields.io/badge/GUI-NiceGUI-4338CA" alt="NiceGUI"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="#intended-use-and-responsibility"><img src="https://img.shields.io/badge/use-research%20%2F%20QA%20only-831843" alt="Research and QA use only; not FDA-cleared"></a>
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
    <a href="#headless-use">Headless use</a> ·
  <a href="https://github.com/kgrizz-git/GUISkinDose/blob/main/docs/source/user/user_guide.md">User guide</a> ·
  <a href="https://github.com/kgrizz-git/GUISkinDose/blob/main/CHANGELOG.md">Changelog</a> ·
  <a href="https://github.com/kgrizz-git/GUISkinDose/discussions">Discussions</a>
</p>

**Independently maintained fork** of [PySkinDose](https://github.com/rvbCMTS/PySkinDose).
Original author: Max Hellström. This fork is **not** an official or endorsed
PySkinDose release unless upstream maintainers say otherwise.

Current maintainer: [@kgrizz-git](https://github.com/kgrizz-git) — see
[SUPPORT.md](https://github.com/kgrizz-git/GUISkinDose/blob/main/SUPPORT.md) and [GOVERNANCE.md](https://github.com/kgrizz-git/GUISkinDose/blob/main/GOVERNANCE.md).

GUISkinDose estimates **peak skin dose (PSD)** and **3D skin dose maps** for
fluoroscopic X-ray procedures. Load a DICOM RDSR (or a tabular event-table
export), preview the examination geometry, run the dose calculation, and export
an audit report — from a graphical interface or headlessly from scripts.

The distribution and import package name is `guiskindose` (distinct from upstream).

| Upload | Geometry |
|---|---|
| ![Upload tab: load a DICOM RDSR or tabular event table](https://raw.githubusercontent.com/kgrizz-git/GUISkinDose/main/docs/source/user/figures/readme/upload.png) | ![Geometry preview: beam, phantom, and event selector](https://raw.githubusercontent.com/kgrizz-git/GUISkinDose/main/docs/source/user/figures/readme/geometry.png) |
| Results | Export |
| ![Results tab: peak skin dose cards and 3D dose map](https://raw.githubusercontent.com/kgrizz-git/GUISkinDose/main/docs/source/user/figures/readme/results.png) | ![Export tab: JSON, HTML, PNG, and rich-report downloads](https://raw.githubusercontent.com/kgrizz-git/GUISkinDose/main/docs/source/user/figures/readme/export.png) |

*Captured with the bundled example data; no patient data.*

## Intended use and responsibility

GUISkinDose is intended for **research, education, development, and
institutional quality-assurance** workflows. It is **not FDA-cleared** (or
otherwise certified) as a medical device, and results are **not** independently
validated for making patient-care decisions on their own.

**Physicists and physicians remain responsible** for reviewing outputs,
confirming that inputs and geometry settings are appropriate, and making any
clinical or patient-care decisions. Do not treat dose maps or PSD values as a
substitute for professional judgment, institutional policy, or regulatory
clearance.

Never commit or attach real patient data to issues, pull requests, or the
repository — see [CONTRIBUTING.md](https://github.com/kgrizz-git/GUISkinDose/blob/main/CONTRIBUTING.md) and
[dev-docs/PRIVACY_AND_SENSITIVE_ASSETS.md](https://github.com/kgrizz-git/GUISkinDose/blob/main/dev-docs/PRIVACY_AND_SENSITIVE_ASSETS.md).

## Quick start

Install from PyPI and launch the GUI:

```bash
pip install "guiskindose[gui]"
guiskindose --mode gui
```

Or install it as a standalone app with [uv](https://docs.astral.sh/uv/) or [pipx](https://pipx.pypa.io/):

```bash
uv tool install "guiskindose[gui]"     # or: pipx install "guiskindose[gui]"
guiskindose --mode gui
```

The GUI opens in your browser. Use `guiskindose[gui-native]` and `--native` to open it in
its own window instead. Install `guiskindose` with no extras for the library and CLI only.

The GUI walks through **Upload** (RDSR DICOM or tabular CSV/TSV/XLSX) → **Data** review →
**Settings** (phantom, per-exam offsets) → **Corrections** → **Geometry** preview →
**Calculate** → **Results** (PSD, dose map) → **Export** (JSON, HTML/PNG dose maps, and
XLSX/PDF/DOCX audit reports). Bundled example RDSR files let you try it without data of
your own.

Feature highlights include multi-exam aggregation with per-exam offsets, DoseTrack and
Radimetrics imports with schema auto-detection, kerma-meter correction by equipment and
tube, rich audit reports, and a human phantom library with habitus scaling. See the
[User guide](https://github.com/kgrizz-git/GUISkinDose/blob/main/docs/source/user/user_guide.md) and the
[feature inventory](https://github.com/kgrizz-git/GUISkinDose/blob/main/dev-docs/FEATURE_INVENTORY.md).

### Your data stays on your computer

GUISkinDose runs entirely on your machine and does not upload study data. The GUI listens
only on `127.0.0.1` and requires a per-launch link that the app opens for you. Logs leave
out file names and paths, because those often contain patient identifiers. See
[Running the GUI](https://github.com/kgrizz-git/GUISkinDose/blob/main/docs/source/user/running_the_gui.md) for launch options, local-access
details, logging, and platform notes.

## What this code is for

Within the intended-use boundary above, GUISkinDose is meant to be used in a few different ways:

1. Inspect or debug the examination geometry before doing dose calculations.
2. Step through irradiation events from an RDSR study to understand beam orientation and positioning.
3. Calculate a skin dose map on a mathematical or human phantom.
4. Export the calculation result as HTML, JSON, XLSX, PDF, or DOCX rich audit report, or as a Python dictionary for downstream processing.
5. Run the analysis headlessly from your own Python scripts.

## Working from source

To work on the code, clone the repository and install it in editable mode:

```bash
git clone https://github.com/kgrizz-git/GUISkinDose.git
cd GUISkinDose
uv sync --extra gui        # or: pip install -e ".[gui]"
```

`run_gui.sh` (macOS/Linux) and `run_gui.bat` (Windows) launch the GUI from a checkout and
set up the environment. Install `.[dev,gui]` for the lint, type, and test toolchain. See
[CONTRIBUTING.md](https://github.com/kgrizz-git/GUISkinDose/blob/main/CONTRIBUTING.md) for the full development setup.

## Requirements

- Python 3.11 or above
- A settings configuration, typically based on [src/guiskindose/settings_example.json](https://github.com/kgrizz-git/GUISkinDose/blob/main/src/guiskindose/settings_example.json)
- A DICOM RDSR file (`.dcm`), a pre-parsed JSON export, or a supported tabular event-table export (`.csv`, `.tsv`, `.xlsx`)

## Headless use

### Command-line flags

Run `guiskindose --help` for the full list. Common headless examples:

```bash
guiskindose --file-path study.dcm
guiskindose --file-path events.csv --input-schema auto
guiskindose --file-path workbook.xlsx --sheet-name "Sheet1"
guiskindose --file-path study.dcm --export-format xlsx --export-path report.xlsx
```

Notable flags: `--input-schema` (default `auto` for tabular files), `--input-preview-only`,
`--export-format {xlsx,pdf,html,docx}`, `--export-path`, `--include-source-identifiers` (opt-in;
may include PHI-bearing source filenames in reports), `--kerma-meter-correction` and related
kerma-meter options, `--equipment-profile` (repeatable custom-profile file) and
`--equipment-profile-sheet` (XLSX sheet name or 0-based index).

### Scripted example

```python
from guiskindose import PyskindoseSettings, get_path_to_example_rdsr_files, load_settings_example_json
from guiskindose.main import main

settings = PyskindoseSettings(settings=load_settings_example_json())
settings.mode = "calculate_dose"
settings.output_format = "dict"
settings.phantom.model = "human"
settings.phantom.human_mesh = "hudfrid"

rdsr_dir = get_path_to_example_rdsr_files()
output = main(settings=settings, file_path=rdsr_dir / "siemens_axiom_example_procedure.dcm")

print(f"Estimated PSD: {output['psd']:.1f} mGy")
```

When `settings.output_format` is set to `dict` or `json`, the result can be used programmatically. The exported result includes items such as patient/table/pad data, event geometry, correction factors, dose map data, and peak skin dose. If you already have normalized RDSR data in a pandas `DataFrame`, use `analyze_normalized_data_with_custom_settings_object()` instead.

### Custom equipment profiles (experimental)

Validated manufacturer/model coordinate profiles can override vendor coordinate
handling for raw inputs, from Python (`assemble_session()`), a settings-file
`equipment_profiles` block, or `--equipment-profile`. See
[Custom equipment profiles](https://github.com/kgrizz-git/GUISkinDose/blob/main/docs/source/user/equipment_profiles.md) for the API,
CLI flags, and capture replay.

**New to GUISkinDose?** Prefer the GUI or the interactive getting-started notebook
([docs/source/getting_started/getting_started.ipynb](https://github.com/kgrizz-git/GUISkinDose/blob/main/docs/source/getting_started/getting_started.ipynb);
run it via `pip install -e ".[notebooks]"` + `python scripts/open_getting_started_notebook.py`, which
opens an ignored local copy so experiments never dirty the tracked source).

## Useful helpers

The package includes helper functions that make exploration easier:

- `load_settings_example_json()` loads a ready-made settings template.
- `print_available_human_phantoms()` lists available human phantom meshes.
- `get_path_to_example_rdsr_files()` returns the folder containing bundled example RDSR files.
- `print_example_rdsr_files()` prints the bundled example filenames.

## Settings and modes

Important settings live in [src/guiskindose/settings_example.json](https://github.com/kgrizz-git/GUISkinDose/blob/main/src/guiskindose/settings_example.json) and the settings classes under [src/guiskindose/settings](https://github.com/kgrizz-git/GUISkinDose/blob/main/src/guiskindose/settings).

| Mode | What it does |
|---|---|
| `plot_setup` | Plot the initial geometry without loading an irradiation sequence |
| `plot_event` | Inspect one irradiation event |
| `plot_procedure` | Inspect the full event sequence |
| `calculate_dose` | Compute the dose map and peak skin dose estimate |

Common phantom models: `plane`, `cylinder`, `human`.

## Documentation

The user documentation lives under [docs/source](https://github.com/kgrizz-git/GUISkinDose/blob/main/docs/source), including the
getting-started notebook. To build it locally, run `pip install -e ".[docs]"` and then
`python -m sphinx -b html docs/source docs/build/html`.

## Notes for this fork

- Independently maintained fork of [PySkinDose](https://github.com/rvbCMTS/PySkinDose); MIT license and upstream copyright preserved.
- Package identity: `guiskindose` (see [dev-docs/GUISKINDOSE_MIGRATION_STATUS.md](https://github.com/kgrizz-git/GUISkinDose/blob/main/dev-docs/GUISKINDOSE_MIGRATION_STATUS.md)).
- How we maintain the fork: [dev-docs/FORK_MAINTAINER_GUIDE.md](https://github.com/kgrizz-git/GUISkinDose/blob/main/dev-docs/FORK_MAINTAINER_GUIDE.md).
- Bugs and features: [GitHub Issues](https://github.com/kgrizz-git/GUISkinDose/issues) (templates require a no-PHI/PII confirmation; see [dev-docs/PRIVACY_AND_SENSITIVE_ASSETS.md](https://github.com/kgrizz-git/GUISkinDose/blob/main/dev-docs/PRIVACY_AND_SENSITIVE_ASSETS.md)).
- Questions and contribution ideas: [GitHub Discussions](https://github.com/kgrizz-git/GUISkinDose/discussions). Ideas welcome — prefer Issues/Discussions over cold PRs ([CONTRIBUTING.md](https://github.com/kgrizz-git/GUISkinDose/blob/main/CONTRIBUTING.md)).
- Security: [SECURITY.md](https://github.com/kgrizz-git/GUISkinDose/blob/main/SECURITY.md). Support channels: [SUPPORT.md](https://github.com/kgrizz-git/GUISkinDose/blob/main/SUPPORT.md).
