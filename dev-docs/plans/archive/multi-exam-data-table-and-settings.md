# Plan — Multi-exam Data Table exam column + Per-exam corrections in Settings

**Status:** Complete (2026-06-19)
**Owner:** GUI / multi-exam workstream
**Related:** [multiple-exams.md](multiple-exams.md), [../../TO_DO.md](../../TO_DO.md) (GUI/UX section)

## Objective

Two related multi-exam GUI improvements, currently tracked as TO_DO items:

1. **Data Table tab — exam-number column.** In multi-exam mode the normalized
   event table concatenates events from every loaded exam with no way to tell
   which exam (or source file) a row came from. Add an exam-identifier column.
2. **Per-exam corrections → Settings tab.** Per-exam patient offsets, coordinate
   corrections, and table-origin overrides currently live inside the *Upload*
   tab's loaded-exam list. Move them into a dedicated **"Per-exam corrections"**
   subsection under the *Settings* tab so each exam's controls are edited
   separately and live next to the global calculation settings.

## Acceptance criteria

- [x] Data Table (normalized view) shows an exam column (number + source file) that
      correctly labels every row in multi-exam mode; single-exam view is unaffected.
- [x] The exam column is display-only and never reaches `analyze_data` /
      `analyze_multiple_exams` (no calculation regression; golden PSD unchanged).
- [x] Per-exam offset / coordinate-correction / table-origin controls render under
      the Settings tab and editing one exam never mutates another.
- [x] Existing per-exam behavior (Phase 2.2–2.5: swap/flip toggles, axis flips,
      table-origin override, per-exam offsets, "Apply global to all") is preserved.
- [x] `AGENTS.md` GUI focus note + relevant `dev-docs/` page updated; `CHANGELOG.md`
      entry added; all validation commands pass.

---

## Current state (where the code lives)

- Concatenated preview frame: `state.rdsr_df` (`gui/state.py:21`). Built by
  `pd.concat([e.normalized_data ...])` at **three** sites in `gui/helpers.py`:
  `load_rdsr` (~L153), `load_tabular` (~L356), `recompute_exam` (~L701).
- Single-exam calc passes `state.rdsr_df.copy()` straight to `analyze_data`
  (`gui/helpers.py:475`). Multi-exam calc uses per-exam `state.loaded_exams`
  (`normalized_data` untouched), so the concat frame is **display + single-exam calc** only.
- Data Table tab reads `state.rdsr_df` / `state.rdsr_raw_df` and rebuilds columns
  from `df.columns` on a 2s timer (`gui/tabs/data.py:111`). Raw view is
  last-loaded-wins (not concatenated), so the exam column applies to the
  **normalized view only**.
- Per-exam controls are rendered by `_refresh_exams_table` inside the Upload tab
  (`gui/app.py:819`), with helpers `_apply_global_offset_to_all` (~L709),
  `_on_exam_offset_change` (~L725), `_on_exam_transform_change` (~L730),
  `_build_table_origin_section` (~L742), `_remove_exam` (~L989). Per-exam data is
  stored in `state.loaded_exam_meta` (parallel to `state.loaded_exams`).
- Settings tab is a separate module: `gui/tabs/settings.py` (`build(ctx)`),
  three expansions (Phantom / Physics / Visual).

---

## Item 2 — Data Table exam column

**Design:** centralize the concat so the exam tag is added in exactly one place,
and keep the tag out of the calculation frame.

- [x] Add `rebuild_rdsr_df(state)` helper in `gui/helpers.py` that rebuilds
      `state.rdsr_df` from `state.loaded_exams`, inserting a leading display column
      (proposed name `__exam__`, value `f"#{i+1} · {meta['file_name']}"` per exam,
      using `loaded_exam_meta` for the label). Use a dunder/sentinel name so it is
      unambiguously a display column.
- [x] Replace all three inline `pd.concat(...)` blocks (`load_rdsr`, `load_tabular`,
      `recompute_exam`) with a call to the new helper. Confirm `state.is_multi_exam`
      and `file_name` updates still happen at each site (helper rebuilds the frame
      only; callers keep their own bookkeeping).
- [x] Single-exam calc path (`gui/helpers.py:475`): drop the display column before
      `analyze_data` — `state.rdsr_df.drop(columns="__exam__", errors="ignore").copy()`.
      (Multi-exam path already ignores `rdsr_df`.)
- [x] Data Table column builder (`gui/tabs/data.py:_refresh_raw_table`): when present,
      pin `__exam__` first with a friendly label ("Exam"); leave raw view unchanged.
- [x] Consider whether the existing export (`_local_export`) should keep or drop the
      column — keep it for the normalized CSV/XLSX (useful provenance), drop it from
      the raw export (raw is single-source). Decide and note in the changelog.

**Risk:** any other consumer that assumes `rdsr_df` columns equal raw normalized
variables. `analyze_data` is the main one (handled above). Grep `state.rdsr_df`
usages and confirm none index by positional/`.columns` assumptions before calc.

---

## Item 3 — Per-exam corrections in Settings tab

**Design:** extract the per-exam list builder into a reusable function and render it
from the Settings tab. Keep `state` + `loaded_exam_meta` as the single source of
truth so the controls behave identically wherever they're mounted.

- [x] Extract `_refresh_exams_table` (and its handlers `_apply_global_offset_to_all`,
      `_on_exam_offset_change`, `_on_exam_transform_change`, `_build_table_origin_section`)
      out of the Upload-tab closure. Two viable approaches — pick one:
      - **(a)** Move into a new `gui/tabs/_per_exam.py` module exposing
        `build_per_exam_section(container)` that reads `state`; call it from
        `settings.py`. Cleanest separation, removes ~180 lines from `app.py`
        (helps the `app.py` refactor TO_DO + 800-line size budget).
      - **(b)** Keep in `app.py` but parameterize the mount container and invoke from
        the Settings build. Smaller diff, less cleanup.
      Recommendation: **(a)** — `app.py` is 1443 lines and already flagged for refactor.
- [x] Add a **"Per-exam corrections"** expansion in `gui/tabs/settings.py` (after
      Phantom Settings, since it concerns geometry/offsets). Mount the extracted
      section there. Show an empty-state hint when no exams are loaded.
- [x] Remove the per-exam list from the Upload tab (or leave a one-line pointer:
      "Per-exam corrections moved to Settings → Per-exam corrections"). Decide whether
      the loaded-exam *summary* (badges, remove button, warnings) stays on Upload while
      only the *correction controls* move — likely keep a compact loaded-files summary
      on Upload, move the editable offset/correction/table-origin controls to Settings.
- [x] Verify the visibility gating still holds: per-exam offsets + coordinate
      corrections only meaningful in multi-exam mode; table-origin override shows for
      single + multi (matches current `exam_supports_table_origin`).
- [x] Confirm reactivity: Settings-tab controls bound to `loaded_exam_meta[i]` must
      still call `reset_results` / the existing `_on_exam_*` handlers so stale results
      are invalidated and `recompute_exam` re-derives the affected exam only.

---

## Validation

```bash
python -m pytest tests/ -q            # unit + GUI smoke
basedpyright
python scripts/check_doc_freshness.py
python scripts/check_file_sizes.py    # confirm app.py shrank, no new >800 file
python scripts/check_changelog.py
```

- [ ] Manual GUI check (still pending — ties into the existing **Multi-exam manual
      smoke check** TO_DO): load 2+ exams, confirm the Data Table exam column labels rows correctly,
      edit one exam's offset/corrections under Settings and confirm only that exam's
      geometry/result changes, run Calculate, verify results accordion.

## Out of scope

- Geometry-tab per-exam event selection, dose-map per-exam toggles (separate TO_DO items).
- Changing the per-exam transform math (Phase 2.2–2.5 logic is reused as-is).
