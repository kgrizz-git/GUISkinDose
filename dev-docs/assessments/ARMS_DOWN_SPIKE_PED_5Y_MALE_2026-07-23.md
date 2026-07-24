# Arms-down spike smoke (2026-07-23)

## Spike id

`ped_5y_male_arms_down` (tmp only — not installed)

- Catalog: `tmp/phantom_gen/arms_down_spike/spike_catalog.json`
- Pose: `scripts/phantom_gen/poses/arms_down_default_fk.json` (retuned)
- Generator: `mpfb_generate.py` optional `"pose": "arms_down_default_fk"`

## Pose retune (same day)

First spike over-adducted (hands near groin) and pitched hands anterior (hip `ty` inflated).
Sweep locked **`upperarm01` X = −0.40**, then tightened to **Z = ±0.40** / `upperarm02` Z = ±0.12 (mild clavicle/shoulder; lowerarm zeroed).

| Metric | A-pose | First spike | Z±0.30 | Z±0.36 | **Z±0.40 (current)** |
|--------|-------:|------------:|-------:|-------:|---------------------:|
| full width `dx` | 68.2 | 33.0 | 43.5 | 38.6 | **35.4** |
| hand–hip gap | — | ~0 | ~6.5 | ~4.3 | **~2.8 cm** |
| hand AP vs torso | — | ~−12 | ~−2.8 | ~−2.7 | **~−2.7 cm** |

Face-up / validate **PASS**. Equal-aspect silhouettes:
`tmp/phantom_gen/arms_down_spike/silhouette_side_by_side_equal.png`,
`silhouette_arms_down_equal.png`, `silhouette_arms_down_lateral_equal.png`.

## Notes

- Full-width drop vs A-pose is still mostly “arms no longer outstretched,” not torso squash.
- Retune keeps a small gap beside the hips and pulls hands back in AP.
- Ready for optional further micro-tune, then Task 2 unit coverage + Task 3 full clinical `_arms_down` wave.

## Follow-up

Full clinical `_arms_down` wave shipped 2026-07-23 (23 meshes + reduced); plan archived.
