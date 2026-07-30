# Character, Stylized, and Public-Domain Mesh Sources

Survey of free / open-license **full-body or humanoid** meshes that could be fun MyPySkinDose phantoms: realistic parametric humans, stylized game characters, and public-domain historical / classical figures.

This is a **candidate-source list**, not a commitment to ship any of these. Clinical dosimetry still prefers anatomical libraries and the MPFB catalog — see [`ADDITIONAL_PHANTOMS.md`](../ADDITIONAL_PHANTOMS.md) and [`plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](../plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md).

**Out of scope here:** isolated organs, bones, prosthetic/engineering mannequins, and **modern trademarked cartoon IPs**. Prefer original CC0 characters or clearly licensed sculpture scans. **Mickey Mouse:** only the **1928 Steamboat Willie** design is public domain in the US (as of 2024); later Mickey designs remain under copyright, and Disney trademarks still apply to branding / source confusion — treat Mickey as a legal special case, not a default fun phantom.

**Formats:** MyPySkinDose ships and loads **binary `.stl`**. Upstream files may be `.stl`, `.obj`, `.ply`, `.fbx`, or `.glTF` — convert with Blender or MeshLab, strip textures/colors, then follow the integration checklist.

**Before committing any STL to this repo:** verify the **per-model** license, convert to binary STL, run the [integration checklist](../ADDITIONAL_PHANTOMS.md#integration-checklist), and hash-pin the file per [`PRIVACY_AND_SENSITIVE_ASSETS.md`](../PRIVACY_AND_SENSITIVE_ASSETS.md).

---

## License cheat sheet (for shipping in a public repo)

| Tier | Examples | Shipping in MyPySkinDose |
|------|----------|--------------------------|
| **Safest** | CC0 / public domain / PDM | Redistribute with provenance note |
| **OK with care** | CC-BY, CC-BY-SA | Attribution (and share-alike for SA) on the **mesh asset** in notices / catalog metadata — does not relicense MIT app code |
| **Usually avoid shipping** | CC-BY-NC | Blocks commercial redistribution of the package |
| **Do not ship raw meshes** | Mixamo, many Daz “free” bases | Use in a private build only; EULAs forbid redistributing raw character files |
| **Special case** | Steamboat Willie–era Mickey fan meshes | PD character design ≠ free-for-all branding; prefer non-Disney cartoon sources |

Always re-check the model page — aggregators mix licenses.

**Conversion:** `.obj` / `.ply` / `.fbx` / `.glTF` → binary `.stl` in Blender or MeshLab. Scale to centimeters and re-anchor to the MyPySkinDose frame.

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

These make memorable phantoms (David on the table, Cosmic Buddha draped, etc.). **Prefer standing / reclining clothed full figures** — dose demos typically need a full body on the table. Busts and life masks are novelty fallbacks only. Recline and scale to cm; many scans are upright and meters- or mm-scale for printing.

**Nude classical art (Venus, David, many SMK casts):** fine as historical demos legally when licensed, but may be awkward in a clinical GUI — see plan decision **D1** in [`FUN_DEMO_PHANTOMS_PLAN.md`](../plans/FUN_DEMO_PHANTOMS_PLAN.md). Prefer **clothed / draped full-body** figures when avoiding that issue.

### Priority classical targets: Venus de Milo and Michelangelo’s David

| Figure | Recommended download | License | Notes |
|------|----------------------|---------|-------|
| **Venus de Milo** | SMK digital cast: [Sketchfab CC0](https://sketchfab.com/3d-models/venus-de-milo-aphrodite-of-milos-53082b5d6cef4c34a9701a2a24f58075), [Commons CC0 STL](https://commons.wikimedia.org/wiki/File:Venus_(Afrodite)_fra_Milo_-_KAS434_1.stl), high-res at [smk.dk/3d](https://www.smk.dk/3d) | **CC0 / PDM** | **Best classical shipping candidate** (license). Cast scan, not Louvre marble. Downscaled Sketchfab ~274k tris; decimate hard. |
| **Venus (Louvre scan)** | [Scan the World on Commons](https://commons.wikimedia.org/wiki/File:Scan_the_World_-_Venus_de_Milo.stl) (~29 MB) | **CC BY-SA 4.0** | Attribution + share-alike on mesh derivatives |
| **David** | [Scan the World on Commons](https://commons.wikimedia.org/wiki/File:David_(Michelangelo).stl) (~57 MB); also [MyMiniFactory object 2052](https://www.myminifactory.com/object/3d-print-michelangelo-s-david-in-florence-italy-2052) (Credit / Remix / **Commercial**) | **CC BY-SA 4.0** on Commons | **Easy to obtain**; large. Credit Scan the World; keep mesh derivatives SA-compatible |

**Integration effort (both):** low for acquisition, moderate for MyPySkinDose readiness — lay supine, scale height to a plausible table-phantom extent (or accept giant/miniature as a joke demo), close holes if needed, decimate to ~3k–8k faces, re-orient normals, smoke-test entrance/exit.

### Clothed / draped full-body statues (preferred for dose demos)

Full-body clothed scans **do exist**, but redistributable ones (CC0 / CC-BY / CC-BY-SA **without NC**) are scarcer than nudes and busts. Many Scan the World toga/robed figures are **Noncommercial** — reject those for shipping.

| Figure / type | Hub | License watch | Notes |
|---------------|-----|---------------|-------|
| **Cosmic Buddha** | [Smithsonian 3D](https://3d.si.edu/object/3d/buddha-draped-robes-portraying-realms-existence:d8c62be8-4ebc-11ea-b77f-2e728ce88125) | **CC0** (object page) | **Shipped** as `cosmic_buddha` (demo); standing ~151 cm; missing head/hands |
| **Petite Herculanaise** (draped woman) | [Cults](https://cults3d.com/en/3d-model/art/statue-of-a-woman-petite-herculanaise-at-the-louvre-paris) / [MMF 6356](https://www.myminifactory.com/object/3d-print-statue-of-a-woman-petite-herculanaise-at-the-louvre-paris-6356) / Zenodo STW | Cults **CC BY-SA**; STW/Zenodo **CC BY-NC-SA** | **Not shipped** — NC mirrors + Cults login; see provenance |
| **Ramesses II** colossal | [Commons STL](https://commons.wikimedia.org/wiki/File:Colossal_sculpture_of_Ramesses_II.stl) | **CC BY 4.0** | **Shipped** as `ramesses_ii` (demo; CLI/on-disk; GUI-hidden) |
| **Louvre Cults batch** (Socrates, Mattei Athena, Childebert, Draped Woman) | Cults Louvre account + STW Zenodo mirrors | Cults **PU** or **CC BY-SA**; Zenodo **CC BY-NC-SA 4.0** | **Not shipped** — reviewed 2026-07-23; local `tmp/STL-downloads-and-links/` only; see [`fun_phantom_provenance.md`](fun_phantom_provenance.md) |
| Other draped Buddha / Bodhisattva | SI / Commons / Scan the World | **Per object** | Prefer SI CC0 or Commons BY/SA; skip MMF NC |
| Scan the World toga / “robed man” | MyMiniFactory | Often **NC / Exclusive** | e.g. Altes Museum Toga — **do not ship** unless Commons BY/SA mirror |
| Greenough Washington / Greek Slave | Smithsonian | **CC0** when marked | Full figures but **nude / semi-nude** — not clothed; same D1 issue |

**Cults vs Scan the World:** When the same Louvre scan is **CC BY-SA** on Cults but **CC BY-NC-SA** on MyMiniFactory/Zenodo, treat **NC** as blocking for redistributable shipping until a clean non-NC source is confirmed. **CULTS PU** forbids redistributing digital files entirely ([Cults licenses](https://cults3d.com/en/licenses)).

### Busts / life masks (fallback only)

| Figure / type | Hub | License watch | Notes |
|---------------|-----|---------------|-------|
| **Abraham Lincoln** life mask / bust | [Smithsonian 3D](https://3d.si.edu/) | **CC0** when marked | Head-only; not typical dose geometry |
| **Helen Keller, Anne Sullivan**, other OA portraits | Smithsonian Open Access | **CC0** when marked | Filter Open Access / CC0 |
| Other Smithsonian people / cultural figures | [3d.si.edu Open Access highlights](https://3d.si.edu/collections/openaccesshighlights) | **CC0** when marked | Skip objects with tighter terms |
| SMK other casts (Apollo, Doryphoros, Discobolus, …) | [smk.dk/3d](https://www.smk.dk/3d) | Often **CC0 / PDM** | Many are nude classical — same sensitivity as Venus/David |

Busts: after orientation, scale so superior–inferior extent is readable (~20–40 cm) if used as fallback. Document scale in provenance.

### Scan the World (MyMiniFactory)

- **Site:** [myminifactory.com/scantheworld](https://www.myminifactory.com/scantheworld/)
- **Formats:** `.stl`, `.obj`
- **License:** **Per object** — some are commercial-friendly; some are NC. Do not generalize. For *David* / *Venus*, prefer the Wikimedia Commons copies above where the license is explicit CC BY-SA 4.0.
- **Fit:** Huge catalog of sculpture + historical scans; always open the license panel before downloading for shipping

### Smithsonian 3D Digitization

- **Site:** [3d.si.edu](https://3d.si.edu/) — prefer objects marked **CC0 / Open Access**
- **Formats:** `.stl`, `.obj` (when download enabled)
- **License:** Many highlights are **CC0**; some objects have tighter terms — **read the object page**
- **Fit:** Best hub for **CC0 cultural figures** — includes clothed full-body (Cosmic Buddha) and busts/life masks; always check the object page

### Other museum / open-access scan portals

Search for CC0 or explicit public-domain full-figure / bust scans (national museums, Wikimedia Commons 3D, Europeana, SMK). Same rules: per-object license, convert, re-anchor, validate normals.

---

## Public-domain / early cartoon characters

**Two layers:** (1) is the **character design** PD in the US for that year’s look? (2) is **this STL** CC0/CC-BY (not NC)? Video-game icons (Mario, Pac-Man, Sonic, …) are **still copyrighted** — out of scope.

| Character | Early form PD (US) | Mesh availability | Shipping note |
|-----------|--------------------|-------------------|---------------|
| **Steamboat Willie** Mickey | 2024 | [Commons CC BY 4.0](https://commons.wikimedia.org/wiki/File:Steamboat_Willie_3D_Model.stl); JoeBert / others CC-BY — see plan | **Shipped** as `steamboat_willie` (demo); stem only |
| **Popeye** (1929) | 2025 | e.g. [Thingiverse CC BY](https://www.thingiverse.com/thing:2417631); many others — verify | **Phase 2**; trademark-safe stem `popeye` |
| **Winnie-the-Pooh** (Milne book) | ~2022 | e.g. [Printables 1925 Public Domain](https://www.printables.com/model/1706462-winnie-the-pooh-pooh-bear-1925); Sketchfab CC-BY | **Phase 2**; **no Disney red shirt** |
| **Betty Boop** (*Dizzy Dishes*) | 2026 (early form) | Many modern Betty / NC Printables | **Weak** — PD look is poodle-flapper; trademarks |
| **Tintin** (early strips) | 2025 (US early) | Fan STLs often NC / personal-use | **Weak** — trademark risk |
| Original CC0 toons | N/A | Quaternius / Kenney | **Safest** filler |

### Mickey Mouse / Steamboat Willie (special case)

- **US copyright:** The **1928 Steamboat Willie** Mickey (and that short) entered the public domain on **2024-01-01**. Later Mickey designs remain copyrighted.
- **Trademark:** Disney still trademarks “Mickey Mouse” and related branding — avoid implying Disney affiliation.
- **Meshes:** Prefer Commons Cojocaru (**CC BY 4.0**); alternates in [`FUN_DEMO_PHANTOMS_PLAN.md`](../plans/FUN_DEMO_PHANTOMS_PLAN.md) § Steamboat Willie candidates. Avoid Sketchfab Free Standard / NC.
- **For this repo:** Stem/label **`steamboat_willie`** (not “Mickey Mouse”).

---

## Suggested shortlist for “fun” phantoms

| Idea | Likely source | License watch |
|------|---------------|---------------|
| Low-poly modern person | Quaternius / Kenney | CC0 — preferred generic |
| Parametric “cartoonish” adult | MakeHuman / MPFB | Core assets CC0 |
| Cosmic Buddha (draped full-body) | Smithsonian Open Access | **CC0** — preferred clothed full-body without nude issue |
| Lincoln (or similar) bust | Smithsonian Open Access | **CC0** — fallback only (not full-body) |
| *Venus de Milo* | **SMK CC0** cast | Safest classical license; D1 nude decision |
| Michelangelo’s *David* | Scan the World / Commons | **CC BY-SA 4.0** |
| Steamboat Willie | Commons CC BY 4.0 | Label `steamboat_willie` |
| Popeye / book Pooh | Thingiverse / Printables (verify) | Phase 2; early design only |
| Mixamo “Y Bot” | Mixamo | Local-only; do not ship |

Label fun meshes clearly in the UI (e.g. “demo / non-clinical”). **v1 execution (archived):**
[`plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md`](../plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md).
Broader backlog: [`plans/FUN_DEMO_PHANTOMS_PLAN.md`](../plans/FUN_DEMO_PHANTOMS_PLAN.md).

---

## Conversion and integration reminders

1. Import in Blender (or MeshLab) from `.stl` / `.obj` / `.ply` / `.fbx` / `.glTF` → apply transforms → export binary STL.
2. Scale so extents are **centimeters** (many game assets are meters or arbitrary units).
3. Orient head-first supine; posterior near `max(Y) ≈ 0`, crown near `max(Z) ≈ 0` — see the [integration checklist](../ADDITIONAL_PHANTOMS.md#integration-checklist). For fun ingest, call `transform_to_psd_frame` with **`--no-obj-y-up`**.
4. Decimate to ~3k–8k faces when possible; re-orient faces coherently; load once through `Phantom` so normals recompute.
5. Record license + attribution + source URL in provenance / NOTICE sidecars (BY/SA). Dependency `THIRD_PARTY_NOTICES.md` is not a substitute for mesh credits.
6. Hash-pin the STL in `approved_asset_inventory.json` with human review fields.

---

## Related documents

- [`ADDITIONAL_PHANTOMS.md`](../ADDITIONAL_PHANTOMS.md) — clinical sources + integration checklist + short summary of this page
- [`plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md`](../plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md) — v1 complete: Cosmic Buddha, Ramesses II, Steamboat shipped; Petite blocked
- [`plans/FUN_DEMO_PHANTOMS_PLAN.md`](../plans/FUN_DEMO_PHANTOMS_PLAN.md) — Venus/David (D1), Phase 2 PD cartoons
- [`plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](../plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md) — MPFB generation runbook
- [`LICENSE_COMPLIANCE.md`](../LICENSE_COMPLIANCE.md) — third-party license policy
- [`PRIVACY_AND_SENSITIVE_ASSETS.md`](../PRIVACY_AND_SENSITIVE_ASSETS.md) — binary STL admission
