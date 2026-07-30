# Assessment: `dev-docs/plans/archive/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md`

> **Historical (2026-07-30):** Parts I–V of the plan shipped and the plan is archived. This Round 7
> assessment remains for traceability of the mid-implementation review; do not treat “NOT shipped”
> findings below as current backlog. Manual multi-exam GUI smoke is still tracked in `TO_DO.md`.

**Date:** 2026-06-24 16:21
**Scope:** Gap and clarity review of the in-progress multi-exam geometry offsets
plan, with emphasis on remaining phases (Part IV, V, VI) and unresolved appendix
items. The plan claims Parts I, II, and III are "shipped" — this assessment
verifies that claim against the current source tree and surfaces the
remaining work, ambiguities, and missing test coverage.

---

## 1. Executive summary

| Area | Status | Notes |
|------|--------|-------|
| Part I — module split / B1–B4 | **Shipped** | `helpers.py` 247 lines, `state.py:118` line removed, loader meta seeding works. |
| Part II — preview helpers + C1 banner + exam selector | **Shipped** | `geometry_preview.py`, `EXAM_INDEX_COLUMN`, `make_geometry_fig` kwargs wired through `run.io_bound` in all three call sites. |
| Part III — multi-exam table-origin sliders | **Shipped** | `exam_supports_table_origin` in `exam_transforms.py`, `_sync_table_sliders_from_meta` updates limits + values, table-origin card visibility via two `bind_visibility_from` predicates. |
| **Part IV — multi-exam patient-offset sliders** | **NOT shipped** | The plan's checklist marks it TODO, but the file still hides the patient card in multi-exam and the sliders still `bind_value(state, attr)`. |
| **Part V — cross-cutting formatters + docs** | **NOT shipped** | The string in `calculate.py:78` is the old one; `_format_patient_offsets` ignores `is_multi_exam`; `_format_table_offset_line` ignores it; `preview_caption` does not exist; docs not updated. |
| Part VI — cross-tab sync plumbing | "DONE" for plumbing; VI-A/B/C still deferred (intentional) | OK as written. |
| Appendix A status table | **Inconsistent with code** | Many items marked DONE are partly or wholly NOT DONE. |
| Appendix B tests | **Not added** | None of the four listed new unit tests exist in `tests/unittests/`. |

**The single biggest issue:** the plan is presented as "in-progress" but Parts
I–III check off as ✅ while Parts IV/V — the user-facing payoff — are still
fully open. The checklist on line 244 marks `composite_checkbox (R1)` as a
Part IV deliverable, but no Part IV code change exists. The "Status: Done"
banner on the plan overall is misleading.

---

## 2. Part IV is the unstated critical path

Plan line 11: "Goal: ... show Geometry offset sliders bound to
`loaded_exam_meta[active]`". The user-visible value of the plan lives in
Part IV, not III. The plan body (lines 190–203) lays out the work, but
none of it is in the source tree.

### 2.1 What is still on the table

1. **Patient offset card visibility** — `src/mypyskindose/gui/tabs/geometry.py:107`:
   ```python
   patient_offset_card.bind_visibility_from(state, "is_multi_exam", backward=lambda v: not v)
   ```
   This hides the card in multi-exam. The plan §Goal (line 14) says multi-exam
   should show the card, with sliders bound to `meta[active].d_*` only. Fix
   requires either showing the card in both modes and routing slider writes
   conditionally, or building a parallel multi-exam card.

2. **`bind_value` leaks globals (T4)** — lines 141 and 143–145:
   ```python
   slider.bind_value(state, attr)
   val_label.bind_text_from(state, attr, backward=lambda v, a=attr: f"{getattr(state, a):.1f} cm")
   ```
   In multi-exam these must read/write `meta[active][attr]`, not globals. The
   plan (line 195) explicitly says "no `bind_value` / `bind_text_from` on globals"
   but they are still there.

3. **`val_labels` does not exist** — Plan §0.3 stub on lines 159–168 names
   `val_labels: dict[str, ui.label]` updated on tick and on sync. The current
   code (lines 142–145) inlines the label and binds it to the global. The dict
   refactor is required by T31 (line 298) and is still TODO in the appendix.

4. **`composite_preview` checkbox UI gap (T29 PARTIAL)** — Plan line 198
   says: "Closure var exists from Part II; **UI connection still absent**." The
   appendix (line 296) marks this PARTIAL. The code has the closure var
   (line 66) and the reset on multi→single (lines 502–505), but no
   `ui.checkbox` for the user to flip it.

5. **`preview_caption` label does not exist (R1)** — Plan line 199:
   "dynamic label below toggle; updates when `composite_preview`,
   `last_table_origin_scrub`, or `active_exam_index` changes". Grep confirms
   no `preview_caption` symbol in `src/mypyskindose/gui/`. The user-facing
   C3 captions (Appendix B lines 310–311) have no anchor in the UI.

6. **`_reset_patient_offset` for multi-exam (R3, T5)** — Plan lines 201, 186:
   zero `meta[active].d_*` in multi. Current code (lines 399–405) always
   zeroes globals and never touches meta. Will break the single→multi
   restore path.

7. **Part IV tests** — Plan line 320 names
   "patient slider write-back to `meta[active]`; globals unchanged in
   multi-exam (T4, T31)" as a Part IV test addition. No such test exists
   in `tests/unittests/test_gui_multi_exam_geometry_offsets.py`.

### 2.2 Concrete proposed surface for Part IV

The plan says "Use `patient_guard`; `val_labels: dict[str, ui.label]` updated
in tick and `_sync_patient_sliders_from_meta` from `meta[active].d_*`". A
refactor pattern that keeps both modes working without forking the slider
construction:

```python
# In multi-exam tick:
def _on_patient_slider_change(attr, slider):
    if patient_guard["suppress"]:
        return
    if state.is_multi_exam:
        idx = state.active_exam_index or 0
        m = state.loaded_exam_meta[idx]
        m[attr] = float(slider.value or 0.0)
    else:
        setattr(state, attr, float(slider.value or 0.0))
        sync_global_patient_offset_to_single_exam_meta(state)
    val_labels[attr].set_text(f"{getattr_value(attr):.1f} cm")
    offset_changed_since_calc = True
    last_table_origin_scrub = False
    _update_stale_caption()
    _schedule_debounced_render()
```

This also requires removing `bind_value`/`bind_text_from` and using
`slider.set_value(...)` during sync (with `patient_guard["suppress"] = True`),
matching the table-origin pattern at lines 220–227.

### 2.3 Recommend splitting Part IV into 4a and 4b

- **IV-a (smaller, shippable):** patient slider write-back to `meta[active]`
  in multi-exam; remove `bind_value`; add `val_labels` dict; patient
  slider sync on exam switch. ~80 LoC + tests.
- **IV-b (cosmetic + UX):** `composite_preview` checkbox + C3/C4
  `preview_caption`; `make_geometry_fig` event re-clamp when slice shrinks
  (N4 cross-cutting); visual polish.

Splitting clarifies scope for reviewers and unblocks the math-correctness
work (IV-a) from the UX polish (IV-b).

---

## 3. Part V is more than string swaps

The Part V table (lines 208–216) reads as a list of "fix this string" and
"hide this widget" items, but several are real behavior changes that need
specification:

### 3.1 `_format_patient_offsets()` (line 19)

Current:
```python
def _format_patient_offsets() -> str:
    return f"X: {state.d_lon:.1f}, Y: {state.d_ver:.1f}, Z: {state.d_lat:.1f} cm"
```

Plan (line 210) says: "When `is_multi_exam`: multi-line per-exam summary,
e.g. `Exam #1: X=…, Y=…, Z=… cm` per loaded exam; truncate after 3 with
`'and N more'`."

**Gaps in this spec:**

- The X/Y/Z axis labels in this format are confusing. The other patient
  offset formatters use `lon/ver/lat` (e.g. the slider rows in
  `settings.py:140–149` and `geometry.py:128–131`). Pick one
  vocabulary: `lon/ver/lat` for clinical convention, or `X/Y/Z` for
  the coordinate axes. Mixing is worse than either.

- The "truncate after 3" is fine, but the suffix format is not specified.
  Should it be `"Exam #1: …, Exam #2: …, Exam #3: …, and 2 more"`, or
  one per line in the multi-line case? For a label, one line reads better.
  For a tooltip / `ui.tooltip`, multi-line. The plan does not say which
  widget hosts this label.

- The function is currently only called from `calculate.py:129` and
  bound to `state.d_lon/d_ver/d_lat` so it refreshes when the global
  changes. For multi-exam, the trigger must be the per-exam meta, not
  the global. **Add a new `bind_text_from` predicate over
  `loaded_exam_meta`** (or a method on `state` that emits when meta
  changes), and remove the global binds to avoid double-render.

- Test name `test_format_patient_offsets_multi_exam` is fine, but it
  needs to cover: 1 exam (still shows single), 2 exams (two lines), 4+
  exams (truncation), and empty `loaded_exams` (no crash, returns "" or
  "—").

### 3.2 `_format_table_offset_line()` in `settings.py:40`

Plan (line 211): "When `is_multi_exam`: `'Per-exam: see Per-exam corrections below.'` —
global `table_offset_*` reflects last load only (R6, T10)."

**Gap:** the function lives in `tabs/settings.py`, but the Calculate
tab imports it via `from .settings import BELOW_FLOOR_KVP_OPTIONS, _format_table_offset_line`.
A new branch needs to be visible to both call sites. Plan should explicitly
state: the branch lives in `tabs/settings.py._format_table_offset_line`
and `tabs/calculate.py` keeps importing the same symbol. (The current
code already does this; just verify after the change.)

**Additional issue:** in the current code (lines 86–91), the
`table_offset_label` binds to four state fields but never to
`loaded_exam_meta` or `is_multi_exam`. After Part V, the multi-exam
caption `"Per-exam: see Per-exam corrections below."` will appear, but
it will not refresh if the user toggles the file load. The plan should
call out a `bind_text_from(state, "is_multi_exam", ...)` predicate.

### 3.3 `settings.py` Phantom offsets hidden when multi-exam (line 213)

Plan: "Hide global spinboxes when multi-exam; caption C6."

**Specification gaps:**

- The global spinboxes (lines 141–149) are wrapped in
  `ui.row().classes("w-full gap-4")`. Hide the row, not each spinbox
  individually. Use `bind_visibility_from(state, "is_multi_exam",
  backward=lambda v: not v)`.

- The `offset_range_hint` (line 124) and the `_update_offset_range_hint`
  function (line 126) become dead code in multi-exam — they read
  `state.d_lon/ver/lat`, which are 0/0/0 after `restore_globals_from_exam_meta`.
  Either hide them too or document that the hint is single-exam only.

- C6 caption (Appendix B line 315): "Patient offsets are managed
  per-exam in multi-exam mode. Adjust them in the Geometry tab or
  Per-exam corrections section below." Where is this caption placed?
  Inside the "Phantom Settings" expansion? Above the (now hidden) row?
  Be explicit.

### 3.4 `calculate.py:78` string

Plan (line 210): replace
`"Per-exam patient offsets editable in Upload tab"` with
`"…in Geometry and Settings tabs"`.

**One-line fix, but check:** the row already has
`bind_visibility_from(state, "is_multi_exam")` so the row only shows
in multi-exam. The new copy is correct only if both tabs really do
edit the same per-exam data — which they do (per `_per_exam.py` and
the Part IV scope described in the plan). Make this an explicit acceptance criterion.

### 3.5 Settings → Geometry cross-tab invalidation (N4)

Plan line 215: "When `apply_exam_transforms` fires from Settings
(`_per_exam.py`), `rebuild_rdsr_df` replaces `state.rdsr_df`; if
Geometry tab is active, re-clamp event index and call
`_refresh_geometry_sliders` (or schedule debounced re-render) so preview
slice stays valid."

**This is not just a doc note — it is a real behavior gap.** When the
user toggles `swap_lat_lon` or `flip_tx` in the per-exam card,
`rebuild_rdsr_df` runs and the Geometry tab's `geom_event_input.value`
(event index) is unchanged but the slice may have a different length.
The fix is small: have `_on_exam_transform_change` in `_per_exam.py`
also call `ctx.refresh_per_exam()` and have the geometry tab's
`_refresh_geometry_sliders` clamp the event input. But the plan does
not say which file owns the clamp.

### 3.6 `data.py` export (Out of scope line 233)

The plan defers "export `table_origin_override` in `data.py`". This
is a real omission: the user can edit `table_origin_override` in
Settings → Per-exam corrections, run a calculation, and export the
normalized data — and there is no record of the override in the export
metadata. Recommend a follow-up TO_DO entry; it is not a Part V
blocker but the audit trail is broken today.

### 3.7 Docs list (line 216)

The plan names seven docs that need updating. Two are missing from the
list but should be on it:

- `dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md` is named, good.
- **`dev-docs/VENDOR_COORDINATE_SYSTEMS.md`** (referenced in the
  harness map) — does not need a multi-exam section but should be
  cross-checked for any wording that contradicts "one patient offset
  per exam" semantics.
- **`dev-docs/MYPYSKINDOSE_MIGRATION_STATUS.md`** — the PySkinDose
  fork has a single global patient offset; the migration doc should
  note the new per-exam semantics so the fork-vs-upstream comparison
  stays accurate.
- **`docs/source/gui_help/positioning_offsets.md`** is named, but
  the plan does not call out the `sync_gui_help.py` step explicitly.
  The harness doc says "canonical source is `docs/source/gui_help/`,
  mirrored by `scripts/sync_gui_help.py`". The plan should say
  "edit `docs/source/gui_help/positioning_offsets.md`, then
  `python scripts/sync_gui_help.py`". Currently the plan only says
  "docs/source/gui_help/positioning_offsets.md (+ sync_gui_help.py)"
  which is ambiguous about which side to edit.

---

## 4. Appendix A status table diverges from the code

The appendix is a useful implementation index, but several rows are
inaccurate or no longer relevant:

| Row | Plan status | Actual | Comment |
|-----|-------------|--------|---------|
| T2 (DONE) | "Remove `state.py:118` line" | Confirmed; line is gone in `state.py` | OK |
| T4 (TODO) | "`bind_value` leaks globals" | Still present in `geometry.py:141` and `bind_text_from` in 143–145 | Accurate — still TODO |
| T5 (DONE) | "`_reset_*` hardcoded to `meta[0]`" | `_reset_table_origin` now uses active index (line 411); `_reset_patient_offset` still uses globals (line 400) | **Partial — T5 covers table-origin but not patient; appendix should say PARTIAL or split into T5a/T5b** |
| T6 (DONE) | "Optional kwargs through `run.io_bound`" | Confirmed in `figures.py:20–26` and `geometry.py:375–381` | OK |
| T7 (DONE) | "Event index out of range" | `geometry.py:373–374` clamps; `figures.py:45` clamps | OK |
| T8 (DONE) | "PAUSED/spinner use full `event_count()`" | `live_preview_allowed` (line 320) uses `preview_event_count(..., composite=True) > 30` only when `is_multi_exam and composite`; spinner at 364 | OK |
| T9 (DONE) | "Selector programmatic update re-fires" | `exam_selector_guard` at line 69, 481, 473 | OK |
| T10 (TODO) | "Stale Calculate/Settings summaries" | `calculate.py:19` and `settings.py:40` unchanged | Accurate — still TODO |
| T11 (DONE) | "Preview frame includes tag columns" | `geometry_preview.py:83` drops `EXAM_INDEX_COLUMN` and `EXAM_COLUMN` | OK |
| T14 (DONE) | "Worker reads mutable `active_exam_index`" | `run.io_bound(make_geometry_fig, ..., active_exam_index=active_idx, ...)` passes the value | OK |
| T15 (DONE) | "Exam switch while `table_origin_pending`" | `_on_exam_select_change` (line 487) commits `old_index` | OK |
| T16 (DONE) | "Preview buttons stale composite flag" | `_render_preview` line 361 calls `_resolve_composite_for_render()` | OK |
| T17 (TODO) | "`set_value` before limit update" | `_sync_table_sliders_from_meta` (line 220) sets limit, calls `update()`, then `set_value` | **Marked TODO in appendix but the code is correct — should be DONE** |
| T19 (DONE) | "Sync helpers IndexError" | Both sync helpers (line 206, 233) guard `idx >= len(state.loaded_exam_meta)` | OK |
| T20 (DONE) | "Loader zeros globals before meta" | `prev_d_*` capture lives in `exam_loaders.py` per Part I | OK |
| T21 (DONE) | "`helpers.py` >800 lines" | Now 247 lines | OK |
| T22 (DONE) | "`EXAM_COLUMN` circular import" | `exam_transforms.py` owns it; `geometry_preview.py:7` imports it; no cycle | OK |
| T23 (DONE) | "Multi→single loses offsets / stale index" | `_remove_exam` line 398 calls `restore_globals_from_exam_meta` | OK |
| T24 (DONE) | "Import cycles" | Verified — `helpers` is a thin facade; `exam_loaders` and `offset_handlers` do not import `helpers` | OK |
| T25 (DONE) | "Settings spinboxes don't refresh Geometry" | `_per_exam.py:58` calls `ctx.refresh_per_exam()` | OK |
| T26 (DONE) | "Composite untested" | `test_rdsr_df_for_geometry_preview_slices_by_exam_index` (line 71 of test file) covers composite | OK |
| T27 (DONE) | "Wrong count for PAUSED" | Line 326 uses composite count | OK |
| T28 (DONE) | "`composite_preview` sticks after multi→single" | Lines 502–505 reset it | OK |
| T29 (PARTIAL) | "Toggle change after slider tick" | Closure var shipped, no checkbox UI | **Honest PARTIAL — keep** |
| T30 (DONE) | "`EXAM_COLUMN` prefix slice fragile" | `EXAM_INDEX_COLUMN` is int; `geometry_preview.py:80` slices by int | OK |
| T31 (TODO) | "Patient val_labels read globals" | `val_labels` dict does not exist; `bind_text_from` on globals | **Accurate — still TODO** |

**Action items for the appendix:**

1. Re-classify T17 as DONE.
2. Re-classify T5 as PARTIAL (table-origin done, patient not).
3. Consider splitting T4 into T4a (patient `bind_value`/`bind_text_from`)
   and T4b (per-axis event-sink path in multi-exam).
4. T29 is honest; once the Part IV checkbox lands, promote to DONE.

---

## 5. Appendix B tests are all missing

The plan names these tests as exit gates (lines 320–323), and the
"Manual matrix" (lines 327–346) and "Checklist" (line 244) both reference
them. None exist:

| Test name | Plan line | Status | Notes |
|-----------|-----------|--------|-------|
| `test_format_patient_offsets_multi_exam` | 322 | **Missing** | Pure-Python test on `_format_patient_offsets` from `tabs/calculate.py`. |
| `test_format_table_offset_line_multi_exam` | 322 | **Missing** | Same shape, on `_format_table_offset_line` from `tabs/settings.py`. |
| `test_per_exam_offset_change_calls_refresh_per_exam` | 322 | **Missing** | Mock `ctx`, simulate `_on_exam_offset_change`, assert `refresh_per_exam` was called. |
| `test_remove_exam_invokes_refresh_per_exam` | 322 | **Missing** | Mock `ctx`, call `_remove_exam`, assert chain ran. |
| Part IV patient write-back test | 320 | **Missing** | Move patient sliders in multi-exam, assert `meta[active].d_*` updated and globals unchanged. |
| Part IV globals-unchanged test | 320 | **Missing** | Same setup as above; assert `state.d_lon/d_ver/d_lat` unchanged. |
| `test_clamp_active_exam_index_after_exam_switch` (implied) | — | **Missing** | The `live_preview_allowed`/`_render_preview` event-index clamp needs a regression test. |
| `test_composite_preview_toggle_pauses_when_large` | 0d, 0l | **Missing** | Threshold logic at 30/100 with composite mode. |
| `test_composite_preview_reset_on_multi_to_single` | 0m | **Missing** | T28. |
| `test_preview_caption_shows_correct_text_per_mode` | 2a | **Missing** | Caption strings C3/C4 (lines 310–313). |
| `test_make_geometry_fig_clamps_event_index_in_multi_exam` | 0a, T7 | **Missing** | `figures.py:45` clamp. |
| `test_settings_per_exam_spinbox_does_not_touch_globals` | Part IV | **Missing** | Sanity: the Settings card's per-exam spinbox writes `meta[i]`, not globals. |

**Test placement:** all of the pure-state tests above can go in
`test_gui_multi_exam_geometry_offsets.py`. The
`ctx.refresh_per_exam` mock tests need a `pytest-mock` or
`unittest.mock.MagicMock` on `PageContext`. The figure tests need a
fixture that builds a minimal `state` with two exam `normalized_data`
frames and a `Phantom` stub.

**Manual matrix** is also open: the plan labels several manual steps
"fails until T3" / "needs Part IV checkbox" — these will not pass
until the corresponding code lands, so the manual matrix should be
re-run as part of Part V exit, not Part III.

---

## 6. Naming and consistency

Minor wording nits that will help readers:

- **"Closure vars"** is used twice (lines 29, 195) without defining what
  closure. Add a one-line explanation in §Preview semantics, or refer
  the reader to a `state` field. (In fact `composite_preview` and
  `last_table_origin_scrub` are local closure variables inside
  `geometry.build`, but `was_multi_exam` is the only one that
  actually needs to track previous state — calling the others
  "closure vars" is correct but jargon-y.)

- **"Editing exam"** selector label (line 99) vs **"selected exam"** in
  copy (line 308, C1). Pick one; C1 says "selected exam" and the UI
  says "Editing exam". These are not the same persona. Either is fine
  but they should agree. The C1 banner also says "Sliders edit the
  **selected exam**" while the UI says "Editing exam" — minor but
  jarring.

- **"scrub"** in `last_table_origin_scrub` and `on_value_change` is
  used to mean "user is actively dragging". The
  `on_global_patient_offset_scrub` helper (`offset_handlers.py:42`)
  has the same word but does not actually check whether the user is
  dragging — it just mirrors globals to single-exam meta on every
  call. If "scrub" is the codebase's term for "tick path", say so in
  `offset_handlers.py`'s module docstring.

- **"composite"** has two meanings in Part V: (a) the multi-exam
  preview that combines all exams' events, and (b) the multi-exam
  dose map that sums skin doses across exams. The plan only means (a),
  but `_format_patient_offsets` and `_format_table_offset_line` show
  per-exam values, which is closer to (b). When writing captions, use
  "all exams" or "per-exam" to avoid confusion with the dose-map
  meaning.

---

## 7. Underspecified edge cases

### 7.1 Removing the only exam

Plan line 115 says "Preserve chain: `_remove_exam` → `_refresh_exams_table` →
`ctx.refresh_per_exam` → `_refresh_geometry_sliders` (table + patient sync)."

But the geometry tab's `was_multi_exam` reset (lines 502–505) only runs in
`_refresh_geometry_sliders`. When `n=0`, `_table_origin_card_visible`
returns False, but the patient offset card still has its own
`bind_visibility_from(state, "is_multi_exam", backward=lambda v: not v)`.
After Part IV, the card needs the same 0-exam branch.

**Suggested handling:** introduce a small helper `_is_single_or_no_exam()`
that returns `not state.is_multi_exam or not state.loaded_exams` and use
it in both card visibility predicates.

### 7.2 Switching from 1→2 exams via load

`on_exams_loaded` (`geometry_preview.py:42–48`) sets `active_exam_index=0`
on a single-exam load and calls `clamp_active_exam_index` otherwise.
After Part IV, when the user loads a second file:

- Patient sliders must refresh from the now-active exam's `meta[0].d_*`.
- `last_table_origin_scrub` resets (line 492 already handles this).
- The new exam inherits the global `d_*` if no `d_*` in its meta
  (B1 loader fix in `exam_loaders.py`). **Verify the loader actually
  copies `state.d_lon/ver/lat` to the new exam's meta on `load_tabular`
  with `replace_existing=False`.** If not, the user is surprised: the
  global offset is the value of the previous exam, but the new exam
  starts at 0.

### 7.3 `was_multi_exam` does not catch all transitions

`was_multi_exam` (line 68, 502–506) only resets `composite_preview` and
`last_table_origin_scrub` on **multi→single**. It does not handle
**single→multi**, which is fine because the initial values are
`False`, but it also does not handle the **2→3** transition (no
state change, just a new exam appended). The exam selector handler
(line 479) handles the new-exam case. OK as-is, but the
`_refresh_geometry_sliders` function (line 501) is the *only* place
that knows about `was_multi_exam` and it is called from
`ctx.refresh_per_exam`. If a future refactor adds a new code path
that changes `is_multi_exam` without going through `refresh_per_exam`,
the `was_multi_exam` state will desync. Worth a one-line comment
naming `refresh_per_exam` as the canonical entry point.

### 7.4 C3 caption "phantom position is exam #{n} only"

Plan line 311: "**Preview: all exams' events; phantom position is exam
#{n} only — other exams use their own offsets at Calculate.**"

This is correct but it raises a UX question: when the user enables
"Show all exams in preview", should the patient phantom render once at
`meta[active]` (current intent) or be hidden entirely (some users may
expect no phantom so they can see all beams unblocked)? The plan does
not address this. The default in `effective_patient_offset_for_preview`
is the active exam's offset (line 51–64 of `geometry_preview.py`),
which is the "render phantom once" choice. **Document this decision in
the part-V acceptance criteria so the next reader does not
"fix" it.**

### 7.5 `make_geometry_fig` and `active_exam_index=None` in single-exam

The function signature allows `active_exam_index=None` (default).
`rdsr_df_for_geometry_preview` returns the full frame in single-exam
mode (line 78 of `geometry_preview.py` checks `state.is_multi_exam`).
`effective_patient_offset_for_preview` returns globals (line 64).
CLI calls (N1, plan line 150) do not pass either kwarg. OK, but
verify with `grep -n "make_geometry_fig(" src/` that **no production
caller** passes `composite=True` accidentally outside the GUI.

---

## 8. Out of scope is fine, but should be in TO_DO

The Out of scope section (lines 231–235) lists:

- offset arrow (deferred to other plan)
- per-exam dose map toggles
- persisting Geometry UI across reload (session-only)
- export `table_origin_override` in `data.py`
- incremental table-origin preview
- per-exam event stepping

None of these are linked in `dev-docs/TO_DO.md`. Recommend
adding the data-export one (it is a real audit-trail gap, see §3.6
above) and the per-exam event stepping (it is the natural follow-up
once Part IV ships).

---

## 9. Recommended order for the remaining work

| # | Item | Why first | Estimate |
|---|------|-----------|----------|
| 1 | Add the four Part V tests (pure functions) | Catch regressions before behavior changes land | S |
| 2 | Add Part IV-a patient slider write-back (T4, T31) | Math correctness, no UX surface | M |
| 3 | Add Part IV-a tests (meta write-back, globals unchanged) | Lock the contract | S |
| 4 | N4 cross-tab re-clamp (plan line 215) | Small, prevents user confusion on per-exam toggle | S |
| 5 | Part V `_format_patient_offsets` / `_format_table_offset_line` / `calculate.py:78` / `settings.py` Phantom hide + C6 | User-visible | M |
| 6 | Part IV-b checkbox + `preview_caption` + C3/C4 | UX polish; depends on IV-a so caption can read from `meta[active].d_*` | M |
| 7 | Manual matrix rerun | Exit gate | S |
| 8 | Docs sweep (plan line 216) | Doc-freshness gate | M |
| 9 | `python scripts/check_doc_freshness.py`, `check_doc_pruning.py`, `check_file_sizes.py` | Exit criteria | S |
| 10 | Archive plan, update `dev-docs/index.md` and `TO_DO.md` | Plan lifecycle rule | S |

After #4, the multi-exam Geometry workflow is mathematically correct and
ships the user's main goal. #6 adds the polish that makes the new
workflow discoverable.

---

## 10. Single-paragraph TL;DR for the maintainer

Parts I–III shipped cleanly. **Part IV is the unstated critical path**
and is mostly un-done: the patient card is still hidden in multi-exam,
sliders still `bind_value` to globals, no `val_labels` dict, no
`composite_preview` checkbox, no `preview_caption`. Part V has four
missing unit tests and a couple of unclear spec details
(axis label vocabulary, caption placement, N4 re-clamp). The
appendix A status table needs T17 promoted to DONE, T5 demoted to
PARTIAL, and T29 promoted to DONE once the Part IV checkbox lands.
Ship IV-a (math) first, then IV-b (polish), then V (formatters + docs).
