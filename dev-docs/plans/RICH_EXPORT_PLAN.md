# Rich Report Export — Implementation Plan

_Status: execution plan (requirements + phased checklist)_  
_Last updated: 2026-07-02_  
_Supersedes draft [RICH_EXPORT_SPEC.md](RICH_EXPORT_SPEC.md) and assessment `tmp/RICH_EXPORT_PLAN_ASSESSMENT_20260702T102827.md`_

## Summary

Add a **Rich Report Export** feature that produces a single, self-contained audit document (XLSX, PDF, HTML, or DOCX) from a completed dose calculation. The report bundles dose-map images, input provenance, effective settings, dosimetric results, correction-factor summaries, and warnings.

This is **additive** to the existing Export tab downloads (JSON, interactive HTML dose map, PNG). Those remain quick, developer-oriented exports; Rich Export targets clinical audit, QA review, and archival use.

**Implementation rule:** complete each phase checklist in order; do not start writer work until Phase 1 payload tests pass.

---

## Goals

| Goal | Detail |
|------|--------|
| Complete audit trail | One file captures what was loaded, how it was normalized, what settings were used, and what was calculated. |
| Human-readable layout | Tables, headings, and embedded images — not raw JSON. |
| Format choice | User picks XLSX, PDF, HTML, or DOCX and the save location. |
| Multi-exam support | Per-exam sections plus cumulative aggregate results. |
| Cross-platform | Pure-Python writers where possible; `kaleido` for static images with graceful runtime fallback. |

## User stories

- **Clinical physicist:** Archive a complete case record (images, settings, results) for regulatory or internal review.
- **Researcher:** Export structured summaries suitable for comparing cases in a spreadsheet (XLSX).
- **QA reviewer:** See discarded events, beam misses, KVP-floor handling, and HVL interpolation warnings in one prominent section.

## Non-goals

| Out of scope | Notes |
|--------------|-------|
| Streaming export during calculation | Export runs only after `calculation_done`. |
| Full per-event data table | Data tab + JSON export retain event-level rows. Rich Export uses aggregated correction statistics only. |
| PACS / DICOM SR push | Separate backlog item (`TO_DO.md`). |
| 3D mesh export (PLY, etc.) | Separate backlog item. |
| v1 content toggles | v1 always includes all mandatory sections. Optional section toggles are a future enhancement. |

---

## Relationship to existing code

| Existing piece | Role for Rich Export |
|----------------|---------------------|
| `gui/tabs/export.py` | JSON / HTML / PNG downloads; reuse `_get_save_path`, provenance helpers, export dialog patterns. |
| `format_export_data.py` | `PySkinDoseOutput`, `MultiExamResult`, `ExamResult`, `EXPORT_SCHEMA_VERSION`. |
| `gui/state.py` | Session state; **single-exam** uses `state.output` (dict); **multi-exam** uses `state.multi_exam_result` (`MultiExamResult`). Collector must branch on `state.multi_exam_result is not None` (or `state.is_multi_exam`). |
| `gui/helpers.py` | Multi-exam cumulative air kerma: `sum(e.output.AirKerma for e in multi_result.exams)` — not stored on `MultiExamResult`. |
| `gui/figures.py` | Interactive dose-map figures; refactor image export into `export/images.py` to avoid GUI coupling. |
| `gui/io_helpers.py` | `_tabular_input_meta` for tabular provenance only; DICOM path needs a parallel branch. |

---

## Output formats

| Format | Extension | Priority | Writer library | Notes |
|--------|-----------|----------|----------------|-------|
| XLSX | `.xlsx` | **P0** | `openpyxl` | Multi-sheet workbook; images via `openpyxl.drawing.image.Image`. |
| PDF | `.pdf` | **P0** | `reportlab` (preferred) or `fpdf2` | No `weasyprint` / headless browsers. |
| HTML | `.html` | **P1** | stdlib + inline base64 | Single self-contained file; no `.zip` bundle in v1. |
| DOCX | `.docx` | **P2** | `python-docx` | Ship only if demand warrants. |

### Image rendering

- Render via `export/images.py` using Plotly `fig.to_image(format="png", width=..., height=..., scale=...)`.
- `kaleido` is a core dependency today; still handle `to_image` failures at runtime (omit images + notice).
- Target: **1800×1200 px at `scale=2`** (~print-quality on letter paper; tune in Phase 1 image tests).

---

## Report content (mandatory sections)

Warnings and discarded events must appear prominently on the first page / overview sheet.

### 1. Title and software identity

- Application name: **MyPySkinDose**
- Package version (`pyproject.toml`)
- Export schema version (`EXPORT_SCHEMA_VERSION`)
- Export timestamp (ISO-8601, local offset when available)
- Execution context: `gui` or `cli`
- Report title: user-supplied, or default `{input_stem}_report_{YYYY-MM-DD}`

### 2. Input provenance

**Dual-branch collection (required):**

| Branch | Condition | Fields |
|--------|-----------|--------|
| Tabular | `state.import_provenance is not None` | Reuse `_tabular_input_meta`: schema, encoding, delimiter, header row, column map, `lat_lon_swapped`, import warnings. Metadata confidence: `tabular_inferred` when adapters infer manufacturer/model. |
| DICOM RDSR | `state.import_provenance is None` | Schema: `dicom_rdsr`. Source files from `state.loaded_exams[].source_file` or `state.file_name`. Encoding / delimiter / header row / column map: `N/A`. Metadata confidence: `dicom_tags`. |

Common to both branches:

- Exam count; event counts (loaded, processed, discarded with reason codes)
- Structured tracking: read discarded events from `discarded_events: dict[str, int]` on input provenance or `ExamResult` (no regex/string parsing of log messages)
- Sheet name when tabular XLSX input

### 3. Equipment (per exam)

Per exam ID: manufacturer, model, station name (if present), software version (if present), normalization profile matched. Note: in Phase 1.1, `ExamResult` is enriched with `equipment_meta` during `analyze_multiple_exams()` so CLI export has full equipment access without GUI state.

### 4. Settings snapshot

Effective `PyskindoseSettings` per exam when offsets differ. Include: phantom model/mesh/scaling/orientation; `below_floor_kvp_policy`, `below_floor_kvp_manual`, `estimate_k_tab`, `k_tab_val`, `corrections_db_path`, `beam_miss_warn`, export colorscale; flag non-defaults vs `settings_example.json`. Report effective kVp per below-floor event after policy application. Note: `ExamResult.settings_snapshot` must be expanded beyond mode/phantom to capture all physics and scaling settings for headless CLI export.

### 5. Normalization and coordinate corrections (per exam)

Coordinate convention block (+X lateral left, +Y AP down, +Z cranial for HFS; plot label names per `VENDOR_COORDINATE_SYSTEMS.md`). Per exam: vendor normalizations, GUI toggles (Tx↔Tz, Ap1×−1, Ap2×−1), table origin (detected / override / effective), patient offsets (`d_lon`, `d_ver`, `d_lat`).

### 6. Phantom and geometry

Phantom model/mesh; physical dimensions; mesh resolution (vertex + triangle counts); beam-miss event count and indices (per `beam_miss_warn`).

### 7. Dosimetric results

Report **per exam** and **cumulative** columns.

| Metric | Unit | Collection notes |
|--------|------|------------------|
| Peak skin dose (PSD) | mGy | Per exam: `output.psd` / `ExamResult.output.PSD`. Cumulative: `aggregate_psd` / `max(aggregate_dose_map)`. |
| PSD peak location | cm | Vertex index `i` on dose-map grid + physical (X,Y,Z). See **PSD peak frame** below. |
| Reference air kerma $K_{a,r}$ | mGy | Per exam: `ExamResult.output.AirKerma`. **Cumulative: `sum(e.output.AirKerma for e in exams)`** — not on `MultiExamResult` today. |
| Total DAP | Gy·cm² | Sum `DoseAreaProduct_Gym2` from event DataFrame when column exists and multiply by $10,000$ ($1 \text{ Gy}\cdot\text{m}^2 = 10^4 \text{ Gy}\cdot\text{cm}^2$); else `N/A`. |
| Total fluoro time | s or mm:ss | Sum duration from event DataFrame when column exists (check fallback candidates in order: `IrradiationDuration_s`, `ExposureTime_ms`/1000, `PulseWidth_ms`/1000, `_dt_duration`); else `N/A`. |
| Events processed / discarded | count | With reason codes (read from structured `discarded_events` dict) |
| Acquisition-mode breakdown | count + $K_{a,r}$ + DAP | Normalize `acquisition_type` to `{fluoroscopy, acquisition, other}`; show raw vendor string in parentheses |

**PSD peak frame (multi-exam offsets):** Dose maps are summed element-wise on a fixed mesh (`aggregate_dose_map += exam_dose_map`), so vertex index `i` is anatomically consistent across exams. Report:

1. Peak vertex index `i`
2. Physical (X, Y, Z) from `patient_skin_cells` at index `i`
3. For cumulative PSD under differing per-exam patient offsets: compare `exam.output.DoseMap[i]` across all exams to identify the **Primary Contributing Exam** (the exam delivering the highest dose fraction to vertex `i`). Report both the physical $(X, Y, Z)$ coordinates in the baseline (Exam 1) frame and in the primary contributing exam's frame, along with the percentage of total PSD contributed by that exam vs. remaining exams.

Anatomical region labels: deferred (coordinates only in v1).

### 8. Correction factors

Keys: `k_bs`, `k_isq`, `k_med`, `k_tab` only (see `constants.py`). Filtration → HVL lookup; report HVL clamp/interp in §9.

**Data shapes in `PySkinDoseOutput`:**

| Factor | Storage | Per-event aggregation |
|--------|---------|---------------------|
| `k_med`, `k_tab` | Per-event scalars | Use value directly |
| `k_bs`, `k_isq` | Sparse per-hit lists aligned with `Hits` | Per event: arithmetic mean across hit cells ($\bar{k}_{event,i}$); if `len(hits[i]) == 0`, define $\bar{k}_{event,i} = \text{None}$ and exclude from averaging |

**Per-exam dose-weighted mean:**

$$\bar{k}_{exam} = \frac{\sum_{i \in \text{hits}} K_{a,r,i} \cdot k_i}{\sum_{i \in \text{hits}} K_{a,r,i}}$$

where $k_i$ is the per-event scalar (or per-event mean for `k_bs`/`k_isq`), $K_{a,r,i}$ from event kerma list. For sparse hit lists (`k_bs`, `k_isq`), restrict numerator and denominator summations exclusively to events where skin hit count > 0 (`len(hits[i]) > 0`) to prevent division-by-zero and artificial kerma dilution from zero-dose pulses. If an exam has zero events with hits ($\sum_{i \in \text{hits}} K_{a,r,i} == 0$), define $\bar{k}_{exam} = \text{None}$ (reported as `"N/A"`) and exclude from cumulative averaging.

**Cumulative dose-weighted mean (multi-exam):**

$$\bar{k}_{total} = \frac{\sum_{e \in exams} AirKerma_e \cdot \bar{k}_e}{\sum_{e \in exams} AirKerma_e}$$

Also report min–max and unweighted arithmetic mean per factor. v1: exam-level + cumulative summaries only (no per-event Rich Export table).

### 9. Warnings, discarded events, QA alerts

Executive alert block: `calc_warnings`, `MultiExamResult.warnings`, import warnings, below-floor KVP details, HVL off-grid events, beam misses, discarded events with reason codes.

### 10. Dose-map images

| Scenario | Images |
|----------|--------|
| Single exam | Dorsal + anterior/ventral (or camera aimed at PSD peak) |
| Multi exam | Cumulative map (two views) + per-exam dorsal view (exam count ≤ 10) |

**Two-Tier Image Resolution Specification (Memory & Speed Budgeting):**
To prevent allocating ~400 MB of uncompressed bitmap memory and freezing background threads during multi-image rendering:
- **Primary / Cumulative Maps (2 views):** Render at high print resolution ($1600 \times 1000 \text{ px}$, `scale=1.5`).
- **Per-Exam Thumbnail Tables (up to 10 exams):** Render at compact document resolution ($800 \times 600 \text{ px}$, `scale=1.0`).
When exam count > 10: cumulative images + per-exam summary tables only; note threshold in report.

Camera presets and dimensions live in `export/images.py` (not hardcoded only in `gui/figures.py`).

---

## Default filename and save location

```
{input_stem}_{YYYY-MM-DD}_{HHMMSS}.{ext}
```

Default directory: first input file's directory; browser upload → Documents (native) or browser download.

---

## GUI interaction (Phase 4)

- **Export tab** card: "Rich report…" (+ optional Results tab button)
- Modal: format dropdown, editable path, Browse (`_get_save_path`), Export on `run.io_bound`, Cancel
- Success: Open file / Open folder (native); kaleido failure → actionable notice

---

## CLI (Phase 5)

```bash
python -m mypyskindose --input file.dcm --settings settings.json \
  --export-format xlsx --export-path ./report.xlsx
```

**Wiring in `main.py`:** when `--export-format` is set, run the normal calculate pipeline (`analyze_data` / `analyze_multiple_exams`), then call `collect_export_payload()` with the result object, normalized DataFrame(s), and effective settings — **no GUI state**. Pass payload to the selected writer and write `--export-path`. Do not add `--mode export`.

---

## Data architecture

```text
src/mypyskindose/export/
  __init__.py
  payload.py          # ExportPayload + collect_export_payload()
  provenance.py       # tabular + DICOM provenance branches
  metrics.py          # PSD peak, kerma sums, correction stats, acquisition breakdown
  images.py           # dose-map PNG/HTML helpers (camera, dimensions)
  writers/
    __init__.py
    xlsx.py
    pdf.py
    html.py
    docx.py           # Phase 6
```

`collect_export_payload()` accepts a **source bundle** dataclass (GUI or CLI populated):

```python
@dataclass
class ExportSource:
    execution_context: Literal["gui", "cli"]
    # Exactly one of:
    output_dict: dict[str, Any] | None          # single-exam
    multi_exam_result: MultiExamResult | None   # multi-exam
    rdsr_df: pd.DataFrame | None
    loaded_exams: list[Any] | None              # GUI multi-exam metadata
    import_provenance: InputProvenance | None
    import_warnings: list[str]
    calc_warnings: list[str]
    settings: PyskindoseSettings                # or per-exam snapshots from ExamResult
    file_name: str | None
    colorscale: str
    # GUI-only optional:
    load_timestamp: datetime | None = None
```

Writers consume `ExportPayload` only.

---

# Phased implementation checklist

## Phase 0 — Design sign-off (no code)

- [ ] **0.1** Review this checklist with stakeholder; confirm v1 scope (XLSX + PDF required; HTML Phase 5; DOCX deferred).
- [ ] **0.2** Confirm `reportlab` added under a new `export` optional extra in `pyproject.toml` (keep core deps unchanged for non-export users).
- [ ] **0.3** Confirm file-size budget: each writer module < 800 lines; split helpers if needed.

---

## Phase 1 — Export payload collector (core)

**Goal:** `collect_export_payload(source: ExportSource) -> ExportPayload` with full unit test coverage. No writers yet.

### 1.1 Package scaffold

- [ ] **1.1.1** Create `src/mypyskindose/export/` package and empty writer subpackage.
- [ ] **1.1.2** Define `ExportPayload` and nested dataclasses mirroring §1–§10 (title, provenance, exams[], cumulative metrics, corrections, warnings, images as `bytes | None` + metadata). Add `warnings: list[str]` to `PySkinDoseOutput` in `format_export_data.py` so calculation warnings are captured in single-exam CLI runs.
- [ ] **1.1.3** Define `ExportSource` input bundle (see Data architecture).
- [ ] **1.1.4** Public API: `collect_export_payload(source) -> ExportPayload`.
- [ ] **1.1.5** Store the entire normalized event DataFrame (`rdsr_df: pd.DataFrame` / `data_norm`) directly on `ExamResult` in `format_export_data.py` (rather than coupling orchestration to export with pre-aggregated metrics), along with effective coordinate overrides (`flip_ap1`, `flip_ap2`, `swap_lat_lon`), effective `table_origin`, `equipment_meta`, and full `settings_snapshot` so `MultiExamResult` is completely self-contained for CLI export without GUI state.

### 1.2 Source resolution (GUI vs CLI, single vs multi)

- [ ] **1.2.1** Implement `resolve_calculation_result(source)`:
  - If `source.multi_exam_result is not None` → multi-exam path (ignore `output_dict`).
  - Elif `source.output_dict is not None` → single-exam path.
  - Else → raise `ExportError("No calculation result")`.
- [ ] **1.2.2** Add `build_export_source_from_gui(state) -> ExportSource` in `gui/` (thin adapter; keeps `export/` GUI-import-free).
- [ ] **1.2.3** Guard: `calculation_done` / equivalent CLI success before export.

### 1.3 Provenance (`export/provenance.py`)

- [ ] **1.3.1** Tabular branch: wrap `_tabular_input_meta` logic (move shared bits to `export/provenance.py`; GUI re-exports or imports from export).
- [ ] **1.3.2** DICOM branch: schema `dicom_rdsr`, filenames from `loaded_exams` / `file_name`, tabular fields `N/A`, confidence `dicom_tags`.
- [ ] **1.3.3** Event counts: total loaded, processed, discarded + reason code list (read from structured `discarded_events: dict[str, int]` on input provenance / `ExamResult`; avoid natural language warning scraping). Ensure calculation warnings from the physics engine are collected in CLI mode (via `PySkinDoseOutput.warnings` or `ExamResult.warnings`) and mapped to the payload.

### 1.4 Dosimetric metrics (`export/metrics.py`)

- [ ] **1.4.1** Per-exam PSD, air kerma, event counts from `ExamResult` / single `output_dict`.
- [ ] **1.4.2** Cumulative PSD from `aggregate_psd` or `max(dose_map)`; cumulative air kerma via **explicit sum** across exams.
- [ ] **1.4.3** PSD peak: `argmax(dose_map)` → vertex index + (X,Y,Z) from skin cells; for multi-exam under differing offsets, identify Primary Contributing Exam, reporting baseline and primary coordinates + percentage dose contribution.
- [ ] **1.4.4** DAP / fluoro time: read from `rdsr_df` columns when present (multiply `DoseAreaProduct_Gym2` by 10,000 for Gy·cm²; check fluoro duration fallback columns in order: `IrradiationDuration_s`, `ExposureTime_ms`/1000, `PulseWidth_ms`/1000, `_dt_duration`); `None` → report as `N/A`.
- [ ] **1.4.5** Acquisition breakdown: group by normalized `acquisition_type`; sum $K_{a,r}$ and DAP per group.

### 1.5 Correction statistics (`export/metrics.py`)

- [ ] **1.5.1** Parse `corrections` block from `output_dict` / `PySkinDoseOutput.to_dict()`.
- [ ] **1.5.2** `k_med` / `k_tab`: per-event scalar dose-weighted means per exam.
- [ ] **1.5.3** `k_bs` / `k_isq`: per event, mean across hit cells (None if `len(hits[i]) == 0`); then dose-weight across events where hit count > 0. If an exam has zero events with hits ($\sum_{i \in \text{hits}} K_{a,r,i} == 0$), report the exam dose-weighted mean as `"N/A"` (or `None`) to prevent division-by-zero.
- [ ] **1.5.4** Cumulative correction means: kerma-weighted across exams (formula in §8).
- [ ] **1.5.5** Min–max and arithmetic mean for each factor.

### 1.6 Settings, equipment, geometry sections

- [ ] **1.6.1** Serialize effective settings per exam (from enriched `ExamResult.settings_snapshot` or `build_settings(state)`).
- [ ] **1.6.2** Equipment from enriched `ExamResult.equipment_meta` or normalized DataFrame (manufacturer, model).
- [ ] **1.6.3** Phantom dimensions + mesh resolution from output patient block.
- [ ] **1.6.4** Coordinate corrections + table origin from enriched `ExamResult` overrides / GUI state.
- [ ] **1.6.5** Flag non-default settings vs `settings_example.json`.

### 1.7 Image generation (`export/images.py`)

- [ ] **1.7.1** Implement `render_dosemap_png(dose_map, patient_dict, *, camera_eye, width, height, scale, colorscale) -> bytes | None` supporting two-tier resolution (1600×1000 px scale=1.5 for cumulative maps; 800×600 px scale=1.0 for per-exam thumbnails).
- [ ] **1.7.2** Camera presets: `DORSAL = dict(x=-2.5, y=1.5, z=0)`, `ANTERIOR` (positive Y or PSD-centered `lookat`).
- [ ] **1.7.3** Optional `look_at_peak`: aim camera at PSD vertex coordinates.
- [ ] **1.7.4** Move Plotly figure creation logic to a pure-logic helper `render_dosemap_plotly_figure(dose_map, patient_dict, colorscale, ...)` in `export/images.py` that takes explicit parameters and does not read from `gui/state.py`. Refactor `gui/figures.py` (`make_dosemap_png` / `make_dosemap_html`) to delegate to this export helper.
- [ ] **1.7.5** Populate `ExportPayload.images` list: `{label, view, exam_id, png_bytes, error_message}`.

### 1.8 Phase 1 tests

- [ ] **1.8.1** `test_payload_single_exam_dict` — fixture from golden `output_dict`; assert PSD, kerma, corrections, provenance DICOM branch.
- [ ] **1.8.2** `test_payload_multi_exam_object` — cumulative kerma sum, cumulative correction weighting, per-exam columns.
- [ ] **1.8.3** `test_payload_dicom_provenance_fallback` — `import_provenance=None` → `dicom_rdsr` schema.
- [ ] **1.8.4** `test_payload_tabular_provenance` — mirrors `_tabular_input_meta` fields.
- [ ] **1.8.5** `test_psd_peak_vertex_index` — known dose map → expected index and coordinates.
- [ ] **1.8.6** `test_correction_sparse_hits` — `k_bs`/`k_isq` averaging with multi-hit events.
- [ ] **1.8.7** `test_export_without_kaleido` — mock `to_image` failure → `png_bytes=None`, no exception.
- [ ] **1.8.8** `test_build_export_source_from_gui` — multi vs single branch on mock `AppState`.

**Phase 1 exit criteria:** all 1.x tests green; `collect_export_payload` usable from a one-off script with fixture data.

---

## Phase 2 — XLSX writer

**Goal:** `write_xlsx(payload, path)` producing a clinical audit workbook.

### 2.1 Workbook layout

- [ ] **2.1.1** Implement `writers/xlsx.py`: `write_xlsx(payload: ExportPayload, path: Path) -> None`.

**Single-exam sheets:**

| Sheet | Content |
|-------|---------|
| `Overview` | Title, version, timestamp, executive alert box, cumulative summary (same as exam summary) |
| `Results` | Dosimetric table + PSD peak location |
| `Settings` | Effective settings + coordinate corrections |
| `Corrections` | Four factors × {min, max, mean, dose-weighted mean} |
| `Warnings` | Full warning list |
| `Images` | Anchored PNGs |

**Multi-exam sheets (exam count ≤ 5):**

| Sheet | Content |
|-------|---------|
| `Overview` | Alerts + cumulative summary |
| `Summary` | Metric \| Exam 1 \| Exam 2 \| … \| Cumulative columns |
| `Equipment & Settings` | Vertical blocks per exam (`--- Exam N ---` headers) |
| `Corrections` | Per-exam sub-tables + cumulative row |
| `Warnings` | All warnings tagged by exam when applicable |
| `Images` | Cumulative images first, then per-exam dorsal |

- [ ] **2.1.2** **Multi-exam sheets (exam count > 5):** add per-exam tabs `Exam N` for settings/corrections; keep `Summary` + `Overview` + `Images` (cumulative only if > 10 exams per image cap).
- [ ] **2.1.3** Cell formats: header row bold; write numeric cells as floats with number formatting (`0.00` / `0.0000`) rather than strings; auto-fit column widths to maximum string length to prevent `###` clipping; explicitly enable sheet gridlines (`ws.views.sheetView[0].showGridLines = True`) on every worksheet.
- [ ] **2.1.4** Executive alert styling: fill warning rows amber (`#FFF3CD`); errors/beam-miss/discarded amber-red (`#F8D7DA`).

### 2.2 Image embedding

- [ ] **2.2.1** `openpyxl.drawing.image.Image` anchored at declared cells (e.g. `B5`).
- [ ] **2.2.2** When `png_bytes is None`: text cell "Image unavailable (kaleido/export error)".
- [ ] **2.2.3** Scale images to fit sheet width without obscuring tables.

### 2.3 Phase 2 tests

- [ ] **2.3.1** `test_write_xlsx_single_exam` — file opens with `openpyxl`; expected sheet names exist.
- [ ] **2.3.2** `test_write_xlsx_multi_exam_summary_columns` — Exam 1, Exam 2, Cumulative headers.
- [ ] **2.3.3** `test_write_xlsx_images_embedded` — sheet `Images` has anchored drawings when PNG present.
- [ ] **2.3.4** `test_write_xlsx_missing_images` — no crash when all images `None`.

**Phase 2 exit criteria:** generate XLSX from fixture payload; manual open in Excel/LibreOffice smoke.

---

## Phase 3 — PDF writer

**Goal:** `write_pdf(payload, path)` using `reportlab`.

### 3.1 Document structure

- [ ] **3.1.1** Implement `writers/pdf.py`: `write_pdf(payload, path) -> None`.
- [ ] **3.1.2** Page 1: title block + **executive alert box** (`#FFF3CD` amber for warnings / `#F8D7DA` red for data loss/skips, 1.5 pt border) + cumulative summary table.
- [ ] **3.1.3** Subsequent pages: settings, results, corrections, warnings, images (page breaks between major sections). Implement a two-pass `ReportLab` canvas subclass (`NumberedCanvas`) to calculate total page count and render a consistent "Page X of Y" footer.
- [ ] **3.1.4** Multi-exam: per-exam subsections with consistent heading styles.

### 3.2 Table rendering

- [ ] **3.2.1** Wrap all table cell text in `reportlab.platypus.Paragraph` with explicit `ParagraphStyle` (word wrap, leading); set explicit table column widths (`colWidths=[...]`) within page bounds; limit text styles to standard PDF core fonts (`Helvetica`, `Helvetica-Bold`) for OS portability.
- [ ] **3.2.2** Long filenames and warning strings must not clip (test with 120+ char fixture strings).
- [ ] **3.2.3** Repeat header row on page breaks for long tables.

### 3.3 Images

- [ ] **3.3.1** Embed PNG via `Image(BytesIO(png_bytes), width=..., height=...)`.
- [ ] **3.3.2** Missing image placeholder paragraph.

### 3.4 Phase 3 tests

- [ ] **3.4.1** `test_write_pdf_smoke` — PDF bytes written, minimum page count.
- [ ] **3.4.2** `test_write_pdf_long_filename_wraps` — no builder exception.
- [ ] **3.4.3** `test_write_pdf_no_images` — completes with notice text.

**Phase 3 exit criteria:** PDF opens in viewer; page 1 alerts visible; tables readable.

---

## Phase 4 — GUI integration

**Goal:** Export tab Rich report dialog wired to collector + writers.

### 4.1 Dependencies

- [ ] **4.1.1** Add `reportlab` to `[project.optional-dependencies]` e.g. `export = ["reportlab>=4.0"]`; document `pip install -e '.[gui,export]'`.
- [ ] **4.1.2** Extend `_get_save_path` extension map for `pdf`, `docx` if not already present.

### 4.2 UI

- [ ] **4.2.1** New Export tab card: "Rich report…" with format description text.
- [ ] **4.2.2** Modal: format `ui.select`, path `ui.input`, Browse button, Export / Cancel.
- [ ] **4.2.3** Default path from `{input_stem}_{date}_{time}.{ext}`.
- [ ] **4.2.4** Export handler: `build_export_source_from_gui(state)` → `collect_export_payload` → writer on `run.io_bound`.
- [ ] **4.2.5** Disable Export when `not state.calculation_done`.
- [ ] **4.2.6** Progress: spinner or `ui.notify('Generating report…')` for multi-exam.
- [ ] **4.2.7** Success actions: Open file / Open folder conditionally rendered ONLY in native mode (`_is_native_mode()`), using cross-platform OS launchers (`os.startfile` on Windows, `open` on macOS, `xdg-open` on Linux). In browser mode, rely solely on `ui.download()`.
- [ ] **4.2.8** (Optional v1.1) Results tab secondary "Export report…" button reusing same dialog factory.

### 4.3 Phase 4 manual smoke

- [ ] **4.3.1** Single-exam DICOM RDSR → XLSX + PDF from Export tab.
- [ ] **4.3.2** Tabular input (Radimetrics or DoseTrack fixture) → XLSX with provenance block.
- [ ] **4.3.3** Multi-exam (2 exams) → Summary sheet columns + cumulative PSD.
- [ ] **4.3.4** Simulate kaleido failure → export completes with notice, no crash.

**Phase 4 exit criteria:** v1 acceptance criteria (GUI path) satisfied for XLSX and PDF.

---

## Phase 5 — HTML writer + CLI

**Goal:** Self-contained HTML export and headless `--export-format`.

### 5.1 HTML writer

- [ ] **5.1.1** `writers/html.py`: single file, embedded CSS, interactive Plotly 3D scenes (`fig.to_html(full_html=False)`), collapsible sections. Reserve static base64 PNG rendering for XLSX/PDF writers.
- [ ] **5.1.2** Executive alert block at top (HTML + inline styles matching PDF amber/red).
- [ ] **5.1.3** Tables for metrics/corrections; `meta` tag with `schema_version` and package version.

### 5.2 CLI flags (`main.py`)

- [ ] **5.2.1** Add `--export-format {xlsx,pdf,html}` and optional `--export-path PATH` (align CLI examples with existing parser arguments `--file-path` / `-f`).
- [ ] **5.2.2** When `--export-format` is set, force `settings.output_format = 'dict'` before calculation to ensure structured output. After successful calculate, build `ExportSource(execution_context="cli", ...)` and write report.
- [ ] **5.2.3** If `--export-path` is omitted, automatically derive output path: `{input_stem}_report_{YYYY-MM-DD}_{HHMMSS}.{ext}` in the same directory as the input file.
- [ ] **5.2.4** Print confirmation path on success (stdout).

### 5.3 Phase 5 tests

- [ ] **5.3.1** `test_cli_export_xlsx` — subprocess or `main()` with tmp path.
- [ ] **5.3.2** `test_write_html_smoke` — HTML contains embedded images or fallback notice.
- [ ] **5.3.3** CLI/GUI parity: same fixture → same cumulative kerma in XLSX Summary (compare cell values).

**Phase 5 exit criteria:** CLI generates XLSX; HTML download available in GUI.

---

## Phase 6 — DOCX writer (optional)

- [ ] **6.1** Add `python-docx` to `export` extra.
- [ ] **6.2** `writers/docx.py` mirroring PDF section order.
- [ ] **6.3** Enable DOCX in GUI format dropdown.
- [ ] **6.4** Smoke test in Word/LibreOffice.

---

## Phase 7 — Polish

- [ ] **7.1** Multi-exam image cap user toggle (GUI checkbox; default off = use threshold 10).
- [ ] **7.2** PDF accessibility: document language, image alt text from labels.
- [ ] **7.3** Localization hooks: extract user-visible strings to constants module.
- [ ] **7.4** Align Results tab correction table to include `k_med` (separate small PR).
- [ ] **7.5** Update `FEATURE_INVENTORY.md`, `CHANGELOG.md`, GUI help (`docs/source/gui_help/export.md`).
- [ ] **7.6** Archive `RICH_EXPORT_SPEC.md` → `plans/archive/` when v1 ships; update `dev-docs/index.md`.

---

## Resolved decisions

| Topic | Decision |
|-------|----------|
| PDF library | `reportlab` in `export` extra |
| XLSX images | `openpyxl` anchored cells |
| Cumulative air kerma | Sum per-exam `AirKerma` in collector |
| Cumulative corrections | Kerma-weighted mean of per-exam weighted means |
| GUI result source | `multi_exam_result` takes precedence over `output` |
| DICOM provenance | Dedicated branch when `import_provenance is None` |
| `k_bs`/`k_isq` aggregation | Mean per event over hits, then kerma-weight across events |
| Per-event correction table | Not in v1 Rich Export |
| HTML shape | Single `.html` file |

---

## v1 acceptance criteria

- [ ] Single-exam calculation → XLSX and PDF from Export tab.
- [ ] All §1–§10 fields present with correct physics names.
- [ ] Multi-exam: per-exam + cumulative columns for PSD, $K_{a,r}$, corrections, warnings.
- [ ] Warnings on first page / overview sheet.
- [ ] Export succeeds when image render fails (notice, no crash).
- [ ] Phase 1–3 unit tests green in CI.
- [ ] New dependencies only via `export` optional extra (+ existing `openpyxl`, `kaleido`).

---

## References

- Draft spec: [RICH_EXPORT_SPEC.md](RICH_EXPORT_SPEC.md)
- Assessment (Initial draft review): `tmp/RICH_EXPORT_PLAN_ASSESSMENT_20260702T102827.md`
- Assessment (Deep codebase audit): `tmp/RICH_EXPORT_PLAN_ASSESSMENT_20260702T144200.md`
- Assessment (Comprehensive codebase audit & gap analysis): `tmp/RICH_EXPORT_PLAN_ASSESSMENT_20260702T151800.md`
- Coordinates: [VENDOR_COORDINATE_SYSTEMS.md](../VENDOR_COORDINATE_SYSTEMS.md)
- Data model: `src/mypyskindose/format_export_data.py`
- GUI export: `src/mypyskindose/gui/tabs/export.py`
