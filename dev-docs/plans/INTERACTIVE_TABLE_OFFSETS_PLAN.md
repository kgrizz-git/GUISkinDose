# Interactive Table Offsets & Settings Display Plan

> **Filename note:** Phase 1 = read-only **auto-detected** table offsets. Phase 2 = interactive **patient** sliders. **Phase 2b** = interactive **table-origin** override in Geometry (writes `table_origin_override` in per-exam meta). Settings → Per-exam corrections spinboxes remain; Geometry is the 3D workflow.

## Overview

Two `TO_DO.md` items:

1. **Interactive offset adjustment in Geometry tab** — **patient** positioning (`d_lon` / `d_ver` / `d_lat`) **and table-origin override** (`table_origin_override` x/y/z in `loaded_exam_meta`) with live 3D preview.
2. **Settings tab: Table Offsets (read-only) + Patient Offsets (adjustable).**

| Concept | Storage | User can change? |
|---------|---------|------------------|
| Auto-detected table offset | `state.table_offset_*`, `meta.table_origin_detected` | Read-only display (Phase 1) |
| Table-origin override | `meta.table_origin_override` | Phase 2b Geometry sliders + Settings → Advanced: table origin |
| Patient offset | `state.d_lon/ver/lat`, `meta.d_*` | Phase 2 Geometry sliders + Settings spinboxes |

### Scope notes

- **Multi-exam Geometry sliders deferred** until `active_exam_index` has a setter UI (patient offsets **and** table-origin). Per-exam editing today: `_per_exam.py`.
- **Multi-exam preview vs dose:** Geometry preview is a **composite** of all loaded exams (global patient offset + each exam’s rebased frames). Dose uses `loaded_exam_meta[i]` per exam. Phase 2 banner states this.
- **Phase 0 resets** globals on new load (`load_rdsr`, `load_tabular` when `not replace_existing`, `clear_all_exams`). `_remove_exam` multi→single restores globals from surviving exam meta. `load_example` → `load_rdsr`.

### Pre-existing bugs (fix in this plan)

- **Calculate tab** (`calculate.py:125-127`, `129-136`): patient and table offset summaries each bind only one axis (`d_lon` / `table_offset_x`); y/z stale.
- **Per-exam global label** (`_per_exam.py:235-237`): static f-string; stale after global offset edits.

### State ownership (implementers)

After first load, single-exam **coordinate flags**, **patient offsets**, and **table-origin override** live in `loaded_exam_meta[0]`; Import Preview and Per-exam corrections both read/write that dict.

---

## Phase 0: Prerequisites

Ship 0.1–0.3 together.

### 0.1 Reset on file load / clear

**Patient offsets** — zero `state.d_lon/ver/lat` before `build_settings` in `load_rdsr`; in `load_tabular` only when `not replace_existing` (parser does not mutate globals; meta appended later copies current values). `clear_all_exams` zeros globals.

**Coordinate flags** — on new loads only (`load_rdsr`; `load_tabular` when `not replace_existing`), also reset `state.swap_lat_lon`, `flip_ap1`, `flip_ap2` to `False`. Preserve on `replace_existing`.

**`_remove_exam` multi→single** (`upload.py:386-394`): when `n == 1` after removing an exam, restore globals from `meta0` (today only `swap_lat_lon`/`flip_ap*` are restored):

```python
state.d_lon = float(meta0.get("d_lon", 0.0))
state.d_ver = float(meta0.get("d_ver", 0.0))
state.d_lat = float(meta0.get("d_lat", 0.0))
```

### 0.2 `build_settings` explicit `patient_offset`

Add `patient_offset: tuple[float, float, float] | None = None` as the **last** parameter (after `output_format`). Grep `build_settings(` before merge.

Add seam helper in `helpers.py`:

```python
def effective_patient_offset_for_preview(state: AppState) -> tuple[float, float, float]:
    # Single-exam: global. Multi-exam: global until active_exam_index ships.
    return (state.d_lon, state.d_ver, state.d_lat)
```

`make_geometry_fig` → `build_settings(..., patient_offset=effective_patient_offset_for_preview(state))`. `create_geometry_plot` already reads `settings.phantom.patient_offset`.

### 0.3 Global offset handlers + meta sync

```python
def sync_global_patient_offset_to_single_exam_meta(state: AppState) -> None:
    if len(state.loaded_exams) == 1 and state.loaded_exam_meta:
        m = state.loaded_exam_meta[0]
        m["d_lon"], m["d_ver"], m["d_lat"] = state.d_lon, state.d_ver, state.d_lat

def on_global_patient_offset_scrub(ctx: PageContext) -> None:
    sync_global_patient_offset_to_single_exam_meta(state)

def on_global_patient_offset_change(ctx: PageContext) -> None:
    on_global_patient_offset_scrub(ctx)
    reset_results()
    ctx.refresh_per_exam()  # unconditional — default is no-op until upload tab wires it
```

- **Settings spinboxes:** `on_global_patient_offset_change(ctx)`.
- **Geometry sliders:** tick wrapper in `geometry.py` calls `on_global_patient_offset_scrub(ctx)` then `offset_changed_since_calc = True` (`nonlocal`); **`ctx.refresh_per_exam()` only in debounced callback**.

**Stale-dose caption (Phase 2 / 2b):** closure flag `offset_changed_since_calc` — set in Geometry tick wrappers (patient + table-origin); clear when `reset_results()` runs **or** when a dose calculation completes successfully. Caption visible when `state.calculation_done and offset_changed_since_calc`.

**Files:** `helpers.py`, `upload.py` (`clear_all_exams` + `_remove_exam`), `settings.py`, `figures.py`, `tests/unittests/test_gui_offset_reset.py` (new).

---

## Phase 1: Table offsets in Settings

1. **Table Offsets (auto-detected)** — three `bind_text_from` labels (`X: … cm`, `Y: …`, `Z: …`); caption when override active: “Manual table origin in use — adjust in Geometry or Per-exam corrections.”
2. Patient header → “Patient Offsets (adjustable, cm)”.
3. **Calculate tab:** same three-binding pattern for patient and table offsets; same axis-prefixed format as Settings.
4. **Display by `normalization_method`:** `Unknown` → “—”; `Tabular` → zeros + note; `Fallback` → amber badge; `Matched` → show values. (`"None"` from `rdsr_normalizer` raises before GUI — never displayed.)

   Store `"normalization_method"` on each `loaded_exam_meta` dict in `helpers.py`:
   - `load_rdsr`: meta literal ~122–157 → `norm.normalization_method`
   - `load_tabular` single-study meta ~332–355 → `"Tabular"`
   - `load_tabular` multi-study meta ~282–305 → `"Tabular"`

   Multi-exam caption when any meta has `Fallback`: “N exam(s) used fallback normalization”.
5. Caption when any `table_origin_override` active.

Visible when Phantom Settings expansion is open (no nested sub-expansion).

**Files:** `settings.py`, `calculate.py`, `helpers.py` (meta field on load)

---

## Phase 2: Geometry — patient offset sliders (single-exam)

**Prerequisites:** Phase 0.

### Closure inside `build(ctx)`

Closure vars (all `nonlocal` where reassigned): `slider_timer`, `last_preview_mode`, `live_preview_requested`, `offset_changed_since_calc`, `table_origin_pending`.

**Debounce** (`results.py:240` precedent — cancel prior timer before scheduling):

```python
def _schedule_debounced_render():
    nonlocal slider_timer
    if slider_timer is not None:
        slider_timer.cancel()
    slider_timer = ui.timer(0.25, _do_debounced_render, once=True)
```

**`_do_debounced_render`:**

1. If `table_origin_pending`: `commit_table_origin_transform(state, 0)`; `table_origin_pending = False`; `reset_results()`  
   *(index `0` valid while Phase 2b is single-exam only; use `active_exam_index` when multi-exam sliders ship)*
2. `refresh_per_exam()` + re-render last mode (`plot_event` uses live `geom_event_input.value`)

`live_preview_allowed()` → false when `state.busy`, or procedure mode with `event_count() > 30`. Render when `live_preview_requested and live_preview_allowed()`. **PAUSED** badge when blocked.

**Sliders:** hidden when `state.rdsr_df is None` or `state.is_multi_exam`. ±150 cm (`PATIENT_OFFSET_SLIDER_RANGE_CM`); tooltip if `|value| > 150`. Tick → update state + `on_global_patient_offset_scrub(ctx)` + `offset_changed_since_calc = True` + `_schedule_debounced_render()`. `geom_spinner` when `event_count() > 100`. Patient scrub does **not** call `reset_results`. Amber caption when `calculation_done and offset_changed_since_calc`: *“Offset changed — run Calculate again for an updated dose map.”*

**Multi-exam:** hide sliders; banner: *“Composite preview of all loaded exams (table positions and global patient offset). Dose uses per-exam offsets and table-origin overrides from Settings → Per-exam corrections.”*

**Reset:** zero → `on_global_patient_offset_change(ctx)` → clear plot → `ui.notify("Patient offset reset to 0", color="info")`.

**Files:** `geometry.py`, `gui/constants.py`, `docs/source/gui_help/positioning_offsets.md` (+ sync)

---

## Phase 2b: Geometry — table-origin sliders (single-exam)

**Goal:** Interactively override vendor table origin in the 3D view. Writes `loaded_exam_meta[0].table_origin_override` — same dict as Settings → Advanced: table origin (`_per_exam.py:93-116`).

**Prerequisites:** Phase 0, Phase 2 (shared closure debounce).

### Data model

- **Detected:** `meta["table_origin_detected"]` (from `norm.trans_offset` or zeros for tabular).
- **Override:** `None` or `{"x","y","z"}` absolute cm. **Apply:** `apply_exam_transforms` → `rebuild_rdsr_df` (O(n) — **not per tick**).

Shared helpers in `helpers.py`:

```python
def effective_table_origin(meta: dict) -> dict[str, float]:
    detected = meta.get("table_origin_detected") or {"x": 0.0, "y": 0.0, "z": 0.0}
    ov = meta.get("table_origin_override")
    if ov is not None:
        return {k: float(ov.get(k, detected[k])) for k in ("x", "y", "z")}
    return {k: float(detected[k]) for k in ("x", "y", "z")}

def stage_table_origin_axis(meta: dict, axis: str, value: float) -> None:
    """Tick path: update meta only (lazy-create override from detected). No apply_exam_transforms."""
    detected = meta.get("table_origin_detected") or {"x": 0.0, "y": 0.0, "z": 0.0}
    if meta.get("table_origin_override") is None:
        meta["table_origin_override"] = dict(detected)
    meta["table_origin_override"][axis] = float(value)

def commit_table_origin_transform(state: AppState, exam_index: int) -> None:
    apply_exam_transforms(state, exam_index)
```

*Pattern: `stage_*` = O(1) meta/dict writes; `commit_*` = O(n) `apply_exam_transforms`. Spinboxes commit immediately; sliders commit in debounced callback.*

**Scrub (Geometry):** `stage_table_origin_axis(meta, axis, value)` + `nonlocal table_origin_pending, offset_changed_since_calc`; set both `True`; `_schedule_debounced_render()`. Preview lags slider ~250 ms — acceptable.

**Settings `_per_exam.py`:** refactor `_on_change` (lines 93-99) to `stage_table_origin_axis` + `commit_table_origin_transform` immediately (spinbox = discrete commit). Preserve `guard["suppress"]` on reset (lines 108-112).

**Reset:** `table_origin_override = None` → `commit_table_origin_transform` → `reset_results()` → `refresh_per_exam()`. **Geometry sliders:** set values from `effective_table_origin(meta)` inside `guard` (same pattern as `_on_reset`) — do not bind directly to override dict (KeyError when `None`).

### UI

- Section below patient sliders; visible when `len(loaded_exams)==1`, `exam_supports_table_origin`, not `is_multi_exam`, `rdsr_df` loaded.
- Sliders x/y/z, range `TABLE_ORIGIN_SLIDER_MIN/MAX` (−250…250). **PAUSED** / stale-dose captions shared with Phase 2.

**Files:** `helpers.py`, `geometry.py`, `_per_exam.py`, `gui/constants.py`, help doc

---

## Phase 3: Offset arrow (deferred)

Toggleable arrow trace when offset non-zero; reuses `effective_patient_offset_for_preview`.

---

## Testing

**Unit (`tests/unittests/test_gui_offset_reset.py`):**
- `test_load_rdsr_resets_global_patient_offset`
- `test_load_tabular_resets_global_patient_offset`
- `test_load_tabular_replace_existing_preserves_global_patient_offset`
- `test_clear_all_exams_resets_global_patient_offset`
- `test_new_load_resets_coordinate_flags_not_replace_existing`
- `test_sync_global_patient_offset_to_single_exam_meta`
- `test_sync_does_not_touch_meta_when_multi_exam`
- `test_build_settings_propagates_explicit_patient_offset`
- `test_on_global_patient_offset_change_invokes_refresh_per_exam`

- `test_remove_exam_restores_global_patient_offset_from_meta`
- `test_stage_table_origin_axis_does_not_call_apply`
- `test_commit_table_origin_transform_rebuilds_rdsr_df`

**Manual matrix:**
| ID | Assert |
|----|--------|
| 0a | Second RDSR load zeros global offsets; exam A per-exam meta preserved |
| 0b | Clear all zeros globals |
| 0c | New load (RDSR ↔ tabular) zeros globals |
| 0d | Multi-exam: per-exam offsets on A preserved when B loaded |
| 0e | Single-exam: preview offset matches dose map |
| 0f | Multi-exam: composite-preview banner visible; dose uses per-exam meta |
| 0g | Tabular re-parse (`replace_existing`) preserves globals |
| 0h | Single exam: Settings edit mirrors `meta[0]`; survives adding exam 2 |
| 0i | Remove exam B (multi→single): `d_lon/ver/lat` restored from remaining exam meta |
| 1a | RDSR table offsets in Settings (three bindings) |
| 1b | Tabular → zeros + note |
| 1c | Change only `d_ver` → Calculate patient summary updates |
| 1d | Change only `table_offset_y` → Calculate table summary updates |
| 1e | `Unknown` / `Fallback` / multi-exam fallback count caption |
| 1f | Multi-exam: Settings global offset edit refreshes per-exam global label |
| 1g | Data export metadata unchanged (`data.py:62-64`) |
| 2a | Sliders hidden single-exam only; multi-exam banner |
| 2b | Debounced scrub → one render after ~250 ms; table-origin preview lags until commit |
| 2c | Procedure >30 events → PAUSED; Setup/Single still live |
| 2d | Settings offset >150 → slider tooltip, value not clamped |
| 2e | Reset → notify + plot cleared + results invalidated |
| 2f | No data loaded → slider row hidden |
| 2g | After calc, patient slider scrub → stale-dose caption |
| 2h | Release table-origin slider; wait ≥300 ms; preview + Data table `Tx/Ty/Tz` reflect new origin |
| 2i | Table-origin Reset → override `None`, matches auto-detected; Settings spinboxes sync |
| 2j | Table-origin scrub after calc → results invalidated (PSD cleared) |

---

## Checklist

**Phase 0**
- [ ] Patient-offset + coordinate-flag reset on new load (`load_rdsr`, `load_tabular` when `not replace_existing`, `clear_all_exams`)
- [ ] `_remove_exam` multi→single restores `d_lon/ver/lat` from meta
- [ ] `patient_offset` last on `build_settings`; grep all callers
- [ ] `effective_patient_offset_for_preview`; sync helper; `_per_exam.py` global-label fix (three bindings)

**Phase 1**
- [ ] Three bindings per offset display (Settings + Calculate)
- [ ] `normalization_method` per exam in meta at three `helpers.py` insertion points (`Unknown` / `Tabular` / `Fallback` / `Matched`)

**Phase 2 / 2b**
- [ ] Closure: `nonlocal` on reassigned vars; `_schedule_debounced_render` cancel-reschedule
- [ ] Geometry tick sets `offset_changed_since_calc`; table-origin tick sets `table_origin_pending`
- [ ] `stage_table_origin_axis` / `commit_table_origin_transform` / `effective_table_origin`; `_per_exam.py` delegates; reset uses `guard["suppress"]`
- [ ] Table-origin scrub stages meta only; `apply_exam_transforms` in debounced callback only

**Cross-cutting**
- [ ] `CHANGELOG.md` — **Fixed:** Calculate patient/table stale bindings; per-exam global label stale; offset + coordinate-flag leak on load; `_remove_exam` offset restore. **Added:** read-only table offsets; Geometry patient + table-origin sliders; reset buttons. Link plan.
- [ ] `docs/source/gui_help/positioning_offsets.md` + `sync_gui_help.py` (Phase 2)
- [ ] `TO_DO.md` items checked; clarify “table offsets” wording

---

## Open questions (resolved)

| # | Decision |
|---|----------|
| 1 | **Yes** — Geometry scrub shows stale-dose caption when `calculation_done` (see Phase 2). |
| 2 | Settings spinbox soft limits (±150)? **No** — unbounded; slider tooltip. |
| 3 | Rename Data export columns? **No** this phase. |
| 4 | Data tab inline table-offset block? **Defer**. |
| 5 | Partial `refresh_per_exam`? **No** — full rebuild in debounce. |
| 6 | Phase 2b scrub cost? **Debounce** `apply_exam_transforms` (stage meta on tick). |
| 7 | Table-origin reset slider sync? **Explicit set** from `effective_table_origin` + `guard["suppress"]` (mirror `_per_exam._on_reset`). |
| 8 | `offset_changed_since_calc` setter? **Geometry tick wrappers** (`nonlocal`), not `helpers.py` scrub handler. |
| 9 | `effective_table_origin` body in plan? **Yes** — full implementation in Phase 2b. |
| 10 | `normalization_method` `"None"` branch? **Dead code** — omit from UI mapping. |

---

## Optional follow-up (out of scope)

- Data tab inline table-offset display
- Settings spinbox soft limits aligned with slider range
- Export `table_origin_override` in `data.py` metadata (today only auto-detected origin at `data.py:62-64`)
- Incremental table-origin preview without full `apply_exam_transforms` per commit
- Offset presets

---

## Exit criteria

Archive when Phases 0–**2b** ship and manual matrix passes. Run `python scripts/check_doc_freshness.py`. Update `dev-docs/index.md`, `dev-docs/plans/archive/README.md`, `TO_DO.md`.

## Future

- Exam-selector UI + `active_exam_index` before multi-exam Geometry sliders (patient **and** table-origin).
- Partial per-exam refresh API if full `refresh_per_exam` proves too heavy.
- Hint when Settings offset `|value| > 150` (slider range) without clamping.

## TO_DO.md

- [ ] Allow manual interactive setting of table offsets in GUI → Phase **2b** (table-origin override) + Phase 2 (patient offsets)
- [ ] Settings tab: Table Offsets read-only + Patient Offsets adjustable → Phase 1
