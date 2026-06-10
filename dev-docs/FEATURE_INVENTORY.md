# Feature Inventory — MyPySkinDose

> See also: [CODEBASE_OVERVIEW.md](CODEBASE_OVERVIEW.md) | [GUI_PLAN.md](GUI_PLAN.md) | [AGENTS.md](../AGENTS.md)

_Last updated: 2026-06-09 — compiled from direct source code reading and harness phase completion_

---

## 0. Harness / CI (shipped)

Repository harness features completed in [HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md) Phases 0–5 and related supply-chain work. Maintainer-visible details are in [CHANGELOG.md](../CHANGELOG.md) `[Unreleased]`.

| Feature | Status | Notes |
|---------|--------|-------|
| Documentation catalog (`dev-docs/index.md`) | Shipped | Phase 0 |
| Doc-freshness checker (`scripts/check_doc_freshness.py`) | Shipped | Phase 1; CI-blocking for broken links and inventory contradictions |
| Root `CHANGELOG.md` + semver alignment | Shipped | Phase 2 |
| `compileall` in CI | Shipped | Phase 2 |
| GitHub Actions v4/v5 | Shipped | Phase 2 |
| `python -m build` in CI (`package-build` job) | Shipped | Phase 3 |
| Dependabot (pip + Actions) | Shipped | Phase 3 |
| Package layering docs + structural tests | Shipped | Phase 4; `test_architecture_layers.py` |
| GUI smoke tests (`tests/gui/`) | Shipped | Phase 5; NiceGUI user simulation, `gui-smoke` CI job |
| Basedpyright strict typecheck | Shipped | CI `typecheck` job |
| Gitleaks secret scanning | Shipped | `.github/workflows/gitleaks.yml` |
| pip-audit dependency scan | Shipped | CI `dependency-audit` job |
| License compliance + `THIRD_PARTY_NOTICES.md` | Shipped | `scripts/check_licenses.py`; inventory in `dev-docs/` |
| Bandit Python SAST | Shipped | CI `bandit` job + pre-commit |
| pre-commit hooks (ruff, gitleaks, doc-freshness, license-notices) | Shipped | basedpyright on pre-push |
| Stale-pattern scan (advisory) | Shipped | Warnings only; release gate before semver bump (see `HARNESS_ENGINEERING.md`) |
| Plan lifecycle (`dev-docs/exec-plans/`) | Deferred | Closed Phase 6 — not needed at current team size |
| `references/` external library index | Partial | `dev-docs/references/` stub; expand before next major dependency review |

---

## 1. Data input

### 1.1 RDSR file loading
- Load DICOM RDSR (`.dcm`) file via `pydicom`
- Load pre-parsed RDSR data from `.json` file (skips parsing step)
- Fall back to bundled example RDSR files if no path given
- Suppress pydicom warnings (configurable)
- Remove rows with invalid kVp = 0 (configurable)

### 1.2 Bundled example RDSR files
Located in `src/mypyskindose/example_data/RDSR/`:
- `philips_allura_clarity_u104.dcm`
- `philips_allura_clarity_u601.dcm`
- `siemens_axiom_artis.dcm`
- `siemens_axiom_example_procedure.dcm`

### 1.3 RDSR parsing (`rdsr_parser.py`)
Extracts per-event data from DICOM tags into a `pd.DataFrame`:
- Manufacturer and model name
- Irradiation event type (fluoroscopy / stationary acquisition)
- Acquisition plane (single plane / plane A / plane B)
- Positioner primary angle (Ap1), secondary angle (Ap2)
- Table longitudinal, height, and lateral positions
- Distance source-to-detector, source-to-isocenter
- kVp, dose at reference point (K_IRP in Gy)
- X-ray filter materials (Al, Cu) and thicknesses (min/max)
- Collimated field area or shutter distances (left/right/top/bottom)
- Detector size (from DICOM comment field for Siemens units)

### 1.4 RDSR normalisation (`rdsr_normalizer.py`)
Converts raw parsed data to a consistent coordinate system:
- Applies vendor-specific translation offsets, direction signs, rotation directions
- Normalises all distances to cm
- Computes DSD, DSI, DID, DSIRP
- Computes field size (FS_lat, FS_long) in two modes:
  - `CFA` — collimated field area (√area used as side length)
  - `ASD` — actual shutter distance (scaled to detector plane)
- Normalises kVp and K_IRP (converts Gy → mGy)
- Parses Cu and Al filter thicknesses per event
- Computes table rotation matrices (Rx, Ry, Rz) for At1/At2/At3

### 1.5 Supported vendors / normalization profiles
Defined in `normalization_settings.json`:
- **Siemens AXIOM-Artis** — CFA field size mode, no translation offset
- **Philips Allura Clarity** — ASD field size mode, has translation offset

New vendors can be added by editing `normalization_settings.json`.

---

## 2. Phantom models

### 2.1 Patient phantoms

| Model | Description | Skin cells | Normal vectors |
|-------|-------------|-----------|----------------|
| `plane` | 2D rectangular flat grid | Yes | No |
| `cylinder` | Elliptic cylinder | Yes | Yes |
| `human` | STL mesh loaded from file | Yes | Yes |

### 2.2 Human mesh files
Located in `src/mypyskindose/phantom_data/`:

| Mesh name | Description |
|-----------|-------------|
| `hudfrid` | Adult male, optimised for skin dose |
| `adult_male` | Adult male |
| `adult_female` | Adult female |
| `junior_male` | Junior male |
| `junior_female` | Junior female |
| `*_reduced_1000t` | Low-resolution variants of each (faster, used in `plot_procedure`) |

Custom STL meshes can be passed as a `tuple(name, mesh.Mesh)` or a temp file path.

### 2.3 Support objects

| Model | Description |
|-------|-------------|
| `table` | Rectangular cuboid patient support table |
| `pad` | Rectangular cuboid support pad (sits on top of table) |

### 2.4 Phantom dimensions (all configurable, all in cm)

**Plane phantom:**
- `plane_length` (default 120), `plane_width` (default 40)
- `plane_resolution`: `"sparse"` (1 pt/cm) or `"dense"` (2 pts/cm)

**Cylinder phantom:**
- `cylinder_length` (default 150)
- `cylinder_radii_a` (default 20, width direction)
- `cylinder_radii_b` (default 10, thickness direction)
- `cylinder_resolution`: `"sparse"` or `"dense"`

**Table:**
- `table_length` (default 281.5), `table_width` (default 45), `table_thickness` (default 5)

**Pad:**
- `pad_length` (default 281.5), `pad_width` (default 45), `pad_thickness` (default 4)

### 2.5 Patient positioning
- Patient orientation: `head_first_supine` or `feet_first_supine`
- Patient offset from table isocenter (cm): `d_lon`, `d_ver`, `d_lat`
- Phantom placed on top of pad, offset applied, reference position saved
- Per-event repositioning: table rotations (At1/At2/At3) + translations (Tx/Ty/Tz) applied

---

## 3. Beam model (`beam_class.py`)

- Pyramid-shaped beam: apex = X-ray source, base = detector plane
- Constructed from RDSR angles: Ap1 (LAT rotation about Z), Ap2 (LON rotation about X), Ap3 (detector rotation about Y)
- Applies field collimation (FS_long, FS_lat) to beam corners
- Positions detector at correct DID distance with correct dimensions
- `plot_setup=True` mode: zero-angle beam for debugging
- `check_hit(patient)`: dot-product test against 4 face normals → boolean hit list
  - For 3D phantoms (cylinder, human): removes exit-path cells using normal vectors

---

## 4. Geometry calculations (`geom_calc.py`)

| Function | What it does |
|----------|-------------|
| `position_patient_phantom_on_table()` | Places phantom on table with orientation + offset, saves reference position |
| `calculate_field_size()` | Computes FS_lat/FS_long from CFA or ASD mode |
| `scale_field_area()` | Scales field area from detector plane to each skin cell (distance-squared scaling) |
| `check_new_geometry()` | Detects which events have changed geometry vs. previous event (avoids redundant recalculation) |
| `check_table_hits()` | Ray-triangle intersection: determines which skin cells have beam passing through table/pad |
| `fetch_and_append_hvl()` | Looks up HVL (mmAl) from SQLite DB by kVp + filtration, appends to DataFrame |
| `calculate_rotation_matrices()` | Converts At1/At2/At3 angles to 3×3 rotation matrices (Rx, Ry, Rz) |
| `vector()` | Creates a vector or unit vector between two 3D points |
| `Triangle.check_intersection()` | Möller–Trumbore-style ray-triangle intersection test |

---

## 5. Dose calculation pipeline

### 5.1 Overview
`calculate_dose()` → `calculate_irradiation_event_result()` (recursive, one call per event)

### 5.2 Per-event steps
1. Check if geometry changed since last event (`check_new_geometry`)
2. If new geometry:
   - Create `Beam` for event
   - Reposition patient, table, pad (`phantom.position()`)
   - `Beam.check_hit()` → hit list
   - `check_table_hits()` → table-hit list
   - `scale_field_area()` → field area per hit cell
   - `calculate_k_isq()` → inverse-square-law correction
3. Apply corrections and accumulate dose (`add_corrections_and_event_dose_to_output`)

### 5.3 Correction factors

| Factor | Symbol | Physics | Method |
|--------|--------|---------|--------|
| Inverse-square law | k_isq | `(d_IRP / d_skin)²` | Computed per cell from source distance |
| Backscatter | k_bs | Benmakhlouf et al. polynomial (kVp, HVL, field size) | Cubic spline interpolation over 5 field sizes |
| Medium | k_med | Air kerma → tissue dose (μ_en/ρ ratio) | Lookup table in SQLite DB by kVp, HVL, field size |
| Table + pad attenuation | k_tab | Beam attenuation through table/pad | Measured values from SQLite DB, or user-specified constant |

### 5.4 Geometry optimisation
- Events with identical geometry (Tx, Ty, Tz, FS_lat, FS_long, Ap1, Ap2, Ap3, At1, At2, At3) reuse previous hit/field/k_isq results — no redundant recalculation

### 5.5 Progress reporting
- `tqdm` progress bar during calculation (terminal or notebook variant)

---

## 6. Database (`corrections.db` + `db_connect.py`)

SQLite database with tables:

| Table | Contents |
|-------|---------|
| `hvl_combined` | HVL (mmAl) by kVp and filtration (inherent + added Al + added Cu) |
| `correction_medium_and_backscatter` | k_med (μ_en quotient) by kVp, HVL, field side length |
| `correction_table_and_pad_attenuation` | Measured k_tab by kVp, Cu/Al filtration, device model, acquisition plane |
| `device_info` | Device-specific metadata |

---

## 7. Visualisation / rendering

### 7.1 Run modes

| Mode | What is rendered | RDSR needed |
|------|-----------------|-------------|
| `plot_setup` | Phantom + table + pad + beam at zero angulation | No (uses event 0 geometry only) |
| `plot_event` | Full 3D geometry for one specific event | Yes |
| `plot_procedure` | All events with interactive slider | Yes |
| `calculate_dose` | 3D dose map coloured by skin dose | Yes |

### 7.2 3D scene elements

| Element | Colour | Type |
|---------|--------|------|
| Patient phantom | `#CE967C` (skin tone) | `Mesh3d` |
| Support table | `#D3D3D3` (light grey) | `Mesh3d` + wireframe |
| Support pad | `slateblue` | `Mesh3d` + wireframe |
| X-ray beam | `red` (semi-transparent, opacity 0.4) | `Mesh3d` + wireframe |
| X-ray detector | `#D3D3D3` | `Mesh3d` + wireframe |
| X-ray source | `#D3D3D3` | Point marker |
| Dose map | `jet` colorscale (configurable) | `Mesh3d` with intensity |

### 7.3 Interactivity in plots

| Feature | Available in |
|---------|-------------|
| Rotate 3D scene (orbit drag) | All modes |
| Zoom | All modes |
| Pan | All modes |
| Hover tooltip: XYZ coordinates | All geometry plots |
| Hover tooltip: skin dose (mGy) + XYZ | Dose map |
| Event slider (step through all events) | `plot_procedure` |
| Slider transition animation (300ms ease) | `plot_procedure` |

### 7.4 Appearance settings

| Setting | Options | Default |
|---------|---------|---------|
| Dark mode | `True` / `False` | `True` |
| Interactive vs. static | `True` / `False` | `True` |
| Notebook mode (resized for Jupyter) | `True` / `False` | `False` |
| Dose map colorscale | Any Plotly built-in (jet, viridis, etc.) | `jet` |
| Plot dose map after calculation | `True` / `False` | `True` |
| Max events for patient inclusion in procedure | int | 10 |
| Which event to show in `plot_event` | int index | 0 |

### 7.5 Static dose map export
When `interactivity=False`:
- Renders 4 static PNG images from preset camera angles: right, back, left, front
- Camera presets: `PLOT_EYE_RIGHT`, `PLOT_EYE_BACK`, `PLOT_EYE_LEFT`, `PLOT_EYE_FRONT`
- Saves to `PlotOutputs/` directory
- Opens images with PIL if not in notebook mode
- Shows combined image in notebook mode

### 7.6 Plot save locations
- Interactive HTML: `PlotOutputs/<mode>.html`
- Static PNG: `PlotOutputs/right.png`, `back.png`, `left.png`, `front.png`
- Output directory configurable via `file_result_output_path`

---

## 8. Output formats

### 8.1 `output_format` options

| Value | What is returned |
|-------|-----------------|
| `"html"` | Plots rendered/saved, `None` returned from `main()` |
| `"dict"` | Python dict (see structure below) |
| `"json"` | JSON string of the same dict |

### 8.2 Output dict structure (`to_dict()`)

```
{
  "psd": float,                    # Peak skin dose in mGy
  "air_kerma": float,              # Total IRP air kerma in mGy
  "patient": {
    "patient_type": str,           # "plane" / "cylinder" / "human"
    "patient": {
      "human_phantom": str,        # mesh name (human only)
      "r_ref": [[x,y,z], ...],     # reference skin cell positions
      "patient_skin_cells": {x,y,z lists},
      "triangle_vertex_indices": {i,j,k lists}
    },
    "orientation": str,
    "offsets": {long, vert, lat}
  },
  "table": {
    "table_surface": {x,y,z},
    "triangle_vertex_indices": {i,j,k},
    "table_length": float
  },
  "pad": {
    "pad_surface": {x,y,z},
    "triangle_vertex_indices": {i,j,k}
  },
  "dose_map": [(cell_index, dose_mGy), ...],  # sparse, only non-zero cells
  "corrections": {
    "correction_value_index": [[cell indices per event], ...],
    "backscatter": [[k_bs per hit per event], ...],
    "medium": [k_med per event, ...],
    "table": [k_tab per event, ...],
    "inverse_square_law": [[k_isq per hit per event], ...]
  },
  "events": {
    "number_of_events": int,
    "rotation": {x, y, z rotation matrices per event},
    "translation": {x, y, z per event},
    "beam": {positions, vertex_indices, trace_order, setup},
    "detector": {positions, vertex_indices, trace_order, setup},
    "phantom_object_trace_order": [int list]
  }
}
```

---

## 9. Settings system

### 9.1 Settings loading
Settings can be provided as:
- JSON file path (string)
- JSON string
- Python dict
- `PyskindoseSettings` object

Falls back to `settings_example.json` if nothing provided.

### 9.2 All configurable settings

**General:**
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `mode` | str | `"plot_event"` | Run mode |
| `rdsr_filename` | str | — | RDSR filename (used when no `file_path` passed) |
| `estimate_k_tab` | bool | `True` | Use estimated k_tab instead of measured |
| `k_tab_val` | float | `0.8` | Estimated table transmission (0–1) |
| `inherent_filtration` | float | `3.1` | X-ray tube inherent filtration (mmAl) |
| `remove_invalid_rows` | bool | `False` | Drop events with kVp = 0 |
| `silence_pydicom_warnings` | bool | `True` | Suppress pydicom warnings |
| `output_format` | str | `"html"` | `"html"`, `"dict"`, or `"json"` |
| `corrections_db_path` | str | `"corrections.db"` | Path to SQLite DB |
| `file_result_output_path` | str/Path | `./PlotOutputs/` | Where to save output files |

**Phantom:**
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `phantom.model` | str | — | `"plane"`, `"cylinder"`, `"human"` |
| `phantom.human_mesh` | str/tuple | — | STL name or `(name, mesh.Mesh)` |
| `phantom.patient_orientation` | str | — | `"head_first_supine"` or `"feet_first_supine"` |
| `phantom.patient_offset.d_lon` | float | 0 | Longitudinal offset (cm) |
| `phantom.patient_offset.d_ver` | float | 0 | Vertical offset (cm) |
| `phantom.patient_offset.d_lat` | float | 0 | Lateral offset (cm) |
| `phantom.dimension.*` | float/str | see §2.4 | All phantom/table/pad dimensions |

**Plot:**
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `plot.interactivity` | bool | `True` | Interactive HTML vs. static PNG |
| `plot.dark_mode` | bool | `True` | Dark background |
| `plot.notebook_mode` | bool | `False` | Optimise sizing for Jupyter |
| `plot.plot_dosemap` | bool | `True` | Show dose map after calculation |
| `plot.max_events_for_patient_inclusion` | int | 10 | Hide patient in procedure above this |
| `plot.plot_event_index` | int | 0 | Which event to show in `plot_event` |

**Normalization (per vendor, in `normalization_settings.json`):**
- `translation_offset`: x, y, z offsets (cm) between machine origin and PySkinDose origin
- `translation_direction`: sign (+/-) for each translation axis
- `rotation_direction`: sign (+/-) for Ap1, Ap2, Ap3, At1, At2, At3
- `field_size_mode`: `"CFA"` or `"ASD"`
- `detector_side_length`: active detector area side length (cm)

### 9.3 Settings printing
`settings.print_parameters()` — prints colour-formatted summary of all settings to terminal using Rich.

---

## 10. CLI (`main.py`)

```bash
python -m mypyskindose.main [--mode headless|gui] [--file-path PATH] [--settings PATH] [--native]
```

| Argument | Description |
|----------|-------------|
| `--mode headless` | Run calculation (default) |
| `--mode gui` | Launch the NiceGUI app |
| `--file-path` | Path to RDSR `.dcm` file |
| `--settings` | Path to settings JSON file |
| `--native` | Open GUI in a native desktop window instead of a browser tab (requires `pywebview`) |

Falls back to `DEVELOPMENT_PARAMETERS` from `dev_data.py` if no settings given.

---

## 11. Public Python API (`__init__.py`)

```python
from mypyskindose import (
    PyskindoseSettings,
    load_settings_example_json,          # → dict
    print_available_human_phantoms,      # prints STL names
    print_example_rdsr_files,            # prints .dcm filenames
    get_path_to_example_rdsr_files,      # → Path
    analyze_data,                        # core orchestration
    Beam,                                # beam class
    Phantom,                             # phantom class
    rdsr_parser,                         # raw DICOM parser
    rdsr_normalizer,                     # RDSR normaliser
    check_new_geometry,                  # geometry change detector
    fetch_and_append_hvl,                # HVL lookup
    position_patient_phantom_on_table,   # phantom positioning
    scale_field_area,                    # field area scaling
    plot_geometry,                       # geometry plot dispatcher
)
```

`main()` also accepts pre-normalised DataFrames via `analyze_normalized_data_with_custom_settings_object()`.

---

## 12. Features NOT yet implemented

| Feature | Status | Notes |
|---------|--------|-------|
| CSV/TSV/XLSX event-table input (normalized schema) | Shipped — Phase 1 (2026-06-09) | Python API + CLI; `normalized` schema adapter; full test suite. See `dev-docs/TABULAR_RDSR_INPUT_PLAN.md`. |
| CSV/TSV/XLSX event-table input (raw RDSR-like schema + auto-detect) | Shipped — Phase 2 (2026-06-09) | `generic_rdsr_like` adapter → `rdsr_normalizer()`; `--input-schema auto`. GUI import workflow is Phase 5. |
| CSV/TSV/XLSX event-table input (Radimetrics, DoseTrack adapters) | Planned — Phases 3–4 | Gated on real vendor export fixtures. |
| PDF/Word report export | Not implemented | Planned in GUI Phase 3 |
| Side-by-side procedure comparison | Not implemented | — |
| Settings validation with user-friendly errors | Partial | Errors surface deep in stack |
| New vendor RDSR support | Manual JSON edit required | No UI for adding vendors |
| Dose map colorscale selector at runtime | Not implemented | Hardcoded to `jet` |
| Table At1/At2/At3 rotation from RDSR | Hardcoded to 0 | `data_norm["At1"] = [0]*len` |
| Ap3 (detector rotation) from RDSR | Hardcoded to 0 | `data_norm["Ap3"] = [0]*len` |
