# Plan: fix HVL-lookup crash on invalid / out-of-grid events

_Created 2026-06-13. Triggered by a dose calculation on the legacy Radimetrics CSV
(`cleaned example RDSR (old).csv`) aborting with `IndexError`._

## Symptom

Running a calculation crashes:

```
File ".../geom_calc.py", line 251, in fetch_and_append_hvl
    cast(pd.Series, hvl_data.loc[ ... ]).iloc[0]
IndexError: single positional indexer is out-of-bounds
```

## Root cause (measured)

`fetch_and_append_hvl` (`src/mypyskindose/geom_calc.py`) resolves each event's HVL
with an **exact-match** lookup against `table_data/hvl_tables/hvl_combined.csv`,
keyed by `(round(kVp), round(inherent_filtration, 1), filter_thickness_Cu,
round(filter_thickness_Al))`, then takes `.iloc[0]`. When no row matches, the
filtered Series is empty and `.iloc[0]` raises, aborting the **entire** run.

For this file, **710 of 712 events resolve fine**; the 2 failures are events with
**kVp ≈ 0.003** → `round()` = 0, below the table's 25 kV floor (table range
25–175 kV; `filtration_added_mmcu ∈ {0,0.1,0.2,0.3,0.4,0.6,0.9}`, `mmal ∈ {0,1}`).
So this specific crash is **invalid near-zero-kVp events** hitting an **unguarded
lookup**. (Cu/Al were in-grid here; genuinely off-grid filtration would fail the
same way — see [[#related]].)

Compounding: the `remove_invalid_rows` guard that would drop dead events
(a) checks `kVp == 0` **exactly** (so `0.003` is not caught), and (b) is applied
only on the RDSR path (`gui/helpers.load_rdsr`,
`helpers/read_and_normalize_rdsr_data`), **not** on the tabular path
(`gui/helpers.load_tabular`). Default is `false`.

## Fix plan

1. **Guard the lookup (stops the crash).** Never `.iloc[0]` on a possibly-empty
   result. If no exact row matches, fall back to nearest-neighbour (or linear
   interpolation) on the tabulated grid, clamped at the edges. This is the
   existing TO_DO "HVL interpolation/extrapolation for out-of-table filtration" —
   the crash makes it urgent and is the unifying fix.
2. **Handle invalid events.** Events with kVp below a physical/table floor
   (e.g. `< 20` kV, under the 25 kV grid) are not real exposures — drop or
   zero-dose them before the HVL/dose step, with a warning. Broaden
   `remove_invalid_rows` from `kVp == 0` to a small threshold, and **apply it on
   tabular loads** too (currently RDSR-only). Decide drop-vs-zero-dose.
3. **Fail soft, not hard.** If an event's HVL still can't be resolved after
   nearest/interpolation, skip that event's dose contribution with a per-event
   warning instead of aborting the whole calculation.
4. **Surface warnings** through the existing import/calc channel
   (`state.normalization_warnings` / calc status). Always report **how many
   events failed the lookup** (were substituted, clamped, or skipped) — a count
   plus the affected event indices — so the user knows the result excludes/altered
   some events. (Future work, [[#related]]: instead of silently choosing, offer
   the user options for below-floor-kVp events — ignore the event, enter a kVp
   manually, or use the exam's average kVp.)
5. **Tests.** Add a fixture/event with (a) kVp ≈ 0 and (b) off-grid filtration;
   assert the calc completes with warnings and **no `IndexError`**.

## Files

- `src/mypyskindose/geom_calc.py` — `fetch_and_append_hvl` (guard + nearest/interp)
- `src/mypyskindose/calculate_dose/calculate_dose.py` — call site / invalid-event handling
- `src/mypyskindose/gui/helpers.py` — `load_tabular` (apply invalid-row filter; surface warnings)
- `src/mypyskindose/helpers/read_and_normalize_rdsr_data.py` — keep RDSR path consistent
- `tests/unittests/` — regression test

## Decisions to confirm before implementing

- Nearest-neighbour vs (bi)linear interpolation for HVL — start with nearest +
  clamp (simplest, no crashes), upgrade to interpolation if accuracy warrants.
- Invalid-kVp threshold (20 vs 25 kV) and drop-vs-zero-dose.
- Whether `remove_invalid_rows` should default to `true` (silently dropping dead
  events is arguably correct, but changes existing behavior — keep opt-in but
  always guard the HVL lookup so it can't crash regardless of the toggle).

<a name="related"></a>
## Related

- TO_DO.md → "HVL interpolation/extrapolation for out-of-table filtration"
  (this plan subsumes/urgent-izes it).
- TO_DO.md → "User options for below-floor / unresolvable kVp events" — the
  interactive follow-up (ignore / manual kVp / exam-average kVp). This plan first
  makes the calc fail soft and report the affected count; that item adds the
  user-facing choice.
