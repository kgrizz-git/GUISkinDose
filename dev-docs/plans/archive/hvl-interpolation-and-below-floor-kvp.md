# Plan — HVL interpolation + user options for below-floor kVp events

**Status:** Complete (2026-06-19) — both phases shipped.
**Owner:** physics / calc + GUI workstream
**Related:** [hvl-invalid-event-crash.md](hvl-invalid-event-crash.md)
(the crash fix this builds on), [TO_DO.md](../../TO_DO.md) → "HVL
interpolation/extrapolation" and "User options for below-floor / unresolvable
kVp events".

## Objective

Two related TO_DO items, sequenced as two phases of one plan because they share a
detection path (off-grid / below-floor events), a substitution mechanism, and the
existing `state.calc_warnings` surfacing channel:

1. **HVL interpolation/extrapolation.** Replace the exact-match-with-nearest-snap
   HVL lookup with **linear N-D interpolation** across the tabulated grid, and the
   unguarded exact-match `k_tab` lookup with a guarded interpolation/snap. Classify
   every event as `exact` / `interpolated` / `clamped` (out-of-range → nearest grid
   edge) and warn per event when not exact. HVL drives **k_bs** and **k_med**;
   **k_tab** keys on Cu/Al/kVp directly.
2. **User options for below-floor kVp events.** Events with **kVp < 25 kV** (below
   the HVL table floor) are currently snapped silently (well, logged). Offer the
   user an explicit policy — **skip** the event, **enter a kVp manually**, or
   **substitute the exam's average kVp** — via a **Settings default + a pre-calc
   prompt** when such events are detected.

## Acceptance criteria

- [x] In-grid events produce identical HVL/k_tab to today (golden PSD unchanged;
      regression test asserts byte-for-byte parity on the example RDSR).
- [x] Off-grid-but-in-bounds events get a linearly interpolated HVL/k_tab instead
      of a nearest snap; out-of-bounds events are clamped to the grid edge and
      flagged `clamped`.
- [x] `k_tab` no longer crashes on an off-grid `(kVp, Cu, Al, model, plane)` tuple
      (current `c.fetchone()[0]` raises `TypeError` on `None`).
- [x] Each non-exact event emits a `logger.warning` through the `mypyskindose`
      logger (so it lands in `state.calc_warnings` → calc-tab status line + toast),
      naming the event index, the query point, the substituted value, and the
      class (`interpolated` / `clamped`).
- [x] Below-floor (kVp < 25) events honor a user-selected policy
      (`snap` default / `skip` / `manual` / `exam_average`); per-exam average is
      computed from that exam's in-floor events only.
- [x] A pre-calc prompt appears when below-floor events are detected and surfaces
      the policy choice; the Settings control holds the persistent default.
- [x] `AGENTS.md` + relevant `dev-docs/` page updated; `CHANGELOG.md` entry added;
      all validation commands pass.

---

## Background — current state (verified 2026-06-19)

- **HVL** — `geom_calc.fetch_and_append_hvl` ([geom_calc.py:223](../../../src/guiskindose/geom_calc.py#L223))
  reads the whole `hvl_combined` table and does an **exact match** on
  `(round(kVp), round(inherent,1), Cu, round(Al))`, with a **nearest-grid snap**
  fallback (added by the crash-fix plan) and a single aggregate `logger.warning`
  for snapped events. HVL is appended as `data_norm["HVL"]`.
- **HVL grid** (`table_data/hvl_tables/hvl_combined.csv`, 65 534 rows):
  - kVp 25–175 (integer), inherent 2.0–5.0 (0.1 step), Cu `{0,0.1,0.2,0.3,0.4,0.6,0.9}`,
    Al `{0,1}`, anode angle `{8,11}`.
  - The **combined** table is *not* a clean Cartesian grid (anode angles overlap),
    but **each anode-angle slice is a complete 4-D regular grid**
    (anode 8 → 28 086 rows, anode 11 → 37 448 rows, both `dupmax==1`). →
    `scipy.interpolate.RegularGridInterpolator` works **per anode-angle slice**.
  - The current lookup **does not constrain anode angle** and takes `.iloc[0]`, so
    it effectively returns the first CSV row (anode 11 leads the file). Interpolation
    must pick the **same slice deterministically** to keep in-grid results identical.
- **k_bs** — `corrections.calculate_k_bs` ([corrections.py:49](../../../src/guiskindose/corrections.py#L49))
  is a **continuous polynomial** in (kVp, HVL); no table lookup. It inherits
  accuracy purely from the HVL value, so fixing HVL fixes k_bs. **No change here.**
- **k_med** — `corrections.calculate_k_med` ([corrections.py:107](../../../src/guiskindose/corrections.py#L107))
  already selects the **closest** tabulated kVp then HVL from the SQLite
  `correction_medium_and_backscatter` table — nearest, cannot crash. Upgrading it to
  interpolation is **optional / lower priority** (its field-size and HVL dependence
  is weak); note it, do it only if Phase 1 leaves it cheap.
- **k_tab** — `corrections.calculate_k_tab` ([corrections.py:186](../../../src/guiskindose/corrections.py#L186))
  does an **exact-match SQL** on `(round(kVp), Cu, Al, model, plane)` ending in
  `c.fetchone()[0]`. On any off-grid tuple this is `None[0]` → **`TypeError`,
  aborting the whole calc.** This is the real remaining crash surface and must be
  guarded.
- **Warnings channel** — `_CalcWarningCollector`
  ([gui/helpers.py:24](../../../src/guiskindose/gui/helpers.py#L24)) attaches to the
  `mypyskindose` logger during `run_calculation`, collecting WARNING+ into
  `state.calc_warnings`, shown on the calculate tab. **Any `logger.warning` we emit
  is already surfaced — no new plumbing needed for Phase 1.**
- **Settings** — `build_settings` ([gui/helpers.py](../../../src/guiskindose/gui/helpers.py))
  maps `state.*` → `PyskindoseSettings` JSON (`estimate_k_tab`, `k_tab_val`,
  `inherent_filtration`, `remove_invalid_rows`, …). Below-floor policy fields will be
  added here and to the settings dataclass.
- **Floor threshold** — decided 2026-06-13: **kVp < 25 kV** is "below floor". Define
  it once as a constant derived from `kvp_grid.min()` so it tracks the table.

---

## Phase 1 — HVL (and k_tab) linear N-D interpolation + per-event flags

**Design:** one reusable grid-lookup helper returning `(value, status)` where
`status ∈ {exact, interpolated, clamped}`. Build it once per calc (the table is
small and static), interpolate within bounds, clamp + flag at the edges.

- [x] **Grid helper.** Add a small `clamped_interp(rgi, axes, query)` helper (in
      `geom_calc.py` or a `table_data`/`_grid.py` module) wrapping a prebuilt
      `scipy.interpolate.RegularGridInterpolator`. We **never extrapolate past the
      grid**: detect out-of-bounds ourselves (any axis query outside
      `[axis.min(), axis.max()]`) and **clamp the query to the nearest edge before
      interpolating**, so the edge node's value is used and the event is labelled
      `clamped`. An on-node query returns the tabulated value (RGI is exact at nodes)
      → label `exact` when every axis coordinate is on a node, else `interpolated`.
      Reused by both HVL (kVp × Cu) and k_tab (kVp × Cu per device/plane).
      *Implemented as `src/guiskindose/grid_interp.py` (`clamped_rgi_lookup` +
      `format_event_indices`); both call sites build/cache their own RGI.*
- [x] **HVL.** Rework `fetch_and_append_hvl` (data shape verified 2026-06-19;
      implemented + tested, golden PSD unchanged):
      - **Resolve anode angle by selection, not interpolation.** Anode angle (8°/11°)
        is a discrete tube-target property; blending slices is physically meaningless.
        Dedup the table on `(kVp, inherent, Cu, Al)` keeping the **first occurrence**
        — exactly what the old `.iloc[0]` returned (anode 11 where present, else 8) —
        so in-grid events keep identical HVLs. (The two anode slices cover *different*
        Cu/Al regions, so no single clean 4-D grid exists across anode; selecting
        sidesteps that.)
      - **Snap the device-fixed axes** (inherent → nearest available, Al → nearest
        available) — these are settings, near-always exact; off-grid is rare.
      - **2-D bilinear over (kVp, Cu)** on the chosen `(inherent, Al)` slice via
        `RegularGridInterpolator`. *Verified:* all 62 `(inherent, Al)` slices are
        complete `(kVp × Cu)` grids (kVp dense 25–175; Cu `{0,…,0.9}`), so RGI builds
        directly with no gap-filling. Cache the interpolator per `(inherent, Al)`.
      - **Round kVp to its nearest integer node, interpolate Cu (raw).** The kVp
        axis is tabulated at a dense **1 kV step**, so rounding loses nothing
        dosimetrically and preserves historical results (incl. the
        `test_fetch_hvl_from_database` characterization at kVp 81.4 → 6.549).
        Interpolation is reserved for the **sparse Cu axis** (tabulated gaps at
        0.5/0.7/0.8 mmCu) — the actual off-grid-filtration target of this work.
        On-node query returns the tabulated value (RGI exact at nodes) → parity.
      - Collect per-event status (`exact`/`interpolated`/`clamped`).
      - Emit **per-event** `logger.warning` for `interpolated`/`clamped` events
        (event index, query, HVL, class), plus keep an aggregate count line. Cap the
        per-event spam (e.g. first N, then "+M more") to avoid flooding long procedures.
- [x] **k_tab guard + interpolation.** In `calculate_k_tab`, replace the unguarded
      `c.fetchone()[0]` (implemented + tested):
      - Load `correction_table_and_pad_attenuation` once; filter to the event's
        `(model, plane)` (model or its de-spaced form, matching the old SQL). If no
        rows → fall back to `k_tab=1.0` and warn — never crash. **This is the real
        remaining crash fix** (unknown/other-vendor devices, e.g. GE).
      - **Exact match first** (round kVp, Cu, Al) → bit-for-bit parity with the old
        lookup (existing `test_fetch_correct_table_correction_*` tests preserved).
      - On miss: snap Al to the nearest measured value, then 2-D interpolate over
        `(kVp, Cu)` with edge clamping via the shared helper. *Verified:* every
        `(model, plane, Al)` subgrid is a complete `(kVp × Cu)` grid — no ragged
        `griddata` fallback needed. Single-Cu-column slices (AlluraClarity/Al=0) use
        the column value at the clamped kVp node.
      - Per-event `interpolated`/`clamped`/`no-device` warnings to `state.calc_warnings`.
- [~] **k_med (optional) — deferred.** Left as nearest-tabulated: it already
      selects the closest kVp/HVL (cannot crash), and its field-size dependence is
      documented in-code as <1%. Noted in the changelog; revisit only if accuracy
      warrants.
- [ ] **Tests** (`tests/unittests/test_geom_calc.py`, `test_corrections.py`):
      - In-grid event → interpolated value **==** old exact value (parity / golden).
      - Off-grid-in-bounds event (e.g. Cu 0.5, between 0.4 and 0.6) → value strictly
        between the bracketing nodes; status `interpolated`; warning emitted.
      - Out-of-bounds event (kVp 200, Cu 1.5) → clamped to edge; status
        `clamped`; no crash.
      - k_tab with an off-grid `(kVp, Cu, Al)` and with an unknown `(model, plane)`
        → no `TypeError`, sensible fallback, warning emitted.
      - Full-calc smoke on the example RDSR → **PSD unchanged** vs the recorded
        golden (all events in-grid there).

**Risk / watch:**
- *Anode-angle ambiguity* — picking a different slice than the old `.iloc[0]` would
  shift in-grid HVLs and break the golden PSD. The parity test guards this; choose
  the slice explicitly and comment why.
- *Performance* — building the interpolator once per calc is fine (static table);
  do **not** rebuild per event.
- *NaN/inf at clamp* — guard `fill_value` so a far-out query never yields NaN that
  propagates into k_bs/k_med.

---

## Phase 2 — User options for below-floor kVp events (Settings default + prompt)

**Design:** a per-calc **policy** applied to events with kVp < floor *before*
`fetch_and_append_hvl`, so Phase 1's interpolation then sees only in-/near-grid
values. The policy has a persistent default in Settings and a pre-calc prompt that
appears only when below-floor events are actually present.

- [x] **Policy model.** Add a setting `below_floor_kvp_policy ∈ {"snap",
      "skip", "manual", "exam_average"}` (default `"snap"` = current behavior, fully
      backward compatible) and `below_floor_kvp_manual` (float, used by `"manual"`).
      Wire through the settings dataclass + `build_settings`. Define the floor
      constant once (`HVL_KVP_FLOOR = 25`, ideally derived from the table min).
      *Implemented: `constants.HVL_KVP_FLOOR` + `BELOW_FLOOR_KVP_POLICIES`;
      `PyskindoseSettings.below_floor_kvp_policy/_manual`; `gui/helpers.build_settings`
      + `settings_example.json` + GUI `AppState` fields.*
- [x] **Application point.** Add `apply_below_floor_kvp_policy(data_norm, policy,
      manual, floor)` (in `geom_calc.py` or `calculate_dose/`), called at the top of
      `calculate_dose` before HVL:
      - `snap` — leave kVp; Phase 1 clamps + flags `clamped` (status quo, just
        now explicit).
      - `skip` — drop below-floor rows (reuse/extend the `remove_invalid_rows`
        path); record dropped indices.
      - `manual` — set below-floor kVp = `manual` value.
      - `exam_average` — set below-floor kVp = mean kVp of that **exam's** in-floor
        events. **Multi-exam:** the multi-exam path calls per-exam
        `normalized_data` (`analyze_multiple_exams`), so "exam average" is naturally
        per-exam; for the concatenated single-exam path the whole frame is one exam.
        If an exam has *no* in-floor events, fall back to `snap` + warn.
      - Always `logger.warning` the count + indices + chosen action (lands in
        `state.calc_warnings`). *Implemented in `geom_calc.apply_below_floor_kvp_policy`,
        called in `calculate_dose` before `fetch_and_append_hvl`; naturally per-exam
        because `calculate_dose` runs once per exam.*
- [x] **Settings control.** Add a "Below-floor kVp handling" control under the
      Physics settings expansion (`gui/tabs/settings.py`): a policy `ui.select` +
      a `ui.number` for the manual kVp (shown only when `manual`). Bind to
      `state.below_floor_kvp_policy` / `state.below_floor_kvp_manual`; invalidate
      results on change (reuse the existing `reset_results` pattern). *Done, with a
      `below_floor_kvp.md` HelpButton; manual-kVp number toggled by a 0.5 s timer
      like the human-mesh selector.*
- [x] **Pre-calc prompt.** In the calculate flow (`gui/helpers.run_calculation` or
      the calculate-tab handler), **before** launching the calc, detect below-floor
      events across loaded exam(s). If any and the user hasn't suppressed it, show a
      dialog: "<N> event(s) below the 25 kV HVL floor. How should they be handled?"
      with the four options pre-selected to the Settings default and a "don't ask
      again" option. Proceeding uses the chosen policy for that run. *Implemented as
      `app._below_floor_prompt`; writes the choice back to `state` (the single source
      both the run and the Settings tab read, so the choice both applies and persists
      for the session — a separate "remember" toggle would have been redundant and was
      dropped). `state.below_floor_prompt_suppressed` backs "don't ask again".*
- [x] **Detection helper.** `count_below_floor_events(exams_or_df, floor)` returning
      per-exam counts + indices, reused by both the prompt and the warning text.
      *Implemented as `geom_calc.count_below_floor_events(data_norm, floor)` (single
      frame → positional indices) + `gui/helpers.below_floor_event_count(state)`
      summing across loaded exams for the prompt.*
- [x] **Tests:**
      - Each policy transforms kVp as specified on a synthetic frame with a couple
        of sub-floor events (skip drops rows; manual sets the value; exam_average
        uses the in-floor mean; snap is a no-op).
      - `exam_average` with an all-below-floor exam falls back to snap + warns.
      - GUI: `importorskip("nicegui")` smoke that `build_settings` propagates the
        policy and the detection helper sums across exams
        (`tests/unittests/test_gui_below_floor_kvp.py`).
      *Per-exam isolation is structural — `calculate_dose` runs once per exam on its
      own frame — so the exam-average mean is per-frame by construction.*

**Risk / watch:**
- *Prompt + headless / CLI* — the policy must be fully applicable **without** the
  prompt (CLI and tests use the Settings/`settings` value directly); the prompt is
  GUI-only sugar over the same setting. Keep the prompt out of the core calc path.
- *`skip` + multi-exam bookkeeping* — dropping rows must not desync
  `loaded_exams` / `loaded_exam_meta` / the `Exam` tag column
  (`rebuild_rdsr_df`). Prefer dropping inside the per-exam `normalized_data` copy
  used for calc, not the stored exam.

---

## Validation

```bash
python -m pytest tests/ -q            # unit + GUI smoke (new parity + policy tests)
basedpyright
python scripts/check_doc_freshness.py
python scripts/check_file_sizes.py    # corrections.py / geom_calc.py stay < 800
python scripts/check_changelog.py
```

- [ ] Manual GUI check (carried to `dev-docs/TO_DO.md` — requires a human at the
      GUI): load an export containing sub-floor and off-grid events; confirm the
      pre-calc prompt appears, each policy changes the result/PSD as expected, and
      interpolated/clamped events show as toasts + status count. Automated `nicegui`
      smoke tests already cover the settings/detection wiring.

## Decisions

- **HVL method: linear N-D interpolation** (`RegularGridInterpolator` per
  anode-angle slice) with **per-event exact/interpolated/clamped flags** (chosen
  2026-06-19). We **never extrapolate** past the grid: a query outside the grid
  bounds is **clamped** to the nearest edge node and flagged `clamped`, so the user
  knows it was a boundary substitution rather than a true in-grid interpolation.
- **Below-floor GUI surface: Settings default + pre-calc prompt** (chosen
  2026-06-19). Settings holds the persistent policy; the prompt fires only when
  sub-floor events are detected.
- **Default policy: `snap`** — keep current behavior unless the user opts into
  skip/manual/exam_average, so existing results don't silently change.
- **Floor threshold: kVp < 25 kV** (HVL table floor; carried from the crash-fix plan).
- **Anode angle is selected, never interpolated** (raised 2026-06-19). It is a
  discrete tube-target property (8°/11°); blending slices is physically meaningless.
  We keep the current implicit selection (first-occurrence dedup ≈ anode 11 where
  present, else 8) so in-grid results are unchanged (parity test enforces this).
  The real latent gap is that the device's anode angle isn't read from metadata —
  making anode angle an **explicit per-device input** (selection, not interpolation)
  is tracked as later work, **out of scope** here.

## Out of scope

- Making anode angle a first-class query/device parameter (read from metadata and
  **selected** per device). Interpolating *across* anode angle is explicitly a
  non-goal (discrete physical property).
- Biplane (tube A/B) handling (separate TO_DO).
- Re-deriving the polynomial `k_bs` model — it stays continuous and simply consumes
  the improved HVL.
- Changing the SQLite correction tables' contents.
