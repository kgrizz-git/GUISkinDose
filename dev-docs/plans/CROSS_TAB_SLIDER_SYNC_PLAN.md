# Plan: Cross-tab Offset/Origin Slider Synchronization

> **Status:** NEEDS REVIEW
>
> **Objective:** Fix the cross-tab synchronization limitation where editing table origin or patient offsets via spinboxes on Tab 3 (Settings) does not reliably update the corresponding sliders and value labels on Tab 4 (Geometry).
>
> **Rationale:** The current synchronization relies on a "push" mechanism (`ctx.refresh_per_exam()`) which is inconsistently applied (present for patient offsets, missing for table origin). Furthermore, navigation via the side drawer bypasses the `update:model-value` event, meaning tab-change "pull" synchronization wouldn't fire. This plan unifies both push and pull mechanisms so the Geometry tab is always up to date.

## Acceptance criteria

- [ ] Table-origin spinboxes in Tab 3 (Settings -> Per-exam corrections) trigger a per-exam refresh on change and reset, matching the behavior of patient-offset spinboxes.
- [ ] Switching to Tab 4 (Geometry) via the tab strip immediately refreshes the geometry tab content, ensuring sliders and text value labels reflect the latest state.
- [ ] Switching to Tab 4 (Geometry) via the left navigation drawer also immediately refreshes the geometry tab content.
- [ ] Switching between any other tabs does not trigger unnecessary geometry tab slider refreshes.
- [ ] *Note: "text value labels" includes patient-offset labels and the table-origin labels (assuming prior completion of `GEOMETRY_TABLE_ORIGIN_SLIDER_VALUES_PLAN.md`).*

## Implementation plan

### 1. Fix root cause: Add `refresh_per_exam` to table-origin handlers

In `src/mypyskindose/gui/tabs/_per_exam.py`:
- In `_on_change` (near line 108), add `ctx.refresh_per_exam()` at the end of the function.
- In `_on_reset` (near line 121), add `ctx.refresh_per_exam()` at the end of the function.
- *Reconciliation Note:* This unifies table-origin behavior with patient offsets. The existing `refresh_per_exam` wrapping in `geometry.py:596-602` will remain as the primary push-sync mechanism.

### 2. Add tab refresher callback to PageContext

In `src/mypyskindose/gui/page_context.py`:
- Add `refresh_geometry_tab: Callable[[], None] = field(default=_noop)` to the `PageContext` class.

### 3. Register the callback in Geometry Tab

In `src/mypyskindose/gui/tabs/geometry.py`:
- At the end of `build(ctx: PageContext)` (near line 602, next to `ctx.refresh_per_exam = ...`), register the local `_refresh_geometry_sliders` closure (which refreshes sliders, exam selector, and captions):
  ```python
  ctx.refresh_geometry_tab = _refresh_geometry_sliders
  ```

### 4. Trigger pull synchronization on tab change & nav drawer

In `src/mypyskindose/gui/app.py`:
- Implement a helper to capture tab changes:
  ```python
  def _on_tab_changed(tab_name: str) -> None:
      state.active_tab = tab_name
      if tab_name == "geometry":
          ctx.refresh_geometry_tab()
  ```
- Change the `update:model-value` handler (near line 116) to call this helper:
  ```python
  with ui.tabs().classes("w-full").on(
      "update:model-value", lambda e: _on_tab_changed(e.args)
  ) as tabs:
  ```
- Update the nav drawer `go()` function (near line 83) to use the new helper, fixing the nav-drawer bypass gap:
  ```python
  def go(name: str):
      tabs.set_value(name)
      _on_tab_changed(name)
      _update_nav_classes()
  ```

## Test coverage

- **Manual Verification:**
  1. Load an RDSR file.
  2. Go to **Settings** -> **Per-exam corrections** (Tab 3).
  3. Modify the table origin values (verify the UI updates).
  4. Navigate to the **Geometry** tab (Tab 4) using the top tab strip. Verify sliders and labels are perfectly in sync.
  5. Go back to Tab 3, modify patient offset values.
  6. Navigate to the **Geometry** tab using the left navigation drawer. Verify sliders and labels are in sync.
