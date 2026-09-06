# Feature Inventory — GUISkinDose

> See also: [CODEBASE_OVERVIEW.md](CODEBASE_OVERVIEW.md) | [GUI_PLAN.md](plans/GUI_PLAN.md) | [AGENTS.md](../AGENTS.md)

_Last updated: 2026-09-06 — Phase 1 documentation assessment pass (hub-doc accuracy vs code)_

---

## 0. Harness / CI (shipped)

Repository harness features completed in [HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](plans/archive/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md) Phases 0–5 and related supply-chain work. Maintainer-visible details are in [CHANGELOG.md](../CHANGELOG.md) `[Unreleased]`.

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
| Sensitive-content and approved-asset gate | Shipped (strict) | `scripts/check_sensitive_content.py`; all current assets reviewed/hash-approved; strict hooks/CI, path-component checks, container-member-name checks, and value-safe path tokens |
| phi-scan PHI/PII text scan | Shipped (secondary) | Weekly + CSV/TSV PR workflow; pinned, quiet, reviewed 90-day baseline, new findings fail, no report/AI upload |
| Presidio advisory scan | Shipped (secondary) | Optional `privacy-scan` extra; weekly + manual workflow with local model, structured identifiers, path hashes, no report upload; noisy `PERSON` mode is targeted/local only |
| Project privacy Semgrep | Shipped (blocking) | Six source-specific leak/write/temp rules, synthetic positive/negative tests, value-safe wrapper, CI + pre-push |
| Runtime/output privacy boundary | Shipped | Opaque exam labels, de-identified serialization/export defaults, explicit identified-export opt-in, atomic Git-aware writes, private upload lifecycle, and pytest checkout guard |
| pip-audit dependency scan | Shipped | CI `dependency-audit` job |
| License compliance + `THIRD_PARTY_NOTICES.md` | Shipped | `scripts/check_licenses.py`; inventory in `dev-docs/` |
| Bandit Python SAST | Shipped | CI `bandit` job + pre-commit |
| pre-commit hooks (ruff, gitleaks, doc-freshness, license-notices) | Shipped | basedpyright on pre-push |
| Stale-pattern and path-reference doc scan | Shipped | `scripts/check_doc_freshness.py`; warnings for stale terms, CI-blocking for broken links, path references, and inventory contradictions |
| GUI help registry | Shipped | `dev-docs/help_registry.json` + `scripts/check_help_registry.py`; validates source help, mirrored bundled help, GUI references, and orphaned help pages |
| UI copy catalog and glossary | Shipped | `dev-docs/ui_copy.json`, `dev-docs/glossary.json`, `src/guiskindose/gui/ui_copy.py`, and `scripts/check_ui_copy.py` |
| Feature documentation matrix | Shipped | `dev-docs/feature_doc_matrix.json` + `scripts/check_feature_doc_matrix.py`; metadata validation plus optional doc-impact review |
| Plan lifecycle | Deferred | Closed Phase 6 — separate execution-plan directories are not needed at current team size |
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
Located in `src/guiskindose/example_data/RDSR/`:
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

Located in `src/guiskindose/phantom_data/` (full-resolution `.stl` plus optional
`*_reduced_3000t` / `*_reduced_1000t` previews). The Settings / CLI mesh list is **filesystem-discovered** —
treat the families below as the product surface, not a frozen stem census (inventory may
be trimmed without a docs rewrite of every id).

| Family | Role |
|--------|------|
| Legacy clinical (`hudfrid`, `adult_*`, `junior_*`, `senior_*`) | Long-standing baseline STLs |
| Pediatric MPFB (`ped_preschool_*`, `ped_5y_*`, `ped_10y_*`) | Age-band parametric meshes |
| Habitus MPFB (`adult_ecto_*`, `adult_endo_*`, `adult_bariatric_{sex}_{n}`) | Thin / soft / class-II series |
| `*_arms_down` | Additive arms-by-torso twins (A-pose siblings kept) |
| `*_reduced_3000t` / `*_reduced_1000t` | Low-face previews (GUI / `plot_procedure` prefer 3k; not listed as full meshes) |

Custom STL meshes can be passed as a `tuple(name, mesh.Mesh)` or a temp file path.
Legacy stem aliases still resolve. Non-clinical demo meshes are not shipped with the
package (see `tmp/phantom_data_demo_stash/README.md` on machines that kept a local copy).

Human STL meshes support body-habitus scaling via `phantom.scale_lat`,
`phantom.scale_ap`, and `phantom.scale_lon` (defaults `1.0`, clamped to
`0.5–2.0`). Scaling is applied to the human mesh before patient/table
positioning; non-uniform scaling recomputes surface normals so beam
entrance/exit filtering uses the scaled geometry. In the GUI, centimetre
readouts use left-right width, anterior-posterior thickness, and
superior-inferior length nomenclature. The left-right value is the widest
torso span in the 20–65% head-foot band, measured from feet toward head, so it
excludes the outstretched arms of shipped T-pose meshes; `scale_lat` still
scales the full lateral mesh axis.

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
| `fetch_and_append_hvl()` | HVL (mmAl) from SQLite DB by kVp + filtration; bilinear interpolation over (kVp, Cu), off-grid filtration interpolated and out-of-range clamped (warns per event); appends to DataFrame |
| `apply_below_floor_kvp_policy()` | Resolves events with kVp below the 25 kV HVL floor per policy (`snap`/`skip`/`manual`/`exam_average`) before the HVL lookup; warns per event |
| `count_below_floor_events()` | Positional indices of events with kVp below the HVL floor (drives the policy warnings + GUI pre-calc prompt) |
| `calculate_rotation_matrices()` (`helpers/`, not `geom_calc`) | Converts At1/At2/At3 angles to 3×3 rotation matrices (Rx, Ry, Rz) |
| `vector()` | Creates a vector or unit vector between two 3D points |
| `Triangle.check_intersection()` | Möller–Trumbore-style ray-triangle intersection test |

---

## 5. Dose calculation pipeline

### 5.1 Overview
`calculate_dose()` → `calculate_irradiation_event_result()` (iterative loop over events)

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
| Table + pad attenuation | k_tab | Beam attenuation through table/pad | Measured values from SQLite DB (exact-match first, then (kVp, Cu) interpolation with edge clamping; unknown device/plane fails soft to k_tab=1.0), or user-specified constant |
| Kerma-meter calibration | k_meter | Convert reported K_IRP → lab-traceable kerma | User CF table/prompt keyed by equipment × tube; fail-soft to `default_factor` (1.0). Applied once before physics corrections. |

### 5.4 Geometry optimisation
- Events with identical geometry (Tx, Ty, Tz, FS_lat, FS_long, Ap1, Ap2, Ap3, At1, At2, At3) reuse previous hit/field/k_isq results — no redundant recalculation

### 5.5 Progress reporting
- `tqdm` progress bar during calculation (terminal or notebook variant)

### 5.6 Diagnostics
- Beam-miss warnings: when an irradiation event deposits zero dose (beam does not intersect the patient phantom), a per-event WARNING identifies the event index, kVp, filtration, and field area. Configurable via `beam_miss_warn` setting (`"per_event"` / `"summary"` / `"off"`); an all-miss sentinel always fires.

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

### 7.7 Rich Report Export (`guiskindose.export`)
Single self-contained audit document from a completed dose calculation, additive to the
JSON/HTML/PNG downloads. Formats: **XLSX** (`openpyxl`), **PDF** (`reportlab`), **HTML** (stdlib),
**DOCX** (`python-docx`). All backing libraries are now core dependencies (the `export` extra is
retained as a no-op alias for backward compatibility). If a backend is somehow missing,
`writers.render_bytes()` raises `MissingExportDependencyError` with install instructions, which the
GUI surfaces as a persistent dialog.
- `collect_export_payload(source)` builds an `ExportPayload` (report-layout, separate from
  `PySkinDoseOutput.to_dict()`); normalizes single-exam dict and multi-exam `MultiExamResult` via
  `ExamView`. Sections: title/software identity, input provenance (DICOM RDSR + tabular branches),
  per-exam equipment/settings/coordinate corrections/phantom, dosimetric results (per-exam +
  cumulative), correction-factor statistics (min/max/mean/dose-weighted), warnings + discarded
  events, and dose-map images (whole-body context + zoom-to-irradiated-region).
- Writers: `render_<fmt>_bytes(payload)` / `write_<fmt>(payload, path)` + a `render_bytes`/
  `write_report` dispatcher (`export/writers/`).
- GUI: Export tab **"Rich report…"** modal (format + optional title; native save-path vs browser
  download) via `gui/export_source.build_export_source_from_gui`.
- CLI: `--export-format {xlsx,pdf,html,docx}`, `--export-path`, `--export-title` (headless path;
  rejects `--aggregate` / `--input-preview-only`).
- Plan: `dev-docs/plans/RICH_EXPORT_PLAN.md`.

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
  "schema_version": int,           # Export JSON schema (increment on incompatible shape changes)
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
| `below_floor_kvp_policy` | str | `"exam_average"` | Below-floor (kVp < 25) handling: `snap`/`skip`/`manual`/`exam_average` |
| `below_floor_kvp_manual` | float | `70.0` | Substituted kVp for `below_floor_kvp_policy="manual"` (example value; code fallback is the 25.0 HVL floor) |
| `silence_pydicom_warnings` | bool | `True` | Suppress pydicom warnings |
| `output_format` | str | `"html"` | `"html"`, `"dict"`, or `"json"` |
| `corrections_db_path` | str | `"corrections.db"` | Path to SQLite DB |
| `file_result_output_path` | str/Path | `./PlotOutputs/` | Where to save output files |

**Phantom:**
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `phantom.model` | str | — | `"plane"`, `"cylinder"`, `"human"` |
| `phantom.human_mesh` | str/tuple | — | STL name or `(name, mesh.Mesh)` |
| `phantom.scale_lat` | float | `1.0` | Human STL lateral/width scale (`0.5–2.0`) |
| `phantom.scale_ap` | float | `1.0` | Human STL AP/vertical-thickness scale (`0.5–2.0`) |
| `phantom.scale_lon` | float | `1.0` | Human STL longitudinal/head-foot scale (`0.5–2.0`) |
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

Defaults above are the code fallbacks applied when keys are absent (`settings/plot_settings.py`); `settings_example.json` is a dev template and intentionally differs.

**Normalization (per vendor, in `normalization_settings.json`):**
- `translation_offset`: x, y, z offsets (cm) between machine origin and PySkinDose origin
- `translation_direction`: sign (+/-) for each translation axis
- `rotation_direction`: sign (+/-) for Ap1, Ap2, Ap3, At1, At2, At3
- `field_size_mode`: `"CFA"` or `"ASD"`
- `detector_side_length`: active detector area side length (cm)

### 9.4 Multi-exam GUI patient offsets

| Surface | Behavior |
|---------|----------|
| **Geometry tab** | `Selected exam` dropdown; patient/table-origin sliders write `loaded_exam_meta[active]`; **Show all exams in preview** composites events (phantom stays at active exam); live preview shows a PAUSED badge when any `Full procedure` path exceeds 30 events (`procedure_live_preview_paused`) |
| **Settings → Phantom** | Global `d_lon/d_ver/d_lat` spinboxes hidden when `is_multi_exam`; C6 caption points to Geometry + Per-exam corrections; human-only body-habitus scale sliders update Geometry preview; **live 3D human-mesh preview** (no RDSR; prefers `_reduced_3000t` then `_reduced_1000t`; reflects scales, orientation, and active-exam offsets) |
| **Settings → Per-exam corrections** | Per-exam spinboxes + coordinate/table-origin overrides; active exam card highlighted |
| **Calculate tab** | Per-exam patient-offset summary (`lon/ver/lat`); table-offset line defers to Per-exam corrections |
| **Upload tab** | Click exam card → set active index and open Geometry tab |

Helpers: `geometry_preview.py` (`rdsr_df_for_geometry_preview`, `clamp_geometry_event_index`), `offset_handlers.py` (`apply_patient_offset_slider_tick`, `bump_per_exam_offsets_version`; `per_exam_offsets_version` lives on `AppState`), `summary_formatters.py`.

### 9.5 Multi-exam GUI Results tab controls

| Surface | Behavior |
|---------|----------|
| **Per-exam Accordion** | Expand exam row to view Peak Skin Dose, Air Kerma, and event count; **Show inline dose map** checkbox renders a 500px 3D dose map inline (max 5 simultaneous inline maps); **Show Dose Map** button opens full-screen dialog |
| **Visible Exams Subset Selector** | Checkboxes per exam + **All** / **None** buttons to filter which exams contribute to the Aggregate Dose Map and recompute aggregate Peak Skin Dose on the subset |

---

## 10. CLI (`main.py`)

```bash
python -m guiskindose.main [--mode headless|gui] [--file-path PATH] [--settings PATH] [--native]
```

| Argument | Description |
|----------|-------------|
| `--mode headless` | Run calculation (default) |
| `--mode gui` | Launch the NiceGUI app |
| `--file-path` | Path to RDSR `.dcm` file |
| `--settings` | Path to settings JSON file |
| `--native` | Open GUI in a native desktop window instead of a browser tab (requires `pywebview`) |

### 10.1 Native window geometry persistence

| Feature | Status | Notes |
|---------|--------|-------|
| Restore last size/position/maximized | Shipped | `~/.guiskindose/gui.json` (reads `~/.mypyskindose/gui.json` if the new file is absent); first run maximized with 75% centered normal bounds |
| Event-driven save | Shipped | Debounced commits on `resized`/`moved`; flush on native `closed` |

Implementation: `gui/window_prefs.py`, wired in `gui/app.py` when `native=True`.

Falls back to `DEVELOPMENT_PARAMETERS` from `dev_data.py` if no settings given.

---

## 11. Public Python API (`__init__.py`)

```python
from guiskindose import (
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

## 12. Open product backlog / deferred capabilities

| Feature | Status | Notes |
|---------|--------|-------|
| CSV/TSV/XLSX event-table input (normalized schema) | Shipped — Phase 1 (2026-06-09) | Python API + CLI; `normalized` schema adapter; full test suite. See `dev-docs/plans/TABULAR_RDSR_INPUT_PLAN.md`. |
| CSV/TSV/XLSX event-table input (raw RDSR-like schema + auto-detect) | Shipped — Phase 2 (2026-06-09) | `generic_rdsr_like` adapter → `rdsr_normalizer()`; `--input-schema auto`. GUI import workflow is Phase 5. |
| CSV/TSV/XLSX event-table input (Radimetrics adapter) | Shipped — Phase 3 (2026-06-10) | `radimetrics` adapter; column map + unit conversions (mGy→Gy, cm²→m², mAs→µAs); auto-detection; unknown model warning; synthetic fixture + tests. Validated against AXIOM-Artis column names only — real vendor fixture needed for production sign-off. |
| CSV/TSV/XLSX event-table input (DoseTrack adapter) | Shipped — Phase 4 (2026-06-10) | `dosetrack` adapter; Equipment Name→Manufacturer inference (`MODEL2MANUF`); ffill; Plane Code normalization; unit conversions (mGy→Gy, Gy·cm²→Gy·m², µA→mA); CFA derivation from DAP formula; Siemens/Philips filter thickness paths; Philips lat/lon swap warning; synthetic AXIOM-Artis fixture + 10 tests. Philips path untested — needs real DoseTrack XLSX. |
| CSV/TSV/XLSX event-table input (Qaelum adapter) | Stub only — Phase 5+ | Registry-wired `qaelum` schema in `input_adapters/stubs.py` raises `NotImplementedError`; excluded from auto-detection. Needs real Qaelum export fixture. |
| CSV/TSV/XLSX event-table input (DoseMonitor adapter) | Stub only — Phase 5+ | Registry-wired `dosemonitor` schema in `input_adapters/stubs.py` raises `NotImplementedError`; excluded from auto-detection. Needs real DoseMonitor export fixture. |
| CSV/TSV/XLSX event-table input (DoseWatch adapter) | Stub only — Phase 5+ | Registry-wired `dosewatch` schema in `input_adapters/stubs.py` raises `NotImplementedError`; excluded from auto-detection. Needs real DoseWatch export fixture. |
| PDF/Word/XLSX/HTML report export | Shipped (2026-07-02) | Rich Report Export — see §7.7; `guiskindose.export`. GUI modal + CLI `--export-format`. |
| Side-by-side procedure comparison | Open backlog | — |
| Settings validation with user-friendly errors | Partial | Errors surface deep in stack |
| New vendor RDSR support | Manual JSON edit required | No UI for adding vendors |
| Dose map colorscale selector at runtime | Open backlog | Current runtime colorscale is fixed to `jet` |
| Table At1/At2/At3 rotation from RDSR | Hardcoded to 0 | `data_norm["At1"] = [0]*len` |
| Ap3 (detector rotation) from RDSR | Hardcoded to 0 | `data_norm["Ap3"] = [0]*len` |
