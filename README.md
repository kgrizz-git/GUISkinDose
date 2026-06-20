# MyPySkinDose

Modified from the upstream PySkinDose project: https://github.com/rvbCMTS/PySkinDose

Original author: Max Hellström

This repository keeps the PySkinDose codebase for estimating 3D skin dose maps from DICOM X-ray Radiation Dose Structured Reports (RDSR), while allowing local modifications and further development in this fork.

The package name in code is `mypyskindose`.

## Requirements

- Python 3.10 or above
- A settings configuration, typically based on [src/mypyskindose/settings_example.json](src/mypyskindose/settings_example.json)
- An RDSR DICOM file, or a normalized/pre-parsed JSON export of RDSR data

## Installation

For local development, install the project in editable mode:

```bash
pip install -e .
```

To include the GUI dependencies:

```bash
pip install -e ".[gui]"
```

For full development setup (linting, testing, docs, Jupyter), install the
optional extras you need:

```bash
pip install -e ".[dev,gui]"             # lint/type/test toolchain + GUI
pip install -e ".[dev,gui,docs,notebooks]"   # everything (docs + JupyterLab)
```

## Running the GUI

MyPySkinDose includes a NiceGUI-based graphical interface.

**Quick launch (macOS/Linux):**

```bash
chmod +x run_gui.sh   # one-time setup, enables executing the sh script
./run_gui.sh
```

The script prompts you to run in browser mode (default) or native window mode.

**Direct Python command:**

```bash
python -m mypyskindose --mode gui              # browser mode
python -m mypyskindose --mode gui --native     # native window (requires pywebview)
```

### Network exposure (browser mode)

The GUI has **no authentication** and loads PHI-derived RDSR data into a single
shared, process-global state. To keep that off the network, browser mode binds to
`127.0.0.1` (localhost only) by default — reachable only from the machine it runs
on.

Serving it to other hosts is opt-in via `--host`:

```bash
python -m mypyskindose --mode gui --host 0.0.0.0   # serve on the LAN
```

Only do this on a trusted network, and behind your own access controls, since
anyone who can reach the port can view loaded patient data, trigger exports, and
mutate shared settings.

### Logging & privacy

The CLI and browser-mode GUI log to the console only. **Native** mode has no
console, so it also writes a diagnostic log to your system temp directory:

```
<tempdir>/mypyskindose-gui.log
```

This file is **truncated at each launch** and **size-capped** (rotating, ~4 MB
max across `.log`/`.log.1`–`.3`), so it does not accumulate across sessions.

To protect PHI, the app **does not log file names or paths** (RDSR filenames
often contain patient name/MRN/accession) — only file type, size, and event
counts. By default the file sink records `INFO` and above; verbose `DEBUG` output
is opt-in per category via a `debug.json` in the working directory, e.g.:

```json
{ "GUI": true, "PROCESSING": true, "CALCULATION": true, "RENDERING": true }
```

Even with debug enabled, identifiers are still redacted. The log lives outside
the repo by design (temp dir); delete it any time — it is recreated on next launch.

### Optional: native Save As dialogs (Tkinter)

The GUI works fully without Tkinter, but uses it for two niceties: the native
**Save As** file dialog when exporting, and detecting your screen size to size
the native window. If Tkinter is missing you'll see a log line like
`No module named '_tkinter'`, exports fall back to a browser-style download, and
the window opens at a default size — nothing crashes.

Tkinter ships with Python but is only built when the Tcl/Tk libraries are present
at build time, so it can be absent (commonly with `pyenv` builds). It is **not** a
pip package — do not add it to the project dependencies. To install it:

| Platform | Command |
|---|---|
| macOS, Homebrew Python | `brew install python-tk` (or `python-tk@3.12` for a specific version) |
| macOS, pyenv Python | `brew install tcl-tk`, then reinstall the interpreter: `pyenv install 3.12.9` |
| Debian / Ubuntu | `sudo apt install python3-tk` |
| Fedora | `sudo dnf install python3-tkinter` |
| Windows | Included with the python.org installer — keep "tcl/tk and IDLE" checked |

Verify with: `python -c "import tkinter; print(tkinter.TkVersion)"`.

If you only need the documentation tooling as well:

```bash
pip install -e ".[docs]"
```

## What this code is for

PySkinDose is meant to be used in a few different ways:

1. Inspect or debug the examination geometry before doing dose calculations.
2. Step through irradiation events from an RDSR study to understand beam orientation and positioning.
3. Calculate a skin dose map on a mathematical or human phantom.
4. Export the calculation result as HTML, JSON, or a Python dictionary for downstream processing.
5. Run the analysis headlessly from your own Python scripts.

The main user-facing workflow is:

1. Load or create a `PyskindoseSettings` object.
2. Choose a phantom and positioning.
3. Select a mode such as `plot_setup`, `plot_procedure`, `plot_event`, or `calculate_dose`.
4. Run `main()` with a path to an RDSR file.
5. Review the interactive plot or exported result.

## Quick Start with Jupyter Notebook

**New to PySkinDose?** The easiest way to learn is to start with the interactive getting-started notebook:

📓 **[docs/source/getting_started/getting_started.ipynb](docs/source/getting_started/getting_started.ipynb)**

This notebook walks you through:
- Loading and configuring settings
- Setting up different phantom models and positioning
- Inspecting RDSR procedures interactively
- Running calculations and generating dose maps
- Exporting results in different formats

To run the notebook:
```bash
pip install -e .
pip install jupyter
jupyter notebook docs/source/getting_started/getting_started.ipynb
```

If you prefer to learn by example with code snippets instead, continue to the section below.

## Typical usage

### 1. Start from the example settings

```python
from mypyskindose import PyskindoseSettings, load_settings_example_json
from mypyskindose.main import main

settings = PyskindoseSettings(settings=load_settings_example_json())
settings.mode = "plot_setup"
settings.phantom.model = "cylinder"

main(settings=settings)
```

This is useful for checking the initial geometry, patient/table positioning, and phantom choice before loading a real study.

### 2. Examine a procedure from an RDSR file

```python
from mypyskindose import PyskindoseSettings, get_path_to_example_rdsr_files, load_settings_example_json
from mypyskindose.main import main

settings = PyskindoseSettings(settings=load_settings_example_json())
settings.mode = "plot_procedure"
settings.phantom.model = "cylinder"
settings.plot.max_events_for_patient_inclusion = 0

rdsr_dir = get_path_to_example_rdsr_files()
main(settings=settings, file_path=rdsr_dir / "siemens_axiom_example_procedure.dcm")
```

Use `plot_procedure` to scroll through irradiation events and understand how the beam geometry changes over the study.

### 3. Calculate a dose map

```python
from mypyskindose import PyskindoseSettings, get_path_to_example_rdsr_files, load_settings_example_json
from mypyskindose.main import main

settings = PyskindoseSettings(settings=load_settings_example_json())
settings.mode = "calculate_dose"
settings.output_format = "dict"
settings.plot.plot_dosemap = True
settings.phantom.model = "human"
settings.phantom.human_mesh = "hudfrid"

rdsr_dir = get_path_to_example_rdsr_files()
output = main(settings=settings, file_path=rdsr_dir / "siemens_axiom_example_procedure.dcm")

print(f"Estimated PSD: {output['psd']:.1f} mGy")
```

When `settings.output_format` is set to `dict` or `json`, the result can be used programmatically. The exported result includes items such as patient/table/pad data, event geometry, correction factors, dose map data, and peak skin dose.

### 4. Run headless with pre-normalized data

If you already have normalized RDSR data in a pandas `DataFrame`, use `analyze_normalized_data_with_custom_settings_object()`.

```python
import pandas as pd
from mypyskindose import load_settings_example_json
from mypyskindose.main import analyze_normalized_data_with_custom_settings_object

settings = load_settings_example_json()
normalized_data = pd.DataFrame(...)  # your normalized RDSR data

result = analyze_normalized_data_with_custom_settings_object(
    data_norm=normalized_data,
    settings=settings,
    output_format="json",
)
```

## Useful helpers

The package includes helper functions that make exploration easier:

- `load_settings_example_json()` loads a ready-made settings template.
- `print_available_human_phantoms()` lists available human phantom meshes.
- `get_path_to_example_rdsr_files()` returns the folder containing bundled example RDSR files.
- `print_example_rdsr_files()` prints the bundled example filenames.

## Settings and modes

Important settings live in [src/mypyskindose/settings_example.json](src/mypyskindose/settings_example.json) and the settings classes under [src/mypyskindose/settings](src/mypyskindose/settings).

Common modes are:

- `plot_setup`: plot the initial geometry without loading an irradiation sequence
- `plot_event`: inspect one irradiation event
- `plot_procedure`: inspect the full event sequence
- `calculate_dose`: compute the dose map and peak skin dose estimate

Common phantom models are:

- `plane`
- `cylinder`
- `human`

## Documentation

Documentation sources live under [docs/source](docs/source), including the getting-started notebook and user guide material.

To build the HTML documentation locally from this repository:

```bash
pip install -e .
pip install -r docs/requirements.txt
python -m sphinx -b html docs/source docs/build/html
```

Then open the built site locally (path exists only after the Sphinx step above):

- `docs/build/html/index.html`

## Notes for this fork

- This repository is a modified fork of the upstream PySkinDose project.
- Upstream project page: https://github.com/rvbCMTS/PySkinDose
- This fork can evolve independently while still preserving attribution to the original project.
