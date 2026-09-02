# `MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md` — Gap & Clarity Review (Round 8)

> **Historical (2026-07-30):** Parts I–V of the plan shipped and the plan is archived under
> `dev-docs/plans/archive/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md`. This Round 8 assessment is retained
> for decision history; open findings below were addressed in subsequent commits unless noted in
> `TO_DO.md` (manual multi-exam smoke).

**Date:** 2026-06-24 20:37 UTC
**Scope:** Independent gap/clarity review of the in-progress plan, with
emphasis on the remaining phases (Part V cross-cutting formatters/docs and
the Part VI polish items) and any inconsistencies introduced by the recent
Part IV "ship" status update. Verifies claims against the current source
tree (`HEAD`).

**Plan state being reviewed:** 390-line plan claiming Parts I–IV (IV-a + IV-b)
shipped; Part V (cross-cutting) and Part VI (optional polish) remaining.

**Method:** Read the plan, then grep the codebase to confirm each shipped
claim. Where claims and code disagree, surface the discrepancy. Where the
remaining phases (V/VI) are ambiguous, lay out the ambiguity. Do not edit any
existing files; this assessment lives in `tmp/` per the requested destination.

---

## 1. Executive summary

| Area | Status | Notes |
|------|--------|-------|
| Part I — module split / B1–B4 | **Shipped** | `helpers.py` is 263 lines, all B1–B4 fixes verified in source. |
| Part II — preview helpers + C1 banner + exam selector | **Shipped** | `clamp_active_exam_index`, `rdsr_df_for_geometry_preview`, `EXAM_INDEX_COLUMN`, `make_geometry_fig` kwargs, C1 banner, exam selector all present. |
| Part III — table-origin sliders | **Shipped** | `_sync_table_sliders_from_meta`, `exam_supports_table_origin`, table-origin card visibility predicates all present. |
| Part IV-a — patient slider write-back | **Shipped** | `apply_patient_offset_slider_tick` (offset_handlers.py:61), `patient_val_labels` dict (geometry.py:149), `read_patient_offset_value` (offset_handlers.py:49), per-active meta sync (geometry.py:169) all present. |
| Part IV-b — composite preview UX | **Shipped** | `composite_checkbox` (geometry.py:119), `preview_caption` (geometry.py:123), C3/C4 caption helper (geometry_preview.py:130), toggle handler (geometry.py:541) all present. |
| **Part V — cross-cutting formatters/docs** | **NOT shipped** | `calculate.py:78` still says "Upload tab"; `_format_patient_offsets` (calculate.py:19) still emits `X/Y/Z` globals; `_format_table_offset_line` (settings.py:40) ignores `is_multi_exam`; Phantom row in settings.py is not hidden in multi-exam; help docs still single-exam-centric. |
| **Part VI — cross-tab sync** | Plumbing shipped; A/B/C deferred (intentional) | OK as written. |
| Appendix A status table | **Largely accurate** | One misclassification still present (T5 row conflates table-origin and patient reset; should be split or marked PARTIAL). |
| Appendix B tests | **Substantially complete** | Tests added in `test_gui_multi_exam_geometry_offsets.py` cover the IV-a/b surface; T10 formatters and N4 re-clamp still have no test. |

**Bottom line:** Parts I–IV and IV-b are genuinely shipped. **Part V is the
real remaining work and contains a number of underspecified spec points** —
string-vocabulary, formatter triggers, caption placement, and doc list. The
plan's Part V row in the table is mostly correct, but it skips several
specifics that need to be nailed down before the formatter code lands.

---

## 2. Part V is the entire remaining user-facing payoff

Plan line 5: "**Part V (cross-cutting)**." The plan's own checklist (line
279) and "Out of scope" (line 253) and the 2026-06-24 status line (line 7)
all agree: Part V is what stands between the current state and archiving.
Each Part V row is a real change, not a doc-only edit. Several are
underspecified.

### 2.1 `calculate.py:78` — the string replacement is correct, but the row's predicate is not

Plan line 232: replace
> "Per-exam patient offsets editable in Upload tab"

with
> "Per-exam patient offsets editable in Geometry and Settings tabs"

The string is at `calculate.py:78`. The enclosing row already has
`bind_visibility_from(state, "is_multi_exam")` (calculate.py:74), so the
row only shows in multi-exam. The fix is small, but two follow-ups are not
called out:

1. **Acceptance criterion check:** the plan says "requires IV-a" — which is
   true and shipped. But the user-facing claim is now "Geometry and Settings
   tabs." Verify that Geometry's per-active-edit (in `geometry.py:418`
   `_on_patient_slider_change`) and Settings' per-exam spinbox
   (`_per_exam.py:158`) both write to `state.loaded_exam_meta[idx].d_*` (or
   `state.d_*` for single-exam via `sync_global_patient_offset_to_single_exam_meta`).
   This is verified by `test_apply_patient_offset_slider_tick_writes_meta_not_globals`
   (`test_gui_multi_exam_geometry_offsets.py:167`). OK.
2. **The `N EXAMS` badge in the same row** (calculate.py:75) binds to
   `state.loaded_exams` (not `is_multi_exam`) — this is fine and
   self-consistent.

The plan does not flag whether the row's other text (e.g., the `5 EXAMS`
badge label) should be reformatted. It shouldn't — the badge is just a
counter. Minor, but call it out so the next maintainer doesn't "fix" it.

### 2.2 `_format_patient_offsets()` (calculate.py:19) — three underspecs

Current:
```python
def _format_patient_offsets() -> str:
    return f"X: {state.d_lon:.1f}, Y: {state.d_ver:.1f}, Z: {state.d_lat:.1f} cm"
```

Plan (line 233) calls for:
- "When `is_multi_exam`: per-exam summary using **lon/ver/lat** labels."
- "Format: `Exam #1: lon=…, ver=…, lat=… cm` on **one line**."
- "Truncate after 3 exams: `…, and N more`."
- Cases: 1 exam (single-line branch), 2–3 exams (full list), 4+
  (truncate), empty `loaded_exams` → `"—"`.
- "Rebind: replace `bind_text_from(state, "d_lon/d_ver/d_lat")` with
  predicate over `loaded_exam_meta` + `is_multi_exam`."

Three concrete gaps that need to be resolved before code lands:

**G2.2.a — axis label vocabulary.**
The plan explicitly says `lon/ver/lat`. The current `X/Y/Z` matches the
coordinate-system docs (`docs/source/gui_help/positioning_offsets.md:24`,
`Lateral (X) / Longitudinal (Y) / Vertical (Z)`) and the per-axis
short-form label in `settings.py:122` ("Patient Offsets (adjustable, cm)").
The Geometry tab **sliders** use `lon/ver/lat` (geometry.py:152–154), and
`_per_exam.py:156` uses the same. So `lon/ver/lat` is the modern convention.

This is a **breaking change** for the Calculate tab's `Patient Offsets:`
line, which is the only label on screen that still uses `X/Y/Z` after the
change. Verify the change is intentional and call out the migration (the
docs/Positioning offsets help page is `X/Y/Z`-heavy and will also need a
sweep). The plan's Part V "Docs" row mentions `positioning_offsets.md`
but not the rest of the help files; if the `X/Y/Z → lon/ver/lat` switch
is global, then all three help files (plus the `X → LAT` axis label in
`figures.py:162–164`) need to be updated for consistency.

**G2.2.b — multi-exam summary predicate and trigger.**
The current bind pattern (calculate.py:132–140) has four `bind_text_from`
calls keyed to `d_lon`, `d_ver`, `d_lat`, `normalization_method`. After the
change, the formatter needs to refresh whenever
`state.loaded_exam_meta[i].d_*` changes for any `i`. NiceGUI's
`bind_text_from` does not natively support "refresh when any item of a
list-of-dicts changes," so the practical options are:

1. Add a new state field, e.g. `state.per_exam_offsets_version: int`, and
   bump it in `apply_patient_offset_slider_tick` and the per-exam spinbox
   on-change handler. Then `bind_text_from(state, "per_exam_offsets_version", ...)`.
2. Use a `ui.timer` to poll `state.loaded_exam_meta` and call
   `patient_offset_summary.set_text(_format_patient_offsets())` when the
   tuple changes.
3. Re-derive the formatter in each write site (slider tick in
   `geometry.py:418`, spinbox in `_per_exam.py:55`, reset in
   `geometry.py:433`) and call `set_text` directly.

The plan does not pick. **Pick one and document it** — this is a real
implementation choice with non-trivial trade-offs (option 1 is the
cleanest but adds state; option 3 duplicates the formatter trigger at
every write site). Recommend option 1, with a one-line docstring on
`per_exam_offsets_version` explaining the bump sites.

**G2.2.c — empty-state return.**
The plan says empty `loaded_exams` → `"—"`. Current code returns
`"X: 0.0, Y: 0.0, Z: 0.0 cm"` even with no data loaded. Behavior change
is intentional; just verify the calling widget handles an em-dash
gracefully. The current `ui.label(_format_patient_offsets())` (line 129)
treats the value as a string, so any string is fine — OK.

### 2.3 `_format_table_offset_line()` (settings.py:40) — branch lives in `settings.py`

Plan (line 234): when `is_multi_exam`, return `"Per-exam: see Per-exam
corrections below."`

The function lives in `tabs/settings.py:40` and is imported into
`tabs/calculate.py:16` (`from .settings import BELOW_FLOOR_KVP_OPTIONS,
_format_table_offset_line`). The branch can stay in `settings.py`; the
import path doesn't change. Plan is correct here.

**G2.3.a — refresh trigger.**
The current `bind_text_from` (settings.py:86–91) is keyed to
`table_offset_x`, `table_offset_y`, `table_offset_z`, and
`normalization_method`. None of those change in multi-exam mode (the
global `table_offset_*` reflect the most recently loaded exam only). The
multi-exam caption needs to refresh on the **multi→single toggle** (load,
remove) and on every **per-exam** table-origin commit, not on
`table_offset_*`.

Two viable triggers:

1. Add a `bind_text_from(state, "is_multi_exam", backward=lambda _v: _format_table_offset_line())`.
   This re-renders the label every time `is_multi_exam` flips, which
   covers load/remove. It does **not** cover per-exam table-origin
   commits, but the multi-exam branch's return value does not depend on
   per-exam state — it's the same string regardless. OK.
2. A `ui.timer` polling `state.is_multi_exam`. Heavier, no benefit.

Pick option 1. The plan's parenthetical "(or meta predicate) so caption
updates on load toggle" (line 234) is correct, just call out the explicit
`is_multi_exam` trigger.

**G2.3.b — also affects the Calculate tab.**
`calculate.py:145` instantiates a separate `table_offset_summary` label
and binds it to the same four globals. The plan does not say whether
the **Calculate tab's** table offset summary should also flip to the
multi-exam caption. Reading the plan literally ("Branch lives here;
`calculate.py` keeps importing the same symbol") — yes, the Calculate
tab's `_format_table_offset_line()` call will also return the
multi-exam caption, because it's the same function. Verify this is the
intent. The Calculate tab is a settings summary, and showing
"Per-exam: see Per-exam corrections below" in the summary is a
reasonable default; but the user might expect the Calculate tab to show
a per-exam table offset table. **Flag this as a UX question** and pick
either (a) same caption in both tabs (simplest, what the plan implies)
or (b) a per-exam table in the Calculate tab (more informative, more
work).

### 2.4 `settings.py` Phantom offsets hidden when multi-exam (line 235)

Plan (line 235): hide the global spinbox row when `is_multi_exam`. Three
specifics are not stated:

**G2.4.a — what exactly to hide.**
The current code (settings.py:140–149) wraps three `ui.number` spinboxes
in `ui.row().classes("w-full gap-4")`. Hiding the row also hides the
spinners; the surrounding `ui.label("Patient Offsets (adjustable, cm)")`
(settings.py:122) is **outside** the row and would still show. Plan
should explicitly call this out: do we want the section header to remain
visible (with a sub-caption explaining per-exam mode), or do we hide
header + row + everything? Reading the plan, "Hide the **entire** global
spinbox `ui.row`" implies just the row, but the surrounding
"Patient Offsets (adjustable, cm)" label is now misleading. Recommend
hiding both the row and the label, with C6 caption replacing them.

**G2.4.b — `offset_range_hint` handling.**
Plan says: "Hide `offset_range_hint` in multi-exam too (it reads globals,
which are 0 after multi-exam load)." Verified — the hint (settings.py:124)
reads `state.d_lon/ver/lat`; in multi-exam these are 0 (or 0/0/0 after
the B1 fix resets them in `reset_global_offsets_on_new_load`), so the
hint can never trigger. Hiding is correct. The `_on_patient_offset_change`
handler (settings.py:136) is bound to the global spinboxes' on-change
events; after hiding the spinboxes, the handler is dead code in
multi-exam. Recommend gating the whole `_update_offset_range_hint` block
behind `not state.is_multi_exam` (or simply deleting it in multi-exam
mode via a `bind_visibility_from`).

**G2.4.c — C6 placement.**
Plan Appendix B (line 349): "**Patient offsets are managed per-exam in
multi-exam mode. Adjust them in the Geometry tab or Per-exam corrections
section below.**"

The plan says "Place C6 caption **inside Phantom Settings expansion, above
the hidden row**." Concrete suggestion: replace the `ui.label("Patient
Offsets (adjustable, cm)")` (settings.py:122) and the hidden row
(settings.py:140–149) with a single `ui.label` that shows the C6 text
when `is_multi_exam`, and the row when not. Bind the row to
`is_multi_exam` with `backward=lambda v: not v`, and bind the C6 caption
to `is_multi_exam` with `backward=bool`.

**G2.4.d — "Apply global to all" button placement in multi-exam.**
`_per_exam.py:255` shows the "Apply global to all" button **only** when
`is_multi_exam`. This is the inverse of the Phantom row hide. Currently
in multi-exam the user sees: hidden Phantom row + visible "Apply global
to all" in Per-exam corrections. The C6 caption needs to point at the
"Apply global to all" button, but the button is in a different
expansion. The plan doesn't mention this — make sure the C6 caption
mentions both the Geometry tab and the "Per-exam corrections" expansion
in Settings (which is what the plan text says), not just "Per-exam
corrections below" if "below" is ambiguous from the user's perspective
when reading the Phantom Settings expansion.

### 2.5 N4 cross-tab re-clamp (line 237)

Plan (line 237): "When `apply_exam_transforms` fires from Settings
(`_per_exam.py`), `rebuild_rdsr_df` replaces `state.rdsr_df`. **Owner:**
`geometry.py` `_refresh_geometry_sliders` clamps `geom_event_input` to
`preview_event_count(...) - 1` and schedules re-render if
`last_preview_mode` set. `_per_exam.py` transform handler must call
`ctx.refresh_per_exam()` (already does for offset changes; verify
transform path)."

**G2.5.a — verify `_on_exam_transform_change` calls `ctx.refresh_per_exam()`.**
Looking at `_per_exam.py:60–69`:
```python
def _on_exam_transform_change(index: int, key: str, value) -> None:
    if not (0 <= index < len(state.loaded_exam_meta)):
        return
    state.loaded_exam_meta[index][key] = bool(value)
    apply_exam_transforms(state, index)
    _invalidate()
    ctx.refresh_event_table()
    ctx.refresh_import_preview()
```

It calls `ctx.refresh_event_table()` and `ctx.refresh_import_preview()`,
but **not** `ctx.refresh_per_exam()`. The plan's "verify transform path"
hedge is correct — the call is missing. **Fix:** add
`ctx.refresh_per_exam()` after `_invalidate()` (matching the pattern in
`_on_exam_offset_change` at line 58, which the plan already accepts as
shipped). Without this, the Geometry tab's `geom_event_input` value is
**not re-clamped** when the user toggles a per-exam coordinate fix in
Settings, so the event index can point to a row that no longer exists
after `apply_exam_transforms` rebuilds the frame.

**G2.5.b — clamp implementation.**
Plan says "clamp `geom_event_input` to `preview_event_count(...) - 1`."
But: the per-exam transform may **shrink** the active exam's slice
(e.g., `swap_lat_lon` re-derives coordinates; if some rows have NaN
coordinates after the swap, `apply_exam_transforms` may drop them).
`geom_event_input.value` should be clamped to the new slice count, not
to the full multi-exam count. Implementation:

```python
slice_count = preview_event_count(
    state,
    active_exam_index=state.active_exam_index if state.is_multi_exam else None,
    composite=False,
)
if slice_count > 0 and int(geom_event_input.value or 0) >= slice_count:
    geom_event_input.set_value(slice_count - 1)
```

Schedule a re-render only if `last_preview_mode` is set (per plan).
Place in `_refresh_geometry_sliders` (geometry.py:552) so it runs after
`ctx.refresh_per_exam` wires through.

**G2.5.c — last_preview_mode survival across Settings edits.**
`_refresh_geometry_sliders` is called from `ctx.refresh_per_exam`, which
in turn is called from `apply_patient_offset_slider_tick` and
`_on_exam_offset_change`. The plan implicitly assumes `last_preview_mode`
is set in the closure scope; verify this. Looking at
`geometry.py:70`, `last_preview_mode` is a closure variable scoped to
`build(ctx)`, so it's shared between the tab builder and all handlers.
Good. But: after a `clear_all_exams`, the user may not have set
`last_preview_mode` yet (no preview button clicked). The plan says
"schedule re-render if `last_preview_mode` set" — this guard is correct.
Verify the implementation: if `last_preview_mode is None`, the clamp
still needs to happen (the user could be in the middle of editing the
event number), so do the clamp regardless and only re-render on
`last_preview_mode` being set.

### 2.6 Docs list (line 238)

Plan lists:
> `docs/source/gui_help/positioning_offsets.md`, `AGENTS.md`,
> `CHANGELOG.md`, `TO_DO.md`, `dev-docs/CODEBASE_OVERVIEW.md`,
> `dev-docs/FEATURE_INVENTORY.md`, `dev-docs/plans/GUI_PLAN.md` §0,
> `dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md`, cross-check
> `dev-docs/VENDOR_COORDINATE_SYSTEMS.md` and
> `dev-docs/GUISKINDOSE_MIGRATION_STATUS.md`.

**G2.6.a — "Edit `docs/source/gui_help/positioning_offsets.md`, then
`python scripts/sync_gui_help.py`."**
The plan says "canonical source is `docs/source/gui_help/positioning_offsets.md`,
mirrored by `scripts/sync_gui_help.py`" — but it does not say **which
side to edit** explicitly. The AGENTS.md `global rule` is "Edit the
source under `docs/`, never the mirrored copies under `src/`" — the
plan's wording is ambiguous. Tighten: "Edit
`docs/source/gui_help/positioning_offsets.md` (canonical); run
`python scripts/sync_gui_help.py` to mirror to
`src/guiskindose/gui/help/positioning_offsets.md`. Do not edit the
mirrored copy directly."

**G2.6.b — missing help files in the sweep.**
The plan only names `positioning_offsets.md` and
`below_floor_kvp.md` (the latter is C5 in the Appendix). But the
multi-exam workflow also affects the Geometry tab help
(`docs/source/gui_help/geometry_workflow.md`). Currently this file
(43 lines) has zero multi-exam awareness. If the "Multiple exams"
subsection is added to `positioning_offsets.md` per Appendix B C5,
fine, but `geometry_workflow.md` should also be updated to mention the
exam selector and composite preview toggle in the Workflow section.

**G2.6.c — `dev-docs/CODEBASE_OVERVIEW.md` and
`dev-docs/FEATURE_INVENTORY.md` need a "multi-exam Geometry" section.**
A `grep` for "multi-exam" in `dev-docs/CODEBASE_OVERVIEW.md` returns no
matches. The current overview has no mention of the exam selector, the
composite preview, the per-active slider semantics, or the
`rdsr_df_for_geometry_preview` helper. After Part V, the overview should
have a paragraph describing:
- The exam selector in the Geometry tab
- The composite preview toggle and its purpose
- The `meta[active]` read/write pattern for patient offsets
- The `composite_live_preview_paused` thresholds (30/100)
The plan's "Docs" row mentions `CODEBASE_OVERVIEW.md` but does not
specify what to add. Same for `FEATURE_INVENTORY.md`.

**G2.6.d — `CHANGELOG.md` entry is missing a "Part V" line.**
Current `CHANGELOG.md` (verified by grep) has entries for Parts I, II,
III, and IV (line 28): "Multi-exam patient-offset sliders (Geometry)
(2026-06-24) — Part IV: ...". The plan does not specify the Part V
changelog wording. Suggest: "**Multi-exam Geometry cross-cutting
updates** (2026-06-24) — Part V: Calculate tab per-exam patient
offsets summary; Settings tab hides global patient offset spinboxes in
multi-exam; Settings → Per-exam corrections transform handler triggers
Geometry refresh; `positioning_offsets.md` help updated; per-exam
offset commit re-clamps Geometry event index."

**G2.6.e — `dev-docs/GUISKINDOSE_MIGRATION_STATUS.md` cross-check.**
The plan says "cross-check" rather than "update." This is correct
because the migration status doc compares MyPySkinDose to upstream
PySkinDose; the new per-exam semantics are a MyPySkinDose-only feature,
so a cross-check is enough. But: if upstream PySkinDose has any
`d_lon/d_ver/d_lat` handling that conflicts with the per-exam
semantics (e.g., upstream uses a single global, and the
migration doc says "compatible" somewhere), that statement needs
updating. Worth a one-line note in the assessment footer.

### 2.7 Tests for Part V (Appendix B "Part V add")

Plan (Appendix B line 360): "Part V add: `test_format_patient_offsets_multi_exam`,
`test_format_table_offset_line_multi_exam` (T10) — cover 1 / 2–3 / 4+ / empty
exams."

**G2.7.a — N4 re-clamp test missing.**
There is no test for the `_on_exam_transform_change` → `geom_event_input`
clamp behavior (G2.5). Add: `test_settings_per_exam_transform_change_clamps_geometry_event_input`
in `test_gui_multi_exam_geometry_offsets.py`. The setup: build a state
with 2 exams, each with 5 events, set `geom_event_input.value = 4`,
call `_on_exam_transform_change(0, "swap_lat_lon", True)`, assert
`geom_event_input.value <= new_active_slice_count - 1`.

**G2.7.b — `_format_patient_offsets` test.**
The plan says "1 / 2–3 / 4+ / empty exams" but the test is missing
from the file. Also: the formatter's "lon/ver/lat" axis labels need
to be asserted in the test, not just the structure — otherwise a
regression that drops back to `X/Y/Z` would not be caught.

**G2.7.c — `_format_table_offset_line` test.**
Plan says "Per-exam: see Per-exam corrections below." in multi-exam.
Test: build a state with `is_multi_exam=True` and 2 exams; assert
`"Per-exam: see Per-exam corrections below."` in the output. Build a
state with `is_multi_exam=False`; assert the current `X: ..., Y: ...,
Z: ...` output. Also test the "Unknown" and "Tabular" branches (the
current code has them, the new multi-exam branch should not change
them).

**G2.7.d — multi-exam `is_multi_exam` change triggers reformat.**
Test: in `is_multi_exam=False`, set up a label bound to the
`_format_patient_offsets` function via `bind_text_from(state, "is_multi_exam", ...)`;
set `state.is_multi_exam=True` with 2 loaded exams; assert the label
text now matches the multi-exam summary format. This is the "refresh
trigger" test that locks in the bind strategy from G2.2.b.

**G2.7.e — `offset_range_hint` hidden in multi-exam.**
Currently the hint reads globals. In multi-exam the hint should be
hidden. Test: build a state with `is_multi_exam=True`; check the
`offset_range_hint.visible == False` (or the bound predicate
`is_multi_exam=False` returns False). Trivial, but locks in the
visibility behavior.

---

## 3. Appendix A — one row needs updating

The appendix's status table (plan lines 295–331) is mostly accurate after
the Round 7 assessment verified Parts I–III. With the recent
"Parts IV-a/b shipped" update, only one row needs an update:

| Row | Current | Recommended | Why |
|-----|---------|-------------|-----|
| T5 | DONE (single row) | Split into T5a (DONE) and T5b (DONE), or mark PARTIAL | The current row text says "_reset_table_origin hardcoded to meta[0] / use active_exam_index when multi-exam" — but there are **two** reset functions: `_reset_table_origin` (geometry.py:446) and `_reset_patient_offset` (geometry.py:433). The current row text describes both without disambiguating. Marking DONE is honest because both are now per-active, but the row text is misleading. |

**Recommendation:** split T5 into T5a (table-origin reset) and T5b
(patient offset reset) to match the IV-a/IV-b split and the existing
T31 row that covers `val_labels` separately.

---

## 4. Part VI — three deferred items need more thought

The plan's Part VI (line 242) defers three cross-tab polish items:
VI-A (Upload exam card click → switch to Geometry), VI-B (Settings
per-exam card highlight for `active_exam_index`), VI-C (disambiguate
duplicate selector labels with `study_id` / `sheet`).

Two of these are simpler than the plan implies, and one is harder:

**VI-A (Upload → Geometry click):** the `ui.card` for each loaded exam
already has a click handler somewhere (verify — if not, add one).
Switching the active tab is `ui.tab_panels.set_value("geometry")`.
Roughly 5 lines of code. **Recommend including VI-A in Part V** as a
small UX win that pairs naturally with the docs sweep.

**VI-B (highlight active exam card):** the Settings per-exam cards
are rebuilt by `refresh()` in `_per_exam.py:223` every time. The card
build is fresh each call, so a simple `border: 2px solid amber` on the
`ui.card` for the active index works. About 3 lines in
`_build_exam_card` (line 136). **Recommend including VI-B in Part V.**

**VI-C (study_id / sheet disambiguation):** this is harder than the
other two. Requires DICOM tag parsing for `StudyInstanceUID` (not
currently in the loaded exam meta) and a sheet-aware label for XLSX
multi-sheet files. Recommend leaving deferred; add a TO_DO entry
referencing VI-C so it doesn't get lost.

---

## 5. Out-of-scope items should be in TO_DO

The plan's Out of scope section (line 253) lists:
- offset arrow (deferred to other plan)
- per-exam dose map toggles
- persisting Geometry UI across reload
- export `table_origin_override` in `data.py` — **already in TO_DO.md line 84**
- incremental table-origin preview
- per-exam event stepping — **already in TO_DO.md line 76**

Both audit-trail items are already in TO_DO. The remaining
out-of-scope items (offset arrow, dose map toggles, etc.) are not in
TO_DO. The plan's author may have intentionally omitted them as
speculative, but `per-exam event stepping` and `per-exam dose map
toggles` are natural follow-ups to Part IV and should be in TO_DO so
they don't get lost when this plan is archived.

Recommend: when archiving, copy these two items into TO_DO with a
link to the archived plan. Other out-of-scope items (offset arrow,
incremental preview, session-only state) can stay in the plan.

---

## 6. Naming and consistency

Five wording nits that survive from prior rounds:

1. **"Editing exam" vs "selected exam".** The plan's UI uses
   `label="Selected exam"` (geometry.py:112) but the plan prose uses
   both terms. C1 banner says "Sliders edit the **selected exam**
   below." C2 (Appendix B line 343) says "**this exam**." Pick
   "selected exam" everywhere (matches the visible UI label and C1).
   The earlier assessment (Round 7) flagged this; still pending.

2. **"scrub".** The codebase uses "scrub" for "slider tick path"
   (offset_handlers.py:88 `on_global_patient_offset_scrub`) and
   "scrub" for "user is dragging" in some prose. The plan's
   "Preview semantics" (line 31) has a parenthetical "In this
   codebase 'scrub' means the slider **tick path**..." — good,
   keep this clarification in the plan. Consider adding a one-line
   glossary entry at the top of the plan.

3. **"composite" has two meanings.** The plan uses "composite" for
   (a) the multi-exam preview that combines all exams' events, and
   never for (b) the multi-exam dose map. Recommend in C3/C4 copy:
   "all exams' events" (not "all exams" alone, which is ambiguous
   between events and dose map). The current copy in
   `geometry_preview.py:144` and `geometry.py:120` is already
   "all exams' events" — good. Just keep it consistent in any
   future doc additions.

4. **"preview_caption" vs "caption".** The symbol is `preview_caption`
   in `geometry.py:123` and the helper is `geometry_preview_caption` in
   `geometry_preview.py:130`. Two different names for the same
   concept. The shorter form is local to the geometry tab, the
   longer form is the public API. This is a defensible split
   (local-closure helper vs exported function), but a one-line
   comment cross-referencing the two would help.

5. **"debounced render" vs "live preview".** The plan uses both
   interchangeably. The actual code uses `_schedule_debounced_render`
   for the slider-driven preview and `live_preview_requested` /
   `live_preview_allowed` for the gated rendering. The two are
   related but not identical — `live_preview_allowed` is the gate,
   `_schedule_debounced_render` is the trigger. Suggest picking
   "debounced render" for the trigger and "live preview" for the
   gate, and using them consistently.

---

## 7. Edge cases not fully covered

### 7.1 Empty `loaded_exams` (0 exams)

Plan covers (line 147): "with 0 exams (`rdsr_df` None), C1 banner and
selector hidden (`is_multi_exam` false); `offset_controls` hidden
(`rdsr_df` None); tab shows header + preview buttons only (plot empty
until load)."

This is correct for the Geometry tab. But:

- **`composite_checkbox` and `preview_caption` visibility.** Both
  are inside `preview_controls` (geometry.py:115), which binds to
  `is_multi_exam`. With 0 exams, `is_multi_exam=False`, so they are
  hidden. Good.
- **`_update_preview_caption` runs at the end of `build`.** With
  0 exams, `geometry_preview_caption` returns `""` (geometry_preview.py:137).
  The label is hidden by `preview_controls`, so setting the text is
  fine. OK.
- **`_format_patient_offsets` empty case.** Plan (G2.2.c) covers
  this. Empty `loaded_exams` → `"—"`.

### 7.2 Switching from 1 → 2 exams via load

When a second exam is loaded, `on_exams_loaded` (geometry_preview.py:42)
sets `active_exam_index=0` (the new exam is appended, but `clamp_active_exam_index`
is called for `n>1`). The Plan IV-a patient slider sync needs to fire
on this transition so the patient sliders show the new active exam's
`meta[0].d_*`. Verified: `_refresh_geometry_sliders` (geometry.py:552)
calls `_sync_patient_sliders_from_meta()` which uses
`read_patient_offset_value` (offset_handlers.py:49). OK.

But: the new exam's `d_lon/ver/lat` are seeded from pre-reset globals
in `exam_loaders.py` per Part I B1. Verify: `exam_loaders.py:82` and
`:250` and `:305` append a new meta dict; the dict is built with
explicit `d_lon`, `d_ver`, `d_lat` from the global. **Check the
loader code to confirm the B1 fix is in all three append sites** —
this is plan-level assumption that should be re-verified after the
prior round 7 assessment.

### 7.3 Removing the only exam (n → 0)

Plan (line 264): "0 exams: After IV-a: patient card hidden with
`offset_controls` (`rdsr_df` None). Table-origin already uses
`_table_origin_card_visible()`."

Verified: `offset_controls` (geometry.py:125) binds to
`bind_visibility_from(state, "rdsr_df", backward=lambda v: v is not None)`,
so it hides when `rdsr_df` is None (which is the case at n=0).
`patient_offset_card` is inside `offset_controls`, so it also hides.
`_table_origin_card_visible` (geometry.py:54) returns False when
`loaded_exam_meta` is empty. OK.

But: the `composite_checkbox` is **outside** `offset_controls` (it's
inside `preview_controls` which binds to `is_multi_exam`). At n=0,
`is_multi_exam=False`, so the checkbox is hidden. OK.

### 7.4 Closing the Geometry tab and re-opening (session state)

Not in scope (plan line 255 explicitly says "persisting Geometry UI
across reload (session-only)"). Confirm: `last_preview_mode`,
`composite_preview`, `last_table_origin_scrub`, `was_multi_exam` are
all closure variables scoped to `build(ctx)`. They reset on tab close
+ reopen. OK as documented.

### 7.5 `exam_selector_guard` programmatic update re-fires

The Round 7 assessment flagged this; plan T9 says DONE. Verified
(geometry.py:77, 512, 520). OK.

### 7.6 `state.rdsr_df` None during `_render_preview`

Plan T13: DONE. Verified (geometry.py:387–389 clears the plot). OK.

But: `_render_preview` is called from `_do_debounced_render` (geometry.py:382)
which is called from `_schedule_debounced_render` (line 363) which
is called from `_on_patient_slider_change` and `_on_table_slider`
and `_on_exam_select_change` and `_on_composite_toggle`. If the user
clicks "Clear all exams" between scheduling and rendering, `rdsr_df`
is None and the plot clears. OK. But: the `await _render_preview(...)`
inside `_do_debounced_render` (line 382) is conditional on
`live_preview_requested and live_preview_allowed()`. If `live_preview_allowed`
returns False because of the PAUSED gate, the render is skipped.
Verify the `geom_plot` is not stale. **Confirmed:** when
`live_preview_allowed` returns False, the render is skipped, but
`geom_spinner.visible` is set in the previous `_update_paused_badge`
call (line 360), so the user sees a PAUSED badge. OK.

---

## 8. Recommended order for the remaining work

The plan's Part V "Recommended order" (line 228) is good: IV-a tests →
N4 re-clamp → formatters + Phantom hide → IV-b → manual matrix → docs
sweep → archive. After the gap review, here's a slightly re-ordered list
with the G-items above absorbed:

| # | Item | Why first | G-items resolved | Estimate |
|---|------|-----------|------------------|----------|
| 1 | Add the four Part V formatter tests (G2.7.b/c/d) | Catch regressions before formatter code lands | G2.7.b, G2.7.c, G2.7.d | S |
| 2 | Add N4 cross-tab re-clamp test (G2.7.a) and fix `_on_exam_transform_change` to call `ctx.refresh_per_exam()` (G2.5.a/b/c) | Small, prevents user confusion on per-exam toggle | G2.5.a, G2.5.b, G2.5.c, G2.7.a | S |
| 3 | Decide and implement axis-label vocabulary (`lon/ver/lat` per plan, or `X/Y/Z` to match docs) | Cross-cutting decision; affects formatter, help, dose map | G2.2.a | S |
| 4 | Add `per_exam_offsets_version` state field (G2.2.b) and rewire formatter binds | Locks refresh trigger; small state change | G2.2.b | M |
| 5 | Implement `_format_patient_offsets` and `_format_table_offset_line` multi-exam branches (G2.2, G2.3) | Core Part V deliverable | G2.2, G2.3.a, G2.3.b | M |
| 6 | Hide Phantom row + label in multi-exam; place C6 caption (G2.4.a/b/c/d) | Visual change; user-visible | G2.4.a, G2.4.b, G2.4.c, G2.4.d | M |
| 7 | Update `calculate.py:78` string (G2.1) | Trivial | G2.1 | XS |
| 8 | Decide and implement Calculate-tab per-exam table offset summary (G2.3.b) | UX question | G2.3.b | S |
| 9 | Add `bind_text_from(state, "is_multi_exam", ...)` to `_format_table_offset_line` (G2.3.a) | Trivial | G2.3.a | XS |
| 10 | Implement VI-A (Upload → Geometry click) and VI-B (active-exam card highlight) | Polish; natural pair with docs sweep | Part VI A/B | S |
| 11 | Update `docs/source/gui_help/positioning_offsets.md` and run `scripts/sync_gui_help.py` (G2.6.a) | Doc-freshness gate | G2.6.a, G2.6.b | M |
| 12 | Update `docs/source/gui_help/geometry_workflow.md` (G2.6.b) | Doc consistency | G2.6.b | S |
| 13 | Update `dev-docs/CODEBASE_OVERVIEW.md` and `dev-docs/FEATURE_INVENTORY.md` with multi-exam Geometry section (G2.6.c) | Doc consistency | G2.6.c | S |
| 14 | Add Part V `CHANGELOG.md` entry (G2.6.d) | Release-history gate | G2.6.d | XS |
| 15 | Cross-check `dev-docs/GUISKINDOSE_MIGRATION_STATUS.md` (G2.6.e) and `dev-docs/VENDOR_COORDINATE_SYSTEMS.md` | Doc consistency | G2.6.e | XS |
| 16 | Append `per-exam event stepping` and `per-exam dose map toggles` to `TO_DO.md` (§5) | Lifecycle rule | §5 | XS |
| 17 | Manual matrix rerun (Appendix B) | Exit gate | — | S |
| 18 | `python scripts/check_doc_freshness.py`, `check_doc_pruning.py`, `check_file_sizes.py` | Exit criteria | — | S |
| 19 | Split T5 row in Appendix A into T5a/T5b (§3) | Appendix hygiene | §3 | XS |
| 20 | Archive plan; update `dev-docs/index.md`, `plans/archive/README.md`, `TO_DO.md` | Plan lifecycle rule | — | S |

After #9, the multi-exam Geometry workflow is mathematically correct
**and** the Calculate + Settings summaries are honest about per-exam
mode. After #15, all user-facing documentation is consistent. After
#20, the plan is archiveable.

---

## 9. Single-paragraph TL;DR for the maintainer

Parts I–IV (a + b) genuinely shipped: every T-item from the prior
round's gaps is fixed, the tests cover the patient-slider write-back
and composite preview surfaces, and the live code matches the plan's
"Done" claims. **Part V is the real remaining work**, and it contains
several underspecified spec points: axis-label vocabulary (`lon/ver/lat`
vs `X/Y/Z` — pick one and apply consistently across formatters, help
docs, dose map, and overview), formatter refresh trigger (state version
field vs timer vs write-site calls), C6 caption placement relative to
the "Apply global to all" button in Per-exam corrections, and the
N4 cross-tab event-index clamp (which also requires adding a missing
`ctx.refresh_per_exam()` call to `_on_exam_transform_change` in
`_per_exam.py:60`). The plan's Part V "Docs" row is missing
`docs/source/gui_help/geometry_workflow.md`, and the
`CODEBASE_OVERVIEW.md` / `FEATURE_INVENTORY.md` / `CHANGELOG.md`
updates are mentioned but not specified. **Action:** execute the 20-item
list in §8; the first five items are small and unblock the rest.

---

## 10. Confidence / verification notes

- **Verified in source:** the patient card is shown in multi-exam
  (geometry.py:128–184 has no `is_multi_exam` hide), the
  `composite_checkbox` and `preview_caption` are present
  (geometry.py:119, 123), `apply_patient_offset_slider_tick` writes
  to `meta[active]` only (offset_handlers.py:61–70), `_reset_patient_offset`
  uses `reset_patient_offset_for_active` which writes to `meta[active]`
  in multi-exam (offset_handlers.py:72–86), and the test file
  `test_gui_multi_exam_geometry_offsets.py` covers the IV-a/b surface
  (245 lines, 15 test functions).
- **Not verified in source:** the `_on_exam_transform_change` →
  `ctx.refresh_per_exam()` call. The grep for `ctx.refresh_per_exam` in
  `_per_exam.py` returns no matches; the function calls
  `ctx.refresh_event_table()` and `ctx.refresh_import_preview()` only.
  This is a **real gap** the plan does not flag. See G2.5.a.
- **Not verified in source:** that `positioning_offsets.md` is out of
  date. The current help file (86 lines) is single-exam-centric but is
  not actively wrong; the update is a content-add, not a correction.
- **Not verified in source:** the "per-exam event stepping" follow-up
  item is in `TO_DO.md` line 76. The "per-exam dose map toggles"
  follow-up is in `TO_DO.md` line 77. The "export `table_origin_override`"
  follow-up is in `TO_DO.md` line 84. Verified by grep.
- **Plan-vs-code deltas:** none for Parts I–IV. Part V is
  correctly identified as the remaining work. The "Status: Done"
  header on the plan (line 7) is honest.
