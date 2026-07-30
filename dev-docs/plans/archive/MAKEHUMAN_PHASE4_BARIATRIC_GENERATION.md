# Phase 4: Bariatric Phantom Generation

> **SUPERSEDED (2026-07-21).** See [`AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](AUTOMATED_PHANTOM_LIBRARY_PLAN.md).

## Objective

Generate 6 bariatric phantoms across BMI classes I, II, and III for both male and female anatomies. These phantoms represent the growing bariatric patient population and present unique challenges for dose distribution due to increased tissue attenuation and table positioning challenges.

## Prerequisites

**Inputs from Phase 1**:
- Working MakeHuman 1.2.0 installation
- Working Blender 3.6+ installation
- Validation script (`validate_phantom.py`)
- Integration test script (`test_mypyskindose_integration.py`)
- Coordinate system transformation workflow

**Inputs from Phase 2-3**:
- Experience with pediatric and adult parameter tuning
- Lessons learned from body type generation
- Understanding of MakeHuman parameter limits
- Updated validation scripts (if modified)

**Additional Requirements**:
- Phase 3 completion confirmed
- Adult phantoms pass all validation checks
- Understanding of MakeHuman limitations for extreme body types
- TCIA segmentation setup as fallback (optional but recommended)

## Target Phantoms

| Phantom Name | BMI Class | BMI Range | Sex | Target Face Count | Priority |
|--------------|-----------|-----------|-----|-------------------|----------|
| `bariatric_class1_male` | Class I | 30-35 | Male | 5,000-8,000 | P1 |
| `bariatric_class1_female` | Class I | 30-35 | Female | 5,000-8,000 | P1 |
| `bariatric_class2_male` | Class II | 35-40 | Male | 5,000-8,000 | P1 |
| `bariatric_class2_female` | Class II | 35-40 | Female | 5,000-8,000 | P1 |
| `bariatric_class3_male` | Class III | 40+ | Male | 5,000-8,000 | P1 |
| `bariatric_class3_female` | Class III | 40+ | Female | 5,000-8,000 | P1 |

## Bariatric Anthropometric Reference Data

Use bariatric-specific anthropometric data for realistic dimensions:

**Height Reference (Bariatric Adults)**:
- Male: 175 cm (similar to general population)
- Female: 162 cm (similar to general population)

**Weight Reference by BMI Class** (Height 175 cm male, 162 cm female):
- Class I (BMI 32.5): Male 100 kg, Female 85 kg
- Class II (BMI 37.5): Male 115 kg, Female 98 kg
- Class III (BMI 42.5): Male 130 kg, Female 112 kg

**Body Dimension Estimates**:
- Chest circumference: Class I 125-135 cm, Class II 140-150 cm, Class III 155-165 cm
- Waist circumference: Class I 120-130 cm, Class II 135-145 cm, Class III 150-160 cm
- Hip circumference: Class I 125-135 cm, Class II 140-150 cm, Class III 155-165 cm
- Abdominal wall thickness: Class I 3-4 cm, Class II 4-5 cm, Class III 5-6 cm

## MakeHuman Parameter Limitations

**Critical Constraint**: MakeHuman has difficulty generating realistic bariatric anatomy beyond BMI ~35. The software's parametric model is optimized for normal body ranges and may produce unrealistic meshes at extreme weights.

**Expected Limitations**:
- Maximum effective weight: ~150 kg (BMI ~48 for 175 cm height)
- Tissue distribution may not match real bariatric anatomy
- Abdominal fat distribution may be unrealistic
- Limb proportions may not scale appropriately

**Fallback Strategy**: If MakeHuman cannot achieve realistic bariatric anatomy, use TCIA + 3D Slicer segmentation as documented in `dev-docs/ADDITIONAL_PHANTOMS.md`.

## MakeHuman Parameter Configuration

### Class I Parameters (BMI 30-35)

**Male Class I**:
- **Age**: 35 years (bariatric patients typically older)
- **Gender**: Male
- **Height**: 175 cm
- **Weight**: 100 kg (BMI 32.7)
- **Muscle**: 35% (moderate muscle under fat)
- **Body Proportions**:
  - Head scale: 1.0
  - Torso scale: 1.3 (significantly wider)
  - Limb scale: 1.2 (thicker limbs)
  - Waist scale: 1.4
  - Chest scale: 1.3
  - Stomach scale: 1.5 (increased abdominal fat)

**Female Class I**:
- **Age**: 35 years
- **Gender**: Female
- **Height**: 162 cm
- **Weight**: 85 kg (BMI 32.4)
- **Muscle**: 30%
- **Body Proportions**:
  - Head scale: 1.0
  - Torso scale: 1.3
  - Limb scale: 1.2
  - Waist scale: 1.4
  - Chest scale: 1.25
  - Hip scale: 1.3
  - Stomach scale: 1.5

### Class II Parameters (BMI 35-40)

**Male Class II**:
- **Age**: 40 years
- **Gender**: Male
- **Height**: 175 cm
- **Weight**: 115 kg (BMI 37.6)
- **Muscle**: 30%
- **Body Proportions**:
  - Head scale: 1.0
  - Torso scale: 1.4
  - Limb scale: 1.25
  - Waist scale: 1.5
  - Chest scale: 1.35
  - Stomach scale: 1.6

**Female Class II**:
- **Age**: 40 years
- **Gender**: Female
- **Height**: 162 cm
- **Weight**: 98 kg (BMI 37.3)
- **Muscle**: 25%
- **Body Proportions**:
  - Head scale: 1.0
  - Torso scale: 1.4
  - Limb scale: 1.25
  - Waist scale: 1.5
  - Chest scale: 1.3
  - Hip scale: 1.35
  - Stomach scale: 1.6

### Class III Parameters (BMI 40+)

**Male Class III**:
- **Age**: 45 years
- **Gender**: Male
- **Height**: 175 cm
- **Weight**: 130 kg (BMI 42.5)
- **Muscle**: 25%
- **Body Proportions**:
  - Head scale: 1.0
  - Torso scale: 1.5 (maximum realistic)
  - Limb scale: 1.3
  - Waist scale: 1.6
  - Chest scale: 1.4
  - Stomach scale: 1.7

**Female Class III**:
- **Age**: 45 years
- **Gender**: Female
- **Height**: 162 cm
- **Weight**: 112 kg (BMI 42.7)
- **Muscle**: 20%
- **Body Proportions**:
  - Head scale: 1.0
  - Torso scale: 1.5
  - Limb scale: 1.3
  - Waist scale: 1.6
  - Chest scale: 1.35
  - Hip scale: 1.4
  - Stomach scale: 1.7

## Generation Workflow (Per Phantom)

### Step 1: Create MakeHuman Model

**Manual Steps**:
1. Open MakeHuman
2. Start with default human model
3. Navigate to **Modelling** tab
4. Set parameters according to the specific BMI class configuration
5. **Critical**: Inspect the 3D model for realistic fat distribution
6. If anatomy appears unrealistic, note parameters for TCIA fallback
7. Save as `{phantom_name}.mhm` (e.g., `bariatric_class1_male.mhm`)

**Realism Check**:
- Fat should distribute primarily around abdomen, not uniformly
- Limbs should thicken but maintain human proportions
- Face should not become excessively round
- Mesh should not show artifacts or self-intersections

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
   - Ratio: 0.10 (more aggressive for larger phantoms)
   - Target face count: 5,000-8,000
4. Apply modifier
5. Verify face count in Stats panel

**Mesh Repair** (Critical for bariatric phantoms):
1. Mesh → Clean Up → Merge By Distance (threshold: 0.02 cm - higher tolerance)
2. Mesh → Normals → Recalculate Outside
3. Check for self-intersections with 3D Print Toolbox
4. Use Mesh → Clean Up → Fill Holes if needed

**Full-Body Preservation**:
- Maintain full-body watertight meshes for all bariatric phantoms so that top-of-head alignment (`Z = 0.0`), body habitus scaling (`_apply_human_scale`), table positioning, and 3D geometry plots work consistently.

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
- Y range (AP): -45.0 to 0.0 cm
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

# Test scaling (bariatric phantoms should handle scaling well)
phantom._apply_human_scale((1.0, 1.0, 1.0))
print(f"✓ Scaling test passed")

# Check table positioning
y_max = phantom.r[:, 1].max()
print(f"  Table contact max Y: {y_max:.2f} cm (should be 0.00)")
```

### Step 7: Bariatric Validation

**Validate bariatric-specific characteristics**:
```python
# Calculate bariatric dimensions
def analyze_bariatric_dimensions(phantom):
    # Get torso region (approximately Z=-20 to Z=-80 cm from head top)
    torso_mask = (phantom.r[:, 2] < -20) & (phantom.r[:, 2] > -80)
    torso_vertices = phantom.r[torso_mask]
    
    # Calculate dimensions
    x_range = float(torso_vertices[:, 0].max() - torso_vertices[:, 0].min())
    y_range = float(torso_vertices[:, 1].max() - torso_vertices[:, 1].min())
    
    return {
        'torso_width_cm': x_range,
        'torso_thickness_cm': y_range,
        'abdominal_thickness_cm': y_range,
        'total_vertices': len(phantom.r)
    }

settings = PyskindoseSettings(load_settings_example_json())
phantom_dim = settings.phantom.dimension

# Compare BMI classes
class1 = Phantom("human", phantom_dim, ("bariatric_class1_male", Path("bariatric_class1_male.stl")))
class2 = Phantom("human", phantom_dim, ("bariatric_class2_male", Path("bariatric_class2_male.stl")))
class3 = Phantom("human", phantom_dim, ("bariatric_class3_male", Path("bariatric_class3_male.stl")))

class1_dims = analyze_bariatric_dimensions(class1)
class2_dims = analyze_bariatric_dimensions(class2)
class3_dims = analyze_bariatric_dimensions(class3)

print(f"Class I torso width: {class1_dims['torso_width_cm']:.1f} cm")
print(f"Class II torso width: {class2_dims['torso_width_cm']:.1f} cm")
print(f"Class III torso width: {class3_dims['torso_width_cm']:.1f} cm")

# Validate progression: class1 < class2 < class3
assert class1_dims['torso_width_cm'] < class2_dims['torso_width_cm'] < class3_dims['torso_width_cm']
```

### Step 8: Realism Assessment

**Subjective evaluation criteria**:
1. **Fat distribution**: Abdominal prominence should increase with BMI class
2. **Limb proportions**: Should thicken but maintain human anatomy
3. **Mesh quality**: No self-intersections or artifacts
4. **Table contact**: Back surface should be reasonably flat for table positioning

**Scoring system** (1-5 scale):
- 5: Excellent - realistic bariatric anatomy
- 4: Good - acceptable for dose studies
- 3: Fair - some limitations but usable
- 2: Poor - significant anatomical issues
- 1: Unusable - recommend TCIA fallback

**Decision point**: If score < 3, document limitations and consider TCIA segmentation alternative.

### Step 9: Parameter Documentation

Create documentation file `{phantom_name}_parameters.md`:

```markdown
# Phantom Parameter Documentation: {phantom_name}

## MakeHuman Parameters
- Age: {age} years
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
- Stomach scale: {stomach_scale}

## Blender Processing
- Scale transformation: Meters to centimeters (×0.01)
- Y alignment: Lowest point to Y=0
- Rotation: 90° around X axis (supine orientation)
- Decimation ratio: {ratio}
- Final face count: {face_count}
- Torso cropping: Yes (essential for bariatric)

## Validation Results
- Coordinate scale: Centimeters
- Y range: {y_min:.2f} to {y_max:.2f} cm
- Watertight: Yes
- MyPySkinDose integration: Passed

## Bariatric Validation
- Expected BMI: {expected_bmi}
- Calculated dimensions:
  - Torso width: {torso_width:.1f} cm
  - Abdominal thickness: {abdominal_thickness:.1f} cm
- BMI class progression: {validation_result}
- Realism assessment: {score}/5

## Notes
- {realism_notes}
- {limitations}
- {recommendations}
```

## TCIA Fallback Strategy

If MakeHuman cannot achieve realistic bariatric anatomy, use TCIA + 3D Slicer segmentation:

### TCIA Data Selection
1. **Access TCIA**: https://www.cancerimagingarchive.net/
2. **Search for**: "CT Colonography" or "Lung Screening" collections
3. **Filter for**: Large patient BMI (if metadata available)
4. **Download**: Anonymous CT series

### 3D Slicer Segmentation Workflow
1. **Import DICOM**: File → Add Data → Select DICOM series
2. **Segmentation module**: Create new segmentation
3. **Threshold tool**: Set threshold to capture body contour
4. **Paint tool**: Manual refinement of body outline
5. **Make model**: Convert segmentation to 3D model
6. **Export**: Export as STL

### Advantages of TCIA Approach
- Real patient anatomy (not parametric approximation)
- True bariatric fat distribution
- Unlimited BMI range (depends on available data)
- Higher anatomical fidelity

### Disadvantages
- Manual process (not automated)
- Requires DICOM processing expertise
- Variable mesh quality (requires cleanup)
- Dependent on TCIA data availability

## Batch Processing Strategy

Process phantoms in this order to maximize learning:

1. **bariatric_class1_male** (baseline - most achievable)
2. **bariatric_class1_female** (copy male parameters, adjust gender)
3. **bariatric_class2_male** (push parameters further)
4. **bariatric_class2_female** (copy male parameters, adjust gender)
5. **bariatric_class3_male** (extreme parameters - may need TCIA)
6. **bariatric_class3_female** (copy male or use TCIA)

**Decision points**:
- After Class I: Evaluate realism vs. MakeHuman limits
- After Class II: Decide whether to continue with MakeHuman or switch to TCIA
- After Class III: Document limitations and recommend best approach

## Bariatric-Specific Considerations

### Table Positioning Challenges
- **Issue**: Bariatric patients may extend beyond standard table width
- **Impact**: May require table positioning adjustments in MyPySkinDose
- **Solution**: Document maximum width and recommend table offset settings

### Dose Distribution Implications
- **Increased attenuation**: More tissue = higher patient dose, lower detector dose
- **Table attenuation**: Thicker patients = more table attenuation
- **Backscatter**: Increased backscatter due to more tissue
- **Validation**: Consider physics validation for extreme body types

### Surface Area Considerations
- **Higher surface area**: Affects total dose calculations
- **Organ dose distribution**: Different from normal-weight patients
- **Documentation**: Record surface area estimates for future reference

### Mesh Density Challenges
- **More surface area**: Same face count = lower resolution
- **Solution**: Consider 6k-8k faces for bariatric (vs 5k for normal)
- **Trade-off**: Higher face count = longer calculation time

## Comparison with Existing Phantoms

Compare bariatric phantoms with existing adult phantoms:

### Dimension Comparison
```python
# Compare with existing adult phantom
existing_adult = Phantom("human", PhantomDimensions(), "adult_male")
bariatric_class3 = Phantom("human", PhantomDimensions(), ("bariatric_class3_male", Path("bariatric_class3_male.stl")))

existing_dims = analyze_bariatric_dimensions(existing_adult)
bariatric_dims = analyze_bariatric_dimensions(bariatric_class3)

print(f"Existing adult male torso width: {existing_dims['torso_width_cm']:.1f} cm")
print(f"Bariatric class III male torso width: {bariatric_dims['torso_width_cm']:.1f} cm")
print(f"Increase: {bariatric_dims['torso_width_cm'] / existing_dims['torso_width_cm']:.1f}x")
```

Expected: Bariatric class III should be 1.5-2.0x wider than normal adult.

## Troubleshooting Bariatric-Specific Issues

### Issue: MakeHuman produces unrealistic "inflated" appearance
**Solution**: This is a known MakeHuman limitation for extreme weights.
- Document the limitation
- Consider TCIA segmentation for this BMI class
- Use MakeHuman phantom only if score ≥ 3/5 on realism assessment

### Issue: Mesh self-intersections in abdominal region
**Solution**: Extreme torso scaling can cause mesh artifacts.
- In Blender, use Mesh → Clean Up → Fix Self-Intersection
- Reduce torso scale parameters slightly
- Consider manual mesh repair in Blender

### Issue: Phantom too wide for standard table in MyPySkinDose
**Solution**: Realistic issue - bariatric patients extend beyond table.
- Document the maximum width
- Recommend table offset settings in user guide
- This is expected behavior, not an error

### Issue: Face count too high despite decimation
**Solution**: Bariatric phantoms have more surface area.
- Increase decimation ratio to 0.08-0.10
- Aggressive torso cropping becomes essential
- Target 5k-6k faces minimum for usability

### Issue: Fat distribution doesn't match real bariatric anatomy
**Solution**: MakeHuman parametric limitations.
- Document discrepancy
- Consider TCIA segmentation for realistic anatomy
- Use MakeHuman phantom only for approximate studies

## Deliverables Checklist

For each of the 6 phantoms:

- [ ] MakeHuman `.mhm` file saved (or TCIA data documented)
- [ ] OBJ export completed (or STL from 3D Slicer)
- [ ] Blender transformation applied
- [ ] Decimation to target face count (5k-8k)
- [ ] Torso cropping completed (essential)
- [ ] STL export completed
- [ ] Validation script passed
- [ ] MyPySkinDose integration test passed
- [ ] Bariatric validation completed
- [ ] Realism assessment scored
- [ ] Parameter documentation completed
- [ ] TCIA fallback documented (if used)

**Overall deliverables**:
- [ ] 6 bariatric STL files in `phantom_data/` directory
- [ ] 6 parameter documentation files
- [ ] BMI class progression analysis
- [ ] Realism assessment summary
- [ ] TCIA fallback documentation (if applicable)
- [ ] Lessons learned document
- [ ] Recommendations for clinical use

## Validation Summary Report Template

```markdown
# Bariatric Phantom Generation - Validation Summary

## Phantoms Generated
1. bariatric_class1_male.stl - Status: {PASS/FAIL} - Realism: {score}/5
2. bariatric_class1_female.stl - Status: {PASS/FAIL} - Realism: {score}/5
3. bariatric_class2_male.stl - Status: {PASS/FAIL} - Realism: {score}/5
4. bariatric_class2_female.stl - Status: {PASS/FAIL} - Realism: {score}/5
5. bariatric_class3_male.stl - Status: {PASS/FAIL} - Realism: {score}/5
6. bariatric_class3_female.stl - Status: {PASS/FAIL} - Realism: {score}/5

## Validation Results Summary
| Phantom | Face Count | Height (cm) | Torso Width (cm) | Abdominal Thickness (cm) | Watertight | MyPySkinDose Load | Realism Score |
|---------|------------|-------------|------------------|--------------------------|------------|-------------------|---------------|
| bariatric_class1_male | {count} | {height} | {width} | {thickness} | {yes/no} | {yes/no} | {score}/5 |
| bariatric_class1_female | {count} | {height} | {width} | {thickness} | {yes/no} | {yes/no} | {score}/5 |
| bariatric_class2_male | {count} | {height} | {width} | {thickness} | {yes/no} | {yes/no} | {score}/5 |
| bariatric_class2_female | {count} | {height} | {width} | {thickness} | {yes/no} | {yes/no} | {score}/5 |
| bariatric_class3_male | {count} | {height} | {width} | {thickness} | {yes/no} | {yes/no} | {score}/5 |
| bariatric_class3_female | {count} | {height} | {width} | {thickness} | {yes/no} | {yes/no} | {score}/5 |

## BMI Class Progression Validation
- Class I torso width: {class1_width} cm
- Class II torso width: {class2_width} cm
- Class III torso width: {class3_width} cm
- Progression check: {PASS/FAIL} (expected: class1 < class2 < class3)

## Comparison with Normal Adult Phantoms
- Normal adult male torso width: {normal_width} cm
- Bariatric class III male torso width: {bariatric_width} cm
- Increase: {increase:.1f}x (expected: 1.5-2.0x)

## Realism Assessment Summary
- Average realism score: {avg_score:.1f}/5
- Phantoms meeting threshold (≥3/5): {count}/6
- Recommended for clinical use: {yes/no}

## TCIA Fallback Usage
- Phantoms using TCIA segmentation: {count}
- Reason for TCIA usage: {reason}
- TCIA data sources: {sources}

## Issues Encountered
- {issue_1}
- {issue_2}

## Resolutions Applied
- {resolution_1}
- {resolution_2}

## Recommendations for Integration (Phase 5)
- {recommendation_1}
- {recommendation_2}

## Clinical Use Recommendations
- {clinical_recommendation_1}
- {clinical_recommendation_2}
```

## Success Criteria

Phase 4 is complete when:

1. All 6 bariatric phantoms are generated (MakeHuman or TCIA)
2. All phantoms pass validation script checks
3. All phantoms load successfully in MyPySkinDose
4. BMI class progression is validated (class1 < class2 < class3)
5. Realism assessment identifies usable phantoms (score ≥ 3/5)
6. Face counts are in target range (5k-8k)
7. Parameter documentation is complete for all phantoms
8. TCIA fallback is documented if used
9. Validation summary report is completed
10. Clinical use recommendations are documented
11. All STL files are ready for integration in Phase 5

## Handoff to Phase 5

Upon Phase 4 completion, provide:
- 6 bariatric STL files
- 6 parameter documentation files
- BMI class progression analysis
- Realism assessment summary
- TCIA fallback documentation (if applicable)
- Validation summary report
- Lessons learned from bariatric generation
- Clinical use recommendations
- Any adjustments to validation approach
- Updated validation script (if modified)

These artifacts will serve as the foundation for final integration and validation in Phase 5.
