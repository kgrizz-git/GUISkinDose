# Bariatric extra-thick extremities generation (2026-07-23)

## Goal

Keep abdomen-dominant `bariatric_class2_{male,female}` and existing
`_thick_extremities` variants unchanged. Add additive
`_extra_thick_extremities` IDs with stronger neck / arm / leg / head MPFB detail
targets (near the 0.9–0.95 ceiling).

## Catalog IDs

- `bariatric_class2_male_extra_thick_extremities`
- `bariatric_class2_female_extra_thick_extremities`

Same class-II abdomen macro/detail base as the prior rows; limb/neck/head targets
raised vs `_thick_extremities` (e.g. male `measure-neck-circ-incr` 0.70 → 0.95,
`measure-upperarm-circ-incr` 0.75 → 0.95). `shape_metric` remains `null` (limb bulk
confounds `abdomen_bulk` vs affine control).

## Band extents (cm, approximate)

| Variant | full width_x | mid-thigh thick_y | mid-calf thick_y | head/neck top 12% width_x |
|---------|-------------:|------------------:|-----------------:|--------------------------:|
| male base | 117.5 | 18.0 | 10.9 | 17.7 |
| male thick | 124.8 | 22.1 | 13.4 | 19.2 |
| male extra | 128.5 | 23.7 | 14.3 | 19.9 |
| female base | 101.0 | 18.9 | 10.9 | 16.8 |
| female thick | 107.5 | 23.1 | 13.8 | 18.1 |
| female extra | 111.3 | 24.6 | 14.8 | 18.8 |

Step base→thick is larger than thick→extra (MPFB targets saturate near 1.0).
Original class-II and thick SHA-256 hashes were verified unchanged after install.

## Result

Full + `_reduced_1000t` STLs installed under `phantom_data/`; inventory hashes
approved 2026-07-23.
