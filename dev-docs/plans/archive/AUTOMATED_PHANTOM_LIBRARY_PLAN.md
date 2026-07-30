# Automated Phantom Library Plan

> **Status:** **Completed** (Phases 0–4; archived 2026-07-30). Further phantom expansion and
> custom-mesh import remain in `dev-docs/TO_DO.md` / `ADDITIONAL_PHANTOMS.md`.
>
> **For agentic workers:** Execute task-by-task. Prefer headless automation over GUI tools.
> Steps use checkbox (`- [ ]`) syntax. Mark a checkbox only after the step is fully done and verified.
>
> **Supersedes:** `MAKEHUMAN_PHANTOM_GENERATION_MASTER_PLAN.md` and Phases 1–5
> (`MAKEHUMAN_PHASE1_SETUP_AND_TESTING.md` … `MAKEHUMAN_PHASE5_INTEGRATION_VALIDATION.md`),
> archived under `dev-docs/plans/archive/`.
>
> **Shape policy (2026-07-21):** v1 requires **true shape variety** (parametric phenotype /
> regional morph targets), **not** global affine stretching of existing STLs. Uniform
> scale-only meshes are explicitly out of scope for shipped phantoms.

**Goal:** Expand the shipped human-mesh library with full-body pediatric and adult habitus
variants that have **distinct body shapes** (not ballooned clones), match MyPySkinDose
coordinate conventions, and are produced by an agent-runnable pipeline.

**Architecture:**

1. **Primary generator:** MakeHuman-compatible parametric humans via **MPFB2 inside Blender
   headless** (`blender -b -P …`), using `HumanService.create_human(macro_detail_dict=…)`
   plus detail targets (stomach, torso, limbs, etc.), then bake → transform → binary STL.
2. **Catalog:** machine-readable phenotype presets (0–1 macros + named detail targets), not
   cm/kg GUI fiction and not `scale_lat/ap/lon` of shipped meshes.
3. **Shared post-process:** re-anchor to MyPySkinDose frame, decimate, validate, install,
   privacy admission.
4. **Affine stretch of existing STLs is forbidden for shipped assets.** It may exist only as
   a developer debug tool, never as a catalog `method`.

**Tech stack:** Blender 4.2+ with MPFB2 addon + MakeHuman system assets; Python 3.11+;
`numpy-stl` / `trimesh`; existing `Phantom` loader; pytest; privacy asset admission.

## Global constraints

- **True shape variety:** each catalog row must change **regional proportions**, not only
  overall size. Pediatric rows must increase head-to-body ratio vs junior/adult bases;
  heavy/bariatric rows must preferentially enlarge abdomen/torso vs limbs.
- **Full-body only** — never crop head or limbs; keep watertight closed surfaces.
- **Coordinate frame:** centimeters; head-first supine; `X` lateral centered at 0;
  `Y` AP with **max Y ≈ 0** (posterior/back on table); `Z` S–I with **max Z ≈ 0**
  (crown of head); body extends to negative Y and Z.
- **Scale anchors:** `_apply_human_scale` uses `(mid_X, max_Y, max_Z)` — preserve meaningful
  max Y / max Z after generation.
- **Automation first:** critical path is `blender -b` + Python scripts. No interactive GUI
  click-paths in the runbook after the one-time environment install.
- **Rough medical realism:** parametric MakeHuman/MPFB anatomy is acceptable; CT-grade
  segmentation is not required for v1. Extreme Class III bariatric may still look “CG”;
  prefer honest labeling over fake medical fidelity.
- **Privacy:** every new/changed `.stl` needs hash-pinned review in
  `dev-docs/approved_asset_inventory.json` before commit.
- **License:** document MPFB/MakeHuman AGPL asset provenance and redistribution notes in
  catalog metadata and `ADDITIONAL_PHANTOMS.md` before shipping.
- **File layout:** flat `src/mypyskindose/phantom_data/{name}.stl` (+ `{name}_reduced_1000t.stl`).
- **Macro units:** catalog stores MakeHuman/MPFB **0–1 phenotype weights** (and optional
  detail target weights). Measured cm extents are **validation expectations**, not generator
  inputs. Age years map as `age_macro ≈ years / 70`.

---

## Why not affine morph?

| Approach | Shape realism | Agent fit |
|---|---|---|
| Global X/Y/Z scale of `adult_*` / `junior_*` | Low — same silhouette, inflated/shrunk | Easy, but **rejected for v1 ship** |
| MPFB/MakeHuman macros + detail targets | Medium — distinct age/sex/habitus silhouettes | Good **if** headless spike passes |
| CT segmentation (TCIA) | High for that patient | Poor automation; optional later |
| ICRP 145 meshes | High reference quality | License/redistribution gate |

Existing shipped extents (validation reference only):

| Mesh | Faces | X half-span (cm) | Y span (cm) | Z height (cm) |
|---|---:|---:|---:|---:|
| `junior_male` | 26756 | 68.5 | 23.2 | 137.9 |
| `junior_female` | 26756 | 62.8 | 20.7 | 128.5 |
| `adult_male` | 26756 | 91.7 | 30.4 | 175.1 |
| `adult_female` | 26756 | 77.8 | 27.9 | 160.6 |

---

## Target catalog (v1)

| ID | Intent | Macro sketch (0–1) | Detail emphasis | Priority |
|---|---|---|---|---|
| `pediatric_5y_male` | ~5 y boy | age≈0.07, gender≈1, height low, weight mid, muscle low | larger head / shorter limbs targets if available | P0 |
| `pediatric_5y_female` | ~5 y girl | age≈0.07, gender≈0, … | same | P0 |
| `pediatric_10y_male` | ~10 y boy | age≈0.14, gender≈1, … | intermediate head/limb | P0 |
| `pediatric_10y_female` | ~10 y girl | age≈0.14, gender≈0, … | intermediate | P0 |
| `adult_ectomorph_male` | thin adult | age≈0.36 (~25 y), gender≈1, weight low, muscle low–mid, height mid | narrow waist/chest | P0 |
| `adult_ectomorph_female` | thin adult | age≈0.36, gender≈0, weight low, … | narrow waist; modest hips | P0 |
| `adult_endomorph_male` | heavy adult | weight high, muscle mid, … | stomach/torso up | P0 |
| `adult_endomorph_female` | heavy adult | weight high, … | stomach + hips | P0 |
| `bariatric_class2_male` | BMI ~35–40 | weight near max + stomach/torso detail max | abdomen-dominant | P1 |
| `bariatric_class2_female` | BMI ~35–40 | same pattern female | abdomen + hips | P1 |

**Deferred:** mesomorph duplicates of `adult_*`, Class I/III rows, senior habitus (existing
`senior_*` already cover age).

Exact macro/detail numbers live in `scripts/phantom_gen/catalog_v1.json` and are tuned after
the spike against measured extents and **shape metrics** (below).

---

## Shape-acceptance metrics (required)

Validation must fail a “uniform balloon” result. For each mesh compute from vertices:

| Metric | Definition | Pediatric expect | Heavy/bariatric expect |
|---|---|---|---|
| `height_z` | `z_max - z_min` | ~108–145 cm by age | ~158–177 cm |
| `width_x` | `x_max - x_min` | smaller than junior/adult | larger than adult |
| `thickness_y` | `y_max - y_min` | smaller | larger |
| `head_ratio` | height of superior 20% of Z-span / `height_z` | **greater** than adult_male | ≈ adult |
| `abdomen_bulk` | mean \|radial\| extent in mid-torso Z band vs mid-thigh Z band | n/a | abdomen_bulk **>** thigh_bulk × 1.15 |
| `nonuniformity` | stdev of per-band width along Z / mean width | pediatric and heavy rows must differ from a pure XYZ-scaled adult control | same |

Also keep standard checks: watertight, anchors, face count, `Phantom` load.

Compare each new mesh to a **synthetic affine control** (scale `adult_male` or `junior_male`
to the same height/width/thickness). Ship only if shape metrics differ from that control
beyond thresholds in the validate config (proves we did not just stretch).

---

## Pipeline

```
catalog_v1.json ──► blender -b -P mpfb_generate.py ──► raw OBJ/STL (tmp)
                            │
                            ▼
                   transform_to_psd_frame.py
                   (m→cm, supine, re-anchor, decimate)
                            │
                            ▼
                   validate_phantom.py  (+ shape metrics vs affine control)
                            │
                            ▼
                   install → phantom_data/ + reduced_1000t + pytest + privacy
```

Working outputs: gitignored `tmp/phantom_gen/`.

---

## File map

| Path | Role |
|---|---|
| `scripts/phantom_gen/README.md` | Env install + agent runbook |
| `scripts/phantom_gen/catalog_v1.json` | Phenotype macros + detail targets + expected metrics |
| `scripts/phantom_gen/mpfb_generate.py` | Blender/MPFB script: create human → bake → export |
| `scripts/phantom_gen/transform_to_psd_frame.py` | Units, orientation, anchors, optional decimate |
| `scripts/phantom_gen/validate_phantom.py` | Anchors + watertight + **shape metrics** |
| `scripts/phantom_gen/generate_reduced.py` | `*_reduced_1000t.stl` |
| `scripts/phantom_gen/run_catalog.py` | Orchestrate Blender → transform → validate → install |
| `scripts/phantom_gen/affine_control.py` | Build stretch-only control mesh for anti-balloon tests (not shipped) |
| `tests/unittests/test_phantom_gen_pipeline.py` | Transform/validate unit tests |
| `tests/unittests/test_phantom_library_integration.py` | Discovery/load when STLs present |
| `tmp/phantom_gen/` | Build outputs |

---

## Phase 0 — Headless MPFB spike (gate)

**Stop the project if this phase fails.** Do not implement a catalog of affine morphs as a
substitute without an explicit user decision to lower the realism bar.

### Task 0.1: Environment

- [x] Install Blender ≥ 4.2 (CLI on `PATH` as `blender` or document absolute path in
      `scripts/phantom_gen/env.local.json` — gitignore that file).
- [x] Install MPFB2 addon into that Blender (Blender Extensions or sideload).
- [x] Install MakeHuman **system asset pack** required by MPFB.
  - Comment: **Not required** for basemesh + macro/detail spike (confirmed 2026-07-21).
- [x] Document exact versions in `scripts/phantom_gen/README.md`.

**Verify:** `blender -b --python-expr "import bpy; print(bpy.app.version_string)"` works.

### Task 0.2: Minimal create + export

- [x] Write `mpfb_generate.py` that, under `blender -b -P`:
  1. Enables/imports MPFB
  2. Calls `HumanService.create_human(macro_detail_dict={...})` for one adult male
  3. Applies shape keys / bakes modifiers so geometry is real
  4. Deletes helpers/clothes/rig if present
  5. Exports Wavefront OBJ or STL to `tmp/phantom_gen/{id}.obj`
- [x] Confirm the script exits 0 with no display server (CI-like: `DISPLAY=` unset on Linux
      if available; on macOS note any known headless limits).

**Verify:** output mesh exists and has >1000 faces.

### Task 0.3: Frame transform + validate

- [x] Implement `transform_to_psd_frame.py`:
  - Detect units (MPFB/MakeHuman often meters or dm — measure and convert to **cm**)
  - Remap Blender OBJ **Y-up** → Z-up height; re-anchor PSD frame
  - Re-anchor: `x_mid=0`, `y_max=0`, `z_max=0`
  - Optional decimate to 5k–12k faces (full-body; do not crop) — deferred; spike keeps full topo
  - Write binary STL
- [x] Implement `validate_phantom.py` with anchor/watertight/`Phantom` load checks.
- [x] Spike STL must pass validate.

### Task 0.4: Prove non-affine shape change

- [x] Generate spike **pediatric** (low age macro) and spike **heavy** (high weight + stomach).
- [x] Build affine controls matched by **uniform height** from adult spike.
- [x] Assert pediatric `head_ratio` > affine-control `head_ratio` (margin +5%).
- [x] Assert heavy `abdomen_bulk` > affine-control `abdomen_bulk` (margin +5%).
- [x] Gate result: **PASS** — see `dev-docs/assessments/MPFB_HEADLESS_SPIKE_2026-07-21.md`.

---

## Phase 1 — Catalog + orchestrator

### Task 1.1: `catalog_v1.json`

- [x] Encode all P0/P1 rows with:
  - `id`, `macros` (age/gender/muscle/weight/height/proportions/…),
  - `detail_targets` (list of `{name, value}`),
  - `expect` (height/width/thickness ranges + shape metric thresholds),
  - `license: "mpfb-makehuman-assets"`.
- [x] No `base_mesh` + `scale` fields for shipped rows.

### Task 1.2: `run_catalog.py`

- [x] For each id: Blender generate → transform → validate → report.
- [x] `--only <id>`, `--install`, exit non-zero on failure.
- [x] Unit tests for transform/validate that do not require Blender (synthetic meshes).
- [x] Blender/MPFB tests marked `@pytest.mark.blender_mpfb` and skipped when Blender/MPFB
      absent (document how to run locally).

---

## Phase 2 — Generate P0 shapes

- [x] Generate four pediatric + four adult ectomorph/endomorph STLs into `tmp/`.
- [x] Tune catalog macros until extent **and** shape-metric checks pass.
- [x] Generate reduced 1k variants.
- [x] Record final macro values in catalog (reproducibility).

**Verify:** pediatric heights increase 5y → 10y → junior; ectomorph width < adult < endomorph;
all pass anti-balloon checks. — **PASS** (`dev-docs/assessments/P0_PHANTOM_GENERATION_2026-07-21.md`).

---

## Phase 3 — P1 bariatric

- [x] Generate class-II pair with abdomen-dominant targets.
- [x] If MPFB cannot produce abdomen_bulk above threshold without mesh artifacts, document
      limitation and either soften class-II targets or stop — **do not** substitute XYZ scale.
      Comment: **PASS** without softening — see `P1_BARIATRIC_PHANTOM_GENERATION_2026-07-21.md`.
- [x] Reduced variants + validate.

---

## Phase 4 — Integrate

- [x] Install passing STLs into `src/mypyskindose/phantom_data/`.
- [x] Integration tests: discovery, load, anchors, scale hook smoke.
- [x] Optional dose smoke on one pediatric + one heavy mesh (example RDSR, `psd > 0`).
- [x] Update `AGENTS.md` mesh list, `CHANGELOG.md`, `ADDITIONAL_PHANTOMS.md` license note.
- [x] Privacy admission for every new binary.
- [x] Semver: **minor** when meshes ship. (`25.2.0`)

---

## Phase 5 — Only if MPFB spike fails

User must choose one:

1. Lower realism bar (re-enable affine morph plan) — requires explicit approval.
2. Spike alternate sources (ICRP redistribution, licensed XCAT, TCIA+Slicer) with the same
   transform/validate/shape-metric harness.
3. Hybrid: commit hand-exported MHM/MPFB meshes once, keep headless transform/validate only
   (weaker reproducibility).

---

## Success criteria

1. Headless MPFB spike PASS (Phase 0) with documented versions.
2. All v1 catalog STLs generated from phenotype targets (not affine stretch).
3. Every shipped mesh beats matched affine controls on the relevant shape metrics.
4. Full-body, watertight, MyPySkinDose anchors, discoverable in GUI, reduced variants present.
5. Docs + privacy inventory updated; MakeHuman GUI plans remain archived.

## Agent operating notes

- Activate project venv for Python validation; use Blender’s Python only inside `-P` scripts.
- Keep intermediates in `tmp/phantom_gen/`.
- Prefer tuning **catalog phenotype values** over weakening shape-metric thresholds.
- If Blender/MPFB tests fail, stop and report — do not silently fall back to stretching.
- Commit only when the user asks; include STLs + inventory + scripts + catalog together.

## Semver / changelog impact

- Plan/docs-only: `[Unreleased]` Changed note (already present); no version bump.
- Shipping new parametric phantoms: **minor** release + Feature changelog entry.
