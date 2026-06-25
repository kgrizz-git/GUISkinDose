# Show Geometry table-origin slider value labels

> **TO_DO item:** "Show Geometry table-origin slider values — mirror patient-offset value labels for table-origin X/Y/Z."

## Objective

Display live value labels (e.g. "3.5 cm") beneath each table-origin slider (X, Y, Z) in the
**Geometry** tab, matching the existing pattern used for the patient-offset sliders
(`patient_val_labels` in `src/mypyskindose/gui/tabs/geometry.py:159`).

## Acceptance criteria

- [ ] Each table-origin slider (X, Y, Z) has a `ui.label` beneath it showing the current value formatted as `"{value:.1f} cm"`.
- [ ] Labels update on every slider tick (same mechanism as `_on_patient_slider_change` → `patient_val_labels[attr].set_text(...)`).
- [ ] Labels update when sliders are synced from metadata (`_sync_table_sliders_from_meta`).
- [ ] Labels update when table origin is reset (`_reset_table_origin` → `_sync_table_sliders_from_meta(idx)`).
- [ ] Labels update when exam selector changes (`_sync_table_sliders_from_meta` called via `_refresh_geometry_sliders`).
- [ ] After switching exams in multi-exam mode, table-origin value labels reflect the new exam's table origin values.
- [ ] Labels use the same CSS classes as patient value labels: `text-caption mono-text`.

## Implementation plan

### 1. Create value label dict for table sliders

After `table_sliders: dict[str, ui.slider] = {}` at `src/mypyskindose/gui/tabs/geometry.py:227`, add:

```python
table_val_labels: dict[str, ui.label] = {}
```

### 2. Add value labels in the slider row

In the `with ui.row().classes("w-full gap-4 items-center"):` block at
`src/mypyskindose/gui/tabs/geometry.py:266`, inside the `for key in ("x", "y", "z"):` loop,
after the `ui.slider(...)` is created (line 284) and before `slider.on_value_change(...)`
(line 310), add:

```python
val_label = ui.label(f"{initial:.1f} cm").classes("text-caption mono-text")
table_val_labels[key] = val_label
```

This mirrors the patient-offset pattern at `src/mypyskindose/gui/tabs/geometry.py:175-177`.

### 3. Update `_sync_table_sliders_from_meta` to update value labels

In `_sync_table_sliders_from_meta` (line 241), inside the `for key, slider in table_sliders.items():` loop,
after `slider.set_value(origin[key])` (line 263), add:

```python
table_val_labels[key].set_text(f"{origin[key]:.1f} cm")
```

This ensures labels refresh when the active exam changes or after `reset_results()` /
`_refresh_geometry_sliders()` re-syncs sliders from metadata.

### 4. Update `_on_table_slider` to update value label on tick

In `_on_table_slider` (line 291), after the existing `stage_table_origin_axis(...)` call and
before `_schedule_debounced_render()` (line 308), add:

```python
table_val_labels[k].set_text(f"{float(s.value or 0.0):.1f} cm")
```

The closure already captures `k=key` and `s=slider` via the default-argument pattern at line 291.

### 5. `_reset_table_origin` requires no change

`_reset_table_origin` (line 463) already calls `_sync_table_sliders_from_meta(idx)` at line 479,
which (after step 3) updates value labels — no additional change needed.

## Test coverage

Unit tests are deferred. `table_val_labels` is a local closure dict inside `build()` — testing it
would require either extracting it to `state.py` (overkill for this feature) or establishing
NiceGUI fixture testing (not yet in place). Manual verification is sufficient given the
pattern parity with `patient_val_labels`, which is already exercised by the multi-exam
geometry offset tests.

## Files to modify

- `src/mypyskindose/gui/tabs/geometry.py` — only file to modify.

## Notes

- `_per_exam.py` table-origin section (spinboxes) already shows formatted values via
  `format="%.1f"` on the number inputs — no changes needed there.
- `_on_composite_toggle` does NOT call `_sync_table_sliders_from_meta` — this is correct because
  composite mode changes the preview events, not slider values.
- The `table_origin_card` is hidden (`_table_origin_card_visible()`) when the active exam does
  not support table-origin overrides, so the `table_val_labels` dict is only populated when the
  card is visible. No defensive `if key in table_val_labels` checks are needed in the four
  update sites above — they all run in the same code path as the slider itself.
- Pattern parity with patient offsets is intentional: any future visual change to
  `patient_val_labels` (e.g. CSS class tweak) should be applied symmetrically to
  `table_val_labels`.

## Review notes (2026-06-25)

Reviewed against `src/mypyskindose/gui/tabs/geometry.py` (603 lines). All line references
verified accurate. Plan is structurally sound: it mirrors the existing
`patient_val_labels` pattern exactly, and the only "update" sites that need to set text are
the four that already manage slider state (`_sync_table_sliders_from_meta`,
`_on_table_slider`, `_reset_table_origin` via the sync function, and `_refresh_geometry_sliders`
via the sync function).

## Interaction with other plans

- **`dev-docs/plans/archive/GEO_TAB_SPINNING_WHEEL_PLAN.md` (shipped 2026-06-25)** — adds
  `_in_render_chain` guard around the re-schedule at the end of `_refresh_geometry_sliders`,
  adds `.mark(...)` to both patient and table-origin sliders, and removes the redundant
  local schedule block in `_on_exam_select_change`. None of those changes touch the four
  edit sites in this plan, so no functional updates are required. Two minor consequences:
  1. The acceptance-criterion rationale for "labels update when exam selector changes"
     becomes stronger: with the redundant local block gone, the only path for value
     labels to refresh on exam change is `ctx.refresh_per_exam()` → `_refresh_geometry_sliders()`
     → `_sync_table_sliders_from_meta()`. This is exactly the path step 3 covers, so
     step 3 is the **sole** guarantee for that acceptance criterion.
  2. Line numbers verified against the current 607-line file: `_on_table_slider` is
     still defined starting at line 291, `slider.on_value_change(_on_table_slider)` is
     now at line 311 (was 310), and `_reset_table_origin` is still at line 463. The
     small +4 line offset is consistent across the file.

Gaps and nits addressed in this revision:

1. The original step 5 said `_reset_table_origin` is at "near line 479" — that is actually
   the call site for `_sync_table_sliders_from_meta(idx)`; the function itself starts at
   line 463. Corrected.
2. The original acceptance criterion wording for `_reset_table_origin` did not call out
   that the update flows through `_sync_table_sliders_from_meta(idx)`; tightened the text
   and the "no change needed" note in step 5 to make that explicit.
3. Added a Notes bullet confirming no defensive `if key in table_val_labels` is required
   (the card is hidden when the dict would be unpopulated).
4. Promoted the line references in steps 1–4 from "near line N" to anchored line numbers
   (`src/mypyskindose/gui/tabs/geometry.py:N`) so the plan is robust to small refactors
   that add or remove lines above each call site.
5. Added a pattern-parity Note reminding future contributors to apply symmetric CSS
   changes if `patient_val_labels` styling is ever updated.

No functional changes were made to the plan — the four edit sites and the dict
initialization are correct as written.

## Progress

- [x] Plan written
- [x] Review (2026-06-25)
- [x] Cross-check against `GEO_TAB_SPINNING_WHEEL_PLAN.md` (shipped) — no functional
      updates needed; interaction notes added.
- [x] Implementation (2026-06-25) — `table_val_labels` dict, initial labels, and
      `set_text` calls added at the four planned sites in `geometry.py`. ruff,
      basedpyright, `scripts/check_file_sizes.py`, and the 13-test GUI suite all pass.
      `dev-docs/TO_DO.md` line 47 marked done.
