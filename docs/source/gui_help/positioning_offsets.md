# Phantom Positioning and Offset Parameters

This guide explains how to use the Settings and Geometry tabs to position the patient phantom correctly when the optimal offsets are not known from RDSR data.

## Overview

The patient offset settings (Longitudinal, Vertical, Lateral) shift the phantom position from its default location. These are **additional offsets** applied on top of the table offsets that are automatically determined from the RDSR data based on the manufacturer and model of the X-ray system.

**Note:** The automatic table offsets are applied "under the hood" during normalization and account for vendor-specific coordinate system conventions. The patient offsets here let you make further adjustments to position the patient correctly on the table.

## Coordinate System

MyPySkinDose uses a unified internal coordinate system. For detailed vendor-specific coordinate transformations, see the technical documentation on <a href="../../../dev-docs/VENDOR_COORDINATE_SYSTEMS.md" target="_blank">Vendor Coordinate Systems</a>.

### Quick Reference

| Parameter | Direction | Effect of Positive Values |
|-----------|-----------|---------------------------|
| Lateral (X) | Side-to-side | Moves patient left relative to beam |
| Longitudinal (Y) | Head-foot | Moves patient toward head (cranial) |
| Vertical (Z) | Up-down | Moves patient up (away from table surface) |
| Rotation | About vertical axis | Rotates patient clockwise (when viewed from above) |

Coordinate axes (X→Lateral, Y→Longitudinal, Z→Vertical) match the technical documentation.[^coord]

[^coord]: X→Lateral, Y→Longitudinal, Z→Vertical.

All values are in **centimeters**.

**Note:** The exact effect of offset parameters may vary depending on the X-ray system manufacturer. The coordinate transformations in `normalization_settings.json` account for vendor-specific conventions.

## Iterative Workflow

When the correct positioning is unknown:

1. **Start in the Geometry tab** — Enter an event number and click "Single Event" to see the current beam-patient geometry

2. **Check the beam position** — Observe where the beam intersects the patient phantom

3. **Adjust offsets in Settings** — If the position doesn't look right, modify the offset values here

4. **Return to Geometry** — Click "Single Event" again to see the updated position

5. **Test multiple events** — Check several events across the procedure to ensure positioning works for all irradiation events

6. **Repeat** until the beam intersects the expected anatomical region for the procedure type

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
