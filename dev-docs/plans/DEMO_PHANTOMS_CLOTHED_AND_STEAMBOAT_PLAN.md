# Clothed Full-Body + Steamboat Demo Phantoms Plan

> **Status (2026-07-22):** Active v1 execution plan. Broader survey / Venus–David D1 backlog:
> [`FUN_DEMO_PHANTOMS_PLAN.md`](FUN_DEMO_PHANTOMS_PLAN.md). Clinical habitus:
> [`AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](AUTOMATED_PHANTOM_LIBRARY_PLAN.md).
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax. Mark a checkbox only after the step is fully done and verified.
>
> **Related:** [`ADDITIONAL_PHANTOMS.md`](../ADDITIONAL_PHANTOMS.md),
> [`references/CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md`](../references/CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md).
>
> **Review fold-in (2026-07-22):** Independent review **GO WITH NITS** applied — NiceGUI
> `{stem: label}` options dict; re-fix normals **after** Y-flip; face-up threshold tunable;
> fun-mode ≤20k face ceiling + `--require-trimesh`; `demo_phantoms` feature_doc_matrix row;
> validate full mesh only (not `_reduced_1000t`); Blender cap fallback acknowledged. Prior fold-ins:
> GUI options map; fill/cap + normals; dual inventory; scale order; torso overrides; Cosmic Buddha =
> standing; banner optional; mesh licenses ≠ `THIRD_PARTY_NOTICES.md`; named smoke RDSR; torso band
> = GUI `(0.20, 0.65)`; no `--allow-subsample` for shipping.

**Goal:** Ship four labeled **demo / non-clinical** phantoms — (1) Cosmic Buddha, (2) Petite Herculanaise,
(3) Ramesses II, (4) Steamboat Willie — each scaled and rotated into the MyPySkinDose PSD frame, decimated,
validated, and discoverable in the GUI.

**Architecture:** Reuse `scripts/phantom_gen/` (`transform_to_psd_frame.py`, `generate_reduced.py`,
`validate_phantom.py`). Add `ingest_fun_mesh.py` + `fun_mesh_manifest.json` that apply **per-mesh** Euler
orientation locked in the manifest, re-anchor with **`obj_y_up=False`**, **cap/fill open boundaries**,
**fix winding/normals (again after any Y-flip)**, decimate to shipping budget + `_reduced_1000t`, and
install into `phantom_data/` with NOTICE sidecars where required.

**Tech stack:** Python 3.11+, `numpy-stl`, `trimesh` (+ `fast-simplification` via `.[phantom-gen]`),
existing `Phantom` loader; Blender/MeshLab only for hole-fill when pure `trimesh` repair fails
(optional `repair_and_cap.py` fallback — large open statue bases often need this).

## Decision record (locked for this plan)

| Topic | Decision |
|-------|----------|
| Nude classical (Venus/David) | Out of scope here — D1 remains on `FUN_DEMO_PHANTOMS_PLAN.md` |
| Watertight | Hard gate; trimesh must be installed for ingest/validate (`wt is None` must **fail**, not pass) |
| Smoke RDSR | `src/mypyskindose/example_data/RDSR/siemens_axiom_example_procedure.dcm` |
| Steamboat source | Commons Cojocaru CC BY 4.0 primary; JoeBert Sketchfab CC-BY alternate; Quaternius only if both fail |
| Demo banner | Optional; help-page `(demo)` notes alone are enough |
| GUI labels timing | Accept raw stems in dropdown until Task 6, **or** land Task 6 Step 1 early after first mesh ships |
| NiceGUI mesh options | `{stem: display_label}` — **bound value = stem** (matches in-repo `ui.select` dict usage) |
| Feature matrix key | New top-level row `demo_phantoms` in `feature_doc_matrix.json` |
| Validate which STL | Run gates on the **full** `{id}.stl` only; do not require `validate_phantom` on `_reduced_1000t` (1000-face edge vs `>=1000` check) |

## Global constraints

- **Demo only:** GUI/docs label `(demo)` / non-clinical; never present as dosimetry reference phantoms.
- **Frame:** centimeters; head-first supine; `X` mid ≈ 0; **max Y ≈ 0** (back on table); **max Z ≈ 0** (crown).
- **Transform / scale order (critical):**  
  `raw → Euler rotate → uniform scale to height_cm → fill/cap → (optional pre-fix normals) →`  
  `PSD anchor with obj_y_up=False + explicit flip → **re-fix winding/normals** → decimate`  
  and **`--no-unit-detect`** when already scaled to cm (avoids double ×100 if span still looks “small”).  
  Do **not** call default `obj_y_up=True` on a pre-oriented STL.
- **Orientation:** Discover per mesh; lock `rotate_deg` + `height_axis` + `flip_y` in the manifest after
  `plot_setup` / Settings preview smoke.
- **`flip_y` → transform API (critical):** Manifest boolean maps to `transform_to_psd_frame` as:
  - `flip_y: true` → `force_flip_y=True` (CLI `--force-flip-y`)
  - `flip_y: false` → `force_flip_y=False` and `flip_y_if_needed=False` (CLI `--no-flip-y`)  
  Never rely on the asymmetric-extent heuristic alone for statues/cartoons.  
  **`force_flip_y` negates Y and reverses triangle handedness** — always re-run `fix_winding` /
  `fix_normals` **after** the PSD transform (and again after decimate if normals are regenerated).
- **Triangle budget:** full mesh **3k–8k** faces (hard ceiling **20k**). Fun-ingest /
  `--require-trimesh` validate mode must enforce **`1000 ≤ faces ≤ 20000`** (default clinical validator
  still allows up to 40k — do not use that ceiling for shipping demos). Always ship `{id}_reduced_1000t.stl`.
- **Watertight / open boundaries:** hard gate — **fill/cap** open loops **before** quadric decimation;
  repair until `validate_phantom.py` reports `watertight is True` (not `None`). Require `trimesh` installed
  for ingest/CI of these meshes. Large open pedestal/base loops may need optional `repair_and_cap.py`
  (Blender); if neither trimesh nor Blender can close the mesh, **drop that ID** under ship policy — do not
  weaken the watertight gate. **Never** pass `--allow-subsample` to `generate_reduced` /
  `decimate_to_target_faces` for shipping (tests/emergencies only).
- **Face-up supine (critical):** After PSD anchoring, the **anterior** (chest/face) must lie toward **−Y**
  and the **posterior** (back) at **max Y ≈ 0** (table). Statue/cartoon bboxes are often near-symmetric, so
  `flip_y_if_needed` is a **no-op** and can leave meshes **face-down**. Ingest must:
  1. Lock `flip_y` in the manifest after visual smoke (map as above).
  2. **Automated face-up gate** (fail validate if not met): in the superior **12%** Z band (from `z_max`
     toward feet), require `y_min_headband ≤ y_max − face_up_frac × thickness_y` with default
     **`face_up_frac = 0.55`** (manifest-overridable; tune if a thin-headed silhouette false-fails).
     Cosmic Buddha has **no head** — for that mesh only, apply the same rule to the superior **20%**
     robe/torso band, and record the exception + any `face_up_frac` override in provenance.
  3. If already-shipped demos are face-down, re-ingest with the locked flip and re-hash both STLs.
- **Normals:** ingest must run `trimesh.repair.fix_winding` / `fix_normals` **after** PSD transform
  (and after decimate when face normals are rebuilt).  
  **Automated outward-normal gate** in `validate_phantom.py` (required for fun ingest):
  cast rays from outside the bbox toward surface centroids (trimesh `RayMeshIntersector` is fine;
  embree not required); at each first hit, require `dot(n, ray_direction) < 0`. Fail if a majority of
  sample hits fail.
- **Anterior-beam smoke (required for every shipped mesh):** run `calculate_dose` (or equivalent GUI/CLI path)
  with settings `phantom.model=human`, `phantom.human_mesh={id}`, against  
  `src/mypyskindose/example_data/RDSR/siemens_axiom_example_procedure.dcm`.  
  Confirm entrance skin is on the anterior (−Y) side and exit on the posterior; wrong-side PSD → fix winding
  / `flip_y` and re-ingest. Do not log absolute paths or PHI; use the package-relative example only.
- **Habitus UI baselines:** GUI torso width uses `_TORSO_WIDTH_Z_FRACTION_RANGE = (0.20, 0.65)` in
  `gui/helpers.py` (from feet toward head) — **not** the clinical validate `head_ratio` 25–45% band.
  Demo silhouettes may make that band misleading. Manifest may include optional `torso_z_fraction_range`
  or `baseline_torso_width_cm`; Task 6 must wire those into `_cache_mesh_baseline_measurements`.
  Empty band does **not** crash the GUI (helpers catch and store `0.0`) but yields useless cm labels —
  set an override after first PSD-frame mesh if needed.
- **Cosmic Buddha limitation:** standing draped figure **missing head and hands** — expect odd habitus
  labels and a weaker “face” cue for face-up checks; still a valid draped full-body demo if smoke passes.
- **Downloads:** many museum/Cults pages need a browser login or interactive download — do **not** assume
  a stable unauthenticated `curl` URL. Save the retrieved file under `tmp/fun_phantoms/raw/{id}/` and record
  retrieval date + exact source page in provenance.
- **Scratch:** downloads only under `tmp/fun_phantoms/` (gitignored). Never commit raw multi‑MB museum dumps.
- **Licenses (mesh assets ≠ Python deps):**
  - **`dev-docs/THIRD_PARTY_NOTICES.md` is Python-package inventory only** (`check_licenses.py` / `uv.lock`).
    **Do not** regenerate it for shipping these STLs unless you also change Python dependencies.
  - Mesh credits go in `fun_phantom_provenance.md` + `phantom_data/NOTICE_{id}.txt` (BY / BY-SA required;
    CC0 → provenance note sufficient).
  - Update **`LICENSE_COMPLIANCE.md`** with a short “redistributed mesh assets” note (esp. Petite **CC BY-SA**:
    app code stays MIT; that STL derivative remains SA).
- **Branding:** stem `steamboat_willie` only — never “Mickey Mouse” / Disney affiliation.
- **Ship policy:** try all four; ship each that clears watertight + smoke. Do not block the release on shipping
  all four if one mesh cannot be repaired — document the blocker in provenance and continue.
  Discovery remains dynamic (`get_human_mesh_names()` globs `phantom_data/`); `DEMO_HUMAN_MESHES` is only for
  labels / tests of shipped stems.
- **SemVer:** shipping new assets + GUI labels → expect a **minor** bump when releasing.
- **Privacy:** for **each** of `{id}.stl` and `{id}_reduced_1000t.stl`, add SHA-256 entries in
  `approved_asset_inventory.json` with `purpose`, `reviewer`, `reviewed_on`; then
  `python scripts/render_asset_inventory.py --write`.
- **Cross-platform:** `pathlib` only; ingest must run on Windows/macOS/Linux.

## Locked meshes (this plan)

| # | Mesh ID | Source | License | Geometry notes | Suggested height |
|---|---------|--------|---------|----------------|------------------|
| 1 | `cosmic_buddha` | [Smithsonian 3D](https://3d.si.edu/object/3d/buddha-draped-robes-portraying-realms-desire:d8c62be8-4ebc-11ea-b77f-2e728ce88125) | **CC0** | Standing draped ~151 cm; **missing head/hands**; rotate to supine | ~151 cm (or scale to ~170) |
| 2 | `petite_herculanaise` | [Cults CC BY-SA](https://cults3d.com/en/3d-model/art/statue-of-a-woman-petite-herculanaise-at-the-louvre-paris) (prefer over MMF; re-check MMF [6356](https://www.myminifactory.com/object/3d-print-statue-of-a-woman-petite-herculanaise-at-the-louvre-paris-6356) if used) | **CC BY-SA** | Standing draped woman → rotate to supine; NOTICE | ~160–170 cm |
| 3 | `ramesses_ii` | [Commons STL](https://commons.wikimedia.org/wiki/File:Colossal_sculpture_of_Ramesses_II.stl) (Dejp3) | **CC BY 4.0** | Already lying; mainly scale + axis lock; NOTICE; proportions may look odd | Scale longest body axis to ~170–200 cm |
| 4 | `steamboat_willie` | [Commons STL](https://commons.wikimedia.org/wiki/File:Steamboat_Willie_3D_Model.stl) (Adrian Cojocaru); fallback JoeBert Sketchfab CC-BY ~5.6k tris | **CC BY 4.0** | Cartoon; NOTICE; trademark-safe labeling | ~120 cm |

**Out of scope here:** Venus/David (nude — see `FUN_DEMO_PHANTOMS_PLAN.md` D1), Lincoln bust, Popeye/Pooh,
Quaternius filler (only if Steamboat **and** JoeBert entirely fail).

---

## File map

| Path | Role |
|------|------|
| `tmp/fun_phantoms/` (gitignored) | Downloads + intermediates |
| `scripts/phantom_gen/fun_mesh_manifest.json` | URLs, licenses, attribution, locked `rotate_deg`, `height_cm`, `height_axis`, `flip_y`; optional `face_up_frac`, `torso_z_fraction_range`, `baseline_torso_width_cm` |
| `scripts/phantom_gen/ingest_fun_mesh.py` | Orient → scale → fill/cap → PSD transform (`--no-obj-y-up` + unit/flip flags) → **re-fix normals** → decimate → validate; optional `--preview-only` |
| `scripts/phantom_gen/transform_to_psd_frame.py` | Existing; must use `--no-obj-y-up` and explicit flip flags |
| `scripts/phantom_gen/generate_reduced.py` | Reuse `decimate_to_target_faces` / `--target-faces`; **no** `--allow-subsample` for shipping |
| `scripts/phantom_gen/validate_phantom.py` | Fun mode: frame + scale + faces ≤20k + watertight True + Phantom load + face-up + outward-normal |
| `scripts/phantom_gen/repair_and_cap.py` (optional) | Headless Blender fallback when trimesh hole-fill fails (large open bases) |
| `src/mypyskindose/phantom_data/{id}.stl` + `_reduced_1000t.stl` | Shipped meshes |
| `src/mypyskindose/phantom_data/NOTICE_*.txt` | BY / BY-SA sidecars |
| `dev-docs/references/fun_phantom_provenance.md` | Credits, retrieval dates, repair notes, face-up exceptions |
| `dev-docs/LICENSE_COMPLIANCE.md` | Short note on redistributed mesh assets (not Python deps) |
| `src/mypyskindose/gui/helpers.py` (+ settings/constants) | `get_human_mesh_options() -> dict[str, str]` as **`{stem: label}`**; torso overrides for demos |
| `tests/unittests/test_demo_phantoms_integration.py` | Or extend `test_phantom_library_integration.py` — discovery, load, PSD anchors |
| `AGENTS.md`, `ADDITIONAL_PHANTOMS.md`, `FEATURE_INVENTORY.md`, `CHANGELOG.md` | Lists + demo labeling |
| `dev-docs/feature_doc_matrix.json` | New row key **`demo_phantoms`** |
| `dev-docs/ui_copy.json`, `help_registry.json` | **Only if** adding a demo warning banner / new UI strings |
| `dev-docs/approved_asset_inventory.json` | Hash + human review for **both** full and `_reduced_1000t` STLs |

---

## Shared ingest workflow (every mesh)

1. Download into `tmp/fun_phantoms/raw/{id}/` (browser/login OK); record URL, license, retrieval date.
2. Discover orientation: try Eulers → `plot_setup` / Settings phantom preview / visual smoke → lock
   `rotate_deg` + `height_axis` + **`flip_y`** (`--preview-only` recommended during discovery).
   Confirm **face-up** (anterior toward −Y) before shipping.
3. Uniform-scale so the **height axis** span ≈ `height_cm`.
4. Fill/cap open boundaries (Blender `repair_and_cap` if trimesh fails). Optional pre-transform
   `fix_winding` / `fix_normals`.
5. PSD-anchor via `transform_to_psd_frame` with `obj_y_up=False`, `meters_to_cm_if_small=False`, and
   `force_flip_y` / `--no-flip-y` per locked `flip_y` → `tmp/fun_phantoms/psd/{id}.stl`.
6. **Re-fix winding/normals** after the transform (Y-flip reverses handedness).
7. Decimate to 3k–8k via `decimate_to_target_faces` (**no** `allow_subsample`) on a closed mesh;
   re-fix normals again if the decimator rebuilds face normals.
8. `generate_reduced.py` → `{id}_reduced_1000t.stl` (again, no `--allow-subsample`). Do **not** require
   `validate_phantom` on the reduced file.
9. `validate_phantom.py --require-trimesh` (fun mode) on the **full** mesh — anchors, scale (50–220 cm),
   faces ≤20k, Phantom load, **watertight is True**, face-up gate (`face_up_frac`), outward-normal gate.
   **Skip** clinical `--compare-affine`. After install, spot-check habitus cm labels; set manifest torso
   override if needed.
10. Anterior-beam entrance/exit smoke on
    `src/mypyskindose/example_data/RDSR/siemens_axiom_example_procedure.dcm`.
11. Install to `phantom_data/`, NOTICE if BY/SA, hash-pin **both** STLs, docs; GUI `(demo)` labels land in
    Task 6 (raw stems acceptable until then).

Example CLI (after scaffolding; flags illustrate the contract ingest must apply):

```bash
source .venv/bin/activate
python scripts/phantom_gen/ingest_fun_mesh.py \
  --id cosmic_buddha \
  --input tmp/fun_phantoms/raw/cosmic_buddha/source.stl \
  --rotate-deg 90,0,0 \
  --height-cm 151 \
  --flip-y \
  --target-faces 6000 \
  --out-dir tmp/fun_phantoms/psd
# ingest internally:
#   scale to cm → fill/cap → transform_to_psd_frame(
#     obj_y_up=False, meters_to_cm_if_small=False, force_flip_y=True)
#   → fix_winding/fix_normals → decimate → validate --require-trimesh
# equivalent one-off transform flags: --no-obj-y-up --no-unit-detect --force-flip-y
```

Use `--no-flip-y` (manifest `flip_y: false`) when the locked Euler already yields face-up.

---

### License inventory (answer)

| Inventory | Update for these meshes? | Why |
|-----------|--------------------------|-----|
| `dev-docs/THIRD_PARTY_NOTICES.md` | **No** (unless Python deps also change) | Generated from installed packages / `uv.lock` via `check_licenses.py` — not mesh assets |
| `phantom_data/NOTICE_*.txt` + `fun_phantom_provenance.md` | **Yes** for BY / BY-SA (Petite, Ramesses, Steamboat); CC0 Cosmic Buddha in provenance | Attribution + SA terms for redistributed STLs |
| `LICENSE_COMPLIANCE.md` | **Yes — short section** | Document that MIT app code can ship CC BY/SA mesh binaries with NOTICE sidecars; SA applies to those mesh derivatives |

Do **not** run `python scripts/check_licenses.py --write-notices` solely because meshes shipped.

---

### Task 1: Manifest + ingest scaffolding

**Files:**
- Create: `scripts/phantom_gen/fun_mesh_manifest.json`
- Create: `scripts/phantom_gen/ingest_fun_mesh.py`
- Modify: `scripts/phantom_gen/README.md`, `validate_phantom.py` (face-up + outward-normal + `--require-trimesh` + ≤20k faces)
- Test: `tests/unittests/test_phantom_gen_pipeline.py` (extend) or new unit test for ingest helpers

**Interfaces:**
- Consumes: `transform_to_psd_frame(..., obj_y_up=False, meters_to_cm_if_small=False when pre-scaled,
  force_flip_y=… / flip_y_if_needed=False)`, `decimate_to_target_faces(..., allow_subsample=False)`,
  `validate`, trimesh repair helpers
- Produces: CLI `ingest_fun_mesh.py --id --input --rotate-deg --height-cm --target-faces --out-dir`
  `[--flip-y|--no-flip-y] [--preview-only]`;
  manifest schema with `id`, `source_url`, `license`, `attribution`, `height_cm`, `height_axis`,
  `rotate_deg`, `flip_y`, `target_faces`, `phase`, optional `face_up_frac`, `torso_z_fraction_range`,
  `baseline_torso_width_cm`

- [ ] **Step 1: Write `fun_mesh_manifest.json`** with rows for all four IDs (placeholder `rotate_deg` /
  `flip_y` until discovery locks them). Include Steamboat fallback URL notes and optional
  `face_up_frac` / torso override fields.

- [ ] **Step 2: Implement `ingest_fun_mesh.py`** — load STL/OBJ/PLY; Euler degrees; scale height axis;
  fill/cap; transform with `obj_y_up=False`, no unit auto-detect after scale, and `force_flip_y` /
  `--no-flip-y` from `--flip-y` / manifest; **re-fix winding/normals after transform**; decimate
  **without** subsample (re-fix normals if needed); write `{id}.stl`; invoke validate with
  `--require-trimesh` (face-up + outward-normal + watertight True + faces ≤20k). Support
  `--preview-only` (extents / faces / no install).

- [ ] **Step 3: Extend `validate_phantom.py`** — add `--require-trimesh` / fun mode that:
  - fails when `watertight in (None, False)`
  - enforces face ceiling **≤20000**
  - runs face-up band check (`face_up_frac`, default 0.55; superior 12% or 20% for headless)
  - runs outward-normal ray check (`RayMeshIntersector`)

- [ ] **Step 4: Document** download friction, scale order, post-flip normal fix, `--no-obj-y-up` /
  `--no-unit-detect` / `--force-flip-y` / `--no-flip-y`, `--require-trimesh`, and “never
  `--allow-subsample` for shipping” in `scripts/phantom_gen/README.md`.

- [ ] **Step 5: Add a small unit test** that a tiny synthetic STL through ingest lands with
  `y_max`/`z_max` ≈ 0 and passes face-up when given a known orientation (or mock transform path). Run:
  `pytest tests/unittests/test_phantom_gen_pipeline.py -v` (or new test file).

- [ ] **Step 6: Commit** scaffolding only (no binary museum STLs).

---

### Task 2: Cosmic Buddha (`cosmic_buddha`)

**Files:**
- Create: `tmp/fun_phantoms/raw/cosmic_buddha/` (gitignored)
- Create: `src/mypyskindose/phantom_data/cosmic_buddha.stl`, `cosmic_buddha_reduced_1000t.stl`
- Modify: `fun_mesh_manifest.json` (lock rotation + `flip_y`), `fun_phantom_provenance.md`,
  `dev-docs/approved_asset_inventory.json` (**both** STLs)

- [x] **Step 1: Download** Smithsonian CC0 mesh (browser OK); confirm object page still says CC0.
  Retrieved 2026-07-22 from the ~7.5 MB / ~150k-face Wikimedia Commons mirror
  (`File:Cosmic-buddha-laser-scan-150k (Smithsonian Institution).stl`); CC0 confirmed via the Commons
  API (`LicenseShortName=CC0`). SI object slug corrected to `…realms-existence…`.

- [x] **Step 2: Discover + lock** upright→supine rotation + `flip_y`; ingest ~151–170 cm / ~6k faces + 1000t.
  Note missing head/hands in provenance; use superior-20% face-up band and tune `face_up_frac` if needed.
  Locked `rotate_deg=[0,0,0]`, `height_axis=z`, `height_cm=151`, `flip_y=false`, `face_up_band_frac=0.20`
  (raw axes already map to PSD; anterior relief on raw −Y). Ingested to 6000 faces + `_reduced_1000t`.

- [x] **Step 3: Validate** full mesh (`--require-trimesh`, face-up + normals) + anterior-beam smoke on
  `siemens_axiom_example_procedure.dcm` + `plot_setup` smoke. Repair robe holes / open base (Blender
  fallback OK). If unrepairable, document and skip shipping this ID.
  All gates PASS (watertight True, ≤20k faces, face-up, outward normals 200/200); anterior-beam smoke
  entrance on −Y (PSD ≈ 16.3 mGy); `plot_setup` builds cleanly. Raw mesh already watertight — no cap needed.

- [x] **Step 4: Install** + provenance (CC0 / SI credit encouraged) + inventory hash **for both**
  `cosmic_buddha.stl` and `cosmic_buddha_reduced_1000t.stl` with review fields; run
  `python scripts/render_asset_inventory.py --write`. Done; `dev-docs/references/fun_phantom_provenance.md`
  created; both STLs hash-pinned; inventory Markdown regenerated.

- [x] **Step 5: Commit** shipped STLs + provenance/inventory/docs deltas for this mesh.

---

### Task 3: Petite Herculanaise (`petite_herculanaise`)

**Files:**
- Create: shipped STLs + `NOTICE_petite_herculanaise.txt`
- Modify: manifest, provenance, `LICENSE_COMPLIANCE.md` (mesh-assets note), inventory (**both** STLs)

- [ ] **Step 1: Download** from Cults (license **CC BY-SA** explicit; login/browser OK). If using MMF
  instead, record the license panel and abort if NC.

- [ ] **Step 2: Ingest** with upright→supine rotation + locked `flip_y`; NOTICE sidecar (attribution + SA
  note that **mesh derivatives** stay SA-compatible; app code remains MIT).

- [ ] **Step 3: Validate** full mesh + anterior-beam smoke on `siemens_axiom_example_procedure.dcm` + GUI smoke.

- [ ] **Step 4: Install** + provenance + inventory both STLs + short LICENSE_COMPLIANCE redistributed-asset note.

- [ ] **Step 5: Commit.**

---

### Task 4: Ramesses II (`ramesses_ii`)

**Files:**
- Create: shipped STLs + `NOTICE_ramesses_ii.txt`
- Modify: manifest, provenance, inventory (**both** STLs)

- [ ] **Step 1: Download** Commons CC BY 4.0 STL (~24 MB raw stays in `tmp/`).

- [ ] **Step 2: Ingest** — already lying; focus scale + PSD-frame axes; lock rotation + `flip_y` that puts
  crown at max Z and back at max Y. Accept colossal proportions if smoke passes.

- [ ] **Step 3: Validate** full mesh + anterior-beam smoke on `siemens_axiom_example_procedure.dcm`.

- [ ] **Step 4: Install** + NOTICE (Dejp3 / CC BY 4.0) + provenance + inventory both STLs.

- [ ] **Step 5: Commit.**

---

### Task 5: Steamboat Willie (`steamboat_willie`)

**Files:**
- Create: shipped STLs + `NOTICE_steamboat_willie.txt`
- Modify: manifest, provenance, inventory (**both** STLs)

- [ ] **Step 1: Download** Commons Cojocaru (**CC BY 4.0**). If watertight repair fails, try JoeBert
  Sketchfab CC-BY (~5.6k tris) before any Quaternius filler.

- [ ] **Step 2: Branding** — stem/UI `steamboat_willie` / “Steamboat Willie (demo)” only. Provenance: US PD
  1928 design + CC BY on 3D mesh + trademark caution.

- [ ] **Step 3: Ingest** (~120 cm); NOTICE for BY; fill/cap + post-flip normal fix before/after decimate;
  lock `flip_y`.

- [ ] **Step 4: Validate** full mesh + anterior-beam smoke on `siemens_axiom_example_procedure.dcm`.

- [ ] **Step 5: Install** + provenance + inventory both STLs.

- [ ] **Step 6: Commit.**

---

### Task 6: Product surfacing, tests, docs

**Files:**
- Modify: `src/mypyskindose/gui/helpers.py` — add `get_human_mesh_options() -> dict[str, str]` as
  **`{stem: display_label}`** for **all** meshes (e.g. `{"adult_female": "Adult Female",
  "cosmic_buddha": "Cosmic Buddha (demo)"}`); keep `get_human_mesh_names()` for discovery/tests;
  **wire** optional `torso_z_fraction_range` / `baseline_torso_width_cm` from
  `fun_mesh_manifest.json` (or a small shipped sidecar) into `_cache_mesh_baseline_measurements`
- Modify: `gui/constants.py` / `tabs/settings.py` to use that options dict for `ui.select`
  (`HUMAN_MESHES = get_human_mesh_options()`)
- Create or extend: `tests/unittests/test_demo_phantoms_integration.py` **or**
  `test_phantom_library_integration.py`
- Modify: `AGENTS.md`, `ADDITIONAL_PHANTOMS.md`, `FEATURE_INVENTORY.md`, `CHANGELOG.md`,
  `CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md`, `docs/source/gui_help/` (+ `sync_gui_help.py`),
  `dev-docs/feature_doc_matrix.json` (**add `demo_phantoms` row**)
- Conditionally: `dev-docs/ui_copy.json`, `help_registry.json` **if** adding a visible demo warning banner

**Interfaces:**
- NiceGUI: `ui.select(options={"cosmic_buddha": "Cosmic Buddha (demo)", ...}, ...).bind_value(state, "human_mesh")`
  — **dict keys are values (stems)**; dict values are display labels. Do **not** invert to label→stem
  (that binds the label string into `state.human_mesh` and breaks STL paths / persisted settings).
- File discovery stays dynamic via glob; do not hardcode required file presence for unshipped demos.
- Raw stem labels between Task 2 and Task 6 are acceptable; prefer landing Step 1 soon after the first
  mesh ships if multiple commits land over days.

- [ ] **Step 1: Implement `{stem: label}` options map** + `DEMO_HUMAN_MESHES` frozenset of **actually
  shipped** stems for `(demo)` suffix / tests. Title-case clinical stems (e.g. `Adult Female`) so demos
  are not the only pretty labels. Add a unit assertion that every options key is a discovered stem.

- [ ] **Step 2: Wire torso overrides** from manifest for shipped demos into GUI baseline measurement
  (override band or explicit `baseline_torso_width_cm`).

- [ ] **Step 3 (optional product):** When `state.human_mesh in DEMO_HUMAN_MESHES`, show a non-clinical
  warning banner; if so, register strings in `ui_copy.json` / `help_registry.json`. Help-page notes alone
  are acceptable without a banner.

- [ ] **Step 4: Integration tests** for shipped IDs only (files exist, discovered, PSD anchors via
  `Phantom(..., phantom_dim=...)`). Parametrize only meshes that actually shipped.

- [ ] **Step 5: Run** targeted pytest — expect PASS.

- [ ] **Step 6: Docs / help** — AGENTS, ADDITIONAL, FEATURE_INVENTORY, add **`demo_phantoms`** to
  `feature_doc_matrix.json`, provenance, CHANGELOG (minor when released). Help: demo / non-clinical;
  Steamboat trademark caution; SA note for Petite; Cosmic Buddha missing head/hands note.

- [ ] **Step 7: Run gates** — `check_doc_freshness`; `check_sensitive_content --require-approved-assets`;
  `check_ui_copy` / `check_help_registry` if banner/strings added. **Do not** `--write-notices` for meshes alone.

- [ ] **Step 8: Commit.**

---

### Task 7: Close-out

- [ ] **Step 1:** Mark Tasks 2–5 complete only for meshes that shipped; note any failed mesh + reason in
  provenance (do not pretend it shipped).

- [ ] **Step 2:** Update `dev-docs/TO_DO.md` and `dev-docs/index.md` status for this plan.

- [ ] **Step 3:** When v1 of this plan is done, archive under `dev-docs/plans/archive/` and fix `index.md`
  paths in the same PR. Leave Venus/David / Phase 2 cartoons on `FUN_DEMO_PHANTOMS_PLAN.md` until decided.

---

## Acceptance criteria

1. Each **shipped** ID appears in `get_human_mesh_names()`, loads with `Phantom(..., phantom_dim=...)`, and
   works in `plot_setup` / dose calc without crash.
2. `_reduced_1000t` present; **full** mesh ≤ 20k faces (prefer ≤ 8k), enforced by fun-mode validate;
   shipped from a **closed** mesh via real quadric decimation (**not** `--allow-subsample`).
3. Fun ingest used **`obj_y_up=False`** + correct scale order; per-mesh `rotate_deg` + **`flip_y`** locked and
   mapped to `force_flip_y` / `--no-flip-y`; normals re-fixed **after** flip; face-up validate gate passes.
4. Watertight is **True** (`--require-trimesh`); outward-normal ray gate passed; anterior-beam entrance/exit
   smoke passed on `siemens_axiom_example_procedure.dcm`.
5. NOTICE sidecars for Petite (BY-SA), Ramesses (BY), Steamboat (BY); Cosmic Buddha provenance OK under CC0.
6. **`THIRD_PARTY_NOTICES.md` unchanged** unless Python deps also changed; `LICENSE_COMPLIANCE.md` notes
   redistributed mesh assets.
7. GUI `ui.select` uses **`{stem: label}`** options; demo torso overrides wired when needed; Steamboat not
   marketed as Disney Mickey.
8. Inventory entries for **both** full and reduced STLs include hash + `purpose` / `reviewer` / `reviewed_on`.
9. CHANGELOG Unreleased notes the addition; SemVer minor on release; **`demo_phantoms`** row in
   `feature_doc_matrix.json`.
10. If a demo banner was added, `ui_copy` / help registry updated; otherwise help-page demo notes suffice.

## Out of scope

- Venus de Milo / Michelangelo’s David (nude classical — separate D1 decision).
- Lincoln bust / other Smithsonian busts.
- Popeye / book Pooh / Betty / Tintin.
- Clinical MPFB catalog rows.
- Shipping undecimated museum scans or enabling Git LFS for raw dumps.
- Regenerating `THIRD_PARTY_NOTICES.md` for mesh-only changes.
- Requiring `validate_phantom` on `_reduced_1000t` (inventory + generate_reduced connectedness check suffice).
