# Patient-Size / Body-Habitus Scaling Plan

> **Status:** Completed and archived.
> **Last reviewed:** 2026-06-25.

Plan for `TO_DO.md` item: *"More patient sizes / phantom body-habitus scaling."*

## 1. Objective

Let users directionally scale the current human-mesh phantoms along lateral/width, AP/vertical thickness, and longitudinal/head-foot axes so that a single mesh can cover a wider range of body sizes without needing additional STL files. Body size changes skin-to-source distance and beam intersection, so scaling materially affects PSD.

Two approaches were considered:

- **(a) Generate or source additional meshes** for under-represented body types, such as obese or large-habitus patients. This is deferred for now. Additional meshes remain a valid future direction and should follow the existing full-res + `_reduced_1000t` pairing convention.
- **(b) Directional scaling of current phantoms**. This plan. The user stretches a mesh via controls in Settings -> Phantom Settings. Scaling is applied when the `Phantom` is constructed, before table placement, event positioning, beam intersection, and dose accumulation.

Rationale for choosing (b) first: it can be implemented against the existing mesh files without sourcing new STL assets, and it gives immediate value for users who know approximate anthropometric dimensions.

## 2. Reviewed Implementation Notes

Important corrections from review:

- `phantom_class.py` currently uses `numpy-stl` (`stl.mesh.Mesh`), not PyVista or trimesh. Plan code should operate on `numpy` arrays after STL vectors are flattened into `Phantom.r`.
- `Phantom` does not currently receive `PyskindoseSettings` or `PhantomSettings`; it receives `phantom_model`, `phantom_dim`, and `human_mesh`. Add explicit constructor arguments such as `human_scale=(1.0, 1.0, 1.0)` instead of referring to `self.settings`.
- Use the local `Phantom.r` coordinate columns for implementation: column 0 = lateral/width, column 1 = AP/vertical thickness, column 2 = longitudinal/head-foot. Some docs and labels use different axis wording; tests should lock the behavior to these array columns.
- Do not scale human mesh points about the full mesh centroid. Existing positioning assumes human meshes have no positive longitudinal `z` values, with the head/top origin at `max(z) == 0`. Centroid-relative longitudinal scaling can create positive `z` values and break positioning/orientation tests. Scaling must preserve the existing local alignment anchors.
- Non-uniform scaling changes surface normals. `Beam.check_hit()` uses `patient.n` to distinguish entrance from exit skin cells, so normals must be recomputed or transformed after scaling.

## 3. Background & Relevant Code

- **Phantom meshes**: `src/mypyskindose/phantom_class.py` loads STL files with `mesh.Mesh.from_file(...)`. Human mesh triangle vertices are flattened into `self.r`; STL triangle normals are repeated into `self.n`.
- **Phantom placement**: `geom_calc.position_patient_phantom_on_table()` positions the already-constructed phantom and saves `r_ref`. Scaling must happen before this function is called.
- **Event positioning**: `Phantom.position()` starts each event from `r_ref`, applies table rotation, then applies table translation. Scaling should therefore be part of the saved reference geometry, not a per-event mutation.
- **Beam intersection**: `beam_class.py::Beam.check_hit()` tests whether patient points are inside the beam and uses `patient.n` for entrance-surface filtering.
- **Dose accumulation**: `calculate_dose/` accumulates dose to skin cells. `calculate_k_isq()` uses actual source-to-cell distances, so inverse-square correction will automatically reflect the scaled geometry.
- **Settings**: `PyskindoseSettings.phantom` is built from `PhantomSettings` in `src/mypyskindose/settings/phantom_settings.py`. This class is a plain initializer, not a dataclass.
- **GUI state/settings**: `src/mypyskindose/gui/state.py` stores UI values; `src/mypyskindose/gui/settings_builder.py::build_settings()` writes them into the settings dict before constructing `PyskindoseSettings`.
- **GUI controls**: `src/mypyskindose/gui/tabs/settings.py` owns the Settings -> Phantom Settings expansion.
- **Geometry preview**: `src/mypyskindose/gui/figures.py::make_geometry_fig()` builds settings and calls `create_geometry_plot()`.

## 4. Acceptance Criteria

1. **Three new phantom settings**: `scale_lat`, `scale_ap`, and `scale_lon`, each defaulting to `1.0`, are stored in `PhantomSettings`, mirrored in `gui/state.py`, included in `settings_example.json`, and round-trip through JSON/dict settings.
2. **Backward compatibility**: Existing settings files that omit the new fields still load with all scale factors set to `1.0`.
3. **Validation**: Scale values must be numeric and constrained to `[0.5, 2.0]`. GUI sliders naturally clamp. Non-GUI settings should clamp with a warning or raise a clear `ValueError`; choose one behavior and test it. If clamping is chosen, emit a core logger warning without importing GUI state into settings code.
4. **Constructor plumbing**: Every human `Phantom(...)` construction path that affects geometry or dose passes the scale tuple from `settings.phantom`. Table, pad, plane, and cylinder phantoms remain unchanged unless future work intentionally extends scaling to mathematical phantoms.
5. **Anchored directional scaling**: Scaling is applied once during human phantom construction after STL vertices are loaded and before `position_patient_phantom_on_table()`. The implementation preserves local alignment anchors, especially `max(r[:, 2]) <= 0` / head-origin behavior, rather than using the full mesh centroid for all axes.
6. **Normals correctness**: Surface normals are recomputed from the scaled triangle vertices or transformed by the inverse-transpose of the non-uniform scale matrix and re-normalized. `patient.n` length remains equal to `len(patient.r)`.
7. **Geometry preview**: The scaled mesh renders correctly in the Geometry tab, and changing a scale control invalidates old calculation results and requests a preview refresh through the same debounced preview mechanism used for geometry controls.
8. **Physics correctness**: Scaled mesh vertices and updated normals are used for beam intersection, inverse-square correction, and dose accumulation. At `scale_lat == scale_ap == scale_lon == 1.0`, baseline PSD and hit maps are unchanged.
9. **GUI controls**: Settings -> Phantom Settings shows three human-only controls: Lateral/width, AP/vertical thickness, and Longitudinal/head-foot. Each shows its current value and updates state.
10. **Docs**: Update `FEATURE_INVENTORY.md`, `AGENTS.md`, and `dev-docs/TO_DO.md` as part of the implementation PR. Add user-facing GUI help only if the controls need explanation beyond their labels.
11. **Tests**: Add focused unit/integration tests for settings defaults/validation, anchored scaling, normals, unchanged scale-1 behavior, and at least one beam/dose behavior change under non-default scaling.

## 5. Implementation Outline

### 5.1 Settings Model

**File: `src/mypyskindose/settings/phantom_settings.py`**

Add module logging before using warnings in validation:

```python
import logging

logger = logging.getLogger(__name__)
```

Add fields in `PhantomSettings.__init__` using `dict.get(...)` for backward compatibility:

```python
self.scale_lat = _validate_scale(ptm_dim.get("scale_lat", 1.0), "scale_lat")
self.scale_ap = _validate_scale(ptm_dim.get("scale_ap", 1.0), "scale_ap")
self.scale_lon = _validate_scale(ptm_dim.get("scale_lon", 1.0), "scale_lon")
```

Add a small module-level helper, for example:

```python
def _validate_scale(value: object, name: str) -> float:
    scale = float(value)
    if not 0.5 <= scale <= 2.0:
        logger.warning("%s=%s outside [0.5, 2.0]; clamping", name, scale)
        return min(2.0, max(0.5, scale))
    return scale
```

If the implementation chooses raising instead of clamping for non-GUI settings, update acceptance criteria and tests accordingly. Whichever behavior is chosen, keep it in the core settings layer and do not reference GUI state from this file.

Add the scale values to `to_printable_string()`.

**File: `src/mypyskindose/settings_example.json`**

Add the fields under the `phantom` section:

```json
"scale_lat": 1.0,
"scale_ap": 1.0,
"scale_lon": 1.0
```

**File: `src/mypyskindose/settings/pyskindose_settings.py`**

No direct parsing changes should be required because `PhantomSettings(ptm_dim=tmp["phantom"])` owns these fields. Update docstrings if useful.

### 5.2 GUI State and Settings Builder

**File: `src/mypyskindose/gui/state.py`**

Add:

```python
phantom_scale_lat: float = 1.0
phantom_scale_ap: float = 1.0
phantom_scale_lon: float = 1.0
```

**File: `src/mypyskindose/gui/settings_builder.py`**

Write the UI state into `base["phantom"]` before constructing `PyskindoseSettings`:

```python
base["phantom"]["scale_lat"] = app_state.phantom_scale_lat
base["phantom"]["scale_ap"] = app_state.phantom_scale_ap
base["phantom"]["scale_lon"] = app_state.phantom_scale_lon
```

Do not add these keys to `phantom.dimension`; they are human phantom settings, not mathematical phantom dimensions.

### 5.3 GUI Controls

**File: `src/mypyskindose/gui/tabs/settings.py`**

Add controls inside the existing "Phantom Settings" expansion after the patient offset section. Keep the controls visible only when `state.phantom_model == "human"`.

Prefer three compact rows or columns with explicit labels, using the existing UI style:

```python
scale_section = ui.column().classes("w-full gap-2 q-mt-sm")
scale_section.bind_visibility_from(state, "phantom_model", backward=lambda v: v == "human")

with scale_section:
    ui.label("Body habitus scaling").classes("text-caption text-grey-6")
    for label, attr in (
        ("Lateral / width", "phantom_scale_lat"),
        ("AP / vertical thickness", "phantom_scale_ap"),
        ("Longitudinal / head-foot", "phantom_scale_lon"),
    ):
        with ui.row().classes("w-full gap-4 items-center"):
            ui.label(label).classes("w-48 text-caption")
            ui.slider(min=0.5, max=2.0, step=0.05, value=getattr(state, attr)).bind_value(
                state, attr
            ).on("update:model-value", _on_phantom_scale_change).classes("grow")
            ui.label().bind_text_from(state, attr, backward=lambda v: f"{float(v):.2f}x").classes("mono-text")
```

Define `_on_phantom_scale_change()` near the other handlers. It should call `reset_results()` and request/mark a geometry preview refresh if the tab has a refresh hook available. If no hook exists yet, add one to `PageContext` rather than relying on `reset_results()` alone.

### 5.4 Human Phantom Scaling

**File: `src/mypyskindose/phantom_class.py`**

Extend `Phantom.__init__` with an optional scale argument:

```python
def __init__(
    self,
    phantom_model: str,
    phantom_dim: PhantomDimensions,
    human_mesh: Optional[Union[str, tuple[str, mesh.Mesh]]] = None,
    human_scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
):
```

For `phantom_model == "human"`, after flattening STL vectors into `self.r`, apply scaling and then update `self.n`.

Avoid centroid-relative scaling for every axis. Use an anchor policy that preserves current local alignment assumptions:

- lateral/width (`r[:, 0]`): scale around the lateral midpoint of the mesh bounds;
- AP/vertical thickness (`r[:, 1]`): preserve the existing bound used for table placement; start with `max(r[:, 1])` because the mathematical phantoms use `max(y) == 0`, and verify this against all shipped human meshes;
- longitudinal/head-foot (`r[:, 2]`): preserve `max(r[:, 2])`, keeping the head-origin/no-positive-z invariant.

Sketch:

```python
def _apply_human_scale(self, scale: tuple[float, float, float]) -> None:
    if np.allclose(scale, (1.0, 1.0, 1.0)):
        return

    sx, sy, sz = scale
    anchor = np.array([
        (self.r[:, 0].min() + self.r[:, 0].max()) / 2.0,
        self.r[:, 1].max(),
        self.r[:, 2].max(),
    ])
    self.r = anchor + (self.r - anchor) * np.array([sx, sy, sz])
    self._recompute_human_normals_from_triangles()
```

Because `self.r` is flattened in groups of three vertices per triangle, normals can be recomputed from each scaled triangle:

```python
def _recompute_human_normals_from_triangles(self) -> None:
    triangles = self.r.reshape(-1, 3, 3)
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    normals[lengths > 0] = normals[lengths > 0] / lengths[lengths > 0, None]
    self.n = np.repeat(normals, 3, axis=0)
```

Confirm the recomputed normal direction matches the existing STL normal orientation at `scale == 1.0`; if the cross-product order is reversed for these meshes, swap the cross-product operands.

The existing `numpy-stl` normals are not guaranteed to be unit length; for example, `hudfrid.stl` has varying original normal magnitudes. This is acceptable because `Beam.check_hit()` uses only the sign of the source-to-cell dot product with `patient.n`. Tests should verify same direction/sign behavior and unit length for recomputed nonzero normals, not equality to the original normal magnitudes.

### 5.5 Constructor Call Sites

Pass `human_scale=(settings.phantom.scale_lat, settings.phantom.scale_ap, settings.phantom.scale_lon)` anywhere a human patient phantom is constructed from settings:

- `src/mypyskindose/calculate_dose/calculate_dose.py`
- `src/mypyskindose/plotting/create_geometry_plot.py`
- any plotting or export path that reconstructs a patient phantom from settings, including the plane fallback in `create_dose_map_plot.py` if it is extended beyond plane-only behavior.

Table and pad constructors do not need scale arguments.

Also check tests and manual-test helpers that instantiate human `Phantom(...)` directly. Existing tests should continue to work through the default `(1.0, 1.0, 1.0)`.

### 5.6 Geometry Preview

The Geometry preview already calls `build_settings()` and creates the patient phantom through `create_geometry_plot()`, so scaled geometry will appear after settings and constructor plumbing are complete.

Do not assume `reset_results()` redraws the preview. The implementation should explicitly request a preview refresh or reuse the debounced refresh mechanism used by Geometry tab sliders.

Optionally show a compact read-only caption in the Geometry tab:

```text
Scale: lateral 1.00x | AP 1.00x | longitudinal 1.00x
```

Keep this caption secondary; the controls belong in Settings.

## 6. Test Plan

### 6.1 Unit Tests

Add or extend tests under `tests/unittests/`.

- **Settings defaults**: Existing `settings_example.json` and minimal old-style settings load with all scale factors equal to `1.0`.
- **Settings validation**: Out-of-range and non-numeric values follow the selected validation behavior.
- **No-op scale**: A human phantom with default scale has identical `r` values to the current unscaled baseline within floating-point tolerance.
- **Anchored longitudinal scaling**: Scaling `scale_lon=2.0` increases longitudinal extent while preserving the invariant that no human mesh point has positive `r[:, 2]`.
- **Lateral scaling**: Scaling `scale_lat=2.0` doubles lateral extent around the selected lateral midpoint.
- **AP scaling**: Scaling `scale_ap=2.0` changes vertical/AP extent while preserving the chosen table-placement anchor.
- **Normals shape and unit length**: `len(patient.n) == len(patient.r)` and nonzero normals are unit length after non-uniform scaling.
- **Normals orientation**: At scale `1.0`, recomputed normals match existing STL normals or intentionally preserve the same entrance/exit behavior.
- **Positioning**: Scaling happens before `position_patient_phantom_on_table()`, and `r_ref` contains the scaled geometry.

### 6.2 Integration Tests

- **Beam intersection changes**: For a synthetic geometry, a laterally scaled human phantom changes hit count or hit identity under a fixed beam.
- **Inverse-square changes**: A scale that changes source-to-skin distance changes `k_isq` for at least one hit cell.
- **Golden baseline unchanged**: Existing golden PSD/hit-map tests remain unchanged at default scale.

### 6.3 GUI Smoke Tests

- Settings -> Phantom Settings shows scale controls only for the human model.
- Changing a scale control updates `AppState`, clears prior calculation results, and triggers/requires a Geometry preview refresh.
- Exported settings JSON includes `scale_lat`, `scale_ap`, and `scale_lon`.

## 7. Future Work

When additional meshes are needed:

1. Generate or source STL files for the new body type.
2. Create `_reduced_1000t` variants using the existing mesh-reduction process.
3. Place them in `phantom_data/` alongside existing meshes.
4. Confirm `get_human_mesh_names()` discovers them.
5. Add notes in `FEATURE_INVENTORY.md` and `AGENTS.md`.
6. Consider presets such as "large habitus" only after real-world dimensions and clinical expectations are agreed.

This future work is complementary to scaling and should not block the scaling implementation.

## 8. Decision Log

| Decision | Rationale |
|----------|-----------|
| Start with directional scaling | Uses existing mesh assets and delivers value without a separate mesh-sourcing/licensing effort. |
| Keep settings on `PhantomSettings` | The scale factors are phantom geometry parameters and fit next to `model`, `human_mesh`, and `patient_orientation`. |
| Pass scale explicitly into `Phantom` | `Phantom` does not own the full settings object; explicit constructor data keeps dependencies narrow. |
| Preserve alignment anchors, not full centroid | Existing positioning assumes a head-origin/no-positive-z convention; centroid scaling can break that invariant. |
| Recompute or transform normals | Non-uniform scaling invalidates STL normals, and hit filtering depends on normal vectors. |
| Range `[0.5, 2.0]` | Broad enough for exploratory patient-size adjustment while reducing the chance of extreme degenerate geometry. |
| GUI controls are human-only | Plane and cylinder dimensions already have separate mathematical size settings; this plan targets STL human meshes. |
| Additional meshes deferred | New body-type assets are useful but require separate data, mesh generation, and licensing decisions. |

## 9. Progress Log

| Date | Status |
|------|--------|
| 2026-06-24 | Plan authored |
| 2026-06-25 | Review completed; implementation hazards and test requirements folded into plan |
| 2026-06-25 | External assessment reviewed; logger setup and normal-magnitude test guidance added |
| 2026-06-25 | Implementation shipped; plan archived |
