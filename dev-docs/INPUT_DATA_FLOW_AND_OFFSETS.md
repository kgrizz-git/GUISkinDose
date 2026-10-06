# Data Input Flow and Offsets

This document summarizes how GUISkinDose handles RDSR inputs, normalization settings, and patient offsets, and outlines recommendations for how the GUI can better handle these parameters to improve user transparency.

Coordinate terminology lives in [VENDOR_COORDINATE_SYSTEMS.md](VENDOR_COORDINATE_SYSTEMS.md). This file explains data flow and offset hierarchy; it should not redefine axis semantics independently. For a compact required-field cheat sheet, see [INPUT_FIELD_REFERENCE.md](INPUT_FIELD_REFERENCE.md).

## 1. Original Flow Inputs

GUISkinDose accepts two primary forms of input data:
- **DICOM RDSR (`.dcm`)**: The standard input format. It runs through `rdsr_parser.py` (extracts tags) and `rdsr_normalizer.py` (standardizes the coordinate space and parameters).
- **Pre-parsed JSON files (`.json`)**: Found in `example_data/RDSR/` (e.g., `beam_collimations.json`, `table_translations.json`). These bypass the parser and normalizer entirely. They are loaded directly into Pandas DataFrames and are primarily used for testing specific geometry and mathematical edge cases.

Tabular exports (`.csv`, `.tsv`, `.xlsx`) are additionally supported via `input_adapters/`.

> **Physical units.** How each input path resolves physical units into the internal DataFrame contract
> (RDSR reads-and-asserts; tabular adapters read the unit from each column header and flag
> variable-unit quantities when the token cannot be confirmed — distances default silently to mm) is
> documented in
> [INPUT_SCHEMA_DETECTION.md → Unit handling](INPUT_SCHEMA_DETECTION.md#unit-handling).

## 1a. Tube identity (plane A / B) in tabular adapters

Every adapter must keep the X-ray tube of each event distinguishable, because kerma-meter correction factors are
keyed by `(equipment, tube)`. Tube identity is resolved from `acquisition_plane_canonical` (a DICOM CID 10003 code)
first, then from the `acquisition_plane` meaning text (`Single Plane` / `Plane A` / `Plane B`), and is otherwise
`unknown`. See the per-adapter audit in
[plans/KERMA_METER_CF_WORKFLOW_PLAN.md](plans/KERMA_METER_CF_WORKFLOW_PLAN.md#phase-0-audit-tube-identity-per-adapter).

**Radimetrics biplane split.** A Radimetrics biplane export lists one row per event with the whole-event
`Reference Point Dose (Total)` plus per-plane `Reference Point Dose (A)` / `(B)` columns (the older export spells them
`Reference_Point_Dose_(A)_mGy` / `(B)`). The adapter (`input_adapters/radimetrics.py::split_biplane_events`) treats the
file as biplane only when both per-plane columns exist and at least one row has non-zero plane B kerma (a file whose
plane B column is all zero or empty stays single-plane). Each such row is then *replaced* by a `Plane A` event and a
`Plane B` event; a plane with zero or empty kerma emits no event, so an A-only row becomes one Plane A event and a B-only
row one Plane B event. Kerma is
rescaled to the exported total, so A + B equals the original total and the total is never added on top. Per-plane
`DAP (A)` / `(B)` columns are used when present; otherwise the total DAP is shared in proportion to kerma. Fluoro time
stays on the first emitted event of a row so procedure totals are not double counted. Rows whose per-plane kerma is
missing or differs from the total by more than 1 % stay as a single total row. It keeps a valid plane code from the export (`Plane A` / `Plane B` / `Single Plane`); with no
valid code its plane is `unknown`. The warning reports how many split events replaced a plane code present in the export. Positioner angles, kVp and table positions come from the single `(RF)` columns and are shared by
both planes of a row.

**Example calibration file.** A fictional starter file ships as package data in
`src/guiskindose/example_data/kerma_meter/` (`calibration_factors_example.csv` plus a column-by-column `README.md`);
`guiskindose.get_path_to_example_kerma_meter_file()` returns its path, and Settings offers it as a download.

**Kerma-meter calibration file periods.** The calibration file (`equipment`, `tube`, `correction_factor`) may add
optional `valid_from` / `valid_to` ISO-date columns (either blank for an open end). Rows without dates behave as one
open-ended calibration. Overlapping periods for the same unit and tube are a load error (`kerma_periods.py`). Dates are
never read from exam data (PHI): the period of each exam is chosen in the GUI dialog or with
`--kerma-meter-calibration-date`; otherwise the current (no `valid_to`) or most recent period applies.

**Missing plane column.** When a Radimetrics file has no plane column and no per-plane evidence, every event still
defaults to `Single Plane` (unchanged behaviour). When the file has per-plane evidence but no plane column, the split
assigns `Plane A` / `Plane B` itself and unsplittable rows get `unknown`, never `Single Plane`.

## 2. Normalization Settings

Different X-ray manufacturers define their reference coordinates differently. `rdsr_normalizer.py` uses `normalization_settings.json` to map these to GUISkinDose's standardized coordinate system. It matches the RDSR's `Manufacturer` and `ManufacturerModelName` to apply:
- **`translation_offset`**: Shifts the machine's table coordinates to match a standard isocenter.
- **Directional Signs**: Ensures rotations (Ap1, At1, etc.) and translations move the phantom in the correct directions.
- **Field Size Mode & Detector Length**: Ensures beam spread is calculated correctly.

## 3. The "Offset Issue" (Dose Projecting Incorrectly)

If dose projects onto strange parts of the 3D human mesh (e.g., the beam hitting the head during a cardiac procedure), it is usually caused by an offset mismatch. There are **two separate offset systems** to understand:

### Table Offsets (Vendor-Specific Machine Coordinates)

**Purpose**: Transform manufacturer-specific coordinates into GUISkinDose's unified coordinate system.

**Applied**: Automatically during RDSR normalization via `normalization_settings.json`.

**Common Issue**: If `normalization_settings.json` lacks an entry for the specific scanner model (or has incorrect coordinates), the table movements will anchor around the wrong spatial origin. For instance, the Philips Allura requires an offset of `{x: -0.3, y: 105.5, z: -173.35}`, while Siemens Artis uses `{x: 0, y: 0, z: 0}`.

### Patient Offsets (User-Adjustable Positioning)

**Purpose**: Position the patient mesh on the table relative to the table's coordinate system.

**Applied**: During dose calculation via `settings.phantom.patient_offset`.

**Common Issue**: In PySkinDose, the `(0, 0, 0)` isocenter of the table corresponds to the head-end of the support table. The `patient_offset` setting (`d_lon`, `d_ver`, `d_lat` in cm) physically shifts the 3D human mesh relative to this table origin. If `d_lon` is set to `0` (the default), the patient's head is flush with the top edge of the table. If the actual patient was positioned lower down, `d_lon` must be changed.

### Which Offset to Adjust?

- **Wrong scanner model detected?** → Check Table Offset in `normalization_settings.json`
- **Patient positioned incorrectly?** → Adjust patient offset in the **Geometry** tab (sliders + live preview) or **Settings** (`d_lon`, `d_ver`, `d_lat` on Phantom in single-exam mode; **Per-exam corrections** in multi-exam — each exam has its own `meta[i].d_*`, while globals are not used for dose in multi-exam mode).

See [VENDOR_COORDINATE_SYSTEMS.md](VENDOR_COORDINATE_SYSTEMS.md) for detailed information about vendor-specific transformations and the offset hierarchy. 

## 4. GUI Improvements for Settings Handling

Currently, settings can be opaque to users running the tool, especially if defaults silently fail to match the reality of the RDSR data. To improve this, the GUI should incorporate the following features:

### A. Explicit Patient Placement (Geometry Preview)
The GUI must surface the `patient_offset` parameters (`d_lon`, `d_lat`, `d_ver`) as interactive sliders or number inputs. 
- **Recommendation**: In "Step 2 — Geometry Preview" of the GUI plan, allow users to adjust these offsets and instantly see the 3D human mesh update its position on the table using the `mode="plot_setup"` or `mode="plot_event"` visualizer. This enables visual verification of the patient's alignment *before* running the lengthy dose calculation.

### B. Manufacturer Normalization Transparency
The GUI should validate the uploaded RDSR against `normalization_settings.json`.
- **Recommendation**: During "Step 1 — Upload RDSR", if the scanner's `Manufacturer` and `Model` are not found in the normalization database, the GUI should display a clear warning: *"Warning: This scanner model is not in the normalization database. Table offsets may be incorrect."* This prevents silent failures where the dose projects incorrectly due to missing machine calibrations. The offsets should also be applied immediately, so that the Geometry tab shows the correct position of the tube and detector relative to the table.

### C. Procedure-Specific Presets
Provide a dropdown for "Procedure Presets" (e.g., Cardiac, Head/Neck, Abdominal). Selecting a preset would automatically populate the `patient_offset` with sensible defaults (e.g., sliding the patient down the table for a cardiac procedure) and select an appropriate `human_mesh`.

### D. Clear Settings Summary
Before hitting "Calculate", present a summary card showing the active phantom model, orientation, and offsets, so users know exactly what geometric assumptions are going into the calculation.
