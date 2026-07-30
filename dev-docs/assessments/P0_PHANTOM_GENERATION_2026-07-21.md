# P0 Phantom Generation — Phase 2 Result

**Date:** 2026-07-21  
**Status:** **PASS** (tmp only; not yet installed into `phantom_data/`)  
**Plan:** [`../plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](../plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md)

## Outputs

All under gitignored `tmp/phantom_gen/p0/`:

- 8 full-resolution P0 STLs + matching `*_reduced_1000t.stl`
- MPFB shape refs `_shape_ref_adult_{male,female}.stl` (validation only)
- `report.json` from `run_catalog.py --priority P0`

## Measured extents (PSD frame, cm)

| ID | Height | Width | Thickness | head_ratio | abdomen_bulk | Validate |
|---|---:|---:|---:|---:|---:|---|
| `pediatric_5y_male` | 77.6 | 50.3 | 21.0 | 0.483 | 9.08 | PASS |
| `pediatric_5y_female` | 74.0 | 47.4 | 20.2 | 0.507 | 8.19 | PASS |
| `pediatric_10y_male` | 107.8 | 68.2 | 28.3 | 0.308 | 18.45 | PASS |
| `pediatric_10y_female` | 101.1 | 62.8 | 25.4 | 0.314 | 16.53 | PASS |
| `adult_ectomorph_male` | 161.6 | 99.1 | 41.5 | — | — | PASS |
| `adult_ectomorph_female` | 145.7 | 85.1 | 33.7 | — | — | PASS |
| `adult_endomorph_male` | 168.5 | 111.6 | 46.9 | — | 40.36 | PASS |
| `adult_endomorph_female` | 155.3 | 97.0 | 40.3 | — | 34.40 | PASS |
| `_shape_ref_adult_male` | 157.3 | 100.2 | 41.8 | 0.201 | 35.01 | REF |
| `_shape_ref_adult_female` | 145.6 | 88.4 | 35.3 | 0.210 | 30.11 | REF |

Shipped juniors (ordering reference): `junior_male` height ≈ 137.9 cm; `junior_female` ≈ 128.5 cm.

## Ordering / anti-balloon gates

| Check | Result |
|---|---|
| 5y → 10y → junior height (both sexes) | PASS |
| ectomorph width < MPFB adult ref < endomorph (both sexes) | PASS |
| ectomorph thickness < endomorph (both sexes) | PASS |
| Pediatric `head_ratio` > uniform-height affine control (+5%) | PASS |
| Endomorph `abdomen_bulk` > gender-matched affine control (+5%) | PASS (male ≈+7.6%, female ≈+7.1%) |

## Tuning notes

1. Initial endomorph stomach-only targets failed the +5% abdomen margin; strengthened with
   `stomach-pregnant-incr`, `stomach-tone-decr`, torso scale-up, and waist/hip circumference targets.
2. Female candidates must compare against `_shape_ref_adult_female` (male ref inflated the control
   abdomen and falsely failed female endomorphs).
3. Ectomorph weight-only macros did not beat neutral width (arm span dominates); added torso/waist
   scale-down detail targets.
4. Final macros/detail weights are recorded in `scripts/phantom_gen/catalog_v1.json`.

## Next

Phase 3 (P1 bariatric) then Phase 4 install + privacy admission + integration tests.
