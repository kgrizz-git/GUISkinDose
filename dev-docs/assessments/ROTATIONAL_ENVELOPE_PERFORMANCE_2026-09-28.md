# Rotational Coverage-Envelope Performance Assessment

Investigated: 2026-09-28 · Status: **evidence record; execution plan lives in**
[plans/ROTATIONAL_ENVELOPE_PERFORMANCE_PLAN.md](../plans/ROTATIONAL_ENVELOPE_PERFORMANCE_PLAN.md)

For the maintainer's question: *"the rotational acquisition coverage calculation is somewhat slow —
are there any inefficiencies that can be improved without degrading quality or accuracy?"*

**Answer: yes. A measured prototype runs the same 360-pose envelope 19× faster and returns
bit-identical dose** (max |difference| = `0.000e+00`, identical peak, identical hit masks). None of the
changes touch the physics, the candidate domain, the aggregation rule, or the disclosure ledger.

Source of truth for the feature itself:
[ROTATIONAL_COVERAGE_ENVELOPE_PLAN.md](../plans/ROTATIONAL_COVERAGE_ENVELOPE_PLAN.md). Historical
evidence record: [ROTATIONAL_ACQUISITION_ASSESSMENT.md](ROTATIONAL_ACQUISITION_ASSESSMENT.md). That
plan has no performance section; this assessment fills that gap and does not change any of its
contracts.

---

## 1. Why it is slow: the shape of the work

A rotational event is evaluated as N candidate poses, each of which runs a **complete** per-event
geometry + physics pass (`_calculate_envelope_event._compute` in
`src/guiskindose/calculate_dose/rotational_event.py:248`). N comes from the candidate domain:

| Domain | Where | N at the default `angular_step_deg = 1.0` | N at `0.25` |
|--------|-------|------------------------------------------|-------------|
| Type-only rotation, no usable endpoints | `closed_circle_domain` (`rotational_envelope.py:196`) | 360 | 1440 |
| One axis moving (short + long hypotheses) | `wrapped_paths` | up to ~720 | up to ~2880 |
| Both axes moving (4 coupled short/long combinations) | `build_candidate_domain` | ~1000 | **4078** (measured, 200°×30° sweep) |

So one spin event costs 360–4000 full event calculations. The default step is `1.0` degree
(`constants.py:60`), which is the common case.

The per-event cost itself is not the problem — a full 24-event static procedure on the `hudfrid`
human mesh (**41 022 skin cells**) takes **0.69 s** end to end. The problem is that each candidate
repeats work that is either redundant or done in pure Python.

---

## 2. Measurements

Microbenchmarks on the `hudfrid` mesh (41 022 cells), Siemens Axiom example procedure, event 1
(1520 hit cells). Scratch benchmark scripts were run from a gitignored `tmp/` path and are not
committed.

### 2.1 Per-candidate cost breakdown (current code)

| Step | Cost | Note |
|------|------|------|
| `compute_event_dose_vector` | **6.55 ms** | of which ~6.0 ms is `list[bool]` fancy-indexing, 0.50 ms `calculate_k_med` |
| `scale_field_area` | **3.21 ms** | Python `for`-loop calling `np.linalg.norm` once per hit cell |
| `beam.check_hit` | **2.00 ms** | of which 1.44 ms is a Python `for`-loop over hit cells |
| `union_mask` or-loop | **0.73 ms** | pure-Python loop over all 41 022 cells, per candidate |
| `_candidate_frame` (`pd.DataFrame` per pose) | 0.24 ms | |
| `patient`/`table`/`pad.position()` | 0.24 ms | **entirely redundant** — see §3.1 |
| `Beam(...)` | 0.11 ms | ~0.09 ms of it is pandas scalar column access |
| `hit_count = sum(1 for _ in filter(None, hits))` | 0.09 ms | |
| `check_table_hits`, `calculate_k_isq`, `np.maximum`, `argmax` | 0.10 ms | already vectorized |
| **Total per candidate** | **≈ 13.8 ms** | |

Extrapolated per rotational event: **5.0 s** at 360 poses, **20 s** at 1440,
**≈ 56 s** for the 4078-pose coupled two-axis domain at `0.25`°.

### 2.2 The `list[bool]` discovery

`Beam.check_hit` returns `hits.tolist()` (`beam_class.py:216`), so `hits` is a **Python list of 41 022
booleans**, and every numpy boolean-index operation on it re-converts the whole list:

| Operation | `hits` as `list[bool]` | `hits` as `ndarray[bool]` |
|-----------|------------------------|---------------------------|
| `event_dose[hits] += x` | 1.293 ms | **0.016 ms** |
| `patient.r[hits]` | 0.682 ms | **0.030 ms** |

`compute_event_dose_vector` does five such read-modify-write operations
(`add_correction_and_event_dose_to_output.py:52-59`), which is the whole 6 ms. This also taxes every
**static** event, not just rotational ones.

### 2.3 Prototype result

A prototype candidate step applying §3.1–§3.6 (ndarray hit masks, vectorized field area, vectorized
entrance-cell test, no redundant repositioning, memoized `k_med`, one reused candidate frame):

```
max |current - prototype| dose over sampled poses: 0.000e+00
current   360-pose envelope:   6.133 s  (peak 22.781107)
prototype 360-pose envelope:   0.319 s  (peak 22.781107)
speedup: 19.3x
```

Hit masks compared equal at every sampled pose. The peak dose is identical to all printed digits.

---

## 3. The inefficiencies, in priority order

### 3.1 Phantom repositioning is redundant for every candidate (bit-exact fix)

`perform_calculations_for_new_geometries` calls `patient.position()`, `table.position()`, and
`pad.position()` on every candidate. `Phantom.position` (`phantom_class.py:376`) reads **only**
`Rx`/`Ry`/`Rz` (from `At1–At3`) and `Tx`/`Ty`/`Tz`. A candidate frame is the parent row with **only
`Ap1` and `Ap2` overridden** (`rotational_event.py:63`), so those six inputs are identical for every
candidate and the recomputed `patient.r` is bit-identical each time.

360 candidates therefore redo 1080 phantom repositions — each a 41 022×3 copy plus three chained
matmuls — to arrive at the array they already had.

Fix: position the phantoms once per event, then evaluate candidates against the standing arrays.
Cleanest shape is an explicit `reposition: bool = True` parameter on
`perform_calculations_for_new_geometries`, so the static path is untouched and the envelope path opts
out.

Related: the "Restore the parent static pose on the shared phantoms" block at
`rotational_event.py:360` and its comment ("candidates leave them positioned at the final synthetic
pose") is **already a no-op** for the same reason. Keep the call as a cheap invariant, but the comment
should be corrected — it describes a hazard that does not exist.

### 3.2 `hits` should be a boolean ndarray internally (bit-exact fix, biggest single win)

Carry hit masks as `np.ndarray[bool]` through `perform_calculations_for_new_geometries`,
`compute_event_dose_vector`, `scale_field_area`, and `check_table_hits`, and convert to `list[bool]`
only at the `output[...]` boundary where the published contract requires a list.

Two traps the plan covers in detail and this summary would otherwise hide: the boundary conversion must
be `.tolist()` (or a `bool()` comprehension) because `list(ndarray)` yields `np.bool_` elements that are
not JSON-serializable; and the `sum(hits)` / `any(hits)` call sites must move to `.any()` in the same
edit, or iterating an ndarray in Python makes the change a net regression.

Worth ~6 ms of the 13.8 ms per candidate, and it speeds up static events too. Note there is an
existing reason the boundary conversion is explicit: `geom_calc.py:662` builds `[bool(h) for h in …]`
because newer numpy stubs fail basedpyright on `ndarray.tolist() -> list[bool]`. Keep that conversion
at the boundary; just stop doing it in the inner loop.

### 3.3 `scale_field_area` is a Python loop (behaviour-identical fix)

`geom_calc.py:214` and `:222`:

```python
scale_factor = [np.linalg.norm(cell - source) / d_ref for cell in cells]
field_area = [round(field_area_ref * np.square(scale), 1) for scale in scale_factor]
```

Vectorized equivalent measured at **0.015 ms vs 3.211 ms** (214×):

```python
np.round(field_area_ref * np.square(np.linalg.norm(cells - source, axis=1) / d_ref), 1)
```

The prototype used exactly this and matched to `0.000e+00`. One caveat to state in the PR:
`np.round` and builtin `round` can in principle disagree on a decimal tie, because `np.round` scales
by 10 and rounds while `round` is decimal-aware. The values are already quantized to 0.1 cm² and only
feed a `sqrt` into a cubic spline, so the effect is far below any physical resolution — but the test
should assert `np.allclose`, not exact equality, and say why.

### 3.4 `Beam.check_hit`'s entrance-cell filter is a Python loop (bit-exact fix)

`beam_class.py:212`:

```python
bool_entrance = [np.dot(temp1[i], temp2[i]) <= 0 for i in range(len(temp1))]
```

is a row-wise dot product. `np.einsum("ij,ij->i", temp1, temp2) <= 0` computes the same quantity at
**0.015 ms vs 1.435 ms** (96×), and helps every event and every 3D phantom, not just rotational.

It is **not** bitwise identical, though, and an earlier draft of this line wrongly said it was:
`np.dot` on a 1-D pair goes through BLAS `ddot` while `einsum` uses numpy's own summation order. Over
500 000 random 3-vector pairs, 34 % of the row products differ in the last ulp (max `1.819e-12`) — but
**0** flipped across the `<= 0` boundary, and the full-pipeline golden matched exactly. Only the sign
reaches the result, so the change is safe in practice while being gated by the golden rather than
guaranteed by construction. The plan carries the full risk statement and a revert path.

### 3.5 Envelope bookkeeping loops over all cells in Python (bit-exact fix)

In `rotational_event.py`:

- `_generate` (`:346`) updates the union mask with
  `for index, hit in enumerate(candidate_hits): union_mask[index] = union_mask[index] or bool(hit)` —
  41 022 Python iterations **per candidate**, 0.73 ms. `np.logical_or(union, mask, out=union)` is
  0.001 ms (730×).
- the two Python hit counts, `int(sum(1 for _ in filter(None, candidate_hits)))` (`:293`) and
  `int(sum(1 for hit in static_hits if hit))` (`:333`) — use
  `int(np.count_nonzero(mask))`, 0.086 ms → 0.001 ms.

In `rotational_envelope.evaluate_envelope`:

- `running = maximum(running, result.dose_vector)` allocates a fresh 41 022-float array per candidate.
  The injected callable is deliberately numpy-free, so pass an in-place-capable `maximum` from the
  dose loop (`lambda a, b: np.maximum(a, b, out=a)`) rather than changing the module.
- `argmax_cell` computes both `np.argmax` and `np.max` but the caller discards the index
  (`_, value = argmax_cell(...)`, `rotational_envelope.py:279`). Only the value is needed.

### 3.6 `calculate_k_med` deep-copies the whole correction table per candidate (memoizable)

`calculate_k_med` (`corrections.py:162`) calls `_load_correction_table`, and `get_table`
(`correction_data.py:122`) returns `cached.copy(deep=True)` of the 715-row
`correction_medium_and_backscatter` table — then runs four pandas mask passes. 0.50 ms per candidate,
360 deep copies per event.

`k_med` is a pure function of `(kvp, hvl, fsl)` where `fsl` is **snapped to one of five tabulated
field side lengths** (`corrections.py:192`, `:204`). Within one event `kvp` and `hvl` are constant, so
the whole event needs at most five distinct lookups and in practice one. Memoize on the snapped
`(kvp, hvl, fsl)` key. Bit-exact by construction.

There is already a `NOTE (perf follow-up, only if profiles ever care)` at `corrections.py:207`
anticipating this. This assessment is that profile.

### 3.7 `_candidate_frame` builds a DataFrame per pose (behaviour-identical fix)

`rotational_event.py:63` constructs `pd.DataFrame([parent_row.values], columns=parent_row.index)` for
every candidate — 0.24 ms, and it produces an **all-object-dtype** frame, which then makes the ~14
scalar column reads inside `Beam.__init__` slower than they need to be. Build the candidate frame once
per event and assign the two angle cells per pose.

### 3.8 Second-order: pandas scalar access inside `Beam.__init__`

After §3.1–§3.7, a profile of the prototype shows **~25 % of the remaining time** in pandas
`DataFrame.__getattr__` / `_ixs` — 5040 calls for 360 candidates, i.e. the ~14 `data_norm.X[event]`
scalar reads in `Beam.__init__` (`beam_class.py:34`). Hoisting those scalars once per event and
passing them (or a small frozen geometry record) to `Beam` would take the 360-pose envelope from
~0.32 s to roughly ~0.20 s. Worth a second phase, not the first.

### 3.9 Low priority: `_deduplicate` is O(N²)

`rotational_envelope.py:112` compares each pose against all accepted poses in Python. Measured:
0.003 s at 360 poses, 0.048 s at 1440, **0.378 s** for the 4078-pose coupled domain. Negligible
against today's 56 s of evaluation, but it becomes ~10 % of the cost once §3.1–§3.7 land. An O(N)
quantized-key dedup would fix it, at the price of no longer being an exact pairwise-tolerance test —
so if it is done, the tolerance semantics change must be stated, and the existing generator unit tests
(positive/negative paths, exact 180°) must still pass unchanged.

---

## 4. Explicitly rejected: bounding-volume early rejection

The obvious-looking "skip candidates whose beam cannot reach the phantom" test (phantom bounding
sphere against the four beam half-spaces — 4 dot products, conservative, therefore exact) was
prototyped and **measured to be a net loss**:

```
poses with >=1 hit: 360 / 360
prototype:                          0.319 s
prototype + bounding-sphere reject: 0.366 s
```

For an isocentred phantom in a full-circle sweep, essentially every pose hits, so the test never fires
and only adds a `Beam` construction plus four dot products per pose. Do not implement it. It could pay
off for a far off-isocentre phantom, but that is not the case that is slow.

---

## 5. Phased fix plan

Moved to [plans/ROTATIONAL_ENVELOPE_PERFORMANCE_PLAN.md](../plans/ROTATIONAL_ENVELOPE_PERFORMANCE_PLAN.md),
which carries the per-file change list, the invariant the whole thing rests on, the tests that need
updating, and the acceptance gate. In outline: Phase 1 is the seven bit-exact hot-loop edits above
(the 19x win), Phase 2 hoists `Beam`'s per-event scalar reads (~35 % more), Phase 3 is the optional
`_deduplicate` rewrite and candidate-level progress reporting.

## 6. What this does not change

The envelope stays a pointwise maximum of full-kerma candidate responses with multiplier `1.0`; the
candidate domain, the short/long direction ambiguity, `include_static_pose`, the static-pose reuse
optimization, the `hits` / `hits_union` semantic split, the per-event correction slots, and every
ledger and disclosure field are untouched. No default changes — in particular `angular_step_deg`
stays `1.0`. The speedup comes from not repeating work, not from evaluating fewer poses.
