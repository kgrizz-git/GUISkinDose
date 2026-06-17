# Recursion → Iteration Refactor

## Objective

Replace the per-event tail recursion in `calculate_irradiation_event_result()` with an iterative loop so that event count is bounded only by memory, not Python's ~1000 frame recursion limit. This unblocks multi-exam processing (multiple exams × hundreds of events each) and prevents `RecursionError` on long single-exam procedures.

## Status (2026-06-16)

| Item | State |
|------|-------|
| Plan review | Done |
| `_build_output_template()` shared-reference fix | **Already shipped** (`calculate_dose.py`) |
| Golden baseline test | **Done** |
| Stress test (1100 events) | **Done** |
| Synthetic event helper | **Done** |
| Loop refactor | **Done** (2026-06-16) |

**Verified recursion threshold (pre-refactor):** with default `sys.getrecursionlimit() == 1000`, `calculate_dose()` on 1100 plane-phantom synthetic events raised `RecursionError` around event ~982. Post-refactor: same input completes in ~3 s.

## Acceptance Criteria

- [x] `calculate_irradiation_event_result()` no longer calls itself recursively.
- [x] Output is bit-identical to the recursive version for all existing test inputs.
- [x] A test with 1100+ events (exceeding `sys.getrecursionlimit()`) completes without error.
- [x] Progress bar updates at every event and shows correct final state.
- [x] All existing unit tests pass.
- [x] No change to public API (`calculate_dose()`, `analyze_data()`, etc.).

## Decision Log

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Keep `calculate_irradiation_event_result()` as the public entry point | Backward-compatible. Callers pass `event=0`, `total_events=N`. The function signature stays the same; only the body changes. |
| D2 | Use `for ev in range(event, total_events):` with mutable state carried across iterations | The recursive version threads `hits`, `table_hits`, `field_area`, `k_isq` through each call frame as mutable arguments. A loop carries them as local variables, updated each iteration. |
| D3 | Preserve the `pbar.update()` call at each iteration | Progress bar semantics must be identical. N updates after processing events 0…N−1, then `pbar.refresh()`. |
| D4 | Keep `perform_calculations_for_new_geometries()` and `add_corrections_and_event_dose_to_output()` as separate functions | They are already pure helpers with no recursion. No reason to inline them. |
| D5 | Golden baseline test first, then refactor | Pin recursive output on `siemens_axiom_artis.dcm` (cylinder phantom). Refactor must pass the same assertions. |
| D6 | Do **not** add `event != 0` validation | The recursive version accepts any starting `event`. The only caller (`calculate_dose`) passes `event=0`, but raising on non-zero would be a behavioral change. Use `for ev in range(event, total_events):` without a guard. |

## Current Code Analysis

### Entry point: `calculate_dose()` (`calculate_dose.py`)

```python
output = calculate_irradiation_event_result(
    normalized_data=normalized_data,
    event=0,
    total_events=len(normalized_data),
    new_geometry=new_geometry,
    k_tab=k_tab,
    hits=[],
    patient=patient,
    table=table,
    pad=pad,
    back_scatter_interpolation=back_scatter_interpolation,
    output=output_template,
    pbar=pbar(total=total_number_of_events, ...),
    corrections_db=settings.corrections_db_path,
)
```

`output_template` is built by `_build_output_template()` with independent per-event placeholders (`[[] for _ in range(N)]`, etc.). Template-shape tests live in `tests/unittests/test_calculate_dose.py`.

### Recursive function: `calculate_irradiation_event_result()` (`calculate_irradiation_event_result.py`)

The function processes one event, then recurses for `event + 1`:

```
event=0 ──► process(event=0) ──► event=1
event=1 ──► process(event=1) ──► event=2
...
event=N-1 ──► process(event=N-1) ──► return
```

**State threaded through recursion:**

| Variable | Type | Meaning | Mutation |
|----------|------|---------|----------|
| `hits` | `List[bool]` | Which patient skin cells are hit by the beam for the current event | Replaced by `perform_calculations_for_new_geometries()` when `new_geometry[event]` is True |
| `table_hits` | `List[bool]` | Which hit cells need table correction | Replaced when `new_geometry[event]` is True |
| `field_area` | `List[float]` | X-ray field area at each hit cell | Replaced when `new_geometry[event]` is True |
| `k_isq` | `np.ndarray` | Inverse-square-law correction factors | Replaced when `new_geometry[event]` is True |
| `output` | `Dict[str, Any]` | Accumulated results (dose map, correction factors per event) | Mutated in-place by `add_corrections_and_event_dose_to_output()` |

**Key observation:** `hits`, `table_hits`, `field_area`, `k_isq` are only updated when `new_geometry[event]` is True. When it is False, `perform_calculations_for_new_geometries()` returns them unchanged. The loop must preserve this conditional-update behavior.

### The recursive tail (lines 132–160)

```python
    event += 1
    if event < total_events:
        if pbar is not None:
            pbar.update()
        output = calculate_irradiation_event_result(..., event=event, ...)
        if event == total_events - 1 and pbar is not None:
            pbar.update()
            pbar.refresh()
    return output
```

**Progress bar sequence (N events):** one `update()` after each processed event (N total), plus `refresh()` after the last. The iterative design matches this with `update()` inside the loop and `refresh()` after the loop.

## Iterative Design

```python
def calculate_irradiation_event_result(...) -> Dict[str, Any]:
    if table_hits is None:
        table_hits = []
    if field_area is None:
        field_area = []
    if k_isq is None:
        k_isq = np.array([])

    for ev in range(event, total_events):
        logger.debug(f"Calculating irradiation event {ev + 1} out of {total_events}")

        hits, table_hits, field_area, k_isq = perform_calculations_for_new_geometries(
            normalized_data=normalized_data,
            event=ev,
            new_geometry=new_geometry[ev],
            patient=patient,
            table=table,
            pad=pad,
            hits=hits,
            table_hits=table_hits,
            field_area=field_area,
            k_isq=k_isq,
        )

        output[c.OUTPUT_KEY_HITS][ev] = hits
        output[c.OUTPUT_KEY_KERMA][ev] = normalized_data.K_IRP[ev]
        output[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW][ev] = k_isq

        output = add_corrections_and_event_dose_to_output(
            normalized_data=normalized_data,
            event=ev,
            hits=hits,
            table_hits=table_hits,
            patient=patient,
            back_scatter_interpolation=back_scatter_interpolation,
            field_area=field_area,
            k_tab=k_tab,
            output=output,
            corrections_db=corrections_db,
        )

        if pbar is not None:
            pbar.update()

    if pbar is not None:
        pbar.refresh()

    return output
```

No `event != 0` guard (see D6). Update the function docstring when refactoring (it already says "loops" but still recurses).

## Test Strategy

### Phase 1: Golden baseline (shipped)

`test_calculate_dose_golden_baseline_siemens_cylinder` in `tests/unittests/test_calculate_dose.py`:

- Runs `calculate_dose()` on `siemens_axiom_artis.dcm` (cylinder phantom, 21 events).
- Asserts pinned scalars (PSD, dose sum, first-3-event kerma/hits/k_med).
- Asserts `np.testing.assert_array_equal` against `tests/fixtures/golden/calculate_dose_siemens_axiom_artis_cylinder_dose_map.npy`.

**Passes on current recursive code.** Must still pass after the loop refactor.

### Phase 2: Stress test (shipped, xfail until refactor)

`test_calculate_dose_handles_1100_events_without_recursion_error`:

- Builds 1100 events via `generate_synthetic_normalized_events()` (`tests/calculate_dose_recursion_helpers.py`).
- Uses `phantom.model = "plane"` for speed.
- Calls `calculate_dose()` directly (not `analyze_data()` — skips plotting).
- Marked `@pytest.mark.slow` (~3 s on dev hardware).
- Marked `@pytest.mark.xfail(strict=True, raises=RecursionError)` until refactor; **remove xfail** when the loop ships.

**Shipped 2026-06-16** — xfail removed; test passes.

**Assertions (corrected):**

```python
assert len(output[c.OUTPUT_KEY_HITS]) == 1100   # per-event slots, not dose_map length
assert np.any(output[c.OUTPUT_KEY_DOSE_MAP] > 0.0)
```

### Phase 3: Synthetic event generation

`generate_synthetic_normalized_events()` clones the first normalized row of `siemens_axiom_artis.dcm` and perturbs `Tx` / `Ap1` on ~30% of subsequent rows. `new_geometry` is **not** a column — `check_new_geometry()` derives it from `Tx`, `Ty`, `Tz`, `FS_lat`, `FS_long`, `Ap1`–`Ap3`, `At1`–`At3`.

### Phase 4: Regression (after refactor)

All tests in `tests/unittests/test_calculate_dose.py`, `test_analyze_data.py`, `test_export_data.py` must pass without modification.

## Implementation Steps

1. [x] **Golden baseline test** — passes on recursive code.
2. [x] **Stress test** — xfail with `RecursionError` on current code.
3. [x] **Refactor** `calculate_irradiation_event_result.py`: replace tail recursion with `for` loop.
4. [x] **Remove stress-test xfail** — stress test must pass.
5. [x] **Run golden + full suite** — all pass.
6. [ ] **Profile** — verify no performance regression (loop overhead should be negligible).

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Progress bar shows different update count | Medium | Low (cosmetic) | Trace update sequence; golden test |
| State mutation order differs | Low | High (wrong dose) | Golden test catches this |
| Helper behavior changes | Low | High | No changes to helpers; existing unit tests |
| Performance regression | Very low | Low | Loop is typically faster than recursion |
| Breaks existing callers | Very low | High | Signature unchanged; single caller at `event=0` |
| Phantom `position()` skipped when `new_geometry` is False | Low | High | Same as recursive version — only called inside helper when True |

## Files Changed (prep, 2026-06-16)

| File | Change |
|------|--------|
| `tests/unittests/test_calculate_dose.py` | Golden baseline + stress tests |
| `tests/calculate_dose_recursion_helpers.py` | Synthetic normalized event builder |
| `tests/fixtures/golden/calculate_dose_siemens_axiom_artis_cylinder_dose_map.npy` | Pinned dose map |
| `pyproject.toml` | `slow` pytest marker |

## Files Changed (refactor, 2026-06-16)

| File | Change |
|------|--------|
| `src/mypyskindose/calculate_dose/calculate_irradiation_event_result.py` | Tail recursion → `for ev in range(event, total_events)` loop |
| `tests/unittests/test_calculate_dose.py` | Removed stress-test xfail |

## Related

- [Multiple Exams Plan](multiple-exams.md) — this refactor is a prerequisite (D5).
- [TO_DO.md](../TO_DO.md) — task listed under "Input data & calculation".
- `calculate_dose.py` — caller that invokes the function.
- `perform_calculations_for_new_geometries.py` — helper called per event.
- `add_corrections_and_event_dose_to_output.py` — helper called per event.
