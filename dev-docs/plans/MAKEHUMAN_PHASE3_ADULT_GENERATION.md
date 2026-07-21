# Phase 3: Adult Phantom Generation

## Objective

Generate 6 adult phantoms representing ectomorph (thin), mesomorph (average), and endomorph (heavy) body types for both male and female anatomies. These phantoms will provide a spectrum of adult body habitus for dose distribution studies and complement the existing adult_male/adult_female phantoms.

## Prerequisites

**Inputs from Phase 1**:
- Working MakeHuman 1.2.0 installation
- Working Blender 3.6+ installation
- Validation script (`validate_phantom.py`)
- Integration test script (`test_mypyskindose_integration.py`)
- Coordinate system transformation workflow

**Inputs from Phase 2**:
- Pediatric phantom generation experience
- Lessons learned from parameter tuning
- Updated validation scripts (if modified)

**Additional Requirements**:
- Phase 2 completion confirmed
- Pediatric phantoms pass all validation checks
- Understanding of MakeHuman parameter effects on mesh geometry

## Target Phantoms

| Phantom Name | Body Type | Sex | BMI Range | Target Face Count | Priority |
|--------------|-----------|-----|-----------|-------------------|----------|
| `adult_ectomorph_male` | Thin (ectomorph) | Male | 18.5-20 | 5,000-8,000 | P1 |
| `adult_ectomorph_female` | Thin (ectomorph) | Female | 18.5-20 | 5,000-8,000 | P1 |
| `adult_mesomorph_male` | Average (mesomorph) | Male | 22-25 | 5,000-8,000 | P1 |
| `adult_mesomorph_female` | Average (mesomorph) | Female | 22-25 | 5,000-8,000 | P1 |
| `adult_endomorph_male` | Heavy (endomorph) | Male | 28-30 | 5,000-8,000 | P1 |
| `adult_endomorph_female` | Heavy (endomorph) | Female | 28-30 | 5,000-8,000 | P1 |

## Adult Anthropometric Reference Data

Use standard adult anthropometric data for realistic body dimensions:

**Height Reference (Median Adults)**:
- Male: 175 cm
- Female: 162 cm

**Weight Reference by Body Type**:
- Ectomorph (BMI 19): Male 58 kg, Female 50 kg
- Mesomorph (BMI 23.5): Male 72 kg, Female 62 kg
- Endomorph (BMI 29): Male 89 kg, Female 76 kg

**Body Dimension Estimates**:
- Chest circumference: Ectomorph 85-90 cm, Mesomorph 95-100 cm, Endomorph 110-120 cm
- Waist circumference: Ectomorph 70-75 cm, Mesomorph 80-85 cm, Endomorph 95-105 cm
- Hip circumference: Ectomorph 85-90 cm, Mesomorph 95-100 cm, Endomorph 110-120 cm

## MakeHuman Parameter Configuration

### Ectomorph Parameters (Thin)

**Male Ectomorph**:
- **Age**: 25 years
- **Gender**: Male
- **Height**: 175 cm
- **Weight**: 58 kg
- **Muscle**: 20% (low muscle mass)
- **Body Proportions**:
  - Head scale: 1.0
  - Torso scale: 0.9 (narrower torso)
  - Limb scale: 0.85 (thinner limbs)
  - Waist scale: 0.8
  - Chest scale: 0.85

**Female Ectomorph**:
- **Age**: 25 years
- **Gender**: Female
- **Height**: 162 cm
- **Weight**: 50 kg
- **Muscle**: 15%
- **Body Proportions**:
  - Head scale: 1.0
  - Torso scale: 0.9
  - Limb scale: 0.85
  - Waist scale: 0.8
  - Chest scale: 0.85
  - Hip scale: 0.9

### Mesomorph Parameters (Average)

**Male Mesomorph**:
- **Age**: 25 years
- **Gender**: Male
- **Height**: 175 cm
- **Weight**: 72 kg
- **Muscle**: 60% (moderate muscle mass)
- **Body Proportions**:
  - Head scale: 1.0
  - Torso scale: 1.0 (normal proportions)
  - Limb scale: 1.0
  - Waist scale: 1.0
  - Chest scale: 1.0

**Female Mesomorph**:
- **Age**: 25 years
- **Gender**: Female
- **Height**: 162 cm
- **Weight**: 62 kg
- **Muscle**: 50%
- **Body Proportions**:
  - Head scale: 1.0
  - Torso scale: 1.0
  - Limb scale: 1.0
  - Waist scale: 1.0
  - Chest scale: 1.0
  - Hip scale: 1.0

### Endomorph Parameters (Heavy)

**Male Endomorph**:
- **Age**: 25 years
- **Gender**: Male
- **Height**: 175 cm
- **Weight**: 89 kg
- **Muscle**: 40% (moderate muscle under fat)
- **Body Proportions**:
  - Head scale: 1.0
  - Torso scale: 1.15 (wider torso)
  - Limb scale: 1.1 (thicker limbs)
  - Waist scale: 1.25
  - Chest scale: 1.15

**Female Endomorph**:
- **Age**: 25 years
- **Gender**: Female
- **Height**: 162 cm
- **Weight**: 76 kg
- **Muscle**: 35%
- **Body Proportions**:
  - Head scale: 1.0
  - Torso scale: 1.15
  - Limb scale: 1.1
  - Waist scale: 1.25
  - Chest scale: 1.15
  - Hip scale: 1.2

## Generation Workflow (Per Phantom)

### Step 1: Create MakeHuman Model

**Manual Steps**:
1. Open MakeHuman
2. Start with default human model
3. Navigate to **Modelling** tab
4. Set parameters according to the specific body type configuration
5. Save as `{phantom_name}.mhm` (e.g., `adult_ectomorph_male.mhm`)

**Example for adult_ectomorph_male**:
- Age slider: 25.0
- Gender: Male
- Height: 175 cm
- Weight: 58 kg
- Muscle: 20%
- Macros → Body Proportions → Head scale: 1.0
- Macros → Body Proportions → Torso scale: 0.9
- Macros → Body Proportions → Limb scale: 0.85
- Macros → Body Proportions → Waist scale: 0.8
- Macros → Body Proportions → Chest scale: 0.85

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
   - Ratio: 0.12 (target 5k-8k faces)
   - Target face count: 5,000-8,000
4. Apply modifier
5. Verify face count in Stats panel

**Mesh Repair** (if needed):
1. Mesh → Clean Up → Merge By Distance (threshold: 0.01 cm)
2. Mesh → Normals → Recalculate Outside
3. Check for holes with 3D Print Toolbox (if available)

**Full-Body Preservation**:
- Maintain full-body watertight meshes for all standard phantoms so that top-of-head alignment (`Z = 0.0`), body habitus scaling (`_apply_human_scale`), table positioning, and 3D geometry plots work consistently.

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
- Face count: 5,000-8,000
- Coordinate scale: centimeters
- Y range (AP): -35.0 to 0.0 cm
- Z range (S-I): -175.0 to 0.0 cm (male) or -162.0 to 0.0 cm (female)
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

# Test scaling (endomorph should scale differently)
phantom._apply_human_scale((1.1, 1.0, 1.0))
print(f"✓ Scaling test passed")
```

### Step 7: Body Type Validation

**Validate body type characteristics**:
```python
# Calculate torso width and AP thickness
def analyze_phantom_dimensions(phantom):
    # Get torso region (approximately Z=-20 to Z=-80 cm from head top)
    torso_mask = (phantom.r[:, 2] < -20) & (phantom.r[:, 2] > -80)
    torso_vertices = phantom.r[torso_mask]
    
    # Calculate dimensions
    x_range = float(torso_vertices[:, 0].max() - torso_vertices[:, 0].min())
    y_range = float(torso_vertices[:, 1].max() - torso_vertices[:, 1].min())
    
    return {
        'torso_width_cm': x_range,
        'torso_thickness_cm': y_range,
        'total_vertices': len(phantom.r)
    }

settings = PyskindoseSettings(load_settings_example_json())
phantom_dim = settings.phantom.dimension

# Compare body types
ectomorph = Phantom("human", phantom_dim, ("adult_ectomorph_male", Path("adult_ectomorph_male.stl")))
mesomorph = Phantom("human", phantom_dim, ("adult_mesomorph_male", Path("adult_mesomorph_male.stl")))
endomorph = Phantom("human", phantom_dim, ("adult_endomorph_male", Path("adult_endomorph_male.stl")))

ecto_dims = analyze_phantom_dimensions(ectomorph)
meso_dims = analyze_phantom_dimensions(mesomorph)
endo_dims = analyze_phantom_dimensions(endomorph)

print(f"Ectomorph torso width: {ecto_dims['torso_width_cm']:.1f} cm")
print(f"Mesomorph torso width: {meso_dims['torso_width_cm']:.1f} cm")
print(f"Endomorph torso width: {endo_dims['torso_width_cm']:.1f} cm")

# Validate progression: ectomorph < mesomorph < endomorph
assert ecto_dims['torso_width_cm'] < meso_dims['torso_width_cm'] < endo_dims['torso_width_cm']
```

### Step 8: Parameter Documentation

Create documentation file `{phantom_name}_parameters.md`:

```markdown
# Phantom Parameter Documentation: {phantom_name}

## MakeHuman Parameters
- Age: 25 years
- Gender: {sex}
- Height: {height} cm
- Weight: {weight} kg
- BMI: {bmi:.1f}
- Muscle: {muscle}%
- Head scale: {head_scale}
- Torso scale: {torso_scale}
- Limb scale: {limb_scale}
- Waist scale: {waist_scale}
- Chest scale: {chest_scale}

## Blender Processing
- Scale transformation: Meters to centimeters (×0.01)
- Y alignment: Lowest point to Y=0
- Rotation: 90° around X axis (supine orientation)
- Decimation ratio: {ratio}
- Final face count: {face_count}
- Torso cropping: {yes/no}

## Validation Results
- Coordinate scale: Centimeters
- Y range: {y_min:.2f} to {y_max:.2f} cm
- Watertight: Yes
- MyPySkinDose integration: Passed

## Body Type Validation
- Expected BMI: {expected_bmi}
- Calculated dimensions:
  - Torso width: {torso_width:.1f} cm
  - Torso thickness: {torso_thickness:.1f} cm
- Body type progression: {validation_result}
```

## Batch Processing Strategy

Process phantoms in this order to maximize parameter reuse:

1. **adult_mesomorph_male** (baseline - closest to default MakeHuman)
2. **adult_mesomorph_female** (copy male parameters, adjust gender/height)
3. **adult_ectomorph_male** (adjust from mesomorph baseline)
4. **adult_ectomorph_female** (copy male ectomorph, adjust gender)
5. **adult_endomorph_male** (adjust from mesomorph baseline)
6. **adult_endomorph_female** (copy male endomorph, adjust gender)

**Parameter reuse strategy**:
- Create MakeHuman macro files for each body type
- Use same body proportions for same body type, different sex
- Adjust only gender-specific parameters (height, muscle mass, hip scale)
- Document the progression between body types

## Body Type-Specific Considerations

### Ectomorph (Thin)
- **Medical relevance**: Common in young adults, chronic illness, certain populations
- **Dose considerations**: Less tissue attenuation, higher dose to organs
- **MakeHuman challenges**: Extreme thin parameters may create mesh artifacts
- **Solutions**: Use moderate parameters rather than extreme settings
- **Validation**: Ensure torso width is 15-20% less than mesomorph

### Mesomorph (Average)
- **Medical relevance**: Represents "standard" patient for dose calibration
- **Dose considerations**: Baseline for correction factor development
- **MakeHuman challenges**: Closest to default, easiest to generate
- **Solutions**: Use as baseline for other body types
- **Validation**: Should match existing adult_male/adult_female dimensions

### Endomorph (Heavy)
- **Medical relevance**: Increasing patient population, dose distribution challenges
- **Dose considerations**: More tissue attenuation, higher table attenuation
- **MakeHuman challenges**: Weight parameters may not achieve extreme obesity
- **Solutions**: Focus on BMI 28-30 range (not bariatric >40)
- **Validation**: Torso width should be 20-25% greater than mesomorph

## Comparison with Existing Adult Phantoms

Compare generated adult phantoms with existing `adult_male`/`adult_female`:

### Dimension Comparison
```python
# Compare with existing adult phantom
existing_adult = Phantom("human", PhantomDimensions(), "adult_male")
new_mesomorph = Phantom("human", PhantomDimensions(), ("adult_mesomorph_male", Path("adult_mesomorph_male.stl")))

existing_dims = analyze_phantom_dimensions(existing_adult)
new_dims = analyze_phantom_dimensions(new_mesomorph)

print(f"Existing adult male torso width: {existing_dims['torso_width_cm']:.1f} cm")
print(f"New mesomorph male torso width: {new_dims['torso_width_cm']:.1f} cm")
print(f"Difference: {abs(existing_dims['torso_width_cm'] - new_dims['torso_width_cm']):.1f} cm")
```

Expected: New mesomorph should be within 5% of existing adult dimensions.

### Mesh Density Comparison
- Existing adult: 26,756 faces (full resolution)
- New adult target: 5,000-8, faces
- New phantoms should have ~20-30% of original face count

## Sex-Specific Adjustments

### Female vs Male Parameters
**Key differences**:
- Height: Females 162 cm vs Males 175 cm
- Weight: Females generally 10-15% lighter at same BMI
- Hip scale: Females typically 1.1-1.2 vs Males 1.0
- Chest scale: Females typically 0.9-1.0 vs Males 1.0
- Muscle mass: Females typically 10-15% less than males

**Validation approach**:
- For each body type, female should have proportionally smaller dimensions
- Hip-to-waist ratio should be higher for females
- Total height should match target (162 cm vs 175 cm)

## Torso Cropping Recommendations

**Why crop**: Fluoroscopic procedures typically target torso region (abdomen, chest, pelvis). Head and lower legs contribute unnecessary geometry.

**Cropping guidelines**:
- **Upper bound**: Cut at shoulder line (approximately Y = 60-70 cm from table)
- **Lower bound**: Cut at mid-thigh (approximately Y = 10-15 cm from table)
- **Benefit**: Reduces face count by 30-40% while maintaining relevant anatomy

**Blender cropping steps**:
1. In Edit Mode, use Box Select (B) to select head region
2. Press X to delete selected vertices
3. Repeat for lower leg region
4. Run Mesh → Clean Up → Delete Loose to remove isolated vertices
5. Recalculate normals (Mesh → Normals → Recalculate Outside)

## Troubleshooting Adult-Specific Issues

### Issue: Body type differences not pronounced enough
**Solution**: MakeHuman has limits on extreme body types. If differences are too subtle:
- Increase body proportion scale differences (torso scale: 0.85 vs 1.0 vs 1.2)
- Consider more extreme weight parameters within MakeHuman limits
- Document limitations and consider TCIA segmentation for extreme cases

### Issue: Female phantom has unrealistic proportions
**Solution**: Female anatomy requires different parameter balance:
- Focus on hip scale (1.1-1.2) rather than overall torso width
- Adjust chest scale separately from overall torso
- Validate against female anthropometric data

### Issue: Endomorph not heavy enough for research needs
**Solution**: MakeHuman has limits (~150 kg max). For true bariatric:
- Document current endomorph as "heavy adult" (BMI 28-30)
- Use Phase 4 bariatric phantoms for BMI 35-40+
- Consider TCIA segmentation for BMI 40+ if needed

### Issue: Torso cropping creates holes in mesh
**Solution**: Cropping can create open edges:
- After cropping, use Mesh → Clean Up → Fill Holes
- Ensure crop boundaries are in flat regions (not curved anatomy)
- Consider keeping a small buffer region rather than clean cuts

## Deliverables Checklist

For each of the 6 phantoms:

- [ ] MakeHuman `.mhm` file saved
- [ ] OBJ export completed
- [ ] Blender transformation applied
- [ ] Decimation to target face count (5k-8k)
- [ ] Torso cropping completed (optional but recommended)
- [ ] STL export completed
- [ ] Validation script passed
- [ ] MyPySkinDose integration test passed
- [ ] Body type validation completed
- [ ] Parameter documentation completed

**Overall deliverables**:
- [ ] 6 adult STL files in `phantom_data/` directory
- [ ] 6 parameter documentation files
- [ ] Body type comparison analysis
- [ ] Comparison with existing adult phantoms
- [ ] Lessons learned document
- [ ] Updated validation script (if needed)

## Validation Summary Report Template

```markdown
# Adult Phantom Generation - Validation Summary

## Phantoms Generated
1. adult_ectomorph_male.stl - Status: {PASS/FAIL}
2. adult_ectomorph_female.stl - Status: {PASS/FAIL}
3. adult_mesomorph_male.stl - Status: {PASS/FAIL}
4. adult_mesomorph_female.stl - Status: {PASS/FAIL}
5. adult_endomorph_male.stl - Status: {PASS/FAIL}
6. adult_endomorph_female.stl - Status: {PASS/FAIL}

## Validation Results Summary
| Phantom | Face Count | Height (cm) | Torso Width (cm) | Watertight | MyPySkinDose Load | Body Type Check |
|---------|------------|-------------|------------------|------------|-------------------|-----------------|
| adult_ectomorph_male | {count} | {height} | {width} | {yes/no} | {yes/no} | {yes/no} |
| adult_ectomorph_female | {count} | {height} | {width} | {yes/no} | {yes/no} | {yes/no} |
| adult_mesomorph_male | {count} | {height} | {width} | {yes/no} | {yes/no} | {yes/no} |
| adult_mesomorph_female | {count} | {height} | {width} | {yes/no} | {yes/no} | {yes/no} |
| adult_endomorph_male | {count} | {height} | {width} | {yes/no} | {yes/no} | {yes/no} |
| adult_endomorph_female | {count} | {height} | {width} | {yes/no} | {yes/no} | {yes/no} |

## Body Type Progression Validation
- Ectomorph torso width: {ecto_width} cm
- Mesomorph torso width: {meso_width} cm
- Endomorph torso width: {endo_width} cm
- Progression check: {PASS/FAIL} (expected: ecto < meso < endo)

## Comparison with Existing Adult Phantoms
- Existing adult male torso width: {existing_width} cm
- New mesomorph male torso width: {new_width} cm
- Difference: {difference:.1f} cm (expected: < 5 cm)

## Sex-Specific Validation
- Male height average: {male_height_avg} cm
- Female height average: {female_height_avg} cm
- Height difference: {height_diff} cm (expected: ~13 cm)

## Issues Encountered
- {issue_1}
- {issue_2}

## Resolutions Applied
- {resolution_1}
- {resolution_2}

## Recommendations for Bariatric Generation (Phase 4)
- {recommendation_1}
- {recommendation_2}
```

## Success Criteria

Phase 3 is complete when:

1. All 6 adult phantoms are generated
2. All phantoms pass validation script checks
3. All phantoms load successfully in MyPySkinDose
4. Body type progression is validated (ectomorph < mesomorph < endomorph)
5. Sex-specific dimensions are realistic
6. Face counts are in target range (5k-8k)
7. Parameter documentation is complete for all phantoms
8. Comparison with existing adult phantoms shows reasonable agreement
9. Validation summary report is completed
10. All STL files are ready for integration in Phase 5

## Handoff to Phase 4

Upon Phase 3 completion, provide:
- 6 adult STL files
- 6 parameter documentation files
- Body type comparison analysis
- Validation summary report
- Lessons learned from adult body type generation
- Any adjustments to decimation strategy
- Recommendations for bariatric parameter limits
- Updated validation script (if modified)

These artifacts will serve as the foundation for bariatric phantom generation in Phase 4.
