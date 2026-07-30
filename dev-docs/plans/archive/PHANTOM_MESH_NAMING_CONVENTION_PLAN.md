# Phantom mesh naming convention

**Status:** implemented (2026-07-23) — canonical stems on disk + persistent aliases.
**Date:** 2026-07-23

## Goals

1. **Scan-friendly prefixes** — age band visible in *filenames* (`ped_`, `adult_`, `demo_`).
   GUI order is **not** implied by prefix alone; rename PR uses an explicit sort key.
2. **Stable canonical stems** — Settings / catalog / STL basename are the new names only.
3. **Composable variants** — numbered bariatric series without long suffixes.
4. **Backward-compatible aliases** — old stems resolve to canonical files; aliases **persist**
   after the rename PR (dropping aliases later = SemVer **major**).
5. **Preserve upstream legacy names** — `adult_male` / `adult_female`, `junior_*`, `hudfrid`.

## Locked decisions (2026-07-23)

1. Keep `adult_male` / `adult_female` as-is.
2. Keep `junior_male` / `junior_female` as-is (upstream legacy; not under `ped_`).
3. Keep `hudfrid` as-is.
4. Bariatrics → `adult_bariatric_{sex}_{n}` with `n ∈ {1,2,3}`:
   - `_1` — abdomen-dominant class-II (BMI ~35–40)
   - `_2` — thicker neck/extremities
   - `_3` — even thicker neck/extremities
   Do **not** extend this line with `_4` for other habitus; new tokens instead.

## Pattern

```text
ped_{cohort}_{sex}              # preschool | 5y | 10y
adult_{habitus}_{sex}           # ecto | endo
adult_bariatric_{sex}_{n}       # n = 1|2|3
demo_{token}

# Permanent exceptions (never rename)
adult_male, adult_female
junior_male, junior_female
hudfrid
senior_male, senior_female      # already conforming; leave as-is
```

Reduced previews: `{stem}_reduced_1000t` (rename with the stem).

## Alias / migration strategy (review P0)

**Canonical files only on disk.** Do **not** keep dual STL copies of old and new stems.

1. `git mv` (or equivalent) full + reduced STLs to target stems — content unchanged ⇒ SHA-256 unchanged.
2. Maintain `HUMAN_MESH_ALIASES: old_stem → canonical_stem` in package code.
3. Single resolver `resolve_human_mesh_stem(stem) -> canonical_stem` used by:
   - `Phantom` full-res load
   - reduced / sparse path builders (`resolve_preview_mesh`, procedure plot suffix)
   - GUI: **canonicalize `state.human_mesh` on Settings build** before `ui.select` bind so
     saved old stems do not silently reset to `hudfrid`
4. `get_human_mesh_names()` / discovery lists **canonical on-disk stems only** (never alias keys).
5. Inventory: update **path** entries in `approved_asset_inventory.json` (hashes unchanged if
   content unchanged); regenerate `.md` via `render_asset_inventory.py --write`.

## Mapping (current → target)

| Current stem | Target stem | Notes |
|--------------|-------------|-------|
| `pediatric_preschool_male` | `ped_preschool_male` | |
| `pediatric_preschool_female` | `ped_preschool_female` | |
| `pediatric_5y_male` | `ped_5y_male` | |
| `pediatric_5y_female` | `ped_5y_female` | |
| `pediatric_10y_male` | `ped_10y_male` | |
| `pediatric_10y_female` | `ped_10y_female` | |
| `junior_*` | *(unchanged)* | Upstream legacy |
| `adult_male` / `adult_female` | *(unchanged)* | Baseline legacy |
| `adult_ectomorph_*` | `adult_ecto_*` | |
| `adult_endomorph_*` | `adult_endo_*` | |
| `bariatric_class2_{sex}` | `adult_bariatric_{sex}_1` | Abdomen-dominant class-II |
| `bariatric_class2_{sex}_thick_extremities` | `adult_bariatric_{sex}_2` | |
| `bariatric_class2_{sex}_extra_thick_extremities` | `adult_bariatric_{sex}_3` | |
| `senior_*` | *(unchanged)* | Already conforming |
| `hudfrid` | *(unchanged)* | |
| `cosmic_buddha` | `demo_cosmic_buddha` | |
| `steamboat_willie` | `demo_steamboat_willie` | |
| `ramesses_ii` | `demo_ramesses_ii` | GUI-hidden |

All `_reduced_1000t` companions rename with the stem (38 files for 19 renames).

## GUI

- **Labels required** for bariatric `_1/_2/_3` (and preferred for all clinical stems via a label map).
- **Sort key** (clinical): ped preschool → ped 5y → ped 10y → junior → adult_male/female →
  adult_ecto → adult_endo → adult_bariatric → senior → hudfrid; then demo section.
- Update `DEMO_HUMAN_MESHES`, `GUI_HIDDEN_HUMAN_MESHES`, `_DEMO_DISPLAY_LABELS`.

## Touch list (rename PR)

- `src/mypyskindose/phantom_data/*.stl` (+ keep `NOTICE_*.txt` filenames as-is; they document
  asset license, not stem)
- `scripts/phantom_gen/catalog_v1.json` entry keys + intents (`_shape_ref_*` unchanged; keep
  class-II / BMI wording in bariatric intents)
- `scripts/phantom_gen/fun_mesh_manifest.json` ids
- Package resolver + Phantom / preview / plot / Settings canonicalize
- Tests: `test_phantom_library_integration`, `test_phantom_gen_pipeline`, `test_demo_phantoms_integration`
- Docs: `AGENTS.md`, `FEATURE_INVENTORY.md`, `ADDITIONAL_PHANTOMS.md`, `CHANGELOG.md`,
  `dev-docs/index.md`, `TO_DO.md`, assessments that hardcode old stems
- Inventory path entries + render markdown

## Non-goals

- Mesh geometry changes
- Arms-at-sides (separate plan)
- Affine remeshing
- Renaming exceptions listed above
- Dropping aliases in the same PR
