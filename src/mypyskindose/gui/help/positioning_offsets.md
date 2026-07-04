# Phantom Positioning and Offset Parameters

This guide explains how to use the Settings and Geometry tabs to position the patient phantom correctly when the optimal offsets are not known from RDSR data.

## Overview

The patient offset settings shift the phantom position from its default location. These are **additional offsets** applied on top of the table offsets that are automatically determined from the RDSR data based on the manufacturer and model of the X-ray system.

**Note:** The automatic table offsets are applied "under the hood" during normalization and account for vendor-specific coordinate system conventions. The patient offsets here let you make further adjustments to position the patient correctly on the table.

## Coordinate System

MyPySkinDose uses a normalized calculation frame plus historical PySkinDose/DICOM table-position aliases. RDSRs name the source fields `TableLongitudinalPosition`, `TableHeightPosition`, and `TableLateralPosition`; they do not call those fields `X`, `Y`, or `Z`. For detailed vendor-specific coordinate transformations, see the technical documentation on <a href="../../../dev-docs/VENDOR_COORDINATE_SYSTEMS.md" target="_blank">Vendor Coordinate Systems</a>.

### Quick Reference

| Control | Calculation field | Existing plot alias | Physical effect for head-first supine |
|---|---|---|---|
| Patient lateral / width | `d_lat` / patient scale | `X - LON / PT L-R` | Side-to-side placement after normalized geometry is built |
| Patient longitudinal / head-foot | `d_lon` / patient scale | `Z - LAT / PT S-I` | Head-foot placement after normalized geometry is built |
| Patient AP / vertical | `d_ver` / patient scale | `Y - VER / PT A-P` | Up-down placement |
| Rotation | patient rotation setting | about vertical axis | Rotates patient around the table-height axis |

The `LON`, `VER`, and `LAT` plot aliases are historical PySkinDose labels inherited from DICOM/operator table-coordinate names after vendor normalization. Siemens and Philips use that DICOM/operator convention. GE raw data uses patient-anatomy longitudinal and lateral naming instead; MyPySkinDose swaps GE raw lateral/longitudinal into the common plotted frame during normalization. For developer-level details, see `dev-docs/VENDOR_COORDINATE_SYSTEMS.md`.

All values are in **centimeters**. In the normalized frame, **+Y (vertical) points down** toward the floor, and the `(0, 0, 0)` origin is the beam isocenter, which coincides with the table head-end when the table-position readout is zero.

**Note:** The exact effect of offset parameters may vary depending on the X-ray system manufacturer. The coordinate transformations in `normalization_settings.json` account for vendor-specific conventions.

Reproducible setting keys include `scale_lat`, `scale_ap`, and `scale_lon` for human phantom body-habitus scaling, plus `table_origin` metadata for manual table-origin overrides.

## Iterative Workflow

When the correct positioning is unknown:

1. **Start in the Geometry tab** — Enter an event number and click "Single Event" to see the current beam-patient geometry

2. **Check the beam position** — Observe where the beam intersects the patient phantom

3. **Adjust offsets** — Use the **Geometry** tab sliders for live 3D preview. In **multi-exam** mode, pick the **Selected exam** in the Geometry tab (or click an exam on the Upload tab) and use **Show all exams in preview** when you need to see every exam's beams together. Edit values under **Settings → Per-exam corrections** for per-exam offsets, or **Settings → Phantom Settings** for single-exam global offsets. Table offsets from vendor normalization are shown read-only; override the table origin in Geometry or **Per-exam corrections → Advanced: table origin** when auto-detection is wrong.

4. **Return to Geometry** — Click "Single Event" again to see the updated position (slider moves debounce ~250 ms)

5. **Test multiple events** — Check several events across the procedure to ensure positioning works for all irradiation events

6. **Repeat** until the beam intersects the expected anatomical region for the procedure type

## Multiple exams

When more than one exam is loaded:

- **Selected exam** — Geometry sliders and the 3D preview phantom use the exam chosen in the **Selected exam** dropdown.
- **Per-exam offsets** — Each exam keeps its own patient offset (`lon` / `ver` / `lat`). Calculate uses every exam's settings; the Calculate tab summarizes offsets per exam.
- **Composite preview** — Enable **Show all exams in preview** to draw all exams' events together while the phantom stays at the selected exam's offset (positioning only).
- **Settings** — Global Phantom patient spinboxes are hidden in multi-exam mode; use Geometry or **Settings → Per-exam corrections** instead.

## Troubleshooting

### Beam Projects to Wrong Body Part

If the beam consistently hits the wrong anatomical region:

1. **Check vendor normalization** — Ensure your system manufacturer/model is supported in `normalization_settings.json`
2. **Adjust longitude offset** — Most common fix for cranial/caudal positioning errors
3. **Check procedure type** — Cardiac procedures should cluster around chest; neurovascular around head

### Beam Misses Patient Entirely

This suggests a large offset error:

1. Check if RDSR data includes valid table position information
2. Try larger offset adjustments (±10-20 cm)
3. Verify the correct phantom model is selected

### Rotations Appear Incorrect

If beam angles seem reversed:

1. May indicate unsupported vendor requiring coordinate normalization
2. Check `VENDOR_COORDINATE_SYSTEMS.md` for known vendor issues
3. Consider reporting the issue with anonymized RDSR sample

## Tips

- Start with small adjustments (1-5 cm) and observe the effect
- Check the Geometry tab frequently — it's the fastest way to verify changes
- Document working values for your system/procedure combinations
- Different procedure types have characteristic beam positions (cardiac → chest, neuro → head, etc.)

## Getting More Help

For detailed technical information about:
- **Coordinate system conventions**: See <a href="../../../dev-docs/VENDOR_COORDINATE_SYSTEMS.md" target="_blank">VENDOR_COORDINATE_SYSTEMS.md</a>
- **Normalization settings**: See `normalization_settings.json` in the package
- **GUI workflow**: Use the help buttons in the Settings and Geometry tabs
