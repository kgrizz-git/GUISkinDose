# Slider Label Reposition Plan

**Source:** [`dev-docs/TO_DO.md`](../TO_DO.md), line 60–61.

---

## Objective

Reposition value labels on the **Geometry tab sliders** so they sit **adjacent to their slider** (on the same horizontal line) instead of one row below.

## Affected file

- `src/mypyskindose/gui/tabs/geometry.py`

> **Note on line numbers:** the references below match the file as of this writing. If the file is modified before implementation, use the code patterns (outer `ui.row` → per-axis `ui.column`, function names) as anchors, not the numeric lines.

## Current layout (stacked)

Both slider groups use an identical `ui.row` → per-axis `ui.column` → (label / slider / value) structure. The label sits above the slider and the value sits below.

## Target layout (adjacent)

Replace the outer 3-axis `ui.row` **and** the per-axis `ui.column` with one `ui.row` per axis that holds (label, slider, value) horizontally.

| Aspect | Before | After |
|--------|--------|-------|
| Outer container | `ui.row().classes("w-full gap-4 items-center")` (all 3 axes) | **Removed** — each axis is self-contained |
| Per-axis container | `ui.column().classes("grow gap-1")` (vertical stack) | `ui.row().classes("w-full gap-2 items-center flex-nowrap")` |
| Label class | `text-caption text-grey-6` | `w-24 text-caption text-grey-6` — fixed width prevents layout shift |
| Slider class | `w-full` | `grow min-w-[100px]` — fills space; defensive min-width floor |
| Value label class | `text-caption mono-text` | `w-20 text-caption mono-text text-right` — fixed width + right-aligned (see AC4) |

## Implementation steps

### Step 1 — Patient offset sliders (around line 161)

Replace the outer `ui.row` + per-axis `ui.column` block with a per-axis `ui.row`:

```python
for axis, lbl, attr in (("lon", "Longitudinal", "d_lon"), ("ver", "Vertical", "d_ver"), ("lat", "Lateral", "d_lat")):
    with ui.row().classes("w-full gap-2 items-center flex-nowrap"):
        ui.label(lbl).classes("w-24 text-caption text-grey-6")
        initial = read_patient_offset_value(state, attr)
        slider = ui.slider(
            min=-PATIENT_OFFSET_SLIDER_RANGE_CM,
            max=PATIENT_OFFSET_SLIDER_RANGE_CM,
            step=0.5,
            value=initial,
        ).classes("grow min-w-[100px]").mark(f"patient-slider-{axis}")
        val_label = ui.label(f"{initial:.1f} cm").classes("w-20 text-caption mono-text text-right")
        patient_sliders[attr] = slider
        patient_val_labels[attr] = val_label
```

### Step 2 — Table origin override sliders (around line 269)

Remove the outer `ui.row()` and dedent its contents (pre-loop `idx0`/`meta0`/`detected0`/`origin0` plus the `for key in ("x", "y", "z"):` loop). Replace the per-axis `ui.column()` with `ui.row()`:

```python
idx0 = _active_exam_index()
meta0 = state.loaded_exam_meta[idx0] if idx0 < len(state.loaded_exam_meta) else {}
detected0 = meta0.get("table_origin_detected") or {"x": 0.0, "y": 0.0, "z": 0.0}
origin0 = effective_table_origin(meta0) if meta0 else detected0
for key in ("x", "y", "z"):
    with ui.row().classes("w-full gap-2 items-center flex-nowrap"):
        ui.label(key.upper()).classes("w-24 text-caption text-grey-6")
        lo, hi = _table_slider_limits(detected0, key)
        initial = float(origin0.get(key, 0.0))
        slider = ui.slider(
            min=lo,
            max=hi,
            step=0.5,
            value=initial,
        ).classes("grow min-w-[100px]").mark(f"table-slider-{key}")
        val_label = ui.label(f"{initial:.1f} cm").classes("w-20 text-caption mono-text text-right")
        table_val_labels[key] = val_label

        def _on_table_slider(e, k=key, s=slider) -> None:
            ...  # callback body unchanged
        slider.on_value_change(_on_table_slider)
        table_sliders[key] = slider
```

`_on_table_slider` and `slider.on_value_change(...)` stay **inside** the `with ui.row()` block — they are Python function defs and method calls, not DOM children, so the container change is harmless. **Do not move them out** — that would break closure scope and `table_sliders[key] = slider` placement.

Note: because the inner container changes from `with ui.column():` to `with ui.row():`, the `def _on_table_slider(...)` body and `slider.on_value_change(...)` call will be **dedented by 4 spaces** (one level) compared to their current position. The logical body is identical.

### Container cards and visibility bindings — unchanged

`patient_offset_card`, `table_origin_card`, their visibility bindings, badges, captions, and reset buttons are not modified. `_table_origin_card_visible()` is unaffected.

### Step 3 — Add index entry (follow-up)

Add a row to the `## Execution plans` table in `dev-docs/index.md`. The link target (relative to `dev-docs/index.md`) is `plans/SLIDER_LABEL_REPOSITION_PLAN.md` and the description is "Reposition slider value labels adjacent to the slider on the Geometry tab." Wrap the path as a markdown link using the same format as the other rows in that table (e.g. the `plans/INTERACTIVE_TABLE_OFFSETS_PLAN.md` row above).

Without this, `python scripts/check_doc_freshness.py` and `scripts/check_agent_guidance.py` won't see the new plan.

> **Note on the code block:** the verbatim index row cannot be embedded in this plan as a markdown code block — `scripts/check_doc_freshness.py` scans all lines (including fenced code blocks) for relative links, and any such link inside the plan would resolve against the plan's own path and trigger a broken-link error. Describe the entry textually instead, as above.

## Value update code — no structural change needed

Value labels are updated via `.set_text()` on the same `patient_val_labels[attr]` / `table_val_labels[key]` dict entries; only the container around the slider/label changes.

The patient slider callback `_on_patient_slider_change` is defined and wired **outside** the slider group. The wiring loop iterates `patient_sliders` after the group is built:

```python
for attr, slider in patient_sliders.items():
    slider.on_value_change(lambda _e, a=attr, s=slider: _on_patient_slider_change(a, s))
```

The table-origin callback `_on_table_slider` is defined and wired **inside** the per-axis `with ui.row()` block (closure capture of `key` and `slider`). `_sync_table_sliders_from_meta` mutates `slider._props["min"]`/`["max"]` and calls `slider.update()` directly; unaffected by the container change.

| Callback | `set_text` anchor (function body) |
|----------|-----------------------------------|
| `_on_patient_slider_change` | `patient_val_labels[attr].set_text(...)` inside function body |
| `_sync_patient_sliders_from_meta` | `patient_val_labels[attr].set_text(...)` inside sync loop |
| `_on_table_slider` (closure) | `table_val_labels[k].set_text(...)` inside closure body |
| `_sync_table_sliders_from_meta` | `table_val_labels[key].set_text(...)` inside sync loop; also `_props` + `update()` |

> **Do not switch the patient slider group to `bind_text_from(state, attr)`.** In multi-exam mode the Geometry patient sliders are per-exam, not global — they read/write `state.loaded_exam_meta[active_index][attr]` via `read_patient_offset_value` / `apply_patient_offset_slider_tick` (`offset_handlers.py:49-75`), not `state.d_lon` / `state.d_ver` / `state.d_lat`. A `bind_text_from(state, "d_lon")` would show the global value (last-loaded exam's offset) instead of the active exam's offset, regressing the multi-exam workflow. The manual `.set_text()` calls in the four callbacks above are required.

## Acceptance criteria

1. Patient offset sliders (lon/ver/lat): value label appears on the same row as the slider, not below.
2. Table origin override sliders (x/y/z): value label appears on the same row as the slider, not below.
3. Value updates (slider drag, sync from exam switch, reset) continue to show correct values in the repositioned label.
4. Visual spacing is reasonable on a typical viewport:
   - Labels are fully readable (not clipped or overlapping).
   - Slider track is at least 100 px wide.
   - **Value label fits without overflow.** Width math: `text-caption` (~12 px) + format `f"{value:.1f} cm"`; longest realistic string is `-250.0 cm` (9 chars, table-origin at extreme). `w-20` (80 px) gives ~10–20 px headroom. `w-16` (64 px) would overflow at the table-origin extremes — do not shrink to `w-16`.
   - Visible gap between the slider and the value label.
5. No regression in Settings tab slider labels (those are already adjacent — `settings.py:181`).

## Decisions log

All resolved during drafting. Recorded so reviewers see the rationale.

- **`gap-2` vs `gap-4`:** per-axis rows are narrower (one axis) than Settings tab rows (`settings.py:181`, which use `gap-4` with a 192 px label). `gap-2` reads tighter; bump to `gap-4` if it feels cramped in review.
- **Label width (`w-24`):** "Longitudinal" (13 chars) at `text-caption` renders ~75–85 px; `w-24` (96 px) gives ~10–20 px margin. If clipping appears, increase to `w-28` (112 px). Do not switch to `text-xs` — would mismatch the design token used by every other slider label.
- **Table label width (`w-24` for "X"/"Y"/"Z"):** keeps the three table sliders vertically aligned with the patient sliders above. If the whitespace feels excessive in review, drop table labels to `w-16`.
- **Slider min-width (`min-w-[100px]`):** defensive floor against `grow` shrinking the track to 0 on narrow viewports. Not critical given `max-w-6xl` on the outer column.
- **Intra-row wrapping (`flex-nowrap`):** prevents label/slider/value from wrapping onto multiple lines on narrow screens, which would defeat the adjacent-label goal.
- **Pre-loop variables (Step 2):** `idx0`/`meta0`/`detected0`/`origin0` dedent one level when the outer `ui.row()` is removed. They remain before the loop, now at the `with table_origin_card:` indentation level.
- **Multi-exam impact:** three per-axis rows add vertical height in multi-exam mode vs. the current 3-column row (~60–80 px per card). The cards are at the top of the geometry tab above the button row and the 700 px plot, so they remain visible on a default-height viewport; the plot is what gets pushed down by vertical overflow. No layout mitigation is required. (Earlier draft proposed swapping card order as a fallback; that would have pushed the more universally-visible patient card *down* whenever the table-origin card is visible — the opposite of the goal. Discarded.)
- **Existing test markers:** `tests/gui/test_gui_flows.py` uses `patient-slider-{lon,ver,lat}` and `table-slider-x` markers via `_set_slider_value`. All `.mark(...)` calls are preserved, so render-loop tests stay green without modification.

## Out of scope

- CSS changes (all positioning via Tailwind/Quasar utility classes).
- The `mono-text` and `technical-label` utility classes are inert (no CSS rule in `styles.py`, `app.py`, or `docs/source/_static/my-styles.css`, and not a standard Tailwind/Quasar class). Kept in value labels for forward compatibility.
- Switching the patient slider group to `bind_text_from` (would regress multi-exam; see note above).
