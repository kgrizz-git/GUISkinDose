# Pediatric 5y male orientation fix (2026-07-22)

## Finding

Shipped `pediatric_5y_male.stl` differed from the validated MPFB catalog output under
`tmp/phantom_gen/`. The shipped mesh passed a coarse face-up heuristic but the superior
headband did **not** rest near the table (`y_max` of the head band ≈ −6.3 cm), unlike
`pediatric_5y_female` and a fresh catalog regenerate (head band ≈ −0.4 cm). That made the
child look face-down / head-pitched in the Settings preview.

## Fix

- Regenerated via `run_catalog.py --only pediatric_5y_male` (Blender/MPFB) and reinstalled
  full + `_reduced_1000t` STLs; inventory hashes updated.
- `run_catalog.process_entry` now runs `face_up_ok` after transform and fails closed if the
  mesh is face-down. Per-entry `force_flip_y` override is supported (default `true`).

## Result

- Fresh mesh: face-up **PASS**; headband Y ≈ `[−14.6, −0.36]`; anchors OK.
