# NEEDS REVIEW

> **Status:** Awaiting reviewer sign-off.

# Patient-Size / Body-Habitus Scaling Plan

Plan for `TO_DO.md` item: *"More patient sizes / phantom body-habitus scaling."*

## 1. Objective

Let users **directionally scale** the current human-mesh phantoms along lateral (X), AP (Y), and longitudinal (Z) axes so that a single mesh can cover a wider range of body sizes without needing additional STL files. Body size changes skin-to-source distance and beam intersection, so scaling materially affects PSD.

Two approaches were considered:

- **(a) Generate or source additional meshes** for under-represented body types (e.g. obese) — **deferred for now**. This remains a valid future direction. Additional meshes would follow the existing full-res + `_reduced_1000t` pairing convention and be wired into `get_human_mesh_names()`.
- **(b) Directional scaling of current phantoms** — **this plan**. The user stretches a mesh along lateral / AP / longitudinal axes via controls in the Settings → Phantom section. Scaling is applied in `phantom_class.py` before dose mapping. Scaled geometry is validated in the Geometry tab.

Rationale for choosing (b) first: it can be implemented against the existing mesh files without sourcing new STL assets, and it gives immediate value for users who know their patient's approximate anthropometric dimensions. Option (a) can be added later as a complementary path.

## 2. Background & relevant code

- **Phantom meshes** — `phantom_class.py` loads STL files via `pyvista` (or `trimesh`). Mesh names come from `helpers.get_human_mesh_names()`, which reads `phantom_data/`. Each mesh has a full-res + `_reduced_1000t` variant.
- **Phantom placement** — `phantom_class.py` positions the mesh on the table/pad using `position_patient_phantom_on_table()`. The mesh vertices are transformed into the global coordinate frame where beam intersection is computed.
- **Beam intersection** — `beam_class.py:181` (`Beam.check_hit`) tests whether beam polygons intersect patient skin cells. Scaling the mesh changes which cells are in the beam path and their distance from the source.
- **Dose accumulation** — `calculate_dose/` accumulates dose to skin cells. The `k_isq` inverse-square correction depends on source-to-skin distance, which scaling changes.
- **Settings** — `PyskindoseSettings.phantom` is a `PhantomSettings` instance (`settings/phantom_settings.py`). GUI mirrors settings in `gui/state.py` (e.g. `phantom_model`, `human_mesh`, `patient_orientation`).
- **GUI Settings tab** — `gui/tabs/settings.py` has a "Phantom Settings" expansion with model selector, mesh selector, orientation, table offsets, and patient offset sliders.
- **Geometry preview** — `gui/figures.make_geometry_fig()` calls `build_settings()` then `create_geometry_plot()`, which constructs the phantom and renders it.
- **GUI helpers** — `gui/settings_builder.py.build_settings()` assembles the `PyskindoseSettings` object from `state` for the calculation pipeline.

## 3. Acceptance criteria

1. **Three new phantom settings** — `scale_lat` (lateral/X), `scale_ap` (AP/Y), and `scale_lon` (longitudinal/Z), each defaulting to `1.0`. Stored in `PhantomSettings` and mirrored in `gui/state.py`.
2. **Directional scaling in `phantom_class.py`** — before any positioning or beam intersection, the mesh vertices are scaled relative to the mesh centroid along each axis: `v' = centroid + (v - centroid) * scale_factor`. Scaling is applied once at load/position time, not per-event.
3. **GUI controls** — three sliders (range `0.5` to `2.0`, step `0.05`, default `1.0`) in **Settings → Phantom Settings**, below the patient offset section. Each slider shows its current value. The sliders are visible only when `phantom_model == "human"`.
4. **Reset on setting change** — changing any scale slider calls `reset_results()` and refreshes the geometry preview.
5. **Geometry tab validation** — the scaled mesh is rendered correctly in the Geometry tab preview. The mesh should look proportionally stretched/compressed along the expected axis.
6. **Settings build** — `gui/settings_builder.py.build_settings()` passes the scale values into `PhantomSettings` so the calculation pipeline receives them.
7. **Settings JSON** — `settings_example.json` includes the three scale fields. `PyskindoseSettings` round-trips them through JSON/dict.
8. **Physics correctness** — scaled mesh vertices are used for all downstream calculations (beam intersection, inverse-square correction, dose accumulation). The `k_isq` factor automatically accounts for changed source-to-skin distance because it uses the actual vertex positions.
9. **Bounds validation** — if any scale factor falls outside `[0.5, 2.0]`, a warning is emitted (CLI: `logger.warning`; GUI: `state.calc_warnings`). Values are clamped in the GUI slider.
10. **Tests** — unit tests verifying: (a) centroid-relative scaling produces correct vertex positions; (b) a `scale_lat=2.0` mesh has twice the lateral extent; (c) beam intersection changes with scaling; (d) golden baseline PSD is unchanged at `scale=1.0`.
11. **Docs** — one-line note in `FEATURE_INVENTORY.md` (Settings / Phantoms). `AGENTS.md` updated with the new settings. `dev-docs/TO_DO.md` link updated.

## 4. Implementation outline

### 4.1 Settings model

**File: `src/mypyskindose/settings/phantom_settings.py`**

Add three fields to `PhantomSettings`:

```python
scale_lat: float = 1.0   # lateral (X-axis) scaling factor
scale_ap: float = 1.0    # AP (Y-axis) scaling factor
scale_lon: float = 1.0   # longitudinal (Z-axis) scaling factor
```

Clamp to `[0.5, 2.0]` in `__post_init__` or a validator. Add to `to_printable_string()` output.

**File: `src/mypyskindose/settings_example.json`**

Add the three fields under the `phantom` section:

```json
"phantom": {
    ...
    "scale_lat": 1.0,
    "scale_ap": 1.0,
    "scale_lon": 1.0
}
```

**File: `src/mypyskindose/settings/pyskindose_settings.py`**

No changes needed — `PhantomSettings` is already deserialized from the `phantom` dict. The new fields will be picked up automatically if they exist in JSON, or default to `1.0` if absent (backward compatible).

### 4.2 GUI state

**File: `src/mypyskindose/gui/state.py`**

Add to `AppState`:

```python
phantom_scale_lat: float = 1.0
phantom_scale_ap: float = 1.0
phantom_scale_lon: float = 1.0
```

### 4.3 GUI controls

**File: `src/mypyskindose/gui/tabs/settings.py`**

Add three sliders inside the "Phantom Settings" expansion, after the patient offset section and before the closing of the expansion:

```python
with ui.column().classes("w-full gap-1").bind_visibility_from(
    state, "phantom_model", backward=lambda v: v == "human"
) as scale_section:
    ui.label("Body habitus scaling (relative to base mesh)").classes("text-subtitle2")
    
    with ui.row().classes("w-full gap-4"):
        ui.slider(min=0.5, max=2.0, step=0.05, value=state.phantom_scale_lat
        ).bind_value(state, "phantom_scale_lat").on(
            "update:model-value", reset_results
        ).classes("grow")
        ui.label().bind_text_from(state, "phantom_scale_lat",
            backward=lambda v: f"{v:.2f}"
        ).classes("mono-text")
        
        ui.slider(min=0.5, max=2.0, step=0.05, value=state.phantom_scale_ap
        ).bind_value(state, "phantom_scale_ap").on(
            "update:model-value", reset_results
        ).classes("grow")
        ui.label().bind_text_from(state, "phantom_scale_ap",
            backward=lambda v: f"{v:.2f}"
        ).classes("mono-text")
        
        ui.slider(min=0.5, max=2.0, step=0.05, value=state.phantom_scale_lon
        ).bind_value(state, "phantom_scale_lon").on(
            "update:model-value", reset_results
        ).classes("grow")
        ui.label().bind_text_from(state, "phantom_scale_lon",
            backward=lambda v: f"{v:.2f}"
        ).classes("mono-text")
```

Labels for the sliders: "Lateral (X)", "AP (Y)", "Longitudinal (Z)" — use `ui.number` with slider props or three separate rows for clarity.

### 4.4 Scaling in phantom_class.py

**File: `src/mypyskindose/phantom_class.py`**

In the `PatientPhantom` class (or wherever the mesh is loaded and positioned), apply directional scaling to the vertices **after loading the STL but before positioning**:

```python
def _apply_scale(self, mesh: pv.DataSet) -> pv.DataSet:
    """Scale mesh vertices relative to centroid along each axis."""
    scale = self.settings.phantom.scale_lat, self.settings.phantom.scale_ap, self.settings.phantom.scale_lon
    
    # Check if any scaling is needed
    if all(s == 1.0 for s in scale):
        return mesh
    
    centroid = mesh.centroid
    points = mesh.points.copy()
    
    # Scale each axis relative to centroid
    points[:, 0] = centroid[0] + (points[:, 0] - centroid[0]) * scale[0]  # X (lateral)
    points[:, 1] = centroid[1] + (points[:, 1] - centroid[1]) * scale[1]  # Y (AP)
    points[:, 2] = centroid[2] + (points[:, 2] - centroid[2]) * scale[2]  # Z (longitudinal)
    
    mesh.points = points
    return mesh
```

Call this method after loading the STL and before `position_patient_phantom_on_table()`.

### 4.5 Settings builder

**File: `src/mypyskindose/gui/settings_builder.py`**

In `build_settings()`, pass the scale values to `PhantomSettings`:

```python
# When constructing PhantomSettings or the ptm_dim dict:
ptm_dim["scale_lat"] = state.phantom_scale_lat
ptm_dim["scale_ap"] = state.phantom_scale_ap
ptm_dim["scale_lon"] = state.phantom_scale_lon
```

Check how `PhantomSettings` is instantiated from `ptm_dim` in the settings builder to ensure the new keys flow through.

### 4.6 Geometry preview

The geometry preview in `gui/figures.make_geometry_fig()` already calls `build_settings()` and constructs the phantom from settings. Since the scaling is applied inside `phantom_class.py` during phantom construction, the preview will automatically show the scaled mesh — no changes needed to the plotting pipeline.

### 4.7 Validation in geometry tab

The Geometry tab already renders the phantom. After scaling, the user can visually verify the mesh is proportionally changed. No new UI is needed — the existing preview suffices. Optionally, a small caption could appear showing the current scale factors:

```
Scale: Lateral 1.00x · AP 1.00x · Longitudinal 1.00x
```

This could be added as a label in the Geometry tab that binds to the scale state values.

## 5. Test plan

### 5.1 Unit tests

**File: `tests/unittests/test_phantom_class.py`** (or append to existing)

- **test_scaling_centroid_relative**: Verify that scaling by `(2.0, 1.0, 1.0)` doubles the lateral extent while keeping the centroid fixed.
- **test_scaling_no_change_at_one**: Verify that `(1.0, 1.0, 1.0)` produces vertices identical to the unscaled mesh (bitwise or within tolerance).
- **test_scaling_applied_before_positioning**: Verify that scaling happens before table positioning, so the scaled mesh is correctly placed on the table.
- **test_phantom_settings_defaults**: Verify `PhantomSettings` defaults are `1.0` for all three scales.
- **test_phantom_settings_clamp**: Verify values outside `[0.5, 2.0]` are clamped.
- **test_golden_baseline_unchanged**: Existing golden-baseline PSD tests continue to pass (scales default to `1.0`).

### 5.2 Integration tests

- **test_scaled_beam_intersection**: A phantom scaled laterally by `2.0` should have more cells intersected by a beam of fixed width.
- **test_scaled_inverse_square**: The `k_isq` correction should differ for a scaled phantom because source-to-skin distance changes.

### 5.3 GUI smoke test

- Load an RDSR, open Settings → Phantom, drag a scale slider, verify the Geometry tab preview updates.
- Verify `reset_results()` clears any previous dose map when a scale changes.
- Verify the scale values appear in the exported settings JSON.

## 6. Future work (option a — deferred)

When additional meshes are needed (e.g. obese body type):

1. Generate or source STL files for the new body type.
2. Create `_reduced_1000t` variants using the existing mesh-reduction pipeline.
3. Place them in `phantom_data/` alongside existing meshes.
4. `get_human_mesh_names()` will auto-discover them (it scans the directory).
5. Add a note in `FEATURE_INVENTORY.md` listing the new mesh.
6. Consider whether the scaling controls should have presets (e.g. "obese" = `scale_lat=1.4, scale_ap=1.3`).

This plan does not implement option (a) — it is left as a future enhancement that can be added at any time without breaking the scaling infrastructure.

## 7. Decision log

| Decision | Rationale |
|----------|-----------|
| Scale relative to mesh centroid | Keeps the mesh centered in its local frame, avoiding unintended translation when scaling. Positioning happens after scaling. |
| Range [0.5, 2.0] | Covers roughly half-size to double-size, which encompasses realistic anthropometric variation without producing degenerate geometries. |
| Step 0.05 | Fine enough for meaningful adjustment without overwhelming the user. |
| Directional (not uniform) scaling | Different body dimensions vary independently (e.g. a wider but not taller patient). Uniform scaling would be less useful. |
| Apply scaling in `phantom_class.py` | Centralizes the geometry transformation where the mesh is already loaded, before any positioning or beam intersection logic. |
| No new settings class | The three scale factors fit naturally into `PhantomSettings` alongside existing phantom parameters. |
| Option (a) deferred | Sourcing/generating new STL meshes is a separate effort with different dependencies (3D scanning, mesh generation, licensing). Scaling provides immediate value. |

## 8. Progress log

| Date | Status |
|------|--------|
| 2026-06-24 | Plan authored |
| — | Implementation pending |
