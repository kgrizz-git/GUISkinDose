# Vendor X/Z Clarification Plan

> Covers two `TO_DO.md` items:
> 1. **GUI / UX** — Clarify vendor-specific X/Z on Geometry plot: either convert display axes to one semantic frame or add a clear in-app note and axis legend.
> 2. **Input Data And Calculation** — Vendor coordinate validation: confirm per-vendor export frames and Philips double-correction risk against source RDSRs before expanding vendor adapters.

## 1. Objective

Make Geometry tab X/Y/Z controls mean the same plotted axes for every vendor and import path, especially GE-like `Tx`/`Tz` swaps. A user changing the `X/LON` table-origin control must move the plotted X axis whether the exam is Siemens-like, Philips-like, GE/swapped, or a tabular export with manual coordinate corrections.

The labels, plot annotations, Data tab aliases, and help text are supporting work. They are not sufficient unless the underlying Geometry controls are vendor-invariant.

The implementation may store manual table-origin overrides in the import/source frame, but the Geometry and Per-exam UI must never expose source-frame behavior. UI reads and writes must be mapped to the final plotted frame after `swap_lat_lon` and axis flips.

This plan does **not** relabel the plotted axes into the anatomical frame documented in `dev-docs/VENDOR_COORDINATE_SYSTEMS.md`. The code path has been traced through `rdsr_normalizer._normalize_table_parameters()`, `Beam.__init__()`, `geom_calc.position_patient_phantom_on_table()`, `Phantom.position()`, and `calculate_dose()`: the implementation consistently treats coordinate index 0 as the current `LON` display axis and coordinate index 2 as the current `LAT` display axis. Renaming the axes to anatomical `X - LAT` / `Z - LON` without a fixture-backed physics rewrite would make the plots less truthful.

## 2. Terminology

Throughout this document:

| Term | Meaning |
|------|---------|
| **DICOM tag name** | The label from the DICOM RDSR standard, e.g. `TableLongitudinalPosition`, `TableLateralPosition`, `TableHeightPosition`. |
| **PySkinDose display alias** | The short label currently used by plots and hover text: `LON`, `VER`, `LAT`. This follows the existing PySkinDose implementation, not the anatomical wording in `VENDOR_COORDINATE_SYSTEMS.md`. |
| **Anatomical semantic name** | The patient/geometric role described in `VENDOR_COORDINATE_SYSTEMS.md`: lateral = side-to-side, longitudinal = head-to-foot, vertical = up-down. |
| **Derived column name** | The short normalized DataFrame key consumed by the engine: `Tx`, `Ty`, `Tz`. |
| **Source frame** | The normalized table-position frame before GUI post-normalization corrections such as `swap_lat_lon` and `flip_tx`/`flip_ty`/`flip_tz`. This is also the current storage frame for `table_origin_detected` and `table_origin_override`. |
| **Final plotted frame** | The frame after GUI coordinate-correction toggles have been applied. Plot axes, Geometry sliders, Per-exam origin fields, and user-facing labels must refer to this frame. |

Use the term **PySkinDose display alias** in implementation comments and help text when referring to `LON`/`VER`/`LAT`. Do not call `Tx (LON)`, `Ty (VER)`, `Tz (LAT)` "semantic aliases"; that wording caused the contradiction this plan is correcting.

## 3. Verified Current State

### 3.1 Table-position mapping

`rdsr_normalizer._normalize_table_parameters()` currently assigns:

| Derived col | Plot axis | Current display alias | Source DICOM tag |
|-------------|-----------|-----------------------|------------------|
| `Tx` | X | `LON` | `TableLongitudinalPosition_mm` |
| `Ty` | Y | `VER` | `TableHeightPosition_mm` |
| `Tz` | Z | `LAT` | `TableLateralPosition_mm` |

That mapping is consumed directly:

- `Phantom.position()` translates table, pad, and patient by `[Tx, Ty, Tz]`.
- `geom_calc.check_new_geometry()` treats `Tx`, `Ty`, `Tz`, `FS_lat`, and `FS_long` as geometry-defining values.
- `calculate_dose()` passes patient offsets as `[d_lon, d_ver, d_lat]`, so `d_lon` moves the X coordinate and `d_lat` moves the Z coordinate.
- `Beam.__init__()` places `FS_long` on coordinate index 0 and `FS_lat` on coordinate index 2.

### 3.2 Plot labels and hover text

There are two rendering pipelines, and both must be considered:

| Pipeline | File / symbol | Current labels |
|----------|---------------|----------------|
| GUI dose map | `gui.figures.make_dosemap_fig()` | `X - LON [cm]`, `Y - VER [cm]`, `Z - LAT [cm]` |
| CLI / notebook geometry | `constants.PLOT_AXIS_TITLE_X/Y/Z`, consumed by `plotting.plot_layout` | `X - LON [cm]`, `Y - VER [cm]`, `Z - LAT [cm]` |

The hover texts are **not** an existing anatomical-semantic counterexample. They match the current PySkinDose display aliases:

- `gui.figures.make_dosemap_fig()` labels `r[i, 0]` as `lon`, `r[i, 1]` as `ver`, and `r[i, 2]` as `lat`.
- `plotting.create_geometry_plot_texts()` labels coordinate index 0 as `LON`, index 1 as `VER`, and index 2 as `LAT`.

Therefore, the current plots and hovers are internally consistent. The confusion comes from the mismatch between those labels and the anatomical coordinate convention described in `VENDOR_COORDINATE_SYSTEMS.md`, plus the lack of in-app explanation.

### 3.3 Confirmed gaps

- The **Data tab** shows derived columns such as `Tx`, `Ty`, and `Tz` with no visible relationship to the plot labels.
- **Vendor offsets** in `normalization_settings.json` apply silently; no Geometry-visual cue distinguishes Siemens-like zero offsets from Philips large Y/Z offsets or unknown `Default` fallback normalization.
- The **tabular import** `swap_lat_lon` toggle exists (`AppState.swap_lat_lon`, applied in `gui.exam_transforms._apply_transform_flags()`), but its effect on the displayed axes is not explained on the plot.
- **Table-origin overrides currently live in the detected pre-swap/source frame, but the UI does not map them to the final plotted frame.** `_apply_transform_flags()` applies `table_origin_override` to `Tx/Ty/Tz` before `swap_lat_lon` swaps `Tx` and `Tz`, while `effective_table_origin()` and `stage_table_origin_axis()` read/write bare `x`, `y`, `z` keys. For a GE-like swapped export, changing the Geometry tab `X` table-origin override can therefore affect the final plotted Z coordinate. That is the core user-facing bug this plan must prevent.
- The Geometry tab `HelpButton` loads `geometry_workflow.md`, which currently has no coordinate-convention section.
- The **Geometry tab sliders** use two naming styles: patient offsets use clinical words (`Longitudinal`, `Vertical`, `Lateral`) while table-origin overrides use bare `X`, `Y`, `Z`. Verified correction to the assessment: `d_lon` moves X, not Z; the inconsistency is naming, not a hidden axis mismatch.
- The **Body habitus scaling** controls in Settings use `Lateral / width`, `AP / vertical thickness`, and `Longitudinal / head-foot` labels without tying `scale_lon`/`scale_lat` to the current plotted frame.
- The plan must state what changes affect CLI/notebook plots and GUI exports, because shared constants and layout helpers are used outside the NiceGUI app.

## 4. Approach

### Option A — Relabel axes into the anatomical frame

Change plot axis titles to:

| Axis | Anatomical title |
|------|------------------|
| X | `X - LAT [cm]` |
| Y | `Y - VER [cm]` |
| Z | `Z - LON [cm]` |

This is **out of scope for this plan**. It can only be considered after a separate fixture-backed coordinate refactor that reconciles `VENDOR_COORDINATE_SYSTEMS.md`, `rdsr_normalizer`, `Beam`, `geom_calc`, dose results, tabular import correction toggles, and golden tests.

### Option B — Keep current labels, make the frame explicit

Keep `X - LON`, `Y - VER`, and `Z - LAT` as the default labels. Add explanatory UI, help text, Data tab aliases, and vendor warnings so users can understand which frame they are looking at.

**Recommendation:** implement Option B, with one non-negotiable invariant: **Geometry tab controls and plot labels must operate in the final plotted frame after vendor corrections.** If the active exam uses a GE-like `Tx`/`Tz` swap, the swap is an import/normalization detail; the user-facing `X/LON` table-origin control must still move the plotted X coordinate, not the pre-swap vendor X value that later appears on plotted Z. This is the primary requirement of the plan.

For table-origin overrides, use **source-frame storage with final-frame UI mapping**:

- Keep `state.loaded_exam_meta[*]["table_origin_detected"]` and `["table_origin_override"]` in the source frame so a physical manual origin follows a later `swap_lat_lon` toggle instead of silently staying attached to the old displayed axis.
- Add helper functions that transform source-frame origin dicts into the final plotted frame for display, slider limits, and audit text. For origin values, `swap_lat_lon` transposes X/Z; sign flips must be treated carefully because current `flip_tx`/`flip_ty`/`flip_tz` behavior pivots about the detected origin and reverses table motion without moving the origin coordinate itself.
- Make `stage_table_origin_axis(meta, axis, value)` accept a final-frame axis/value from the UI and inverse-map it into the stored source-frame override before `_apply_transform_flags()` runs.
- Keep `_apply_transform_flags()` applying the stored source-frame override before `swap_lat_lon`, because the UI mapping layer is what makes the controls vendor-invariant.

This accepts the 2026-06-25 assessment's state-frame concern while preserving the user's primary requirement: Geometry controls and plot labels mean the same thing across vendors.

## 5. Phase Ordering

1. **Phase 1 starts with the table-origin frame mapping fix**: labels/help may ship in the same phase, but the phase is not complete until Geometry table-origin controls move the same plotted axis across Siemens-like, Philips-like, GE/swapped, and manually corrected tabular exams.
2. **Phase 2 must run before Phase 3 warning logic is treated as complete**: manufacturer badges and unknown-vendor warnings should be grounded in the validation matrix.
3. **Do not implement anatomical axis relabeling in Phase 3**: any toggle defaults to the current PySkinDose display aliases and may optionally show derived column names. Anatomical relabeling belongs in a future coordinate-refactor plan.

## 6. Work Items

### Phase 1: Make Geometry Controls Vendor-Invariant and Explain the Plot Frame

1. **Table-origin override frame mapping fix** — in `src/mypyskindose/gui/exam_transforms.py` and `src/mypyskindose/gui/offset_handlers.py`, keep origin storage source-frame but make all UI controls final-frame:
   - keep `state.loaded_exam_meta[*]["table_origin_detected"]` and `["table_origin_override"]` stored as source-frame `{"x", "y", "z"}` keys
   - add source↔final origin mapping helpers that transpose X/Z for `swap_lat_lon`; document that `flip_tx`/`flip_ty`/`flip_tz` reverse table motion about the detected origin and therefore do not simply sign-flip origin coordinates
   - treat mirrored detected origins as out of scope for automatic sign-flip correction: if a vendor's origin value itself is wrong, the user must correct it with the table-origin override after applying the direction toggle, and Phase 3 warnings/help should say so
   - make `effective_table_origin(meta)` return final plotted-frame values for Geometry and Per-exam display
   - make `stage_table_origin_axis(meta, axis, value)` accept a final plotted-frame `axis`/`value` and inverse-map it into the stored source-frame override
   - update `_table_origin_override_note(meta)` so audit text states that stored values are source-frame and, when different, reports final plotted-frame values
   - keep `_apply_transform_flags()` applying the stored source-frame origin override before `swap_lat_lon`
   The acceptance rule: enabling `swap_lat_lon` must not change which plotted axis a Geometry tab `X`, `Y`, or `Z` table-origin slider moves, and toggling `swap_lat_lon` after an override is active must transpose the displayed override to the correct final plotted axis instead of silently pinning it to the old UI axis.

2. **GUI dose map annotation** — in `src/mypyskindose/gui/figures.py`, keep the current axis titles and add a Plotly scene annotation:
   - `X (Tx / LON) = DICOM TableLongitudinalPosition`
   - `Y (Ty / VER) = DICOM TableHeightPosition`
   - `Z (Tz / LAT) = DICOM TableLateralPosition`

3. **CLI / notebook geometry annotation** — in `src/mypyskindose/plotting/plot_layout.py`, add the same annotation to `default_geometry_layout()` and `default_procedure_layout()`. This means standalone HTML and notebook geometry plots will show the coordinate note too.

4. **Data tab aliases** — in `src/mypyskindose/gui/tabs/data.py`, add a small column-label map near the top of the file and apply it when building NiceGUI table columns:
   ```python
   COLUMN_LABEL_ALIASES = {
       "Tx": "Tx (X/LON)",
       "Ty": "Ty (Y/VER)",
       "Tz": "Tz (Z/LAT)",
   }
   ```
   Keep exports unchanged: CSV/XLSX/TXT should still write the actual DataFrame column names (`Tx`, `Ty`, `Tz`), not display labels.

5. **Geometry help content** — edit only `docs/source/gui_help/geometry_workflow.md`, then run `python scripts/sync_gui_help.py` to update the mirrored `src/mypyskindose/gui/help/geometry_workflow.md`. Add a concise section explaining:
   - current plot axes use `X/LON`, `Y/VER`, `Z/LAT`
   - those labels are PySkinDose display aliases for the normalized DataFrame columns
   - Geometry and Per-exam table-origin controls always operate in the final plotted frame after vendor corrections
   - manual table-origin overrides are stored in source/import coordinates internally, then mapped to the plotted frame for display and editing
   - `VENDOR_COORDINATE_SYSTEMS.md` documents the anatomical/internal-coordinate discussion for developers
   - `AGENTS.md` and shared agent/developer guidance must not keep the stale shorthand `X = lateral, Y = longitudinal, Z = vertical` without also warning that the current plotted PySkinDose display frame is `X/LON`, `Y/VER`, `Z/LAT`. If this plan leaves the deeper anatomical-coordinate contradiction unresolved, update the guidance to point readers here and to `VENDOR_COORDINATE_SYSTEMS.md` instead of presenting the stale shorthand as settled behavior.

6. **Geometry slider labels** — make one consistent naming pass in `src/mypyskindose/gui/tabs/geometry.py`:
   - patient offset labels: `Longitudinal (X/LON)`, `Vertical (Y/VER)`, `Lateral (Z/LAT)`
   - table-origin labels: `Table Origin Longitudinal (X/LON)`, `Table Origin Vertical (Y/VER)`, `Table Origin Lateral (Z/LAT)`
   This removes the mismatch between clinical words and bare axes. It is only correct after Phase 1 item 1 makes table-origin overrides vendor-invariant.

7. **Per-exam table-origin labels** — in `src/mypyskindose/gui/tabs/_per_exam.py`, use the same visible labels as Geometry for table-origin number inputs:
   - `Table Origin Longitudinal (X/LON)`
   - `Table Origin Vertical (Y/VER)`
   - `Table Origin Lateral (Z/LAT)`
   These controls must also call the final-frame mapping helper from item 1.

8. **Cross-tab table-origin synchronization** — preserve the existing shared-state behavior between Geometry and Settings -> Per-exam corrections while changing the mapping helpers:
   - Geometry table-origin slider commits must refresh Per-exam controls after the debounced transform commit
   - Per-exam table-origin number changes and reset actions must refresh Geometry sliders/captions
   - coordinate-correction toggles such as `swap_lat_lon` must refresh both tabs so displayed final-frame origin values transpose immediately
   - add a focused test for the `PageContext` refresh path or an isolated helper-level test proving both UI builders read from the same `effective_table_origin(meta)` final-frame values

9. **Body habitus scaling labels** — in `src/mypyskindose/gui/tabs/settings.py`, update the human-phantom scale labels so users can relate the scale setting to the plotted frame:
   - `Lateral / width (Z/LAT)`
   - `AP / vertical thickness (Y/VER)`
   - `Longitudinal / head-foot (X/LON)`
   Keep the underlying settings keys unchanged (`phantom_scale_lat`, `phantom_scale_ap`, `phantom_scale_lon`) and add/update GUI tests that assert the new labels. Phantom scaling is global by design: per-exam `swap_lat_lon` and table-position corrections normalize each exam into the common plotted `Tx/Ty/Tz` frame before the shared phantom is positioned, so mixed-vendor multi-exam calculations still use one coherent phantom scale.

10. **GUI export behavior** — `make_dosemap_html()` and `make_dosemap_png()` call `make_dosemap_fig()`, so they should inherit the same labels and annotation. Add tests for this if the annotation is parameterized.

### Phase 2: Vendor Coordinate Validation

1. **Build a validation matrix** in `dev-docs/VENDOR_COORDINATE_SYSTEMS.md` or a linked appendix. Include at least:

| Source path | Current fixture status | Required validation |
|-------------|------------------------|---------------------|
| DICOM RDSR Siemens examples | real DICOM examples exist in `src/mypyskindose/example_data/RDSR/` | characterize normalized `Tx/Ty/Tz` and keep golden values stable |
| DICOM RDSR Philips examples | real DICOM examples exist in `src/mypyskindose/example_data/RDSR/` | characterize large offset behavior and sign handling |
| DICOM RDSR GE examples | no bundled GE DICOM fixture currently exists | obtain a real GE RDSR or matched de-identified fixture; characterize whether `Tx`/`Tz` need swapping and keep golden values stable |
| `generic_rdsr_like` | synthetic RDSR-shaped fixture exists | confirm round-trip against source RDSR parser output |
| `radimetrics` | synthetic Siemens fixture exists; gitignored local GE Radimetrics-style exports exist in `test_data_gitignored/` | characterize the local GE exports as private validation inputs for schema detection, GE warning behavior, and `swap_lat_lon` UI behavior; still mark real matched export + source RDSR as missing until obtained |
| `dosetrack` | synthetic Siemens fixture only; real Philips XLSX missing | mark Philips swap path and real XLSX validation as unvalidated until obtained |
| `qaelum` | stub adapter exists; no real export fixture | mark adapter unimplemented and coordinate frame unvalidated until a matched export + source RDSR is obtained |
| `dosemonitor` | stub adapter exists; no real export fixture | mark adapter unimplemented and coordinate frame unvalidated until a matched export + source RDSR is obtained |
| `dosewatch` | stub adapter exists; no real export fixture | mark adapter unimplemented and coordinate frame unvalidated until a matched export + source RDSR is obtained |
| `normalized` | already-normalized input | confirm no vendor correction is applied |

2. **Document the transform stage** for each adapter:
   - raw DICOM-frame input should flow through `rdsr_normalizer()` exactly once
   - already-normalized input should not call `rdsr_normalizer()`
   - GUI post-normalization toggles (`swap_lat_lon`, `flip_ap1`, `flip_ap2`) must be described as user coordinate-correction overrides, not adapter validation
   - table-origin overrides are positioning controls in the final plotted frame, not vendor-frame coordinate transforms

3. **Philips and GE risk check** — explicitly document the double-correction risk:
   - Philips: large Y/Z offsets make double-correction visibly wrong
   - GE / swapped exports: `Tx`/`Tz` swap can be missed or applied twice
   - Siemens: zero offsets can hide a double-correction bug numerically

4. **CLI validation flag scope** — do not implement `--validate-coordinates` inside Phase 2 unless it receives its own mini-design and tests. A tested CLI flag is likely 80-100+ LOC across argparse, adapter/normalizer integration, warning formatting, and tests.

### Phase 3: In-App Vendor Awareness

Phase 3 depends on Phase 2's validation matrix.

1. **Manufacturer badge** — show detected manufacturer/model near the Geometry plot. Source it from the active exam metadata (`state.loaded_exam_meta`) or the single-exam state fields.

2. **Unknown-manufacturer warning** — show a Geometry tab banner when normalization falls back to `Default` or when a tabular export lacks coordinate-convention confidence. The banner should point users to manual offset review in Settings / Per-exam corrections. `_C1_BANNER` is a UI pattern reference only; do not reuse its text.
   - For unknown/fallback manufacturers, explicitly mention that `Tx`/`Tz` may be swapped or signed incorrectly.
   - For Philips-like exams, explicitly mention that large table offsets make double-correction visible and should be checked against the source RDSR when possible.
   - For GE-like or manually swapped tabular exports, explicitly mention the `Tx`/`Tz` swap risk and whether the GUI correction toggle is active.
   - For axis-direction flips, state that the flip reverses table motion about the detected origin; if the detected origin value itself is mirrored, users should correct the table-origin override manually.

3. **Axis label mode toggle** — optional and GUI-only for this plan:
   - Add `axis_label_mode: str = "pyskindose"` to `AppState`.
   - Supported values:
     - `"pyskindose"`: default, current titles `X - LON`, `Y - VER`, `Z - LAT`
     - `"derived"`: titles `X - Tx`, `Y - Ty`, `Z - Tz`
   - Do **not** add an anatomical `X - LAT` / `Z - LON` mode in this plan.
   - The toggle state is session-only in this plan. Do not add it to `PyskindoseSettings` here; if users need persistence later, add a separate GUI-preferences design so core calculation settings do not silently gain UI-only export preferences.

4. **Export consistency** — if the axis label mode affects dose-map exports, pass the selected mode into `make_dosemap_fig()`, `make_dosemap_html()`, and `make_dosemap_png()` instead of reading hidden global state from an export worker.
   - Coordinate annotations must be produced by the same label-mode helper as the axis titles. In `"pyskindose"` mode, show the full `X (Tx / LON)` style note; in `"derived"` mode, avoid redundant `X - Tx` wording and keep only the DICOM tag mapping if the note remains visible.

## 7. Test Coverage

| What to test | Where | How |
|-------------|-------|-----|
| GUI dose-map labels and annotation | `gui.figures.make_dosemap_fig()` | Snapshot `fig.to_dict()` and assert scene axis title strings plus annotation text. |
| GUI HTML/PNG export inheritance | `gui.figures` | Assert export builders call the same figure path or expose the same annotation in figure dict before rendering. |
| CLI / notebook plot annotation | `plotting.plot_layout` | Unit-test `default_geometry_layout()` / `default_procedure_layout()` annotations and axis titles. |
| Data tab display aliases | `gui.tabs.data` | Mount or isolate the column-building helper and assert `Tx (X/LON)`, `Ty (Y/VER)`, `Tz (Z/LAT)` labels. |
| Data export column stability | `gui.tabs.data` | Export a small DataFrame and assert raw column names remain `Tx`, `Ty`, `Tz`. |
| Help source/mirror sync | docs + script | Edit `docs/source/gui_help/geometry_workflow.md`; run `python scripts/sync_gui_help.py`; assert mirrored file matches. |
| Agent/developer guidance consistency | docs | Assert `AGENTS.md` / shared guidance no longer present stale anatomical shorthand as the active plotted-frame convention without the PySkinDose display-frame caveat. |
| Geometry slider labels | `gui.tabs.geometry` | GUI test or text assertion confirming patient and table-origin labels include the same `X/LON`, `Y/VER`, `Z/LAT` frame. |
| GE / swapped table-origin behavior | `gui.exam_transforms` / `gui.offset_handlers` | With `swap_lat_lon=True`, call `stage_table_origin_axis(meta, "x", final_detected_x + 10)` and assert final plotted `Tx` changes by 10 while final `Tz` does not receive that X delta. Repeat the inverse for Z. |
| Toggle-after-override behavior | `gui.exam_transforms` / `gui.offset_handlers` | Set a source-frame table-origin override with `swap_lat_lon=False`, then toggle `swap_lat_lon=True`; assert `effective_table_origin(meta)` transposes the displayed X/Z values and the stored source-frame override still composes correctly through `_apply_transform_flags()`. |
| Cross-tab table-origin synchronization | `gui.tabs.geometry` / `gui.tabs._per_exam` | Exercise or isolate the refresh callbacks so Geometry edits refresh Per-exam controls, Per-exam edits refresh Geometry controls, and toggling `swap_lat_lon` refreshes both final-frame displays. |
| Local GE tabular characterization | `test_data_gitignored/` + `radimetrics` adapter | When available locally, run the gitignored GE Radimetrics-style exports through schema detection/normalization and record non-sensitive aggregate coordinate ranges plus warnings; do not commit private exports. |
| Vendor validation matrix | docs | Grep `VENDOR_COORDINATE_SYSTEMS.md` for each shipped adapter and its validation status. |
| Optional axis label toggle | Geometry / figures | Toggle from `"pyskindose"` to `"derived"` and assert axis titles update without changing plotted coordinates. |

Run at minimum:

```bash
python scripts/sync_gui_help.py
python scripts/check_doc_freshness.py
pytest tests/unittests/test_input_adapters.py tests/unittests/test_rdsr_normalizer_characterization.py
```

Add focused GUI/plot tests for any new helpers introduced by Phase 1 or Phase 3.

## 8. Acceptance Criteria

1. The same Geometry table-origin slider moves the same plotted axis for Siemens-like, Philips-like, GE/swapped, and manually corrected tabular exams; vendor-specific swaps are not exposed as different slider behavior.
2. Table-origin override state can remain source-frame internally, but Geometry and Per-exam controls display and edit final plotted-frame values; toggling `swap_lat_lon` after an override is active preserves physical override intent by transposing the displayed X/Z origin values.
3. Plot axes remain truthful to the current implementation: default labels are `X - LON`, `Y - VER`, `Z - LAT`.
4. Geometry and dose-map plots include a concise explanation that ties `X/Y/Z`, `Tx/Ty/Tz`, and `LON/VER/LAT` together.
5. Data tab column headers show `Tx (X/LON)`, `Ty (Y/VER)`, and `Tz (Z/LAT)` without changing exported DataFrame column names.
6. Geometry help content explains the coordinate labels and is edited from `docs/source/gui_help/`, with the mirrored GUI help file synced.
7. `AGENTS.md` and shared agent/developer guidance no longer present the stale anatomical shorthand as the active plotted-frame convention without the PySkinDose display-frame caveat.
8. Geometry patient-offset, table-origin, Per-exam table-origin, and body-habitus controls use one visible naming frame.
9. The vendor-coordinate document records validation status for DICOM Siemens, Philips, and GE examples, `generic_rdsr_like`, `radimetrics`, `dosetrack`, `qaelum`, `dosemonitor`, `dosewatch`, and `normalized`.
10. Unknown or fallback manufacturer handling is visible in the GUI before users run dose calculations and explicitly names `Tx`/`Tz` swap or large-offset double-correction risks when relevant.
11. Any optional axis-label toggle defaults to the current PySkinDose display alias mode and never defaults to anatomical relabeling.

## 9. Open Questions

- Should `VENDOR_COORDINATE_SYSTEMS.md` be revised in the same PR to clarify the difference between the anatomical documentation frame and the current PySkinDose display aliases? This plan should at least add a warning note if it leaves the deeper doc contradiction unresolved.
- When real Radimetrics and DoseTrack matched export/source-RDSR fixtures become available, should they live under `tests/fixtures/tabular_inputs/` or a separate restricted-data fixture path?
- Can any local gitignored GE Radimetrics-style export be paired with its original de-identified DICOM RDSR? Without that matched source, it helps characterize the tabular adapter and manual correction override behavior, but it cannot fully validate the DICOM GE convention.
- Should `--validate-coordinates` be its own plan after Phase 2 documents the validation matrix? Current recommendation: yes.

## 10. 18:04 Assessment Disposition

The 2026-06-25 `tmp/assessment_vendor_xz_plan_20260625_1804.md` assessment was reviewed against the code. Applied findings:

- added GE DICOM RDSR to the validation matrix, marked as missing fixture until a real or matched de-identified GE RDSR is obtained
- added explicit Geometry <-> Per-exam table-origin synchronization requirements and test coverage
- clarified that plot annotations must be generated consistently with any optional axis-label mode
- clarified the `flip_tx`/`flip_ty`/`flip_tz` scope: flips reverse table motion about the detected origin, but mirrored origin values remain a manual table-origin correction problem
- added the mixed-vendor multi-exam phantom scaling note: per-exam coordinate corrections normalize exams into the shared plotted frame before the global phantom scale is used

## 11. New Assessment Disposition

The 2026-06-25 `tmp/assessment_vendor_xz_plan_20260625.md` assessment was reviewed against the code. Applied findings:

- accepted the table-origin state-frame concern: overrides should remain source-frame internally, with tested final-frame UI mapping for Geometry and Per-exam controls
- added the toggle-after-override edge case so `swap_lat_lon` changes transpose displayed override values instead of silently reassigning physical intent
- added body-habitus scaling label work for `scale_lon`, `scale_ap`, and `scale_lat`
- made table-origin labels symmetric with patient-offset labels
- added `qaelum`, `dosemonitor`, and `dosewatch` stub adapters to the validation matrix
- strengthened unknown/fallback, Philips-like, and GE/swapped warning-banner requirements
- made the axis-label toggle persistence decision explicit: session-only in this plan; persistent GUI preferences need a separate design

Partially rejected:

- Do not expose source-frame table-origin controls directly. The accepted design is source-frame storage plus final-frame UI mapping, because the primary requirement is that user-facing X/Y/Z controls move the same plotted axes across vendors.

## 12. Previous Assessment Disposition

The 2026-06-25 assessment was reviewed against the code. Applied findings:

- duplicate §3.3 heading removed
- hover-text classification corrected; current hover text matches `X/LON`, `Y/VER`, `Z/LAT`
- Phase 3 toggle default corrected to current PySkinDose display aliases
- CLI/notebook/export impact added
- phase ordering added
- Data tab aliases changed from ambiguous "semantic aliases" to explicit `Tx (X/LON)` style labels
- `geom_calc` / `Phantom.position()` / `calculate_dose()` data flow explicitly traced
- toggle state location specified as `AppState`, session-only
- `--validate-coordinates` moved out of default Phase 2 scope

Corrected assessment overstatement:

- The assessment claimed patient `Longitudinal` / `d_lon` shifts along Z. Actual code passes `[d_lon, d_ver, d_lat]` directly to `patient.translate()`, so `d_lon` shifts X. The remaining issue is inconsistent labeling between patient sliders and table-origin sliders.

## 13. Related Files Reference

| File | Role in this plan |
|------|-------------------|
| `src/mypyskindose/gui/figures.py` | GUI dose-map scene axes, hover text, HTML/PNG exporters |
| `src/mypyskindose/constants.py` | CLI/notebook axis title constants |
| `src/mypyskindose/plotting/plot_layout.py` | Shared layout for geometry/procedure plots |
| `src/mypyskindose/plotting/create_geometry_plot_texts.py` | CLI geometry hover text |
| `src/mypyskindose/gui/tabs/data.py` | Dynamic Data tab column labels and table exports |
| `src/mypyskindose/gui/tabs/geometry.py` | Geometry HelpButton, patient sliders, table-origin sliders |
| `src/mypyskindose/gui/exam_transforms.py` | Post-normalization coordinate correction toggles |
| `src/mypyskindose/gui/state.py` | GUI state for optional axis-label mode |
| `src/mypyskindose/rdsr_normalizer.py` | DICOM tag to `Tx/Ty/Tz` mapping |
| `src/mypyskindose/beam_class.py` | Beam geometry and `FS_long` / `FS_lat` axis usage |
| `src/mypyskindose/geom_calc.py` | Geometry calculations and patient positioning |
| `src/mypyskindose/phantom_class.py` | `Tx/Ty/Tz` table/patient translation |
| `src/mypyskindose/normalization_settings.json` | Vendor offset and sign definitions |
| `dev-docs/VENDOR_COORDINATE_SYSTEMS.md` | Coordinate documentation and validation matrix |
| `docs/source/gui_help/geometry_workflow.md` | Source help content to edit |
| `src/mypyskindose/gui/help/geometry_workflow.md` | Mirrored help content generated by sync script |
