# Custom equipment profiles (Python API, experimental)

Validated manufacturer/model coordinate profiles can be assembled into a frozen session and bound
on settings before loading **raw** input (DICOM or raw-shaped tabular). Matching exams apply all
15 effective coordinate fields before geometry calculation; dict/JSON results report the per-exam
match, inheritance notice, and session hashes under `equipment_profile_match`:

```python
from guiskindose import PyskindoseSettings, load_settings_example_json
from guiskindose.equipment_profiles import assemble_session
from guiskindose.main import analyze_input_file

session = assemble_session(documents=[{"schema_version": 1, "profiles": [...]}])
settings = PyskindoseSettings(settings=load_settings_example_json(), equipment_profile_session=session)
settings.mode = "calculate_dose"
output = analyze_input_file("study.dcm", settings=settings)
print(output["equipment_profile_match"]["notice"]["text"])
```

A settings dict (or JSON text) may carry its own sources instead under an
`equipment_profiles` block (`files` with `path`/`format`/`sheet`, `store`
with `path`/`ids`), assembled during construction — no silent ignore:

```python
config = load_settings_example_json()
config["equipment_profiles"] = {"files": [{"path": "my_profile.json"}]}
settings = PyskindoseSettings(settings=config)  # base defaults to the working directory
```

Pass `settings_base_dir` for settings files living elsewhere, and never pass
both a block and `equipment_profile_session` (refused closed). Request paths
never appear in exports or `to_settings_dict`.

Pre-transformed inputs (`normalized` tables, preparsed `.json`, bare DataFrames) refuse a
nonempty session instead of silently skipping it. In-app equipment-profile store
authoring and rich-report integration are not part of this slice (GUI session binding
and run-configuration capture replay ship separately on the equipment run-state branch).

```bash
guiskindose --file-path study.dcm --equipment-profile my_profile.json
```

Repeat `--equipment-profile` for several files (JSON, CSV, TSV, XLSX; relative paths
resolve against the working directory); `--equipment-profile-sheet` selects the XLSX
sheet by name or 0-based index. An explicit existing store database composes via
`--equipment-profile-store` (read-only, never created) with optional repeatable
`--equipment-profile-id` (current revisions regardless of the enable flag; without IDs,
all enabled current records apply). Assembly failures exit non-zero with a value-free error
before any exam input is read. Coordinate-only profiles apply; transmission content,
wildcards without promotion, and alias maps are rejected by the initial gate.

A settings file may carry its own sources under an `equipment_profiles` block
(`files` with `path`/`format`/`sheet`, `store` with `path`/`ids`); relative paths
resolve against the settings file's directory (working directory for inline
JSON/dict configs). CLI flags and the settings block compose into one candidate
assembled once and bound last — duplicate claims across sides fail closed.

A validated capture (`CapturedCoordinates`, produced from a prior run) replays one raw input
file offline through `analyze_input_file(..., equipment_capture_context=...)`
(raw DICOM or tabular) or `main(..., equipment_capture_context=...)` (DICOM only): no live session is needed or accepted, and the
returned frame calculates with the stored match mapping. The capture verifies recipe,
geometry, identity, and count — not authenticity or full raw/dose content hashes. Dose also depends on the input dose and filtration data, phantom, physics, and correction
settings. Matching captured geometry alone does not guarantee the original dose result.
Several raw files replay together through
`analyze_multiple_input_files(..., equipment_capture_contexts=[...])` with one capture
or `None` per explicit file path (positional, no guessing or globs; at most 64 files
and 10_000 aggregate retained events): every authority is validated before any file is
read, splits refuse so one file stays one exam, `None` entries normalize through the
standard baseline path, and calculation runs only after all files load.
