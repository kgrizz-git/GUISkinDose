# Clothed Full-Body + Steamboat Demo Phantoms Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax. Mark a checkbox only after the step is fully done and verified.
>
> **Related:** [`ADDITIONAL_PHANTOMS.md`](../ADDITIONAL_PHANTOMS.md),
> [`references/CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md`](../references/CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md),
> broader candidate survey / nude classical backlog:
> [`FUN_DEMO_PHANTOMS_PLAN.md`](FUN_DEMO_PHANTOMS_PLAN.md) (Venus/David remain D1-gated there).
> Clinical habitus expansion remains [`AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](AUTOMATED_PHANTOM_LIBRARY_PLAN.md).
>
> **Assessment fold-in (2026-07-22):** Incorporates agreed items from
> `tmp/20260722_105000_demo_phantoms_plan_assessment.md` (GUI options map, fill/cap + normals, dual inventory,
> scale order; torso overrides without crash claim; Cosmic Buddha = standing; banner optional; mesh licenses ≠
> `THIRD_PARTY_NOTICES.md`).

**Goal:** Ship four labeled **demo / non-clinical** phantoms — (1) Cosmic Buddha, (2) Petite Herculanaise,
(3) Ramesses II, (4) Steamboat Willie — each scaled and rotated into the MyPySkinDose PSD frame, decimated,
validated, and discoverable in the GUI.

**Architecture:** Reuse `scripts/phantom_gen/` (`transform_to_psd_frame.py`, `generate_reduced.py`,
`validate_phantom.py`). Add `ingest_fun_mesh.py` + `fun_mesh_manifest.json` that apply **per-mesh** Euler
orientation locked in the manifest, re-anchor with **`obj_y_up=False`**, **cap/fill open boundaries**,
**fix winding/normals**, decimate to shipping budget + `_reduced_1000t`, and install into `phantom_data/`
with NOTICE sidecars where required.

**Tech stack:** Python 3.11+, `numpy-stl`, `trimesh`, existing `Phantom` loader; Blender/MeshLab only for
hole-fill when pure `trimesh` repair fails (optional `repair_and_cap.py` fallback).

## Global constraints

- **Demo only:** GUI/docs label `(demo)` / non-clinical; never present as dosimetry reference phantoms.
- **Frame:** centimeters; head-first supine; `X` mid ≈ 0; **max Y ≈ 0** (back on table); **max Z ≈ 0** (crown).
- **Transform / scale order (critical):**  
  `raw → Euler rotate → uniform scale to height_cm → PSD anchor with obj_y_up=False`  
  and **`--no-unit-detect`** when already scaled to cm (avoids double ×100 if span still looks “small”).  
  Do **not** call default `obj_y_up=True` on a pre-oriented STL.
- **Orientation:** Discover per mesh; lock `rotate_deg` + `height_axis` in the manifest after `plot_setup` smoke.
- **Triangle budget:** full mesh **3k–8k** faces (hard ceiling **20k**); always ship `{id}_reduced_1000t.stl`.
- **Watertight / open boundaries:** hard gate — **fill/cap** open loops before quadric decimation; repair until
  `validate_phantom.py` passes. (`generate_reduced` may fall back to triangle subsample on simplify failure —
  that is not an acceptable shipping outcome.)
- **Face-up supine (critical):** After PSD anchoring, the **anterior** (chest/face) must lie toward **−Y** and the **posterior** (back) at **max Y ≈ 0** (table). Statue/cartoon bboxes are often near-symmetric, so `transform_to_psd_frame`’s `flip_y_if_needed` heuristic is a **no-op** and can leave meshes **face-down**. Ingest must:
  1. Lock an explicit `flip_y: true|false` (or `rotate_deg` that includes a 180° about Z) in the manifest after visual smoke.
  2. Fail validate unless an anterior tip check passes (e.g. head-band `y_min` clearly more negative than posterior contact; or optional nose landmark).
  3. Prefer `--no-flip-y` + manifest-controlled flip rather than relying on the asymmetric-extent heuristic.
  If already-shipped demos are face-down, re-ingest with the locked flip and re-hash both STLs.
- **Normals:** ingest must run `trimesh.repair.fix_winding` / `fix_normals` (or equivalent); validate should
  include an automated outward-normal sanity check where practical; **anterior-beam entrance/exit smoke** on a
  trusted example RDSR for every shipped mesh (wrong-side PSD → fix winding).
- **Habitus UI baselines:** demo silhouettes may make the default 25–45% Z torso band misleading. Manifest may
  include optional `torso_z_fraction_range` or `baseline_torso_width_cm`. Empty band does **not** crash the GUI
  (helpers catch and store `0.0`) but yields useless cm labels — fix after first PSD-frame mesh if needed.
  Cosmic Buddha is a **standing** draped figure (missing head/hands), not seated.
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
| 1 | `cosmic_buddha` | [Smithsonian 3D](https://3d.si.edu/object/3d/buddha-draped-robes-portraying-realms-desire:d8c62be8-4ebc-11ea-b77f-2e728ce88125) | **CC0** | Standing draped ~151 cm → rotate to supine | ~151 cm (or scale to ~170) |
| 2 | `petite_herculanaise` | [Cults CC BY-SA](https://cults3d.com/en/3d-model/art/statue-of-a-woman-petite-herculanaise-at-the-louvre-paris) (prefer over MMF; re-check MMF [6356](https://www.myminifactory.com/object/3d-print-statue-of-a-woman-petite-herculanaise-at-the-louvre-paris-6356) if used) | **CC BY-SA** | Standing draped woman → rotate to supine; NOTICE | ~160–170 cm |
| 3 | `ramesses_ii` | [Commons STL](https://commons.wikimedia.org/wiki/File:Colossal_sculpture_of_Ramesses_II.stl) (Dejp3) | **CC BY 4.0** | Already lying; mainly scale + axis lock; NOTICE; proportions may look odd | Scale longest body axis to ~170–200 cm |
| 4 | `steamboat_willie` | [Commons STL](https://commons.wikimedia.org/wiki/File:Steamboat_Willie_3D_Model.stl) (Adrian Cojocaru); fallback JoeBert Sketchfab CC-BY ~5.6k tris | **CC BY 4.0** | Cartoon; NOTICE; trademark-safe labeling | ~120 cm |

**Out of scope here:** Venus/David (nude — see `FUN_DEMO_PHANTOMS_PLAN.md` D1), Lincoln bust, Popeye/Pooh, Quaternius filler (only if Steamboat entirely fails).

---

## File map

| Path | Role |
|------|------|
| `tmp/fun_phantoms/` (gitignored) | Downloads + intermediates |
| `scripts/phantom_gen/fun_mesh_manifest.json` | URLs, licenses, attribution, locked `rotate_deg`, `height_cm`, `height_axis`; optional `torso_z_fraction_range` / `baseline_torso_width_cm` |
| `scripts/phantom_gen/ingest_fun_mesh.py` | Orient → scale → fill/cap → fix normals → `--no-obj-y-up` (+ `--no-unit-detect` if pre-scaled) → decimate → validate; optional `--preview-only` |
| `scripts/phantom_gen/transform_to_psd_frame.py` | Existing; must use `--no-obj-y-up` |
| `scripts/phantom_gen/generate_reduced.py` | Reuse `decimate_to_target_faces` / `--target-faces` |
| `scripts/phantom_gen/validate_phantom.py` | Frame + scale + faces + watertight + Phantom load; prefer outward-normal sanity check |
| `scripts/phantom_gen/repair_and_cap.py` (optional) | Headless Blender fallback when trimesh hole-fill fails |
| `src/mypyskindose/phantom_data/{id}.stl` + `_reduced_1000t.stl` | Shipped meshes |
| `src/mypyskindose/phantom_data/NOTICE_*.txt` | BY / BY-SA sidecars |
| `dev-docs/references/fun_phantom_provenance.md` | Credits, retrieval dates, repair notes |
| `dev-docs/LICENSE_COMPLIANCE.md` | Short note on redistributed mesh assets (not Python deps) |
| `src/mypyskindose/gui/helpers.py` (+ settings/constants) | `get_human_mesh_options() -> dict[str, str]` display→stem for **all** human meshes |
| `tests/unittests/test_demo_phantoms_integration.py` | Or extend `test_phantom_library_integration.py` — discovery, load, PSD anchors |
| `AGENTS.md`, `ADDITIONAL_PHANTOMS.md`, `FEATURE_INVENTORY.md`, `CHANGELOG.md` | Lists + demo labeling |
| `dev-docs/ui_copy.json`, `help_registry.json` | **Only if** adding a demo warning banner / new UI strings |
| `dev-docs/approved_asset_inventory.json` | Hash + human review for **both** full and `_reduced_1000t` STLs |

---

## Shared ingest workflow (every mesh)

1. Download into `tmp/fun_phantoms/raw/{id}/`; record URL, license, retrieval date.
2. Discover orientation: try Eulers → `plot_setup` / Settings phantom preview / visual smoke → lock
   `rotate_deg` + `height_axis` + **`flip_y`** (`--preview-only` recommended during discovery).
   Confirm **face-up** (anterior toward −Y) before shipping.
3. Uniform-scale so the **height axis** span ≈ `height_cm`.
4. Fill/cap open boundaries; `fix_winding` / `fix_normals`.
5. `transform_to_psd_frame … --no-obj-y-up --no-unit-detect` (already cm) → `tmp/fun_phantoms/psd/{id}.stl`.
6. Decimate to 3k–8k via `decimate_to_target_faces` (must succeed on a closed mesh — do not ship subsample fallback).
7. `generate_reduced.py` → `{id}_reduced_1000t.stl`.
8. `validate_phantom.py` — anchors, scale (50–220 cm), face count, Phantom load, watertight, outward-normal sanity.
   **Skip** clinical `--compare-affine`. After install, spot-check habitus cm labels; set manifest torso override if needed.
9. Anterior-beam entrance/exit smoke on example RDSR.
10. Install to `phantom_data/`, NOTICE if BY/SA, hash-pin **both** STLs, docs, GUI `(demo)` label via unified options map.

Example CLI (after scaffolding):

```bash
source .venv/bin/activate
python scripts/phantom_gen/ingest_fun_mesh.py \
  --id cosmic_buddha \
  --input tmp/fun_phantoms/raw/cosmic_buddha/source.stl \
  --rotate-deg 90,0,0 \
  --height-cm 151 \
  --target-faces 6000 \
  --out-dir tmp/fun_phantoms/psd
```

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
- Modify: `scripts/phantom_gen/README.md`, optionally `validate_phantom.py`
- Test: `tests/unittests/test_phantom_gen_pipeline.py` (extend) or new unit test for ingest helpers

**Interfaces:**
- Consumes: `transform_to_psd_frame(..., obj_y_up=False, meters_to_cm_if_small=False when pre-scaled)`,
  `decimate_to_target_faces`, `validate`, trimesh repair helpers
- Produces: CLI `ingest_fun_mesh.py --id --input --rotate-deg --height-cm --target-faces --out-dir`
  `[--preview-only]`;
  manifest schema with `id`, `source_url`, `license`, `attribution`, `height_cm`, `height_axis`,
  `rotate_deg`, `flip_y`, `target_faces`, `phase`, optional `torso_z_fraction_range` / `baseline_torso_width_cm`

- [ ] **Step 1: Write `fun_mesh_manifest.json`** with rows for all four IDs (placeholder `rotate_deg` until
  discovery locks them). Include Steamboat fallback URL notes and optional torso override fields.

- [ ] **Step 2: Implement `ingest_fun_mesh.py`** — load STL/OBJ/PLY; Euler degrees; scale height axis;
  fill/cap + fix winding/normals; transform with `obj_y_up=False` and no unit auto-detect after scale;
  decimate; write `{id}.stl`; invoke validate. Support `--preview-only` (extents / faces / no install).

- [ ] **Step 3: Document** download paths, scale order, and `--no-obj-y-up` / `--no-unit-detect` in
  `scripts/phantom_gen/README.md`.

- [ ] **Step 4: Add a small unit test** that a tiny synthetic STL through ingest lands with
  `y_max`/`z_max` ≈ 0 when given a known orientation (or mock transform path). Run:
  `pytest tests/unittests/test_phantom_gen_pipeline.py -v` (or new test file).

- [ ] **Step 5: Commit** scaffolding only (no binary museum STLs).

---

### Task 2: Cosmic Buddha (`cosmic_buddha`)

**Files:**
- Create: `tmp/fun_phantoms/raw/cosmic_buddha/` (gitignored)
- Create: `src/mypyskindose/phantom_data/cosmic_buddha.stl`, `cosmic_buddha_reduced_1000t.stl`
- Modify: `fun_mesh_manifest.json` (lock rotation), `fun_phantom_provenance.md`,
  `dev-docs/approved_asset_inventory.json` (**both** STLs)

- [ ] **Step 1: Download** Smithsonian CC0 mesh; confirm object page still says CC0.

- [ ] **Step 2: Discover + lock** upright→supine rotation; ingest ~151–170 cm / ~6k faces + 1000t.

- [ ] **Step 3: Validate** + anterior-beam smoke + `plot_setup` smoke. Repair robe holes if needed.

- [ ] **Step 4: Install** + provenance (CC0 / SI credit encouraged) + inventory hash **for both**
  `cosmic_buddha.stl` and `cosmic_buddha_reduced_1000t.stl` with review fields; run
  `python scripts/render_asset_inventory.py --write`.

- [ ] **Step 5: Commit** shipped STLs + provenance/inventory/docs deltas for this mesh.

---

### Task 3: Petite Herculanaise (`petite_herculanaise`)

**Files:**
- Create: shipped STLs + `NOTICE_petite_herculanaise.txt`
- Modify: manifest, provenance, `LICENSE_COMPLIANCE.md` (mesh-assets note), inventory (**both** STLs)

- [ ] **Step 1: Download** from Cults (license **CC BY-SA** explicit). If using MMF instead, record
  the license panel and abort if NC.

- [ ] **Step 2: Ingest** with upright→supine rotation; NOTICE sidecar (attribution + SA note that **mesh
  derivatives** stay SA-compatible; app code remains MIT).

- [ ] **Step 3: Validate** + anterior-beam smoke + GUI smoke.

- [ ] **Step 4: Install** + provenance + inventory both STLs + short LICENSE_COMPLIANCE redistributed-asset note.

- [ ] **Step 5: Commit.**

---

### Task 4: Ramesses II (`ramesses_ii`)

**Files:**
- Create: shipped STLs + `NOTICE_ramesses_ii.txt`
- Modify: manifest, provenance, inventory (**both** STLs)

- [ ] **Step 1: Download** Commons CC BY 4.0 STL (~24 MB raw stays in `tmp/`).

- [ ] **Step 2: Ingest** — already lying; focus scale + PSD-frame axes; lock rotation that puts crown at
  max Z and back at max Y. Accept colossal proportions if smoke passes.

- [ ] **Step 3: Validate** + anterior-beam smoke.

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

- [ ] **Step 3: Ingest** (~120 cm); NOTICE for BY; fill/cap + fix winding before decimate.

- [ ] **Step 4: Validate** + anterior-beam smoke.

- [ ] **Step 5: Install** + provenance + inventory both STLs.

- [ ] **Step 6: Commit.**

---

### Task 6: Product surfacing, tests, docs

**Files:**
- Modify: `src/mypyskindose/gui/helpers.py` — add `get_human_mesh_options() -> dict[str, str]`
  (human-readable label → stem for **all** meshes; demos get `(demo)` suffix); keep
  `get_human_mesh_names()` for discovery/tests
- Modify: `gui/constants.py` / `tabs/settings.py` to use the options dict for `ui.select`
- Create or extend: `tests/unittests/test_demo_phantoms_integration.py` **or**
  `test_phantom_library_integration.py`
- Modify: `AGENTS.md`, `ADDITIONAL_PHANTOMS.md`, `FEATURE_INVENTORY.md`, `CHANGELOG.md`,
  `CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md`, `docs/source/gui_help/` (+ `sync_gui_help.py`)
- Conditionally: `dev-docs/ui_copy.json`, `help_registry.json` **if** adding a visible demo warning banner

**Interfaces:**
- `ui.select(options=get_human_mesh_options(), ...).bind_value(state, "human_mesh")` — bound value = stem.
- File discovery stays dynamic via glob; do not hardcode required file presence for unshipped demos.

- [ ] **Step 1: Implement unified display→stem map** + `DEMO_HUMAN_MESHES` frozenset of **actually shipped**
  stems for label suffix / tests. Title-case clinical stems (e.g. `Adult Female`) so demos are not the only
  pretty labels.

- [ ] **Step 2 (optional product):** When `state.human_mesh in DEMO_HUMAN_MESHES`, show a non-clinical
  warning banner; if so, register strings in `ui_copy.json` / `help_registry.json`. Help-page notes alone
  are acceptable without a banner.

- [ ] **Step 3: Integration tests** for shipped IDs only (files exist, discovered, PSD anchors via
  `Phantom(..., phantom_dim=...)`). Parametrize only meshes that actually shipped.

- [ ] **Step 4: Run** targeted pytest — expect PASS.

- [ ] **Step 5: Docs / help** — AGENTS, ADDITIONAL, FEATURE_INVENTORY, provenance, CHANGELOG (minor when
  released). Help: demo / non-clinical; Steamboat trademark caution; SA note for Petite.

- [ ] **Step 6: Run gates** — `check_doc_freshness`; `check_sensitive_content --require-approved-assets`;
  `check_ui_copy` / `check_help_registry` if banner/strings added. **Do not** `--write-notices` for meshes alone.

- [ ] **Step 7: Commit.**

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
2. `_reduced_1000t` present; full mesh ≤ 20k faces (prefer ≤ 8k); shipped from a **closed** mesh (not subsample fallback).
3. Fun ingest used **`obj_y_up=False`** + correct scale order; per-mesh `rotate_deg` + **`flip_y`** locked;
   face-up validate passes (anterior toward −Y).
4. Watertight gate passed; winding/normals fixed in ingest; anterior-beam entrance/exit smoke passed.
5. NOTICE sidecars for Petite (BY-SA), Ramesses (BY), Steamboat (BY); Cosmic Buddha provenance OK under CC0.
6. **`THIRD_PARTY_NOTICES.md` unchanged** unless Python deps also changed; `LICENSE_COMPLIANCE.md` notes
   redistributed mesh assets.
7. GUI uses unified display→stem options; Steamboat not marketed as Disney Mickey.
8. Inventory entries for **both** full and reduced STLs include hash + `purpose` / `reviewer` / `reviewed_on`.
9. CHANGELOG Unreleased notes the addition; SemVer minor on release.
10. If a demo banner was added, `ui_copy` / help registry updated; otherwise help-page demo notes suffice.

## Out of scope

- Venus de Milo / Michelangelo’s David (nude classical — separate D1 decision).
- Lincoln bust / other Smithsonian busts.
- Popeye / book Pooh / Betty / Tintin.
- Clinical MPFB catalog rows.
- Shipping undecimated museum scans or enabling Git LFS for raw dumps.
- Regenerating `THIRD_PARTY_NOTICES.md` for mesh-only changes.
