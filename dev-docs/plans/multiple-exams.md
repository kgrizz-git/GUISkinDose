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
- [ ] Each exam gets its own dose map and `PySkinDoseOutput`; phantom (patient/table/pad) is shared across exams.
- [ ] Output contains per-exam PSDs plus an optional aggregate (max PSD across exams).
- [ ] GUI shows a list of loaded exams with per-exam metadata (file name, event count, study ID, detected schema) and per-exam results after calculation.
- [ ] Recursion-to-iteration refactor is complete (prerequisite: >1000 events across multiple exams).
- [ ] Full test coverage for multi-exam paths (unit + smoke).

## Decision Log

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Exams are split by **study-level identifier**, not by file boundary in tabular input | A single export can contain multiple studies; splitting by study ID is the user-friendly default. File boundary splitting is the fallback for RDSR batches. |
| D2 | Settings are **global by default** with per-exam override for patient/table offsets and event-processing conventions | Most users run the same phantom across exams. The phantom model and mesh are always shared. Per-exam overrides are needed when patient positioning changes between procedures (different offsets) or when exams come from different manufacturers whose coordinate conventions differ (e.g. different gantry angle sign conventions). |
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
│   ├── settings_snapshot: dict   # effective settings used (PyskindoseSettings.model_dump())
│   ├── output: PySkinDoseOutput  # per-exam result
│   └── warnings: list[str]
├── aggregate_psd: float          # max PSD across exams
├── total_events: int
└── warnings: list[str]
```

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

**`analyze_data.py`**: Detect multi-exam input. For each exam DataFrame, call `calculate_dose()` independently. Phantom (patient, table, pad) is created once and shared across all exams.

**`calculate_dose/calculate_dose.py`**: Needs one change: `patient` is currently created inside `calculate_dose()` and returned. For phantom sharing across exams, patient creation must be lifted out — either by extracting it to the orchestrator or by accepting an optional pre-built patient. `table` and `pad` are already created in `analyze_data()` and passed in, so the same pattern should apply to `patient`.

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
    settings_snapshot: dict  # PyskindoseSettings.model_dump()
    output: PySkinDoseOutput
    warnings: list[str]

@dataclass
class MultiExamResult:
    exams: list[ExamResult]
    aggregate_psd: float          # max PSD across exams
    total_events: int
    warnings: list[str]

    def to_dict(self) -> dict:
        return {
            "exams": [
                {
                    "exam_id": e.exam_id,
                    "source_file": e.source_file,
                    "event_count": e.event_count,
                    "settings_snapshot": e.settings_snapshot,
                    "warnings": e.warnings,
                    "output": e.output.to_dict(),
                }
                for e in self.exams
            ],
            "aggregate_psd": self.aggregate_psd,
            "total_events": self.total_events,
            "warnings": self.warnings,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
```

`format_analysis_result_for_export()` is bypassed in the multi-exam path. The orchestrator calls `calculate_dose()` directly for each exam and wraps the result in `ExamResult`, then assembles `MultiExamResult`.

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

- File uploader already accepts multiple files (Quasar `multiple` prop is not set; add it).
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
- Optional per-exam override section:
  - Patient offset overrides per exam.
  - Table offset overrides per exam.
  - Event-processing convention overrides per exam (e.g. coordinate sign conventions for different manufacturers).
  - "Apply global" button copies global settings to all exams.

### Prerequisite: Recursion → Iteration ✅ Complete

**Full plan:** [recursion-to-iteration.md](recursion-to-iteration.md)

Shipped in commit `96ce63b` (`fix(calc): replace per-event recursion with iterative event loop`). `calculate_irradiation_event_result()` now uses a `for` loop; the ~1000-frame recursion limit no longer applies.

## Implementation Order

1. ✅ **Recursion → iteration refactor** — complete (`96ce63b`).
2. **`ExamResult` and `MultiExamResult` dataclasses** — in `format_export_data.py`.
3. **Input adapter multi-study split** — `normalized.py` adapter returns list when >1 study ID detected.
4. **`analyze_multiple_exams()` orchestrator** — in `analyze_data.py` / `main.py`; shared phantom; skipped plotting; error handling (partial failure returns partial results with per-exam warnings).
5. **CLI multi-file support** — `--file-path nargs="+"`, glob expansion, `--output-format` blocking for `"html"`, `--input-schema` choices updated.
6. **GUI multi-exam upload** — multiple files, per-exam list, per-exam results.
7. **Per-exam settings overrides** (optional, lower priority).
8. **Tests** — unit, integration, GUI smoke.

## Testing

### Unit tests

- `test_normalized_multi_study_split()` — adapter splits on `study_id` column.
- `test_normalized_single_study_returns_single()` — single study ID → single result (no regression).
- `test_exam_result_serialization()` — `ExamResult` fields round-trip correctly.
- `test_multi_exam_result_serialization()` — `to_dict()` and `to_json()` round-trip.
- `test_analyze_multiple_exams()` — orchestrator processes list of DataFrames, returns `MultiExamResult`.
- `test_recursion_iteration_equivalence()` — recursive vs iterative output identical for 500 events.
- `test_recursion_iteration_no_crash_1100_events()` — iterative version handles >1000 events.

### Integration tests

- Load two example RDSR files, verify two PSDs in output.
- Load a synthetic multi-study CSV, verify per-exam grouping.
- Load multi-exam input where one exam fails, verify partial results with warnings.

### GUI smoke tests

- Upload two files, verify both appear in exam list.
- Click Calculate, verify per-exam result cards.
- Verify aggregate PSD shown.

## Open Questions

- **Q1:** Should multi-exam output include a **cumulative** dose map (summed across exams) or only per-exam maps? → **Recommendation:** per-exam only. Cumulative is clinically questionable (different time points, different phantom positions). Can be added later if requested.

- **Q2:** Should the CLI support a `--aggregate` flag for a single "worst-case" PSD? → **Recommendation:** yes, `aggregate_psd` is always in the output dict. A CLI flag to print only the aggregate to stdout is convenient.

- **Q3:** For tabular multi-study splitting, what is the **default study-identifier column** if none is detected? → **Recommendation:** check for `studyinstanceuid`, `study_id`, `accession_number`, `patient_id` in that order (matching the lowercase set already in `normalized.py:100`). `studyinstanceuid` (DICOM 0020,000D) is the most canonical identifier. If none present, keep the current error behavior (cannot determine study boundaries).

- **Q4:** Should per-exam settings overrides be in the first implementation or Phase 2? → **Recommendation:** Phase 2. First version uses global settings for all exams.

- **Q5:** How should the progress bar behave across multiple exams? → **Options:** (a) One shared bar (0–total_events across all exams), (b) Per-exam bars (reset for each exam), (c) One bar with sub-labels showing exam name. → **Recommendation:** (a) One shared bar for simplicity; the user sees continuous progress. Per-exam bars (b) are better if exams are very disparate in size (e.g. 10 events vs 5000 events).

- **Q6:** What should happen when an exam fails during multi-exam processing? → **Options:** (a) Return partial `MultiExamResult` with succeeded exams and the failed exam in `warnings`, (b) Raise immediately on first failure, (c) Skip failed exams silently. → **Recommendation:** (a) Return partial results with per-exam warnings. This is the most user-friendly: the user gets what succeeded and knows what failed.

- **Q7:** Should `"html"` output be blocked in multi-exam mode, or produce an HTML file with all dose maps? → **Recommendation:** Block `"html"` with a clear error message. An HTML file with N dose maps would be prohibitively large. If requested later, a separate `"html_batch"` mode could generate multiple HTML files (one per exam).

- **Q8:** How should `main()` accept multiple files — via `file_paths` list parameter, or only through CLI and `analyze_input_file()`? → **Recommendation:** Add `file_paths: list[str] | None = None` to `main()` for API consistency. Keep `file_path` for backward compatibility.
