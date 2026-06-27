# Additional Anthropomorphic Phantoms

This document outlines potential sources for additional anthropomorphic phantoms in STL format (or formats convertible to STL) that could be used in MyPySkinDose.

## 1. Research & Open Source Repositories

Because generic 3D printing sites often yield non-medical models when searching for "phantom", it is best to focus on medical research hubs.

### XCAT (Extended Cardiac-Torso) Phantoms
The XCAT phantom is a highly detailed, widely used computational phantom in medical imaging.
*   **Source:** [Mesh50_XCAT (GitHub)](https://github.com/B-Auer/mesh50_XCAT)
*   **Description:** This repository, maintained by Benjamin Auer, provides mesh-based versions of the 4D extended cardiac-torso (XCAT) phantom. They are available in Head, Head-Torso-Abdominal, and Whole Body configurations, specifically designed for simulation software like GATE or Geant4.
*   **License:** MIT License (Distribution of these phantoms, free of charge, is permitted by the original XCAT developer team).

### Martinos Center Anthropomorphic Phantoms
*   **Source:** [Martinos Center Phantoms](https://phantoms.martinos.org/)
*   **Description:** Hosted by the Athinoula A. Martinos Center for Biomedical Imaging, this is a hub where researchers share CAD models of phantoms used in MRI and other imaging research. Includes highly realistic head and body phantoms.
*   **License:** Varies by model; typically available for research use.

### Zenodo
*   **Source:** [Zenodo](https://zenodo.org/)
*   **Description:** A general-purpose open repository heavily used by the academic community. Searching for terms like "anthropomorphic phantom STL" or "dosimetry phantom STL" often yields specialized models (like breast phantoms or patient-derived anatomical models) uploaded alongside research papers.
*   **License:** Varies (often Creative Commons).

## 2. Segmenting Clinical Data (DICOM to STL)

If pre-made STLs are insufficient, a common approach is to generate your own by segmenting open-source clinical scans.

*   **Source Data:** [The Cancer Imaging Archive (TCIA)](https://www.cancerimagingarchive.net/) is a massive public repository of anonymized clinical DICOM images (CT, MRI, etc.).
*   **Conversion:** You can download a DICOM dataset and use free, open-source medical image processing software like **3D Slicer** or **ImageJ** to segment the skin/body contour and export the resulting 3D mesh directly as an `.stl` file.
*   **Advantage:** Provides nearly infinite variations of patient body types.

## 3. General 3D Model Sites

Sites like Thingiverse, Cults3D, or CGTrader can be used, but require specific search terms to filter out non-medical models:
*   **Search terms:** `"anatomical phantom"`, `"dosimetry phantom"`, or `"medical imaging phantom"`.
*   *Note:* Ensure the mesh you download is a closed, watertight surface (a true solid), which is necessary for computational ray-tracing in MyPySkinDose.

## Integration Considerations for MyPySkinDose

If adding a custom STL to `src/mypyskindose/phantom_data/`, ensure the following:
1.  **Scale:** The STL coordinates must be scaled correctly (MyPySkinDose expects coordinates in **centimeters**).
2.  **Origin:** The origin `(0,0,0)` of the STL should make sense relative to the patient's anatomy (e.g., centered in the torso), to allow correct positioning relative to the simulated X-ray table.
3.  **Mesh Density:** Very high polygon counts will significantly slow down the geometric intersection calculations. Use a tool like MeshLab or Blender to decimate (reduce the polygon count of) the mesh before adding it.

---

## Added by Minimax M3

Reviewer notes on accuracy, gaps, and large-torso phantom recommendations.

### Accuracy review

- **Mesh50_XCAT license is misleading as written.** The *Mesh50 converter code* in `B-Auer/mesh50_XCAT` is MIT, but the underlying XCAT phantom data is distributed by the Duke/XCAT group under a separate research-and-clinical-use agreement; commercial redistribution typically requires a separate license. The bullet should make this distinction, or the "MIT" wording will mislead downstream distributors of MyPySkinDose.
- **"Closed watertight" is necessary but not sufficient.** MyPySkinDose's `check_hit` (`src/mypyskindose/beam_class.py:181`) classifies entrance vs. exit skin cells by the sign of `dot(v, n)`, and the table-hit test in `src/mypyskindose/geom_calc.py:521` assumes the triangle's normal points "upward (negative y direction)." A watertight mesh with **inconsistent winding or inverted normals** will silently mis-classify entrance/exit, producing wrong PSD with no error. The integration checklist should explicitly require consistent winding and outward-facing normals — `phantom_class.py:296` already has `_recompute_human_normals_from_triangles()` for exactly this reason, and any new phantom should be re-validated through that path.
- **The "scale: cm" requirement is correct but under-specified.** All shipped meshes put `y=0` at the back/table contact surface (the patient "sits" on the pad). New phantoms that place the origin at the geometric center of the bounding box will float above the table or sink into it, depending on the sign convention. Recommend stating: "the lowest skin-cell `y` coordinate should equal 0 (table-pad contact plane), with `+y` upward, and the patient lying along the `−z` direction."
- **Decimation targets are not given.** The shipped `*_reduced_1000t.stl` files cap the mesh at ~1000 triangles (≈50 KB). For interactive calculation this is a good upper bound; for high-fidelity PSD maps, 5–20k triangles is usually a safe ceiling. Worth stating explicitly.
- **"Decimate with MeshLab/Blender" glosses over the failure mode.** Some decimation algorithms flip triangle winding or recompute normals with the wrong orientation. The new phantom should be re-loaded by `Phantom` and verified: `Phantom._recompute_human_normals_from_triangles()` is the right re-derivation path and should be the documented expectation.

### Sources worth adding

- **ICRP Publication 145 mesh-type reference phantoms** (adult male/female, pediatric) — the current international standard for computational dosimetry, mesh-form, with a clear redistribution policy. Highest-relevance addition for a dosimetry tool.
- **BodyParts3D** (DBpedia) — large, well-cited open anatomical database; covers the whole body with anatomical labeling. License is CC-BY-SA, which is compatible with attribution-only projects.
- **Embodi3D** — purpose-built medical STL/3MF repository (anatomical models, often patient-derived). Quality is highly variable; treat as "candidate source," not "ready to ship."
- **NIH 3D Print Exchange** — small but well-curated; several public-domain anatomical models that have already passed basic watertight/normal checks.
- **Visible Human Project (NLM)** — public-domain cryosection data; can be segmented in 3D Slicer to produce high-fidelity phantoms, but the surface meshes are large and benefit from decimation.
- **MakeHuman + Blender** — parametric, not medical, but useful for generating body-habitus variants (ectomorph/mesomorph/endomorph) when a bariatric-specific dataset isn't available.
- **Dr. Paul Segars' XCAT page at Duke** (in addition to Mesh50) — hosts the canonical bariatric XCAT variants, the pediatric series, and the licensing FAQ. Mesh50 only ships one body habitus.
- **PLY → STL** — Zenodo, BodyParts3D, and several lab sites distribute PLY. Document the conversion: MeshLab `File → Export → STL` (binary), or `trimesh` (`mesh.export('out.stl')`). Note that some PLY files have per-vertex color attributes that balloon file size; strip before conversion.

### Specific recommendations for large patient torso phantoms

For "bariatric" or generally large-torso representation, the cheapest useful path is to **scale an existing adult mesh** with the GUI's `scale_lat` / `scale_ap` / `scale_lon` settings (clamped 0.5–2.0 in `phantom_class.py:281`). For clinical realism beyond ±20% in any axis, the next-best options, in order of cost vs. fidelity:

1. **TCIA + 3D Slicer "Flood Filling" / "Wrap" smoothing on a bariatric CT.** Public CTs exist in TCIA's "CT Colonography" and "Lung Screening" collections. Threshold the body contour, run "Wrap" smoothing (recommended over "Laplacian" for retaining a soft tissue feel), decimate to ~5k triangles, export as STL. This is the fastest path to a real bariatric surface.
2. **XCAT bariatric variant from Duke.** Highest anatomical fidelity; obtain via the Duke XCAT distribution agreement, not from Mesh50.
3. **ICRP 145 mesh phantoms** if you can attribute and ship them; otherwise use as the validation reference.
4. **Scaled shipped mesh (`adult_male`) as a last resort.** The clamp at 2.0 will not produce a true 400-lb patient, but is enough for moderate-habitus sensitivity studies.

Practical guidance for the resulting STL:

- **Triangle budget: 2k–5k triangles** for torso-only or whole-body bariatric phantoms. Going above 20k triangles will push per-event ray casting past 5 s, which is the user-noticeable threshold in the GUI.
- **Cap the mesh at the shoulders and mid-thigh.** Most fluoroscopy is cranio-caudal over the torso; including the full head and lower limbs roughly doubles triangle count with no PSD impact for cardiac/abdominal procedures. Crop early.
- **Anchor the back surface at `y = 0`.** The position logic in `phantom_class.py:362` translates the phantom by `+table_length/2` along `z` and applies RDSR table rotations, so a mesh that already sits at `y=0` on the back-of-the-body needs no further adjustment.
- **Re-derive normals after import** via the existing `Phantom._recompute_human_normals_from_triangles()` (line 296). The recompute is robust to winding because it derives the normal from the triangle vertex order — so as long as the STL is consistently wound (outward), the recompute will match. Mixed-winding meshes will still need manual repair in MeshLab (`Filters → Normals → Re-orient All Faces Coherently`).
- **Validate the entrance/exit classification** end-to-end with a known-good RDSR: a single anterior LAO projection on the new bariatric phantom should produce a PSD on the anterior surface, not the back. A flipped normal will show up here as PSD on the wrong side.
- **Body-habitus scaling interacts with cropping.** If you crop the original adult mesh, the GUI's `scale_lat`/`scale_ap`/`scale_lon` sliders (`phantom_class.py:281`) become the primary knob for the user. A cropped mesh that is missing the head will be visibly distorted by `scale_ap` because the anchor point (max-y) is the back-of-the-head, not the torso. For torso-only phantoms, the anchor should ideally be reset (the existing `_apply_human_scale` always anchors at `max(y)`; a torso-only phantom benefits from a manual `y`-anchor at the shoulder girdle).

### Cross-references already in this repo

- `src/mypyskindose/phantom_class.py:55` — `Phantom.__init__` is the single integration point.
- `src/mypyskindose/phantom_class.py:281` — `_apply_human_scale` is the existing scaling hook; the GUI sliders write into it.
- `src/mypyskindose/phantom_class.py:296` — `_recompute_human_normals_from_triangles` should be the documented normal-derivation path for any new phantom.
- `src/mypyskindose/gui/helpers.py:280` — `get_available_phantom_meshes()` is the GUI's discovery of `phantom_data/*.stl`; any new file dropped there shows up automatically (the function explicitly excludes `*_reduced_1000t`).
- `dev-docs/VENDOR_COORDINATE_SYSTEMS.md`, `dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md`, and the body-habitus plans in `dev-docs/plans/` cover the coordinate-frame side of the problem this doc doesn't touch.


## Added by Deepseek V4 Pro

### Overall assessment

The Minimax M3 section above is substantially accurate and well-researched. I verified its code references against the current codebase (commit context as of this writing). Below are additions, a few corrections, and independent recommendations.

### Corrections and clarifications

- **Coordinate system documentation vs. code reality.** `VENDOR_COORDINATE_SYSTEMS.md` is the canonical coordinate reference. Physical mesh geometry uses X as lateral/across-table, Y as vertical, and Z as longitudinal/along-table for head-first supine positioning, while historical PySkinDose plot aliases still show `X - LON`, `Y - VER`, and `Z - LAT`. Evidence: `position_patient_phantom_on_table` lowers the patient in Y (`dr=[0, -pad_thickness, 0]`) onto the pad, and `Phantom.position()` rotates around Z (`self.r[:, 2] += table_length/2`). The Minimax section's advice to anchor at `y=0` for the table contact plane is correct for the physical mesh convention.

- **Table-hit test normal dependency is overstated.** Minimax claims `geom_calc.py:521` "assumes the triangle's normal points 'upward (negative y direction).'" The docstring at line 509 does say this, but the intersection algorithm at `check_intersection` (lines 546–573) is Möller-Trumbore-like barycentric: the normal sign cancels out of the ray-plane distance `k` (both numerator and denominator flip), and the barycentric check is purely geometric and orientation-independent. The normal direction matters only for the source-above-triangle filter (line 603: "Start points above triangle returns False"), which is a guard, not the core hit-test. A watertight mesh with inverted normals would still produce correct hit/miss results in this code path; the Minimax paragraph overstates the severity.

- **ICRP 145 mesh phantoms.** Strongly agree this is the single most important missing source. These are the current international reference standard for computational dosimetry (ICRP Publication 145, 2020). The adult male/female and pediatric series are mesh-form, well-documented, and have a clear redistribution policy. If MyPySkinDose ships any new phantom, this should be first in line — both for dosimetric credibility and for validation of results against published reference values.

### Phantom inventory gap

AGENTS.md lists 5 available meshes: `hudfrid`, `adult_male`, `adult_female`, `junior_male`, `junior_female`. The `phantom_data/` directory also contains `senior_male` and `senior_female` — they are distinct meshes (different MD5 hashes) with the same 26,756-face topology as the adult/junior full-resolution variants. These should be listed in AGENTS.md and surfaced in the GUI's mesh selector. The `print_available_human_phantoms()` function in `__init__.py:22` already discovers them (it globs `*.stl` excluding `*reduced_1000t`), so they are functional but invisible to users of the documentation.

### Triangle counts of shipped meshes

| Mesh | Faces | File size |
|------|-------|-----------|
| adult_male / adult_female / junior_male / junior_female / senior_male / senior_female (full) | 26,756 | ~1.3 MB |
| hudfrid (full) | 13,674 | ~668 KB |
| All `*_reduced_1000t` variants | 1,000 | ~49 KB |

The Minimax recommendation of "5–20k triangles as a safe ceiling" is reasonable for interactive use, but note the shipped full meshes already exceed that ceiling at 26.8k faces. The reduced 1,000-face versions are adequate for quick preview but lose torso contour detail relevant to PSD hotspot localization. A practical sweet spot for new phantoms would be 3k–8k faces — detail comparable to hudfrid but with manageable ray-cast times.

### Additional sources for large-torso phantoms

Beyond the excellent TCIA + 3D Slicer workflow recommended above:

- **MakeHuman + Blender decimation pipeline.** MakeHuman generates parametric body meshes with sliders for weight, muscle, height, etc. Export as OBJ, load in Blender, use the "Decimate" modifier (Planar or Collapse mode, not Un-Subdivide) to target 3k–8k faces, export as binary STL. This is faster than segmenting CT data and produces consistently wound, watertight meshes. The main limitation is that MakeHuman's extreme-weight models are not bariatric-surgery-grade — they represent ~150 kg max — but they are useful for moderate-habitus sensitivity studies and require no IRB or data-use agreement.

- **Visible Human Project (NLM) segmentation.** The Minimax section mentions this but understates its value for large patients. The Visible Human Male dataset (the "Visible Korean Human" is also public) can be segmented in 3D Slicer with a higher threshold to capture the outer skin contour including subcutaneous adipose. The resulting mesh is extremely dense (100k+ faces from cryosection resolution) and must be aggressively decimated, but the surface detail fidelity is unmatched. Target 5k–10k faces for the decimated output.

### `_apply_human_scale` anchor behavior

Minimax correctly identifies that `_apply_human_scale` anchors at `(center_x, max_y, max_z)`. In the code's actual coordinate convention (Y=vertical, Z=longitudinal), this anchors scaling at the front-top of the head. For a torso-only bariatric mesh:

- `scale_ap` (Y) will expand/contract from the anterior chest surface toward the back — correct, keeps the back in table contact.
- `scale_lat` (X) is symmetric about the midline — correct.
- `scale_lon` (Z) will expand/contract from the head downward — **problematic for torso-only meshes** because the head is absent, so max_z becomes the shoulder/neck region, and scaling will asymmetrically stretch the upper torso more than the abdomen.

**Recommendation for torso-only phantoms:** before export from the modeling tool, add a small reference vertex at the crown-of-head position (or wherever the longitudinal anchor should be) to preserve correct scaling behavior without modifying `_apply_human_scale`. Alternatively, if modifying the code is acceptable, expose the anchor point as a parameter in `Phantom.__init__` (currently hardcoded at line 286–292).

### Cross-reference to settings surface

The GUI's **Settings → Phantom Settings → Body habitus scaling** sliders (`scale_lat`, `scale_ap`, `scale_lon`) write directly into `_apply_human_scale`. Any new phantom that is dropped into `phantom_data/` will automatically appear in the mesh selector (via `print_available_human_phantoms` / the GUI equivalent) and will be compatible with these sliders — *provided* the mesh is in centimeters, consistently wound, and has a meaningful `max_y` and `max_z` for the anchor. The validation steps in Minimax's "Practical guidance" bullet list (lines 80–87) remain the definitive checklist for new phantom integration.
