# Interactive Table Offsets & Settings Display Plan

> **Filename note:** The plan file name predates scope refinement. **Phase 1** surfaces auto-detected **table** offsets (read-only). **Phase 2** adds interactive **patient** offset sliders in the Geometry tab. Manual **table-origin** override already ships in Settings → Per-exam corrections (`_per_exam.py`); this plan does not replace that control.

## Overview

Two `TO_DO.md` items address gaps in how offsets are exposed and adjusted in the GUI:

1. **Interactive offset adjustment in Geometry tab** (`TO_DO`: “Allow manual interactive setting of table offsets in GUI”) — historically worded “table offsets,” but the actionable gap is **patient** positioning (`d_lon` / `d_ver` / `d_lat`). Table offsets stay vendor-normalized and read-only; users adjust patient placement interactively in the 3D view instead of only via Settings spinboxes.
2. **Settings tab: show Table Offsets (read-only) and Patient Offsets (adjustable)** — display auto-detected table-offset values and distinguish them from user-adjustable patient offsets.

Both features share `state.table_offset_*` (auto-detected, last-loaded exam in multi-exam) and `state.d_lon/ver/lat` (global patient offsets).

### Scope notes (added after assessment review)

- **Phase 2 multi-exam slider binding is deferred.** `state.active_exam_index` is a stub — defined in `state.py:51` and only ever set to `None` (`state.py:118`, `helpers.py:561` in `clear_multi_exam_state`). No UI element or handler sets it to a meaningful value, and there is no exam selector in the Geometry tab. Implementing “active-exam slider re-binding” requires a new exam selector widget plus explicit unbind/rebind logic (NiceGUI's `bind_value` is to a specific dict reference, not a key path). To keep Phase 2 shippable, **Phase 2 sliders bind to the global `state.d_lon/ver/lat` only** (single-exam workflow). Multi-exam slider support is deferred to a later phase that adds the `active_exam_index` infrastructure. For multi-exam offset editing, the per-exam spinboxes in `_per_exam.py:155-166` remain the supported path.
- **Offset reset on file load is a Phase 0 prerequisite.** Neither `load_rdsr` nor `load_tabular` currently resets `state.d_lon/ver/lat` when a new file is loaded; only `state.table_offset_x/y/z` is overwritten. Without a reset, user-adjusted offsets “leak” from one file to the next. Phase 0.1 commits to adding the global reset in both load functions and in `clear_all_exams`. The newly-appended per-exam entry inherits the zeroed global automatically; per-exam meta for already-loaded exams is **not** touched (user edits are preserved across new loads). **`load_tabular(..., replace_existing=True)`** (schema/sheet re-parse) must **not** zero globals — only fresh appends and `clear_all_exams` reset.
- **`build_settings` per-exam offset is a Phase 0 prerequisite.** The geometry preview reads the **global** offset via `build_settings` (`helpers.py:52-54`), but `run_calculation` reads **per-exam** offsets from `state.loaded_exam_meta` in multi-exam mode (`helpers.py:440-447`). Single-exam mode already uses the global offset for both paths. Phase 0.2 adds an explicit `patient_offset` parameter and a small `effective_patient_offset_for_preview(state)` helper so preview logic is centralized; **multi-exam preview still uses the global offset until `active_exam_index` exists** (documented limitation, not a silent bug).

---

## Current State

### Existing

- **Table offsets:** computed by `rdsr_normalizer()`, stored in `state.table_offset_x/y/z` (`helpers.load_rdsr:174-176`). Values from vendor scanner convention (`normalization_settings.trans_offset`). In multi-exam mode these globals reflect the **last-loaded** DICOM exam only (`load_rdsr` / `load_tabular` overwrite them on each load).
- **Patient offsets:** global spinboxes in Settings tab (`settings.py:61-71`); changes call `reset_results()`.
- **Per-exam patient offsets:** `state.loaded_exam_meta[*][d_lon/ver/lat]` in `_per_exam.py` (visible only when `state.is_multi_exam`).
- **Table-origin override:** `_per_exam.py` “Advanced: table origin” — per-axis spinboxes that re-base table positions (single- and multi-exam). Phase 1's read-only table offset display complements this existing override (not a replacement).
- **Geometry tab:** renders 3D views but has no offset controls.
- **Help:** `docs/source/gui_help/positioning_offsets.md` (mirrored to `src/mypyskindose/gui/help/`) explains offset semantics; step 3 still says “Adjust offsets in Settings” — update when Phase 2 ships.

### Missing

- Table offsets visible only during Data tab export (`data.py:62-64`), not in Settings or Geometry.
- No interactive patient-offset adjustment from Geometry tab.
- Settings tab conflates table offsets and patient offsets visually.
- No visual offset indicator in Geometry 3D view.
- Patient offsets persist across file loads (no reset in `load_rdsr`, `load_tabular`, or `clear_all_exams`).
- Geometry preview and dose map read offsets from different sources in **multi-exam** mode (preview: global `state.d_lon/ver/lat`; dose: per-exam `loaded_exam_meta[i][d_lon/ver/lat]`). Single-exam mode is already aligned.

---

## Phase 0: Prerequisites (must precede Phase 1/2)

Two changes that the rest of the plan depends on. Implement and ship first.

### 0.1 Reset patient offsets on file load and clear

- **`helpers.load_rdsr` (`helpers.py:70-187`):** immediately after `try:`, before `build_settings(...)` (currently ~line 80), set `state.d_lon = state.d_ver = state.d_lat = 0.0`. The new entry appended to `state.loaded_exam_meta` later (`:122-157`) copies these values into its `meta[d_lon/ver/lat]`, so the new exam starts at zero **automatically — do not also reset the meta dicts of already-loaded exams.** Those represent user edits that should survive a new load.
- **`helpers.load_tabular` (`helpers.py:202-399`):** same zeroing at the top of the `try` block, **before** `build_settings` and **before** the `replace_existing` branch — but only for **new** loads (`replace_existing=False`). When `replace_existing=True`, preserve the current global offset (user may be switching schema/sheet only).
- **`clear_all_exams` in `tabs/upload.py:185-218`:** add the same zeroing (currently resets `table_offset_x/y/z` but not patient offsets). Per-exam meta is cleared by `clear_multi_exam_state` so no separate action is needed there.

Place all three resets **before** any other state mutation in the function (so partial-failure doesn't leave mixed state).

### 0.2 Fix `build_settings` to accept an explicit patient offset

Add an optional `patient_offset: tuple[float, float, float] | None = None` parameter to `build_settings` (`helpers.py:36`). When `None`, fall back to the current global `state.d_lon/ver/lat` (preserves existing callers). When provided, use it directly for `phantom.patient_offset`.

Add a helper in `helpers.py`:

```python
def effective_patient_offset_for_preview(state: AppState) -> tuple[float, float, float]:
    """Offset used by the Geometry tab preview.

    Single-exam: global (matches analyze_data).
    Multi-exam: global until active_exam_index is wired; per-exam preview is deferred.
    """
    return (state.d_lon, state.d_ver, state.d_lat)
```

Update `figures.make_geometry_fig` (`figures.py:29`) to pass `patient_offset=effective_patient_offset_for_preview(state)`. When multi-exam active-exam preview ships later, only this helper (and the Geometry tab caller) need to change.

Update `tests/unittests/test_gui_below_floor_kvp.py` if the `build_settings` signature change requires explicit kwargs in tests.

This change is small but is the **only** way to guarantee single-exam geometry preview matches the dose map and to centralize multi-exam preview policy.

### Files changed

- `src/mypyskindose/gui/helpers.py` (0.1, 0.2)
- `src/mypyskindose/gui/tabs/upload.py` (0.1)
- `src/mypyskindose/gui/figures.py` (0.2 — call-site update)
- `tests/unittests/test_gui_below_floor_kvp.py` (0.2 — only if signature change breaks tests)

---

## Phase 1: Display Table Offsets in Settings Tab

**Goal:** Show auto-detected table offset values in Settings → Phantom Settings.

### Changes

1. **Add read-only “Table Offsets (auto-detected)” display** in Phantom Settings expansion, above patient offset spinboxes.
   - Three read-only labels: `table_offset_x`, `table_offset_y`, `table_offset_z` with units (cm).
   - Info icon/tooltip: “Vendor-specific table coordinate origin from RDSR normalization. Read-only; adjust patient offsets below. For a wrong scanner match, use Per-exam corrections → Advanced: table origin.”
   - **Fallback badge:** Show amber warning if `state.normalization_method == "Fallback"`. Use the same condition as the existing upload tab warning (`tabs/upload.py:59-60`); do not re-implement detection logic. (`state.normalization_warnings` is also currently equivalent — populated only when `normalization_method == "Fallback"` in `helpers.load_rdsr:177-181` — but the existing pattern uses `normalization_method` directly, so prefer that for consistency.)
   - **Multi-exam caveat (inline caption):** When `state.is_multi_exam`, note “Values shown are from the most recently loaded DICOM exam” (tabular loads zero these globals).
   - **Table-origin override summary:** When any `loaded_exam_meta[i].table_origin_override` is non-`None`, show an amber caption: “Manual table-origin override active on N exam(s) — see Per-exam corrections below.” (Per-exam cards already show an `ORIGIN` badge at `_per_exam.py:144-147`; this is an aggregate heads-up in Phantom Settings.)
   - Location: `settings.py`, Phantom Settings expansion, after “Phantom model and positioning” row, before patient offset spinboxes.

2. **Rename label** above existing spinboxes to “Patient Offsets (adjustable, cm)”.

### Layout

```
settings.py (Phantom Settings expansion):

  [HelpButton "Phantom Positioning Offsets"]

  [Phantom model] [Human mesh]
  [Patient orientation]

  ── Table Offsets (auto-detected) ───────────────────────  NEW
      X: 12.3 cm   Y: 105.0 cm   Z: 173.0 cm              NEW
      [?] tooltip: "Vendor-specific table coordinate origin
                   from RDSR normalization. Read-only; adjust
                   patient offsets below."
      [⚠ Fallback: scanner model not matched]              NEW (conditional on state.normalization_method == "Fallback")
      [Multi-exam: values from last loaded DICOM exam]   NEW (conditional on state.is_multi_exam)
      [N exam(s): manual table-origin override active]   NEW (conditional on any override)

  ── Patient Offsets (adjustable, cm) ────────────────────  Renamed
      [Longitudinal] [Vertical] [Lateral]
```

### Files changed

- `src/mypyskindose/gui/tabs/settings.py`

### Decisions

- Display always visible but compact (no expansion).
- Tabular / no DICOM normalization: when `state.normalization_method == "Tabular"` (or all loaded exams are tabular), show `(0, 0, 0)` with note “Tabular input — no vendor normalization; table offsets are zero. Use Per-exam corrections → Advanced: table origin if needed.”

---

## Phase 2: Interactive Offset Adjustment in Geometry Tab (single-exam)

**Goal:** Adjust **patient** offsets from the Geometry 3D view with live preview. Eliminates Settings → Geometry round-trip. **Single-exam workflow only** — see “Multi-exam scope” below.

**Prerequisites:** Phase 0.1 (offset reset on file load) and Phase 0.2 (`build_settings` accepts explicit `patient_offset`) must be shipped first.

### Approach

Three sliders in Geometry tab, directly bound to the global `state.d_lon/ver/lat`. NiceGUI reactive binding — no “Apply” step. Same backing values as the Settings tab Patient Offsets spinboxes (`settings.py:63-71`); writing either surface updates both.

Track the **last rendered preview mode** (`plot_setup` | `plot_event` | `plot_procedure`) and the last event index so debounced live preview re-invokes the same view the user was looking at.

### Layout

```
geometry.py (controls row, after existing):

  [Event #]  [Setup]  [Single event]  [Full procedure]

  ── Interactive offset (cm) ─────────────────────────────  NEW (single-exam only)
      [Longitudinal slider: -50 ───●──── 50]               NEW
      [Vertical slider:    -50 ───●──── 50]               NEW
      [Lateral slider:     -50 ───●──── 50]               NEW
      [Reset] [Live preview ☑]                             NEW
```

### Behavior

- Sliders directly bound to `state.d_lon/ver/lat`.
- Value text next to each slider (mono font, same pattern as the k_tab slider label in `settings.py:89`).
- Range: ±50 cm (matches `_per_exam.py:160-161`).
- **Do not** attach `reset_results` to slider `on_value_change` — live scrubbing is exploratory; stale PSD until the user recalculates is acceptable.
- **Reset button:** set all three globals to `0.0` **and** call `reset_results()` (match Settings spinbox semantics for an intentional offset clear).
- **Live preview checkbox:** when checked, slider changes trigger geometry re-render via debounced handler (see below). When unchecked, no re-render — user must click “Single event” or “Full procedure”.
- **Debounce:** slider `on_value_change` handler uses a module-level timer variable + `ui.timer(0.25, callback=render, once=True)`, stopping any previous in-flight timer before starting a new one. Prevents flooding the render pipeline with ±50 cm × 100 steps per slider. **Do not** use `ui.timer(0.25, render)` alone — that creates a **recurring** timer (one per change), not a one-shot debounce. The codebase already uses the `once=True` form elsewhere (`tabs/results.py:240`).
- **No dose recalculation.** Sliders trigger only the last-used preview function (`preview_setup` / `preview_event` / `preview_procedure`), never `run_calculation()`.
- Sliders affect the **currently displayed plot mode** (Setup/Single/Full), not a specific button.
- `make_geometry_fig()` uses `effective_patient_offset_for_preview(state)` via `build_settings(..., patient_offset=...)`. In single-exam mode, preview and dose map always agree.

### Multi-exam scope

In multi-exam mode (`state.is_multi_exam`), the Geometry tab sliders are **hidden** (or shown disabled with a tooltip: “Multi-exam: edit per-exam offsets in Settings → Per-exam corrections”). Per-exam offset editing in multi-exam mode stays the responsibility of the existing `_per_exam.py:155-166` spinboxes. Geometry preview in multi-exam continues to use the **global** offset (Phase 0.2 helper); per-exam preview alignment is deferred until `active_exam_index` exists.

### Files changed

- `src/mypyskindose/gui/tabs/geometry.py`

### Decisions

- Range: ±50 cm (matches existing per-exam range).
- Value text: yes, mono font next to each slider.
- Affects all plot modes, not just “Single event”.
- Sliders hidden in multi-exam mode (per-exam editing handled by `_per_exam.py`).
- Multi-exam slider support deferred (requires `active_exam_index` infrastructure).

---

## Phase 3: Visual Feedback — Offset Arrow in Geometry View (deferred)

**Goal:** Show patient offset as visual indicator in 3D plot (arrow or marker).

### Future implementation

1. In `make_geometry_fig`, after building the figure, when `effective_patient_offset_for_preview(state)` is non-zero, add a `go.Scatter3d` arrow trace from phantom origin to offset position (reuse offset already passed into `build_settings` — no second offset parameter).
2. Label: “Δlon=5, Δver=0, Δlat=3 cm”.

### Files changed (future)

- `src/mypyskindose/gui/figures.py`
- `src/mypyskindose/gui/tabs/geometry.py` (checkbox)

### Decisions

- Toggleable via “Show offset arrow” checkbox.
- Deferred until Phase 1–2 interaction model is validated.

---

## File Structure

```
src/mypyskindose/gui/
├── tabs/
│   ├── settings.py          # Phase 1: table offset display, label rename
│   ├── geometry.py          # Phase 2: interactive offset sliders
│   ├── upload.py            # Phase 0.1: clear_all_exams offset reset
│   └── _per_exam.py         # (existing) no changes needed
├── helpers.py               # Phase 0.1 (load functions) + Phase 0.2 (build_settings + preview helper)
├── figures.py               # Phase 0.2 (call-site update) + Phase 3 (deferred arrow)
└── state.py                 # (existing) no changes needed

docs/source/gui_help/
└── positioning_offsets.md   # Phase 2: mention Geometry sliders (sync via scripts/sync_gui_help.py)
```

---

## Documentation & changelog (per PR)

When shipping each phase (or the full plan in one PR):

- Add a `CHANGELOG.md` entry under **Unreleased** (GUI / offsets).
- Update `docs/source/gui_help/positioning_offsets.md` for Phase 2 (Geometry sliders workflow); run `scripts/sync_gui_help.py` — do not edit the mirror under `src/mypyskindose/gui/help/` directly.
- No `AGENTS.md` change required unless behavior crosses a bullet already listed there; optional one-line mention under GUI focus when Phase 2 ships.

---

## TO_DO.md Items Linked

- [ ] Allow manual interactive setting of table offsets in GUI — **Phase 2 (patient offsets in Geometry tab; rename/clarify TO_DO wording when closing)**.
- [ ] Settings tab: show Table Offsets (read-only) and Patient Offsets (adjustable) — **Phase 1**.

---

## Priority

1. **Phase 0** — Prerequisites: offset reset on file load + `build_settings` accepts `patient_offset`. Required for Phases 1 and 2 to behave correctly.
2. **Phase 1** — Display table offsets (highest impact, zero UX risk).
3. **Phase 2** — Interactive single-exam sliders (solves round-trip problem, moderate complexity).
4. **Phase 3** — Offset arrow (nice-to-have, deferred).

---

## Testing

- **Unit tests (recommended for Phase 0):** Add cases in `tests/unittests/test_multi_exam.py` or a small `test_gui_offset_reset.py` — load twice / `clear_all_exams` / `replace_existing=True` does not zero globals. GUI smoke (`tests/gui/test_gui_smoke.py`) unchanged unless new labels are asserted.
- **Phase 0 prerequisites:**
  - 0a. Load RDSR, adjust offsets in the Settings spinboxes, then load a second RDSR → the **global** offsets (Settings spinboxes) snap to 0. (Per-exam meta for exam A is preserved; see 0d.)
  - 0b. Load RDSR, adjust offsets, then “Clear all” → offsets snap to 0.
  - 0c. Load RDSR, then load tabular (or vice versa) → offsets snap to 0 on each **new** load.
  - 0d. In multi-exam mode, adjust per-exam offsets on exam A, then load exam B → A's per-exam `meta[d_lon/ver/lat]` is **preserved**, and B's per-exam offsets default to 0.0 (the new global value).
  - 0e. **Single-exam:** geometry preview matches dose map for the same offset values (adjust global offset, preview, calculate, compare phantom placement to dose accumulation).
  - 0f. **Multi-exam (known limitation):** geometry preview uses global offset; per-exam dose uses `loaded_exam_meta` — document until `active_exam_index` ships. No false pass on 0e for multi-exam.
  - 0g. Re-parse same tabular file with `replace_existing` (schema/sheet change) → global patient offsets **unchanged**.
- **Phase 1 manual tests:**
  1. Load RDSR → table offsets displayed in Settings with correct values.
  2. Load tabular file → offsets show (0, 0, 0) with tabular note.
  3. Load RDSR with fallback normalization → warning badge appears.
  4. Multi-exam: load two DICOM files → caption notes values are from last load.
  5. **Regression:** Data tab export → table offsets still in metadata.
- **Phase 2 manual tests (single-exam workflow):**
  6. Adjust Geometry sliders → live preview updates plot (debounced), same mode as last preview button.
  7. Adjust Settings spinboxes → Geometry sliders update (shared `state.d_lon/ver/lat`); Settings still calls `reset_results`.
  8. Reset button → sliders zero **and** results cleared (`reset_results`).
  9. Slider scrubbing alone → no `reset_results` / no auto dose run.
  10. Live preview off → slider changes don't update plot; manual mode switch does.
  11. In multi-exam mode, Geometry sliders are hidden (or disabled with tooltip).
  12. Single-exam: geometry preview matches dose map for same offsets (extends 0e).

---

## Dependencies

- Depends on: `state.d_lon/ver/lat`, `state.table_offset_x/y/z`, `make_geometry_fig`, `rdsr_normalizer()` table offset computation.
- **Phase 1 and Phase 2 depend on Phase 0** (offset reset on file load + `build_settings` accepts `patient_offset`).
- Blocks nothing (additive UX, non-breaking for existing workflows).

---

## Exit criteria (plan lifecycle)

Archive to `dev-docs/plans/archive/` when Phases 0–2 are shipped and manual tests pass. Phase 3 may remain deferred. On archive: update `dev-docs/index.md`, `dev-docs/plans/archive/README.md`, and `TO_DO.md` (check off items, clarify “table offsets” TO_DO wording).

---

## Future Considerations

- **Multi-exam slider support in Geometry tab.** Requires (a) a real exam selector widget (dropdown or radio) that drives `state.active_exam_index`, (b) `effective_patient_offset_for_preview` reading `loaded_exam_meta[active]`, and (c) explicit unbind/rebind logic in the slider handler on exam switch (NiceGUI's `bind_value` is to a specific dict reference, not a key path).
- Extend interactive adjustment to **table-origin override** (currently per-exam only). “Set table origin from click” in Geometry.
- **Preset offset profiles** (cardiac, head/neck, abdominal) as dropdown in Settings.
- **Offset snapping** to clinical positions (gantry angle zero, table mid-position).
