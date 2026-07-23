# Settings phantom preview

The **Settings → Phantom Settings** panel includes a live 3D preview of the selected
**human** mesh on the support table and pad. No RDSR upload is required.

## What it shows

- Mesh identity (which human phantom is selected)
- Face-up / back-on-support pose (patient orientation)
- Body-habitus scales (`scale_lat`, `scale_ap`, `scale_lon`)
- Patient offsets (`d_lon`, `d_ver`, `d_lat`)

When multiple exams are loaded, offsets follow the **active exam** (same rule as the
Geometry preview). Global offset spinboxes on Settings apply when a single exam is loaded.

## Performance note

When a `{mesh}_reduced_1000t.stl` companion exists, the preview uses that lighter mesh for
snappy updates. **Dose calculation still uses the full STL.** Reduced preview bounds are
approximate — do not treat them as equal to calculation bounds.

## Limitations

- Plane and cylinder models show a short “preview available for human mesh” note instead of a plot.
- This panel does not replace the Geometry tab event/setup preview (which needs RDSR data).
- Demo / non-clinical meshes (for example Cosmic Buddha, Steamboat Willie) are **hidden by
  default**. To list them in a **Demo** section at the end of the mesh dropdown, set
  `"show_demo_phantoms": true` in `~/.mypyskindose/gui.json` (local preferences; not
  committed). Use demos for visuals only — not as dosimetry reference phantoms.
  Cosmic Buddha is missing its head and hands. Steamboat Willie must not be marketed as
  Disney “Mickey Mouse.” Ramesses II remains on disk for advanced/CLI use but is not
  listed in the GUI (excess stone/plinth geometry).

Related: [Phantom positioning and offsets](positioning_offsets.md).
