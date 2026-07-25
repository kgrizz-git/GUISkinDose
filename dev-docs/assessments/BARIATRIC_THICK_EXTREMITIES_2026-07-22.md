# Bariatric thick-extremities generation (2026-07-22)

## Goal

Keep abdomen-dominant `bariatric_class2_{male,female}` unchanged and ship additive
`_thick_extremities` variants with thicker arms, legs, neck, and head via MPFB detail targets.

## Targets (additive on class-II abdomen set)

- Arms: `measure-upperarm-circ-incr`, L/R `*-upperarm-fat-incr`, `*-lowerarm-fat-incr`,
  `*-upperarm-scale-horiz-incr`, `*-lowerarm-scale-horiz-incr`
- Legs: `measure-thigh-circ-incr`, `measure-calf-circ-incr`, L/R upper/lower leg fat + horiz scale
- Neck: `measure-neck-circ-incr`, `neck-scale-horiz-incr`, `neck-double-incr`
- Head: `head-scale-horiz-incr`, `head-scale-depth-incr`

## Validation note

`abdomen_bulk` vs affine-control fails for thick-extremity rows because limb bulk raises the
thigh reference in that metric. Catalog `shape_metric` is therefore `null` for these IDs;
extents + face-up + Phantom load still gate shipping. Original class-II rows keep
`abdomen_bulk` anti-balloon checks.

## Result

Both male and female thick-extremity STLs + `_reduced_1000t` installed; original class-II
SHA-256 hashes unchanged.
