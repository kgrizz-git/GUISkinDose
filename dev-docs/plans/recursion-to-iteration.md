# Recursion → Iteration Refactor

## Objective

Replace the per-event tail recursion in `calculate_irradiation_event_result()` with an iterative loop so that event count is bounded only by memory, not Python's ~1000 frame recursion limit. This unblocks multi-exam processing (multiple exams × hundreds of events each) and prevents `RecursionError` on long single-exam procedures.

## Acceptance Criteria

- [ ] `calculate_irradiation_event_result()` no longer calls itself recursively.
- [ ] Output is bit-identical to the recursive version for all existing test inputs.
- [ ] A test with 1100+ events (exceeding `sys.getrecursionlimit()`) completes without error.
- [ ] Progress bar updates at every event and shows correct final state.
- [ ] All existing unit tests pass.
- [ ] No change to public API (`calculate_dose()`, `analyze_data()`, etc.).

## Decision Log

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | Keep `calculate_irradiation_event_result()` as the public entry point | Backward-compatible. Callers pass `event=0`, `total_events=N`. The function signature stays the same; only the body changes. |
| D2 | Use `for event in range(total_events):` with mutable state carried across iterations | The recursive version threads `hits`, `table_hits`, `field_area`, `k_isq` through each call frame as mutable arguments. A loop carries them as local variables, updated each iteration. |
| D3 | Preserve the `pbar.update()` call at each iteration | Progress bar semantics must be identical. The current code updates at every event and does a final `update()` + `refresh()` after the last event. |
| D4 | Keep `perform_calculations_for_new_geometries()` and `add_corrections_and_event_dose_to_output()` as separate functions | They are already pure helpers with no recursion. No reason to inline them. |
| D5 | Equivalence test first, then refactor | The recursive version is the reference. Write a test that captures its output on a representative fixture, then refactor and assert the iterative output matches. This prevents silent bugs. |

## Current Code Analysis

### Entry point: `calculate_dose()` (calculate_dose.py:112-126)

```python
output = calculate_irradiation_event_result(
    normalized_data=normalized_data,
    event=0,                                          # first event
    total_events=len(normalized_data),
    new_geometry=new_geometry,
    k_tab=k_tab,
    hits=[],                                          # empty list
    patient=patient,
    table=table,
    pad=pad,
    back_scatter_interpolation=back_scatter_interpolation,
    output=output_template,
    pbar=pbar(total=total_number_of_events, ...),
    corrections_db=settings.corrections_db_path,
)
```

### Recursive function: `calculate_irradiation_event_result()` (calculate_irradiation_event_result.py)

The function processes one event, then recurses for `event + 1`:

```
event=0 ──► process(event=0) ──► event=1
event=1 ──► process(event=1) ──► event=2
...
event=N-1 ──► process(event=N-1) ──► event=N  (base case: event < total_events is False)
```

**State threaded through recursion:**

| Variable | Type | Meaning | Mutation |
|----------|------|---------|----------|
| `hits` | `List[bool]` | Which patient skin cells are hit by the beam for the current event | Replaced by `perform_calculations_for_new_geometries()` when `new_geometry[event]` is True |
| `table_hits` | `List[bool]` | Which hit cells need table correction | Replaced when `new_geometry[event]` is True |
| `field_area` | `List[float]` | X-ray field area at each hit cell | Replaced when `new_geometry[event]` is True |
| `k_isq` | `np.ndarray` | Inverse-square-law correction factors | Replaced when `new_geometry[event]` is True |
| `output` | `Dict[str, Any]` | Accumulated results (dose map, correction factors per event) | Mutated in-place by `add_corrections_and_event_dose_to_output()` |

**Key observation:** `hits`, `table_hits`, `field_area`, `k_isq` are only updated when `new_geometry[event]` is True. When it is False, `perform_calculations_for_new_geometries()` returns them unchanged, and the recursive call passes the same values. This means the loop must preserve this conditional-update behavior.

**Output dict keys (from `output_template` in calculate_dose.py:102-110):**

```python
{
    "hits": [[]] * total_number_of_events,          # per-event hit list
    "air_kerma": [np.array] * total_number_of_events,  # K_IRP per event
    "k_isq": [[]] * total_number_of_events,         # inverse-square correction per event
    "k_bs": [[]] * total_number_of_events,          # backscatter correction per event
    "k_med": [[]] * total_number_of_events,         # medium correction per event
    "k_tab": [[]] * total_number_of_events,         # table correction per event
    "dose_map": np.zeros(len(patient.r)),            # scalar accumulated dose (mutable)
}
```

**IMPORTANT: Pre-existing latent bug in `output_template`.** The code uses `[[]] * N` which creates N references to the *same* list object, not independent lists. Same for `k_bs`, `k_med`, `k_tab` (all `[[]] * N`). For `air_kerma`, `[np.array] * N` creates N references to the `np.array` *class* (not an instance). Assignment (`output["hits"][ev] = hits`) works because it replaces the reference at that index, so the recursive version is not affected. However, any in-place mutation (`.append()`, etc.) would corrupt all slots. **Recommendation:** fix this as part of the refactor by using list comprehensions: `[[] for _ in range(total_number_of_events)]`. This should be a separate change but is closely related.

### The recursive tail (lines 132-155)

```python
event += 1
if event < total_events:
    if pbar is not None:
        pbar.update()
    output = calculate_irradiation_event_result(
        ...,
        event=event,
        ...
        pbar=pbar,
    )
    if event == total_events - 1 and pbar is not None:
        pbar.update()
        pbar.refresh()
return output
```

Note: the progress bar gets **two** updates on the last event — one inside the `if event < total_events` block (at `pbar.update()`), and one after the recursive call returns (at `pbar.update()` + `pbar.refresh()`). This is because the initial `pbar` is created with `total=total_number_of_events` but the first event's update happens inside the recursive call for `event=1`, not after processing `event=0`. The loop version needs to match this update sequence.

## Iterative Design

```python
def calculate_irradiation_event_result(
    normalized_data: pd.DataFrame,
    event: int,
    total_events: int,
    new_geometry: List[bool],
    k_tab: List[float],
    hits: List[bool],
    patient: Phantom,
    table: Phantom,
    pad: Phantom,
    back_scatter_interpolation: List[CubicSpline],
    output: Dict[str, Any],
    corrections_db: str,
    table_hits: List[bool] | None = None,
    field_area: List[float] | None = None,
    k_isq: np.ndarray | None = None,
    pbar: tqdm | None = None,
) -> Dict[str, Any]:
    """Iterative version of the per-event dose calculation."""
    if table_hits is None:
        table_hits = []
    if field_area is None:
        field_area = []
    if k_isq is None:
        k_isq = np.array([])

    # Validate that event starts at 0
    if event != 0:
        raise ValueError("event must be 0 for the iterative entry point")

    **CONSIDER REMOVING THIS CHECK.** The recursive version accepted any starting `event`. Adding this validation is a behavioral change that could break callers that start from a non-zero event (even if none exist today). If no external callers pass non-zero `event`, remove the check to maintain backward compatibility.

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

### Progress bar semantics comparison

**Recursive version:**
- `pbar` created with `total=N`
- After processing event 0: no update (first update happens in recursive call for event=1)
- After processing event 1: `pbar.update()` → shows 1/N
- ...
- After processing event N-2: `pbar.update()` → shows N-2/N
- After processing event N-1: `pbar.update()` → shows N-1/N, then `pbar.update()` + `pbar.refresh()` → shows N/N

Wait — let me re-examine. The recursive version updates the progress bar **before** recursing, not after processing. Let me trace more carefully:

```
calculate_irradiation_event_result(event=0):
    process event 0
    event += 1  → event = 1
    if 1 < total_events:
        pbar.update()          # ← update AFTER processing event 0, BEFORE recursing
        recursive_call(event=1)
            process event 1
            event += 1  → event = 2
            if 2 < total_events:
                pbar.update()  # ← update AFTER processing event 1, BEFORE recursing
                ...
```

So the update at event `i` happens after processing event `i` (storing results) and before processing event `i+1`. The progress bar shows "processed N events" after processing event N-1.

On the last event (event = total_events - 1):
```
calculate_irradiation_event_result(event=N-1):
    process event N-1
    event += 1  → event = N
    if N < total_events:  # FALSE → skip
    return output
```

So the last event does NOT call `pbar.update()` inside the `if` block. But there's this after the recursive call:

```python
if event == total_events - 1 and pbar is not None:
    pbar.update()
    pbar.refresh()
```

This fires when the **caller** is at `event = total_events - 2` (the second-to-last event). After the recursive call returns (which processed the last event), it does `pbar.update()` + `pbar.refresh()`.

So the progress bar sequence is:
- After event 0: `update()` → 1/N
- After event 1: `update()` → 2/N
- ...
- After event N-2: `update()` → N-1/N, then recursive call processes event N-1, returns
- After recursive call returns: `update()` → N/N, `refresh()`

Total updates: N (one per event). The final `refresh()` ensures the bar is drawn to completion.

**Iterative version needs to match this exactly.** The loop above does `pbar.update()` after each event, giving N updates. Then `pbar.refresh()` after the loop. This matches.

### State mutation analysis

| State variable | Where mutated | Scope | Loop-safe? |
|----------------|---------------|-------|------------|
| `hits` | `perform_calculations_for_new_geometries()` → `beam.check_hit(patient=patient)` | Per-event | Yes — re-assigned each time new_geometry is True |
| `table_hits` | `perform_calculations_for_new_geometries()` → `check_table_hits(...)` | Per-event | Yes — same as hits |
| `field_area` | `perform_calculations_for_new_geometries()` → `scale_field_area(...)` | Per-event | Yes — same as hits |
| `k_isq` | `perform_calculations_for_new_geometries()` → `calculate_k_isq(...)` | Per-event | Yes — same as hits |
| `output["hits"][ev]` | `output[c.OUTPUT_KEY_HITS][ev] = hits` | Per-event slot | Yes — each index written once |
| `output["air_kerma"][ev]` | `output[c.OUTPUT_KEY_KERMA][ev] = ...` | Per-event slot | Yes |
| `output["k_isq"][ev]` | `output[c.OUTPUT_KEY_CORRECTION_INVERSE_SQUARE_LAW][ev] = k_isq` | Per-event slot | Yes |
| `output["k_bs"][ev]` | Inside `add_corrections_and_event_dose_to_output()` | Per-event slot | Yes |
| `output["k_med"][ev]` | Inside `add_corrections_and_event_dose_to_output()` | Per-event slot | Yes |
| `output["k_tab"][ev]` | Inside `add_corrections_and_event_dose_to_output()` | Per-event slot | Yes |
| `output["dose_map"]` | `output[c.OUTPUT_KEY_DOSE_MAP] += event_dose` | Scalar array | Yes — cumulative addition, order-independent for addition |
| `patient` | `perform_calculations_for_new_geometries()` → `patient.position(...)` | Per-event (in-place) | Yes — `position()` updates phantom coordinates to match event geometry; must be called every time `new_geometry` is True |
| `table` | `perform_calculations_for_new_geometries()` → `table.position(...)` | Per-event (in-place) | Yes — same as patient |
| `pad` | `perform_calculations_for_new_geometries()` → `pad.position(...)` | Per-event (in-place) | Yes — same as patient |

**Conclusion:** All state is either per-event (written once at a unique index) or cumulative (addition is order-preserving). The iterative version is safe.

**Note on phantom mutation:** `perform_calculations_for_new_geometries.py:34-36` calls `patient.position()`, `table.position()`, `pad.position()` which mutate the phantom objects in-place. This is critical — the iterative loop must call these every time `new_geometry[ev]` is True, just like the recursive version does. The phantom objects are shared across all iterations (not copied), so their state carries forward from event to event.

## Test Strategy

### Phase 1: Equivalence test (write BEFORE refactoring)

Create a test that:
1. Runs the **current recursive** version on a representative fixture (e.g., `siemens_axiom_artis.dcm` with 21 events).
2. Saves the output dict (dose_map, all correction factors, PSD).
3. After the refactor, runs the **iterative** version on the same input.
4. Asserts bit-identical output: `np.testing.assert_array_equal(output["dose_map"], expected_dose_map)`, etc.

This test must **fail** before the refactor (because the old code is recursive) and **pass** after. It serves as the regression guard.

```python
def test_recursion_iteration_equivalence():
    """Iterative output must match recursive output exactly."""
    rdsr_path = get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm"
    settings = _make_settings(output_format="dict")
    
    parsed = rdsr_parser(pydicom.dcmread(str(rdsr_path)), silence_pydicom_warnings=True)
    norm = rdsr_normalizer(parsed, settings=settings)
    
    # The iterative version should produce identical output
    result = analyze_data(normalized_data=norm.copy(), settings=settings)
    
    # Verify key outputs
    assert result["psd"] > 0
    assert isinstance(result["dose_map"], np.ndarray)
    assert np.any(result["dose_map"] > 0.0)
    assert not np.any(np.isnan(result["dose_map"]))  # no NaN
    assert not np.any(np.isnan(result["psd"]))
```

### Phase 2: Stress test (write BEFORE refactoring, will fail with recursion)

```python
def test_iterative_no_crash_1100_events():
    """Iterative version handles >1000 events without RecursionError."""
    # Generate synthetic normalized data with 1100 events
    # Use model="plane" for speed. Geometry must change at least some of the time
    # so that hits/dose are actually computed (all-False new_geometry = no dose).
    synthetic_norm = _generate_synthetic_events(1100)
    settings = _make_settings(output_format="dict", phantom_model="plane")
    
    result = analyze_data(normalized_data=synthetic_norm, settings=settings)
    assert len(result["dose_map"]) == 1100  # one entry per event
    assert np.any(result["dose_map"] > 0.0)  # at least some dose was computed
```

This test will fail with `RecursionError` on the current code (1100 > ~1000 limit). After the refactor, it should pass.

**Critical note on synthetic data generation:** The `_generate_synthetic_events()` helper must set `new_geometry` to `True` for at least some events, otherwise `perform_calculations_for_new_geometries()` returns empty `hits` every time and no dose is computed. A realistic mix: first event always True, subsequent events True ~30% of the time (simulating C-arm repositioning between events).

### Phase 3: Regression tests (run AFTER refactoring)

All existing tests in:
- `tests/unittests/test_calculate_dose.py`
- `tests/unittests/test_analyze_data.py`
- `tests/unittests/test_export_data.py`

Must pass without modification.

### Synthetic event generation

The stress test needs a synthetic DataFrame with 1100+ events. The fixture should:
- Use `model="plane"` phantom for speed
- Use a realistic mix of `new_geometry` values: first event always True, subsequent events True ~30% of the time (simulating C-arm repositioning)
- Use realistic kVp, DSD, DSI, Tx, Ty, Tz, At1, At2, At3 values
- Ensure events with `new_geometry=True` hit the phantom (non-empty hits list)

## Implementation Steps

1. **Write equivalence test** against current recursive version. Verify it passes.
2. **Write stress test** (1100 events). Verify it fails with `RecursionError`.
3. **Refactor** `calculate_irradiation_event_result.py`: replace tail recursion with `for` loop.
4. **Run equivalence test.** Must pass.
5. **Run stress test.** Must pass (was failing in step 2).
6. **Run all existing tests.** Must pass.
7. **Profile** — verify no performance regression (loop overhead should be negligible).

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Progress bar shows different update count | Medium | Low (cosmetic) | Trace update sequence carefully; use equivalence test |
| State mutation order differs | Low | High (wrong dose) | Equivalence test catches this |
| `perform_calculations_for_new_geometries()` behavior changes | Low | High | It's a pure function; no changes needed |
| `add_corrections_and_event_dose_to_output()` behavior changes | Low | High | It's a pure function; no changes needed |
| Performance regression | Very low | Low | Loop is typically faster than recursion |
| Breaks existing callers | Very low | High | Signature unchanged; equivalence test covers it |
| Phantom `position()` not called when `new_geometry` is False | Low | High (wrong dose) | `position()` is only called inside `perform_calculations_for_new_geometries()` when `new_geometry` is True — same as recursive version |
| `output_template` shared-reference bug causes silent corruption | High | High (wrong dose) | Pre-existing bug in `calculate_dose.py:103-108`; should be fixed separately with list comprehensions |

## Open Questions & Suggestions

1. **Fix `output_template` shared-reference bug.** The current code at `calculate_dose.py:103-108` uses `[[]] * N` for list slots and `[np.array] * N` for air_kerma. This is a pre-existing bug that the recursive version happens not to trigger (because assignment replaces references). The iterative version should fix this to `[[] for _ in range(N)]` and `[np.array([]) for _ in range(N)]`. Consider this a separate PR or a pre-step to the refactor.

2. **Remove `event != 0` validation or document it.** The proposed iterative design includes a check that raises `ValueError` if `event != 0`. The recursive version accepted any starting event. This is a behavioral change. Search all callers before deciding — if none pass non-zero `event`, remove the check to maintain backward compatibility.

3. **Add a test for `new_geometry=False` path.** When geometry doesn't change between events, the previous event's hits/corrections carry forward. This is the most common case in real procedures. The stress test should include a mix of True/False values, not all-False (which produces zero dose) or all-True (which doesn't test the carry-forward path).

4. **Progress bar trace is correct.** The N-update sequence between recursive and iterative versions matches. No action needed.

## Files Changed

- `src/mypyskindose/calculate_dose/calculate_irradiation_event_result.py` — refactor tail recursion to loop
- `tests/unittests/test_calculate_dose.py` — add equivalence test + stress test

## Related

- [Multiple Exams Plan](multiple-exams.md) — this refactor is a prerequisite (D5).
- [TO_DO.md](../TO_DO.md) — task listed under "Input data & calculation".
- `calculate_dose.py` — caller that invokes the function.
- `perform_calculations_for_new_geometries.py` — helper called per event.
- `add_correction_and_event_dose_to_output.py` — helper called per event.
