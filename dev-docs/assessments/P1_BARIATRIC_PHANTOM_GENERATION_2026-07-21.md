# P1 Bariatric Phantom Generation — Phase 3 Result

**Date:** 2026-07-21  
**Status:** **PASS** (tmp outputs; installed in Phase 4)  
**Plan:** [`../plans/AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](../plans/AUTOMATED_PHANTOM_LIBRARY_PLAN.md)

## Outputs

Under `tmp/phantom_gen/p1/`:

| ID | Height (cm) | Width | Thickness | abdomen_bulk | vs affine (+5%) | Validate |
|---|---:|---:|---:|---:|---|---|
| `bariatric_class2_male` | 174.7 | 117.5 | 49.4 | 43.02 | 38.88 → **+10.6%** | PASS |
| `bariatric_class2_female` | 160.3 | 101.0 | 42.6 | 36.14 | 33.15 → **+9.0%** | PASS |

Reduced `*_reduced_1000t.stl` generated for both.

## Ordering vs endomorph

| Sex | endomorph width | bariatric width | endomorph thickness | bariatric thickness |
|---|---:|---:|---:|---:|
| male | 111.6 | 117.5 | 46.9 | 49.4 |
| female | 97.0 | 101.0 | 40.3 | 42.6 |

Bariatric exceeds endomorph on width and thickness for both sexes. No affine shipping fallback used.

## Notes

Catalog macros/detail targets from Phase 2 endomorph tuning (already abdomen-weighted) were
sufficient for class-II rows without further softening. Honest labeling: parametric CG habitus,
not CT-grade Class III medical fidelity.
