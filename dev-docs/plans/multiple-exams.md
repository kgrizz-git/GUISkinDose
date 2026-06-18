# Multiple Exams Plan

## Objective

Allow MyPySkinDose to process multiple exams (studies/procedures) in a single run across four input scenarios:

1. **Multiple RDSR files** — a batch of `.dcm` files, each a separate exam.
2. **Multiple tabular files** — a batch of `.csv`/`.tsv`/`.xlsx` files, each a separate exam.
3. **Mixed formats** — any combination in a single run (e.g. one DICOM + one CSV + one XLSX); each file routed by extension and merged into one `MultiExamResult`.
4. **Single tabular file, multiple studies** — one file whose rows span several studies, split automatically on a study-identifier column (`studyinstanceuid`, `study_id`, `accession_number`, `patient_id`, or `study_uid` in that priority order).

Each exam gets its own dose map and PSD. A per-exam patient offset is supported. All other settings are global by default.

---

## Status at a Glance

| Area | Status |
|------|--------|
| Python core — data model, orchestrator, partial-failure handling | ✅ Complete |
| Input adapter multi-study split | ✅ Complete |
| CLI multi-file / mixed-format support, `--aggregate` flag | ✅ Complete |
| Recursion → iteration refactor | ✅ Complete (`96ce63b`) |
| Unit tests | ✅ Complete (18 tests) |
| GUI Phase 1 — single-file upload, auto-split, exam list, results accordion | 🔧 Bugs fixed; needs smoke test |
| GUI Phase 2.1 — multi-file/mixed-format upload accumulation, per-exam list with remove | ✅ Complete; needs smoke test |
| GUI Phase 2.2–2.4 — per-exam transform / offset / convention overrides | ⬜ Not started |

---

## Key Decisions

| # | Decision |
|---|----------|
| D1 | Tabular multi-exam split is by **study-level identifier column** (not file boundary). File boundary is used for RDSR batches. |
| D2 | Settings are **global** with per-exam `patient_offset` override (Phase 1). Per-exam coordinate/convention overrides are Phase 2. |
| D3 | Output: list of `ExamResult` wrapped in `MultiExamResult`. Keeps `PySkinDoseOutput` API intact; adds aggregate stats. |
| D4 | GUI results: **collapsible accordion** with per-exam cards. Avoids information overload; each exam's dose map inspectable independently. |
| D5 | Recursion → iteration refactor is a **separate prerequisite**. Independently fixes RecursionError on long single-exam procedures; blocks multi-exam beyond ~1000 total events. |
| D6 | **Fresh `Phantom` per exam** (not shared with reset). `position_patient_phantom_on_table()` applies incremental translates; sharing would require storing and restoring origin. Fresh instances guarantee identical topology (same mesh file → same vertex ordering → element-wise sum is valid). |
| D7 | **GUI Phase 1 is one-file-at-a-time**. Simplest correct design; multi-study via a single CSV works. Multi-file accumulation needs temp-file lifecycle redesign and upload widget changes — that is Phase 2. |

---

## Data Model

```
MultiExamResult
├── exams: list[ExamResult]
│   ├── exam_id: str               # study_uid, accession, or filename
│   ├── source_file: str
│   ├── event_count: int
│   ├── patient_offset: list[float]  # [d_lon, d_ver, d_lat] used for this exam
│   ├── settings_snapshot: dict
│   ├── output: PySkinDoseOutput   # per-exam dose map, PSD, corrections, patient
│   └── warnings: list[str]
├── aggregate_dose_map: np.ndarray  # element-wise sum across exams (same phantom topology)
├── aggregate_psd: float            # max(aggregate_dose_map)
├── total_events: int
└── warnings: list[str]
```

Element-wise summation is valid because all exams use fresh `Phantom` instances built from the same STL/model file — `dose_map[i]` always refers to the same anatomical skin vertex regardless of world-space positioning.

---

## To-Do Checklist

### Core & CLI

- [x] `ExamResult` and `MultiExamResult` dataclasses with `to_dict()` / `to_json()` — `format_export_data.py`
- [x] Input adapter multi-study split — `normalized.py` returns `list[InputAdapterResult]` when >1 study ID
- [x] `registry.py` propagates list return transparently
- [x] `analyze_multiple_exams(exams, settings, per_exam_offsets)` — fresh phantoms, aggregate map, partial-failure handling — `analyze_data.py`
- [x] `analyze_multiple_input_files(file_paths, settings)` — mixed-format routing, merges all exams — `main.py`
- [x] `analyze_input_file()` dispatches to `analyze_multiple_exams()` on list result
- [x] CLI `--file-path nargs="+"` accepts any number of files in any format mix
- [x] CLI `--aggregate` flag prints only `aggregate_psd` to stdout
- [x] `html` output format silently forced to `dict` in multi-exam mode (logged warning)
- [x] Recursion → iteration refactor — `calculate_irradiation_event_result.py` (`96ce63b`)

### GUI Phase 1 — Single-file upload, auto-split

- [x] `AppState` fields: `is_multi_exam`, `loaded_exams`, `multi_exam_result`
- [x] `load_tabular()` detects multi-study split, builds concatenated event table, sets `is_multi_exam` — `helpers.py` *(Bug 1 fixed: df overwrite removed; coordinate transforms scoped to single-exam path)*
- [x] `run_calculation()` dispatches to `analyze_multiple_exams()` when `is_multi_exam` — `helpers.py`
- [x] Upload tab: "Loaded Exams" summary table (study ID, event count, status) when `is_multi_exam`
- [x] Results tab: per-exam accordion with PSD (`.PSD`), Air Kerma (`.AirKerma`), event count *(Bug 3 fixed: was calling `.get()` on `PySkinDoseOutput`)*
- [x] Per-exam "Show Dose Map" dialog serializes `PySkinDoseOutput.to_dict()` before rendering *(Bug 3 fixed)*
- [ ] End-to-end smoke test: upload multi-study CSV → exam list populated → calculate → accordion renders → aggregate map renders

> **Phase 1 limitation (by design, D7):** a second upload replaces the first. Users with multiple separate files should merge them into a single CSV/XLSX with a study-ID column, or use the CLI.

---

## Phase 2: Multi-File Upload Accumulation & Per-Exam Overrides

Phase 2 brings the GUI up to the same capability as the CLI (`--file-path` with multiple mixed-format files) and exposes per-exam overrides already supported in the Python core. **Phase 2.1 (multi-file accumulation) is complete**; Phase 2.2–2.4 (per-exam transform / offset / convention overrides) are not yet started.

> **Read this before implementing:** Phase 2.1 involves non-trivial coupling across `app.py`, `helpers.py`, and `state.py`. The sections below describe the exact fields and functions that must change, and the constraints to preserve.

---

### Phase 2.1 — Multi-file / mixed-format upload

**Goal:** the user can upload any number of files (DICOM, CSV, XLSX, or a mix) via the upload widget, accumulating them as separate exams, then click Calculate once to process all.

#### State changes required (`state.py`)

New fields to add to `AppState`:

```python
# Per-entry parallel to loaded_exams; each dict holds the per-exam
# parsed metadata (file_name, source_type, input_schema, sheet_name,
# provenance, import_warnings, swap_lat_lon, flip_ap1, flip_ap2).
loaded_exam_meta: list[dict] = field(default_factory=list)
```

Fields that change semantics (existing fields become "for the most recently added entry" rather than "for the one loaded file"):

- `state.file_path` — currently a single `Path | None`. In Phase 2 it becomes the path of the most-recently-added file (used by `_on_schema_change()` and `_on_sheet_change()` to re-parse). This meaning is retained; it should NOT be turned into a list (the per-exam paths live in `loaded_exam_meta`).
- `state.file_name` — currently displayed as "No file loaded" / filename. With accumulation, the top-bar label should show `"N files loaded"` when `len(loaded_exam_meta) > 1`.
- `state.rdsr_df` — currently the full event DataFrame for single-exam display. In multi-exam mode it is the concatenated DataFrame used for the event table preview only (this is already the Phase 1 behaviour). Keep this semantics.

Do **not** convert `state.is_multi_exam` semantics — it should remain `True` whenever `len(state.loaded_exams) > 1`.

#### Temp file lifecycle (`app.py` — `_register_temp_upload`, `_cleanup_temp_uploads`)

Current `_register_temp_upload()` (lines 71–79) pops-and-deletes all previous entries before appending. **Replace** with an accumulating version:

```python
def _register_temp_upload(path: Path) -> None:
    """Track a freshly written upload temp file (accumulating; do not delete others)."""
    _uploaded_temp_files.append(path)

def _remove_temp_upload(path: Path) -> None:
    """Delete one specific temp file and deregister it (called when user removes an exam)."""
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        dprint("GUI", f"Could not delete temp upload {path}: {exc}")
    try:
        _uploaded_temp_files.remove(path)
    except ValueError:
        pass
```

`_cleanup_temp_uploads()` (atexit) is already correct — it iterates and unlinks all registered paths.

Add a `_clear_all_temp_uploads()` called from the "Clear All" button:

```python
def _clear_all_temp_uploads() -> None:
    while _uploaded_temp_files:
        old = _uploaded_temp_files.pop()
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass
```

#### Upload handler (`app.py` — `handle_upload`, lines 240–321)

Current handler **replaces** state on every upload (resets `swap_lat_lon`, `flip_ap1`, `flip_ap2`, calls `reset_results()`). New behaviour: **appends** to the exam list.

Key changes:

1. **Do not reset transform flags on every upload.** Transform flags reset is now per-exam (stored in `loaded_exam_meta`), not global.
2. **Do not call `reset_results()` on upload** — results are already stale once any exam is added or removed; call it explicitly when the exam list changes.
3. **After successful parse**, call a new `_append_exam_to_state(tmp_path, suffix, ok_result)` helper instead of setting flat state fields directly. This helper:
   - Appends the `InputAdapterResult`(s) to `state.loaded_exams`.
   - Appends a matching metadata dict to `state.loaded_exam_meta`: `{"file_name": file_name, "file_path": tmp_path, "source_type": suffix, "schema": state.input_schema, "sheet": state.input_sheet_name, "provenance": result.provenance, "warnings": result.warnings, "swap_lat_lon": False, "flip_ap1": False, "flip_ap2": False}`.
   - Rebuilds `state.rdsr_df` as `pd.concat([e.normalized_data for e in state.loaded_exams], ignore_index=True)`.
   - Sets `state.is_multi_exam = len(state.loaded_exams) > 1`.
   - Sets `state.file_path = tmp_path` and `state.file_name` (single name or `"N files"` label).
   - Calls `_set_transform_defaults()` only for the newly-added entry.
4. **RDSR (DICOM) files** call `load_rdsr(tmp_path, state)` which sets `state.rdsr_df` and `state.loaded_exams` via the existing single-exam path. For Phase 2 accumulation, `load_rdsr` must be updated to **append** an `InputAdapterResult`-like object (with `.normalized_data`, `.provenance`, `.warnings`) to `state.loaded_exams` instead of replacing it. The simplest approach is to wrap the result of `rdsr_normalizer()` in a synthetic `InputAdapterResult` and append.

#### Upload widget (`app.py` — `_build_uploader`, lines 332–343)

Add `:multiple="true"` Quasar prop so users can select multiple files in one dialog. NiceGUI's `ui.upload` fires `on_upload` once per file, so the handler fires N times (one per file). **Those handlers run concurrently** (each awaits `run.io_bound` and yields the loop), so they must be **serialised** — otherwise the second file trips the busy-guard and is rejected with a "still uploading" notice. Implemented with a module-level `asyncio.Lock` (`_upload_lock`): `handle_upload` acquires it and delegates to `_do_upload`, so files queue and load one-by-one.

```python
_uploader["el"] = ui.upload(
    on_upload=handle_upload,
    label="DRAG AND DROP OR CLICK TO SELECT",
    max_file_size=MAX_UPLOAD_BYTES,
    multiple=True,        # ← add this
).props(
    'accept=".dcm,.csv,.tsv,.xlsx,.xlsm" flat bordered color=deep-purple auto-upload'
).classes("w-full bg-black/40 uploader-no-list")
```

#### Loaded exam list UI (`app.py` — upload tab, after the uploader card)

Replace the current single-file card (the `bind_visibility_from(state, "file_name", backward=bool)` row, lines 360–372) with a scrollable exam list. Each row:

- File name (truncated) + format badge (DICOM / CSV / XLSX)
- Schema name from `loaded_exam_meta[i]["provenance"].schema_name`
- Event count: `len(state.loaded_exams[i].normalized_data)`
- Study IDs: comma-joined `loaded_exam_meta[i]["provenance"].study_ids` if present
- Warning badge (orange ⚠) if `loaded_exam_meta[i]["warnings"]` is non-empty
- Remove (×) button: calls `_remove_exam(i)` which removes `loaded_exams[i]` and `loaded_exam_meta[i]`, calls `_remove_temp_upload(loaded_exam_meta[i]["file_path"])`, rebuilds `state.rdsr_df`, updates `state.is_multi_exam`, calls `reset_results()`, calls `_refresh_exams_table()`.

The existing `_refresh_exams_table()` function (already present) drives this; extend it for the new row structure.

#### Schema selector (`app.py` — `schema_select` / `_on_schema_change`, lines 461–500)

Currently re-parses `state.file_path` (the one loaded file). With accumulation, `_on_schema_change()` should:
- Apply to the **most recently added tabular exam** only (i.e. `state.loaded_exam_meta[-1]`), since schema is per-file.
- Update `loaded_exam_meta[-1]["schema"]` and re-call the appropriate loader.
- Rebuild `state.rdsr_df` from all exams.
- The schema selector label should change to `"Input schema (last added tabular file)"` to make this clear.

Alternatively, schema selection can be deferred entirely to be per-exam in the loaded exam list UI (Phase 2.2 scope) — the schema selector is then hidden when multiple files are loaded.

#### `clear_loaded_file()` → `clear_all_exams()` (`app.py`, lines 374–410)

Rename and update: call `_clear_all_temp_uploads()`, reset `state.loaded_exams = []`, `state.loaded_exam_meta = []`, and all the existing single-exam state fields. The "Reset upload" and "Clear All" buttons both call this.

#### `run_calculation()` (`helpers.py`, lines 204–273)

Already dispatches to `analyze_multiple_exams()` when `state.is_multi_exam`. No changes needed in the calculation path itself for Phase 2.1 — per-exam offsets (Phase 2.3) are the only addition.

#### Phase 2.1 checklist

- [x] Add `loaded_exam_meta: list[dict]` field to `AppState` (`state.py`)
- [x] Change `_register_temp_upload()` to accumulating; add `_remove_temp_upload()` and `_clear_all_temp_uploads()` (`app.py`)
- [x] Add `_remove_exam(i)` helper (`app.py`) — rebuilds concat preview, deletes the temp file only when no remaining exam shares its path (multi-study), updates top-bar labels. *(Append logic was inlined into the accumulating `load_rdsr()`/`load_tabular()` rather than a standalone `_append_exam_to_state()` helper — same effect.)*
- [x] Update `load_rdsr()` to wrap the result in a synthetic `InputAdapterResult` and append to `state.loaded_exams` (`helpers.py`)
- [x] Update `handle_upload()` to append (via the accumulating loaders) instead of replacing flat state; transform flags are no longer reset globally on upload (`app.py`)
- [x] Add `multiple=True` to `ui.upload` widget (`app.py`)
- [x] Replace single-file card with scrollable loaded exam list — per-exam card with #, format badge, file name, schema, study ID, event count, warning badge, and remove (×) button (`app.py`)
- [x] Update `_refresh_exams_table()` to build per-exam rows (now an imperative `ui.column` rebuild, not a `ui.table`) (`app.py`)
- [x] Update `_on_schema_change()` / `_on_sheet_change()` re-parse to replace in place — added `replace_existing` to `load_tabular()` + `_drop_exams_for_path()`, so re-parsing updates the entry instead of appending a duplicate (`app.py`, `helpers.py`)
- [x] Rename `clear_loaded_file()` to `clear_all_exams()`, wire "Clear All" button (`app.py`)
- [x] Update `ctx.file_label` and `ctx.events_label` to reflect N-file summary (`app.py`)
- [x] Update `state.file_name` display logic: show `"N files"` when multiple (`app.py`)
- [x] Guard `_set_transform_defaults()` to no-op in multi-exam mode (transforms reach only the concat preview, not per-exam data — deferred to Phase 2.2) (`app.py`)

---

### Phase 2.2 — Per-exam coordinate transform overrides

**Goal:** each exam in the loaded exam list has its own swap-lat-lon / flip-Ap1 / flip-Ap2 toggles, independent of other exams.

#### Current state

`state.swap_lat_lon`, `state.flip_ap1`, `state.flip_ap2` are global booleans. The toggle handlers in `app.py` (`_on_swap_toggle`, `_on_flip_ap1_toggle`, `_on_flip_ap2_toggle`) call `load_tabular()` to re-parse and then re-apply the global flags. This was scoped to single-exam in Phase 1 (Bug 1 fix); the global flags are already not applied to multi-exam concatenated data.

#### Required changes

1. **Store per-exam transforms in `loaded_exam_meta`** (already proposed in Phase 2.1): `{"swap_lat_lon": bool, "flip_ap1": bool, "flip_ap2": bool}`.
2. **Move the coordinate correction card** from the global upload section into each exam list row (inline or via an expandable section per row).
3. **Transforms are applied at load time** (not on Calculate): when a toggle changes for exam `i`, re-call `load_tabular(loaded_exam_meta[i]["file_path"], state_subset)` with the per-exam schema and sheet, apply the transforms to `loaded_exams[i].normalized_data`, then rebuild `state.rdsr_df` from all exams.
4. **`_set_transform_defaults()`** (already exists in `app.py`) should be called per-exam with the provenance of that specific exam, writing into `loaded_exam_meta[i]` rather than global state.
5. **Global coordinate correction card** (lines 542–620 in `app.py`) is hidden when `is_multi_exam` is True; per-exam toggles live in the exam list rows instead.

#### Phase 2.2 checklist

- [ ] Add `swap_lat_lon`, `flip_ap1`, `flip_ap2` fields to `loaded_exam_meta[i]` dict (part of Phase 2.1's `_append_exam_to_state`) (`app.py`)
- [ ] Add per-exam transform toggle UI to each exam list row (inline or expandable) (`app.py`)
- [ ] Write `_apply_exam_transforms(exam_index: int)` helper: re-applies transforms to `loaded_exams[i].normalized_data` from `loaded_exam_meta[i]` flags; rebuilds `state.rdsr_df` (`helpers.py`)
- [ ] Update `_set_transform_defaults()` to accept an `exam_index` and write to `loaded_exam_meta[i]` (`app.py`)
- [ ] Hide global coordinate correction card when `is_multi_exam` is True (`app.py`)
- [ ] Remove global `_on_swap_toggle`, `_on_flip_ap1_toggle`, `_on_flip_ap2_toggle` handlers (or scope them to single-exam only) (`app.py`)

---

### Phase 2.3 — Per-exam patient offset overrides

**Goal:** the user can set independent d_lon / d_ver / d_lat for each exam. The Python core already accepts `per_exam_offsets: list[list[float]]` in `analyze_multiple_exams()`.

#### Required changes

1. **New state field** in `AppState`:
   ```python
   per_exam_offsets: list[dict[str, float]] = field(default_factory=list)
   # e.g. [{"d_lon": 0.0, "d_ver": 0.0, "d_lat": 0.0}, ...]
   ```
   Default for each new exam: copy of the current global `{d_lon: state.d_lon, d_ver: state.d_ver, d_lat: state.d_lat}`.

2. **UI**: add a per-exam offset row to the exam list (d_lon, d_ver, d_lat `ui.number` spinboxes, range −50 to 50 cm). These bind to `state.per_exam_offsets[i]`. Include an "Apply global to all" button that copies `state.d_lon/d_ver/d_lat` into every entry.

3. **Wire into `run_calculation()`** (`helpers.py`, line 239): build `per_exam_offsets_list = [[m["d_lon"], m["d_ver"], m["d_lat"]] for m in state.per_exam_offsets]` and pass to `analyze_multiple_exams(exams=state.loaded_exams, settings=settings, per_exam_offsets=per_exam_offsets_list)`.

4. **`_append_exam_to_state()`** should append a default offset dict using the current global offset.

5. **`clear_all_exams()`** resets `state.per_exam_offsets = []`.

#### Phase 2.3 checklist

- [ ] Add `per_exam_offsets: list[dict[str, float]]` field to `AppState` (`state.py`)
- [ ] Populate default entry (from global offset) in `_append_exam_to_state()` (`app.py`)
- [ ] Add per-exam d_lon / d_ver / d_lat spinboxes to each exam list row (`app.py`)
- [ ] Add "Apply global offset to all" button (`app.py`)
- [ ] Reset `state.per_exam_offsets` in `clear_all_exams()` (`app.py`)
- [ ] Remove entry in `_remove_exam(i)` alongside `loaded_exams[i]` and `loaded_exam_meta[i]` (`app.py`)
- [ ] Wire `per_exam_offsets` into `run_calculation()` → `analyze_multiple_exams()` (`helpers.py`)

---

### Phase 2.4 — Per-exam event-processing convention overrides *(low priority)*

- [ ] Deferred — no concrete use case beyond Phase 2.2's coordinate transform toggles. Revisit if a vendor's RDSR uses a different rotation-direction convention than the global setting.

---

## Open Questions

- **Q5 — Progress bar across exams:** GUI Phase 1 uses one tqdm-patched bar across all total events. Per-exam progress segmentation is Phase 2.
- **Q8 — `main()` multi-file API:** `analyze_multiple_input_files(file_paths, settings)` is the programmatic entry point. `main(file_path, settings)` is unchanged for backward compatibility. Adding `file_paths` to `main()` is not planned unless there is a concrete use case.

---

## Testing

### ✅ Existing (`test_multi_exam.py`)

- [x] `TestExamResultSerialization` — `ExamResult` field round-trip
- [x] `TestMultiExamResultSerialization` — `to_dict()`, `to_json()`, aggregate PSD, element-wise sum
- [x] `TestMultiStudySplitViaRegistry` — single-study no-regression; multi-study split; group sizes; provenance; `__study_id__` stripped
- [x] `TestAnalyzeMultipleExams` — `MultiExamResult` shape; aggregate map equals sum; PSD; per-exam offsets independent; source file preserved; partial failure; dict/JSON round-trip

### Needed

- [ ] Verify or add: iterative output identical to reference for 500 events
- [ ] Verify or add: iterative version handles >1000 events without `RecursionError`

- [ ] Integration test: two example RDSR files via `analyze_multiple_input_files()` → correct `MultiExamResult`
- [ ] Integration test: mixed-format run (1 DICOM + 1 CSV) via `analyze_multiple_input_files()`
- [ ] Integration test: multi-study tabular CSV end-to-end through `analyze_input_file()`
- [ ] GUI smoke test: multi-study CSV upload → exam list → calculate → accordion + aggregate map render

---

## CLI Reference

```bash
# Single file (unchanged behaviour)
python -m mypyskindose --file-path exam1.dcm

# Multiple files, same format
python -m mypyskindose --file-path exam1.dcm exam2.dcm exam3.dcm

# Mixed formats in one run
python -m mypyskindose --file-path patient1.dcm patient2.csv patient3.xlsx

# Single tabular file — auto-split by study_id column
python -m mypyskindose --file-path batch.csv

# Print only aggregate PSD
python -m mypyskindose --file-path batch.csv --aggregate
```

> **Shell glob note:** unquoted globs (e.g. `--file-path exams/*.dcm`) are expanded by the shell and work. Quoted globs are passed as a literal string and will fail — no internal glob expansion beyond a simple existence check fallback.
