# Phantom Positioning and Offset Parameters

This guide explains how to use the Settings and Geometry tabs to position the patient phantom correctly when the optimal offsets are not known from RDSR data.

## Overview

Accurate dose calculations depend on correctly positioning the patient phantom relative to the X-ray beam. The RDSR file provides table position and beam angle information, but the initial positioning of the patient on the table often requires manual adjustment through offset parameters.

## Coordinate System

MyPySkinDose uses a unified internal coordinate system. For detailed vendor-specific coordinate transformations, see the technical documentation on [Vendor Coordinate Systems](../../dev-docs/VENDOR_COORDINATE_SYSTEMS.md).

### Quick Reference

| Parameter | Direction | Effect of Positive Values |
|-----------|-----------|---------------------------|
| Latitude (X) | Lateral (side-to-side) | Moves patient left relative to beam |
| Longitude (Y) | Longitudinal (head-foot) | Moves patient toward head (cranial) |
| Rotation | About vertical axis | Rotates patient clockwise (when viewed from above) |

**Note:** The exact effect of offset parameters may vary depending on the X-ray system manufacturer. The coordinate transformations in `normalization_settings.json` account for vendor-specific conventions.

## Iterative Positioning Workflow

When correct positioning is unknown, use this iterative approach:

### Step 1: Visualize Events

1. Go to the **Geometry** tab
2. Enter an event number in the "Event Number" field
3. Click **Single Event** to render the beam and patient position
4. Observe where the beam intersects the patient phantom

### Step 2: Identify Positioning Issues

Common positioning problems:

| Issue | Possible Cause |
|-------|---------------|
| Beam hits wrong body region | Patient offset needs adjustment |
| Beam misses patient entirely | Large offset error or RDSR data issue |
| Beam at unexpected angle | May be correct for procedure type, or vendor normalization issue |

### Step 3: Adjust Offsets

1. Go to the **Settings** tab
2. Locate the "Phantom Positioning" section
3. Adjust offset values:
   - **Latitude**: Shifts patient laterally (side-to-side)
   - **Longitude**: Shifts patient along table (head-foot direction)
   - **Rotation**: Rotates patient orientation
4. Return to Geometry tab and click **Single Event** again

### Step 4: Check Multiple Events

1. Test several events across the procedure (early, middle, late)
2. Verify that the beam intersects the expected body region for all events
3. Procedures like cardiac catheterization should show beams clustered around the chest

### Step 5: Iterate

Repeat steps 3-4 until positioning looks correct across representative events.

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

- **Start with known procedure types**: Cardiac, neuro, abdominal procedures have characteristic beam positions
- **Use the Geometry tab frequently**: It's the fastest way to verify positioning changes
- **Check the Data tab**: Review normalized table positions to understand the range of motion
- **Document working offsets**: Once you find good offsets for a system/procedure combination, save them

## Getting More Help

For detailed technical information about:
- **Coordinate system conventions**: See [VENDOR_COORDINATE_SYSTEMS.md](../../dev-docs/VENDOR_COORDINATE_SYSTEMS.md)
- **Normalization settings**: See `normalization_settings.json` in the package
- **GUI workflow**: Use the help buttons in the Settings and Geometry tabs

## Future Improvements

This documentation will be enhanced as we gather more information about:
- Vendor-specific coordinate system behavior
- Typical offset values for common system/table combinations
- Procedure-specific positioning presets
