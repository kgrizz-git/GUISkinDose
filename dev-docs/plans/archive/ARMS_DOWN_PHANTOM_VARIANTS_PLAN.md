# Arms-down phantom variants plan

> **Status:** Complete (2026-07-23). Archived under `dev-docs/plans/archive/`.

> **For agentic workers:** Execute task-by-task. Prefer additive catalog rows; never
> overwrite existing A-pose STLs. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Ship **additive** human-mesh variants with arms down by the torso (table-side
clinical pose) without replacing current A-pose meshes.

**Architecture:** Extend `scripts/phantom_gen/mpfb_generate.py` to optionally add the
MPFB `default` FK rig, apply a curated pose JSON, bake pose as rest, then continue the
existing bake → PSD transform → validate → install path. New catalog ids append
`_arms_down` to the canonical clinical stem.

**Tech stack:** Blender + MPFB (existing `BLENDER_USER_RESOURCES`),
`scripts/phantom_gen/poses/arms_down_default_fk.json`, catalog_v1.json, privacy inventory.

## Locked decisions (2026-07-23)

1. **Suffix:** `_arms_down` (e.g. `ped_5y_male_arms_down`).
2. **Scope:** **all clinical** meshes, including legacy (`adult_male` / `adult_female`,
   `junior_*`, `senior_*`, `hudfrid` via MPFB re-create where needed) — **not** demos.
3. **Additive only** — never replace A-pose stems.
4. **Spike first** — one clinical id smoke in `tmp/` before full catalog wave.

## Global constraints

- Pose must keep face-up / PSD anchors; validate with existing gates.
- Legacy upstream binaries are not riggable in place: arms-down twins are **MPFB
  regenerates** (macros approximating stature/habitus) + pose, new stems only.
- SemVer: **minor** when first `_arms_down` meshes ship.

## Clinical stem checklist (A-pose base → `_arms_down`)

| Base (canonical) | Arms-down id |
|------------------|--------------|
| `ped_preschool_male/female` | `…_arms_down` |
| `ped_5y_male/female` | `…_arms_down` |
| `ped_10y_male/female` | `…_arms_down` |
| `junior_male/female` | `…_arms_down` (MPFB approx) |
| `adult_male/female` | `…_arms_down` (MPFB approx) |
| `adult_ecto_*` / `adult_endo_*` | `…_arms_down` |
| `adult_bariatric_{sex}_{1,2,3}` | `…_arms_down` |
| `senior_male/female` | `…_arms_down` (MPFB approx) |
| `hudfrid` | `hudfrid_arms_down` (MPFB approx) |

Demos (`demo_*`) — out of scope.

## Legacy MPFB approx macros (catalog)

| Arms-down id | Notes (macros in `catalog_v1.json`) |
|--------------|-------------------------------------|
| `junior_male_arms_down` | age 0.22, height 0.48 (~ped_10y male stature) |
| `junior_female_arms_down` | age 0.22, height 0.45 |
| `adult_male_arms_down` / `hudfrid_arms_down` | age 0.36, height 0.55 (neutral adult male family) |
| `adult_female_arms_down` | age 0.36, height 0.5 |
| `senior_male_arms_down` | age 0.72, height 0.52 |
| `senior_female_arms_down` | age 0.72, height 0.48 |

These are **not** binary clones of the legacy STLs; they match approximate SI stature for
table-side posing.

## Pose lock (spike)

`arms_down_default_fk.json`: `upperarm01` X=−0.40, Z=±0.40; `upperarm02` Z=±0.12.
Hand–hip gap ~2.8 cm on `ped_5y_male_arms_down`. Assessment:
[assessments/ARMS_DOWN_SPIKE_PED_5Y_MALE_2026-07-23.md](../../assessments/ARMS_DOWN_SPIKE_PED_5Y_MALE_2026-07-23.md).

---

## Tasks

### Task 1: Spike / smoke (one clinical)

- [x] Lock suffix `_arms_down` + all-clinical scope (this plan).
- [x] Generate `ped_5y_male_arms_down` to `tmp/phantom_gen/arms_down_spike/`.
- [x] Transform + validate; compare band widths vs A-pose sibling.
- [x] Tune `arms_down_default_fk.json` (less adduction + negative upperarm X for AP); spike hip `ty` matches A-pose.
- [x] Record metrics: [assessments/ARMS_DOWN_SPIKE_PED_5Y_MALE_2026-07-23.md](../../assessments/ARMS_DOWN_SPIKE_PED_5Y_MALE_2026-07-23.md).

### Task 2: Generator plumbing

- [x] Backup `mpfb_generate.py` under gitignored `tmp/backups/` (during spike).
- [x] Catalog optional `"pose": "arms_down_default_fk"` (file under `poses/`).
- [x] Pose apply path in `mpfb_generate.py` (rig → set_pose → apply as rest).
- [x] Unit-test: pose flag accepted; missing pose file fails clearly.

### Task 3: Full clinical catalog wave

- [x] Add `_arms_down` rows for every clinical base above (clone macros/details; set pose).
- [x] Expect: narrower `width_x` than A-pose sibling; keep `height_z`; `shape_metric` often `null`.
- [x] Legacy approx macros: document chosen MPFB macros for junior/adult/senior/hudfrid twins.

### Task 4: Install + inventory + GUI

- [x] Generate + reduced; inventory path entries; labels + sort (each `_arms_down` after sibling).
- [x] CHANGELOG, AGENTS, FEATURE_INVENTORY, tests, Settings preview smoke.

## Non-goals

- Replacing A-pose meshes
- Demo `_arms_down`
- Full animation / IK / Rigify
