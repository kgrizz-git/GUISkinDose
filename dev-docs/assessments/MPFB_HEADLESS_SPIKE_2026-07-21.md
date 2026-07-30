# MPFB Headless Phantom Spike — Phase 0 Gate Result

**Date:** 2026-07-21  
**Status:** **PASS**  
**Plan:** [`dev-docs/plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](../plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md)

## Environment

| Component | Version / path |
|---|---|
| Blender | 5.2.0 LTS (`/opt/homebrew/bin/blender`) |
| MPFB | 2.0.16 (`bl_ext.blender_org.mpfb`, build 20260613) |
| Isolated config | `tmp/blender_user/` via `BLENDER_USER_RESOURCES` (host prefs untouched) |
| System asset pack | Not required for basemesh + macro/detail targets |

## Pipeline exercised

```text
spike_catalog.json → blender -b -P mpfb_generate.py → OBJ
  → transform_to_psd_frame.py (OBJ Y-up remap, m→cm, re-anchor)
  → validate_phantom.py (+ shape metrics vs uniform-height affine control)
```

## Spike meshes (tmp only; not shipped)

| ID | Height (cm) | Width (cm) | Thickness (cm) | head_ratio | abdomen_bulk | Basic validate |
|---|---:|---:|---:|---:|---:|---|
| `spike_adult_male` | 157.3 | 100.2 | 41.8 | 0.201 | 35.01 | PASS |
| `spike_pediatric` (age≈0.07) | 77.6 | 50.3 | 21.0 | 0.483 | 9.08 | PASS |
| `spike_heavy` (weight 0.95 + stomach) | 174.7 | 114.0 | 48.9 | 0.176 | 41.17 | PASS |

## Anti-balloon shape gates

Controls = uniform-height scale of `spike_adult_male` (preserves adult ratios).

| Candidate | Metric | Candidate | Control | Margin | Result |
|---|---|---:|---:|---:|---|
| pediatric | `head_ratio` | 0.483 | 0.201 | +5% | **PASS** (~2.4× adult ratio) |
| heavy | `abdomen_bulk` | 41.17 | 38.88 | +5% | **PASS** (~+5.9%) |

## Lessons for Phase 1+

1. Blender `wm.obj_export` is **Y-up** — transform must remap `(x,y,z)→(x,z,y)` before PSD anchoring.
2. Very young macros with `proportions ≠ 0.5` can request missing `uncommonproportions` baby targets; keep `proportions: 0.5` for age≈0.07 or ensure target files exist.
3. Affine controls for shape tests must use **uniform** scale (not anisotropic bbox match), or ratios are meaningless.
4. `head_ratio` must be head/torso radial bulk, not “top 20% height fraction” (tautology).
5. Heavy abdomen margin is thin (~6%); strengthen stomach/detail targets in the real catalog if needed.

## Gate decision

Phase 0 **PASS**. Proceed to Phase 1 (full `catalog_v1.json` + orchestrator). Do **not** fall back to shipping affine-stretched existing STLs.
