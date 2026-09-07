# User guide

## GUI workflow

Launch the NiceGUI app from a development install:

```bash
python -m guiskindose --mode gui
```

Or use the console script:

```bash
guiskindose --mode gui
```

Add `--native` to open a desktop window instead of a browser tab (requires the `gui-native` extra).

Typical workflow: **Upload** (RDSR DICOM or tabular CSV/TSV/XLSX) → **Data** review → **Settings**
(phantom, physics, per-exam offsets) → **Geometry** preview → **Calculate** → **Results** (PSD, dose map)
→ **Export** (JSON, HTML/PNG dose map, rich XLSX/PDF/DOCX report).

Example RDSR files ship under `src/guiskindose/example_data/RDSR/`. In-app help on each tab mirrors
`docs/source/gui_help/` (synced into the package at build time).

## Headless / scripted use

For automation, call the package entry point with a settings object and optional RDSR path:

```python
from guiskindose import PyskindoseSettings, load_settings_example_json
from guiskindose.main import main

settings = PyskindoseSettings(settings=load_settings_example_json())
settings.mode = "calculate_dose"
settings.output_format = "dict"
settings.phantom.model = "human"
settings.phantom.human_mesh = "hudfrid"
output = main(file_path="path/to/file.dcm", settings=settings)
print(output["psd"])  # peak skin dose in mGy
```

Set `settings.output_format` to `"html"`, `"dict"`, or `"json"`. The CLI uses the same entry point
for all inputs: tabular files are dispatched to `analyze_input_file(...)` with `--input-schema`
(default `auto`), while RDSR DICOM files use `main(...)`. See
[dev-docs/INPUT_SCHEMA_DETECTION.md](../../../dev-docs/INPUT_SCHEMA_DETECTION.md)
for schema detection details.

For normalized DataFrame workflows, `analyze_normalized_data_with_custom_settings_object` remains
available when you already have vendor-normalized event tables.

## Further reading

- [Installation](install.html)
- [Background](background.html)
- Repository [AGENTS.md](../../../AGENTS.md) for maintainer-oriented API and settings reference
