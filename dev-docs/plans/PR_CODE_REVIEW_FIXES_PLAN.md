# PR Code Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve all CodeRabbit pull request review comments (critical, major, and nitpicks) on branch `refactor/sonar-lizard-fixes` with safe CI timeout coverage.

**Architecture:** Address each identified code issue with robust, targeted fixes. We will replace assertions with proper validations, correct calculation indexing, safe-guard degenerate physics interpolation, implement lightweight representations, and enforce timeouts on script executions.

**Tech Stack:** Python 3.11+, pytest, pandas, numpy, scipy, argparse

## Global Constraints

- Target line length: 120 characters (enforced by ruff).
- All units remain in cm unless noted.
- Keep modifications minimal and preserve existing documentation/comments.
- Add specific unit tests to verify each changed component.
- All file paths in documentation must be repo-relative (no absolute paths or `file://` URIs).

---

## Pre-Implementation Verification

Before starting implementation, complete these verification steps:

- [ ] **Verify target branch exists:** Run `git branch -a | grep refactor/sonar-lizard-fixes` to confirm the target branch exists
- [ ] **Create feature branch:** Create a feature branch from `refactor/sonar-lizard-fixes` for testing fixes
- [ ] **Verify test infrastructure:** Run `pytest tests/unittests/ -v` to establish baseline and confirm all test files exist
- [ ] **Verify function signatures:** Check that all functions to be modified exist and have matching signatures
- [ ] **Verify imports exist:** Confirm all imports used in code snippets exist in the specified modules
- [ ] **Verify constants exist:** Check that constants like `STATUS_CLAMPED`, `STATUS_INTERPOLATED`, `STATUS_EXACT` exist in `grid_interp.py`
- [ ] **Verify dataclass fields:** Confirm `PySkinDoseOutput` dataclass has all fields referenced in the test
- [ ] **Backup current state:** Consider creating a backup commit before starting changes

---

### Task 1: Phantom Class Resolution and Error Message Fixes

**Files:**
- Modify: `src/guiskindose/phantom_class.py`
- Test: `tests/unittests/test_phantom_vertices.py`

**Interfaces:**
- Consumes: `PhantomDimensions` configuration
- Produces: Correctly validated resolution inputs and typo-free human mesh specification error checks.

- [ ] **Step 1: Write a failing test for invalid plane/cylinder resolution inputs**

Add the following tests to `tests/unittests/test_phantom_vertices.py` (ensure `import pytest` is present at the top of the file):

*Pre-flight verification:* Verify that `PhantomDimensions.__init__` signature in `src/guiskindose/settings/phantom_dimensions.py` accepts a `ptm_dim: dict` parameter, not keyword arguments. The test must mutate an existing settings instance rather than construct with keyword arguments.

```python
import pytest

def test_invalid_plane_resolution_raises_value_error() -> None:
    from guiskindose.phantom_class import Phantom
    from guiskindose.settings import PyskindoseSettings, load_settings_example_json
    settings = PyskindoseSettings(settings=load_settings_example_json())
    dim = settings.phantom.dimension
    dim.plane_resolution = "invalid_res"
    with pytest.raises(ValueError, match="Unsupported plane_resolution"):
        Phantom(phantom_model="plane", phantom_dim=dim)

def test_invalid_cylinder_resolution_raises_value_error() -> None:
    from guiskindose.phantom_class import Phantom
    from guiskindose.settings import PyskindoseSettings, load_settings_example_json
    settings = PyskindoseSettings(settings=load_settings_example_json())
    dim = settings.phantom.dimension
    dim.cylinder_resolution = "invalid_res"
    with pytest.raises(ValueError, match="Unsupported cylinder_resolution"):
        Phantom(phantom_model="cylinder", phantom_dim=dim)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unittests/test_phantom_vertices.py -k "resolution_raises_value_error" -v`
Expected: FAIL (raises AssertionError due to the old assert validation in `phantom_class.py`)

- [ ] **Step 3: Update resolution checks and fix spacing in `phantom_class.py`**

In `_init_plane` of `src/guiskindose/phantom_class.py`, add the `else: raise ValueError` block, delete the now-redundant `assert res_width is not None` and `assert res_length is not None` lines (lines 123-124), and add proper type annotations to avoid static analysis errors:

```python
    def _init_plane(self, phantom_dim: PhantomDimensions) -> None:
        """Create a plane phantom (2D rectangular grid); set self.r, self.ijk, self.dose."""
        # Resolution variables — set below depending on the plane_resolution setting.
        res_length: float
        res_width: float

        # Use a dense grid if specified by user
        if phantom_dim.plane_resolution.lower() == "dense":
            res_length = res_width = 2.0

        elif phantom_dim.plane_resolution.lower() == "sparse":
            res_length = res_width = 1.0

        else:
            raise ValueError(
                f"Unsupported plane_resolution: '{phantom_dim.plane_resolution}'. "
                "Allowed values are 'dense' or 'sparse'."
            )
```

Also, fix the space typo in `_load_human_mesh` error message in `src/guiskindose/phantom_class.py`:

```python
        if human_mesh is None:
            raise ValueError('Human model needs to be specified for phantom_model = "human"')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unittests/test_phantom_vertices.py -k "resolution_raises_value_error" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/guiskindose/phantom_class.py tests/unittests/test_phantom_vertices.py
git commit -m "fix: replace phantom resolution asserts with ValueError, add type annotations, and fix error message spacing"
```

---

### Task 2: Human Mesh Index and Test Repair

**Files:**
- Modify: `src/guiskindose/phantom_class.py`
- Modify: `tests/unittests/test_phantom_vertices.py`

**Interfaces:**
- Consumes: Loaded mesh vector arrays
- Produces: Correct triangle indexing arrays `self.ijk` containing all triangles.

- [ ] **Step 1: Write a failing test checking correct human mesh triangle count**

Modify `test_human_mesh_index_vectors_present_after_refactor` in `tests/unittests/test_phantom_vertices.py`:

```python
def test_human_mesh_index_vectors_present_after_refactor() -> None:
    """``Phantom.ijk`` must remain the triangle-index array (n_triangles, 3)."""
    p = _hudfrid_phantom()
    ijk = np.asarray(p.ijk)
    assert ijk.ndim == 2
    assert ijk.shape[1] == 3
    # Verify triangle count: vertices = triangles × 3
    assert len(p.r) == ijk.shape[0] * 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unittests/test_phantom_vertices.py::test_human_mesh_index_vectors_present_after_refactor -v`
Expected: FAIL (test will fail due to incorrect triangle count; actual failure mode TBD)

- [ ] **Step 3: Fix bounds of `np.arange` calls in `_load_human_mesh`**

Update `self.ijk` calculation in `src/guiskindose/phantom_class.py`:

```python
        # Create index vectors for plotly mesh3d plotting
        self.ijk = np.column_stack(
            (np.arange(0, len(self.r), 3), np.arange(1, len(self.r), 3), np.arange(2, len(self.r), 3))
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unittests/test_phantom_vertices.py::test_human_mesh_index_vectors_present_after_refactor -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/guiskindose/phantom_class.py tests/unittests/test_phantom_vertices.py
git commit -m "fix: correct human mesh triangle indexing bounds and check count in test"
```

---

### Task 3: Degenerate Interpolation Handling

**Files:**
- Modify: `src/guiskindose/corrections.py`
- Modify: `tests/unittests/test_corrections.py`

**Interfaces:**
- Consumes: Pivot tables loaded from DB/cache
- Produces: Corrected physics correction values for single-row kVp grids.

- [ ] **Step 1: Write a failing test for degenerate kVp slice interpolation**

Add the following test to `tests/unittests/test_corrections.py`:

*Pre-flight verification:* Confirm that `STATUS_CLAMPED`, `STATUS_INTERPOLATED`, and `STATUS_EXACT` constants exist in `src/guiskindose/grid_interp.py`. Adjust import if needed. Also verify that `clamped_rgi_lookup` is defined in `src/guiskindose/grid_interp.py` or `src/guiskindose/corrections.py`. If it doesn't exist, add it to the corrections module.

```python
def test_interpolate_off_grid_degenerate_kv_axis() -> None:
    from guiskindose.corrections import _interpolate_off_grid
    from guiskindose.grid_interp import STATUS_CLAMPED, STATUS_INTERPOLATED, STATUS_EXACT
    import pandas as pd
    import numpy as np

    piv = pd.DataFrame(
        data=[[0.8, 0.9]], 
        index=[80.0], 
        columns=[0.3, 0.6]
    )
    piv.index.name = "kvp_kv"
    piv.columns.name = "filtration_added_mmcu"

    cache_key = ("AXIOM-Artis", "Single Plane", 0.0)
    pivot_cache = {cache_key: piv}

    dummy_rows = pd.DataFrame({"filtration_added_mmal": [0.0]})

    # Interpolate along Cu axis only (midway between 0.8 and 0.9 is 0.85)
    val, status = _interpolate_off_grid(
        rows=dummy_rows, model="AXIOM-Artis", plane="Single Plane", 
        kvp=80.0, cu=0.45, al=0.0, pivot_cache=pivot_cache
    )
    assert abs(val - 0.85) < 1e-5
    assert status == STATUS_INTERPOLATED

    # Query with KVp out of bounds (clamped to 80.0)
    val, status = _interpolate_off_grid(
        rows=dummy_rows, model="AXIOM-Artis", plane="Single Plane", 
        kvp=90.0, cu=0.45, al=0.0, pivot_cache=pivot_cache
    )
    assert abs(val - 0.85) < 1e-5
    assert status == STATUS_CLAMPED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unittests/test_corrections.py::test_interpolate_off_grid_degenerate_kv_axis -v`
Expected: FAIL (raises ValueError/TypeError from `RegularGridInterpolator` due to dimension mismatch)

- [ ] **Step 3: Update `_interpolate_off_grid` in `src/guiskindose/corrections.py` to handle 1D kVp grids**

Show the full updated `_interpolate_off_grid` function to avoid context dependency errors:

```python
def _interpolate_off_grid(
    rows: pd.DataFrame,
    model: str,
    plane: str,
    kvp: float,
    cu: float,
    al: float,
    pivot_cache: dict[tuple[str, str, float], pd.DataFrame],
) -> tuple[float, str]:
    """Snap Al to the nearest measured grid value, build-or-reuse the
    ``(kVp × Cu)`` pivot for this ``(model, plane, Al)`` slice, and run a
    clamped ``RegularGridInterpolator`` lookup.

    ``pivot_cache`` is initialised by ``calculate_k_tab`` and threaded through
    each event so the pivot table is only built once per ``(model, plane,
    Al-snapped)`` key. The key is derived from the *input* ``model``/``plane``
    (not ``rows``) so callers using a spaced alias and the de-spaced DB form
    share a single cache slot, matching the pre-refactor behaviour.

    Returns ``(value, status)`` where ``status`` is ``STATUS_CLAMPED`` if Al was
    snapped off the query or the rgi lookup clamped, else the underlying
    ``STATUS_EXACT`` / ``STATUS_INTERPOLATED``.
    """
    al_grid = np.sort(np.unique(rows["filtration_added_mmal"].to_numpy(dtype=float)))
    al_snap = float(al_grid[int(np.abs(al_grid - round(al)).argmin())])

    cache_key = (model, str(plane), al_snap)
    piv = pivot_cache.get(cache_key)
    if piv is None:
        sl = rows[rows["filtration_added_mmal"] == al_snap]
        piv = sl.pivot_table(index="kvp_kv", columns="filtration_added_mmcu", values="k_patient_support")
        pivot_cache[cache_key] = piv

    cu_axis = piv.columns.to_numpy(dtype=float)
    al_clamped = al_snap != round(al)
    if len(cu_axis) >= 2:
        kv_axis = piv.index.to_numpy(dtype=float)
        if len(kv_axis) >= 2:
            rgi = RegularGridInterpolator((kv_axis, cu_axis), piv.to_numpy(dtype=float))
            value, status = clamped_rgi_lookup(rgi, kv_axis, cu_axis, kvp, cu)
        else:
            # Single kVp row, multiple Cu columns
            kv_c = kv_axis[0]
            cu_c = float(np.clip(cu, cu_axis[0], cu_axis[-1]))
            value = float(np.interp(cu_c, cu_axis, piv.to_numpy(dtype=float)[0, :]))
            was_clamped = (kv_c != round(kvp)) or (cu_c != cu)
            if was_clamped:
                status = STATUS_CLAMPED
            elif bool(np.any(np.isclose(cu_axis, cu_c))):
                status = STATUS_EXACT
            else:
                status = STATUS_INTERPOLATED
    else:
        # Single Cu column — no Cu axis to interpolate; the integer kVp node is
        # exact after clamping to the table's kVp range.
        kv_axis = piv.index.to_numpy(dtype=float)
        kv_c = float(np.clip(round(kvp), kv_axis[0], kv_axis[-1]))
        value = float(np.interp(kv_c, kv_axis, piv.to_numpy(dtype=float)[:, 0]))
        # For single Cu column, cu must match the only available value
        cu_single = cu_axis[0] if len(cu_axis) > 0 else 0.0
        status = STATUS_CLAMPED if (kv_c != round(kvp) or cu != cu_single) else STATUS_EXACT

    return value, STATUS_CLAMPED if (al_clamped or status == STATUS_CLAMPED) else status
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unittests/test_corrections.py::test_interpolate_off_grid_degenerate_kv_axis -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/guiskindose/corrections.py tests/unittests/test_corrections.py
git commit -m "fix: handle degenerate 1-row kVp grids in off-grid attenuation interpolation"
```

---

### Task 4: Lightweight Repr for Export Output

**Files:**
- Modify: `src/guiskindose/format_export_data.py`
- Test: `tests/unittests/test_export_data_post_init.py`

**Interfaces:**
- Consumes: Export result variables
- Produces: A clean, lightweight custom string representation for `PySkinDoseOutput` objects.

- [ ] **Step 1: Write a failing test for `PySkinDoseOutput.__repr__`**

Add the following test to `tests/unittests/test_export_data_post_init.py`:

*Pre-flight verification:* Verify that `PySkinDoseOutput` in `src/guiskindose/format_export_data.py` has fields with `field(init=False)` and cannot be constructed directly. The test must bypass `__init__` using `object.__new__()`. Also confirm the type and default value of `PatientOffsets` in `PySkinDoseOutput` to ensure the repr will render correctly.

```python
def test_pyskindose_output_lightweight_repr() -> None:
    from guiskindose.format_export_data import PySkinDoseOutput

    # Bypass __init__ and __post_init__ validations since fields have init=False
    out = object.__new__(PySkinDoseOutput)
    out.PSD = 1.2345
    out.AirKerma = 4.5678
    out.AirKermaCorrected = 4.0
    out.PadThickness = 2.0
    out.PatientOffsets = {"long": 10.0, "vert": 5.0, "lat": -2.0}

    repr_str = repr(out)
    assert "PSD=1.2345" in repr_str
    assert "AirKerma=4.5678" in repr_str
    assert "data_norm" not in repr_str
    assert "dose_map" not in repr_str
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unittests/test_export_data_post_init.py -k "lightweight_repr" -v`
Expected: FAIL (or returns standard huge dataclass representation containing all arrays/frames)

- [ ] **Step 3: Define `__repr__` method on `PySkinDoseOutput`**

Add `__repr__` method to the end of the `PySkinDoseOutput` class in `src/guiskindose/format_export_data.py`:

```python
    def __repr__(self) -> str:
        return (
            f"PySkinDoseOutput(PSD={self.PSD:.4f}, AirKerma={self.AirKerma:.4f}, "
            f"AirKermaCorrected={self.AirKermaCorrected:.4f}, PadThickness={self.PadThickness:.4f}, "
            f"PatientOffsets={self.PatientOffsets})"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unittests/test_export_data_post_init.py -k "lightweight_repr" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/guiskindose/format_export_data.py tests/unittests/test_export_data_post_init.py
git commit -m "feat: implement lightweight safe __repr__ on PySkinDoseOutput"
```

---

### Task 5: GUI Exam Loader Study ID Association

**Files:**
- Modify: `src/guiskindose/gui/exam_loaders.py`

**Interfaces:**
- Consumes: Re-parsed input tables
- Produces: Association of preserved coordinate transform flags keyed by `study_id` instead of fragile positional alignment.

- [ ] **Step 1: Update metadata entry construction with study ID**

*Pre-flight validation check:* Verify that the `InputAdapterResult` dataclass exposes `study_id: str | None = field(default=None)` in `src/guiskindose/input_adapters/models.py`. (Confirmed: it is already present in `models.py:30`).
*Ordering constraint:* Note that Step 1 (updating the signature and dictionary returned by `_build_exam_meta_entry`) must be applied before Step 3 (updating `_append_multi_study_exams` and `_append_single_study_exam` callers) to prevent keyword argument `TypeError` failures.

In `src/guiskindose/gui/exam_loaders.py`, update the full function `_build_exam_meta_entry` to avoid truncation. Ensure `"normalization_method": "Tabular"` is retained:

```python
def _build_exam_meta_entry(
    state: AppState,
    file_path: Path,
    schema_name: str,
    base: pd.DataFrame,
    provenance,
    warnings,
    flags: dict,
    seed_d_lon: float,
    seed_d_ver: float,
    seed_d_lat: float,
    study_id: str | None = None,
) -> dict:
    """Construct a per-exam meta entry shared by single and multi-study paths."""
    return {
        "file_name": file_path.name,
        "file_path": file_path,
        "source_type": file_path.suffix.lstrip("."),
        "schema": schema_name,
        "sheet": state.input_sheet_name,
        "provenance": provenance,
        "warnings": list(warnings),
        "base_data": base,
        "study_id": study_id,
        "swap_lat_lon": flags["swap_lat_lon"],
        "flip_ap1": flags["flip_ap1"],
        "flip_ap2": flags["flip_ap2"],
        "flip_tx": flags.get("flip_tx", False),
        "flip_ty": flags.get("flip_ty", False),
        "flip_tz": flags.get("flip_tz", False),
        # Tabular exports carry no normalization trans_offset, so the
        # auto-detected origin is zero; a manual override (Phase 2.5) is
        # then an absolute table-origin shift.
        "table_origin_detected": {"x": 0.0, "y": 0.0, "z": 0.0},
        "table_origin_override": None,
        "d_lon": seed_d_lon,
        "d_ver": seed_d_ver,
        "d_lat": seed_d_lat,
        "normalization_method": "Tabular",
    }
```

- [ ] **Step 2: Verify helper functions exist and collect `study_id` in `_collect_preserved_flags`**

*Pre-flight verification:* Confirm that `_blank_transform_flags()` and `_default_transform_flags(state)` exist in `src/guiskindose/gui/exam_loaders.py`. If `_blank_transform_flags()` doesn't exist, add it. **Important:** Do NOT overwrite `_default_transform_flags(state)` if it already exists - it reads user settings and should be preserved. If `_default_transform_flags` exists with a different signature (e.g., no `state` parameter), report the difference and adjust the step accordingly.

```python
def _blank_transform_flags() -> dict:
    """Return a blank transform flags dictionary with all defaults set to False."""
    return {
        "swap_lat_lon": False,
        "flip_ap1": False,
        "flip_ap2": False,
        "flip_tx": False,
        "flip_ty": False,
        "flip_tz": False,
    }
```

Then update `_collect_preserved_flags` in `src/guiskindose/gui/exam_loaders.py`:

```python
def _collect_preserved_flags(
    state: AppState, file_path: Path, replace_existing: bool
) -> list[dict]:
    """Collect per-exam coordinate-transform flags from prior loads of file_path."""
    if not replace_existing:
        return []
    return [
        {
            "study_id": m.get("study_id"),
            "swap_lat_lon": m.get("swap_lat_lon", False),
            "flip_ap1": m.get("flip_ap1", False),
            "flip_ap2": m.get("flip_ap2", False),
            "flip_tx": m.get("flip_tx", False),
            "flip_ty": m.get("flip_ty", False),
            "flip_tz": m.get("flip_tz", False),
        }
        for m in state.loaded_exam_meta
        if m.get("file_path") == file_path
    ]
```

- [ ] **Step 3: Update re-parsing and appending functions in `src/guiskindose/gui/exam_loaders.py`**

*Pre-flight verification:* Run `grep -rn "_append_multi_study_exams\|_append_single_study_exam" src/ tests/` to find all callers. Update any callers outside this step (e.g., unit tests, other tabs) in the same commit to prevent breakage. Also verify that `_apply_transform_flags` accepts `flip_tx`, `flip_ty`, `flip_tz` keyword arguments by checking its signature in `src/guiskindose/gui/exam_loaders.py`.

Provide full implementations for both `_append_multi_study_exams` and `_append_single_study_exam` to prevent function truncation:

```python
def _append_multi_study_exams(
    raw_exams: list,
    state: AppState,
    file_path: Path,
    seed_d_lon: float,
    seed_d_ver: float,
    seed_d_lat: float,
    preserved_flags: list[dict],
) -> tuple[Any, str]:
    """Append every exam from a multi-study tabular file and rebuild concat preview."""
    new_exams = raw_exams
    preserved_map = {f["study_id"]: f for f in preserved_flags if f.get("study_id") is not None}
    for j, exam in enumerate(new_exams):
        schema_name = exam.provenance.schema_name
        base = exam.normalized_data.copy()
        
        flags = _blank_transform_flags()
        if exam.study_id is not None and exam.study_id in preserved_map:
            flags = preserved_map[exam.study_id]
        elif j < len(preserved_flags):
            flags = preserved_flags[j]

        exam.normalized_data = _apply_transform_flags(
            base, flags["swap_lat_lon"], flags["flip_ap1"],
            flags["flip_ap2"], schema_name,
            flip_tx=flags.get("flip_tx", False),
            flip_ty=flags.get("flip_ty", False),
            flip_tz=flags.get("flip_tz", False),
        )
        state.loaded_exams.append(exam)
        state.loaded_exam_meta.append(
            _build_exam_meta_entry(
                state, file_path, schema_name, base, exam.provenance, exam.warnings,
                flags, seed_d_lon, seed_d_ver, seed_d_lat, exam.study_id
            )
        )
    result_for_finalize = raw_exams[0]  # use first exam's provenance for UI hints
    total_events = sum(len(e.normalized_data) for e in new_exams)
    msg = f"Loaded {len(new_exams)} exams, {total_events} total events"
    return result_for_finalize, msg


def _append_single_study_exam(
    result,
    state: AppState,
    file_path: Path,
    seed_d_lon: float,
    seed_d_ver: float,
    seed_d_lat: float,
    preserved_flags: list[dict],
) -> tuple[Any, str]:
    """Append a single-exam tabular file and rebuild concat preview."""
    base = result.normalized_data.copy()
    flags = preserved_flags[0] if (preserved_flags) else _default_transform_flags(state)
    result.normalized_data = _apply_transform_flags(
        base, flags["swap_lat_lon"], flags["flip_ap1"],
        flags["flip_ap2"], result.provenance.schema_name,
        flip_tx=flags.get("flip_tx", False),
        flip_ty=flags.get("flip_ty", False),
        flip_tz=flags.get("flip_tz", False),
    )
    state.loaded_exams.append(result)
    state.loaded_exam_meta.append(
        _build_exam_meta_entry(
            state, file_path, result.provenance.schema_name, base, result.provenance, result.warnings,
            flags, seed_d_lon, seed_d_ver, seed_d_lat, result.study_id
        )
    )
    msg = f"Loaded {len(result.normalized_data)} events ({result.provenance.schema_name})"
    return result, msg
```

- [ ] **Step 4: Verify parsing/loading with tests**

Run: `pytest tests/unittests/test_input_adapters.py -v`
Expected: PASS

*Note:* Loading tabular files mutates `AppState` (a NiceGUI state object). Tests that mutate GUI state without a running event loop may behave differently from the running GUI. If `AppState` requires an event loop, consider using `pytest-asyncio` or skipping GUI-state tests in non-interactive mode.

- [ ] **Step 5: Commit**

```bash
git add src/guiskindose/gui/exam_loaders.py
git commit -m "fix: map re-parsed coordinate transformation flags by study ID"
```

---

### Task 6: Audit dependencies Timeout and Validation

**Files:**
- Modify: `scripts/audit_dependencies.py`
- Modify: `tests/unittests/test_audit_dependencies.py`

**Interfaces:**
- Consumes: CLI argv parameters
- Produces: Safe restricted commands executed with finite execution timeouts.

- [ ] **Step 1: Write a failing test for pip-audit flag validation**

Add the following test to `tests/unittests/test_audit_dependencies.py`:

*Pre-flight verification:* Ensure `from unittest.mock import patch` is present at the top of the test file. If not, add it. Also verify that `ad` is defined as a pytest fixture in `tests/conftest.py` or at module scope in `test_audit_dependencies.py`. If not, use a direct import instead.

```python
def test_pip_audit_validation_rejects_unknown(ad):
    """Non-allowlisted tokens (including --ignore) must raise ValueError on pip-audit fallback path."""
    with patch("shutil.which", return_value=None):
        with pytest.raises(ValueError, match="unsupported or unsafe"):
            ad.main(["--unknown-flag"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unittests/test_audit_dependencies.py::test_pip_audit_validation_rejects_unknown -v`
Expected: FAIL

- [ ] **Step 3: Update `scripts/audit_dependencies.py` to enforce timeout and validation**

In `scripts/audit_dependencies.py`:

Add the `_UV_AUDIT_RESERVED_FLAGS` constant at the module level (if not already present):

*Pre-flight verification:* Verify that `_run_uv_audit` in `scripts/audit_dependencies.py` appends `--frozen` or `--locked` to subprocess execution. These must be included in the allowed flags to avoid ValueError.

```python
_UV_AUDIT_RESERVED_FLAGS = frozenset({
    "--frozen",
    "--locked",
    "--skip-uv-lock",  # uv-specific flag to skip lock file check
})
```

Add the `build_pip_audit_argv` function to validate and restrict arguments:

```python
def build_pip_audit_argv(extra_args: list[str]) -> list[str]:
    """Build a trusted list of extra arguments for pip-audit (similar to build_uv_audit_argv)."""
    allowed_values = frozenset({
        "--desc", "on", "off",
        "--vulnerability-service", "osv", "pypi",
        "--format", "columns", "json", "cyclonedx-json", "cyclonedx-xml",
        "-f",
    })
    allowed_prefixes = (
        "--desc=",
        "--vulnerability-service=",
        "--format=",
        "-f=",
    )
    cmd_args = []
    for arg in extra_args:
        # Check for control characters or whitespace injection (safety gate)
        if any(ch in arg for ch in "\n\r\x00") or arg.strip() != arg:
            raise ValueError("unsupported or unsafe audit argument")
        
        # Skip uv-only flags so they don't get passed to pip-audit
        if arg in _UV_AUDIT_RESERVED_FLAGS:
            continue
            
        if arg in allowed_values or arg.startswith(allowed_prefixes):
            cmd_args.append(arg)
        else:
            raise ValueError(f"unsupported or unsafe audit argument: {arg}")
    return cmd_args
```

2. Update subprocess runs to add timeouts (10 seconds for probes, 300 seconds for actual audits) and apply the validation wrapper:

In `_probe_uv_audit`:
```python
        version_out = subprocess.run(
            [uv_bin, "--version"], capture_output=True, text=True, check=True, timeout=10.0
        ).stdout
```
and
```python
        probe = subprocess.run(
            [uv_bin, "audit", "--help"], capture_output=True, text=True, cwd=repo_root, timeout=10.0
        )
```

In `_run_uv_audit`:
```python
    try:
        result = subprocess.run(audit_argv, cwd=repo_root, timeout=300.0)
        return result.returncode
```

In `_run_pip_audit_fallback`:
```python
    try:
        # Default to include descriptions, but allow overriding/extending via extra_args
        cmd = ["pip-audit"]
        if not any(arg.startswith("--desc") for arg in extra_args):
            cmd.extend(["--desc", "on"])
        # Mirror the tracked [tool.uv.audit] suppressions onto pip-audit (which has no
        # pyproject config) so both audit paths honor the same documented policy.
        tracked_ignores = _load_audit_ignores(repo_root)
        if tracked_ignores:
            print(f"INFO: applying tracked audit suppressions from [tool.uv.audit]: {', '.join(tracked_ignores)}")
            sys.stdout.flush()
            for vuln_id in tracked_ignores:
                cmd.extend(["--ignore-vuln", vuln_id])

        # Validate and append arguments
        validated_args = build_pip_audit_argv(extra_args)
        cmd.extend(validated_args)

        result = subprocess.run(cmd, cwd=repo_root, timeout=300.0)
        return result.returncode
```

*Pre-flight verification:* Verify that `_load_audit_ignores` exists in `scripts/audit_dependencies.py`. If it doesn't exist, add this minimal stub that reads `[tool.uv.audit]` from pyproject.toml:

```python
def _load_audit_ignores(repo_root: Path) -> list[str]:
    """Load audit ignore IDs from pyproject.toml [tool.uv.audit]."""
    pyproject_path = repo_root / "pyproject.toml"
    if not pyproject_path.exists():
        return []
    import tomli
    try:
        with open(pyproject_path, "rb") as f:
            data = tomli.load(f)
        audit_config = data.get("tool", {}).get("uv", {}).get("audit", {})
        return audit_config.get("ignore", [])
    except Exception:
        return []
```

3. Update `main` to remove the internal `sys.exit` (so it only returns the exit code), and wrap the entrypoint with `sys.exit` in `if __name__ == "__main__":`:

*Note:* Adding `timeout` parameters to `subprocess.run` calls will raise `subprocess.TimeoutExpired` tracebacks when processes hang. This is an expected failure mode for tests/CI when hangs occur, which is acceptable behavior.

```python
def main(argv: list[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    uv_bin = _probe_uv_audit(repo_root)
    extra_args = sys.argv[1:] if argv is None else list(argv)

    if uv_bin:
        code = _run_uv_audit(uv_bin, repo_root, extra_args)
    else:
        code = _run_pip_audit_fallback(repo_root, extra_args)
    return code

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Update the 10 specific tests in `test_audit_dependencies.py` to assert returned status code**

Update the following 10 tests in `tests/unittests/test_audit_dependencies.py` to assert the returned code instead of catching `SystemExit`:
- `test_main_uv_audit_success`
- `test_main_uv_missing_fallback`
- `test_main_uv_lock_missing_fallback`
- `test_main_uv_audit_unsupported_fallback`
- `test_main_uv_too_old_fallback`
- `test_main_allowlisted_passthrough`
- `test_main_ci_enforcement`
- `test_main_uv_audit_exec_filenotfound_fallback`
- `test_pip_audit_fallback_mirrors_tracked_ignores`
- `test_main_pip_audit_missing_error`

For each test, replace the pattern:
```python
# Old pattern:
with pytest.raises(SystemExit) as excinfo:
    ad.main()
assert excinfo.value.code == 0

# New pattern:
code = ad.main()
assert code == 0
```

Apply the same pattern for tests expecting non-zero exit codes:
```python
# Old pattern:
with pytest.raises(SystemExit) as excinfo:
    ad.main()
assert excinfo.value.code != 0

# New pattern:
code = ad.main()
assert code != 0
```

Do **not** modify `test_main_flag_filtering` (as it expects a `ValueError` rather than `SystemExit`).

Run: `pytest tests/unittests/test_audit_dependencies.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/audit_dependencies.py tests/unittests/test_audit_dependencies.py
git commit -m "fix: validate pip-audit args, add finite timeouts to subprocess calls, and return code from main"
```

---

### Task 7: Minor Formatting and Schema Cleanup

**Files:**
- Modify: `scripts/check_help_registry.py`
- Modify: `src/guiskindose/main.py`
- Modify: `dev-docs/index.md`

**Interfaces:**
- Consumes: Modified registry maps and module imports
- Produces: Correctly typed argparse parser and formatted line-length.

- [ ] **Step 1: Format registry check warnings and schema list checks**

In `scripts/check_help_registry.py`, split line 170 to keep it under 120 characters:

```python
        result.errors.append(
            f"{context}: missing mirrored help file {target_dir / source}; run scripts/sync_gui_help.py"
        )
```

In `_check_gui_references` in `scripts/check_help_registry.py`, validate that `gui_files` is a list and contains only strings:

*Pre-flight verification:* Ensure `from pathlib import Path` is present at the top of `scripts/check_help_registry.py`. If not, add it directly to the import section of the file before proceeding with the code changes below.

```python
    if "gui_files" in entry:
        gui_files = entry["gui_files"]
        if not isinstance(gui_files, list):
            result.errors.append(f"{context}: 'gui_files' must be a list of file paths")
            return
    else:
        gui_files = []

    gui_texts: list[str] = []
    for gui_file in gui_files:
        if not isinstance(gui_file, (str, Path)):
            result.errors.append(f"{context}: GUI file paths must be strings, got {type(gui_file)}")
            continue
        gui_path = repo_root / str(gui_file)
        if not gui_path.is_file():
            result.errors.append(f"{context}: missing GUI file {gui_file}")
            continue
        gui_texts.append(gui_path.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Add `argparse` type annotation to `get_argument_parser`**

In `src/guiskindose/main.py`, merge the `TYPE_CHECKING` import on line 4 rather than adding a duplicate import statement:

```python
from typing import Any, Optional, Sequence, TYPE_CHECKING
```

Add the `TYPE_CHECKING` import block and update `get_argument_parser` signature:

```python
if TYPE_CHECKING:
    import argparse
```

```python
def get_argument_parser(arguments) -> "argparse.Namespace":
```

- [ ] **Step 3: Add new plan file to `dev-docs/index.md`**

In `dev-docs/index.md`, list the new plan under the **Execution plans (`plans/`)** table:

```markdown
| [plans/PR_CODE_REVIEW_FIXES_PLAN.md](PR_CODE_REVIEW_FIXES_PLAN.md) | **Active** — Resolve open CodeRabbit PR review comments on branch refactor/sonar-lizard-fixes. |
```

- [ ] **Step 4: Run help registry and license audits**

Run: `python scripts/check_help_registry.py` and `pytest tests/unittests/`
Expected: PASS

Also run basedpyright to verify type annotations:
```bash
basedpyright src/guiskindose/main.py
```
Expected: PASS (no type errors for argparse.Namespace forward reference)

- [ ] **Step 5: Commit**

```bash
git add scripts/check_help_registry.py src/guiskindose/main.py dev-docs/index.md
git commit -m "style: address help registry line length and type hint get_argument_parser"
```

---

## Post-Implementation Verification

After completing all tasks, perform these verification steps:

- [ ] **Run full test suite:** `pytest tests/unittests/ -v` to ensure no regressions
- [ ] **Run specific test files:** Run individual test files for each modified component
- [ ] **Manual GUI testing:** Test the exam loader functionality with actual tabular files
- [ ] **Performance testing:** Verify timeout protections work (test with intentionally slow operations)
- [ ] **Integration testing:** Test with actual RDSR files to ensure interpolation fixes work correctly
- [ ] **Documentation review:** Ensure all behavior changes are documented if needed
- [ ] **Code review:** Self-review all changes for consistency and style compliance
- [ ] **Final verification:** Run `python scripts/check_help_registry.py` and `python scripts/audit_dependencies.py`

---

## Implementation Notes

### Task Dependencies
- Task 5 depends on Task 1 being completed first (function signature ordering constraint)
- Task 6 test updates depend on the main function changes being completed first

### Risk Mitigation
- All changes are backward compatible and preserve existing behavior for valid inputs
- New validations only affect error cases that previously would have failed with asserts
- Timeout values (10s, 300s) are conservative and can be adjusted if needed for CI environment

### Rollback Plan
If any task causes issues, individual commits can be reverted:
- Each task has its own commit for easy rollback
- Test changes are coupled with implementation changes in the same commit
