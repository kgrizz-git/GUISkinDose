# Fun Demo Phantoms Implementation Plan

> **Status (2026-07-22):** **Active v1 execution** for Cosmic Buddha + Petite Herculanaise + Ramesses II +
> Steamboat Willie lives in
> [`DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md`](DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md).
> This document remains the broader candidate survey and holds **D1-gated** Venus/David tasks plus Phase 2
> cartoon / bust backlog.
>
> **For agentic workers:** For the clothed+Steamboat v1, follow the plan linked above. Use
> `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans`.
> Steps use checkbox (`- [ ]`) syntax. Mark a checkbox only after the step is fully done and verified.
>
> **Related:** [`ADDITIONAL_PHANTOMS.md`](../ADDITIONAL_PHANTOMS.md),
> [`references/CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md`](../references/CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md).
> Clinical habitus expansion remains [`AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](AUTOMATED_PHANTOM_LIBRARY_PLAN.md).
>
> **Plan review (2026-07-21):** Incorporates constructive criticism on transform defaults,
> `Phantom` ctor, validate/watertight policy, GUI label binding, license NOTICE packaging,
> nude-sculpture UX, and Steamboat Willie alternates.

**Goal:** Ship clearly labeled **demo / non-clinical** humanoid STLs across three themes — (A) classical sculpture (pending nude-content decision), (B) public-domain / early cartoon figures (Steamboat Willie first; Popeye / book-Pooh as follow-ons), (C) **historical / draped figures** (**full-body preferred**; busts only as intentional novelty) — after download → orient → PSD-frame (`--no-obj-y-up`) → decimate → validate → privacy admission.

**Architecture:** Reuse `scripts/phantom_gen/` post-process tools. Add `ingest_fun_mesh.py` + `fun_mesh_manifest.json` that (1) records provenance under gitignored `tmp/`, (2) applies **per-mesh** Euler orientation discovered and locked in the manifest, (3) re-anchors with **`obj_y_up=False`**, (4) decimates to shipping budget + 1000t preview, (5) installs into `phantom_data/` with NOTICE/attribution sidecars where required.

**Tech stack:** Python 3.11+, `numpy-stl`, `trimesh` (decimation + watertight checks), existing `Phantom` loader; Blender/MeshLab only for hole-fill / join when validator fails watertight.

**Candidate survey (not all v1):** [`references/CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md`](../references/CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md).

## Open maintainer decisions (resolve before Task 2+)

| ID | Question | Options | Default if undecided |
|----|----------|---------|----------------------|
| **D1 Nude sculptures** | Venus/David are nude classical scans in a clinical GUI | (a) ship in main list with `(demo)` + content note in help; (b) ship behind explicit “include demo art” opt-in; (c) defer classical nudes; prefer clothed historical + cartoons | **Defer classical nudes (c)** until D1 answered — scaffolding (Task 1) still proceeds |
| **D2 Watertight** | Classical/cartoon meshes may be open | (a) hard gate — repair until `validate_phantom` watertight passes; (b) add `--allow-non-watertight` for demos only | **(a) hard gate** |
| **D3 Steamboat source** | Prefer which mesh? | See [Steamboat Willie candidates](#steamboat-willie-candidates); primary remains Commons CC BY | Keep **Commons Adrian Cojocaru** unless NoAI optics push to JoeBert (~5.6k tris, CC-BY) |
| **D4 David SA packaging** | How to satisfy BY-SA | (a) `NOTICE` + license pointer beside STL + provenance doc; (b) keep David optional/external | **(a)** |
| **D5 Demo PSD bar** | Quality bar | (a) crash-free + recognizable; (b) required anterior-beam entrance/exit smoke on fixed RDSR for every shipped demo | **(b)** for all shipped demos |
| **D6 Historical / draped** | Prefer **clothed full-body** demos to dodge D1 and match dose geometry needs | (a) include ≥1 **clothed full-body** CC0/CC-BY(/SA) scan in **v1** (e.g. Cosmic Buddha); (b) Phase 2 after cartoons; (c) bust-only (Lincoln) if no full-body clears | **(a) clothed full-body in v1** if license + watertight clear; busts are fallback only |

Mark the chosen option in this table when decided; do not mark Tasks 2–3 complete under default (c) if classical nudes were deferred.

## Global constraints

- **Demo only:** never present as dosimetry reference phantoms; GUI/docs say demo / non-clinical.
- **Content sensitivity:** classical nudes need an explicit D1 decision and, if shipped, a short help note that these are historical art demos, not clinical anatomy.
- **Frame:** centimeters; head-first supine; `X` mid ≈ 0; **max Y ≈ 0** (back on table); **max Z ≈ 0** (crown); body toward −Y/−Z.
- **Transform contract (critical):** After orientation + height scale, call `transform_to_psd_frame` with **`obj_y_up=False`** (CLI `--no-obj-y-up`). Default `obj_y_up=True` remaps `(x,y,z)→(x,z,y)` and will destroy a pre-oriented sculpture frame. Do **not** rely on `flip_y_if_needed` (symmetric bboxes → no-op).
- **Orientation discovery:** One `--rotate-deg 90,0,0` will not fit all sources. Per mesh: try rotations → GUI/`plot_setup` smoke → **lock** `rotate_deg` + `height_axis` in `fun_mesh_manifest.json`.
- **Triangle budget:** full mesh **3k–8k** faces (hard ceiling **20k**); always ship `{name}_reduced_1000t.stl`.
- **Watertight:** follow D2; default = repair until validator passes. Aligns Out of scope with acceptance criteria.
- **Normals:** after every decimation, ensure coherent outward winding; **anterior-beam entrance/exit smoke required for every shipped demo** (D5).
- **Privacy:** SHA-256 in `approved_asset_inventory.json` with **human review fields** (`purpose`, `reviewer`, `reviewed_on`) like existing STLs; `python scripts/render_asset_inventory.py --write`.
- **Scratch:** only under `tmp/fun_phantoms/` — never commit raw 50+ MB sources (David ~57 MB stays in `tmp/`). Decimated ships are small; **no Git LFS required** if face budget holds.
- **License packaging:**
  - CC0 (Venus): provenance note sufficient.
  - CC BY / BY-SA: `dev-docs/references/fun_phantom_provenance.md` **plus** redistributable NOTICE/attribution sidecar (e.g. `phantom_data/NOTICE_david_michelangelo.txt`). Dependency `THIRD_PARTY_NOTICES.md` is **not** a substitute.
- **Locked v1 candidates (subject to D1/D3/D6):**

| Mesh ID | Theme | Source | License | Attribution / notes |
|---------|-------|--------|---------|---------------------|
| `venus_de_milo` | Classical (nude) | SMK cast — [Commons CC0](https://commons.wikimedia.org/wiki/File:Venus_(Afrodite)_fra_Milo_-_KAS434_1.stl) | **CC0** | **Blocked while D1=defer**; cast scan; missing arms / plinth possible |
| `david_michelangelo` | Classical (nude) | [Commons Scan the World](https://commons.wikimedia.org/wiki/File:David_(Michelangelo).stl) | **CC BY-SA 4.0** | **Blocked while D1=defer**; NOTICE sidecar (D4) |
| `steamboat_willie` | PD cartoon | [Commons STL](https://commons.wikimedia.org/wiki/File:Steamboat_Willie_3D_Model.stl) (Adrian Cojocaru) | **CC BY 4.0** | Stem/UI **`steamboat_willie`** only; see alternates; D3 |
| `cosmic_buddha` | Historical / draped | Smithsonian Cosmic Buddha — [3d.si.edu](https://3d.si.edu/object/3d/buddha-draped-robes-portraying-realms-desire:d8c62be8-4ebc-11ea-b77f-2e728ce88125) | **CC0** (confirmed on object page) | **Primary clothed full-body**; standing ~151 cm; scale + supine rotate |
| `petite_herculanaise` | Classical draped | Louvre Scan the World — [Cults CC BY-SA](https://cults3d.com/en/3d-model/art/statue-of-a-woman-petite-herculanaise-at-the-louvre-paris) (MMF [object 6356](https://www.myminifactory.com/object/3d-print-statue-of-a-woman-petite-herculanaise-at-the-louvre-paris-6356); re-confirm MMF panel at download) | **CC BY-SA** (Cults) | **Try in v1**; fully draped woman; NOTICE sidecar; scale + supine rotate |
| `ramesses_ii` | Historical / draped | [Commons STL](https://commons.wikimedia.org/wiki/File:Colossal_sculpture_of_Ramesses_II.stl) (Dejp3) | **CC BY 4.0** (confirmed) | **Try in v1**; already lying — mainly scale + axis lock; NOTICE; proportions may be odd |
| `lincoln_life_mask` | Historical bust | Smithsonian Open Access **CC0** Lincoln life mask / bust | **CC0** when marked | **Fallback only** if all three full-body tries fail watertight/ship |
| `popeye` / `winnie_pooh` | PD cartoon follow-on | See [Other PD cartoon candidates](#other-pd-cartoon-candidates) | Mesh license TBD | **Phase 2** unless swapped into v1 |

- **Named PD cartoon / trademark:** never use Disney “Mickey Mouse” branding. For Popeye / Pooh / Betty / Tintin: early-PD design only; trademark-safe stems (`steamboat_willie`, `popeye`, `winnie_pooh`).
- **SemVer:** shipping new assets + GUI labels → expect a **minor** version bump when releasing.
- **Cross-platform:** pathlib only; ingest must run on Windows/macOS/Linux.

---

## Steamboat Willie candidates

Many fan meshes exist; **per-model license** always wins over “character is PD.”

| Candidate | Where | License (as listed) | Notes | Ship fit |
|-----------|-------|---------------------|-------|----------|
| **Adrian Cojocaru (primary)** | [Commons STL](https://commons.wikimedia.org/wiki/File:Steamboat_Willie_3D_Model.stl) (~6.85 MB); Sketchfab animated source | **CC BY 4.0** | Commons mirror is the clearest redistributable STL; Sketchfab page also has **NoAI** tag (often Sketchfab-platform-only — record decision) | **Preferred** |
| **JoeBert (RIGGED)** | [Sketchfab](https://sketchfab.com/3d-models/rigged-steamboat-willie-47c5ba4e87344e62ae836b4c65db81a4) | **CC Attribution** | ~**5.6k tris** — already near shipping budget; good alternate if Commons mesh is hard to repair | Strong alternate |
| **HotDiggity23** | [Sketchfab](https://sketchfab.com/3d-models/mickey-mouse-steamboat-willie-model-3f9bfd873a5e4f3ca2377adf63b25256) | **CC Attribution** (~25k tris) | Author asks for credit | OK alternate |
| **lorenzo96roma** | [Pinshape OBJ](https://pinshape.com/items/67110-3d-printed-steamboat-willie-mickey-mouse) | **CC BY** | OBJ ~5.6 MB; login may be required | OK if Commons fails |
| **tramdrey** | [Sketchfab](https://sketchfab.com/3d-models/steamboat-willie-58c5716c49c947f2a5aa152cec39cec0) | **Free Standard** (not CC) + NoAI | **Do not ship** — proprietary Sketchfab standard license | Reject |
| **Printables / Thingiverse assorted** | e.g. CMR, Arpboy, Peter Farell; Thingiverse minifig **CC BY-NC-SA** | Varies / often NC or unclear | Verify per page; **skip NC** | Usually reject |
| **CGTrader paid packs** | various | Royalty-free store terms | Not open-license FOSS redistribution | Reject |

**Fallback if no Steamboat mesh clears license + watertight:** ship a Quaternius/Kenney **CC0** low-poly humanoid as the cartoon demo instead (still labeled demo).

---

## Other PD cartoon candidates (Phase 2 / optional v1 swap)

Character PD ≠ mesh license. Prefer CC0/CC-BY meshes of the **early** design; skip NC and modern redesigns. Video-game icons (Mario, Pac-Man, …) remain **out of scope** (still copyrighted).

| Character | US character PD (early form) | Mesh leads | Ship fit |
|-----------|------------------------------|------------|----------|
| **Popeye** (1929 *Thimble Theatre*) | PD since 2025 | e.g. [Thingiverse Simonarri](https://www.thingiverse.com/thing:2417631) (**CC BY**); many MakerWorld/Cults — verify each | **Good Phase 2**; stem `popeye` |
| **Winnie-the-Pooh** (Milne/Shepard book) | PD since ~2022 | e.g. [Printables “Pooh Bear - 1925”](https://www.printables.com/model/1706462-winnie-the-pooh-pooh-bear-1925) (**Public Domain** mark); other CC-BY Sketchfab | **Good Phase 2** if **no Disney red shirt** |
| **Betty Boop** (*Dizzy Dishes* 1930) | Early form PD 2026 | Many Printables = modern Betty / NC | **Weak** — PD look is poodle-flapper; trademarks strong |
| **Tintin** (early strips) | Early US PD 2025 | Fan STLs often NC / personal-use | **Weak** — trademark enforcement risk |
| **Quaternius / Kenney** | N/A (original CC0) | [quaternius.com](https://quaternius.com/), [kenney.nl](https://kenney.nl/assets) | **Safest cartoon filler** — no franchise trademarks |

Manifest may list these under `phase: 2` until a mesh is selected and cleared.

---

## Historical / draped figure candidates (v1 + backlog)

**Prefer clothed / draped full-body standing figures** (dose work needs a full torso + limbs on the table). Busts and life masks are novelty fallbacks only. Always confirm **per-object** CC0/CC-BY(/SA) — many Scan the World “robed man / toga” scans are **BY-NC** and must not ship.

### Clothed / draped full-body — **try all three in v1** (licenses confirmed)

Scale to a plausible table-phantom height (or keep near life-size) and lock `rotate_deg` / `height_axis` in the manifest after `plot_setup` smoke. Pipeline: download → orient supine → `--no-obj-y-up` → decimate → validate → D5 entrance/exit.

| Candidate | Source | License (verified) | Geometry notes | Priority |
|-----------|--------|--------------------|----------------|----------|
| **Cosmic Buddha** | [Smithsonian 3D](https://3d.si.edu/object/3d/buddha-draped-robes-portraying-realms-desire:d8c62be8-4ebc-11ea-b77f-2e728ce88125) | **CC0** | Standing ~151 cm; upright → rotate to supine; robes may need hole-fill | **Try first** |
| **Petite Herculanaise** | [Cults](https://cults3d.com/en/3d-model/art/statue-of-a-woman-petite-herculanaise-at-the-louvre-paris) / [MMF 6356](https://www.myminifactory.com/object/3d-print-statue-of-a-woman-petite-herculanaise-at-the-louvre-paris-6356) | **CC BY-SA** on Cults; re-check MMF at download | Standing draped woman; same upright→supine; NOTICE + SA on mesh derivatives | **Try second** |
| **Ramesses II** colossal | [Commons](https://commons.wikimedia.org/wiki/File:Colossal_sculpture_of_Ramesses_II.stl) | **CC BY 4.0** | Already **lying**; mainly scale + axis alignment; colossal proportions | **Try third** |

Ship whichever clear watertight + D5; do not block v1 on shipping all three. Lincoln bust remains fallback only.

### Busts / portraits (fallback — not typical dose geometry)

| Candidate | Source hub | License watch | Notes | Priority |
|-----------|------------|---------------|-------|----------|
| **Abraham Lincoln** life mask / bust | [Smithsonian 3D](https://3d.si.edu/) Open Access | **CC0** when marked | Head-only; use only if no full-body clears | Fallback |
| **Helen Keller / Anne Sullivan** (and similar OA portraits) | Smithsonian Open Access | **CC0** when marked | Bust-scale | Backlog |
| **Other Smithsonian OA people** | Filter `media_usage:CC0` on 3d.si.edu | **CC0** | Skip objects with tighter terms | Backlog |

### Classical nudes / other (D1-gated or NC traps)

| Candidate | Source hub | License watch | Notes | Priority |
|-----------|------------|---------------|-------|----------|
| **Venus / David / other classical nudes** | SMK / Scan the World / Commons | CC0 or BY-SA | Tasks 2–3; **D1 gate** | v1 only if D1 ≠ defer |
| **SMK other casts** (Apollo, Doryphoros, Discobolus, …) | [smk.dk/3d](https://www.smk.dk/3d) | Often **CC0 / PDM** | Many nude classical — same D1 sensitivity | Backlog / D1 |
| **Scan the World toga / “robed man”** | MyMiniFactory | Often **NC / Exclusive Noncommercial** | e.g. Altes Museum Toga Statue — **do not ship** | Reject unless Commons BY/SA mirror |
| **Greenough Washington / Greek Slave** | Smithsonian | **CC0** when marked | Famous full figures but **nude / semi-nude** — same D1 issue | Not “clothed” |

Full-body draped: scale height to a plausible table-phantom cm extent (or keep near life-size). Busts: ~20–40 cm SI extent if used. Document scale in provenance.

---

## File map

| Path | Role |
|------|------|
| `tmp/fun_phantoms/` (gitignored) | Downloads + intermediates |
| `scripts/phantom_gen/ingest_fun_mesh.py` (new) | Orient → scale → transform(`obj_y_up=False`) → decimate → validate |
| `scripts/phantom_gen/fun_mesh_manifest.json` (new) | URLs, licenses, attribution, **locked `rotate_deg`**, `height_cm`, `height_axis` |
| `scripts/phantom_gen/transform_to_psd_frame.py` | Existing; call with `--no-obj-y-up`; optional `--rotate` if convenient |
| `scripts/phantom_gen/generate_reduced.py` | Already has `--target-faces` — **reuse** `decimate_to_target_faces` (do not reinvent) |
| `scripts/phantom_gen/validate_phantom.py` | Frame + scale + faces + watertight + Phantom load; add `--allow-non-watertight` **only if D2=(b)** |
| `src/mypyskindose/phantom_data/{id}.stl` + `_reduced_1000t.stl` | Shipped meshes |
| `src/mypyskindose/phantom_data/NOTICE_*.txt` | BY / BY-SA attribution sidecars |
| `dev-docs/references/fun_phantom_provenance.md` (new) | Credits, retrieval dates, repair notes, NoAI decision |
| `AGENTS.md`, `ADDITIONAL_PHANTOMS.md`, `FEATURE_INVENTORY.md`, `CHANGELOG.md` | Lists + demo labeling |
| `dev-docs/approved_asset_inventory.json` | Hash + human review metadata |
| GUI settings mesh `ui.select` | **`options={display: stem}`** so bound value stays the stem |

---

## Shared workflow (every mesh)

1. Download into `tmp/fun_phantoms/raw/{id}/`; sidecar JSON with URL, license, retrieval date.
2. **Discover orientation:** apply candidate Eulers; confirm head→+Z, back→+Y visually; lock in manifest (`rotate_deg`, `height_axis`).
3. Uniform-scale so the **height axis** span ≈ `height_cm` (not blindly “Z” before rotation is correct).
4. `transform_to_psd_frame … --no-obj-y-up` → `tmp/fun_phantoms/psd/{id}.stl`.
5. Decimate to 3k–8k via `decimate_to_target_faces` (from `generate_reduced.py`).
6. Re-check / repair winding; regenerate normals path via `Phantom` load.
7. `generate_reduced.py` → `{id}_reduced_1000t.stl`.
8. `validate_phantom.py` — must pass anchors, scale (50–220 cm), face count, Phantom load, and watertight (unless D2 allows otherwise). **Skip** clinical `--compare-affine` shape metrics.
9. **Anterior-beam entrance/exit smoke** on a trusted example RDSR (wrong-side PSD → fix normals).
10. Install to `phantom_data/`, NOTICE if needed, hash-pin with review fields, docs, `(demo)` GUI label via display→value map.

---

## Task 1: Manifest + ingest scaffolding

**Files:**
- Create: `scripts/phantom_gen/fun_mesh_manifest.json`
- Create: `scripts/phantom_gen/ingest_fun_mesh.py`
- Modify: `scripts/phantom_gen/README.md`
- Modify if needed: `scripts/phantom_gen/transform_to_psd_frame.py` (document `--no-obj-y-up` for fun ingest; optional Euler helper)
- Modify if D2=(b): `validate_phantom.py` (`--allow-non-watertight`)

- [ ] **Step 1: Write `fun_mesh_manifest.json`** with rows for v1 + phase-2 candidates (id, theme, source_url, license, attribution, `suggested_height_cm`, placeholder `rotate_deg` / `height_axis`, `phase: 1|2`). Include Steamboat alternates, clothed full-body historical (Cosmic Buddha / Petite Herculanaise; Lincoln bust as fallback), and PD cartoon follow-ons as documented above.

- [ ] **Step 2: Implement `ingest_fun_mesh.py`**

```bash
python scripts/phantom_gen/ingest_fun_mesh.py \
  --id venus_de_milo \
  --input tmp/fun_phantoms/raw/venus_de_milo/source.stl \
  --rotate-deg 90,0,0 \
  --height-cm 170 \
  --target-faces 6000 \
  --out-dir tmp/fun_phantoms/psd
```

Behavior: load STL/OBJ/PLY; apply XYZ Euler **degrees**; scale height axis; call transform helpers with **`obj_y_up=False`**; decimate via `decimate_to_target_faces`; write `{id}.stl`; run `validate_phantom` (full gate per D2).

- [ ] **Step 3: Reuse** existing `generate_reduced.py --target-faces` (already implemented). Do not duplicate.

- [ ] **Step 4: Document** download + `--no-obj-y-up` contract in `scripts/phantom_gen/README.md`.

- [ ] **Step 5: Commit** scaffolding only (no binary STLs).

---

## Task 2: Venus de Milo (`venus_de_milo`) — requires D1 ≠ defer

**Blocked while D1 = defer classical.**

- [ ] **Step 1: Download** SMK CC0 Commons STL into `tmp/…/raw/venus_de_milo/`.

- [ ] **Step 2: Discover + lock** rotation; ingest ~170 cm / ~6k faces + 1000t.

- [ ] **Step 3: Validate** frame + watertight; GUI smoke; **anterior-beam smoke**; note missing arms/plinth in provenance.

- [ ] **Step 4: Install** + provenance + inventory (hash + reviewer fields).

- [ ] **Step 5: Commit.**

---

## Task 3: Michelangelo’s David (`david_michelangelo`) — requires D1 ≠ defer

**Blocked while D1 = defer classical.**

- [ ] **Step 1: Download** Commons STL to `tmp/` only (~57 MB).

- [ ] **Step 2: Ingest** (heavy decimation); write `NOTICE_david_michelangelo.txt` (BY-SA credit + link + “changes: reoriented, scaled, decimated”).

- [ ] **Step 3: Validate + anterior-beam smoke + GUI smoke.**

- [ ] **Step 4: Install** + provenance + inventory.

- [ ] **Step 5: Commit.**

---

## Task 4: Steamboat Willie (`steamboat_willie`) — requires D3

- [ ] **Step 1: Download** chosen candidate (default Commons Cojocaru) to `tmp/…/raw/steamboat_willie/`. If watertight repair fails, try **JoeBert** (~5.6k tris, CC-BY) before falling back to Kenney/Quaternius CC0.

- [ ] **Step 2: Branding** — stem/UI `steamboat_willie` / “Steamboat Willie (demo)” only. Provenance: US PD 1928 design + CC BY on 3D interpretation + trademark caution + Sketchfab NoAI courtesy note if applicable.

- [ ] **Step 3: Ingest** (~120 cm height); repair if open/multi-part; NOTICE for BY.

- [ ] **Step 4: Validate + anterior-beam smoke.**

- [ ] **Step 5: Install** + provenance + inventory.

- [ ] **Step 6: Commit.**

---

## Task 4b: Clothed full-body trio — Cosmic Buddha, Petite Herculanaise, Ramesses II — D6=(a)

**Try all three** (licenses confirmed). Ship every mesh that clears watertight + D5; order below is try order, not a hard “all or nothing.”

- [ ] **Step 1: Manifest rows** for `cosmic_buddha`, `petite_herculanaise`, `ramesses_ii` with source URLs, licenses, `suggested_height_cm`, placeholder `rotate_deg` / `height_axis`.

- [ ] **Step 2: Cosmic Buddha (CC0)** — download from SI to `tmp/…/raw/cosmic_buddha/`; upright→supine rotate; scale; `--no-obj-y-up`; decimate; validate; D5 smoke; install if clear.

- [ ] **Step 3: Petite Herculanaise (CC BY-SA)** — prefer Cults (license explicit) or MMF after re-checking license panel; NOTICE sidecar; same pipeline as Step 2.

- [ ] **Step 4: Ramesses II (CC BY 4.0)** — Commons STL; already lying — focus scale + PSD-frame axes; NOTICE; accept odd colossal proportions if smoke passes.

- [ ] **Step 5 (fallback):** If **none** of the three ship, ingest Lincoln CC0 bust and document blockers.

- [ ] **Step 6: Hash-pin + commit** shipped STLs only.

---

## Task 4c (Phase 2): Popeye and/or book-style Pooh

- [ ] **Step 1: Pick** one cleared mesh from [Other PD cartoon candidates](#other-pd-cartoon-candidates) (CC0/CC-BY; not NC; early design; Pooh without Disney red shirt).

- [ ] **Step 2: Ingest** with trademark-safe stem (`popeye` / `winnie_pooh`); NOTICE if BY.

- [ ] **Step 3: Validate + smoke + install + inventory + commit.**

---

## Task 5: Product surfacing + docs

- [ ] **Step 1: `DEMO_HUMAN_MESHES` frozenset** + GUI `ui.select` **display→value** map (`{"Steamboat Willie (demo)": "steamboat_willie", "Cosmic Buddha (demo)": "cosmic_buddha", …}`) so persisted settings stay stems. Cover with a regression test that bound values have matching `.stl` files.

- [ ] **Step 2: Unit tests** — follow `tests/unittests/test_phantom_library_integration.py`:

```python
from mypyskindose.phantom_class import Phantom
from mypyskindose.settings import PyskindoseSettings, load_settings_example_json
# exact imports as in test_phantom_library_integration.py

settings = PyskindoseSettings(settings=load_settings_example_json())
phantom = Phantom(
    phantom_model="human",
    phantom_dim=settings.phantom.dimension,
    human_mesh=mesh_name,
)
```

Assert: file exists, `_reduced_1000t` companion, anchors `y_max`/`z_max` ≈ 0, discovery lists stem. Optional scale smoke. Heavy dose calc only if gated. Parametrize over **actually shipped** demo IDs.

- [ ] **Step 3: Docs** — `AGENTS.md`, `ADDITIONAL_PHANTOMS.md`, `FEATURE_INVENTORY.md`, character sources, provenance, CHANGELOG (minor when released). Help: demo note; **nude-art content note if Venus/David ship**; draped full-body note if Cosmic Buddha (etc.) ships; bust note only if Lincoln fallback ships (`docs/source/gui_help/` → `sync_gui_help.py`). Update `ui_copy` / help registry if new warning strings.

- [ ] **Step 4: Run** `check_doc_freshness`, `check_sensitive_content --require-approved-assets`, targeted pytest.

- [ ] **Step 5: Commit.**

---

## Task 6: Close-out

- [ ] **Step 1: Complete** only meshes actually shipped under D1–D6; update checkboxes honestly if classical nudes deferred.

- [ ] **Step 2: Update** `TO_DO.md` / `index.md` status; leave Phase 2 cartoon/historical backlog items visible in the plan or TO_DO.

- [ ] **Step 3: Archive** this plan under `dev-docs/plans/archive/` when v1 done; fix `index.md` paths in the same PR.

---

## Out of scope

- Clinical catalogs (ICRP, XCAT, MPFB habitus rows).
- Modern Mickey / Disney logos; modern Betty; aggressively trademarked Tintin merchandising looks.
- Video-game characters (Mario, Pac-Man, Sonic, …) — still copyrighted.
- Mixamo/Daz, Sketchfab **Free Standard** / NC meshes.
- Automatic “fun mode” beyond `(demo)` labels and optional D1 opt-in.
- Shipping undecimated museum scans or enabling Git LFS for raw 57 MB David.

---

## Acceptance criteria

1. Each **shipped** demo ID appears in discovery (non-reduced), loads with correct `Phantom(..., phantom_dim=...)`, and works in `plot_setup` / dose calc without crash.
2. `_reduced_1000t` present; full mesh ≤ 20k faces (prefer ≤ 8k).
3. Fun ingest used **`obj_y_up=False`**; per-mesh `rotate_deg` locked in manifest.
4. Watertight policy matches D2; anterior-beam entrance/exit smoke passed for each shipped demo.
5. Provenance + NOTICE sidecars cover BY / BY-SA; inventory has hash **and** human review metadata.
6. GUI display labels ≠ bound stems; Steamboat not marketed as Disney Mickey; other PD cartoons use trademark-safe stems.
7. If Venus/David ship: help includes non-clinical + historical-art/nude-content note per D1.
8. If a draped full-body ships (D6): help notes historical/draped demo (non-clinical); object URL + license recorded. If only a bust ships as fallback, help notes bust limitation.
9. Manifest documents Phase 2 PD cartoon + additional historical backlog even if not shipped in v1.
