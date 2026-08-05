# Rich Report Export — Master Plan

_Status: **Phases 1–6 shipped** (XLSX + PDF + HTML + DOCX, GUI modal, CLI flags). Phase 7 leftovers and
manual save smoke are **deferred** in [TO_DO.md](../TO_DO.md) (Deferred Until Needed)._  
_Last updated: 2026-07-30_  
_Supersedes draft [RICH_EXPORT_SPEC.md](archive/RICH_EXPORT_SPEC.md) and folds in prior ad-hoc assessments_

## Implementation status (2026-07-02)

**Shipped:** `src/mypyskindose/export/` package — `payload.py` (`collect_export_payload`,
`resolve_calculation_result`), `_exam_view.py` (single-dict / multi-object normalizer),
`metrics.py`, `sections.py`, `provenance.py`, `images.py` (+ zoom-to-dose), `models.py`,
`cli_source.py`, and `writers/{xlsx,pdf,html,docx}.py` + a `render_bytes`/`write_report` dispatcher.
GUI adapter `gui/export_source.py` and Export-tab modal; CLI `--export-format/--export-path/--export-title`
wired in `__main__.py` via `main.run_cli_export` + `validate_export_flags`. `gui/figures.py`
delegates to `export/images.py`. `reportlab` + `python-docx` added as the optional `export` extra.
Docs: CHANGELOG + FEATURE_INVENTORY §7.7 updated; draft spec archived. Tests:
`tests/unittests/test_export_{payload,xlsx,pdf,html,cli,docx}.py` (27 tests). Full suite green.

**Remaining (deferred, low priority):** Phase 7 leftovers — multi-exam image-cap GUI toggle (7.1),
deeper PDF/DOCX tagged-a11y (7.2, HTML already has `alt`), localization-string extraction (7.3),
Results-tab `k_med` alignment (7.4, separate PR), and per-tab GUI help (no export help loader exists
today). Phase 4 manual browser/native save smoke (4.3.x) needs a human. Minor code deferrals: XLSX
explicit `cell.number_format` (values are pre-formatted strings); browser `showSaveFilePicker()`
progressive enhancement (baseline `ui.download()` fallback is implemented and is the required
behavior). GUI native "Open file / Open folder" success actions (4.2.7) are **implemented**
(`_open_path`, Windows/macOS/Linux launchers, 6 unit tests) — pending Windows manual smoke.

## Summary

Add a **Rich Report Export** feature that produces a single, self-contained audit document (XLSX, PDF, HTML, or DOCX) from a completed dose calculation. The report bundles dose-map images, input provenance, effective settings, dosimetric results, correction-factor summaries, and warnings.

This is **additive** to the existing Export tab downloads (JSON, interactive HTML dose map, PNG). Those remain quick, developer-oriented exports; Rich Export targets clinical audit, QA review, and archival use.

The payload and writer pipeline should stay **separate from the existing JSON/dict export schema** by default. Additive schema enrichment is acceptable when the new fields are broadly useful outside Rich Export (for example warnings, provenance summary, discarded-event summary, or fuller effective settings), but report-layout-specific data should stay in the Rich Export payload rather than bloating `PySkinDoseOutput.to_dict()`.

**Implementation rule:** complete each phase checklist in order; do not start writer work until Phase 1 payload tests pass.

---

## Goals

| Goal | Detail |
|------|--------|
| Complete audit trail | One file captures what was loaded, how it was normalized, what settings were used, and what was calculated. |
| Human-readable layout | Tables, headings, and embedded images — not raw JSON. |
| Format choice | User picks XLSX, PDF, HTML, or DOCX; CLI/native choose a save path, browser mode downloads with a suggested filename. |
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
| Browser-only save-dialog parity across all browsers | Browser save-picker support is progressive enhancement only; standard browser download remains the required baseline behavior. |

---

## Relationship to existing code

| Existing piece | Role for Rich Export |
|----------------|---------------------|
| `gui/tabs/export.py` | JSON / HTML / PNG downloads; provenance helpers, export dialog patterns. |
| `gui/io_helpers.py` | Reuse `_get_save_path` (native only) and `_tabular_input_meta`; browser mode must continue to rely on `ui.download()` rather than a fake path picker. |
| `format_export_data.py` | `PySkinDoseOutput`, `MultiExamResult`, `ExamResult`; Rich Export should avoid an unnecessary public schema bump and use a separate payload model. |
| `gui/state.py` | Session state; **single-exam** uses `state.output` (dict); **multi-exam** uses `state.multi_exam_result` (`MultiExamResult`). Collector must branch on `state.multi_exam_result is not None` (or `state.is_multi_exam`). |
| `gui/helpers.py` | Multi-exam cumulative air kerma: `sum(e.output.air_kerma for e in multi_result.exams)` — not stored on `MultiExamResult`. |
| `gui/figures.py` | Interactive dose-map figures; refactor image export into `export/images.py` to avoid GUI coupling. |
| `input_adapters/models.py` | `InputAdapterResult` / `InputProvenance` already carry normalized data and provenance; prefer reusing them in the export source bundle instead of copying DataFrames onto result models. |
| `main.py` | CLI currently has separate single/multi-file execution branches and no report flags; Rich Export should unify export-capable dispatch instead of bolting logic onto only one branch. |

---

## Output formats

| Format | Extension | Priority | Writer library | Notes |
|--------|-----------|----------|----------------|-------|
| XLSX | `.xlsx` | **P0** | `openpyxl` | Multi-sheet workbook; images via `openpyxl.drawing.image.Image`. |
| PDF | `.pdf` | **P0** | `reportlab` | No `weasyprint` / headless browsers. |
| HTML | `.html` | **P1** | stdlib + inline base64 | Single self-contained file; no `.zip` bundle in v1. |
| DOCX | `.docx` | **P2** | `python-docx` | Ship only if demand warrants. |

### Image rendering

- Render via `export/images.py` using Plotly `fig.to_image(format="png", width=..., height=..., scale=...)`.
- `kaleido` is a core dependency today; still handle `to_image` failures at runtime (omit images + notice).
- Use the two-tier image budget defined in §10: high-resolution cumulative views plus lighter per-exam thumbnails.

---

## Report content (mandatory sections)

Warnings and discarded events must appear prominently on the first page / overview sheet.

### 1. Title and software identity

- Application name: **MyPySkinDose**
- Package version (`pyproject.toml`)
- Rich export schema version (new payload-specific constant, separate from `EXPORT_SCHEMA_VERSION`)
- Export timestamp (ISO-8601, local offset when available)
- Execution context: `gui` or `cli`
- Report title: user-supplied, or default `MyPySkinDose report — {YYYY-MM-DD HH:MM}`

### 2. Input provenance

**Dual-branch collection (required):**

| Branch | Condition | Fields |
|--------|-----------|--------|
| Tabular | `state.import_provenance is not None` | Reuse `_tabular_input_meta`: schema, encoding, delimiter, header row, column map, `lat_lon_swapped`, import warnings. Metadata confidence: `tabular_inferred` when adapters infer manufacturer/model. |
| DICOM RDSR | `state.import_provenance is None` | Source type: `dicom`; schema name: `rdsr` (align with current `InputProvenance` usage). Source files from `state.loaded_exams[].source_file` or `state.file_name`. Encoding / delimiter / header row / column map: `N/A`. Metadata confidence: `dicom_tags`. |

Common to both branches:

- Exam count; event counts (loaded, processed, discarded with reason codes)
- Structured tracking: read discarded events from `discarded_events: dict[str, int]` added to `ExamResult` during `analyze_multiple_exams()` (no regex/string parsing of log messages)
- **Single-exam caveat:** `ExamResult` exists only on the multi-exam path. Single-exam runs (`main()` → bare dict / `PySkinDoseOutput`) have **no `ExamResult` wrapper**, so structured `discarded_events` has no carrier there. For single-exam, either (a) attach the same `discarded_events: dict[str, int]` to the single-exam source bundle populated by `build_export_source_from_*`, or (b) fall back to the warning-capture helper (§1.1.7). Do **not** silently report zero discards for single-exam when the count is simply unavailable — mark it `N/A` if neither source is populated.
- Sheet name when tabular XLSX input

### 3. Equipment (per exam)

Per exam ID: manufacturer, model, and normalization profile matched. Include station name and software version only if they are actually available from the source adapter or a future parser enhancement; they are **not** required for v1.

**Unit parsing / conversions (shipped):** `ExamSection.unit_conversions` (from `provenance.unit_conversions`) is rendered in the equipment block of every writer as `Units: <field>` rows (e.g. `mGy → Gy (from 'Air Kerma (mGy)')`). It is empty for DICOM RDSR (units read+asserted, not converted) and `normalized` inputs. See [INPUT_SCHEMA_DETECTION.md → Unit handling](../INPUT_SCHEMA_DETECTION.md#unit-handling).

### 4. Settings snapshot

Effective `PyskindoseSettings` per exam when offsets differ. Serialize the effective settings directly in the payload collector (from GUI/CLI source adapters or per-exam settings objects); do **not** expand `PySkinDoseOutput.to_dict()` just for report generation. Include at minimum: `mode`, `phantom` (model/mesh/scaling/orientation), `normalization_settings`, `below_floor_kvp_policy`, `below_floor_kvp_manual`, `estimate_k_tab`, `k_tab_val`, `corrections_db_path`, `beam_miss_warn` (note CLI default is `per_event` while GUI default is `summary`), `inherent_filtration`, `remove_invalid_rows`; flag non-defaults vs `settings_example.json`. Report effective kVp per below-floor event after policy application.

### 5. Normalization and coordinate corrections (per exam)

Coordinate convention block (+X lateral left, +Y AP down, +Z cranial for HFS; plot label names per `VENDOR_COORDINATE_SYSTEMS.md`). Per exam: vendor normalizations, GUI toggles (Tx↔Tz, Ap1×−1, Ap2×−1), table origin (detected / override / effective), patient offsets (`d_lon`, `d_ver`, `d_lat`).

### 6. Phantom and geometry

Phantom model/mesh; physical dimensions; mesh resolution (vertex + triangle counts); beam-miss event count and indices (per `beam_miss_warn`).

### 7. Dosimetric results

Report **per exam** and **cumulative** columns.

**Two output representations (must normalize before computing metrics):** the collector receives calculation results in two different shapes and must reduce them to one internal form:

| Path | Carrier | `dose_map` shape | Access style |
|------|---------|------------------|--------------|
| Single-exam | `source.output_dict` (a **dict**, `state.output`) | **Sparse**: `[(vertex_index, dose), …]` for `dose > 0` only (see `PySkinDoseOutput.to_dict()`); `psd` is a top-level scalar | dict keys (`output_dict["psd"]`, `["air_kerma"]`) |
| Multi-exam | `MultiExamResult.exams[].output` (**`PySkinDoseOutput` objects**); `aggregate_dose_map` is a full `np.ndarray` | Full dense `np.ndarray` on `.dose_map` / `aggregate_dose_map` | canonical lowercase attributes (`.psd`, `.air_kerma`, `.dose_map`) |

Because the single-exam `dose_map` is sparse, **`argmax` over a dense array does not apply there** — the peak vertex index is the first element of the max-dose tuple, not a positional argmax. Normalize both forms in `resolve_calculation_result` (1.2.1) so downstream metrics code sees a consistent `(psd, air_kerma, dense_or_sparse-aware peak lookup)` interface.

| Metric | Unit | Collection notes |
|--------|------|------------------|
| Peak skin dose (PSD) | mGy | Per exam: `output.psd` / `ExamResult.output.psd`. Cumulative: `aggregate_psd` / `max(aggregate_dose_map)`. |
| PSD peak location | cm | Vertex index `i` on dose-map grid + physical (X,Y,Z). See **PSD peak frame** below. |
| Reference air kerma $K_{a,r}$ | mGy | Per exam: `ExamResult.output.air_kerma`. **Cumulative: `sum(e.output.air_kerma for e in exams)`** — not on `MultiExamResult` today. |
| Total DAP | Gy·cm² | Sum `DoseAreaProduct_Gym2` from event DataFrame when column exists and multiply by $10,000$ ($1 \text{ Gy}\cdot\text{m}^2 = 10^4 \text{ Gy}\cdot\text{cm}^2$); else `N/A`. |
| Total fluoro time | s or `N/A` | Only report when the normalized/source data exposes a trustworthy duration column. v1 must **not** infer total fluoro time from pulse width alone. |
| Events processed / discarded | count | With reason codes (read from structured `discarded_events` dict) |
| Acquisition-mode breakdown | count + $K_{a,r}$ + DAP | Normalize `acquisition_type` to `{fluoroscopy, acquisition, other}`; show raw vendor string in parentheses |

**PSD peak frame (multi-exam offsets):** Dose maps are summed element-wise on a fixed mesh (`aggregate_dose_map += exam_dose_map`), so vertex index `i` is anatomically consistent across exams. Report:

1. Peak vertex index `i`
2. Physical (X, Y, Z) from `patient_skin_cells` at index `i`
3. For cumulative PSD under differing per-exam patient offsets: compare `exam.output.dose_map[i]` across all exams to identify the **Primary Contributing Exam** (the exam delivering the highest dose fraction to vertex `i`). Report both the physical $(X, Y, Z)$ coordinates in the baseline (Exam 1) frame and in the primary contributing exam's frame, along with the percentage of total PSD contributed by that exam vs. remaining exams.

Anatomical region labels: deferred (coordinates only in v1).

### 8. Correction factors

Four factors: `k_bs`, `k_isq`, `k_med`, `k_tab` (the `OUTPUT_KEY_CORRECTION_*` constants in `constants.py`). Filtration → HVL lookup; report HVL clamp/interp in §9.

**Dict-key naming caveat (must read before coding the collector):** the `k_bs`/`k_isq`/`k_med`/`k_tab` names are only the *internal* `analysis_result` keys. `PySkinDoseOutput.to_dict()["corrections"]` uses **different** key names:

| Physics factor | `to_dict()["corrections"]` key | `PySkinDoseOutput` canonical object API |
|----------------|-------------------------------|------------------------------|
| `k_bs` | `backscatter` | `.backscatter_correction` |
| `k_isq` | `inverse_square_law` | `.inverse_square_law_correction` |
| `k_med` | `medium` | `.medium_correction` |
| `k_tab` | `table` | `.table_correction` |
| hit cell indices | `correction_value_index` | `.sparse_hit_indices()` |
| per-event kerma | `kerma` | `.events.kerma` |

Prefer reading from the **attributes** (multi-exam `ExamResult.output` objects) and from these exact dict keys (single-exam `output_dict`) — do **not** look up `corrections["k_bs"]` etc.; those keys do not exist in the exported dict.

**Data shapes in `PySkinDoseOutput`:**

| Factor | Storage | Per-event aggregation |
|--------|---------|---------------------|
| `k_med`, `k_tab` | Per-event scalars (`.medium_correction[i]`, `.table_correction[i]` are floats) | Use value directly |
| `k_bs`, `k_isq` | Sparse per-hit lists aligned with `.sparse_hit_indices()` | Per event: arithmetic mean across hit cells ($\bar{k}_{event,i}$); if `len(hits[i]) == 0`, define $\bar{k}_{event,i} = \text{None}$ and exclude from averaging |

**Per-exam dose-weighted mean:**

$$\bar{k}_{exam} = \frac{\sum_{i \in \text{hits}} K_{a,r,i} \cdot k_i}{\sum_{i \in \text{hits}} K_{a,r,i}}$$

where $k_i$ is the per-event scalar (or per-event mean for `k_bs`/`k_isq`), $K_{a,r,i}$ from event kerma list. Restrict numerator and denominator summations across all correction factors exclusively to events where skin hit count > 0 (`len(hits[i]) > 0`) to prevent division-by-zero and artificial kerma dilution from zero-dose pulses (where zero-hit pulses record 0.0). If an exam has zero events with hits ($\sum_{i \in \text{hits}} K_{a,r,i} == 0$), define $\bar{k}_{exam} = \text{None}$ (reported as `"N/A"`) and exclude from cumulative averaging.

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
mypyskindose_report_{YYYY-MM-DD}_{HHMMSS}.{ext}
```

Default directory: first input file's directory for CLI and native GUI. In browser-mode GUI there is **no explicit path chooser**; the app provides a download filename and the browser handles the destination.

---

## GUI interaction (Phase 4)

- **Export tab** card: "Rich report…" (+ optional Results tab button)
- Modal: format dropdown, optional title field, Export / Cancel. Show editable path + Browse (`_get_save_path`) **only in native mode**.
- Browser mode: progressively enhance save UX. Use browser `showSaveFilePicker()` when available; otherwise fall back to `ui.download()` with the generated filename plus a short toast explaining that the browser saved it using the browser's normal download location/settings.
- Guardrail: browser save-picker support must never block export, replace the working fallback, or justify browser-specific behavior that risks existing download functionality.
- Success: Open file / Open folder (native only); kaleido failure → actionable notice

---

## CLI (Phase 5)

```bash
python -m mypyskindose --file-path file.dcm --settings settings.json \
  --export-format xlsx --export-path ./report.xlsx \
  --export-title "Case audit report"
```

**Wiring in `main.py`:** add `--export-format`, optional `--export-path`, and optional `--export-title`. When `--export-format` is set, route both single-file and multi-file execution through a shared export-capable path that captures the result object, normalized input bundle(s), provenance, and warnings — **no GUI state**. Reject incompatible flag combinations such as `--export-format` with `--input-preview-only` or `--aggregate`. Do not add `--mode export`.

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
class ExportExamSource:
    exam_id: str
    normalized_data: pd.DataFrame
    provenance: InputProvenance | None
    source_file: str | None
    effective_settings: PyskindoseSettings
    patient_offset: tuple[float, float, float]
    transform_meta: dict[str, Any] = field(default_factory=dict)
    extra_warnings: list[str] = field(default_factory=list)


@dataclass
class ExportSource:
    execution_context: Literal["gui", "cli"]
    # Exactly one of:
    output_dict: dict[str, Any] | None          # single-exam
    multi_exam_result: MultiExamResult | None   # multi-exam
    exams: list[ExportExamSource] = field(default_factory=list)
    calc_warnings: list[str] = field(default_factory=list)
    file_name: str | None = None
    colorscale: str = "jet"
    report_title: str | None = None
    load_timestamp: datetime | None = None
```

Writers consume `ExportPayload` only. Implement `render_*_bytes(payload) -> bytes` for browser-mode downloads and thin `write_*` wrappers for CLI/native path writes.

---

# Phased implementation checklist

## Phase 0 — Design sign-off (no code)

- [x] **0.1** Review this checklist with stakeholder; confirm v1 scope (XLSX + PDF required; HTML Phase 5; DOCX deferred).
- [x] **0.2** Confirm `reportlab` added under a new `export` optional extra in `pyproject.toml` (keep core deps unchanged for non-export users), then update license-notices workflow/docs as required by `dev-docs/LICENSE_COMPLIANCE.md`.
- [x] **0.3** Confirm file-size budget: each writer module < 800 lines; split helpers if needed.
- [x] **0.4** Confirm default filenames should be PHI-safer generic timestamps, not input-derived stems.
- [x] **0.5** Confirm browser-mode GUI should use progressive enhancement: `showSaveFilePicker()` when available, otherwise standard browser download with a short explanatory toast.
- [x] **0.6** Confirm browser save-picker support is optional enhancement only and must not break or delay the standard browser download path.

---

## Phase 1 — Export payload collector (core)

**Goal:** `collect_export_payload(source: ExportSource) -> ExportPayload` with full unit test coverage. No writers yet.

### 1.1 Package scaffold

- [ ] **1.1.1** Create `src/mypyskindose/export/` package and empty writer subpackage.
- [ ] **1.1.2** Define `ExportPayload` and nested dataclasses mirroring §1–§10 (title, provenance, exams[], cumulative metrics, corrections, warnings, images as `bytes | None` + metadata), plus a payload-specific schema-version constant. Keep report-layout data out of the existing JSON/dict export schema; additive schema enrichment is allowed only for fields that are broadly useful outside Rich Export.
- [ ] **1.1.3** Define `ExportExamSource` / `ExportSource` input bundles (see Data architecture).
- [ ] **1.1.4** Public API: `collect_export_payload(source) -> ExportPayload`.
- [ ] **1.1.5** Build export sources from existing GUI/CLI input bundles (`InputAdapterResult`, GUI per-exam meta, effective settings objects) instead of copying full normalized DataFrames into public result models.
- [ ] **1.1.6** If structured discarded-event counts cannot be recovered from the source bundle alone, add the **minimal** in-memory metadata needed on `ExamResult` (for example `discarded_events: dict[str, int]`) without expanding `PySkinDoseOutput.to_dict()` for report-only needs. **`ExamResult` is multi-exam only** — for the single-exam path (no `ExamResult`), carry the same `discarded_events` on the single-exam source bundle (`ExportExamSource` / `ExportSource`) or fall back to the warning-capture helper (1.1.7); never fabricate a zero count when unavailable (report `N/A`).
- [ ] **1.1.7** Implement a reusable warning-capture helper for GUI and CLI code paths so calculation-level QA warnings emitted via the `mypyskindose` logger are preserved for export without mutating the existing export JSON schema.

### 1.2 Source resolution (GUI vs CLI, single vs multi)

- [ ] **1.2.1** Implement `resolve_calculation_result(source)`:
  - If `source.multi_exam_result is not None` → multi-exam path (ignore `output_dict`).
  - Elif `source.output_dict is not None` → single-exam path.
  - Else → raise `ExportError("No calculation result")`.
  - **Normalize the two output shapes** (see §7 table) into one internal per-exam view so metrics/corrections code never branches on dict-vs-object: expose `psd`, `air_kerma`, correction arrays (via the §8 attribute/key map), and a **peak-vertex accessor** that handles the single-exam **sparse** `dose_map` (`[(idx, dose), …]` → max by dose, index = tuple[0]) and the multi-exam **dense** `np.ndarray` (`argmax`) uniformly.
- [ ] **1.2.2** Add `build_export_source_from_gui(state) -> ExportSource` in `gui/` (thin adapter; keeps `export/` GUI-import-free).
- [ ] **1.2.3** Add `build_export_source_from_cli(...) -> ExportSource` so CLI export does not depend on GUI state or ad-hoc reconstruction from serialized dicts.
- [ ] **1.2.4** Guard: `calculation_done` / equivalent CLI success before export.

### 1.3 Provenance (`export/provenance.py`)

- [ ] **1.3.1** Tabular branch: wrap `_tabular_input_meta` logic (move shared bits to `export/provenance.py`; GUI re-exports or imports from export).
- [ ] **1.3.2** DICOM branch: source type `dicom`, schema name `rdsr`, filenames from `loaded_exams` / `file_name`, tabular fields `N/A`, confidence `dicom_tags`.
- [ ] **1.3.3** Event counts: total loaded, processed, discarded + reason code list (read from structured `discarded_events: dict[str, int]` on input provenance / `ExamResult`; avoid natural language warning scraping). Ensure calculation warnings from the physics engine are collected in CLI mode (via the shared warning-capture helper and existing `ExamResult.warnings` / run-warning lists) and mapped to the payload.

### 1.4 Dosimetric metrics (`export/metrics.py`)

- [ ] **1.4.1** Per-exam PSD, air kerma, event counts from `ExamResult` / single `output_dict`.
- [ ] **1.4.2** Cumulative PSD from `aggregate_psd` or `max(dose_map)`; cumulative air kerma via **explicit sum** across exams.
- [ ] **1.4.3** PSD peak via the normalized peak-vertex accessor (1.2.1): dense `argmax` for multi-exam `aggregate_dose_map`; **max-by-dose over the sparse `[(idx, dose), …]` tuples** for the single-exam `output_dict` (index = `tuple[0]`, **not** a positional argmax). Then map vertex index → (X,Y,Z) from `patient_skin_cells` (guarding against uniform-zero maps by returning `None` for peak index and coordinates when PSD == 0 — for single-exam this means the sparse `dose_map` is empty); for multi-exam under differing offsets, identify Primary Contributing Exam, reporting baseline and primary coordinates + percentage dose contribution.
- [ ] **1.4.4** DAP / fluoro time: read from normalized/source columns when present (multiply `DoseAreaProduct_Gym2` by 10,000 for Gy·cm²). Only report fluoro time when a source exposes a trustworthy duration column; do not treat `PulseWidth_ms` as total fluoro duration.
- [ ] **1.4.5** Acquisition breakdown: group by normalized `acquisition_type`; sum $K_{a,r}$ and DAP per group.

### 1.5 Correction statistics (`export/metrics.py`)

- [ ] **1.5.1** Parse `corrections` block using the **§8 dict-key / attribute map** (dict keys are `backscatter` / `inverse_square_law` / `medium` / `table` / `correction_value_index` / `kerma` — **not** `k_bs`/`k_isq`/…). Read from `PySkinDoseOutput` attributes for multi-exam objects and from those exact `to_dict()["corrections"]` keys for single-exam `output_dict`.
- [ ] **1.5.2** `k_med` / `k_tab`: per-event scalar dose-weighted means per exam.
- [ ] **1.5.3** `k_bs` / `k_isq`: per event, mean across hit cells (None if `len(hits[i]) == 0`); then dose-weight across events where hit count > 0. If an exam has zero events with hits ($\sum_{i \in \text{hits}} K_{a,r,i} == 0$), report the exam dose-weighted mean as `"N/A"` (or `None`) to prevent division-by-zero.
- [ ] **1.5.4** Cumulative correction means: kerma-weighted across exams (formula in §8).
- [ ] **1.5.5** Min–max and arithmetic mean for each factor.

### 1.6 Settings, equipment, geometry sections

- [ ] **1.6.1** Serialize effective settings per exam from the `ExportExamSource.effective_settings` object (or existing GUI `build_settings(state)` output).
- [ ] **1.6.2** Equipment from normalized DataFrame / provenance-backed source metadata (manufacturer, model, normalization profile).
- [ ] **1.6.3** Phantom dimensions + mesh resolution from output patient block.
- [ ] **1.6.4** Coordinate corrections + table origin from `ExportExamSource.transform_meta` / GUI per-exam metadata.
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
- [ ] **1.8.3** `test_payload_dicom_provenance_fallback` — `import_provenance=None` → source type `dicom`, schema `rdsr`.
- [ ] **1.8.4** `test_payload_tabular_provenance` — mirrors `_tabular_input_meta` fields.
- [ ] **1.8.5** `test_psd_peak_vertex_index` — known dose map → expected index and coordinates.
- [ ] **1.8.6** `test_correction_sparse_hits` — `k_bs`/`k_isq` averaging with multi-hit events.
- [ ] **1.8.7** `test_export_without_kaleido` — mock `to_image` failure → `png_bytes=None`, no exception.
- [ ] **1.8.8** `test_build_export_source_from_gui` — multi vs single branch on mock `AppState`.
- [ ] **1.8.9** `test_build_export_source_from_cli` — single vs multi path, provenance preserved, no GUI imports.
- [ ] **1.8.10** `test_all_exam_miss_scenario` — all events miss phantom → cumulative PSD is 0, peak location is `None`, corrections are `N/A`.

**Phase 1 exit criteria:** all 1.x tests green; `collect_export_payload` usable from a one-off script with fixture data.

---

## Phase 2 — XLSX writer

**Goal:** `render_xlsx_bytes(payload)` + `write_xlsx(payload, path)` producing a clinical audit workbook.

### 2.1 Workbook layout

- [ ] **2.1.1** Implement `writers/xlsx.py`: `render_xlsx_bytes(payload: ExportPayload) -> bytes` plus `write_xlsx(payload: ExportPayload, path: Path) -> None`.

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
- [ ] **2.1.3** Cell formats: header row bold; write numeric cells as floats with explicit `cell.number_format` property (`'0.0'` for dose/kerma, `'0.0000'` for correction factors, `'0'` for fluoro time); translate patient offset setting names to clear physical anatomical directions (`d_lon`/`Tx` $\rightarrow$ Lateral Left-Right, `d_ver`/`Ty` $\rightarrow$ Vertical Anterior-Posterior, `d_lat`/`Tz` $\rightarrow$ Longitudinal Superior-Inferior); auto-fit column widths to maximum string length to prevent `###` clipping; explicitly enable sheet gridlines using robust syntax (`ws.sheet_view.showGridLines = True`) on every worksheet.
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

**Goal:** `render_pdf_bytes(payload)` + `write_pdf(payload, path)` using `reportlab`.

### 3.1 Document structure

- [ ] **3.1.1** Implement `writers/pdf.py`: `render_pdf_bytes(payload) -> bytes` plus `write_pdf(payload, path) -> None`.
- [ ] **3.1.2** Page 1: title block + **executive alert box** (`#FFF3CD` amber for warnings / `#F8D7DA` red for data loss/skips, 1.5 pt border) + cumulative summary table.
- [ ] **3.1.3** Subsequent pages: settings (translating patient offset setting names to clear physical anatomical directions: Lateral Left-Right, Vertical Anterior-Posterior, Longitudinal Superior-Inferior), results, corrections, warnings, images (page breaks between major sections). Implement a two-pass `ReportLab` canvas subclass (`NumberedCanvas`) to calculate total page count and render a consistent "Page X of Y" footer.
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
- [ ] **4.2.2** Modal: format `ui.select`, optional title field, Export / Cancel; path `ui.input` + Browse button only when `_is_native_mode()`.
- [ ] **4.2.3** Default filename from `mypyskindose_report_{date}_{time}.{ext}` (browser download name or native save-path basename).
- [ ] **4.2.4** Export handler: `build_export_source_from_gui(state)` → `collect_export_payload` → `render_*_bytes` on `run.io_bound`; native mode optionally writes via `write_*`, browser mode tries `showSaveFilePicker()` when supported and falls back to `ui.download()`. The fallback path is the required baseline and must remain the authoritative behavior during implementation.
- [ ] **4.2.5** Disable Export when `not state.calculation_done`.
- [ ] **4.2.6** Progress: spinner or `ui.notify('Generating report…')` for multi-exam.
- [x] **4.2.7** Success actions: Open file / Open folder rendered in native mode via a success dialog, using cross-platform OS launchers (`os.startfile` on Windows, `open`/`open -R` on macOS, `xdg-open` on Linux) in `_open_path()`; browser mode shows the download toast. Covered by `tests/gui/test_export_open_path.py` (6 tests). **Windows manual smoke still pending.**
- [ ] **4.2.8** (Optional v1.1) Results tab secondary "Export report…" button reusing same dialog factory.

### 4.3 Phase 4 manual smoke

- [ ] **4.3.1** Single-exam DICOM RDSR → XLSX + PDF from Export tab.
- [ ] **4.3.2** Tabular input (Radimetrics or DoseTrack fixture) → XLSX with provenance block.
- [ ] **4.3.3** Multi-exam (2 exams) → Summary sheet columns + cumulative PSD.
- [ ] **4.3.4** Simulate kaleido failure → export completes with notice, no crash.
- [ ] **4.3.5** Browser-mode GUI on Chromium-family browser: `showSaveFilePicker()` path works when available.
- [ ] **4.3.6** Browser-mode GUI fallback: download starts with generated filename and explanatory toast when save-picker support is unavailable; native mode shows path/Browse controls.
- [ ] **4.3.7** Regression guard: disabling or breaking save-picker support must not break browser export; fallback download still works in all supported browsers.

**Phase 4 exit criteria:** v1 acceptance criteria (GUI path) satisfied for XLSX and PDF.

---

## Phase 5 — HTML writer + CLI

**Goal:** Self-contained HTML export and headless `--export-format`.

### 5.1 HTML writer

- [ ] **5.1.1** `writers/html.py`: single file, embedded CSS, interactive Plotly 3D scenes (`fig.to_html(full_html=False)`), collapsible sections. Reserve static base64 PNG rendering for XLSX/PDF writers.
- [ ] **5.1.2** Executive alert block at top (HTML + inline styles matching PDF amber/red).
- [ ] **5.1.3** Tables for metrics/corrections; `meta` tag with `schema_version` and package version.

### 5.2 CLI flags (`main.py`)

- [ ] **5.2.1** Add `--export-format {xlsx,pdf,html}`, optional `--export-path PATH`, and optional `--export-title TEXT` (align CLI examples with existing parser arguments `--file-path` / `-f`).
- [ ] **5.2.2** When `--export-format` is set, force `settings.output_format = 'dict'` before calculation to ensure structured output. Route through a shared export-capable execution path that also captures warnings and provenance, then build `ExportSource(execution_context="cli", ...)`.
- [ ] **5.2.3** If `--export-path` is omitted, automatically derive output path: `mypyskindose_report_{YYYY-MM-DD}_{HHMMSS}.{ext}` in the same directory as the input file.
- [ ] **5.2.4** Reject incompatible flag combinations such as `--export-format` with `--aggregate` or `--input-preview-only`.
- [ ] **5.2.5** Print confirmation path on success (stdout).

### 5.3 Phase 5 tests

- [ ] **5.3.1** `test_cli_export_xlsx` — subprocess or `main()` with tmp path.
- [ ] **5.3.2** `test_write_html_smoke` — HTML contains embedded images or fallback notice.
- [ ] **5.3.3** CLI/GUI parity: same fixture → same cumulative kerma in XLSX Summary (compare cell values).
- [ ] **5.3.4** `test_cli_export_flag_conflicts` — `--export-format` rejects `--aggregate` / `--input-preview-only`.

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
- [x] **7.6** Archived `RICH_EXPORT_SPEC.md` → `plans/archive/`; `dev-docs/index.md` updated.

---

## Resolved decisions

| Topic | Decision |
|-------|----------|
| PDF library | `reportlab` in `export` extra |
| XLSX images | `openpyxl` anchored cells |
| Existing JSON/dict export schema | Keep report-layout data out; additive enrichment is allowed for broadly useful fields only |
| Cumulative air kerma | Sum per-exam `air_kerma` in collector |
| Cumulative corrections | Kerma-weighted mean of per-exam weighted means |
| GUI result source | `multi_exam_result` takes precedence over `output` |
| DICOM provenance | Dedicated branch when `import_provenance is None`, but schema naming stays aligned with current `rdsr` / `dicom` usage |
| `k_bs`/`k_isq` aggregation | Mean per event over hits, then kerma-weight across events |
| Per-event correction table | Not in v1 Rich Export |
| HTML shape | Single `.html` file |
| GUI/browser save UX | Native mode may choose a filesystem path; browser mode uses `showSaveFilePicker()` when supported and otherwise falls back to normal browser download plus a short explanatory toast |
| Browser save-picker risk policy | Never trade away the existing cross-browser download path for save-picker support; the picker is additive only |
| Default filename | PHI-safer generic timestamped name, not input-derived stem |

---

## v1 acceptance criteria

- [x] Single-exam calculation → XLSX and PDF from Export tab.
- [x] All §1–§10 fields present with correct physics names.
- [x] Multi-exam: per-exam + cumulative columns for PSD, $K_{a,r}$, corrections, warnings.
- [x] Warnings on first page / overview sheet.
- [x] Export succeeds when image render fails (notice, no crash). — `test_export_without_kaleido`
- [x] Browser-mode GUI works without fake local-path semantics; native mode supports Browse/save-path selection. (Baseline `ui.download()` fallback shipped; `showSaveFilePicker()` progressive enhancement deferred — never blocks export.)
- [x] Phase 1–3 unit tests green in CI. (Plus Phase 5 CLI/HTML tests — 25 total.)
- [x] New dependencies only via `export` optional extra (+ existing `openpyxl`, `kaleido`).
- [x] Existing JSON/dict export schema remains backward compatible (payload is separate; no `PySkinDoseOutput.to_dict()` change).
- [ ] Manual browser/native save smoke (Phase 4.3.x) — pending human verification.

---

## References

- Draft spec: [RICH_EXPORT_SPEC.md](archive/RICH_EXPORT_SPEC.md)
- Coordinates: [VENDOR_COORDINATE_SYSTEMS.md](../VENDOR_COORDINATE_SYSTEMS.md)
- Input flow: [INPUT_DATA_FLOW_AND_OFFSETS.md](../INPUT_DATA_FLOW_AND_OFFSETS.md)
- Data model: `src/mypyskindose/format_export_data.py`
- Input adapters: `src/mypyskindose/input_adapters/models.py`
- GUI export: `src/mypyskindose/gui/tabs/export.py`
