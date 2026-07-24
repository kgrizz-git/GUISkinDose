# Additional Anthropomorphic Phantoms

Reference for expanding MyPySkinDose’s human STL library: what is already shipped, preferred generation paths, external sources, and the mesh requirements the dose engine depends on.

For the **agent-executable generation pipeline** (catalog, headless MPFB/Blender, validation gates), see [`plans/AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](plans/AUTOMATED_PHANTOM_LIBRARY_PLAN.md). This page is the broader source survey and integration checklist; that plan is the runbook.

Coordinate conventions for geometry and plotting are defined in [`VENDOR_COORDINATE_SYSTEMS.md`](VENDOR_COORDINATE_SYSTEMS.md) and [`INPUT_DATA_FLOW_AND_OFFSETS.md`](INPUT_DATA_FLOW_AND_OFFSETS.md).

---

## Currently shipped meshes

Human meshes live in `src/mypyskindose/phantom_data/` as `{name}.stl`. Discovery (CLI and GUI)
globs `*.stl` and **excludes** `*_reduced_1000t` preview variants. Prefer the runtime mesh list
(or `get_human_mesh_names()`) over treating any table here as a frozen census — stems may be
trimmed as the catalog settles.

**Families (not an exhaustive id list):**

| Family | Typical notes |
|--------|---------------|
| Legacy clinical | `hudfrid`, `adult_*`, `junior_*`, `senior_*` baselines |
| Pediatric MPFB | `ped_preschool_*`, `ped_5y_*`, `ped_10y_*` age bands |
| Habitus MPFB | `adult_ecto_*`, `adult_endo_*`, `adult_bariatric_{sex}_{n}` |
| Arms-down twins | `*_arms_down` additive siblings (A-pose kept) |
| Reduced previews | `*_reduced_1000t` (~1k faces; not listed as full meshes) |

Non-clinical demo / fun meshes are **not** shipped. A local recovery stash (gitignored) may
exist at `tmp/phantom_data_demo_stash/` with attribution notes if someone previously pulled
those assets; do not re-add without license + inventory review.

Set `settings.phantom.model = "human"` and `settings.phantom.human_mesh` to a discovered
non-reduced name. Body-habitus sliders (`scale_lat`, `scale_ap`, `scale_lon`, clamped 0.5–2.0)
apply at load via `Phantom._apply_human_scale` and are for **moderate sensitivity studies**,
not for shipping new body shapes (see below).

---

## Preferred path for new habitus variants

**Policy:** shipped phantoms must have **true shape variety** (parametric phenotype / regional morph targets), not global affine stretches of existing STLs.

1. **Headless MPFB under Blender** — primary path. Catalog presets + `scripts/phantom_gen/` produce full-body meshes in the MyPySkinDose frame. See [`plans/AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](plans/AUTOMATED_PHANTOM_LIBRARY_PLAN.md) (Phases 0–4 complete; v1 catalog meshes shipped).
2. **MakeHuman standalone GUI** — same asset family as MPFB; use only if headless automation is blocked and a hybrid hand-export path is explicitly approved. Extreme-weight models are not Class-III bariatric fidelity.
3. **GUI `scale_*` on a shipped mesh** — acceptable for interactive “what if” habitus checks; **not** a shipping method for new catalog rows.

Document provenance before committing new STLs: MakeHuman/MPFB **core assets are CC0**; community packs may be CC0 or CC-BY; MakeHuman/MPFB **source code** is AGPL/GPL. Every new or changed `.stl` also needs hash-pinned review in `approved_asset_inventory.json` ([`PRIVACY_AND_SENSITIVE_ASSETS.md`](PRIVACY_AND_SENSITIVE_ASSETS.md)).

---

## External sources

Focus on medical-research hubs. Generic 3D-print sites often return non-medical “phantoms”; if you use them, search `"anatomical phantom"`, `"dosimetry phantom"`, or `"medical imaging phantom"`, and still run the integration checklist below.

### Highest priority for a dosimetry tool

| Source | What it offers | License / notes |
|--------|----------------|-----------------|
| **[ICRP Publication 145](https://www.icrp.org/publication.asp?id=ICRP%20Publication%20145)** mesh-type reference phantoms | Adult male/female and pediatric series; current international computational-dosimetry standard | Clear redistribution policy; prefer as first candidate if attribution/shipping is allowed; otherwise use as a validation reference |
| **Duke XCAT** ([Segars / XCAT distribution](https://olv.duke.edu/technologies/xcat/)) | Detailed cardiac-torso series including pediatric and bariatric variants | Research/clinical agreement from the Duke/XCAT group; **not** redistributable under MIT alone |
| **[Mesh50_XCAT](https://github.com/B-Auer/mesh50_XCAT)** | Mesh converters / mesh forms useful with GATE/Geant4 | Converter code is MIT; **underlying XCAT data** remains under the Duke agreement — do not treat Mesh50 as a blanket MIT grant for phantom redistribution |

### Other useful repositories

| Source | What it offers | License / notes |
|--------|----------------|-----------------|
| **[Martinos Center Phantoms](https://phantoms.martinos.org/)** | Shared CAD models for MRI and imaging research | Varies by model; typically research use |
| **[Zenodo](https://zenodo.org/)** | Paper-adjacent anatomical / dosimetry STLs | Often Creative Commons; check each record |
| **BodyParts3D** | Large open anatomical database, whole-body, labeled | CC-BY-SA |
| **Embodi3D** | Medical STL/3MF, often patient-derived | Quality highly variable; treat as candidate, not ready-to-ship |
| **[NIH 3D Print Exchange](https://3d.nih.gov/)** | Curated public-domain anatomical models | Often already watertight-checked |
| **PLY sources** (Zenodo, BodyParts3D, labs) | Same anatomy in PLY | Convert with MeshLab (`File → Export → STL`, binary) or `trimesh` (`mesh.export("out.stl")`); strip per-vertex color before conversion to keep files small |

### Segmenting clinical or cryosection data

When parametric or published meshes are insufficient:

1. **[The Cancer Imaging Archive (TCIA)](https://www.cancerimagingarchive.net/)** — anonymized CT/MRI. Collections such as CT Colonography and lung screening can include larger habitus.
2. Segment the outer body contour in **3D Slicer** (Flood Filling / Wrap smoothing preferred over Laplacian for soft-tissue feel) or ImageJ; export STL.
3. Decimate aggressively (cryosection or high-res CT often yields 100k+ faces). Target the triangle budgets in [Integration checklist](#integration-checklist).
4. **Visible Human / Visible Korean Human (NLM and related)** — public cryosection data; highest surface fidelity after segmentation, but dense; same decimation/validation path.

TCIA + Slicer remains the best **manual** fallback for a real bariatric surface when parametric tools cannot reach the needed habitus. It is poor for agent automation compared with the MPFB catalog path.

---

## Fun / stylized / historical phantoms

Clinical catalogs stay anatomical. Separately, it can be useful (and fun) to ship or demo **non-clinical** humanoids: low-poly game characters, MakeHuman cartoon morphs, and classical / historical figures.

**Input formats:** MyPySkinDose loads **binary `.stl`**. Candidate sources may ship `.stl`, `.obj`, `.ply`, `.fbx`, or `.glTF` — convert in Blender or MeshLab, then run the [integration checklist](#integration-checklist).

**Short version:**

| Kind | Good starting points | Shipping note |
|------|----------------------|---------------|
| Realistic parametric | MakeHuman / MPFB (core assets **CC0**) | Preferred generation path already |
| Stylized / original cartoon | [Quaternius](https://quaternius.com/), [Kenney.nl](https://kenney.nl/assets) (**CC0**) | Safest fun candidates (no franchise trademarks) |
| Clothed / draped full-body | Cosmic Buddha (**CC0**, shipped); Ramesses II (**CC BY 4.0**, shipped); Petite Herculanaise + other Louvre Cults/STW scans (**blocked** — NC / CULTS PU; see provenance) | Prefer SI CC0 / Commons BY; see [`references/fun_phantom_provenance.md`](references/fun_phantom_provenance.md) |
| Historical busts / portraits | [Smithsonian 3D](https://3d.si.edu/) Open Access (**CC0** when marked) — e.g. Lincoln | Fallback only (not full-body) |
| *Venus de Milo* | Prefer **SMK** plaster-cast scan (**CC0** / PDM) | Easy download; **nude art** — plan decision D1 |
| Michelangelo’s *David* | Scan the World on **Wikimedia Commons** (**CC BY-SA 4.0**) | Easy download; nude art — D1; SA on mesh |
| Other classical / historical statues | [Scan the World](https://www.myminifactory.com/scantheworld/), SMK | **Per-object** license; many togas are **NC** — skip those |
| Steamboat Willie / Popeye / book Pooh | Commons / Thingiverse / Printables (verify) | Steamboat Willie shipped (CC BY); early PD designs only |
| Mixamo / Daz free bases | Mixamo, Daz starters | Private experiments only; **do not commit raw meshes** |

Still apply the [integration checklist](#integration-checklist) (cm scale, table-contact frame, watertight mesh, outward normals). Label fun meshes as demo/non-clinical in the UI.

### Venus de Milo and David — can we add them easily?

**Yes, as fun/demo phantoms** — downloadable STLs already exist. The work is conversion/integration (not hunting for a mesh): scale to cm, lay the upright statue **supine** on the table pad, decimate to ~3k–8k faces, fix winding/normals, hash-pin, and record provenance. They will not look like patients (missing arms on Venus; oversized head/hand on David; standing-sculpture proportions).

| Figure | Recommended source | License | Ease |
|------|---------------------|---------|------|
| **Venus de Milo** | [SMK – National Gallery of Denmark](https://sketchfab.com/3d-models/venus-de-milo-aphrodite-of-milos-53082b5d6cef4c34a9701a2a24f58075) digital cast (also [Wikimedia Commons CC0](https://commons.wikimedia.org/wiki/File:Venus_(Afrodite)_fra_Milo_-_KAS434_1.stl)); high-res via [smk.dk/3d](https://www.smk.dk/3d) | **CC0 / public domain** — safest for shipping | Straightforward; prefer SMK over Louvre Scan-the-World copies |
| **Venus (alternate)** | [Scan the World on Wikimedia](https://commons.wikimedia.org/wiki/File:Scan_the_World_-_Venus_de_Milo.stl) | **CC BY-SA 4.0** — OK with attribution + share-alike on derivatives of the mesh | Same pipeline; larger / different scan |
| **David** | [Scan the World on Wikimedia](https://commons.wikimedia.org/wiki/File:David_(Michelangelo).stl) (~57 MB STL) | **CC BY-SA 4.0** (commercial remix allowed with credit + SA). MyMiniFactory lists the same object as Credit / Remix / Commercial — still verify before commit | Download is easy; file is heavy — decimate before shipping |

**CC BY-SA note:** Does not relicense the MIT application code. It does require attribution and that **modified versions of that mesh** stay under a compatible share-alike license; put credit + license in catalog metadata / notices next to the STL.

**Mickey Mouse:** Only the **1928 Steamboat Willie** depiction is PD in the US (2024); later designs + Disney trademarks still apply. Shippable mesh: [Commons](https://commons.wikimedia.org/wiki/File:Steamboat_Willie_3D_Model.stl) (**CC BY 4.0**). Other early PD cartoons (Popeye 2025, book Pooh ~2022) and clothed full-body scans (Smithsonian Cosmic Buddha CC0, etc.) are surveyed in the reference doc.

**Execution plan (v1 complete — Cosmic Buddha, Ramesses II, Steamboat; Petite blocked):**
[`plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md`](plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md).
Venus/David and Phase 2 cartoons remain on [`plans/FUN_DEMO_PHANTOMS_PLAN.md`](plans/FUN_DEMO_PHANTOMS_PLAN.md).

**Full source list, formats, and license caveats:** [`references/CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md`](references/CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md).

---

## Large / bariatric representation

Ordered by fit for this project:

1. **MPFB/Blender catalog row** with abdomen/torso-weighted detail targets (preferred true-shape path).
2. **TCIA + 3D Slicer** body-contour segmentation of a large-patient CT (highest realism for one patient; manual).
3. **Duke XCAT bariatric variant** under the proper distribution agreement (high anatomical fidelity; not Mesh50-only).
4. **ICRP 145** meshes if redistribution is cleared; otherwise validation reference.
5. **GUI `scale_lat` / `scale_ap` / `scale_lon`** on `adult_*` for moderate habitus sensitivity only (clamp 2.0 will not model extreme Class III mass).

**Keep full-body meshes** for the automated library. Cropping to shoulders/mid-thigh can cut triangle count for a one-off research mesh, but it interacts badly with habitus scaling (see checklist) and is out of scope for the shipping catalog.

---

## Integration checklist

Dropping a file into `src/mypyskindose/phantom_data/{name}.stl` is enough for discovery (`print_available_human_phantoms()` and the GUI mesh selector). It is **not** enough for correct PSD. Before committing:

### Frame and units

- Coordinates in **centimeters**.
- Head-first supine physical frame: **X** lateral (centered near 0), **Y** AP/vertical, **Z** longitudinal (S–I). See `VENDOR_COORDINATE_SYSTEMS.md` for plot-label aliases vs physical axes.
- Match shipped habit: **posterior/back near `max(Y) ≈ 0`** (table contact), **crown near `max(Z) ≈ 0`**, body extending toward negative Y and Z. A mesh centered at the bounding-box origin will float or sink relative to the pad.
- `position_patient_phantom_on_table` and `Phantom.position()` assume that table-contact convention; do not invent a second origin rule per mesh.

### Topology and normals

- Closed, watertight surface (required for ray casting).
- **Consistent winding with outward-facing normals.** Entrance vs exit skin cells use the sign of `dot(v, n)` in `Beam.check_hit`. Inconsistent or inverted normals can put PSD on the wrong side of the patient with no hard error.
- After any decimation or import, re-derive normals via `Phantom._recompute_human_normals_from_triangles()` (runs after `_apply_human_scale`). Repair mixed winding in MeshLab (`Filters → Normals → Re-orient All Faces Coherently`) before shipping.
- Table intersection (`geom_calc.check_intersection`) is largely orientation-robust for hit/miss, but a source-above-triangle guard still uses normal direction — prefer correct outward normals everywhere.

### Triangle budget

| Use | Faces | Guidance |
|-----|------:|----------|
| Interactive / GUI-friendly | ~1k–5k | Reduced previews use 1k; fine for setup checks |
| New shipped phantoms (sweet spot) | ~3k–8k | Detail near `hudfrid` without the full adult cost |
| Upper practical ceiling | ~20k | Above this, per-event casting often feels slow in the GUI |
| Current full adult/junior/senior | 26,756 | Already above the “comfortable” ceiling; keep new assets leaner when possible |

Decimation can flip winding; always re-validate normals after MeshLab/Blender reduce.

### Habitus scaling anchors

`_apply_human_scale` anchors at `(mid_X, max_Y, max_Z)` — midline, anterior-most Y, superior-most Z (crown). For full-body meshes this keeps the back on the table under `scale_ap` and stretches longitudinally from the head.

If you ever author a **torso-only** research mesh:

- `scale_lon` becomes asymmetric (anchor is the cut superior edge, not the crown).
- Prefer adding a reference vertex at the intended crown before export, or expose a scale anchor in code — do not silently rely on full-body assumptions.

### End-to-end smoke check

With a known anterior LAO (or similar) projection on a trusted RDSR, PSD should land on the **anterior** surface of the new phantom, not the back. Wrong-side PSD almost always means inverted or mixed normals.

### Privacy and license

- Hash-pin new STLs in `approved_asset_inventory.json`.
- Record third-party license and attribution (XCAT ≠ Mesh50 MIT; ICRP/MPFB/CC terms as applicable) before redistribution in this public repo.

---

## Code touchpoints

| Location | Role |
|----------|------|
| `Phantom.__init__` / human branch in `phantom_class.py` | Loads STL from `phantom_data/` |
| `Phantom._apply_human_scale` | GUI/body-habitus scaling + normal recompute |
| `Phantom._recompute_human_normals_from_triangles` | Authoritative normal derivation after scale/import |
| `print_available_human_phantoms()` / GUI helper that globs `phantom_data/*.stl` | Mesh discovery (skips `*_reduced_1000t`) |
| `Beam.check_hit` | Entrance/exit from normal sign |
| Settings → Phantom → Body habitus scaling | Writes `scale_lat` / `scale_ap` / `scale_lon` |

---

## Related documents

- [`plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md`](plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md) — **completed v1** (Petite blocked): Cosmic Buddha, Ramesses II, Steamboat
- [`plans/FUN_DEMO_PHANTOMS_PLAN.md`](plans/FUN_DEMO_PHANTOMS_PLAN.md) — broader backlog (Venus/David D1, Phase 2 PD cartoons)
- [`plans/AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](plans/AUTOMATED_PHANTOM_LIBRARY_PLAN.md) — generation runbook and catalog policy
- [`assessments/MPFB_HEADLESS_SPIKE_2026-07-21.md`](assessments/MPFB_HEADLESS_SPIKE_2026-07-21.md) — Phase 0 headless spike result
- [`references/CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md`](references/CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md) — stylized, cartoon, and public-domain figure mesh sources
- [`VENDOR_COORDINATE_SYSTEMS.md`](VENDOR_COORDINATE_SYSTEMS.md) — physical vs plot-label coordinates
- [`PRIVACY_AND_SENSITIVE_ASSETS.md`](PRIVACY_AND_SENSITIVE_ASSETS.md) — STL admission
- [`TO_DO.md`](TO_DO.md) — backlog item for exploring additional phantoms
