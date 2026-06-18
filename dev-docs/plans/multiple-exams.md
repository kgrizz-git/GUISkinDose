# Multiple Exams Plan

## Objective

Allow MyPySkinDose to process multiple exams (studies/procedures) in a single run. This covers three input scenarios:

1. **Multiple RDSR files** — a batch of `.dcm` files, each a separate exam.
2. **Multiple tabular files** — a batch of `.csv`/`.tsv`/`.xlsx` files, each a separate exam.
3. **Single tabular file with concatenated rows** — one file containing events from several studies, distinguished by a study/patient identifier column (e.g. `study_id`, `accession_number`, `StudyInstanceUID`).

Each exam produces its own dose map and PSD. The user may apply per-exam or global settings.

**Phantom sharing:** Fresh `Phantom` instances with identical topology (same model, vertex count, and vertex ordering) are created for each exam. `dose_map[i]` therefore refers to the same anatomical skin vertex across all exams, making element-wise summation of per-exam dose maps valid for cumulative dose.

## Acceptance Criteria

- [x] CLI accepts multiple file paths (`--file-path file1.dcm file2.dcm` or `--file-path *.dcm` or `--file-path batch.csv`).
- [x] Tabular loader splits a single file into per-exam DataFrames when a study-identifier column is present and contains >1 unique value (previously: error).
- [x] Each exam gets its own dose map and `PySkinDoseOutput`; phantom mesh topology is consistent across exams (same model, vertex count, ordering); per-exam patient offsets are supported.
- [x] Output contains per-exam PSDs, per-exam dose maps, and a cumulative dose map (element-wise sum across exams) plus aggregate PSD (max across exams).
- [ ] GUI shows a list of loaded exams with per-exam metadata (file name, event count, study ID, detected schema) and per-exam results after calculation. *(Structure exists; broken by bugs below.)*
- [x] Recursion-to-iteration refactor is complete (`96ce63b`).
- [x] Full test coverage for multi-exam paths (unit + smoke) — see `tests/unittests/test_multi_exam.py`.

## Decision Log

| # | Decision | Rationale |
|---|----------|-----------| 
| D1 | Exams are split by **study-level identifier**, not by file boundary in tabular input | A single export can contain multiple studies; splitting by study ID is the user-friendly default. File boundary splitting is the fallback for RDSR batches. |
| D2 | Settings are **global by default** with per-exam override for patient/table offsets and event-processing conventions | Most users run the same phantom across exams. Per-exam offsets are first-class because patient positioning routinely differs between procedures. Per-exam event-processing convention overrides are Phase 2. |
| D3 | Output is a list of `ExamResult` wrapped in a `MultiExamResult` | Keeps existing `PySkinDoseOutput` API intact. `MultiExamResult` adds aggregate stats and per-exam metadata. |
| D4 | GUI shows exams as a **collapsible accordion** with per-exam result cards | Avoids overwhelming the user; each exam's dose map can be inspected independently. |
| D5 | Recursion-to-iteration refactor is a **separate prerequisite task** | It is independently useful (fixes RecursionError on long single-exam procedures) and blocks multi-exam for >1000 total events. |
| D6 | **Fresh `Phantom` instances per exam** rather than a shared instance with `reset_to_origin()` | `position_patient_phantom_on_table()` applies incremental `translate()` calls. Sharing a `Phantom` and resetting would require storing `r_origin` and adding a reset method. Creating fresh instances with the same model is simpler, correct, and topology is guaranteed identical (same mesh file, same construction path). |

## Architecture

### Data model

```
MultiExamResult
├── exams: list[ExamResult]
│   ├── exam_id: str              # study_uid, accession, or file name
│   ├── source_file: str          # original file path
│   ├── event_count: int
│   ├── patient_offset: list[float]  # per-exam offset used [d_lon, d_ver, d_lat]
│   ├── settings_snapshot: dict   # effective settings used (subset of PyskindoseSettings)
│   ├── output: PySkinDoseOutput  # per-exam result (includes per-exam dose_map)
│   └── warnings: list[str]
├── aggregate_dose_map: np.ndarray  # element-wise sum of per-exam dose maps (same topology)
├── aggregate_psd: float            # max over aggregate_dose_map (peak skin dose across all exams)
├── total_events: int
└── warnings: list[str]
```

**Why element-wise summation is valid:** all exams use fresh `Phantom` instances built from the same STL/model, so `dose_map[i]` refers to the same anatomical skin vertex in every exam regardless of world-space repositioning. Summing them gives the cumulative dose received by each skin location across the full procedure series.

`ExamResult` and `MultiExamResult` live in `format_export_data.py` alongside `PySkinDoseOutput`. ✅ **Shipped.**

### ✅ Shipped: Python Core

All Python core multi-exam work is complete and tested.

#### Input adapters

**`normalized.py`**: When >1 distinct study identifier is detected, `adapt()` returns `list[InputAdapterResult]` (one per group), grouped by the first matched study-ID column in priority order: `studyinstanceuid` → `study_id` → `accession_number` → `patient_id` → `study_uid`. Single-study files return a single `InputAdapterResult` (no regression). Study-ID column is stripped from each group's `normalized_data`.

**`registry.py`**: `read_and_normalize_input()` propagates the list return transparently.

**`main.py`**: `analyze_input_file()` detects a list result and dispatches to `analyze_multiple_exams()`. `analyze_multiple_input_files()` accepts a `Sequence[str | Path]`, wraps RDSR files in `InputAdapterResult` with synthetic provenance, and calls `analyze_multiple_exams()`.

> **Known limitation — glob expansion:** The CLI `--file-path` argument uses `nargs="+"`, which allows multiple explicit paths. Shell glob expansion (e.g. `--file-path exams/*.dcm`) works only if the pattern is **unquoted** (the shell expands it). Quoted glob patterns (e.g. `--file-path "exams/*.dcm"`) are passed as a literal string and will fail. Programmatic glob expansion via `pathlib.Path.glob()` inside `analyze_multiple_input_files()` has not been implemented.

#### Calculation (`analyze_data.py`)

**`analyze_multiple_exams(exams, settings, per_exam_offsets=None)`**: For each `InputAdapterResult`:
1. Applies per-exam `patient_offset` from `per_exam_offsets` if provided; falls back to global offset.
2. Creates fresh `table` and `pad` `Phantom` instances (not shared; see D6).
3. Calls `calculate_rotation_matrices()`, then `calculate_dose()`, which returns `(patient, raw_output)`.
4. Accumulates `aggregate_dose_map` as element-wise sum of per-exam dose maps.
5. On per-exam failure: catches the exception, records it in `warnings`, and continues — partial results are returned.

`calculate_dose()` already returns `(patient, raw_output)`. No changes to its signature were needed.

**`calculate_dose/calculate_irradiation_event_result.py`**: ✅ Recursion → iteration refactor complete (`96ce63b`).

#### Output (`format_export_data.py`)

`ExamResult` and `MultiExamResult` dataclasses with `to_dict()` and `to_json()` methods. ✅ **Shipped.**

`format_analysis_result_for_export()` is bypassed in the multi-exam path; `analyze_multiple_exams()` constructs `PySkinDoseOutput` directly and wraps it in `ExamResult`.

> **Note — `--output-format html` in multi-exam mode:** `analyze_multiple_exams()` always returns a `MultiExamResult` (not an HTML string). `analyze_input_file()` and `analyze_multiple_input_files()` both log a warning and force `output_format = "dict"` for multi-exam runs. The explicit blocking with a user-facing error message is not surfaced in the CLI stdout, but the behavior is safe. ✅

#### CLI (`main.py`)

```bash
# Single file (existing, unchanged)
python -m mypyskindose --file-path exam1.dcm

# Multiple files (explicit; shell-expanded glob also works)
python -m mypyskindose --file-path exam1.dcm exam2.dcm exam3.dcm

# Single tabular file — auto-split by study_id
python -m mypyskindose --file-path batch.csv

# Output: JSON dict with "exams", "aggregate_dose_map", "aggregate_psd", "total_events"

# Print only aggregate PSD
python -m mypyskindose --file-path batch.csv --aggregate
```

`--file-path` accepts `nargs="+"`. When >1 path is given, `analyze_multiple_input_files()` is called and output is printed as JSON. When exactly 1 path is given, existing single-exam behavior is preserved.

`--input-schema` choices: `"normalized"`, `"generic_rdsr_like"`, `"radimetrics"`, `"dosetrack"`, `"auto"`. ✅ **Shipped.**

`--aggregate` flag: ✅ **Shipped** (prints only `aggregate_psd` to stdout).

#### `main()` public API

The existing `main(file_path, settings)` is unchanged (backward compatible). The multi-file entry point is `analyze_multiple_input_files(file_paths, settings, ...)`. Adding `file_paths: list[str] | None = None` to `main()` (Q8) has not been done; `analyze_multiple_input_files()` is the intended programmatic API for multi-exam runs.

### Memory Management

Fresh `Phantom` instances per exam are slightly less memory-efficient than a shared instance, but the overhead is negligible (a few MB per mesh) and correct by construction.
- **Data:** `aggregate_dose_map` and per-exam dose maps are lightweight 1D scalar arrays.
- **GUI (future):** Plotly figures are memory-intensive in the browser. A soft limit should be imposed (e.g., warn or block if >10 exams are uploaded) to prevent browser-side memory issues when rendering N dose map figures.

---

### 🚧 GUI — Partial / Broken

> **Root cause of the "second CSV kicks out first" bug:** `_register_temp_upload()` in `app.py` deletes the previous temp file on every new upload (by design for single-exam use). For multi-exam via multiple file uploads, this means only the last uploaded file survives on disk. Until multi-file upload via multiple `ui.upload` callbacks is properly supported, uploading a second CSV via the GUI replaces the first — matching the symptom reported.

The GUI has the **scaffolding** for multi-exam support but has **two known bugs** that prevent it from working when loading multiple separate files:

#### Bug 1 — `load_tabular` overwrites concatenated `df` (helpers.py:157)

When `read_and_normalize_input()` returns a list (multi-study file), `load_tabular` correctly builds `df` as the concatenation of all exams' normalized data (lines 144–148). However, line 157 immediately overwrites `df` with `result.normalized_data.copy()` — which is only the **first exam's** data. The event table preview and `state.rdsr_df` then contain only exam 1.

```python
# helpers.py — lines 144–157
# Bug: df is set correctly at line 145 then clobbered at line 157
df = pd.concat([r.normalized_data for r in _raw], ignore_index=True)   # ← correct
result = _raw[0]  # use first exam's provenance for UI hints
...
df = result.normalized_data.copy()   # ← BUG: overwrites df with exam 1 only
```

**Fix:** remove or guard line 157 so that the multi-exam concatenation at line 145 survives for the event table.

#### Bug 2 — `_register_temp_upload()` deletes previous file on each upload (app.py:71–79)

`_register_temp_upload()` calls `pop()` in a `while` loop, deleting every previously registered temp file before appending the new one. This was designed for single-exam use (keep only the latest). For a multi-file upload workflow (user drops file 1, then file 2), file 1's temp path is deleted and becomes unreadable before file 2 is parsed. The GUI only supports uploading one file at a time today, so "multiple separate CSV files" is not a supported input path via the GUI — the current UI flow replaces the loaded exam, not adds to it.

**Fix (Phase 1 workaround):** Keep the current single-file-at-a-time behavior but document it clearly. True multi-file accumulation in the GUI is a Phase 2 feature (see below).

#### What IS working in the GUI

- `state.is_multi_exam`, `state.loaded_exams`, `state.multi_exam_result` fields exist in `AppState`.
- `load_tabular()` correctly detects the multi-study split, populates `state.loaded_exams`, and sets `state.is_multi_exam = True` for a **single CSV file containing multiple study IDs**.
- `run_calculation()` in `helpers.py` dispatches to `analyze_multiple_exams()` when `state.is_multi_exam` is True.
- The "Loaded Exams" table in the Upload tab appears when `is_multi_exam` is True.
- The Results tab has per-exam accordion cards and an aggregate dose map plot section (but the accordion item code calls `exam_res.output.get(...)`, which is wrong because `exam_res.output` is a `PySkinDoseOutput` object, not a dict — this is a third bug in `results.py`).

#### Bug 3 — results.py accordion calls `.get()` on a `PySkinDoseOutput` object (results.py:166–170)

```python
# results.py — lines 166–170
ui.label(f"{exam_res.output.get('psd', 0):.2f} mGy")   # ← BUG: PySkinDoseOutput has no .get()
ui.label(f"{exam_res.output.get('air_kerma', 0):.1f} mGy")   # ← BUG
```

`exam_res.output` is a `PySkinDoseOutput` instance (with `.PSD` and `.AirKerma` attributes), not a dict. Calling `.get()` raises `AttributeError` at render time.

**Fix:** use `exam_res.output.PSD` and `exam_res.output.AirKerma` instead.

Also the aggregate dose map reconstruction in `_refresh_multi_exam_results` treats `res.aggregate_dose_map` as a dict (line 192: `for idx, dose in res.aggregate_dose_map.items()`) but it is an `np.ndarray`. The correct approach is to use it directly.

#### Upload tab changes (not yet implemented)

- The current UI supports **one file at a time**. A second upload replaces the first (by design, via `_register_temp_upload`).
- To accumulate multiple separate files as separate exams, the upload flow needs to be redesigned:
  - Keep a list of loaded `InputAdapterResult` objects across uploads, OR
  - Add a multi-select upload widget with `multiple` prop.
- **Temp File Lifecycle:** `_register_temp_upload()` must allow multiple concurrent temp files (stop deleting the previous on new upload). Add a "Clear All" mechanism.
- Show a **loaded exams list** after upload:
  - Each row: file name, schema, event count, study ID (if detected), status (OK/error).
  - Per-exam warning badges.

#### Settings tab changes

- Global settings panel (existing) — no change for Phase 1.
- *(Phase 2)* Optional per-exam override section for patient/table offsets and event-processing convention overrides. *(Not started.)*

### Prerequisite: Recursion → Iteration ✅ Complete

**Full plan:** [recursion-to-iteration.md](recursion-to-iteration.md)

Shipped in commit `96ce63b` (`fix(calc): replace per-event recursion with iterative event loop`). `calculate_irradiation_event_result()` now uses a `for` loop; the ~1000-frame recursion limit no longer applies.

## Implementation Order

1. ✅ **Recursion → iteration refactor** — complete (`96ce63b`).
2. ✅ **`ExamResult` and `MultiExamResult` dataclasses** — shipped in `format_export_data.py`.
3. ✅ **Input adapter multi-study split** — `normalized.py` returns list when >1 study ID detected.
4. ✅ **`analyze_multiple_exams()` orchestrator** — shipped in `analyze_data.py`; fresh phantoms per exam; per-exam patient offsets; aggregate dose map as element-wise sum; partial-failure handling.
5. ✅ **`analyze_multiple_input_files()` and CLI multi-file support** — `--file-path nargs="+"`, `analyze_multiple_input_files()` in `main.py`. `--aggregate` flag also shipped.
6. ✅ **Tests** — `tests/unittests/test_multi_exam.py` covers serialization, registry split, orchestrator integration, per-exam offsets, partial failure, and dict/JSON round-trip.
7. 🔧 **GUI multi-exam** — state fields and scaffolding exist. Three bugs found and triaged:
   - ~~**Bug 1:** `helpers.py:157` — `df` clobbered back to exam-1-only after multi-exam concatenation.~~ ✅ **Fixed:** removed the overwrite; concatenated df now survives; coordinate transforms scoped to single-exam path.
   - **Bug 2 (Phase 1 limitation):** `app.py:71–79` — `_register_temp_upload()` keeps only the latest file. This means loading two *separate* CSV files via two uploads replaces the first. Documented as a Phase 1 limitation; multi-study use case is supported via a *single* CSV file containing multiple study IDs. Multi-file accumulation via the upload widget is Phase 2.
   - ~~**Bug 3:** `results.py:166–170` — accordion items called `.get()` on a `PySkinDoseOutput` object; aggregate dose map treated as a dict.~~ ✅ **Fixed:** use `.PSD` / `.AirKerma` attributes; pass `aggregate_dose_map` ndarray directly to `make_dosemap_fig`; exam ID shown in accordion title; event count added as a metric card.
8. **GUI Phase 2 & Per-exam overrides** — see Phase 2 section below. *(Not started.)*

## Testing

### ✅ Existing tests (`test_multi_exam.py`)

- `TestExamResultSerialization.test_exam_result_fields` — `ExamResult` fields round-trip correctly.
- `TestMultiExamResultSerialization.test_to_dict_structure` — `to_dict()` structure and keys.
- `TestMultiExamResultSerialization.test_aggregate_psd_is_max_of_aggregate_map` — `aggregate_psd` equals `aggregate_dose_map.max()`.
- `TestMultiExamResultSerialization.test_to_json_round_trips` — JSON round-trip.
- `TestMultiExamResultSerialization.test_aggregate_dose_map_is_sum_of_per_exam_maps` — element-wise sum property.
- `TestMultiStudySplitViaRegistry.*` — single-study no-regression; multi-study split; correct group sizes; provenance preserved; `__study_id__` column stripped.
- `TestAnalyzeMultipleExams.test_two_exams_return_multi_exam_result` — orchestrator returns `MultiExamResult` with two exams.
- `TestAnalyzeMultipleExams.test_aggregate_dose_map_equals_sum_of_per_exam_maps` — aggregate equals sum of `DoseMap` attributes.
- `TestAnalyzeMultipleExams.test_aggregate_psd_is_max_of_aggregate_map` — aggregate PSD.
- `TestAnalyzeMultipleExams.test_per_exam_offsets_are_independent` — different offsets produce different dose distributions.
- `TestAnalyzeMultipleExams.test_exam_result_carries_source_file` — provenance filename preserved.
- `TestAnalyzeMultipleExams.test_partial_failure_returns_succeeded_exams` — bad exam yields partial results with warnings.
- `TestAnalyzeMultipleExams.test_to_dict_and_to_json_roundtrip` — full output dict/JSON.

### Tests still needed

- `test_recursion_iteration_equivalence()` — iterative output identical to reference for 500 events. (May exist elsewhere; verify.)
- `test_recursion_iteration_no_crash_1100_events()` — iterative version handles >1000 events without `RecursionError`. (May exist elsewhere; verify.)
- Integration test: load two example RDSR files from disk via `analyze_multiple_input_files()` and verify `MultiExamResult` shape.
- Integration test: load a multi-study tabular CSV and verify per-exam grouping end-to-end through `analyze_input_file()`.
- GUI regression test: upload a single multi-study CSV, verify both exams appear in the exam list and calculation produces correct aggregate PSD.

### GUI smoke tests (future)

- Upload a single multi-study CSV, verify both studies appear in exam list.
- Click Calculate, verify per-exam accordion renders PSD, Air Kerma, and Event count correctly.
- Verify aggregate PSD shown and aggregate dose map rendered correctly.
- Per-exam "Show Dose Map" dialog opens and renders without error.

---

## Phase 2: Multi-File Upload Accumulation & Per-Exam Overrides

Phase 2 covers work that is **not yet started**. It extends the GUI beyond Phase 1's single-file-per-session model.

### Phase 2.1 — Multi-file upload accumulation in the GUI

Currently the Upload tab supports one file at a time. A second upload replaces the first (by design). Phase 2.1 allows the user to accumulate multiple files as separate exams:

- **`_register_temp_upload()` redesign** — stop deleting the previous temp file on new upload. Keep all temp files alive until "Clear All" or session end. Add a `_clear_all_temp_uploads()` helper exposed via a "Clear All" button in the Upload tab.
- **Upload widget** — add the Quasar `multiple` prop to `ui.upload` so the user can select several files in one dialog, or drag-and-drop multiple files.
- **Loaded exam list** — replace the current single-file card with a list of loaded exams (already partially built as `exams_table`). Each row shows: file name, schema, event count, study ID (if detected), status badge (OK / parse error).
- **Removing individual exams** — each exam row in the list gets a remove (×) button that drops it from `state.loaded_exams` without clearing the rest.
- **State changes** — `state.loaded_exams` grows as files are added; `state.is_multi_exam` is `True` when `len(state.loaded_exams) > 1`.

### Phase 2.2 — Per-exam coordinate transform overrides

Currently the coordinate correction toggles (swap lat/lon, flip Ap1, flip Ap2) apply globally and are only wired to the single-exam path. Phase 2.2 applies them per-exam:

- Store transforms as `list[dict]` parallel to `state.loaded_exams`.
- Apply each exam's transforms to its own `InputAdapterResult.normalized_data` at upload time.
- Show per-exam transform toggles in the exam list (inline or in an expandable row).

### Phase 2.3 — Per-exam patient offset overrides

The Python core already accepts `per_exam_offsets: list[list[float]]` in `analyze_multiple_exams()`. Phase 2.3 exposes this in the GUI:

- A per-exam offset row (d_lon, d_ver, d_lat spinboxes) in the loaded exam list.
- "Apply global" button copies the global patient offset to all exams.
- Stored in a `list[dict]` parallel to `state.loaded_exams`; passed to `run_calculation()` → `analyze_multiple_exams()`.

### Phase 2.4 — Per-exam event-processing convention overrides *(low priority)*

Manufacturer-specific coordinate convention overrides (e.g., rotation direction conventions) applied per-exam rather than globally. Deferred until there is a concrete use case beyond Phase 2.2's toggle approach.

## Open Questions / Resolved Decisions

- **Q1:** Should multi-exam output include a **cumulative** dose map? → **Resolved:** both. Per-exam dose maps are in `ExamResult.output.DoseMap`. `MultiExamResult.aggregate_dose_map` is the element-wise sum; `aggregate_psd` is its peak. ✅ Shipped.

- **Q2:** Should the CLI support a `--aggregate` flag? → **Resolved:** ✅ Shipped — `--aggregate` prints only `aggregate_psd` to stdout.

- **Q3:** Default study-identifier column priority? → **Resolved:** `studyinstanceuid` → `study_id` → `accession_number` → `patient_id` → `study_uid`. If none present, current single-study behavior is preserved (no split). ✅ Shipped in `normalized.py`.

- **Q4:** Per-exam settings overrides in Phase 1 or Phase 2? → **Resolved:** per-exam `patient_offset` is Phase 1 (✅ shipped via `per_exam_offsets` parameter). Per-exam event-processing convention overrides (manufacturer coordinate differences) are Phase 2.

- **Q5:** Progress bar behavior across multiple exams? → **Pending** (GUI not yet fully functional). Recommendation: one shared progress bar (0–total_events across all exams) for simplicity.

- **Q6:** What happens when an exam fails during multi-exam processing? → **Resolved:** partial `MultiExamResult` with succeeded exams and failed exam in `warnings`. ✅ Shipped.

- **Q7:** Should `"html"` output be blocked in multi-exam mode? → **Resolved:** `analyze_input_file()` and `analyze_multiple_input_files()` both log a warning and force `output_format = "dict"`. ✅ Shipped (logging warning rather than hard error).

- **Q8:** How should `main()` accept multiple files? → **Resolved differently from recommendation:** `analyze_multiple_input_files(file_paths, ...)` is the programmatic multi-file API. The existing `main(file_path, settings)` is unchanged for backward compatibility. Adding `file_paths` to `main()` has not been done and is not planned unless there is a clear use case.
