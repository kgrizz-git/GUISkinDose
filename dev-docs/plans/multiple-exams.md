# Multiple Exams Plan

## Objective

Allow MyPySkinDose to process multiple exams (studies/procedures) in a single run. This covers three input scenarios:

1. **Multiple RDSR files** — a batch of `.dcm` files, each a separate exam.
2. **Multiple tabular files** — a batch of `.csv`/`.tsv`/`.xlsx` files, each a separate exam.
3. **Single tabular file with concatenated rows** — one file containing events from several studies, distinguished by a study/patient identifier column (e.g. `study_id`, `accession_number`, `StudyInstanceUID`).

Each exam produces its own dose map and PSD. The user may apply per-exam or global settings.

**Phantom sharing:** There is one phantom per run (same patient across exams). The phantom (patient, table, pad) is created once and shared across all exams. Each exam gets its own dose map and `PySkinDoseOutput`.

## Acceptance Criteria

- [ ] CLI accepts multiple file paths (`--file-path file1.dcm file2.dcm` or `--file-path *.dcm` or `--file-path batch.csv`).
- [ ] Tabular loader splits a single file into per-exam DataFrames when a study-identifier column is present and contains >1 unique value (previously: error).
- [ ] Each exam gets its own dose map and `PySkinDoseOutput`; phantom mesh (model, topology, vertex ordering) is shared across exams; per-exam patient offsets are supported.
- [ ] Output contains per-exam PSDs, per-exam dose maps, and a cumulative dose map (element-wise sum across exams) plus aggregate PSD (max across exams).
- [ ] GUI shows a list of loaded exams with per-exam metadata (file name, event count, study ID, detected schema) and per-exam results after calculation.
- [ ] ✅ Recursion-to-iteration refactor is complete (`96ce63b`).
- [ ] Full test coverage for multi-exam paths (unit + smoke).

## Decision Log

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Exams are split by **study-level identifier**, not by file boundary in tabular input | A single export can contain multiple studies; splitting by study ID is the user-friendly default. File boundary splitting is the fallback for RDSR batches. |
| D2 | Settings are **global by default** with per-exam override for patient/table offsets and event-processing conventions | Most users run the same phantom across exams. The phantom model and mesh are always shared (same topology, same vertex count and ordering). Per-exam offsets are first-class because patient positioning routinely differs between procedures. Per-exam event-processing conventions are needed when exams come from different manufacturers with different coordinate conventions. |
| D3 | Output is a list of `ExamResult` wrapped in a `MultiExamResult` | Keeps existing `PySkinDoseOutput` API intact. `MultiExamResult` adds aggregate stats and per-exam metadata. |
| D4 | GUI shows exams as a **collapsible accordion** with per-exam result cards | Avoids overwhelming the user; each exam's dose map can be inspected independently. |
| D5 | Recursion-to-iteration refactor is a **separate prerequisite task** | It is independently useful (fixes RecursionError on long single-exam procedures) and blocks multi-exam for >1000 total events. |

## Architecture

### Data model

```
MultiExamResult
├── exams: list[ExamResult]
│   ├── exam_id: str              # study_uid, accession, or file name
│   ├── source_file: str          # original file path
│   ├── event_count: int
│   ├── patient_offset: list[float]  # per-exam offset used (d_lon, d_ver, d_lat)
│   ├── settings_snapshot: dict   # effective settings used (PyskindoseSettings.model_dump())
│   ├── output: PySkinDoseOutput  # per-exam result (includes per-exam dose_map)
│   └── warnings: list[str]
├── aggregate_dose_map: np.ndarray  # element-wise sum of per-exam dose maps (same mesh)
├── aggregate_psd: float            # max over aggregate_dose_map (peak skin dose across all exams)
├── total_events: int
└── warnings: list[str]
```

**Why element-wise summation is valid:** all exams use the same phantom model, so `dose_map[i]` refers to the same anatomical skin vertex in every exam regardless of world-space repositioning. Summing them gives the cumulative dose received by each skin location across the full procedure series.

`ExamResult` is a wrapper around `PySkinDoseOutput` that carries per-exam metadata. It lives in `format_export_data.py` alongside `MultiExamResult`.

### Layer changes

#### 1. Input adapters

**`normalized.py`** (and other adapters): Replace the multi-study error with a split.

```python
# Before (line 209-215):
if unique_ids > 1:
    raise ValueError("...multiple procedures...")

# After:
if unique_ids > 1:
    # Group by the first detected study-identifier column
    group_col = detected_col
    groups = data_df.groupby(group_col, sort=False)
    # Return a list of InputAdapterResult, one per group
    return [InputAdapterResult(data=group_df, ...) for _, group_df in groups]
```

The adapter's `adapt()` function returns either a single `InputAdapterResult` (one procedure) or a `list[InputAdapterResult]` (multiple procedures).

**`registry.py`**: `read_and_normalize_input()` returns `InputAdapterResult | list[InputAdapterResult]`.

**`main.py`**: `analyze_input_file()` and `main()` detect multi-result and dispatch to `analyze_multiple_exams()`.

**`--input-schema` choices**: The CLI `--input-schema` argument should list all five supported schemas: `"normalized"`, `"generic_rdsr_like"`, `"radimetrics"`, `"dosetrack"`, `"auto"`.

#### 2. Calculation (`analyze_data.py`, `calculate_dose/`)

**`analyze_data.py`**: Detect multi-exam input. For each exam DataFrame, call `calculate_dose()` independently. After all exams complete, sum per-exam dose maps element-wise to produce `aggregate_dose_map`.

**Phantom sharing and per-exam repositioning:** The patient phantom (model, topology, vertex ordering) must be instantiated exactly once and shared across all exams to minimize memory usage. However, `position_patient_phantom_on_table()` uses incremental `translate()` calls that mutate `patient.r` in place. To support per-exam offsets without instantiating multiple meshes, we must add a `reset_to_origin()` method to the `Phantom` class that restores `r` to its pre-positioning state (requires storing `r_origin` at construction). `table` and `pad` phantoms are also reused and reset.

**`calculate_dose/calculate_dose.py`**: Needs one change: `patient` is currently created inside `calculate_dose()` and returned. For the orchestrator to control per-exam offsets and collect per-exam `patient` references (needed to extract the dose map), patient creation must be lifted out or `calculate_dose()` must accept per-exam offset parameters directly.

**`calculate_dose/calculate_irradiation_event_result.py`**: ✅ Recursion → iteration refactor complete (shipped `96ce63b`).

**Plotting**: Each exam produces its own geometry plot and dose map plot as normal. No changes to plotting behavior — the user gets one plot per exam, which is the intended output.

#### 3. Output (`format_export_data.py`)

Add `ExamResult` and `MultiExamResult`:

```python
@dataclass
class ExamResult:
    exam_id: str
    source_file: str
    event_count: int
    patient_offset: list[float]      # [d_lon, d_ver, d_lat] used for this exam
    settings_snapshot: dict          # PyskindoseSettings.model_dump()
    output: PySkinDoseOutput
    warnings: list[str]

@dataclass
class MultiExamResult:
    exams: list[ExamResult]
    aggregate_dose_map: np.ndarray  # element-wise sum of per-exam dose maps
    aggregate_psd: float            # max over aggregate_dose_map
    total_events: int
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "exams": [
                {
                    "exam_id": e.exam_id,
                    "source_file": e.source_file,
                    "event_count": e.event_count,
                    "patient_offset": e.patient_offset,
                    "settings_snapshot": e.settings_snapshot,
                    "warnings": e.warnings,
                    "output": e.output.to_dict(),
                }
                for e in self.exams
            ],
            "aggregate_dose_map": self.aggregate_dose_map.tolist(),
            "aggregate_psd": self.aggregate_psd,
            "total_events": self.total_events,
            "warnings": self.warnings,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
```

`format_analysis_result_for_export()` is bypassed in the multi-exam path. The orchestrator calls `calculate_dose()` directly for each exam and wraps the result in `ExamResult`, then assembles `MultiExamResult`.

### Memory Management

By reusing a single `Phantom` instance across exams, we avoid the memory overhead of duplicating the 3D mesh.
- **Data:** `aggregate_dose_map` and per-exam dose maps are just lightweight 1D scalar arrays.
- **GUI:** While the Python backend memory footprint is minimal, Plotly figures are highly memory-intensive in the browser. If we render a separate 3D Plotly figure for each exam in the GUI, it could crash the browser. A soft limit should be imposed (e.g., warn or block if > 10 exams are uploaded) to prevent browser-side memory issues.

#### 4. CLI (`main.py`)

```bash
# Single file (existing)
python -m mypyskindose --file-path exam1.dcm

# Multiple files (glob or explicit)
python -m mypyskindose --file-path exam1.dcm exam2.dcm exam3.dcm
python -m mypyskindose --file-path "exams/*.dcm"
python -m mypyskindose --file-path batch.csv   # auto-split by study_id

# Output format: JSON dict with "exams" key
```

`argparse` change: `--file-path` accepts `nargs="+"` (one or more paths). If a single path is given, behavior is unchanged. If multiple paths are given, each is loaded and processed as a separate exam. Glob patterns (e.g. `"exams/*.dcm"`) are expanded via `pathlib.Path.glob()` if the path does not resolve to an existing file.

**`main()` function signature**: Add an optional `file_paths: list[str] | None = None` parameter. When `file_paths` is provided, `main()` processes all files as separate exams. The existing `file_path: str | None` parameter is kept for backward compatibility; if both are provided, `file_paths` takes precedence.

**`--output-format` interaction**: In multi-exam mode, `"html"` output should be blocked with a clear error message. An HTML file containing N dose maps would be prohibitively large. `"dict"` and `"json"` are the supported formats for multi-exam output.

#### 5. GUI (`gui/`)

**Upload tab changes:**

- Add the Quasar `multiple` prop to the `ui.upload` element.
- **Temp File Lifecycle:** Modify `_register_temp_upload` and `_uploaded_temp_files` in `app.py` to allow multiple concurrent temporary files (stop deleting the previous file upon new upload). Add a "Clear All" mechanism to handle cleanup when the user resets the session.
- On multi-file upload, each file is processed as a separate exam.
- Show a **loaded exams list** after upload:
  - Each row: file name, schema, event count, study ID (if detected), status (OK/error).
  - Clicking a row highlights that exam's data in the event table preview.
  - Per-exam warning badges (e.g. "2 events snapped to nearest HVL grid").

**Calculate tab changes:**

- "Calculate" button processes all loaded exams.
- Results shown as per-exam cards:
  - Exam name / file, PSD, air kerma, event count.
  - Per-exam dose map figure (Plotly).
  - Aggregate PSD banner at top (max across exams).
- If a single exam is loaded, the UI is identical to current behavior (no visual change).

**Settings tab changes:**

- Global settings panel (existing).
- *(Phase 2)* Optional per-exam override section:
  - *Note: Building dynamic, per-exam settings panels in NiceGUI will add significant complexity. Phase 1 will use global settings for all exams in the GUI (though the Python core API will support per-exam overrides immediately).*
  - Patient offset overrides per exam.
  - Table offset overrides per exam.
  - Event-processing convention overrides per exam.
  - "Apply global" button copies global settings to all exams.

### Prerequisite: Recursion → Iteration ✅ Complete

**Full plan:** [recursion-to-iteration.md](recursion-to-iteration.md)

Shipped in commit `96ce63b` (`fix(calc): replace per-event recursion with iterative event loop`). `calculate_irradiation_event_result()` now uses a `for` loop; the ~1000-frame recursion limit no longer applies.

## Implementation Order

1. ✅ **Recursion → iteration refactor** — complete (`96ce63b`).
2. **`ExamResult` and `MultiExamResult` dataclasses** — in `format_export_data.py`; include `patient_offset` on `ExamResult` and `aggregate_dose_map` on `MultiExamResult`.
3. **Input adapter multi-study split** — `normalized.py` adapter returns list when >1 study ID detected.
4. **`analyze_multiple_exams()` orchestrator** — in `analyze_data.py` / `main.py`; per-exam phantom repositioning using `reset_to_origin()` to share the single `Phantom` instance; per-exam patient offsets passed to `position_patient_phantom_on_table()`; aggregate dose map computed as element-wise sum of per-exam dose maps after all exams complete; error handling (partial failure returns partial results with per-exam warnings).
5. **CLI multi-file support** — `--file-path nargs="+"`, glob expansion, `--output-format` blocking for `"html"`, `--input-schema` choices updated.
6. **GUI multi-exam upload** — multiple files, per-exam list, per-exam results; aggregate dose map plot (using global settings).
7. **GUI Phase 2 & Per-exam overrides** — UI panels for per-exam patient/table offsets, and per-exam event-processing convention overrides (manufacturer coordinate differences).
8. **Tests** — unit, integration, GUI smoke.

## Testing

### Unit tests

- `test_normalized_multi_study_split()` — adapter splits on `study_id` column.
- `test_normalized_single_study_returns_single()` — single study ID → single result (no regression).
- `test_exam_result_serialization()` — `ExamResult` fields round-trip correctly.
- `test_multi_exam_result_serialization()` — `to_dict()` and `to_json()` round-trip.
- `test_analyze_multiple_exams()` — orchestrator processes list of DataFrames, returns `MultiExamResult` with correct per-exam dose maps and aggregate.
- `test_aggregate_dose_map_is_sum_of_per_exam_maps()` — `aggregate_dose_map` equals element-wise sum of `ExamResult.output.dose_map` for all exams.
- `test_per_exam_offsets_are_independent()` — two exams with different `patient_offset` values each use the correct offset; neither affects the other's phantom positioning.
- `test_recursion_iteration_equivalence()` — iterative output identical to reference for 500 events.
- `test_recursion_iteration_no_crash_1100_events()` — iterative version handles >1000 events.

### Integration tests

- Load two example RDSR files, verify two per-exam PSDs and a cumulative dose map in output.
- Load two exams with different `patient_offset` values; verify aggregate dose map equals sum of per-exam maps and that per-exam dose maps differ from each other.
- Load a synthetic multi-study CSV, verify per-exam grouping.
- Load multi-exam input where one exam fails, verify partial results with warnings.

### GUI smoke tests

- Upload two files, verify both appear in exam list.
- Click Calculate, verify per-exam result cards.
- Verify aggregate PSD shown.

## Open Questions

- **Q1:** Should multi-exam output include a **cumulative** dose map (summed across exams) or only per-exam maps? → **Decision:** both. Per-exam dose maps are included in each `ExamResult.output`. The `MultiExamResult.aggregate_dose_map` is the element-wise sum across all exams — the total dose received by each skin vertex across the full procedure series. `aggregate_psd` is the peak of that cumulative map.

- **Q2:** Should the CLI support a `--aggregate` flag for a single "worst-case" PSD? → **Recommendation:** yes, `aggregate_psd` is always in the output dict. A CLI flag to print only the aggregate to stdout is convenient.

- **Q3:** For tabular multi-study splitting, what is the **default study-identifier column** if none is detected? → **Recommendation:** check for `studyinstanceuid`, `study_id`, `accession_number`, `patient_id` in that order (matching the lowercase set already in `normalized.py:100`). `studyinstanceuid` (DICOM 0020,000D) is the most canonical identifier. If none present, keep the current error behavior (cannot determine study boundaries).

- **Q4:** Should per-exam settings overrides be in the first implementation or Phase 2? → **Decision:** per-exam patient/table offsets are Phase 1 (first-class requirement — patients are routinely repositioned between procedures). Per-exam event-processing convention overrides (manufacturer coordinate differences) are Phase 2.

- **Q5:** How should the progress bar behave across multiple exams? → **Options:** (a) One shared bar (0–total_events across all exams), (b) Per-exam bars (reset for each exam), (c) One bar with sub-labels showing exam name. → **Recommendation:** (a) One shared bar for simplicity; the user sees continuous progress. Per-exam bars (b) are better if exams are very disparate in size (e.g. 10 events vs 5000 events).

- **Q6:** What should happen when an exam fails during multi-exam processing? → **Options:** (a) Return partial `MultiExamResult` with succeeded exams and the failed exam in `warnings`, (b) Raise immediately on first failure, (c) Skip failed exams silently. → **Recommendation:** (a) Return partial results with per-exam warnings. This is the most user-friendly: the user gets what succeeded and knows what failed.

- **Q7:** Should `"html"` output be blocked in multi-exam mode, or produce an HTML file with all dose maps? → **Recommendation:** Block `"html"` with a clear error message. An HTML file with N dose maps would be prohibitively large. If requested later, a separate `"html_batch"` mode could generate multiple HTML files (one per exam).

- **Q8:** How should `main()` accept multiple files — via `file_paths` list parameter, or only through CLI and `analyze_input_file()`? → **Recommendation:** Add `file_paths: list[str] | None = None` to `main()` for API consistency. Keep `file_path` for backward compatibility.
