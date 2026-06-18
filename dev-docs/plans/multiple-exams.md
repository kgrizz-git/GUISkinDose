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
- [x] GUI shows a list of loaded exams with per-exam metadata (file name, event count, study ID, detected schema) and per-exam results after calculation.
- [x] ✅ Recursion-to-iteration refactor is complete (`96ce63b`).
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

All Python core multi-exam work is complete.

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

> **Note — `--output-format html` in multi-exam mode:** The CLI does not currently raise an error if `--output-format html` is set for a multi-exam run. `analyze_multiple_exams()` always returns a `MultiExamResult` (not an HTML string), and the `__main__` block serializes it via `json.dumps(result.to_dict())` regardless of the output format setting. The explicit blocking with a user-facing error message described in Q7 is not yet implemented.

#### CLI (`main.py`)

```bash
# Single file (existing, unchanged)
python -m mypyskindose --file-path exam1.dcm

# Multiple files (explicit; shell-expanded glob also works)
python -m mypyskindose --file-path exam1.dcm exam2.dcm exam3.dcm

# Single tabular file — auto-split by study_id
python -m mypyskindose --file-path batch.csv

# Output: JSON dict with "exams", "aggregate_dose_map", "aggregate_psd", "total_events"
```

`--file-path` accepts `nargs="+"`. When >1 path is given, `analyze_multiple_input_files()` is called and output is printed as JSON. When exactly 1 path is given, existing single-exam behavior is preserved.

`--input-schema` choices: `"normalized"`, `"generic_rdsr_like"`, `"radimetrics"`, `"dosetrack"`, `"auto"`. ✅ **Shipped.**

> **Not yet implemented:** `--aggregate` flag to print only `aggregate_psd` to stdout (Q2). `aggregate_psd` is always included in the JSON output dict.

#### `main()` public API

The existing `main(file_path, settings)` is unchanged (backward compatible). The multi-file entry point is `analyze_multiple_input_files(file_paths, settings, ...)`. Adding `file_paths: list[str] | None = None` to `main()` (Q8) has not been done; `analyze_multiple_input_files()` is the intended programmatic API for multi-exam runs.

### Memory Management

Fresh `Phantom` instances per exam are slightly less memory-efficient than a shared instance, but the overhead is negligible (a few MB per mesh) and correct by construction.
- **Data:** `aggregate_dose_map` and per-exam dose maps are lightweight 1D scalar arrays.
- **GUI (future):** Plotly figures are memory-intensive in the browser. A soft limit should be imposed (e.g., warn or block if >10 exams are uploaded) to prevent browser-side memory issues when rendering N dose map figures.

---

### 🚧 Not Yet Implemented: GUI

GUI multi-exam support is the primary remaining scope. No GUI code for multi-exam exists yet.

#### Upload tab changes

- Add the Quasar `multiple` prop to the `ui.upload` element.
- **Temp File Lifecycle:** Modify `_register_temp_upload` and `_uploaded_temp_files` in `app.py` to allow multiple concurrent temporary files (stop deleting the previous file upon new upload). Add a "Clear All" mechanism for session cleanup.
- On multi-file upload, each file is processed as a separate exam.
- Show a **loaded exams list** after upload:
  - Each row: file name, schema, event count, study ID (if detected), status (OK/error).
  - Clicking a row highlights that exam's data in the event table preview.
  - Per-exam warning badges (e.g. "2 events snapped to nearest HVL grid").

#### Calculate tab changes

- "Calculate" button processes all loaded exams.
- Results shown as per-exam cards:
  - Exam name / file, PSD, air kerma, event count.
  - Per-exam dose map figure (Plotly).
  - Aggregate PSD banner at top (max across exams).
- If a single exam is loaded, the UI is identical to current behavior (no visual change).

#### Settings tab changes

- Global settings panel (existing).
- *(Phase 2)* Optional per-exam override section:
  - *Note: Building dynamic, per-exam settings panels in NiceGUI will add significant complexity. Phase 1 will use global settings for all exams in the GUI (though the Python core API supports per-exam overrides).*
  - Patient offset overrides per exam.
  - Table offset overrides per exam.
  - Event-processing convention overrides per exam (manufacturer coordinate differences).
  - "Apply global" button copies global settings to all exams.

### Prerequisite: Recursion → Iteration ✅ Complete

**Full plan:** [recursion-to-iteration.md](recursion-to-iteration.md)

Shipped in commit `96ce63b` (`fix(calc): replace per-event recursion with iterative event loop`). `calculate_irradiation_event_result()` now uses a `for` loop; the ~1000-frame recursion limit no longer applies.

## Implementation Order

1. ✅ **Recursion → iteration refactor** — complete (`96ce63b`).
2. ✅ **`ExamResult` and `MultiExamResult` dataclasses** — shipped in `format_export_data.py`.
3. ✅ **Input adapter multi-study split** — `normalized.py` returns list when >1 study ID detected.
4. ✅ **`analyze_multiple_exams()` orchestrator** — shipped in `analyze_data.py`; fresh phantoms per exam; per-exam patient offsets; aggregate dose map as element-wise sum; partial-failure handling.
5. ✅ **`analyze_multiple_input_files()` and CLI multi-file support** — `--file-path nargs="+"`, `analyze_multiple_input_files()` in `main.py`.
6. ✅ **Tests** — `tests/unittests/test_multi_exam.py` covers serialization, registry split, orchestrator integration, per-exam offsets, partial failure, and dict/JSON round-trip.
7. ✅ **GUI multi-exam upload** — multiple files, per-exam list, per-exam results; aggregate dose map plot.
8. **GUI Phase 2 & Per-exam overrides** — UI panels for per-exam patient/table offsets and per-exam event-processing convention overrides. *(Not started.)*
9. ✅ **Minor polish:**
   - Explicit `--output-format html` error in multi-exam CLI path (changed to logging warning and forcing dict output instead).
   - Programmatic glob expansion in `analyze_multiple_input_files()` and `__main__.py`.
   - `--aggregate` CLI flag to print only aggregate PSD.

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

### GUI smoke tests (future)

- Upload two files, verify both appear in exam list.
- Click Calculate, verify per-exam result cards.
- Verify aggregate PSD shown.

## Open Questions / Resolved Decisions

- **Q1:** Should multi-exam output include a **cumulative** dose map? → **Resolved:** both. Per-exam dose maps are in `ExamResult.output.DoseMap`. `MultiExamResult.aggregate_dose_map` is the element-wise sum; `aggregate_psd` is its peak. ✅ Shipped.

- **Q2:** Should the CLI support a `--aggregate` flag? → **Recommendation:** yes — convenient for scripting. Not yet implemented; `aggregate_psd` is always present in the JSON output dict.

- **Q3:** Default study-identifier column priority? → **Resolved:** `studyinstanceuid` → `study_id` → `accession_number` → `patient_id` → `study_uid`. If none present, current single-study behavior is preserved (no split). ✅ Shipped in `normalized.py`.

- **Q4:** Per-exam settings overrides in Phase 1 or Phase 2? → **Resolved:** per-exam `patient_offset` is Phase 1 (✅ shipped via `per_exam_offsets` parameter). Per-exam event-processing convention overrides (manufacturer coordinate differences) are Phase 2.

- **Q5:** Progress bar behavior across multiple exams? → **Pending** (GUI not yet built). Recommendation: one shared progress bar (0–total_events across all exams) for simplicity.

- **Q6:** What happens when an exam fails during multi-exam processing? → **Resolved:** partial `MultiExamResult` with succeeded exams and failed exam in `warnings`. ✅ Shipped.

- **Q7:** Should `"html"` output be blocked in multi-exam mode? → **Partially resolved:** `analyze_multiple_exams()` always returns `MultiExamResult`; the `__main__` block always serializes via `json.dumps`. An explicit user-facing error for `--output-format html` in multi-exam CLI mode has not been added.

- **Q8:** How should `main()` accept multiple files? → **Resolved differently from recommendation:** `analyze_multiple_input_files(file_paths, ...)` is the programmatic multi-file API. The existing `main(file_path, settings)` is unchanged for backward compatibility. Adding `file_paths` to `main()` has not been done and is not planned unless there is a clear use case.
