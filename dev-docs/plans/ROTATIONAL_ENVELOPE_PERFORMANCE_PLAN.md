# Rotational Coverage-Envelope Performance Plan

Created: 2026-09-28 · Status: **ready to implement**

Execution plan for the findings in
[assessments/ROTATIONAL_ENVELOPE_PERFORMANCE_2026-09-28.md](../assessments/ROTATIONAL_ENVELOPE_PERFORMANCE_2026-09-28.md).
Read the assessment for the measurements; this file is the change list.

Feature source of truth (unchanged by this plan):
[ROTATIONAL_COVERAGE_ENVELOPE_PLAN.md](ROTATIONAL_COVERAGE_ENVELOPE_PLAN.md).

**Goal:** make the coverage envelope ~19× faster with a **bit-identical** dose map. Measured on a
360-pose envelope: 6.13 s → 0.32 s, `max |before − after|` = `0.000e+00`.

**Non-goal:** changing any default, contract, disclosure field, candidate domain, or aggregation rule.
In particular `angular_step_deg` stays `1.0`. The speedup comes entirely from not repeating work.

---

## 0. The invariant everything rests on

A candidate frame is the parent event row with **only `Ap1` and `Ap2` overridden**
(`rotational_event._candidate_frame`, `rotational_event.py:63`). Therefore, across all candidates of
one event:

- `Tx`, `Ty`, `Tz`, `At1–At3` and the derived `Rx`/`Ry`/`Rz` are **constant** → `Phantom.position`
  (`phantom_class.py:376`) produces a bit-identical `patient.r` every time (Phase 1a).
- `kVp` and `HVL` are **constant** → `calculate_k_med`'s `(kvp, hvl, snapped fsl)` lookup key varies
  only through `fsl`, which is snapped to one of five tabulated values (Phase 1f).
- `FS_lat`, `FS_long`, `DSD`, `DSI`, `DID`, `DSL`, `K_IRP` are **constant** → every scalar
  `Beam.__init__` reads except the two angles can be hoisted (Phase 2).

If a future change ever lets a candidate vary anything else, Phases 1a and 1f become wrong. Phase 1a
adds an assertion-style guard for exactly this (§1a).

---

## Phase 1 — bit-exact hot-loop cleanup

Seven independent edits. Each is safe alone, so they can land as one PR or seven commits, but the
acceptance gate in §4 must pass at the end.

### 1a. Position the phantoms once per event, not once per candidate

**Files:** `src/guiskindose/calculate_dose/perform_calculations_for_new_geometries.py`,
`src/guiskindose/calculate_dose/rotational_event.py`

Add a keyword-only `reposition: bool = True` parameter to
`perform_calculations_for_new_geometries`. When false, skip the three `*.position(...)` calls and use
the phantoms as they stand. The default keeps every existing caller — including
`calculate_irradiation_event_result.py:256` — byte-for-byte unchanged.

In `_calculate_envelope_event`, position all three phantoms **unconditionally** at the top:

```python
# Candidates never vary Tx/Ty/Tz or At1-At3, so one positioning at the parent
# pose is valid for the whole domain. Done unconditionally rather than under
# new_geometry_flag so the candidate loop never depends on the cache invariant.
patient.position(data_norm=normalized_data, event=ev)
table.position(data_norm=normalized_data, event=ev)
pad.position(data_norm=normalized_data, event=ev)
```

then pass `reposition=False` from the candidate `_compute` call (`rotational_event.py:251`). Leave the
static-pose call at `:216` as-is (`reposition` defaults true) so its behaviour is untouched.

Guard the invariant rather than trusting it. In `_candidate_frame`, after building the frame, assert
the positioning columns match the parent — cheap, runs once per candidate, and turns a future silent
wrong answer into a loud failure:

```python
_POSE_INVARIANT_COLUMNS = ("Tx", "Ty", "Tz", "At1", "At2", "At3")
```

**Correct the stale comment** at `rotational_event.py:360` while here. "candidates leave them
positioned at the final synthetic pose" was never true — candidates re-positioned to the *same* pose,
so the restore was already a no-op. Keep the restore call (cheap invariant, and
`test_phantoms_restored_to_static_pose_after_envelope` asserts a parent-frame `position` call exists),
but say what it actually does.

### 1b. Carry hit masks as boolean ndarrays in the hot path

**Files:** `src/guiskindose/beam_class.py`,
`src/guiskindose/calculate_dose/perform_calculations_for_new_geometries.py`,
`src/guiskindose/calculate_dose/add_correction_and_event_dose_to_output.py`,
`src/guiskindose/calculate_dose/rotational_event.py`

This is the single biggest win (~6 ms of 13.8 ms per candidate) and it also speeds up static events.

`Beam.check_hit` returns `hits.tolist()` (`beam_class.py:216`), so `hits` is a Python list of ~41 000
booleans and **every** numpy boolean-index operation re-converts the whole list: `event_dose[hits] +=`
costs 1.293 ms against 0.016 ms for an ndarray mask.

Do **not** change `check_hit`'s return type — `tests/unittests/test_beam_hit.py:23` and `:33` assert
`check_hit(patient) == [True, False]`, and two tests in `test_calculate_dose.py` mock it returning a
list. Instead add the array form and make the list form a wrapper:

```python
def check_hit_mask(self, patient: Phantom) -> np.ndarray:
    """Boolean entrance-cell mask (the array form of :meth:`check_hit`)."""
    ...

def check_hit(self, patient: Phantom) -> list[bool]:
    """List form of :meth:`check_hit_mask`, kept for the public API."""
    return self.check_hit_mask(patient=patient).tolist()
```

`perform_calculations_for_new_geometries` then calls `check_hit_mask` and returns an ndarray `hits`.
`compute_event_dose_vector` and `scale_field_area` accept either (`np.asarray(hits, dtype=bool)` is a
no-op on an array).

Convert back to `list[bool]` **at the output boundary only** — one conversion per event rather than
five per candidate:

- `calculate_irradiation_event_result.py:279` / `:281`
- `rotational_event.py:380` (already `list(static_hits)`) / `:381`

Two tests pin that the published value really is a list
(`test_calculate_dose.py:354`, `test_rotational_envelope_dose.py:78`), which is the behaviour we want;
they must keep passing unchanged. The export boundary is already tolerant of either
(`format_export_data.py:759`, `normalize_hit_masks` at `:47`, `analyze_data.py:251`) — leave that
belt-and-braces handling in place.

**Tests that need updating** (they mock a list return and assert list equality on the result):

- `tests/unittests/test_calculate_dose.py:239`/`:258` —
  `beam.check_hit.return_value = [False, False, False]` becomes `check_hit_mask.return_value =
  np.array([False, False, False])`, and `assert hits == [...]` becomes
  `np.testing.assert_array_equal(...)`.
- `tests/unittests/test_calculate_dose.py:272`/`:276` — same change for `hit_beam` / `miss_beam`.
- `assert table_hits == []` / `assert field_area == []` in the same tests become size assertions.

### 1c. Vectorize `scale_field_area`

**File:** `src/guiskindose/geom_calc.py:173`

`geom_calc.py:214` and `:222` are two Python comprehensions, one calling `np.linalg.norm` per cell.
Measured 3.211 ms → 0.015 ms (214×).

`scale_field_area` is re-exported as public API (`guiskindose/__init__.py:14`) and documented as
returning `List[float]`, so keep that signature and add the array form alongside, same pattern as 1b:

```python
def scale_field_area_array(...) -> np.ndarray:
    cells = patient.r[np.asarray(hits, dtype=bool)]
    distances = np.linalg.norm(cells - source, axis=1)
    return np.round(field_area_ref * np.square(distances / d_ref), 1)


def scale_field_area(...) -> list[float]:
    return scale_field_area_array(...).tolist()
```

**Stated caveat.** `np.round` scales by 10 and rounds; builtin `round` is decimal-aware. They can in
principle disagree on an exact decimal tie. The values are already quantized to 0.1 cm² and only feed
`sqrt` into a cubic spline, so the effect is orders of magnitude below any physical resolution — but
the new test should assert `np.allclose` against the old comprehension, not exact equality, and say
why in a comment. The full-pipeline golden in §4 is the real guard.

### 1d. Vectorize the entrance-cell filter in `check_hit`

**File:** `src/guiskindose/beam_class.py:212`

```python
# before
bool_entrance = [np.dot(temp1[i], temp2[i]) <= 0 for i in range(len(temp1))]
hits[hits] = bool_entrance
# after
hits[hits] = np.einsum("ij,ij->i", temp1, temp2) <= 0
```

Identical arithmetic — a row-wise dot product. Measured 1.435 ms → 0.015 ms (96×). Benefits every
event and every 3D phantom, not just rotational ones. `tests/unittests/test_beam_hit.py` covers both
the plane and the 3D-entrance branch and must pass unchanged.

### 1e. Vectorize the envelope bookkeeping loops

**File:** `src/guiskindose/calculate_dose/rotational_event.py`

- `_generate`'s union update (`:349`) is a Python `or`-loop over **all** cells, per candidate —
  0.733 ms. With `union_mask` as a `np.zeros(n_cells, dtype=bool)` it becomes
  `np.logical_or(union_mask, candidate_mask, out=union_mask)` at 0.001 ms (730×). Convert to
  `list[bool]` once, where it is published at `:381`.
- The two Python hit counts — `int(sum(1 for _ in filter(None, candidate_hits)))` (`:293`) and
  `int(sum(1 for hit in static_hits if hit))` (`:333`) — become `int(np.count_nonzero(mask))`.
- `evaluate_envelope` (`rotational_envelope.py:278`) allocates a fresh `n_cells` array per candidate
  via `running = maximum(running, ...)`. The module is deliberately numpy-free, so **do not change
  it**; pass an in-place-capable callable from the dose loop instead:
  `maximum=lambda a, b: np.maximum(a, b, out=a)`. Its contract (returns the folded array) still holds.
- `argmax_cell` (`rotational_envelope.py:279`) computes `np.argmax` **and** `np.max` but the caller
  discards the index. Pass `argmax_cell=lambda v: (0, float(v.max()))` — or, better, widen nothing and
  simply stop computing the argmax inside the injected lambda. The index is unused today; if it is
  ever wanted, it must come back as a real feature with a test, not as an accidental by-product.

### 1f. Memoize `calculate_k_med` on its snapped lookup key

**File:** `src/guiskindose/corrections.py:162`

Each call runs `_load_correction_table`, which returns `cached.copy(deep=True)` of the 715-row
`correction_medium_and_backscatter` table (`correction_data.py:122`), then four pandas mask passes —
0.504 ms, 360 deep copies per event.

`k_med` is a pure function of `(kvp, hvl, fsl)` where `fsl` is already snapped to one of
`[5, 10, 20, 25, 35]` (`corrections.py:192`, `:204`). Within one event `kvp` and `hvl` are constant
(§0), so the whole event needs at most five distinct lookups and usually one.

Split the function: keep `calculate_k_med`'s signature, move the table work into a cached
`_k_med_for_key(kvp, hvl, fsl, corrections_db)` behind an explicit small cache. Prefer an explicit
dict keyed on `(float(kvp), float(hvl), int(fsl), corrections_db)` over `functools.lru_cache`, so
`correction_data.clear_cache()` (tests only) has a matching `clear` to call and the cache cannot
outlive a corrections-source change. Wire that clear into whatever `clear_cache` already resets.

There is already a `NOTE (perf follow-up, only if profiles ever care)` at `corrections.py:207`
anticipating this — replace it with a pointer to this plan.

### 1g. Build the candidate frame once per event

**File:** `src/guiskindose/calculate_dose/rotational_event.py:63`

`_candidate_frame` constructs `pd.DataFrame([parent_row.values], columns=parent_row.index)` per
candidate: 0.24 ms, and it produces an **all-object-dtype** frame, which then makes every scalar
column read inside `Beam.__init__` slower than it needs to be. Build it once in
`_calculate_envelope_event` and assign the two angle cells per pose
(`frame.at[0, "Ap1"] = ...`). Keep `_candidate_frame` as the one-shot builder so its index-reset
contract (`event=0` positional addressing) stays in one place and documented.

---

## Phase 2 — hoist `Beam`'s per-event scalars

**File:** `src/guiskindose/beam_class.py:34`

After Phase 1, a profile of the prototype shows **~25 % of the remaining time** inside pandas
`DataFrame.__getattr__` / `_ixs`: 5040 calls for 360 candidates, i.e. the ~14
`data_norm.X[event]` scalar reads in `Beam.__init__`. All but `Ap1`/`Ap2` are constant across a
candidate domain (§0).

Expected: 360-pose envelope ~0.32 s → ~0.20 s.

This changes `Beam.__init__`'s surface, and `Beam` is constructed from plotting and geometry-preview
code paths too, so it needs its own review and its own PR. Shape to aim for: a small frozen
`BeamGeometryInputs` record built once per event, with `Beam.from_inputs(inputs, ap1, ap2, ap3)`
alongside the existing `Beam(data_norm=…, event=…)` constructor, which becomes a thin adapter. Do not
remove the DataFrame constructor.

## Phase 3 — optional follow-ons

Neither is required for the speedup; both are recorded so they are not forgotten.

- **`_deduplicate` is O(N²)** (`rotational_envelope.py:112`). Measured 0.003 s at 360 poses, 0.048 s
  at 1440, **0.378 s** for a 4078-pose coupled domain. Negligible against today's evaluation cost, but
  ~10 % of it after Phase 1. An O(N) quantized-key dedup would fix it **at the price of no longer
  being an exact pairwise-tolerance test** — if done, state the semantics change explicitly and keep
  the existing generator tests (positive/negative paths, exact 180°) passing unchanged.
- **Candidate-level progress.** `pbar.update()` fires once per **event**
  (`calculate_irradiation_event_result.py:312`), so a multi-second rotational event reports nothing and
  the GUI's `_update_progress` (`gui/tabs/calculate.py:522`) has nothing to show. After Phase 1 a
  360-pose event is ~0.3 s and this stops mattering; a 4000-pose `0.25`° domain would still benefit.

---

## 4. Acceptance

Phase 1 is done when all of the following hold.

1. **Static golden is bit-identical.** `test_calculate_dose_golden_baseline_siemens_cylinder`
   (`tests/unittests/test_calculate_dose.py:371`) already ends in
   `np.testing.assert_array_equal(dose_map, expected_dose_map)` against a saved `.npy`. It must pass
   **without regenerating the golden file**. This is the primary gate for 1b, 1c, 1d, and 1f.
2. **New rotational golden.** There is no envelope dose-map golden today. Add one: run
   `_frame_with_spin()` from `tests/unittests/test_rotational_envelope_dose.py` at a fixed
   `angular_step_deg`, save the dose map, and assert `assert_array_equal` against it. Generate the
   golden from `main` **before** starting Phase 1, commit it first, and never regenerate it inside
   this work. Without this, Phase 1a and 1e have no exact gate.
3. **Existing suites pass unchanged**, except the four `check_hit`-mocking assertions in
   `tests/unittests/test_calculate_dose.py` called out in 1b. Specifically:
   `test_rotational_envelope.py`, `test_rotational_envelope_dose.py`, `test_beam_hit.py`,
   `test_rotational_acquisition.py`, `test_rotational_normalizer_contract.py`.
4. **`test_psd_algorithm_doc.py` passes.** `dev-docs/PSD_CALCULATION_ALGORITHM.md` is machine-checked
   against the code. 1a changes when phantoms are positioned, and 1b changes the hit-mask type — check
   whether the doc describes either, and update the doc in the same PR if so.
5. **`test_phantoms_restored_to_static_pose_after_envelope` passes unchanged.** It asserts a
   parent-frame `Phantom.position` call at the envelope event exists. 1a keeps both the static-pose
   call and the explicit restore, so it should — verify rather than assume, because this is the test
   most likely to be surprised by 1a.
6. **A recorded before/after timing**, committed as a note in this plan or the assessment. Not a
   strict CI assertion (machine-dependent), but the number must be written down so a future regression
   is visible.
7. **No new warnings.** `emit_warnings=False` is threaded through the candidate path today; the
   memoization in 1f must not accidentally cache a *warning-emitting* first call and then suppress it
   for a later legitimate caller, nor the reverse. Key the cache on the lookup only and keep the
   warning decision outside it.

## 5. What this plan does not change

The envelope stays a pointwise maximum of full-kerma candidate responses with multiplier `1.0`. The
candidate domain, the short/long direction ambiguity, `include_static_pose`, the static-pose reuse
optimization, the `hits` / `hits_union` semantic split, the per-event correction slots, and every
ledger and disclosure field are untouched. `angular_step_deg` stays `1.0`. No public function is
removed and no return type on a public function changes — 1b and 1c add array variants beside the
list-returning originals rather than replacing them.
