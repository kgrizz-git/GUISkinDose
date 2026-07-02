NEEDS REVIEW

# Rich Report Export Spec

## Goal

Add a "Rich Export" action to the GUI and (optionally) the CLI that produces a self-contained report file (XLSX, PDF, DOCX, or HTML bundle) containing:

- Dose images (Plotly figures rendered to embedded PNG/SVG)
- All input parameters (settings, phantom, equipment, normalizations, offsets)
- All result values (PSD, total air kerma, correction factors, event counts, warnings)
- Full provenance (file names, number of exams, discarded events)

The user chooses **filename**, **location**, and **format** via a native or NiceGUI save dialog with intelligent defaults.

## Motivations / User Stories

- **Clinical physicist:** "I need to save a complete audit trail for each case — the images, the settings I used, and the results — in one file I can archive or email."
- **Researcher:** "Give me an XLSX with all the data so I can compare across cases in a spreadsheet."
- **QA reviewer:** "Show me which events were discarded and what warnings were raised so I can verify the calculation was sound."

## Output Formats

| Format | Extension | Priority | Notes |
|--------|-----------|----------|-------|
| XLSX | `.xlsx` | P0 | Multi-sheet workbook with images embedded as sheet backgrounds or linked. |
| PDF | `.pdf` | P0 | Print-layout report with embedded images, tables, and metadata. |
| HTML bundle | `.html` or `.zip` | P1 | Self-contained HTML with inline SVG/PNG images (base64). |
| DOCX | `.docx` | P2 | Word document with images and tables; lower priority. |

## Content: Every Report Must Include

### 1. Title / Header
- Application name and version (from `pyproject.toml`)
- Date and time of export
- Report title (auto-generated: `{filename}_report_{date}` or user-supplied)

### 2. Input Provenance
- File name(s) of all input files loaded (RDSR `.dcm`, CSV/TSV/XLSX)
- Number of exams detected
- Number of irradiation events total (across all exams)
- Input schema used (if tabular: `normalized`, `generic_rdsr_like`, `radimetrics`, `dosetrack`)
- Sheet name (if XLSX multi-sheet input)

### 3. Settings Snapshot
- Mode used (`calculate_dose`, `plot_setup`, etc.)
- Phantom model (`plane`, `cylinder`, `human`)
- Human mesh name (if applicable, e.g. `hudfrid`, `adult_male`)
- Body habitus scaling factors (scale_lat, scale_ap, scale_lon)
- Output format setting
- `below_floor_kvp_policy` and its effective value per event
- Any other non-default settings

### 4. Normalization & Coordinate Info
- Manufacturer and equipment model name detected
- Vendor-specific normalizations applied (Siemens floor-stand flip, Philips kV_Ref fix, GE lateral/longitudinal swap, etc.)
- Per-exam coordinate corrections:
  - Tx ↔ Tz swap toggle (per-exam)
  - Ap1 ×−1 toggle (per-exam)
  - Ap2 ×−1 toggle (per-exam)
- Table-origin:
  - Detected table offset (per-exam, if available)
  - Table-origin override (per-exam, if set)
  - Effective table origin used for calculation
- Patient offsets (d_lon, d_ver, d_lat) per exam

### 5. Phantom & Geometry
- Phantom model and mesh selection
- Table model and dimensions (if plane/cylinder)
- Pad model
- Whether any events had zero intersection (missed the phantom entirely)

### 6. Calculation Results — Summary (All metrics reported both per-exam and cumulative)

| Metric | Value (Per-Exam & Cumulative) | Unit |
|--------|-------------------------------|------|
| Peak Skin Dose (PSD) | (value) | mGy |
| Reference Point Dose / Total Air Kerma ($K_{IRP}$ / $K_{a,r}$) | (value) | mGy |
| Total DAP (Dose-Area Product) | (value) | mGy·cm² |
| Total Fluoroscopy Time | (value) | s (or min:s) |
| Number of "acquisitions" (cine / acquisition event types) | (count) | — |
| Number of events processed | (count) | — |
| Number of events discarded / failed | (count) | — |

### 7. Correction Factors (per-exam and/or global averages)

| Correction | Average value | Range (min–max) |
|------------|--------------|-----------------|
| Backscatter factor (BSF) | (float) | (min–max) |
| Table attenuation factor (TAF) | (float) | (min–max) |
| Pad attenuation factor | (float) | (min–max) |
| k_tab (filtration correction) | (float) | (min–max) |
| k_iso (isocenter distance correction) | (float) | (min–max) |
| k_r (reference point correction) | (float) | (min–max) |
| k_l (lateral calibration correction) | (float) | (min–max) |

### 8. Warnings & Discarded Events
- Total number of discarded events, with reason codes (e.g. "below floor KVP", "zero intersection", "missing data")
- Full list of warning messages raised during calculation
- Any events where HVL interpolation clamped or used fallback policies
- Beam-miss warnings (no intersection with phantom)

### 9. Dose Map Images

- **Single-exam mode:** One dose-map image (dorsal view, default orientation).
- **Multi-exam mode:**
  - One composite dose-map image showing accumulated dose across all exams.
  - One dose-map image per exam (labeled with exam number/name).
- Each image should include a colorbar and axis labels (matching the interactive Plotly figure style).
- Render at sufficient resolution for print (300 DPI equivalent).

## Intelligent Default Filename

Default export path:

```
{input_file_stem}_{date}_{time}.{ext}
```

- `input_file_stem`: stem of the first input file loaded (sanitized).
- `date`: `YYYY-MM-DD`.
- `time`: `HHMMSS`.
- `ext`: chosen format extension.

Example: `case001_2026-07-01_143022.xlsx`

Default save directory: the directory of the first input file, or the user's Documents folder if no input file path is available.

## GUI Interaction

- **Trigger:** An "Export report…" button on the **Results tab** and/or a top-level **Export → Rich report** menu item.
- **Dialog:** A modal or popup with:
  1. **Format selector:** dropdown (XLSX, PDF, HTML, DOCX) with brief description of each.
  2. **File path:** editable text field pre-filled with the default path, plus a **Browse…** button.
  3. **Content toggles** (optional, v2): checkboxes for "Include images", "Include full settings", "Include per-event data", etc.
  4. **Export** button to generate and save (with progress indicator for large procedures).
  5. **Cancel** / **Close**.
- After export: show a success notification with a **Open file** / **Open containing folder** action.

## CLI option (v2)

```bash
python -m mypyskindose --mode export --input file.dcm --export-format xlsx --export-path ./report.xlsx
```

The export mode reuses a previously completed calculation from in-memory state, or can run the full pipeline + export in one command.

## Multi-exam specifics

- For multi-exam calculations, each per-exam section (settings, corrections, images) is clearly labeled by exam index and (where available) exam name.
- The composite dose map is the primary result image; per-exam maps are secondary.
- Per-exam correction factor tables are reported side-by-side or in sub-tables.

## Non-goals (v1)

- Streaming or incremental export during calculation.
- Export of the full per-event data table (rows of individual irradiation events). A separate "Export event table" feature already exists.
- Direct PACS push or DICOM SR export (separate TODO item).
- 3D mesh export (separate TODO item).

## Open Questions

1. **PDF generation library:** `reportlab` vs `weasyprint` vs `fpdf2` vs `playwright` (headless browser PDF). Evaluate dependency weight, HTML→PDF quality, and image support.
2. **XLSX image embedding:** `openpyxl` supports inline images (anchored drawings) but not background fills; confirm approach.
3. **Plotly image export:** `plotly.io.write_image` requires `kaleido` or `orca`. Ensure `kaleido` is an optional dependency and gracefully handled if missing.
4. **Multi-exam page count:** For very large procedures with many exams, consider limiting per-exam images to prevent multi-hundred-page PDFs.
5. **Per-event correction detail:** Should the report include per-event correction values in a table, or only the exam-level averages? Spec currently says averages only; revisit based on user feedback.

## Implementation Phases (sketch)

| Phase | Scope |
|-------|-------|
| **Phase 1** | Export data-collection module: gather all of the above into a single `ExportPayload` dataclass. Add unit tests. |
| **Phase 2** | XLSX writer: multi-sheet workbook with event summary, settings, corrections, and embedded dose-map images. |
| **Phase 3** | PDF writer: reportlab-based layout with title page, tables, and images. |
| **Phase 4** | GUI export dialog: file chooser, format picker, progress, success notification. |
| **Phase 5** | HTML bundle writer; CLI `--export-format` flag. |
| **Phase 6** | DOCX writer (if demand warrants). |
| **Phase 7** | Polish: right-to-left support, localization, accessibility tagging in PDF. |

## Review Commentary: Gaps, Errors, and Suggested Improvements

This section provides an architectural, dosimetric, and codebase-aligned review of the specification above against current MyPySkinDose behavior and clinical physics requirements.

### 1. Critical Correction Factors Mismatch (Section 7)
Section 7 currently contains inaccurate correction factor names and omissions that contradict MyPySkinDose physics (`src/mypyskindose/corrections.py`, `constants.py`, and `format_export_data.py`):
- **Non-existent factors listed:** The spec lists `k_iso (isocenter distance correction)`, `k_r (reference point correction)`, and `k_l (lateral calibration correction)`. These parameters do not exist in the MyPySkinDose codebase or calculation pipeline.
- **Missing Medium Correction (`k_med`):** The reference point medium correction factor (`k_med`, dosimetric conversion from air kerma to water/tissue dose at the reference plane, `OUTPUT_KEY_CORRECTION_MEDIUM`) is evaluated for every event but is **completely omitted** from Section 7.
- **Misnamed Inverse Square Law Correction (`k_isq`):** In MyPySkinDose, relative source-to-skin vs. source-to-reference distance correction is denoted `k_isq` (`OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW`, labeled `ISQ` in GUI table summaries), not `k_iso`.
- **Table and Pad Attenuation Separation:** Section 7 lists `Table attenuation factor (TAF)`, `Pad attenuation factor`, and `k_tab (filtration correction)` as three separate rows. In MyPySkinDose, table and pad attenuation are measured together and combined into `k_tab` (loaded from `correction_table_and_pad_attenuation.csv` column `k_patient_support`, `OUTPUT_KEY_CORRECTION_TABLE`). Furthermore, `k_tab` represents support attenuation, not "filtration correction" (filtration $Cu/Al$ is used along with $kVp$ to interpolate beam quality $HVL$ for `k_bs` and `k_tab` lookup).
- **Averaging Methodology:** Reporting simple unweighted arithmetic means across irradiation events can distort clinical audits. The specification should mandate reporting both the range (min–max) and **dose-weighted averages** ($\frac{\sum K_{i} \cdot k_{i}}{\sum K_{i}}$, where $K_i$ is reference point air kerma $K_{a,r}$) so that high-dose events are appropriately weighted.

### 2. Peak Skin Dose & Dosimetric Metrics Gaps (Section 6)
- **Per-Exam & Cumulative Reporting Requirement:** To support comprehensive clinical audits and interventional radiation safety reviews, every primary summary metric—specifically **Peak Skin Dose (PSD)**, **Reference Point Dose ($K_{a,r}$ / $K_{IRP}$)**, **Total Dose-Area Product (DAP)**, **Total Fluoroscopy Time**, and the **Number of "acquisitions"** (irradiation event types with "acquisition" or similar in their DICOM/tabular event type name, such as *Stationary Acquisition* or *Stepped Acquisition*, as opposed to individual fluoroscopy pulses or exposures)—must be explicitly reported **both per-exam and cumulatively across all exams**.
- **Spatial Provenance of PSD:** Section 6 lists Peak Skin Dose (PSD) only as a numerical value in mGy. For clinical intervention and follow-up, the report MUST include the **3D spatial coordinate $(X, Y, Z)$ and/or anatomical region** on the patient mesh where the peak skin dose occurred. For multi-exam procedures, both per-exam PSD peak locations and the cumulative PSD peak location must be recorded, as the cumulative hot spot may occur at a different anatomical vertex than individual exam peaks.
- **Reference Air Kerma Explicit Notation:** Clarify that "Total Air Kerma at Reference Point" (aka Reference Point Dose) corresponds to cumulative Interventional Reference Point air kerma ($K_{a,r}$ or $K_{IRP}$), reported as the sum across all valid irradiation events in mGy (reported both per-exam and total cumulative).
- **Acquisition Mode Breakdown:** RDSR events represent either Fluoroscopy (continuous/pulsed) or Digital Subtraction Angiography / Spot / Cine acquisitions. The summary table should break down event counts, total reference air kerma, and DAP by acquisition mode (e.g., *Total Events: 120 (85 Fluoro, 35 Cine Acquisition)*) to show respective contribution to skin dose.

### 3. Multi-Exam Equipment & Provenance Tracking (Sections 2 & 4)
- **Per-Exam Equipment Breakdown:** Section 4 lists equipment manufacturer and model name as singular. In clinical practice, multi-exam procedures may be performed across different fluoroscopy suites or scanner models (e.g., Exam 1 on Siemens AXIOM-Artis, Exam 2 on Philips AlluraXper). The specification must require tracking manufacturer, model name, station name, and software versions **per exam ID**.
- **Metadata Confidence & Tabular Origin:** Note whether equipment metadata originated from explicit DICOM RDSR tags (`(0008, 0070) Manufacturer`, `(0008, 1090) Model Name`) or was inferred from tabular schemas (e.g., `MODEL2MANUF` mapping in DoseTrack adapters). Include upload timestamp, file schema (`normalized`, `generic_rdsr_like`, `radimetrics`, `dosetrack`), and sheet name for multi-sheet XLSX inputs.

### 4. Coordinate Conventions, Offsets & Phantom Resolution (Sections 4 & 5)
- **Explicit Coordinate Sign Conventions:** When reporting table offsets (`table_origin_override`, `table_offset_lon/lat/ver`), patient offsets (`d_lon`, `d_ver`, `d_lat`), and normalization overrides (`Tx↔Tz swap`, `Ap1×−1`, `Ap2×−1`, and GE `swap_lateral_longitudinal`), the report should explicitly define the underlying coordinate system (+X = lateral left, +Y = vertical AP pointing down, +Z = longitudinal cranial for head-first supine positioning) to eliminate ambiguity.
- **Phantom Physical & Mesh Resolution:** In addition to habitus scaling factors (`scale_lat`, `scale_ap`, `scale_lon`), Section 5 should record physical dimensions (`patient.dimension`, table/pad length/width/thickness) and the **computational mesh resolution** (total vertices `len(patient.r)` and triangle faces `len(patient.ijk)`). This confirms for medical physicists the grid granularity over which dose accumulation was computed.

### 5. Settings Snapshot Completeness (Section 3)
- **Missing Physics & Fallback Parameters:** Section 3 omits key physics parameters that directly impact dose calculations: `estimate_k_tab` (boolean flag to use static fallback table attenuation), `k_tab_val` (fallback attenuation value, default 0.8), `corrections_db_path` (SQLite database filename/version), and effective KVP override values when `below_floor_kvp_policy` is set to `manual`.
- **Software Versioning:** Explicitly record the exact package version string from `pyproject.toml` and runtime execution mode (`gui` or `cli`).

### 6. Plot Images & Visual Projections (Section 9 & Open Question 3)
- **Multi-Angle Projections:** Section 9 specifies a single "dorsal view, default orientation" for single-exam dose maps. Because high skin doses frequently occur on anterior (cardiology) or lateral (interventional neuroradiology) surfaces, a single dorsal view will obscure hot spots. The spec should mandate capturing at least two orthogonal projections (e.g., Posterior/Dorsal and Anterior/Ventral) or auto-centering camera gaze on the PSD vertex.
- **Plotly Image Export Mechanics:** For Open Question 3 (`kaleido` vs. `orca`), note that `src/mypyskindose/gui/figures.py` already implements `make_dosemap_png()` using `fig.to_image(format="png")` with `kaleido`. If `kaleido` is not installed in lightweight web environments, the system should gracefully fall back to the standalone interactive HTML bundle export.

### 7. Architectural & Library Recommendations (Open Questions 1 & 2)
- **PDF Engine Selection (Open Question 1):** Strongly recommend **pure Python PDF libraries** (`reportlab` or `fpdf2`) over `weasyprint` or headless browser automation (`playwright`). `weasyprint` depends on external system libraries (Pango, Cairo, GDK-PixBuf), which introduces severe cross-platform installation fragility across Windows, macOS, and Linux, violating MyPySkinDose portability principles.
- **XLSX Image Embedding (Open Question 2):** Confirm that `openpyxl.drawing.image.Image` supports anchoring images directly to spreadsheet cells (e.g., `ws.add_image(img, 'B5')`). This approach is widely supported across desktop Excel, LibreOffice, and Google Sheets, avoiding layout breakage associated with sheet background fills.
- **Audit Trail & Prominent Warnings:** Warnings (beam-misses, KVP floor clamping/skipping, off-grid HVL linear interpolations) and discarded events must be rendered prominently in an executive alert box on the first page or overview sheet of the report.
