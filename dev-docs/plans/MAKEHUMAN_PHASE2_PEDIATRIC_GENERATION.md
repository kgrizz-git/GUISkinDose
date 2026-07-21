# Phase 2: Pediatric Phantom Generation

## Objective

Generate 4 pediatric phantoms (5-year and 10-year, male and female) using the MakeHuman pipeline established in Phase 1. These phantoms will fill the gap between the existing junior phantom (~15 years) and provide accurate dose estimation for pediatric fluoroscopic procedures.

## Prerequisites

**Inputs from Phase 1**:
- Working MakeHuman 1.2.0 installation
- Working Blender 3.6+ installation
- Validation script (`validate_phantom.py`)
- Integration test script (`test_mypyskindose_integration.py`)
- Coordinate system transformation workflow
- Test phantom (`makehuman_test_male.stl`) as reference

**Additional Requirements**:
- Phase 1 completion confirmed
- Test phantom passes all validation checks
- MyPySkinDose development environment active

## Target Phantoms

| Phantom Name | Age | Sex | Target Face Count | Priority |
|--------------|-----|-----|-------------------|----------|
| `pediatric_5y_male` | 5 years | Male | 3,000-5,000 | P1 |
| `pediatric_5y_female` | 5 years | Female | 3,000-5,000 | P1 |
| `pediatric_10y_male` | 10 years | Male | 3,000-5,000 | P1 |
| `pediatric_10y_female` | 10 years | Female | 3,000-5,000 | P1 |

## Pediatric Anthropometric Reference Data

Use CDC growth charts as reference for realistic pediatric dimensions:

**5-Year-Old (Median)**:
- Height: 110 cm (boys), 109 cm (girls)
- Weight: 18 kg (boys), 18 kg (girls)
- Chest circumference: ~55 cm
- Head circumference: ~50 cm

**10-Year-Old (Median)**:
- Height: 140 cm (boys), 140 cm (girls)
- Weight: 32 kg (boys), 33 kg (girls)
- Chest circumference: ~70 cm
- Head circumference: ~52 cm

## MakeHuman Parameter Configuration

### 5-Year-Old Parameters

**Male (5 years)**:
- **Age**: 5 years
- **Gender**: Male
- **Height**: 110 cm
- **Weight**: 18 kg
- **Muscle**: 30% (lower muscle mass than adults)
- **Body Proportions**: 
  - Head scale: 1.1 (larger head-to-body ratio)
  - Torso scale: 0.8
  - Limb scale: 0.7

**Female (5 years)**:
- **Age**: 5 years
- **Gender**: Female
- **Height**: 109 cm
- **Weight**: 18 kg
- **Muscle**: 25%
- **Body Proportions**:
  - Head scale: 1.1
  - Torso scale: 0.8
  - Limb scale: 0.7

### 10-Year-Old Parameters

**Male (10 years)**:
- **Age**: 10 years
- **Gender**: Male
- **Height**: 140 cm
- **Weight**: 32 kg
- **Muscle**: 40%
- **Body Proportions**:
  - Head scale: 1.05
  - Torso scale: 0.9
  - Limb scale: 0.85

**Female (10 years)**:
- **Age**: 10 years
- **Gender**: Female
- **Height**: 140 cm
- **Weight**: 33 kg
- **Muscle**: 35%
- **Body Proportions**:
  - Head scale: 1.05
  - Torso scale: 0.9
  - Limb scale: 0.85

## Generation Workflow (Per Phantom)

### Step 1: Create MakeHuman Model

**Manual Steps**:
1. Open MakeHuman
2. Start with default human model
3. Navigate to **Modelling** tab
4. Set parameters according to the specific phantom configuration
5. Save as `{phantom_name}.mhm` (e.g., `pediatric_5y_male.mhm`)

**Example for pediatric_5y_male**:
- Age slider: 5.0
- Gender: Male
- Height: 110 cm
- Weight: 18 kg
- Muscle: 30%
- Macros → Body Proportions → Head scale: 1.1
- Macros → Body Proportions → Torso scale: 0.8
- Macros → Body Proportions → Limb scale: 0.7

### Step 2: Export to OBJ

**Export Settings**:
- Format: OBJ (Wavefront)
- Scale: 1.0
- Export helpers: Unchecked
- Export clothes: Unchecked
- Export rig: Unchecked
- Filename: `{phantom_name}.obj`

### Step 3: Blender Processing

**Import and Transform**:
1. File → Import → Wavefront (.obj) → Select `{phantom_name}.obj`
2. Apply coordinate system transformation (from Phase 1):
   - Scale: ×0.01 (meters to centimeters)
   - Rotation: Rotate -90° around X axis, then 180° around Y axis (supine orientation)
   - Alignment: Set max Y = 0 (posterior back contact), max Z = 0 (head top), center X at 0
3. Apply transforms: Scale, Rotation, Location

**Mesh Decimation**:
1. Switch to Edit Mode (Tab)
2. Press `A` to select all vertices
3. Add Decimate modifier:
   - Ratio: 0.15 (higher than adults to preserve pediatric detail)
   - Target face count: 3,000-5,000
4. Apply modifier
5. Verify face count in Stats panel

**Mesh Repair** (if needed):
1. Mesh → Clean Up → Merge By Distance (threshold: 0.01 cm)
2. Mesh → Normals → Recalculate Outside
3. Check for holes with 3D Print Toolbox (if available)

### Step 4: Export to STL

**Export Settings**:
- Format: STL
- Selection Only: Checked
- Batch Mode: Off
- Scale: 1.0
- ASCII: Unchecked (binary STL)
- Filename: `{phantom_name}.stl`

### Step 5: Validation

**Run validation script**:
```bash
python validate_phantom.py {phantom_name}.stl
```

**Expected validation results**:
- File exists: True
- Loadable: True
- Face count: 3,000-5,000
- Coordinate scale: centimeters
- Y range (AP): -25.0 to 0.0 cm
- Z range (S-I): -110.0 to 0.0 cm (5y) or -140.0 to 0.0 cm (10y)
- Watertight: True
- Passed: True

### Step 6: MyPySkinDose Integration Test

**Run integration test**:
```python
from pathlib import Path
from mypyskindose import Phantom, PyskindoseSettings, load_settings_example_json

settings = PyskindoseSettings(load_settings_example_json())
phantom_dim = settings.phantom.dimension
stl_path = Path("{phantom_name}.stl")

phantom = Phantom(
    phantom_model="human",
    phantom_dim=phantom_dim,
    human_mesh=("{phantom_name}", stl_path)
)

print(f"✓ {phantom_name} loaded successfully")
print(f"  Vertices: {len(phantom.r)}")
print(f"  Face count: {len(phantom.r) // 3}")
```

### Step 7: Parameter Documentation

Create documentation file `{phantom_name}_parameters.md`:

```markdown
# Phantom Parameter Documentation: {phantom_name}

## MakeHuman Parameters
- Age: {age} years
- Gender: {sex}
- Height: {height} cm
- Weight: {weight} kg
- Muscle: {muscle}%
- Head scale: {head_scale}
- Torso scale: {torso_scale}
- Limb scale: {limb_scale}

## Blender Processing
- Scale transformation: Meters to centimeters (×0.01)
- Y alignment: Back surface to Y=0 (AP range: {y_min:.2f} to 0.00 cm)
- Z alignment: Top of head to Z=0 (S-I range: {z_min:.2f} to 0.00 cm)
- Rotation: Supine orientation (head toward -Z, back at Y=0)
- Decimation ratio: {ratio}
- Final face count: {face_count}

## Validation Results
- Coordinate scale: Centimeters
- Y range (AP): {y_min:.2f} to 0.00 cm
- Z range (S-I): {z_min:.2f} to 0.00 cm
- Watertight: Yes
- MyPySkinDose integration: Passed

## Anthropometric Validation
- Expected height: {expected_height} cm
- Actual height: {actual_height} cm
- Expected weight: {expected_weight} kg
- Actual weight estimate: {actual_weight} kg
- Notes: {validation_notes}
```

## Batch Processing

To improve efficiency, process phantoms in this order:

1. **pediatric_5y_male** (establish baseline for 5-year parameters)
2. **pediatric_5y_female** (copy male parameters, adjust gender)
3. **pediatric_10y_male** (adjust parameters for 10-year)
4. **pediatric_10y_female** (copy male parameters, adjust gender)

**Parameter reuse strategy**:
- Save MakeHuman macro files for each age group
- Use same body proportions for same age, different sex
- Adjust only gender-specific parameters (muscle mass, slight height differences)

## Pediatric-Specific Considerations

### Head-to-Body Ratio
Pediatric patients have larger head-to-body ratios than adults. Ensure:
- Head scale is 1.05-1.1 (vs 1.0 for adults)
- This affects C-arm positioning and dose distribution
- Validate head size against CDC growth charts

### Torso Dimensions
Pediatric torsos are smaller relative to total height:
- Torso scale: 0.8-0.9 (vs 1.0 for adults)
- Affects table positioning and field size
- Ensure Y-range validation matches expected torso length

### Limb Proportions
Pediatric limbs are shorter:
- Limb scale: 0.7-0.85 (vs 1.0 for adults)
- Affects patient positioning on table
- May need to adjust Z-positioning in MyPySkinDose

### Surface Area Considerations
Pediatric patients have different surface-area-to-weight ratios:
- Affects backscatter correction factors
- May need pediatric-specific correction factors
- Document surface area for future reference

## Validation Against Existing Phantoms

Compare generated pediatric phantoms with existing `junior_male`/`junior_female`:

### Height Comparison
```python
# Compare phantom heights (measured along Z axis)
def get_phantom_height(phantom):
    z_range = abs(phantom.r[:, 2].min() - phantom.r[:, 2].max())
    return z_range

settings = PyskindoseSettings(load_settings_example_json())
phantom_dim = settings.phantom.dimension

# Load existing junior phantom (~15y, ~138 cm height)
junior = Phantom("human", phantom_dim, "junior_male")
junior_height = get_phantom_height(junior)

# Load new pediatric phantom
pediatric_10y = Phantom("human", phantom_dim, ("pediatric_10y_male", Path("pediatric_10y_male.stl")))
pediatric_height = get_phantom_height(pediatric_10y)

print(f"Junior height: {junior_height:.1f} cm")
print(f"Pediatric 10y height: {pediatric_height:.1f} cm")
print(f"Difference: {junior_height - pediatric_height:.1f} cm")
```

Expected: Junior (~15 years) should be 10-15 cm taller than 10-year phantom.

### Mesh Density Comparison
- Junior: 26,756 faces (full resolution)
- Pediatric target: 3,000-5,000 faces
- Pediatric should have lower density due to smaller size

## Troubleshooting Pediatric-Specific Issues

### Issue: Head size seems too large/small
**Solution**: Verify head scale parameter against CDC head circumference data. Adjust head scale in MakeHuman and regenerate.

### Issue: Torso too short for procedures
**Solution**: Pediatric torsos are naturally shorter. Ensure table positioning in MyPySkinDose accounts for this. Consider extending torso scale slightly if needed for procedural coverage.

### Issue: Face count too high for small phantom
**Solution**: Pediatric phantoms can use lower face counts (3k minimum) due to smaller surface area. Increase decimation ratio to 0.2-0.25 if needed.

### Issue: Limbs interfere with table positioning
**Solution**: MakeHuman limb scale affects arm position. If arms interfere with table, adjust limb scale or pose arms differently in MakeHuman before export.

## Deliverables Checklist

For each of the 4 phantoms:

- [ ] MakeHuman `.mhm` file saved
- [ ] OBJ export completed
- [ ] Blender transformation applied
- [ ] Decimation to target face count (3k-5k)
- [ ] STL export completed
- [ ] Validation script passed
- [ ] MyPySkinDose integration test passed
- [ ] Parameter documentation completed
- [ ] Anthropometric validation completed

**Overall deliverables**:
- [ ] 4 pediatric STL files in `phantom_data/` directory
- [ ] 4 parameter documentation files
- [ ] Validation summary report
- [ ] Comparison with existing junior phantoms
- [ ] Lessons learned document

## Validation Summary Report Template

```markdown
# Pediatric Phantom Generation - Validation Summary

## Phantoms Generated
1. pediatric_5y_male.stl - Status: {PASS/FAIL}
2. pediatric_5y_female.stl - Status: {PASS/FAIL}
3. pediatric_10y_male.stl - Status: {PASS/FAIL}
4. pediatric_10y_female.stl - Status: {PASS/FAIL}

## Validation Results Summary
| Phantom | Face Count | Height (cm) | Watertight | MyPySkinDose Load | Anthropometric Check |
|---------|------------|-------------|------------|-------------------|----------------------|
| pediatric_5y_male | {count} | {height} | {yes/no} | {yes/no} | {yes/no} |
| pediatric_5y_female | {count} | {height} | {yes/no} | {yes/no} | {yes/no} |
| pediatric_10y_male | {count} | {height} | {yes/no} | {yes/no} | {yes/no} |
| pediatric_10y_female | {count} | {height} | {yes/no} | {yes/no} | {yes/no} |

## Comparison with Existing Phantoms
- Junior male height: {junior_height} cm
- Pediatric 10y male height: {pediatric_height} cm
- Difference: {difference} cm (expected: 10-15 cm)

## Issues Encountered
- {issue_1}
- {issue_2}

## Resolutions Applied
- {resolution_1}
- {resolution_2}

## Recommendations for Adult Generation (Phase 3)
- {recommendation_1}
- {recommendation_2}
```

## Success Criteria

Phase 2 is complete when:

1. All 4 pediatric phantoms are generated
2. All phantoms pass validation script checks
3. All phantoms load successfully in MyPySkinDose
4. Anthropometric validation confirms realistic dimensions
5. Heights follow expected progression (5y < 10y < junior)
6. Face counts are in target range (3k-5k)
7. Parameter documentation is complete for all phantoms
8. Validation summary report is completed
9. All STL files are ready for integration in Phase 5

## Handoff to Phase 3

Upon Phase 2 completion, provide:
- 4 pediatric STL files
- 4 parameter documentation files
- Validation summary report
- Lessons learned from pediatric generation
- Updated validation script (if modified)
- Any adjustments to coordinate transformation workflow
- Recommendations for adult phantom parameters

These artifacts will serve as the foundation for adult ectomorph/mesomorph/endomorph generation in Phase 3.
