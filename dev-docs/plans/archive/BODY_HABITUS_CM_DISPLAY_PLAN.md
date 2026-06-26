# Body Habitus cm Display Plan

**Status:** Completed (2026-06-26). Archived after implementation.

Replace the bare scaling-factor readouts on the three body-habitus sliders
(`phantom_scale_lat`, `phantom_scale_ap`, `phantom_scale_lon`) with labels that
also show the **resulting mesh dimension in centimeters**, computed as
`baseline_extent × slider_factor` where `baseline_extent = (max − min)` of the
unscaled STL vertices along the slider's axis. Example: `1.00x` becomes
`1.00x  (182.7 cm)`.

---

## Background

- **Human meshes are T-pose with arms spread.** The HUDLFRI and other MakeHuman
  STLs are exported in a T-pose, so the lateral/width extent of the unscaled
  mesh is ~183 cm (fingertip to fingertip), not shoulder width. AP/vertical
  thickness (~30 cm) and longitudinal/head-foot extent (~175 cm) match typical
  adult values. The display shows the **actual STL
  extent**, which is what the scaling math is anchored against.
- **Axis convention.** `col 0 = lateral, col 1 = AP, col 2 = longitudinal` —
  this is the convention used by `_apply_human_scale` in the human-mesh scaling
  branch of `src/mypyskindose/phantom_class.py` and the archived
  `dev-docs/plans/archive/PATIENT_SIZE_SCALING_PLAN.md` §2. The display is
  consistent with existing scaling logic, not with the `(LON, VER, LAT)`
  hover-label convention in `figures.py` / `create_geometry_plot_texts.py`
  (a separate, pre-existing inconsistency that is out of scope here).
- **`tests/unittests/`** is the home for pure helpers; the existing `tests/gui/`
  exercises NiceGUI flows under the `gui` extra. `get_mesh_baseline_extents`
  and the pure formatter are pure helpers and belong in `tests/unittests/`.
- **Human mesh is global GUI state.** `state.human_mesh` is a single shared
  value, not per-exam. Multi-exam calculations still use one selected mesh, so
  switching the mesh updates all three cm labels through the same `human_mesh`
  binding.

---

## Acceptance criteria

1. Each of the three scaling sliders in **Settings → Phantom Settings → Body
   habitus scaling** shows `N.NNx  (XX.X cm)` next to the slider, updated live
   as the slider moves.
2. The cm value reflects the **currently selected human mesh** — switching
   between meshes (e.g. `hudfrid` ↔ `junior_female`) recomputes the baseline
   and updates all three labels.
3. Baseline extents are computed once per mesh name and cached for the
   process lifetime (no repeated STL loads on slider drag).
4. Corrupt or unreadable STLs, unknown mesh names, and empty `human_mesh`
   strings render as `—` (em-dash) in the cm position, with the cm value
   cached as `(0.0, 0.0, 0.0)` so a transient read failure does not retry on
   every render.
5. The format-string uses ASCII `x` (literal letter) for the multiplier in
   the rendered text, matching the existing `phantom_scale_*` slider labels in
   `src/mypyskindose/gui/tabs/settings.py`.
6. Imports stay within `numpy-stl` (`from stl import mesh`) and stdlib
   `pathlib` / `logging` — all already in `pyproject.toml` dependencies or
   already imported in `helpers.py`. Do **not** add `numpy`; it is unnecessary
   for this helper and would be unused in the proposed implementation.
7. Existing scaling behaviour is unchanged — this is **display-only**.
8. The longer cm labels do not squeeze the slider track or overflow their row;
   use a fixed-width, non-shrinking value label and a slider min-width, matching
   the layout guard used by the archived Geometry slider-label reposition work.

---

## Implementation

### 1. `src/mypyskindose/gui/helpers.py` — add `get_mesh_baseline_extents`

Add the import after the existing stdlib import block and before the first
GUI submodule import. Use `from stl import mesh as stl_mesh`; the alias avoids
shadowing the natural word "mesh" elsewhere in the file.

Add the function and cache **at the end of the file, after
`get_human_mesh_names`**, for logical grouping with the other mesh-related
helper. Add `"get_mesh_baseline_extents"` to `__all__` between
`"get_human_mesh_names"` and `"load_rdsr"` to preserve alphabetical order.
Change `get_human_mesh_names()` to use `_PHANTOM_DATA_DIR` too, so both mesh
helpers share the same path source and tests can monkeypatch one value.

```python
from stl import mesh as stl_mesh

_PHANTOM_DATA_DIR = Path(__file__).parent.parent / "phantom_data"
_MESH_EXTENT_CACHE: dict[str, tuple[float, float, float]] = {}
_gui_logger = logging.getLogger("mypyskindose.gui.helpers")


def get_human_mesh_names() -> list[str]:
    """Return available human mesh names (full-resolution only)."""
    return sorted(p.stem for p in _PHANTOM_DATA_DIR.glob("*.stl") if not p.stem.endswith("_reduced_1000t"))


def get_mesh_baseline_extents(mesh_name: str) -> tuple[float, float, float]:
    """Return (lat_extent, ap_extent, lon_extent) in cm for the unscaled mesh.

    Each extent is ``max - min`` along axis 0/1/2 of the STL vertex array,
    matching the column order used by ``_apply_human_scale`` in
    ``phantom_class.py`` and the archived PATIENT_SIZE_SCALING_PLAN.

    Results are cached per mesh name. Corrupt or unreadable STLs are
    cached as ``(0.0, 0.0, 0.0)`` so the GUI can render ``—`` and a
    transient read failure does not retry on every render.
    """
    if mesh_name in _MESH_EXTENT_CACHE:
        return _MESH_EXTENT_CACHE[mesh_name]

    phantom_path = _PHANTOM_DATA_DIR / f"{mesh_name}.stl"
    if not phantom_path.exists():
        _MESH_EXTENT_CACHE[mesh_name] = (0.0, 0.0, 0.0)
        return _MESH_EXTENT_CACHE[mesh_name]

    try:
        m = stl_mesh.Mesh.from_file(str(phantom_path))
        verts = m.vectors.reshape(-1, 3)
        if verts.size == 0:
            raise ValueError("STL contains no triangles")
        extents = (
            float(verts[:, 0].max() - verts[:, 0].min()),
            float(verts[:, 1].max() - verts[:, 1].min()),
            float(verts[:, 2].max() - verts[:, 2].min()),
        )
    except Exception as exc:
        _gui_logger.warning(
            "Could not read baseline extents for human mesh %r (%s); "
            "rendering cm display as '—'.",
            mesh_name, exc,
        )
        extents = (0.0, 0.0, 0.0)

    _MESH_EXTENT_CACHE[mesh_name] = extents
    return extents
```

The private `_MESH_EXTENT_CACHE` is module-local; tests can reset it with
`helpers._MESH_EXTENT_CACHE.clear()`.

### 2. `src/mypyskindose/gui/summary_formatters.py` — add pure formatter

The existing pattern (`format_table_offset_line`, `format_patient_offsets`,
`multi_exam_phantom_offset_caption`) is to keep pure formatting functions in
this module and have `tabs/settings.py` provide a thin wrapper that closes
over the shared `state`. Add a pure function here so the formatting math is
testable without NiceGUI:

```python
def format_scale_cm_label(scale_factor: float, axis: int, extents: tuple[float, float, float]) -> str:
    """Format the `1.00x  (XX.X cm)` label for a body-habitus slider.

    `axis` selects the lateral/AP/longitudinal extent in `extents`
    (matching the ``(scale_lat, scale_ap, scale_lon)`` tuple order used
    by ``_apply_human_scale``). Returns the ``—`` sentinel when the
    extent is zero (unknown / unreadable mesh).
    """
    if extents[axis] == 0.0:
        return f"{scale_factor:.2f}x  (—)"
    cm = scale_factor * extents[axis]
    return f"{scale_factor:.2f}x  ({cm:.1f} cm)"
```

### 3. `src/mypyskindose/gui/tabs/settings.py` — add wrapper, multi-bind labels

Add `get_mesh_baseline_extents` to the existing grouped helper import at the
top of the file, and add `format_scale_cm_label` to the existing
`summary_formatters` import:

```python
from ..helpers import (
    any_table_origin_override,
    fallback_normalization_exam_count,
    get_mesh_baseline_extents,     # ADD
    on_global_patient_offset_change,
)
...
from ..summary_formatters import (
    format_scale_cm_label,                       # ADD
    format_table_offset_line,
    multi_exam_phantom_offset_caption,
)
```

Add `_format_scale_cm` as a thin wrapper between `_format_table_offset_line`
and `build`, matching the existing wrapper pattern:

```python
def _format_scale_cm(scale_factor: float, axis: int) -> str:
    extents = get_mesh_baseline_extents(state.human_mesh)
    return format_scale_cm_label(scale_factor, axis, extents)
```

Replace the current slider loop body with a multi-bind that re-renders when
either the slider value or the mesh name changes. This matches the existing
multi-source label-binding precedent used by `table_offset_label` in the same
file. Both backward lambdas capture `axis` and `attr` by default-argument value
to avoid the loop-closure pitfall:

```python
for label, attr, axis in (
    ("Lateral / width",          "phantom_scale_lat", 0),
    ("AP / vertical thickness",  "phantom_scale_ap", 1),
    ("Longitudinal / head-foot", "phantom_scale_lon", 2),
):
    with ui.row().classes("w-full gap-4 items-center"):
        ui.label(label).classes("w-48 text-caption")
        ui.slider(
            min=0.5, max=2.0, step=0.05,
            value=getattr(state, attr),
        ).bind_value(state, attr).on(
            "update:model-value", _on_phantom_scale_change
        ).classes("grow min-w-[100px]")

        _lbl = ui.label().classes("w-40 shrink-0 text-caption mono-text text-right")
        _lbl.bind_text_from(
            state, attr,
            backward=lambda v, a=axis: _format_scale_cm(v, a),
        )
        _lbl.bind_text_from(
            state, "human_mesh",
            backward=lambda _v, a=attr, x=axis: _format_scale_cm(
                getattr(state, a), x
            ),
        )
```

`_on_phantom_scale_change` and the existing `mesh_select.update:model-value`
handler need no changes — the multi-bind on the label is reactive. Keep the
initial label text empty (`ui.label()`) because the first bind populates it
when the element is created, matching the existing slider labels in this file.
The fixed `w-40` value-label width comfortably fits the longest expected label
(`2.00x  (365.5 cm)` for the widest current mesh at max scale) while preserving
a usable slider track through `min-w-[100px]`.

## Edge cases

| Case | Behaviour |
|------|-----------|
| Mesh name is unknown or empty | `get_mesh_baseline_extents` returns `(0.0, 0.0, 0.0)`; label shows `1.00x  (—)` |
| STL file missing on disk | Same as above |
| STL file is zero-byte, garbage, or truncated | `get_mesh_baseline_extents` logs a warning via the `mypyskindose.gui.helpers` logger and caches `(0.0, 0.0, 0.0)`; label shows `—`. The cache prevents retrying the broken read on every render |
| Slider at min/max on `hudfrid` | `0.50x` shows half baseline (`91.4 / 15.0 / 87.3 cm`); `2.00x` shows double baseline (`365.5 / 59.9 / 349.4 cm`) for lateral / AP / longitudinal |

---

## Files changed

| File | Change |
|------|--------|
| `src/mypyskindose/gui/helpers.py` | Add `from stl import mesh as stl_mesh`, `_PHANTOM_DATA_DIR`, `_gui_logger`, `_MESH_EXTENT_CACHE`, and `get_mesh_baseline_extents()` near the mesh helpers; refactor `get_human_mesh_names()` to read its path from `_PHANTOM_DATA_DIR` (behavior-preserving: same return type, same sorting, same `_reduced_1000t` filter); add `"get_mesh_baseline_extents"` to `__all__` between `"get_human_mesh_names"` and `"load_rdsr"` |
| `src/mypyskindose/gui/summary_formatters.py` | Add `format_scale_cm_label()` (pure, takes extents explicitly) |
| `src/mypyskindose/gui/tabs/settings.py` | Add `get_mesh_baseline_extents` and `format_scale_cm_label` to existing grouped imports; add `_format_scale_cm()` between `_format_table_offset_line` and `build`; replace the current `phantom_scale_*` label `bind_text_from` with the multi-bind in the slider loop; give the longer value label a fixed width and the slider a minimum width |
| `src/mypyskindose/gui/state.py` | No changes; labels are computed from existing state in `bind_text_from` callbacks |

---

## Test plan

1. **Manual**: Launch GUI, select a human mesh, verify three sliders show `N.NNx  (XX.X cm)`.
2. **Manual**: Drag each slider — cm values update live.
3. **Manual**: Switch mesh in dropdown — cm values recalculate (e.g. `hudfrid` → `junior_female` drops lateral from ~183 cm to ~126 cm).
4. **Manual**: Select non-human phantom (plane/cylinder) — scaling section hides (existing behaviour, must still hold).
5. **Edge**: Cover both unknown and empty mesh values:
   - Set `state.human_mesh = "nonsense"` — labels show `—`, no crash, and the
     broken value is cached under `"nonsense"` (verify by dragging the slider
     and seeing that the same `—` persists).
   - Set `state.human_mesh = ""` — labels show `—`, no crash, and the broken
     value is cached under `""`.
6. **Regression**: Verify unscaled (`1.00x`) shows the baseline extent from the STL.
7. **Automated**: Unit-test `get_mesh_baseline_extents` in `tests/unittests/test_gui_helpers.py`:
   - start each cache-sensitive test with `helpers._MESH_EXTENT_CACHE.clear()`
   - cache miss → cache hit returns identical tuple, and monkeypatching
     `helpers.stl_mesh.Mesh.from_file` after the first call proves the second
     call does not hit disk again
   - unknown mesh name returns `(0.0, 0.0, 0.0)` and stores that tuple under
     the unknown name in `helpers._MESH_EXTENT_CACHE`
   - each of the 7 full-resolution meshes (`adult_female`, `adult_male`, `hudfrid`, `junior_female`, `junior_male`, `senior_female`, `senior_male` — note that `get_human_mesh_names` filters out the `*_reduced_1000t` reduced-resolution variants) returns positive extents in all three axes
   - **axis-order invariant**: `extents[0]` is the col-0 extent (lateral, matches the scale_lat anchor at the X-midpoint in `_apply_human_scale`); `extents[1]` is col-1 (AP); `extents[2]` is col-2 (longitudinal). Lock with a parametrized assertion per mesh so a future mesh-import orientation swap is caught.
   - corrupt-STL resilience: write a zero-byte / garbage `broken.stl` to
     `tmp_path`, monkeypatch `helpers._PHANTOM_DATA_DIR = tmp_path`, and assert
     `helpers.get_mesh_baseline_extents("broken") == (0.0, 0.0, 0.0)` without
     raising
8. **Automated**: Unit-test `format_scale_cm_label` in `tests/unittests/test_gui_summary_formatters.py` — normal case returns `f"{factor:.2f}x  ({cm:.1f} cm)"`, zero-extent case returns `f"{factor:.2f}x  (—)"`, both with literal ASCII `x`.
9. **Automated**: GUI smoke test in `tests/gui/test_gui_flows.py` — set
   `state.phantom_model = "human"` and `state.human_mesh = "hudfrid"` before
   opening the page, then assert the three scale labels contain the literal
   substring `"cm"` (catches a missing bind without coupling to exact strings).
   Clear/restore any mutated global `state` fields in the test so later GUI
   tests do not inherit the modified mesh/model.

---

## Verification checklist

- [x] Baseline extents load correctly for all 7 full-resolution meshes
- [x] All three slider labels render `N.NNx  (XX.X cm)` and use literal ASCII `x`
- [x] cm labels update on slider drag (live, not just on release)
- [x] cm labels update on mesh switch (cache hit after first lookup)
- [x] Unknown mesh name shows `—`, no crash, cached so a drag does not retry the lookup
- [x] Corrupt or unreadable STL shows `—`, no crash, warning logged once
- [x] Non-human phantom model hides the scaling section entirely
- [x] Multi-exam: switching mesh in dropdown updates all labels
- [x] Closure-capture correctness: each label uses its own `attr`/`axis` (no cross-talk when one slider is dragged)
- [x] Multi-bind pattern matches the existing `table_offset_label` precedent in `src/mypyskindose/gui/tabs/settings.py`
- [x] Layout remains readable at min/max values: value label fits in its fixed
      width and the slider track stays usable beside it
- [x] `__all__` list in `helpers.py` remains alphabetically sorted after the new entry is inserted
- [x] `ruff check`, `basedpyright`, and `pytest tests/unittests/ -k "mesh or scale"` all pass on the modified files
