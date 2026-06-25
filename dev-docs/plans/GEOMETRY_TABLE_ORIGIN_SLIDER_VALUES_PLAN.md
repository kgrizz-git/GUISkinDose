# Show Geometry table-origin slider value labels

> **TO_DO item:** "Show Geometry table-origin slider values — mirror patient-offset value labels for table-origin X/Y/Z."

## Objective

Display live value labels (e.g. "3.5 cm") beneath each table-origin slider (X, Y, Z), matching the pattern used for patient-offset sliders.

## Acceptance criteria

- [ ] Each table-origin slider (X, Y, Z) has a `ui.label` beneath it showing the current value formatted as `"{value:.1f} cm"`.
- [ ] Labels update on every slider tick (same mechanism as `_on_patient_slider_change` → `patient_val_labels[attr].set_text(...)`).
- [ ] Labels update when sliders are synced from metadata (`_sync_table_sliders_from_meta`).
- [ ] Labels update when table origin is reset (`_reset_table_origin`).
- [ ] Labels update when exam selector changes (`_sync_table_sliders_from_meta` called via `_refresh_geometry_sliders`).
- [ ] After switching exams in multi-exam mode, table-origin value labels reflect the new exam's table origin values.
- [ ] Labels use the same CSS classes as patient value labels: `text-caption mono-text`.

## Implementation plan

### 1. Create value label dicts for table sliders

After `table_sliders: dict[str, ui.slider] = {}` (near line 227), add:

```python
table_val_labels: dict[str, ui.label] = {}
```

### 2. Add value labels in the slider row

In the `with ui.row().classes("w-full gap-4 items-center"):` block (near line 266), after each slider is created and before `slider.on_value_change(...)` (near line 310), add:

```python
val_label = ui.label(f"{initial:.1f} cm").classes("text-caption mono-text")
table_val_labels[key] = val_label
```

### 3. Update `_sync_table_sliders_from_meta` to update value labels

In `_sync_table_sliders_from_meta` (near line 241), after `slider.set_value(origin[key])` (near line 263), add:

```python
table_val_labels[key].set_text(f"{origin[key]:.1f} cm")
```

### 4. Update `_on_table_slider` to update value label

In `_on_table_slider` (near line 291), after the existing logic (near line 308), add. The existing lambda at line 310 already captures loop variables via `k=key, s=slider` — use the same pattern:

```python
table_val_labels[k].set_text(f"{float(s.value or 0.0):.1f} cm")
```

### 5. Update `_reset_table_origin` to sync value labels

`_reset_table_origin` already calls `_sync_table_sliders_from_meta(idx)` (near line 479), which now updates value labels — no additional change needed.

## Test coverage

Unit tests are deferred. `table_val_labels` is a local closure dict inside `build()` — testing it would require either extracting it to `state.py` (overkill for this feature) or using NiceGUI fixture testing (not yet established). Manual verification is sufficient given the pattern parity with patient value labels (already tested via multi-exam geometry offset tests).

## Files to modify

- `src/mypyskindose/gui/tabs/geometry.py` — only file to modify

## Notes

- `_per_exam.py` table-origin section (spinboxes) already shows formatted values via `format="%.1f"` on the number inputs — no changes needed there.
- `_on_composite_toggle` does NOT call `_sync_table_sliders_from_meta` — this is correct because composite mode changes the preview events, not slider values.

## Progress

- [x] Plan written
- [x] Review (2026-06-25)
- [ ] Implementation
