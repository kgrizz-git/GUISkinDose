# Branding

The app icon is `src/guiskindose/gui/static/guiskindose_icon.svg`. It shows a supine patient on the
table, with the X-ray tube underneath and the skin-dose hotspot on the back. The GUI serves the SVG as
the browser favicon. `guiskindose_icon.ico` beside it is a multi-size raster copy for the native window
and the Windows and Linux taskbar.

[icon_candidates/](icon_candidates/) keeps the alternatives that were considered:

| File | Idea |
|---|---|
| `f_supine_side.svg` | Side view of the patient, tube under the table. This is the current icon. |
| `e_beam_on_body.svg` | Front silhouette with a beam cone landing on a hotspot. |
| `a_dose_map.svg` | Front silhouette with a dose hotspot. |
| `b_beam_cone.svg` | Beam cone onto a curved skin surface. |

All artwork is synthetic and uses the `DESIGN.md` palette. To change the icon, copy a candidate over
the app SVG and regenerate the ICO at 16–256 px. Both files need new approved-inventory hashes.
