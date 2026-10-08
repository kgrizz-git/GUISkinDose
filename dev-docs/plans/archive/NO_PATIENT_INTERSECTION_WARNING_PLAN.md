# COMPLETED — shipped 2026-06-24

> **Status:** Implemented and all tests passing (329/329). Plan is archived at `dev-docs/plans/archive/NO_PATIENT_INTERSECTION_WARNING_PLAN.md`.

<details>
<summary>Revision history (2026-06-24 reviews)</summary>

**Round 1 (self-review):**
1. **Phase 0 fix description** — corrected: `addHandler` was already before the `if`; the fix is only to wrap both branches in `try/finally`.
2. **`KEY_PARAM_BEAM_MISS_WARN` usage** — now consistently used in `pyskindose_settings.py` (was literal string, now uses the imported constant, matching `KEY_PARAM_BELOW_FLOOR_KVP_POLICY` pattern).
3. **Test fixture guidance** — added §3.10 with concrete fixture construction approach (large patient offset vs normalised data, `caplog` usage).
4. **NaN guard for field area** — added `float()` wrapping note in §4.2 step 2.
5. **`_MAX_TOASTS` explicit definition** — added module-level constant definition code block.
6. **GUI `beam_miss_warn` select widget** — added explicit placement and code pattern in §4.5.1.

**Round 2 (assessment at `tmp/assessment_20260624_232935.md`):**
7. **RangeIndex assumption** — corrected: pipeline already relies on `rdsr_normalizer`'s guaranteed 0..N−1 `RangeIndex`; `.iloc` is defensive, not a non-RangeIndex fix. Updated §3 item 2, §4.2 step 2 comment, §6.
8. **Summary truncation** — replaced manual list construction with existing `format_event_indices` helper from `guiskindose.grid_interp`. Updated §4.2 step 3, §6.
9. **Status label source** — replaced fragile substring-matching with direct lookup from `output["missed_event_indices"]`. Updated §4.5.4, §6.
10. **Multi-exam downgrade log** — moved from per-exam loop to once-before-loop to avoid spam. Updated §4.4, §6.

</details>

# No-Patient-Intersection Warning Plan

Plan for `TO_DO.md` item: *"Add debug/warning if any dose events have no intersection with patient."*

## 1. Objective

Surface a clear, actionable warning when an irradiation event deposits **no dose to the patient phantom** because the beam does not intersect the patient surface. Today this case is silent: `perform_calculations_for_new_geometries` (`calculate_dose/perform_calculations_for_new_geometries.py:39-65`) returns an empty `hits` list and the per-event dose is just zero — indistinguishable from a valid event with a very small DAP.

A miss is almost always one of:

- an **incorrect patient offset** (`d_lon` / `d_ver` / `d_lat`),
- a **vendor coordinate frame** mismatch (e.g. un-swapped lat/lon for GE — see `VENDOR_COORDINATE_SYSTEMS.md`),
- a **misread / wrong-patient RDSR**,
- a **rotational acquisition** modelled as a single static `Ap1` / `Ap2` (the related `TO_DO.md` "Review rotational-acquisition handling" item),
- or (legitimately) a beam aimed at the table / pad only (calibration, table-only fluoro, QA).

The plan ships a warning for the first four cases and **does not** try to distinguish the legitimate fifth — the user decides.

## 2. Background & relevant code

- **Hit detection** — `Beam.check_hit(patient)` (`beam_class.py:181`) returns `List[bool]`, one per patient skin cell.
- **Per-event orchestration** — `perform_calculations_for_new_geometries` (`calculate_dose/perform_calculations_for_new_geometries.py:17`) calls `check_hit`, then short-circuits when `not sum(hits)` (line 60-65 resets `table_hits` / `field_area` / `k_isq`). The miss is currently logged only at `DEBUG`.
- **Per-event loop** — `calculate_irradiation_event_result` (`calculate_dose/calculate_irradiation_event_result.py:98`) loops over `range(event, total_events)` and writes `output[OUTPUT_KEY_HITS][ev] = hits` per event.
- **Multi-exam path** — `analyze_multiple_exams` (`analyze_data.py:103-256`) calls `calculate_dose(...)` per exam, getting `(patient, raw_output)`, and collects per-exam warnings into `ExamResult.warnings`.
- **GUI surfacing** — `state.calc_warnings` (`gui/state.py:91`) is populated by a `WARNING+` log collector in `gui/helpers.py:144-202`; `gui/tabs/calculate.py:233-238` shows the count and toasts each message. We will reuse this — the change is just to emit `logger.warning(...)` at the right point.
- **Pre-existing handler leak** — the same collector block has a bug (Phase 0): the multi-exam branch never calls `_calc_logger.removeHandler(_collector)`, leaking handlers and producing exponentially duplicated toasts across runs. Fix lands first.
- **CLI surfacing** — `main.py:114, 121, 163, 396` already pass through `logger.warning` to stderr. No CLI code change needed.
- **Precedent** — HVL / grid-interp / below-floor-kVp warnings (`geom_calc.py:303-342`, `corrections.py:304-317`, `grid_interp.py`) ride the same collector. This plan follows that pattern.

## 3. Acceptance criteria

1. **Per-event warning emitted once** when `not any(hits)` in `calculate_irradiation_event_result`.
2. **Warning message** identifies the event (1-based index, total, exam id when multi-exam), the kVp / filtration / field size (so the user can recognise the event in the Data Table), and points at the likely remediation (offset sliders / vendor coordinate toggle / rotation handling). Fields, sourced from the normalized DataFrame via **`.iloc[ev]` (positional) indexing**:
    - `{kVp}` ← `float(normalized_data[c.KEY_NORMALIZATION_KVP].iloc[ev])` (kV). `c.KEY_NORMALIZATION_KVP` is the standard `from guiskindose import constants as c` alias used in `calculate_irradiation_event_result.py` and `geom_calc.py:246, 248, 299`. Use `.iloc[ev]` for positional indexing — the pipeline's existing `[ev]` label-based accesses (e.g. `normalized_data.K_IRP[ev]` at line 117) work because `rdsr_normalizer` guarantees a clean 0..N−1 `RangeIndex`, but `.iloc` is the safer defensive choice in new warning code.
    - `{filter}` ← `f"{normalized_data.filter_thickness_Cu.iloc[ev]:g} mm Cu + {normalized_data.filter_thickness_Al.iloc[ev]:g} mm Al"`. Same columns as `geom_calc.py:422-423` / `corrections.py:247-248`; key strings in `constants.py:106-107`.
    - `{a}` ← detector-plane field area in cm², `float(normalized_data.FS_lat.iloc[ev]) * float(normalized_data.FS_long.iloc[ev])` (matches `field_area_ref` in `geom_calc.py:216`; keys in `input_adapters/normalized.py:74-75`). This is the collimated area at the detector, not the skin-plane area — `field_area` is empty for a missed event.
    - Resulting format: `"Event {i+1}/{N} (exam {id}, {kVp:.0f} kVp, {filter_desc}, field {field_area_cm2:.1f} cm²): beam does not intersect patient — check patient offsets and vendor coordinate frame."`
3. **No double-warning** between the per-event path and the multi-exam orchestrator. `calculate_irradiation_event_result` is the **single owner** of every `logger.warning` call; `analyze_multiple_exams` builds per-exam strings in memory and appends them to `exam_warnings` only.
4. **GUI surfacing** — message appears in `state.calc_warnings`, counted on the Calculate tab status line, and toasted (throttled — see §4.5). The full list is also visible in the Results-tab `ExamResult.warnings` accordion.
5. **CLI surfacing** — message appears on stderr at `WARNING` level; no code path change needed.
6. **Opt-out / dial-down** — a new setting `beam_miss_warn ∈ {"off", "summary", "per_event"}` (CLI default `"per_event"`, GUI default `"summary"`) controls verbosity. `"summary"` emits one warning per run with the count and affected indices; `"off"` emits nothing per-event / per-run (the all-miss sentinel still fires). Surfaced in GUI Settings → Physics.
7. **All-miss sentinel** — when **every** event in a run misses, emit `"All {N} events missed the patient phantom — dose map is all zeros; check patient offsets and vendor coordinate frame."` Always-on, regardless of the dial, not gated on `settings` (unit tests / legacy paths must still see it).
8. **Tests** in `tests/unittests/test_calculate_dose.py` (appended — `tests/calculate_dose/` does not exist):
    - single event whose beam is offset far from the phantom → exactly one `WARNING` with the expected substring.
    - mixed run (3 hit, 2 miss) → two `WARNING`s with the right 1-based indices.
    - all-miss run → per-event warnings **plus** the all-miss sentinel; the per-run summary does **not** fire (K == N, not 0 < K < N).
    - `beam_miss_warn="off"` → zero per-event warnings; the all-miss sentinel still fires.
    - multi-exam: one exam fully misses, one hits → per-exam summary string in `exam_warnings` for the first; per-event warnings for the second only if the per-event dial is on.
    - `None`-guard: a legacy call without `settings` does not raise `AttributeError` and the all-miss sentinel still fires.
    - golden baselines (`tests/unittests/test_calculate_dose.py::TestGoldenBaselines`) continue to pass.
9. **Docs** — one-line note in `FEATURE_INVENTORY.md` (Calculations / Diagnostics). `AGENTS.md` and `CLAUDE.md` are unchanged.
10. **Test fixture construction** — the existing `generate_synthetic_normalized_events` helper produces events that hit the phantom by design. For no-hit tests, use a large patient offset on the existing Siemens 21-event dataset (e.g. `d_lon=500` shifts the patient far enough that the beam misses all skin cells). Pass this offset via `PyskindoseSettings` through the normal `_run_calculate_dose()` path. Capture warnings with `caplog.at_level(logging.WARNING, logger="guiskindose")`. For the single-event test case, use `_run_calculate_dose()` and verify `caplog.records`. For the mixed case (3 hit / 2 miss), use a smaller offset or a custom 5-event dataset where geometry is perturbed to straddle the phantom boundary — the exact fixture values will be tuned during Phase 1.

## 4. Implementation outline

### 4.1 Settings

- **`PyskindoseSettings`** (`settings/pyskindose_settings.py:79`):
  - `self.beam_miss_warn: str = tmp.get(KEY_PARAM_BEAM_MISS_WARN, "per_event")` — the `tmp.get(..., "per_event")` fallback is mandatory so existing user configs and test parameter dicts (which pre-date this field) load without `KeyError`. Mirrors the `below_floor_kvp_policy` pattern at `pyskindose_settings.py:127-129`.
  - Add `KEY_PARAM_BEAM_MISS_WARN = "beam_miss_warn"` to `constants.py` (alongside `KEY_PARAM_BELOW_FLOOR_KVP_POLICY` at `constants.py:38`) and import it into `pyskindose_settings.py`'s import block the same way (top-level import, **not** the `c.` prefix — the two prefix conventions are different: `c.KEY_NORMALIZATION_KVP` in the calc module, `KEY_PARAM_*` in the settings module).
  - The `Literal` annotation is fine for typecheck; the runtime value is a plain `str`.
- **`AppState`** (`gui/state.py:19`) — add `beam_miss_warn: str = "summary"` next to `below_floor_kvp_policy: str = "snap"` (line 73). GUI default is `"summary"`, **not** `"per_event"`, to avoid flooding the user with toasts on a typical multi-event calculation.
- **`build_settings`** (`gui/settings_builder.py:17-57`) — without an explicit `base["beam_miss_warn"] = app_state.beam_miss_warn` line, any change the user makes in the GUI Settings tab is silently dropped on calculation. Add the mapping next to the `below_floor_kvp_policy` line (line 31).
- **`settings_example.json`** — add `"beam_miss_warn": "per_event"` (CLI default).

### 4.2 Core emission (`calculate_irradiation_event_result`)

Two new optional kwargs: `settings: PyskindoseSettings | None = None` and `exam_id: str | None = None`. Both default to `None` so legacy callers (the single call site in `calculate_dose.py:117` already passes `settings` via threading; unit tests that don't inject a settings object) keep working without `AttributeError`.

1. **Per-event detection** — initialise `missed_event_indices: list[int] = []` before the loop. After each `perform_calculations_for_new_geometries` call, `if not any(hits): missed_event_indices.append(ev)`.
2. **Per-event warning** — inside the same branch, build (variable definitions from §3 item 2; reiterated here for self-containedness of the implementation outline):

    ```python
    # positional .iloc — safer than label-based [ev] (redundant given
    # rdsr_normalizer's guaranteed RangeIndex, but defensive for warnings)
    kVp = float(normalized_data[c.KEY_NORMALIZATION_KVP].iloc[ev])
    filter_desc = (
        f"{normalized_data.filter_thickness_Cu.iloc[ev]:g} mm Cu + "
        f"{normalized_data.filter_thickness_Al.iloc[ev]:g} mm Al"
    )
    # float() wraps guard against NaN in corrupted data (rare but defensive)
    # Note: float(np.nan) → nan, which displays as "field nan cm²" — acceptable
    # in a warning context; the value won't crash the format string.
    field_area_cm2 = (
        float(normalized_data.FS_lat.iloc[ev])
        * float(normalized_data.FS_long.iloc[ev])
    )

    exam_str = f"exam {exam_id}, " if exam_id else ""
    msg = (
        f"Event {ev + 1}/{total_events} ({exam_str}{kVp:.0f} kVp, "
        f"{filter_desc}, field {field_area_cm2:.1f} cm²): "
        f"beam does not intersect patient — check patient offsets and vendor coordinate frame."
    )
    if settings is not None and settings.beam_miss_warn == "per_event":
        logger.warning(msg)
    ```
    The `settings is not None` guard is **mandatory** — without it, a `None` `settings` (unit tests, legacy paths) raises `AttributeError`. The conditional `exam_str` keeps single-exam messages clean ("exam" appears only when there is an id).
3. **Per-run summary (only in `"summary"` mode)** — after the loop, if `settings is not None and settings.beam_miss_warn == "summary" and 0 < K < total_events` where `K = len(missed_event_indices)`, emit one `logger.warning` using the existing `format_event_indices` helper from `guiskindose.grid_interp` (which returns `"[1, 2, 3] (+5 more)"` for overflow, or just `"[1, 2, 3]"` when within limit): `f"Run {total_events} events; {K} event(s) missed the patient phantom: {format_event_indices(missed_event_indices)}."` The `0 < K < N` predicate excludes the trivial K == 0 case and the all-miss case (handled by the sentinel).
4. **All-miss sentinel (always-on)** — if `total_events > 0 and len(missed_event_indices) == total_events`, emit `"All {total_events} events missed the patient phantom — dose map is all zeros; check patient offsets and vendor coordinate frame."` The `total_events > 0` guard prevents the sentinel from firing on a degenerate empty dataset. **Not gated on `settings`** — must fire even if the caller didn't pass settings, because an all-miss run is always a bug.
5. **Export** — `output["missed_event_indices"] = missed_event_indices` so the GUI / export can show the count without re-parsing logs. Indices are 0-based (Python convention); consumers converting to user-facing labels should add 1.

### 4.2.1 Threading `settings` and `exam_id` through `calculate_dose`

`calculate_dose` (`calculate_dose/calculate_dose.py:117-131`) is the actual orchestrator. Without forwarding, every warning is suppressed. Add `exam_id: str | None = None` to its signature (after `pad`), then in the `calculate_irradiation_event_result(...)` call, pass `settings=settings, exam_id=exam_id`. Both callers in `analyze_data.py` forward the exam id:

- `analyze_data` → `calculate_dose(..., exam_id=None)` (single-exam, by design).
- `analyze_multiple_exams` → `calculate_dose(..., exam_id=exam.study_id or exam.provenance.original_filename)`. Mirrors the existing `ExamResult.exam_id` field at `format_export_data.py:477`.

### 4.3 Multi-exam path

In `analyze_multiple_exams` (`analyze_data.py:174`), **do not call `logger.warning`** for the same condition as `calculate_irradiation_event_result` — that would double-fire on the GUI's collector. The orchestrator's job is limited to:

- After each `calculate_dose(...)` call, if `raw_output["missed_event_indices"]` is non-empty, **build a string in memory** of the form `f"Exam {i} ({exam.study_id or exam.provenance.original_filename}): {len(missed)} of {len(data_norm)} event(s) missed the patient phantom."` and `.append(...)` it to `exam_warnings` (the existing per-exam warnings bag, surfaced in `ExamResult.warnings` and the Results-tab accordion). `data_norm` is the local variable holding the post-`calculate_rotation_matrices` DataFrame for the current exam (existing at `analyze_data.py:162`).
- If `len(missed) == len(data_norm) > 0`, also append a per-exam all-miss string: `f"Exam {i} ({id}): all {len(data_norm)} event(s) missed the patient phantom — dose map for this exam is all zeros; check patient offsets and vendor coordinate frame."` The "all N events missed" phrase mirrors the §4.2 step 4 sentinel so the toast and the per-exam accordion recognisably describe the same condition.

The actual `logger.warning(...)` calls happen inside `calculate_irradiation_event_result`, which the multi-exam override runs with `beam_miss_warn="summary"` (next section) — the collector sees each message exactly once.

### 4.4 Dial behaviour

- `"per_event"` (default) — one `logger.warning` per missed event; no per-run summary; the all-miss sentinel still fires.
- `"summary"` — no per-event warnings; one `logger.warning` at the end of `calculate_irradiation_event_result` (so per-exam in multi-exam); the all-miss sentinel still fires.
- `"off"` — no per-event warnings and no summary; the all-miss sentinel still fires.

**Multi-exam override** — `analyze_multiple_exams` deepcopies settings per exam (the existing `analyze_data.py:152-159` pattern). The existing deepcopy is conditional on `effective_offset != global_offset`; we widen it to also fire when the dial is `"per_event"` so the per-exam `beam_miss_warn = "summary"` override does not mutate the caller's settings object. Emit the downgrade notice **once before the loop** (not per-exam):

```python
_downgraded = False
if settings.beam_miss_warn == "per_event":
    logger.info(
        "beam_miss_warn downgraded from 'per_event' to 'summary' for multi-exam run."
    )
    _downgraded = True
```

Then inside the per-exam loop:

```python
if effective_offset != global_offset or _downgraded:
    exam_settings = copy.deepcopy(settings)
    if effective_offset != global_offset:
        exam_settings.phantom.patient_offset.d_lon = effective_offset[0]
        exam_settings.phantom.patient_offset.d_ver = effective_offset[1]
        exam_settings.phantom.patient_offset.d_lat = effective_offset[2]
    if _downgraded:
        exam_settings.beam_miss_warn = "summary"
else:
    exam_settings = settings
```

The `logger.info(...)` fires once so a CLI user with `tail -F` on stderr sees the change without per-exam spam. Single-exam runs honour the dial verbatim.

### 4.5 GUI

No new tab. Reuse `state.calc_warnings` and the existing toast flow (`gui/tabs/calculate.py:233-238`).

#### 4.5.1 Settings widget

Add a select dropdown to the Physics Settings expansion in `gui/tabs/settings.py` (alongside the existing `below_floor_kvp_policy` select at line 193). Define the options dict near the existing `BELOW_FLOOR_KVP_OPTIONS` (line 33):

```python
BEAM_MISS_WARN_OPTIONS = {
    "per_event": "Per event (one warning per missed event)",
    "summary": "Summary (one warning per run)",
    "off": "Off (only all-miss sentinel)",
}
```

Insert the select after the `manual_kvp` block (after line 210):

```python
ui.select(
    BEAM_MISS_WARN_OPTIONS,
    label="Beam-miss warning verbosity",
    value=state.beam_miss_warn,
).bind_value(state, "beam_miss_warn").on(
    "update:model-value", reset_results
).classes("w-full")
```

This widget does **not** need a timer or conditional visibility (unlike `manual_kvp`); it is always shown.

#### 4.5.2 Toast throttling

The current loop fires 800 toasts on a 1000-event run with 800 misses, which can lag or crash the NiceGUI browser. HVL / grid-interp warnings don't suffer this because they aggregate to 1–2 messages per run (`geom_calc.py:303-342`), so the comparison is apples-to-oranges. Replace the `for warning in state.calc_warnings: ui.notify(...)` loop at `gui/tabs/calculate.py:237-238` with a bounded form.

Add a module-level constant near the top of `gui/tabs/calculate.py` (after imports):

```python
_MAX_TOASTS: int = 5
```

Replace the existing loop:

```python
for i, warning in enumerate(state.calc_warnings):
    if i < _MAX_TOASTS:
        ui.notify(warning, type="warning", timeout=12000, multi_line=True)
    else:
        ui.notify(
            f"... and {len(state.calc_warnings) - _MAX_TOASTS} more warnings. "
            f"See Results tab for the full list.",
            type="warning",
            timeout=12000,
        )
        break
```

The `break` runs only on the first iteration past the cap, so exactly one "and N more" toast is emitted; when `len == _MAX_TOASTS`, the loop ends at `i == _MAX_TOASTS - 1` and no "and 0 more" is fired. The full list is still on `state.calc_warnings` and in the Results-tab accordion — the throttle is presentation-only.

#### 4.5.3 Trade-off

The cap is a flat slice of the warnings list as-ordered by the collector. A user who opts into `"per_event"` and produces many beam-miss warnings plus a critical HVL / clamped warning could see the HVL warning under "... and N more". This is acceptable because (a) the GUI default is `"summary"` so the flood is rare; (b) the full list remains in the Results tab; (c) prioritising non-beam warnings is a Phase 3+ polish, not a Phase 1 requirement. See §5.

#### 4.5.4 Status label

Enhance the existing `calc_status_label` (`gui/tabs/calculate.py:234-240`) to show a beam-miss count. Instead of fragile substring-matching on warning messages, read `missed_event_indices` directly from the calculation output (already stored per §4.2 step 5):

- **Single-exam:** `K = len(state.output.get("missed_event_indices", []))` if `state.output` is not `None`, else 0.
- **Multi-exam:** `K = sum(len(e.output.get("missed_event_indices", [])) for e in state.multi_exam_result.exams)` if `state.multi_exam_result` is not `None`, else 0.

When `K > 0`, append `· {K} beam-miss event(s)` to the status text. This approach is independent of the `beam_miss_warn` dial setting and the warning message wording — it reads the authoritative data. No new control needed.

### 4.6 CLI

No new code — `logger.warning` rides `main.py`'s existing stderr handler. Add one line to the CLI `--help` text noting that beam-miss warnings are emitted at WARNING level (and that the multi-exam override downgrades to `summary` with an INFO log).

## 5. Risks & non-goals

- **Non-goal: auto-correcting the offset.** A beam miss is almost always a real user / coord-frame problem, not something to silently compensate. The plan only warns.
- **Non-goal: distinguishing "legitimately aimed at table" from "missed patient".** The user interprets the warning in context (cardiac, head, QA). A "QA mode" or per-event flag is out of scope.
- **Non-goal: ray-trace visualisation of the missed beam.** Redundant with the Geometry tab's per-event plot. Could be a follow-on overlay.
- **Risk: toast spam.** Mitigated by the §4.5 GUI throttle (5 + summary), the `"summary"` dial, and the GUI's `"summary"` default. The collector itself is cheap; the cost is in `ui.notify`.
- **Risk: regression on golden baselines.** The four bundled example RDSRs all hit by construction; the default dial is `"per_event"`, so a new beam-miss warning in a golden test signals a fixture or setup regression, not a real failure. Tests should fail loudly, not be silenced.
- **Risk: toast-throttle hiding important non-beam warnings.** See §4.5 "Trade-off".
- **Risk: silent dial downgrade in CLI multi-exam.** Mitigated by the §4.4 `logger.info(...)` line.

## 6. Open questions

All resolved. Key resolutions:

- Settings plumbing: explicit `settings: PyskindoseSettings | None = None` kwarg on `calculate_irradiation_event_result`, threaded through `calculate_dose` (§4.2.1).
- Sentinel severity: `WARNING`, not `ERROR`, for the first cut.
- Status-label wording: append `· {K} beam-miss event(s)`, sourced from `output["missed_event_indices"]` directly (not substring-matching on warning text).
- Settings field name: `beam_miss_warn` (matches `below_floor_kvp_policy` short-name style).
- Multi-exam per-event: forced to `"summary"` per-exam; CLI sees an `INFO` log once (before the loop, not per-exam) on downgrade (§4.4).
- `.iloc` indexing: positional (defensive); pipeline already relies on `rdsr_normalizer`'s guaranteed 0..N−1 `RangeIndex` for existing `[ev]` accesses (§3 item 2 / §4.2 step 2).
- Multi-exam settings mutation: widened deepcopy condition + `logger.info` on downgrade (§4.4).
- Toast throttle constant: 5, defer tuning to first-cut review.
- Summary truncation: reuse `format_event_indices` from `guiskindose.grid_interp` (§4.2 step 3).

## 7. Phasing

- **Phase 0 (prerequisite bug fix):** close the `_CalcWarningCollector` handler leak in `gui/helpers.py:144-202`. The multi-exam branch (`gui/helpers.py:148-190`) never calls `removeHandler`, so each calculate-or-recalculate cycle appends a new handler to `_calc_logger` (the single-exam branch correctly does in its `finally`). Fix: wrap both branches in a `try/finally` block. The existing `_calc_logger.addHandler(_collector)` at line 147 (already before the `if`) stays put; the existing single-exam `try/finally` at lines 191/200 is widened to span the entire if/else, with `finally: _calc_logger.removeHandler(_collector)` at the very end. The `state.calc_warnings = list(_collector.messages)` assignments (lines 188 and 202) stay inside their respective branches. This must ship first — the new beam-miss emissions will amplify the leak's user-visible impact (duplicate × N toasts per leak cycle).
- **Phase 1 (MVP):** core `logger.warning` per missed event in `calculate_irradiation_event_result`, single-exam only, dial hard-coded to `"per_event"`. Appended tests in `tests/unittests/test_calculate_dose.py`. ~30 lines + test cases.
- **Phase 2:** `PyskindoseSettings.beam_miss_warn` field, GUI Settings select, all-miss sentinel, multi-exam per-exam summary + override, `build_settings` mapping, `AppState` field. ~80 lines + the GUI select.
- **Phase 3 (polish):** GUI status-label summary, CLI `--help` note, `FEATURE_INVENTORY.md` one-liner.

Phases 1 and 2 are likely to land together; Phase 3 is doc / GUI polish that can ride any release.

## 8. Validation commands

- `ruff check src/guiskindose/calculate_dose tests/unittests src/guiskindose/settings`
- `basedpyright src/guiskindose/calculate_dose/calculate_irradiation_event_result.py src/guiskindose/calculate_dose/calculate_dose.py src/guiskindose/calculate_dose/perform_calculations_for_new_geometries.py`
- `pytest tests/unittests/test_calculate_dose.py -q`
- `pytest tests/unittests/test_calculate_dose.py::test_calculate_dose_golden_baseline_siemens_cylinder -q`
- `python scripts/check_doc_freshness.py` — confirms the `FEATURE_INVENTORY.md` and `TO_DO.md` link are not stale.
- `python scripts/check_file_sizes.py` — confirms appended test cases stay under the 800-line module limit.
