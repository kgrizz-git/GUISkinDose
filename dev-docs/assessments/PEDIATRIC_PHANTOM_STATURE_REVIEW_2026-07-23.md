# Pediatric phantom stature review (2026-07-23)

## Question

Are superior–inferior (SI) heights of the shipped `pediatric_5y_*` and
`pediatric_10y_*` phantoms appropriate for those ages?

## Pre-relabel measurements (before option-2 keep-all)

| Mesh (then) | height_z (cm) | CDC ~P50 | Ratio |
|-------------|--------------:|---------:|------:|
| `pediatric_5y_male` | 77.6 | ~109 | ~0.71 |
| `pediatric_5y_female` | 74.0 | ~108 | ~0.69 |
| `pediatric_10y_male` | 107.8 | ~138 | ~0.78 |
| `pediatric_10y_female` | 101.1 | ~138 | ~0.73 |

**Verdict then:** not age-appropriate for median stature (~20–30% short).

## Resolution (option 2 — keep all meshes)

User chose keep-all relabel (2026-07-23):

| New stem | Content | height_z (cm) | CDC ~P50 |
|----------|---------|--------------:|---------:|
| `pediatric_preschool_*` | former short 5y | 77.6 / 74.0 | (toddler/preschool placeholder) |
| `pediatric_5y_*` | former 10y | 107.8 / 101.1 | ~109 / ~108 |
| `pediatric_10y_*` | new MPFB regenerate | 139.4 / 136.9 | ~138 |

Catalog macros for new 10y: male `height=0.48` `age=0.22`; female `height=0.55`
`age=0.24`. Expect bands tightened around these SI ranges.

## Arms-at-sides (separate, additive only)

Feasible via MPFB `default` rig + custom pose JSON
(`scripts/phantom_gen/poses/arms_at_sides_default_fk.json`). Spike only under
`tmp/phantom_gen/arms_at_sides_spike/` — do **not** replace existing A-pose STLs.
