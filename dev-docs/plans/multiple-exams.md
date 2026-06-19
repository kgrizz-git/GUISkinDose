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
| GUI Phase 2.2 — per-exam coordinate transform overrides | ✅ Complete; needs smoke test |
| GUI Phase 2.3 — per-exam patient-offset overrides | ✅ Complete; needs smoke test |
| GUI Phase 2.5 — manual per-exam table-origin override | ✅ Complete; needs smoke test |
| GUI Phase 2.4 — per-exam convention overrides | ⬜ Deferred (no concrete use case) |

---

## Key Decisions

| # | Decision |
|---|----------|
| D1 | Tabular multi-exam split is by **study-level identifier column** (not file boundary). File boundary is used for RDSR batches. |
| D2 | Settings are **global** with per-exam **patient offset** override (Phase 1 core; GUI in Phase 2.3). Per-exam coordinate/convention overrides are Phase 2. **Table-origin offset** is a separate quantity (handled per-file at normalization, see [Offset Terminology](#offset-terminology-disambiguation)); a manual override is Phase 2.5. |
| D3 | Output: list of `ExamResult` wrapped in `MultiExamResult`. Keeps `PySkinDoseOutput` API intact; adds aggregate stats. |
| D4 | GUI results: **collapsible accordion** with per-exam cards. Avoids information overload; each exam's dose map inspectable independently. |
| D5 | Recursion → iteration refactor is a **separate prerequisite**. Independently fixes RecursionError on long single-exam procedures; blocks multi-exam beyond ~1000 total events. |
| D6 | **Fresh `Phantom` per exam** (not shared with reset). `position_patient_phantom_on_table()` applies incremental translates; sharing would require storing and restoring origin. Fresh instances guarantee identical topology (same mesh file → same vertex ordering → element-wise sum is valid). |
| D7 | **GUI Phase 1 is one-file-at-a-time**. Simplest correct design; multi-study via a single CSV works. Multi-file accumulation needs temp-file lifecycle redesign and upload widget changes — that is Phase 2. |

---

## Offset Terminology (disambiguation)

"Offset" is overloaded in this codebase. There are **two distinct quantities**, applied at **different pipeline stages**, and the Phase 2 work touches only one of them. Keep them separate when reading or extending the phases below.

| | **Table-origin offset** (`trans_offset` + `trans_dir`) | **Patient offset** (`d_lon`, `d_ver`, `d_lat`) |
|---|---|---|
| **What it is** | Vendor/system convention for where the table coordinate origin sits and which direction each axis runs. A property of the **scanner manufacturer/model**. | A user-chosen shift of the **patient on the table** (e.g. patient lay 5 cm cranial of isocenter). |
| **Where applied** | At **normalization** time — [`rdsr_normalizer.py`](../../src/mypyskindose/rdsr_normalizer.py) builds `Tx/Ty/Tz` from `norm.trans_offset` + `norm.trans_dir`. | At **dose-calc** time — `geom_calc.py` `patient.translate(dr=patient_offset)`. |
| **Source** | `settings.normalization_settings`, **matched per file** from the DICOM manufacturer/model. | `settings.phantom.patient_offset`, set by the user. |
| **Per-exam already?** | **Yes, by construction** — each file is normalized separately before reaching `analyze_multiple_exams()`, which consumes already-normalized `Tx/Ty/Tz`. A mixed-manufacturer batch already gets each vendor's convention correctly. | **Core-ready**: `analyze_multiple_exams(per_exam_offsets=...)` deep-copies settings per exam. GUI wiring is Phase 2.3. |
| **Phase** | Automatic; not a Phase 2.x item. Residual fixups for tabular exports that lack convention metadata are the swap/flip toggles → **Phase 2.2**. **Manual numeric override → new Phase 2.5.** | **Phase 2.3.** |

> **Key point:** different manufacturers' table/origin conventions are handled *automatically* by per-file normalization — you do **not** need a per-exam UI for the common case. Phase 2.5 adds a **manual** numeric override for the edge case where the scanner is misdetected (or a tabular export carries no usable convention), which today has no lever beyond the swap/flip toggles.

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

Phase 2 brings the GUI up to the same capability as the CLI (`--file-path` with multiple mixed-format files) and exposes per-exam overrides already supported in the Python core. **Phase 2.1 (multi-file accumulation), 2.2 (per-exam coordinate transforms), 2.3 (per-exam patient offsets), and 2.5 (manual table-origin override) are complete**; only 2.4 (convention overrides) remains, intentionally deferred (no concrete use case). Note the two distinct offset quantities — see [Offset Terminology](#offset-terminology-disambiguation).

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

#### Design as shipped

Rather than re-parsing the file on every toggle (the original sketch below), each
exam keeps a **pristine `base_data` copy** in its `loaded_exam_meta[i]` entry and
its own `swap_lat_lon` / `flip_ap1` / `flip_ap2` flags. A single engine in
`helpers.py` re-derives the transformed frame from the base + flags — idempotent
(each flag is an involution) and order-independent, so no re-parse and no risk of
double-applying. Both the single-exam global card and the per-exam toggles drive
the **same** engine, so the two never disagree.

- **`helpers.py`**
  - `_apply_transform_flags(base, swap, flip_ap1, flip_ap2, schema_name)` → returns a
    transformed copy; swap is skipped for the canonical `normalized` schema.
  - `apply_exam_transforms(state, index)` → re-derives `loaded_exams[index].normalized_data`
    from `meta["base_data"]` + flags and rebuilds the concatenated `state.rdsr_df`.
  - `exam_supports_transforms(exam, meta)` → True only for **non-normalized tabular**
    exams (DICOM conventions are applied at normalization; `normalized` is already canonical).
  - `_exam_is_ge(exam)` → GE detection from the exam's import warnings, used to set
    the **per-exam** auto lat/lon-swap default at load.
  - `load_tabular()` stores `base_data` per exam, seeds each exam's default flags
    (GE auto-swap for non-normalized in the multi path; global flags in the single
    path), and **preserves** user flags across a schema/sheet re-parse.
- **`app.py`**
  - Per-exam **"Coordinate corrections"** expandable section per exam-list row
    (swap / flip-Ap1 / flip-Ap2 switches), shown only for `exam_supports_transforms`
    exams in multi-exam mode; each toggle calls `apply_exam_transforms(i)` and marks
    results stale.
  - Global coordinate-correction card hidden in multi-exam mode (visibility managed
    imperatively in `_refresh_import_preview`).
  - `_set_transform_defaults()` and the global `_on_*_toggle()` handlers rewritten to
    write into `loaded_exam_meta[0]` and re-derive via `apply_exam_transforms(0)`
    (single-exam only).
  - `_remove_exam()` syncs the global flags back to the surviving exam when the list
    returns to a single entry.

#### Phase 2.2 checklist

- [x] Per-exam `swap_lat_lon` / `flip_ap1` / `flip_ap2` + pristine `base_data` stored in `loaded_exam_meta[i]` (`helpers.py`)
- [x] Per-exam transform toggle UI (expandable section) in each exam list row, gated by `exam_supports_transforms` (`app.py`)
- [x] `apply_exam_transforms(state, index)` engine — re-derives from base + flags, rebuilds `state.rdsr_df` (`helpers.py`)
- [x] Per-exam GE auto-swap default at load + flag preservation across re-parse (`helpers.py`)
- [x] `_set_transform_defaults()` writes per-exam (`loaded_exam_meta[0]`) and re-derives via the engine (`app.py`)
- [x] Hide global coordinate correction card when `is_multi_exam` is True (`app.py`)
- [x] Global `_on_*_toggle` handlers scoped to single-exam, routed through the per-exam engine (`app.py`)
- [x] Tests: per-exam independence, swap reversibility from base, normalized-schema skip, concat rebuild, gating, loader stores base (`test_multi_exam.py::TestGuiPerExamTransforms`)

---

### Phase 2.3 — Per-exam patient offset overrides

> **Scope:** this is the **patient offset** (shifting the patient on the table), *not* the table-origin offset. See [Offset Terminology](#offset-terminology-disambiguation). Manual table-origin override is Phase 2.5.

**Goal:** the user can set independent d_lon / d_ver / d_lat for each exam. The Python core already accepts `per_exam_offsets: list[list[float]]` in `analyze_multiple_exams()`.

> **Implementation note (deviation from the original sketch below):** the per-exam
> offset is stored **inside each `loaded_exam_meta[i]` dict** (keys `d_lon`, `d_ver`,
> `d_lat`) rather than in a separate parallel `state.per_exam_offsets` list. The
> meta list is already kept in lockstep with `loaded_exams` across every lifecycle
> path (append in both loaders, drop in `_drop_exams_for_path`, pop in
> `_remove_exam`, clear in `clear_multi_exam_state`), so reusing it means the offset
> rides along automatically — no third list to keep index-aligned, and no extra
> reset/remove wiring. Same rationale as the inlined-append decision in Phase 2.1.

#### What shipped

1. **Per-exam offset storage** — each exam's meta dict gains `d_lon`/`d_ver`/`d_lat`,
   seeded from the current global offset at load time (in `load_rdsr()` and both
   branches of `load_tabular()`, `helpers.py`).
2. **UI** — per-exam `d_lon`/`d_ver`/`d_lat` `ui.number` spinboxes (range −50…50 cm,
   step 1) rendered inside each exam card by `_refresh_exams_table()` and bound
   directly to the meta dict. An **"Apply global to all"** button copies the global
   offset into every exam. Both are shown **only in multi-exam mode** — a single
   exam runs through `analyze_data` with the global offset, where per-exam values
   would have no effect, so showing them would mislead (`app.py`).
3. **Staleness** — editing any spinbox (or pressing "Apply global to all") calls
   `reset_results()` and clears the PSD label, so a stale result is never shown
   against changed offsets (`app.py`).
4. **`run_calculation()`** builds `per_exam_offsets = [[m["d_lon"], m["d_ver"],
   m["d_lat"]] for m in state.loaded_exam_meta]` and passes it to
   `analyze_multiple_exams(...)` (`helpers.py`).
5. **Calculate-tab summary** label updated from "Per-exam offsets: global (Phase 2)"
   to "Per-exam patient offsets editable in Upload tab" (`app.py`).

#### Phase 2.3 checklist

- [x] Per-exam offset stored in `loaded_exam_meta[i]` (`d_lon`/`d_ver`/`d_lat`) — chosen over a separate `AppState.per_exam_offsets` field (see deviation note) (`state.py`/`helpers.py`)
- [x] Populate default entry (from global offset) at load time in `load_rdsr()` / `load_tabular()` (`helpers.py`)
- [x] Add per-exam d_lon / d_ver / d_lat spinboxes to each exam list row, bound to the meta dict (`app.py`)
- [x] Add "Apply global offset to all" button (`app.py`)
- [x] Reset per-exam offsets in `clear_all_exams()` — covered automatically by `clear_multi_exam_state()` zeroing `loaded_exam_meta` (`helpers.py`)
- [x] Remove entry in `_remove_exam(i)` — covered automatically by popping `loaded_exam_meta[i]` (`app.py`)
- [x] Wire `per_exam_offsets` into `run_calculation()` → `analyze_multiple_exams()` (`helpers.py`)
- [x] Tests: loader seeds offset defaults from global; `run_calculation` forwards per-exam offsets (`test_multi_exam.py::TestGuiPerExamOffsets`)

---

### Phase 2.4 — Per-exam event-processing convention overrides *(low priority)*

- [ ] Deferred — no concrete use case beyond Phase 2.2's coordinate transform toggles. Revisit if a vendor's RDSR uses a different rotation-direction convention than the global setting.

---

### Phase 2.5 — Manual per-exam table-origin offset override *(edge-case escape hatch)*

> **Scope:** this is the **table-origin offset** (`trans_offset`), *not* the patient offset. See [Offset Terminology](#offset-terminology-disambiguation).

**Why this exists:** table-origin offset and axis direction are normally set *automatically* per file from the matched manufacturer/model ([`rdsr_normalizer.py`](../../src/mypyskindose/rdsr_normalizer.py) — `norm.trans_offset` / `norm.trans_dir`), so mixed-manufacturer batches already coordinate correctly with **no** user input. This phase is the **manual escape hatch** for the cases where automation can't help:

- The scanner is **misdetected** (unknown model → fallback normalization with a generic/zero `trans_offset`).
- A **tabular export** (Radimetrics/DoseTrack) carries table positions but no usable manufacturer-convention metadata, so the correct origin can't be inferred — only the swap/flip toggles (Phase 2.2) exist today, and they don't shift the origin.

**Current limitation:** there is **no** numeric `trans_offset` override anywhere in the GUI — single- *or* multi-exam. `state.table_offset_x/y/z` are display-only (shown in the Calculate summary). This phase adds an editable override, scoped per exam.

#### Design

1. **State:** store an optional per-exam override in `loaded_exam_meta[i]`:
   ```python
   # None ⇒ use the auto-detected trans_offset from normalization (default).
   "table_origin_override": dict | None,  # {"x": float, "y": float, "z": float} in cm
   ```
   Default `None` so the common path is untouched and the auto-detected value still flows through.

2. **Apply point:** the override must be applied at **normalization** time (it feeds `Tx/Ty/Tz`), not at dose-calc time — unlike patient offset. Two options:
   - **(a) Re-normalize** the exam with a settings object whose `normalization_settings.trans_offset` is replaced by the override (clean for RDSR; mirrors the schema/sheet re-parse path via `_drop_exams_for_path` + re-load).
   - **(b) Post-adjust** the normalized frame: add `(override − detected)` to the `Tx/Ty/Tz` columns of `loaded_exams[i].normalized_data`. Cheaper, no re-parse, and works uniformly for tabular + RDSR. **Prefer (b)** unless direction (`trans_dir`) also needs overriding (then re-normalize).

3. **UI:** an expandable "Advanced: table origin" section per exam-list row, hidden by default, with x/y/z `ui.number` spinboxes pre-filled from the detected `trans_offset` and a "Reset to auto-detected" button that sets the override back to `None`. Surface a small badge on the row when an override is active so it's visible that the exam is no longer using the auto value.

4. **Provenance/export:** record the override in `ExamResult.settings_snapshot` (and the warnings list) so an overridden run is auditable — a manual origin shift materially changes the dose map.

> **As shipped:** chose option **(b) post-adjust** — implemented inside the Phase 2.2
> per-exam transform engine. `_apply_transform_flags()` gained `table_origin_override`
> + `table_origin_detected` params and re-bases `Tx/Ty/Tz` by `(override − detected)`
> **first** (in the detected, pre-swap frame) so the numeric shift composes correctly
> with any swap/flip. `apply_exam_transforms()` always re-derives from the pristine
> `base_data`, so an override toggles on/off cleanly. The override applies to any exam
> with table-position columns — DICOM (misdetected scanner; `detected` = matched
> `trans_offset`) and tabular (`detected` = 0, so the override is an absolute shift).
> Auditability is via a per-exam warning threaded through the new
> `analyze_multiple_exams(per_exam_extra_warnings=...)` param, which lands in
> `ExamResult.warnings` (and thus the export) — cleaner than mutating
> `settings_snapshot`, since the override is already baked into the data the core sees.

#### Phase 2.5 checklist

- [x] Add `"table_origin_override": dict | None` to the `loaded_exam_meta[i]` dict (default `None`) (`helpers.py`)
- [x] Capture the auto-detected `trans_offset` per exam in `loaded_exam_meta[i]` (`table_origin_detected`) so the spinboxes pre-fill and "reset to auto" works — DICOM from `norm.trans_offset`, tabular = 0 (`helpers.py`)
- [x] Apply via the per-exam engine: post-adjust `Tx/Ty/Tz` by `(override − detected)` when set; rebuild `state.rdsr_df` (`helpers.py`)
- [x] Add the expandable "Advanced: table origin" per-exam UI (x/y/z spinboxes + "Reset to auto-detected", with a no-retrigger guard on reset) (`app.py`)
- [x] Add an "ORIGIN" badge to the exam-list row when an override is active (`app.py`)
- [x] Record the override in a per-exam warning for auditability via `analyze_multiple_exams(per_exam_extra_warnings=...)` → `ExamResult.warnings` (`analyze_data.py` / `helpers.py`)
- [x] Reset overrides in `clear_all_exams()` (via `clear_multi_exam_state`) and drop the entry in `_remove_exam(i)` (covered by popping `loaded_exam_meta[i]`) (`app.py`)
- [x] Tests: override re-bases by delta, reset restores base, support gating, audit note only when active, loader seeds defaults (`test_multi_exam.py::TestGuiTableOriginOverride`)
- [ ] *(Stretch)* per-exam `trans_dir` (axis-direction) override via re-normalization, if a real misdetection case needs it

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
