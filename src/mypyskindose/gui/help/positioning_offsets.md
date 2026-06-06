# Phantom Positioning Offsets

These parameters control the initial position of the patient phantom relative to the X-ray table and beam.

## Overview

The patient offset settings (Longitudinal, Vertical, Lateral) shift the phantom position from its default location. These are **additional offsets** applied on top of the table offsets that are automatically determined from the RDSR data based on the manufacturer and model of the X-ray system.

**Note:** The automatic table offsets are applied "under the hood" during normalization and account for vendor-specific coordinate system conventions. The patient offsets here let you make further adjustments to position the patient correctly on the table.

## Parameters

### Longitudinal
Shifts the patient along the table (head-foot direction).

### Vertical  
Shifts the patient up or down relative to the table surface.

### Lateral
Shifts the patient side-to-side.

All values are in **centimeters**.

## Iterative Workflow

When the correct positioning is unknown:

1. **Start in the Geometry tab** — Enter an event number and click "Single Event" to see the current beam-patient geometry

2. **Check the beam position** — Observe where the beam intersects the patient phantom

3. **Adjust offsets in Settings** — If the position doesn't look right, modify the offset values here

4. **Return to Geometry** — Click "Single Event" again to see the updated position

5. **Test multiple events** — Check several events across the procedure to ensure positioning works for all irradiation events

6. **Repeat** until the beam intersects the expected anatomical region for the procedure type

## Tips

- Start with small adjustments (1-5 cm) and observe the effect
- Check the Geometry tab frequently — it's the fastest way to verify changes
- Document working values for your system/procedure combinations
- Different procedure types have characteristic beam positions (cardiac → chest, neuro → head, etc.)
