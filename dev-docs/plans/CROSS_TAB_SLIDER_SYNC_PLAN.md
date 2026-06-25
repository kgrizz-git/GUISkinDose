# Plan: Cross-tab Offset/Origin Slider Synchronization

> **Status:** COMPLETED (2026-06-25)
> **Blocker:** ~~Must wait for completion of `dev-docs/plans/GEOMETRY_TABLE_ORIGIN_SLIDER_VALUES_PLAN.md` before implementation (to ensure table-origin value labels exist).~~ (resolved — value labels shipped separately)
>
> **Objective:** Fix the cross-tab synchronization limitation where editing table origin or patient offsets via spinboxes on Tab 3 (Settings) does not reliably update the corresponding sliders and value labels on Tab 4 (Geometry).
>
> **Rationale:** The current synchronization relies on a "push" mechanism (`ctx.refresh_per_exam()`) which is inconsistently applied (present for patient offsets, missing for table origin). Navigation via the side drawer also bypasses the `update:model-value` event, meaning tab-change "pull" synchronization wouldn't fire. This plan unifies both push and pull mechanisms so the Geometry tab is always up to date.

## Acceptance criteria

- [ ] Table-origin spinboxes in Tab 3 (Settings -> Per-exam corrections) trigger a per-exam refresh on change and reset, matching the behavior of patient-offset spinboxes.
- [ ] Switching to Tab 4 (Geometry) via the tab strip immediately refreshes the geometry tab content, ensuring sliders, text value labels, and the live preview figure reflect the latest state.
- [ ] Switching to Tab 4 (Geometry) via the left navigation drawer also immediately refreshes the geometry tab content.
- [ ] Switching between any other tabs does not trigger unnecessary geometry tab slider refreshes.
- [ ] *Note: "text value labels" includes patient-offset labels and the table-origin labels (from the prerequisite plan).*

## Implementation plan

### 1. Fix root cause: Add `refresh_per_exam` to table-origin handlers

In `src/mypyskindose/gui/tabs/_per_exam.py`:
- In `_on_change` (near line 108), add `ctx.refresh_per_exam()` at the end of the function.
- In `_on_reset` (near line 121), add `ctx.refresh_per_exam()` at the end of the function.
- **Critical Fix (E3):** Because `refresh()` currently calls `exams_list.clear()` and re-creates every card (line 231), calling `refresh_per_exam()` from within a spinbox change will destroy the active widget tree and close the "Advanced: table origin" expansion panel. Before adding the calls above, refactor `refresh()` to:
  a) **Recommended:** When the only change is a per-axis table-origin value (or the reset), call a new `refresh_table_origin_axis(idx, key)` helper that updates `inputs[key].set_value(new_value)` and `status_label.set_text(_status_text())` *without* clearing `exams_list`. The `inputs` dict already exists in closure scope and persists across re-builds of *other* controls, so this is a one-line addition per spinbox.
  b) **Fallback (more invasive):** Save the `value` (open state) of every `ui.expansion` and the `value` of every coordinate-correction `ui.switch` before `exams_list.clear()`, then restore them after re-mount. Only use this if option (a) turns out to leave stale state in adjacent controls.
- The plan recommends (a) and treats (b) as an escape hatch. The `inputs` dict + `status_label` references in `_build_table_origin_section` are already captured in closure, so updating them post-creation is straightforward.
- *Reconciliation Note:* This unifies table-origin behavior with patient offsets. The existing `refresh_per_exam` wrapping in `geometry.py:596-602` will remain as the primary push-sync mechanism.

### 2. Add tab refresher callback to PageContext

In `src/mypyskindose/gui/page_context.py`:
- Add `refresh_geometry_tab: Callable[[], None] = field(default=_noop)` to the `PageContext` class.
- Add a comment: *"Refresh sliders and captions when the user navigates into this tab. Default no-op — geometry.py wires it on build."*

### 3. Register the callback in Geometry Tab

In `src/mypyskindose/gui/tabs/geometry.py`:
- At the end of `build(ctx: PageContext)` (currently at line 607, immediately after `ctx.refresh_per_exam = _refresh_per_exam_with_sliders`), register the local `_refresh_geometry_sliders` closure:
  ```python
  ctx.refresh_geometry_tab = _refresh_geometry_sliders
  ```
- **Interaction with `GEOMETRY_TABLE_ORIGIN_SLIDER_VALUES_PLAN.md`:** once that plan ships, `_sync_table_sliders_from_meta` (called inside `_refresh_geometry_sliders`) will also update `table_val_labels[key]`. Because step 3 of this plan hooks `_refresh_geometry_sliders` to the tab-change pull, the value labels will refresh on tab entry *for free* — no additional change needed in this plan. This is the reason the plan's blocker on the value-labels plan exists: the cross-tab pull would otherwise re-render the figure but leave the value labels stale.

### 4. Trigger pull synchronization on tab change & nav drawer

In `src/mypyskindose/gui/app.py`:
- Define `_on_tab_changed` at a scope that can close over both `_update_nav_classes` (defined inside the `left_drawer` block, line 88) and `ctx` (defined later, line 127). The cleanest fix is to **move `_update_nav_classes` and `nav_buttons` out of the left_drawer block** to the same nesting level as `_on_tab_changed`, OR define `_on_tab_changed` inside the left_drawer block alongside `_update_nav_classes` and forward it up via a local reference. The plan recommends the former (move out) because it also simplifies the closure mechanics. Sketch:

  ```python
  def _update_nav_classes() -> None:
      for btn, target in nav_buttons:
          if state.active_tab == target:
              btn.classes(add="active", remove="text-grey-4")
          else:
              btn.classes(remove="active", add="text-grey-4")

  nav_buttons: list[tuple[ui.button, str]] = []

  def _on_tab_changed(tab_name: str) -> None:
      state.active_tab = tab_name
      _update_nav_classes()
      if tab_name == "geometry":
          ctx.refresh_geometry_tab()
          ctx.refresh_geometry_preview()
  ```

  `nav_buttons` is mutated by `nav_btn` below; that order is fine because `go()` (and the tab-strip listener) only fire on user interaction, which is well after page-load wiring is complete.
- Change the `update:model-value` handler (near line 116) to call this helper instead of doing `setattr`:
  ```python
  with ui.tabs().classes("w-full").on(
      "update:model-value", lambda e: _on_tab_changed(e.args)
  ) as tabs:
  ```
- Update the nav drawer `go()` function (near line 83) to rely exclusively on `tabs.set_value()` to fire the listener. Remove its local assignment of `state.active_tab` and the explicit `_update_nav_classes()` call (the listener now handles both):
  ```python
  def go(name: str):
      tabs.set_value(name)  # fires update:model-value -> _on_tab_changed
  ```
  Note: NiceGUI dispatches `update:model-value` as a client event; for an in-process tab change triggered by `set_value`, the handler is invoked synchronously on the same event-loop tick. For programmatic restores, the listener still fires correctly.
- In the initial page-load restore (`app.py:150-151`), the existing `ctx.tabs.set_value(state.active_tab)` is sufficient — the listener fires and calls `_on_tab_changed` (which in turn calls `refresh_geometry_tab`). No additional change needed there; just verify the order: `set_value` → listener → `_on_tab_changed` → `ctx.refresh_geometry_tab()`. The `ctx` is built before the restore (line 127), and `ctx.refresh_geometry_tab` is wired by `geometry_tab.build(ctx)` at line 139, which runs *before* the restore at line 151. Good.
- *Note on assignment paths (E1/E2):* `update:model-value` on the tab strip is the *only* path that calls `_on_tab_changed`. `go()` simply sets the value on the `tabs` element, triggering the event. There is no double-call.
- *Note on `geometry` -> `geometry` (G6):* Clicking "Geometry" in the drawer while already on Geometry is a no-op (value unchanged → no event), which is correct.
- *Note on `_apply_global_offset_to_all`:* We intentionally do not add `ctx.refresh_geometry_tab` here to avoid feedback loops; it triggers `refresh_per_exam` which is sufficient.

### 5. Update Changelog

- Add a one-line note in `CHANGELOG.md` under the `## [Unreleased]` → `### Fixed` subsection (currently contains the `_CalcWarningCollector` handler leak entry) documenting the fix for cross-tab slider synchronization. Example:
  - **`Cross-tab slider sync in GUI`** (2026-06-25) — table-origin spinbox changes in Settings → Per-exam corrections now refresh Geometry sliders; switching to the Geometry tab (via the tab strip or the left nav drawer) refreshes sliders, value labels, and the live preview figure. Plan: `dev-docs/plans/CROSS_TAB_SLIDER_SYNC_PLAN.md`.

## Test coverage

- **Unit Tests:**
  - Add a small pytest regression test using a `MagicMock` PageContext and a stub `tabs` object. Assert that `ctx.refresh_geometry_tab` and `ctx.refresh_geometry_preview` are called when `state.active_tab` transitions to `"geometry"`, and are **not** called when transitioning to any other tab.
  - **Interaction with shipped `GEO_TAB_SPINNING_WHEEL_PLAN.md` regression tests:** the `_in_render_chain` guard in `_refresh_geometry_sliders` (geometry.py:596) means a tab-entry call to `ctx.refresh_geometry_tab()` will schedule **at most one** debounced render even if the entry fires repeatedly (e.g. tab strip clicks while already on Geometry are no-ops; multi-event tab navigation does not stack timers). The shipped `test_geometry_patient_slider_no_render_loop` and `test_geometry_table_slider_no_render_loop` provide indirect coverage — if this plan's tab-entry refresh ever introduced a render loop, those tests would fail under the same conditions. No new render-loop test is needed in this plan.

- **Manual Verification:**
  1. Load an RDSR file.
  2. Go to **Settings** -> **Per-exam corrections** (Tab 3).
  3. Modify the table origin values (verify the UI updates and the expansion panel stays open!).
  4. Navigate to the **Geometry** tab (Tab 4) using the top tab strip. Verify sliders, labels, and the figure are perfectly in sync.
  5. Go back to Tab 3, modify patient offset values.
  6. Navigate to the **Geometry** tab using the left navigation drawer. Verify sliders and labels are in sync.
