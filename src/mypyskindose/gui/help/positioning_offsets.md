# Phantom Positioning Offsets

These parameters control the initial position of the patient phantom relative to the X-ray table and beam.

## Parameters

### Latitude (X-axis)
- **Direction**: Lateral (side-to-side)
- **Effect**: Shifts the patient left or right relative to the beam
- **Units**: Centimeters

### Longitude (Y-axis)
- **Direction**: Longitudinal (head-foot)
- **Effect**: Shifts the patient toward the head (cranial) or feet (caudal)
- **Units**: Centimeters

### Rotation
- **Direction**: About the vertical axis
- **Effect**: Rotates the patient's orientation on the table
- **Units**: Degrees

## Tips for Adjusting Offsets

1. **Start with small adjustments** (1-5 cm) and observe the effect in the Geometry tab
2. **Check multiple events** to ensure positioning works across the entire procedure
3. **Document working values** for your system/procedure combinations

## Troubleshooting

| Problem | Try |
|---------|-----|
| Beam hits wrong body part | Adjust longitude offset |
| Beam misses patient | Check for large offset errors (try ±10-20 cm) |
| Patient appears rotated | Adjust rotation parameter |

---

**Note:** Coordinate effects may vary by manufacturer. See the technical documentation for vendor-specific details.
