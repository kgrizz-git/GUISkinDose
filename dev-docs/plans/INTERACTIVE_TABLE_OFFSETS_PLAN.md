# Interactive Table Offsets & Settings Display Plan

## Overview

Two TO_DO items address gaps in how table offsets are exposed and adjusted in the GUI:

1. **Interactive table offset setting in Geometry tab** — adjust offsets directly in the 3D view rather than only through Settings spinboxes.
2. **Settings tab: show Table Offsets (read-only) and Patient Offsets (adjustable)** — display auto-detected values and distinguish them from user-adjustable offsets.

Both share `state.table_offset_*` (auto-detected) and `state.d_lon/ver/lat` (patient offsets).

---

## Current State

### Existing

- **Table offsets:** computed by `rdsr_normalizer()`, stored in `state.table_offset_x/y/z` (`helpers.load_rdsr:174-176`). Values from vendor scanner convention (`normalization_settings.trans_offset`).
- **Patient offsets:** global spinboxes in Settings tab (`settings.py:61-71`).
- **Per-exam patient offsets:** `state.loaded_exam_meta[*][d_lon/ver/lat]` in `_per_exam.py`.
- **Table-origin override:** `_per_exam.py` "Advanced: table origin" — per-axis spinboxes that re-base table positions. Phase 1's read-only table offset display complements this existing override (not a replacement).
- **Geometry tab:** renders 3D views but has no offset controls.
- **Help:** `src/mypyskindose/gui/help/positioning_offsets.md` explains offset semantics.

### Missing

- Table offsets visible only during Data tab export (`data.py:62-64`), not in Settings or Geometry.
- No interactive offset adjustment from Geometry tab.
- Settings tab conflates table offsets and patient offsets visually.
- No visual offset indicator in Geometry 3D view.

---

## Phase 1: Display Table Offsets in Settings Tab

**Goal:** Show auto-detected table offset values in Settings → Phantom Settings.

### Changes

1. **Add read-only "Table Offsets (auto-detected)" display** in Phantom Settings expansion, above patient offset spinboxes.
   - Three read-only labels: `table_offset_x`, `table_offset_y`, `table_offset_z` with units (cm).
   - Info icon/tooltip: "Vendor-specific table coordinate origin from RDSR normalization. Read-only; adjust patient offsets below."
   - **Fallback badge:** Show amber warning if `state.normalization_warnings` is non-empty (same condition as `helpers.load_rdsr:178-181`: `state.normalization_method == "Fallback"`). Do not re-implement detection logic.
   - Location: `settings.py`, Phantom Settings expansion, after "Phantom model and positioning" row, before patient offset spinboxes.

2. **Rename label** above existing spinboxes to "Patient Offsets (adjustable, cm)".

3. **Multi-exam note:** When per-exam corrections visible (multi-exam mode), note if a per-exam table-origin override is active (amber badge style, same as `_per_exam.py:144-147`).

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
      [⚠ Fallback: scanner model not matched]              NEW (conditional on state.normalization_warnings)

  ── Patient Offsets (adjustable, cm) ────────────────────  Renamed
      [Longitudinal] [Vertical] [Lateral]
```

### Files changed

- `src/mypyskindose/gui/tabs/settings.py`

### Decisions

- Display always visible but compact (no expansion).
- Tabular inputs: show (0, 0, 0) with note "No RDSR data loaded — table offsets are zero for tabular inputs."

---

## Phase 2: Interactive Offset Adjustment in Geometry Tab

**Goal:** Adjust patient offsets from Geometry 3D view with live preview. Eliminates Settings → Geometry round-trip.

### Approach

Three sliders in Geometry tab, directly bound to `state.d_lon/ver/lat`. NiceGUI reactive binding — no "Apply" step.

### Layout

```
geometry.py (controls row, after existing):

  [Event #]  [Setup]  [Single event]  [Full procedure]

  ── Interactive offset (cm) ─────────────────────────────  NEW
      [Longitudinal slider: -50 ───●──── 50]               NEW
      [Vertical slider:    -50 ───●──── 50]               NEW
      [Lateral slider:     -50 ───●──── 50]               NEW
      [Reset] [Live preview ☑]                             NEW
```

### Behavior

- Sliders directly bound to `state.d_lon/ver/lat`.
- Value text next to each slider (mono font, like `settings.py:89`).
- Range: ±50 cm (matches `_per_exam.py:161`).
- **Live preview checkbox:** when checked, slider changes trigger geometry re-render via debounced handler (see below). When unchecked, no re-render — user must click "Single event" or "Full procedure".
- **Debounce:** slider `on_value_change` handler uses `ui.timer(0.25, ...)` to debounce re-renders at ~250ms. Prevents flooding the render pipeline with ±50 cm × 100 steps per slider.
- **No dose recalculation.** Sliders trigger only `preview_event()` (geometry re-render), never `reset_results()`. Dose recalculates only on Calculate tab navigation or explicit request.
- **Reset** sets all sliders to zero.
- Sliders affect the **currently displayed plot mode** (Setup/Single/Full), not a specific button.
- `preview_event()` internally calls `build_settings(state, ...)` which reads current `state.d_lon/ver/lat`, so offset changes propagate to the plot.

### Multi-exam behavior

Sliders bind to **per-exam** offsets (`state.loaded_exam_meta[state.active_exam_index][d_lon/ver/lat]`) in multi-exam mode, matching `_per_exam.py` behavior.

- On exam switch (event selection or exam selector), sliders re-bind to the new exam's per-exam values.
- Uninitialized per-exam offsets default to **0.0** (matches `_per_exam.py:156` `meta.setdefault(axis, 0.0)`). This is distinct from the global `state.d_lon/ver/lat`.
- Per-exam offsets stored in `loaded_exam_meta[i][d_lon/ver/lat]` (same dict as `_per_exam.py`).

### Files changed

- `src/mypyskindose/gui/tabs/geometry.py`

### Decisions

- Range: ±50 cm (matches existing per-exam range).
- Value text: yes, mono font next to each slider.
- Affects all plot modes, not just "Single event".

---

## Phase 3: Visual Feedback — Offset Arrow in Geometry View (deferred)

**Goal:** Show patient offset as visual indicator in 3D plot (arrow or marker).

### Future implementation

1. Update `make_geometry_fig` signature: add `patient_offset: tuple[float, float, float] | None = None`.
2. When non-zero, add `go.Scatter3d` arrow trace from phantom origin to offset position.
3. Label: "Δlon=5, Δver=0, Δlat=3 cm".

### Files changed (future)

- `src/mypyskindose/gui/figures.py`
- `src/mypyskindose/gui/tabs/geometry.py`

### Decisions

- Toggleable via "Show offset arrow" checkbox.
- Deferred until Phase 1–2 interaction model is validated.

---

## File Structure

```
src/mypyskindose/gui/
├── tabs/
│   ├── settings.py          # Phase 1: table offset display, label rename
│   ├── geometry.py          # Phase 2: interactive offset sliders
│   └── _per_exam.py         # (existing) no changes needed
├── figures.py               # Phase 3 (deferred)
└── state.py                 # (existing) no changes needed
```

---

## TO_DO.md Items Linked

- [ ] Allow manual interactive setting of table offsets in GUI — Phase 2.
- [ ] Settings tab: show Table Offsets (read-only) and Patient Offsets (adjustable) — Phase 1.

---

## Priority

1. **Phase 1** — Display table offsets (highest impact, zero UX risk).
2. **Phase 2** — Interactive sliders (solves round-trip problem, moderate complexity).
3. **Phase 3** — Offset arrow (nice-to-have, deferred).

---

## Testing

- **Unit tests:** None (covered by GUI smoke tests).
- **Manual tests:**
  1. Load RDSR → table offsets displayed in Settings with correct values.
  2. Load tabular file → offsets show (0, 0, 0) with note.
  3. Load RDSR with fallback normalization → warning badge appears.
  4. Adjust Geometry sliders → live preview updates plot (debounced).
  5. Adjust Settings spinboxes → Geometry sliders update (direct binding).
  6. Multi-exam → per-exam offsets and global offset interaction works.
  7. Reset button → all sliders return to zero.
  8. **Regression:** Data tab export → table offsets still in metadata.
  9. Multi-exam exam switch → Geometry sliders update to per-exam offsets.
  10. No dose recalculation → slider changes don't alter dose values.
  11. Live preview off → slider changes don't update plot; manual mode switch does.
  12. Concurrent edits → slider + spinbox changes resolve via NiceGUI binding (last write wins).
  13. Value reset on file load → loading new file resets d_lon/ver/lat to 0; sliders snap to 0 via binding.
  14. Tabular input state reset → loading tabular after RDSR resets offsets to (0,0,0); sliders reflect this.

---

## Dependencies

- Depends on: `state.d_lon/ver/lat`, `state.table_offset_x/y/z`, `make_geometry_fig`, `rdsr_normalizer()` table offset computation.
- Blocks nothing (additive UX, non-breaking for existing workflows).

---

## Future Considerations

- Extend interactive adjustment to **table-origin override** (currently per-exam only). "Set table origin from click" in Geometry.
- **Preset offset profiles** (cardiac, head/neck, abdominal) as dropdown in Settings.
- **Offset snapping** to clinical positions (gantry angle zero, table mid-position).
