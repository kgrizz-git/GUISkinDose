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

  Worth spelling out, because it is the one thing a reader can get backwards: `Rx`/`Ry`/`Rz` are
  DataFrame columns built by `helpers/calculate_rotation_matrices.py` from **`At1`/`At2`/`At3` only**
  — the *table* rotation. Its module docstring says so outright: "Positioner (C-arm) angles
  Ap1/Ap2/Ap3 are handled separately in beam geometry, not here." `Beam.__init__` builds its own,
  separate rotation matrices from `Ap1`/`Ap2`/`Ap3` (`beam_class.py:73–99`) and never touches the
  phantom. So the candidate angles move the beam and cannot move the phantom — verified: for a
  candidate frame, `Rx`/`Ry`/`Rz` come through equal to the parent's, and a reused frame yields
  `beam.r` and `beam.N` bit-identical to a freshly built one.
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

Guard the invariant rather than trusting it. After building the candidate frame, assert its
positioning columns match the parent — this turns a future silent wrong answer into a loud failure.
Note the interaction with 1g: once the frame is built once per event, the guard runs **once per event**,
not once per candidate, which makes it free enough to keep in production rather than behind a debug
flag:

```python
# Rx/Ry/Rz are included even though they are derived from At1-At3: they are
# what position() actually reads, so guarding the derived value as well as its
# inputs keeps the check honest if calculate_rotation_matrices ever changes.
_POSE_INVARIANT_COLUMNS = ("Tx", "Ty", "Tz", "At1", "At2", "At3", "Rx", "Ry", "Rz")
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

**Convert the `sum()` / `any()` call sites in the same edit — this is not optional.** `sum()` and
`any()` over an ndarray iterate it element by element in Python, boxing every value, so leaving them
alone turns Phase 1b into a *net regression*. Measured on 41 022 elements:

| Expression | Cost | Replace with | Cost |
|---|---|---|---|
| `sum(list[bool])` (today) | 63 µs | — | — |
| `sum(ndarray)` (after 1b, unfixed) | **964 µs** | `mask.any()` | **0.5 µs** |
| `any(ndarray)` all-miss (after 1b, unfixed) | 161 µs | `mask.any()` | 0.7 µs |
| — | — | `np.count_nonzero(mask)` | 1.2 µs |

The sites, all on the per-candidate path:

- `perform_calculations_for_new_geometries.py:77` — `if sum(hits):` → `if hits.any():`
- `add_correction_and_event_dose_to_output.py:40` — `if not sum(hits):` → `if not hits.any():`
- `rotational_event.py:264` — `if not any(candidate_hits):` → `if not candidate_mask.any():`

Two of those run per candidate, so left unfixed they add ~1.9 ms to a per-candidate budget of ~0.9 ms
and the 19× headline collapses to roughly 6–7×. The prototype these numbers come from never called
`sum()` — it used `.any()` throughout — so this is the plan under-transcribing its own prototype, not a
flaw in the measurement. Anyone implementing 1b from the earlier draft would have missed it.

**Convert back to `list[bool]` at the output boundary with `.tolist()`, never `list(...)`.** This is a
silent-corruption trap, verified on numpy 2.4.2:

| Expression | Element type | `isinstance(x, bool)` | `json.dumps` |
|---|---|---|---|
| `list(mask)` | `np.bool_` | **False** | **raises `TypeError`** |
| `mask.tolist()` | `bool` | True | OK |

`list(ndarray)` yields `np.bool_` elements, which are *not* Python bools and are **not JSON
serializable** — so a dict/JSON export would raise at the boundary. Worse, the guard tests would not
catch it: `test_calculate_dose.py:354`'s `isinstance(output["hits"][ev], list)` checks only the outer
type and passes deceptively, and `format_export_data.py:759`'s
`event if isinstance(event, list) else event.tolist()` would pass the `np.bool_` elements straight
through into `PySkinDoseOutput.hits`.

The sites:

- `calculate_irradiation_event_result.py:279` / `:281`
- `rotational_event.py:380` — currently `list(static_hits)`, which is correct **only** while
  `static_hits` is a list. Once 1b makes it an array this line must change to `.tolist()`. An earlier
  draft of this plan described it as "already `list(static_hits)`", which is exactly the wrong
  reading — treat it as a required edit.
- `rotational_event.py:381` (the union mask, now an array per 1e)

**Use the comprehension form, not `.tolist()`, wherever basedpyright sees a `list[bool]` return.** The
`check_hit` wrapper shown above cannot literally be `return self.check_hit_mask(...).tolist()`: newer
numpy stubs type `tolist()` as unassignable to `list[bool]`, which is the documented reason
`geom_calc.py:662` already writes `[bool(hit) for hit in hits]`. Use that form in any annotated
`-> list[bool]` position and keep `.tolist()` for the unannotated output-dict assignments.

**Reconcile with the assessment on `check_table_hits`.** The assessment's §3.2 includes
`check_table_hits` (`geom_calc.py:582`) in the ndarray conversion; this plan's file list for 1b
originally omitted `geom_calc.py`. Decision: **include it** — return the mask as an array so
`temp[table_hits] = k_tab_scalar` (`add_correction_and_event_dose_to_output.py:57-58`) stops converting
a list per candidate. Same public-API treatment as 1b/1c if any caller needs the list form; today the
only caller is `perform_calculations_for_new_geometries.py:79`.

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

**The rounding question, settled by measurement.** `np.round` scales by 10 and rounds; builtin
`round` is decimal-aware, so they can in principle disagree on an exact decimal tie — and this plan
requires the existing `assert_array_equal` golden (§4.1) to pass *without regeneration*, so a single
tie would be a showstopper rather than a rounding nicety. It was therefore checked directly rather
than argued:

- Every field-area value the example procedure produces was computed both ways: **30 222 values
  across the cylinder, plane, and human phantoms, all identical, max difference `0.000e+00`.**
- End to end, with 1c *and* 1d patched in, the golden dose map for
  `siemens_axiom_artis.dcm` + cylinder matched the committed
  `tests/fixtures/golden/calculate_dose_siemens_axiom_artis_cylinder_dose_map.npy` **exactly**
  (`np.array_equal` true, PSD `1.3020214659058027` before and after, per-event hit counts and `k_med`
  unchanged).

So the new unit test should assert **exact** equality against the old comprehension, not
`np.allclose` — asserting a tolerance would hide precisely the tie this was checked for. The residual
theoretical risk is only that some *future* fixture lands on a tie, and the golden gate is what would
catch it; note that in the test's docstring so a future failure is read correctly rather than being
papered over with a tolerance.

### 1d. Vectorize the entrance-cell filter in `check_hit`

**File:** `src/guiskindose/beam_class.py:212`

```python
# before
bool_entrance = [np.dot(temp1[i], temp2[i]) <= 0 for i in range(len(temp1))]
hits[hits] = bool_entrance
# after
hits[hits] = np.einsum("ij,ij->i", temp1, temp2) <= 0
```

Measured 1.435 ms → 0.015 ms (96×). Benefits every event and every 3D phantom, not just rotational
ones. `tests/unittests/test_beam_hit.py` covers both the plane and the 3D-entrance branch and must pass
unchanged.

**This is the one Phase-1 edit that is NOT bit-identical by construction.** An earlier draft called it
"identical arithmetic"; that is wrong. `np.dot` on a 1-D float64 pair dispatches to BLAS `ddot`, while
`np.einsum` uses numpy's own kernels with a different summation order. Measured over 500 000 random
3-vector pairs with mixed magnitudes: **170 848 (34 %) of the row dot products differ bitwise**, max
absolute difference `1.819e-12`.

What makes it usable anyway is that only the **sign** feeds the result — `<= 0` — and a differing last
ulp changes the sign only when the true dot product is within an ulp of zero:

- **0 of 500 000** trials flipped across the `<= 0` boundary.
- End to end on real data, the golden dose map matched exactly with 1c *and* 1d applied.

So the honest classification is *equivalent up to floating point, gated by the golden* — the same class
as 1c, not a class of its own. Consequences to accept before implementing:

- A boundary flip would not be a last-ulp dose wiggle. It adds or removes a cell from the hit mask, and
  that cell's dose changes by the **full event contribution** — a visible dose-map artefact.
- The evidence is one machine's BLAS. CI runs the golden on Ubuntu and Windows at PR time and macOS
  weekly, so einsum-vs-that-platform's-BLAS agreement is a **new, untested equivalence**. If a
  platform's golden goes red on this edit and nothing else, 1d is the cause.
- **Revert path:** 1d is independent of every other edit. Drop it and keep the rest; the remaining
  Phase-1 work still delivers the great majority of the speedup, since 1d is 1.4 ms of 13.8 ms.

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
- `argmax_cell` (`rotational_envelope.py:279`) computes `np.argmax` **and** `np.max`, but the caller
  destructures `_, value =` and throws the index away. `evaluate_envelope` unpacks a two-tuple, so the
  contract must stay a two-tuple: pass `argmax_cell=lambda v: (0, float(v.max()))` and stop computing
  the argmax. That is the only change here — do **not** try to narrow `evaluate_envelope`'s signature.
  The index is dead today; if it is ever wanted, it comes back as a real feature with a test, not as an
  accidental by-product.

### 1f. Memoize `calculate_k_med` on its snapped lookup key

**File:** `src/guiskindose/corrections.py:162`

Each call runs `_load_correction_table`, which returns `cached.copy(deep=True)` of the 715-row
`correction_medium_and_backscatter` table (`correction_data.py:122`), then four pandas mask passes —
0.504 ms, 360 deep copies per event.

`k_med` is a pure function of `(kvp, hvl, fsl)` where `fsl` is already snapped to one of
`[5, 10, 20, 25, 35]` (`corrections.py:192`, `:204`). Within one event `kvp` and `hvl` are constant
(§0), so the whole event needs at most five distinct lookups and usually one.

Split the function: keep `calculate_k_med`'s signature, move the table work into a cached
`_k_med_for_key(kvp, hvl, fsl, source_key)` behind an explicit small cache. Prefer an explicit dict
over `functools.lru_cache`, so `correction_data.clear_cache()` (tests only) has a matching `clear` to
call and the cache cannot outlive a corrections-source change. Wire that clear into whatever
`clear_cache` already resets.

Key on `(float(kvp), float(hvl), int(fsl), source_key)` where `source_key` is the **resolved** source
identity from `resolve_corrections_source`, not the raw `corrections_db` string. The raw string would
give the same database separate cache entries when reached by different spellings — the test suite
passes both `"corrections.db"` and absolute paths — which is not a correctness bug but does silently
throw away the cache.

**The warning hoist, with a mechanism rather than an instruction.** `_warn_once`
(`correction_data.py:152-155`) returns early when `emit_warnings=False` **before** adding the class to
`_warned`, so it does not latch. That produces a concrete regression if the memo wraps the warning:

1. An envelope event runs first. Its candidates pass `emit_warnings=False`
   (`rotational_event.py:240`, `:286`), so the deprecation warning is suppressed and the memo is
   populated for key `K`.
2. A later legacy-static event hits the same key `K` with `emit_warnings=True` (the default from
   `add_corrections_and_event_dose_to_output`). It gets a cache hit, never calls
   `_load_correction_table`, and therefore **never reaches `resolve_corrections_source`** — losing a
   warning the code emits today.

So the split must be: the memoized helper covers the *table lookup only*, and
`calculate_k_med` calls `resolve_corrections_source` (or whatever raises the source-level warning)
**unconditionally on every call, outside the memo**, threading the real `emit_warnings` through. The
cache key then covers the lookup; the warning decision is never cached. Add a regression test for
exactly the ordering above — envelope event first, static event second, warning still emitted.

There is already a `NOTE (perf follow-up, only if profiles ever care)` at `corrections.py:207`
anticipating this work — replace it with a pointer to this plan.

### 1g. Build the candidate frame once per event

**File:** `src/guiskindose/calculate_dose/rotational_event.py:63`

`_candidate_frame` constructs `pd.DataFrame([parent_row.values], columns=parent_row.index)` per
candidate: 0.24 ms of pure construction cost. Build it once in `_calculate_envelope_event` and assign
the two angle cells per pose (`frame.at[0, "Ap1"] = ...`). Keep `_candidate_frame` as the one-shot
builder so its index-reset contract (`event=0` positional addressing) stays in one place and
documented.

Verified rather than assumed, since reusing a frame across poses invites dtype surprises: the frame is
**mixed**-dtype (`float64`, `int64`, `str`, `object`), not all-object as first supposed; `.at`
assignment leaves `Ap1`/`Ap2` as `float64` and changes no other column's dtype; and `Beam` built from
the reused frame gives `beam.r` and `beam.N` bit-identical to one built from a fresh frame, at
`Ap1` = 0, 37.5, and 180 degrees.

### 1h. Type annotations and API-surface decisions

Two things Phases 1b and 1c imply that are easy to leave half-done. This repo runs **basedpyright** as
a pre-push hook, so a half-updated annotation fails the push, not CI.

- `perform_calculations_for_new_geometries` annotates `hits: list[bool]`, `table_hits: list[bool]`,
  `field_area: list[float]` and returns `tuple[list[bool], list[bool], list[float], np.ndarray]`.
  After 1b/1c the hot path carries arrays. Widen the parameters to accept either
  (`Sequence[bool] | np.ndarray`) and make the return type say what it actually returns. Same for
  `compute_event_dose_vector`'s `hits`/`table_hits`/`field_area`. Update the numpydoc blocks in the
  same edit — the docstrings state `List[bool]` in prose and `check_doc_freshness.py` scans docs, not
  docstrings, so nothing will catch a stale one but a reader.
- There is already precedent for why the boundary conversion is explicit rather than
  `ndarray.tolist()`: `geom_calc.py:662` builds `[bool(hit) for hit in hits]` with a comment that newer
  numpy stubs type `tolist()` as unassignable to `list[bool]` under basedpyright. Expect the same
  friction at any new boundary and reuse that pattern.
- **`check_hit_mask` and `scale_field_area_array` are internal.** Do **not** add them to
  `guiskindose/__init__.py`. The public surface stays `check_hit` and `scale_field_area`, which is the
  whole point of adding variants beside them rather than changing them. State this in their docstrings
  so a later contributor does not "helpfully" export them.

---

## Phase 2 — hoist `Beam`'s per-event scalars

**File:** `src/guiskindose/beam_class.py:34`

After Phase 1, a profile of the prototype shows **~25 % of the remaining time** inside pandas
`DataFrame.__getattr__` / `_ixs`: 5040 calls for 360 candidates, i.e. the ~14
`data_norm.X[event]` scalar reads in `Beam.__init__`. All but `Ap1`/`Ap2` are constant across a
candidate domain (§0).

Expected: 360-pose envelope ~0.32 s → ~0.20 s.

**Record one hazard now, before anyone starts Phase 2:** `Beam.__init__` reads
`data_norm.DSL[0]` — index `[0]`, not `event` (`beam_class.py:161`) — while every other scalar is read
at `event`. Hoisting "per-event scalars" must preserve that quirk exactly and take `DSL` the same way it
is taken today. Do **not** silently "fix" it to `DSL[event]` as part of a performance change: if `DSL`
ever varies across events, that is a numbers change wearing a refactor's clothes, and it belongs in its
own PR with its own golden discussion.

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
2. **New rotational golden — and it must use a cylinder, not a plane.** There is no envelope
   dose-map golden today. Add one: run `_frame_with_spin()` from
   `tests/unittests/test_rotational_envelope_dose.py` at a fixed `angular_step_deg`, save the dose map,
   and assert `assert_array_equal`. Generate it from `main` **before** starting Phase 1, commit it
   first, and never regenerate it inside this work. Without it, Phases 1a and 1e have no exact gate.

   **Override the phantom model to `cylinder`.** That test module's `_settings` helper forces
   `phantom.model = "plane"` (`test_rotational_envelope_dose.py:19`), and the entrance-cell filter that
   1d rewrites is guarded by `if patient.phantom_model != "plane"` (`beam_class.py:208`). A
   plane-phantom rotational golden would therefore gate 1a, 1b, 1c, 1e, and 1f but **never execute 1d
   at all** — leaving 1d's only exact gate the *static* Siemens cylinder golden, and leaving the
   envelope path (the thing actually being optimized, and where grazing cells with
   `dot(v, n) ≈ 0` live) untested for it. A cylinder run is still cheap and closes that hole.
3. **Existing suites pass unchanged**, except the four `check_hit`-mocking assertions in
   `tests/unittests/test_calculate_dose.py` called out in 1b. Specifically:
   `test_rotational_envelope.py`, `test_rotational_envelope_dose.py`, `test_beam_hit.py`,
   `test_rotational_acquisition.py`, `test_rotational_normalizer_contract.py`.
4. **`test_psd_algorithm_doc.py` passes — and the doc needs no change.** Resolved rather than left as
   a check: `dev-docs/PSD_CALCULATION_ALGORITHM.md:175-186` describes this stage as "Patient, table,
   and pad are positioned for this event" and "yielding boolean `hits`". Both stay true after 1a (still
   positioned for this event, just once) and 1b (still boolean, different container). The doc test pins
   entry-point *names*, and 1a only adds a keyword parameter to
   `perform_calculations_for_new_geometries`, so the name survives. Re-run the test rather than
   assuming, but do not expect a doc edit.
5. **`test_phantoms_restored_to_static_pose_after_envelope` passes unchanged**
   (`tests/unittests/test_rotational_envelope_dose.py:120`). It collects every `Phantom.position` call
   and asserts `assert parent_calls` — that *at least one* parent-frame call at the envelope event
   exists. After 1a there are **two** (the new unconditional positioning at the top of
   `_calculate_envelope_event`, plus the existing restore at the bottom) instead of one-per-candidate.
   A non-empty check is satisfied by two, so it passes; the point is that the test constrains
   existence, not count. If anyone later tightens it to an exact count, it must be written against 1a's
   two calls.

   Related: the phantom-positioning change alters *when* `Phantom.position` runs, so it is the one
   Phase-1 edit whose correctness is not provable from arithmetic alone. The new rotational golden in
   §4.2 is what actually gates it.
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
