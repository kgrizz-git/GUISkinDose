# Refactor Assessment

**Date:** 2026-06-11  
**Scope:** `src/guiskindose/`, `scripts/`, `tests/`  
**Excluded:** `.venv/`, `backups/`, `*.egg-info`, dev-docs

> This is the diagnostic. The executable, phased plan derived from it lives in [plans/archive/refactor-execution.md](../plans/archive/refactor-execution.md) (**completed** 2026-06-23).

---

## 1. File Size Overview

Top files by line count (Python source only):

| File | Lines |
|---|---|
| `gui/app.py` | 1,551 |
| `input_adapters/column_mapper.py` | 547 |
| `format_export_data.py` | 528 |
| `geom_calc.py` | 507 |
| `phantom_class.py` | 367 |
| `input_adapters/dosetrack.py` | 294 |
| `rdsr_normalizer.py` | 290 |
| `main.py` | 274 |
| `constants.py` | 251 |
| `plotting/plot_procedure.py` | 246 |

`app.py` at 1,551 lines is an extreme outlier — nearly 3× the second-largest file and growing with every new GUI feature.

---

## 2. The `app.py` Monolith

### 2.1 Structure

The entire GUI is a single `index()` function (lines 316–1349, **1,033 lines**) that mixes four distinct concerns:

- **UI construction** — NiceGUI widget declarations, layout, CSS bindings
- **Event handlers** — 9 `async def` closures, 10 sync closures, all defined inside `index()`
- **Business logic** — coordinate transform application, figure generation orchestration
- **State mutation** — 134+ direct accesses to `state.*` scattered throughout

### 2.2 Nested closures

All event handlers are defined as closures inside `index()` because they close over widget references (e.g. `sheet_row`, `coord_auto_label`, `event_table`). This makes them untestable and impossible to reuse. Every new feature adds more closures to the same scope.

Async closures alone:
`handle_upload`, `load_example`, `_on_sheet_change`, `preview_setup`, `preview_event`, `preview_procedure`, `do_calculate`, `download_html`, `download_png`

### 2.3 Recommendation

Split into per-tab modules under `gui/tabs/`:

```
gui/
  app.py          # just calls ui.page("/") + ui.run()
  layout.py       # drawer, nav, top bar
  state.py        # (existing)
  helpers.py      # (existing)
  tabs/
    upload.py     # ~150 lines
    data.py       # ~120 lines
    settings.py   # ~120 lines
    geometry.py   # ~200 lines
    calculate.py  # ~120 lines
    results.py    # ~150 lines
    export.py     # ~180 lines
  widgets/
    import_preview.py   # import preview card + sheet picker + coord toggles
    event_table.py      # irradiation event table
```

The key enabling change: stop closing over widget references. Instead, store widget objects in a thin `PageContext` dataclass passed explicitly to each tab builder function. Handlers then receive the context rather than close over the enclosing scope. This makes them extractable, testable, and composable.

---

## 3. Input Adapter Duplication

All four real adapters (`normalized`, `generic_rdsr_like`, `radimetrics`, `dosetrack`) follow identical structure:

1. Call `detect_header_row()` 
2. Call `map_columns()`
3. Call `check_duplicate_mappings()`
4. Coerce numeric columns
5. Apply unit conversions
6. Call `rdsr_normalizer()`
7. Build `InputProvenance` + `InputAdapterResult`

Steps 1–3 and 7 are copy-pasted with minor variations. The three stub adapters (`qaelum`, `dosemonitor`, `dosewatch`) are 42–43 lines each of identical boilerplate.

### Recommendation

Extract a `BaseAdapter` (or a free function `run_adapter_pipeline`) that handles steps 1–3 and 7, leaving each adapter to implement only the unit conversions and column-specific logic:

```python
# input_adapters/base.py
def run_pipeline(
    loaded: _RawLoad,
    known_names: frozenset[str],
    patterns: dict[str, list[str]],
    transform_fn: Callable[[pd.DataFrame, list[str]], tuple[pd.DataFrame, list[str]]],
    original_filename: str,
    settings: PyskindoseSettings | None = None,
) -> InputAdapterResult:
    ...
```

Collapse the three stub adapters into a single `_stub_adapter(vendor_name)` factory that raises `NotImplementedError` with the implementation instructions. That's one file instead of three.

---

## 4. Temp File Leak

In `app.py:423`, uploaded files are written to disk with `delete=False`:

```python
with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
    tmp.write(e.content.read())
    tmp_path = Path(tmp.name)
# tmp_path is never deleted — not on success, not on failure
```

The temp file persists until the OS cleans it up. On a long-running server this accumulates indefinitely.

### Fix

```python
import atexit, weakref
_tmp_files: list[Path] = []

def _write_upload_to_tmp(content: bytes, suffix: str) -> Path:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        path = Path(tmp.name)
    _tmp_files.append(path)
    return path

@atexit.register
def _cleanup_tmp_files():
    for p in _tmp_files:
        p.unlink(missing_ok=True)
```

Or simply delete after `run.io_bound` completes, since `load_rdsr` and `load_tabular` both read the file fully before returning.

---

## 5. Global Mutable State and Thread Safety

`gui/state.py` exposes a single shared `AppState` dataclass instance. NiceGUI runs async handlers concurrently via asyncio, and uses `run.io_bound()` to push blocking I/O onto a thread pool. Both paths share the same `state` object with no locks.

**Risk scenarios:**
- Two rapid uploads (user double-clicks) could interleave `state.rdsr_df` writes.
- `do_calculate()` reads `state.rdsr_df` while `_on_swap_toggle()` is replacing it.
- `run.io_bound(load_tabular, ...)` mutates `state` on a worker thread while the main asyncio loop also reads it.

The `AppState` dataclass has 30+ fields; many are written by helpers and read by app.py with no synchronization.

### Recommendation

Short-term: document the assumption that only one operation runs at a time (which is effectively true for single-user native mode) and add a `_busy` flag to block concurrent operations. Longer-term: move state mutations out of worker threads by having helpers return values rather than writing to `state` directly.

---

## 6. Error Handling

### Bare broad catches with print

| Location | Pattern |
|---|---|
| `gui/helpers.py:86, 145, 185, 210` | `except Exception: print(traceback); return False, err` |
| `gui/app.py:69, 842, 1216, 1399+` | `except Exception as e: dprint(...); return None` |
| `input_adapters/dosetrack.py:271` | `except Exception as exc: raise ValueError(...)` |

Catching `Exception` is appropriate at I/O boundaries (file load, calculation). The problem is the pattern at lower levels (adapter internals, geometry functions) where specific exceptions would give better diagnostics.

### No structured logging

`dprint()` (a thin debug-flag gate over `print`) and bare `print()` are used inconsistently. There is no log level, no file sink, no structured format. When running in native mode there is no console to read from.

### Recommendation

Replace `dprint` with Python's stdlib `logging` throughout. One `logging.getLogger(__name__)` per module, configured at startup. This costs nothing and immediately enables file-based logging for diagnosing native-mode issues.

---

## 7. Test Coverage Gaps

Files with no corresponding unit tests (sorted by size):

| File | Lines | Risk |
|---|---|---|
| `format_export_data.py` | 528 | High — complex JSON/HTML serialization, provenance embedding |
| `geom_calc.py` | 507 | High — core physics calculations |
| `phantom_class.py` | 367 | Medium — mesh construction logic |
| `rdsr_normalizer.py` | 290 | High — central normalization; bugs are silent wrong numbers |
| `main.py` | 274 | Low — CLI glue |
| `beam_class.py` | 214 | Medium |
| `rdsr_parser.py` | 185 | Medium — DICOM tag extraction |
| `constants.py` | 251 | Low — data tables |

`rdsr_normalizer.py` is especially high-risk: it applies per-vendor offsets and direction inversions. A regression there produces plausible-looking but wrong dose maps with no error raised.

---

## 8. `column_mapper.py` Scope Creep

At 547 lines, `column_mapper.py` does too much:

- Defines `_normalize_str`, `_score_row`, `detect_header_row` (generic utilities)
- Defines `NORMALIZED_COLUMN_NAMES`, `GENERIC_RDSR_COLUMN_NAMES`, `RADIMETRICS_COLUMN_NAMES`, `DOSETRACK_COLUMN_NAMES` (per-vendor knowledge)
- Defines `map_columns`, `check_duplicate_mappings`, `unmapped_columns_warning` (mapping engine)

The per-vendor column name sets belong in their respective adapter modules. `column_mapper.py` should own only the generic detection/mapping engine, keeping it stable as vendors are added or modified.

---

## 9. `format_export_data.py` — Untested and Complex

528 lines, no tests. Produces the JSON and HTML outputs that users actually save and share. Potential issues:

- Provenance embedding in HTML uses string concatenation to inject a comment into `<head>` — fragile if the HTML structure changes.
- NaN handling in JSON export (`fillna`) is done ad-hoc per call site rather than centrally.
- No schema versioning in JSON output — a downstream consumer has no way to detect format changes.

---

## 10. Minor Issues

**`constants.py` (251 lines):** Mix of physical constants, lookup tables, and configuration values. Consider splitting into `physics_constants.py` and `lookup_tables.py` for findability.

**`plotting/` fragmentation:** 15 files for plotting, many with 1–2 functions each. No shared base for common figure styling (colors, fonts, layout defaults). Style changes require touching every file.

**`main.py` CLI parsing (274 lines):** The argparse setup is long but not a refactoring priority — it's mostly inert declarative code. _Resolved 2026-07-29 — Phase 4c extracted the parser into `cli_args.py` (per-flag helpers) and `main.py` dropped below the 800-line ceiling; see `tmp/20260728T193500Z_sonar_lizard_issues_plan.md`._

**`phantom_class.py`:** `Phantom` class has methods that do geometric computation and methods that do visualization. These are different concerns and could be separated, but the class is 367 lines and manageable as-is.

---

## Priority Order

| Priority | Item | Effort | Value |
|---|---|---|---|
| 1 | Fix temp file leak | 30 min | High — correctness/resource |
| 2 | Add logging framework | 2 h | High — operability |
| 3 | Add tests for `rdsr_normalizer.py` | 4 h | High — correctness |
| 4 | Add tests for `format_export_data.py` | 3 h | High — correctness |
| 5 | Extract adapter base pipeline | 4 h | Medium — maintainability |
| 6 | Move per-vendor column sets into adapter modules | 2 h | Medium — cohesion |
| 7 | Split `app.py` into tab modules | 2–3 days | High — but low urgency until the file grows further |
| 8 | `PageContext` pattern to decouple widget references | 1 day | Prerequisite for #7 |
| 9 | Add `_busy` flag / operation guard | 2 h | Medium — correctness under fast interaction |
