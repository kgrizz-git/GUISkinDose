# Character, Stylized, and Public-Domain Mesh Sources

Survey of free / open-license **full-body or humanoid** meshes that could be fun MyPySkinDose phantoms: realistic parametric humans, stylized game characters, and public-domain historical / classical figures.

This is a **candidate-source list**, not a commitment to ship any of these. Clinical dosimetry still prefers anatomical libraries and the MPFB catalog — see [`ADDITIONAL_PHANTOMS.md`](../ADDITIONAL_PHANTOMS.md) and [`plans/AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](../plans/AUTOMATED_PHANTOM_LIBRARY_PLAN.md).

**Out of scope here:** isolated organs, bones, prosthetic/engineering mannequins, and trademarked cartoon IPs (Mickey, Mario, etc.). Prefer original CC0 characters or public-domain sculpture scans.

**Before committing any STL to this repo:** verify the **per-model** license, convert to binary STL, run the [integration checklist](../ADDITIONAL_PHANTOMS.md#integration-checklist), and hash-pin the file per [`PRIVACY_AND_SENSITIVE_ASSETS.md`](../PRIVACY_AND_SENSITIVE_ASSETS.md).

---

## License cheat sheet (for shipping in a public repo)

| Tier | Examples | Shipping in MyPySkinDose |
|------|----------|--------------------------|
| **Safest** | CC0 / public domain | Redistribute with provenance note |
| **OK with care** | CC-BY, CC-BY-SA | Attribution (and share-alike for SA) in notices / catalog metadata |
| **Usually avoid shipping** | CC-BY-NC | Blocks commercial redistribution of the package |
| **Do not ship raw meshes** | Mixamo, many Daz “free” bases | Use in a private build only; EULAs forbid redistributing raw character files |

Always re-check the model page — aggregators mix licenses.

**Formats:** `.obj` / `.fbx` / `.glTF` → convert in Blender or MeshLab to binary `.stl`. Strip textures/colors; MyPySkinDose uses geometry only. Scale to centimeters and re-anchor to the MyPySkinDose frame.

---

## Realistic / parametric humans

### MakeHuman Community

- **Site:** [makehumancommunity.org](http://www.makehumancommunity.org/)
- **Formats:** `.obj`, `.stl`, `.fbx` (and Blender/MPFB workflows)
- **License:** **Core bundled assets are CC0.** Community asset packs may be CC0 or CC-BY — check each pack. MakeHuman **source code** is AGPL; MPFB code is GPL — that does not make core mesh output AGPL.
- **Fit:** Same family as the preferred headless MPFB pipeline. Best path for realistic full-body habitus variants intended for the catalog.
- **Note:** Extreme-weight morphs are not Class-III bariatric medical fidelity; label honestly.

### Manuel Bastioni Lab / MB-Lab (Blender)

- **Repo:** [github.com/animate1978/MB-Lab](https://github.com/animate1978/MB-Lab) (archived but usable)
- **Formats:** Export `.obj` / `.stl` from Blender
- **License:** GPL (add-on); treat exported meshes per project practice and any bundled asset notices
- **Fit:** Parametric realistic/stylized humans inside Blender when MakeHuman/MPFB is unavailable

### Sketchfab (filter Downloadable + Free)

- **Site:** [sketchfab.com](https://sketchfab.com/) — search human / base mesh; filter downloadable + free
- **Formats:** Often `.obj`, `.glTF`; sometimes `.stl`
- **License:** Per model (CC0, CC-BY, or custom). Prefer CC0 base meshes.
- **Fit:** Quick realistic or low-poly humanoids for demos. Quality and topology vary widely.

### Thingiverse (full-body humans only)

- **Site:** [thingiverse.com](https://www.thingiverse.com/) — search full-body / anatomical phantom / mannequin; **skip** organ-only uploads
- **Formats:** Primarily `.stl`
- **License:** Per thing (CC0, CC-BY, CC-BY-SA, …)
- **Fit:** Occasional printable full-body figures; always inspect watertightness and winding

---

## Stylized / game-style humanoids

Good for demos, teaching, and “fun” phantom selectors. Expect low poly counts (often already in the interactive triangle budget) and non-anatomical proportions — PSD maps will still compute, but do not present them as clinical body models.

### Quaternius

- **Site:** [quaternius.com](https://quaternius.com/)
- **Formats:** `.obj`, `.fbx`, `.glTF` (some packs include `.blend`)
- **License:** **CC0**
- **Fit:** Low-poly people packs, modular characters — excellent ship-friendly candidates after scale/frame conversion

### Kenney.nl

- **Site:** [kenney.nl/assets](https://kenney.nl/assets?q=3d) (e.g. Blocky Characters, Mini Characters, animated character packs)
- **Formats:** `.obj`, `.fbx`, etc.
- **License:** **CC0**
- **Fit:** Toon / blocky humanoids; modular heads/bodies. Fun placeholders; clearly label as stylized

### Mixamo (Adobe)

- **Site:** [mixamo.com](https://www.mixamo.com/)
- **Formats:** `.fbx` (convert via Blender)
- **License:** Free with Adobe account for use in projects; **do not redistribute raw character/animation files** as standalone assets (so **do not commit Mixamo STLs to this public repo**)
- **Fit:** Private local experiments / screenshots only

### Daz 3D free starters

- **Site:** [daz3d.com/free-3d-models](https://www.daz3d.com/free-3d-models)
- **Formats:** Export via Daz Studio (`.obj` / `.fbx`)
- **License:** Per-product EULA — typically **not** open-source redistributable bases
- **Fit:** Personal rendering only; not a shipping source for MyPySkinDose

---

## Classical sculptures and historical figures

These make memorable phantoms (David on the table, Lincoln life mask as a head-heavy oddity, etc.). Prefer **standing / reclining full figures** or life-size busts you intentionally accept as non-full-body. Recline and scale to cm; many scans are upright and meters-scale.

### Scan the World (MyMiniFactory)

- **Site:** [myminifactory.com/scantheworld](https://www.myminifactory.com/scantheworld/)
- **Formats:** `.stl`, `.obj`
- **License:** Often **CC-BY-NC** — fine for private demos; **problematic to ship** in a commercially usable public package. Check each scan.
- **Examples of interest:** Michelangelo’s *David*, *Venus de Milo*, and other classical sculpture scans
- **Fit:** Fun demos and education; clear NC before committing

### Smithsonian 3D Digitization

- **Site:** [3d.si.edu](https://3d.si.edu/) — prefer objects marked **CC0 / Open Access**
- **Formats:** `.stl`, `.obj` (when download enabled)
- **License:** Many highlights are **CC0**; some objects have tighter terms — **read the object page**
- **Examples of interest:** Abraham Lincoln life masks / busts, other historical figure scans in Open Access
- **Fit:** Strong public-domain candidates when CC0 is confirmed

### Other museum / open-access scan portals

Search for CC0 or explicit public-domain full-figure scans (national museums, Wikimedia Commons 3D, Europeana). Same rules: per-object license, convert, re-anchor, validate normals.

---

## Suggested shortlist for “fun” phantoms

If adding a playful set alongside clinical meshes:

| Idea | Likely source | License watch |
|------|---------------|---------------|
| Low-poly modern person | Quaternius / Kenney | CC0 — preferred for shipping |
| Parametric “cartoonish” adult | MakeHuman / MPFB with extreme face/body targets | Core assets CC0 |
| *David* or *Venus de Milo* | Scan the World | Often NC — local-only unless a CC0/CC-BY scan is found |
| Lincoln (or similar) bust / figure | Smithsonian Open Access | Prefer CC0 objects only |
| Mixamo “Y Bot” style | Mixamo | Local-only; do not ship raw mesh |

Label fun meshes clearly in the UI (e.g. “demo / non-clinical”) so users do not confuse them with dosimetry reference phantoms.

---

## Conversion and integration reminders

1. Import in Blender → apply transforms → export binary STL (or MeshLab).
2. Scale so extents are **centimeters** (many game assets are meters or arbitrary units).
3. Orient head-first supine; posterior near `max(Y) ≈ 0`, crown near `max(Z) ≈ 0` — see the [integration checklist](../ADDITIONAL_PHANTOMS.md#integration-checklist).
4. Decimate to ~3k–8k faces when possible; re-orient faces coherently; load once through `Phantom` so normals recompute.
5. Record license + attribution + source URL in catalog metadata / `THIRD_PARTY_NOTICES` as appropriate.
6. Hash-pin the STL in `approved_asset_inventory.json`.

---

## Related documents

- [`ADDITIONAL_PHANTOMS.md`](../ADDITIONAL_PHANTOMS.md) — clinical sources + integration checklist + short summary of this page
- [`plans/AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](../plans/AUTOMATED_PHANTOM_LIBRARY_PLAN.md) — MPFB generation runbook
- [`LICENSE_COMPLIANCE.md`](../LICENSE_COMPLIANCE.md) — third-party license policy
- [`PRIVACY_AND_SENSITIVE_ASSETS.md`](../PRIVACY_AND_SENSITIVE_ASSETS.md) — binary STL admission
