# MakeHuman Phantom Generation - Master Plan

## Overview

This master plan orchestrates the generation of a comprehensive phantom library using MakeHuman software to create anatomically diverse patient phantoms for MyPySkinDose. The approach uses parametric human modeling to generate consistent, watertight meshes across a spectrum of body habitus types from pediatric to bariatric, for both male and female anatomies.

## Objectives

1. **Expand phantom diversity**: Add phantoms covering pediatric to bariatric body types
2. **Fill anatomical gaps**: Provide intermediate sizes between current junior/adult/senior meshes
3. **Enable body habitus studies**: Support research on dose distribution across patient populations
4. **Maintain quality**: Ensure all phantoms meet MyPySkinDose integration requirements
5. **Create reproducible pipeline**: Establish automated workflow for future phantom generation

## Phantom Target Matrix

| Category | Age/Size | Male | Female | Target Face Count | Priority |
|----------|----------|------|--------|------------------|----------|
| Pediatric | ~5 years | ✅ | ✅ | 3k-5k | P1 |
| Pediatric | ~10 years | ✅ | ✅ | 3k-5k | P1 |
| Junior | ~15 years | ✅ | ✅ | 3k-5k | P2 (existing: `junior_male`, `junior_female`) |
| Adult | ~25 years | ✅ | ✅ | 26k (1k red) | P2 (existing: `adult_male`, `adult_female`) |
| Adult - Ectomorph | ~25 years, thin | ✅ | ✅ | 5k-8k | P1 |
| Adult - Mesomorph | ~25 years, average | ✅ | ✅ | 5k-8k | P1 |
| Adult - Endomorph | ~25 years, heavy | ✅ | ✅ | 5k-8k | P1 |
| Senior | ~65 years | ✅ | ✅ | 26k (1k red) | P2 (existing: `senior_male`, `senior_female`) |
| Bariatric - Class I | BMI 30-35 | ✅ | ✅ | 5k-8k | P1 |
| Bariatric - Class II | BMI 35-40 | ✅ | ✅ | 5k-8k | P1 |
| Bariatric - Class III | BMI 40+ | ✅ | ✅ | 5k-8k | P1 |
| Reference | Reference | - | - | 13k (1k red) | P2 (existing: `hudfrid`) |

**Total new phantoms**: 16 (8 new categories × 2 sexes; excluding 7 existing phantoms: `hudfrid`, `adult_male`, `adult_female`, `junior_male`, `junior_female`, `senior_male`, `senior_female`). Total library after integration: 23 phantoms (46 STL files including `_reduced_1000t.stl` variants).

## Integration Requirements (All Phantoms)

Every generated phantom must meet these MyPySkinDose specifications:

1. **Coordinate System**: 
   - Units: centimeters
   - Lateral axis (`X` / `PT L-R`): Across the table, centered at `X = 0.0` (spanning `-width/2` to `+width/2`)
   - Vertical axis (`Y` / `PT A-P`): Table height / AP thickness. Posterior skin back contact plane is at `Y = 0.0` (max Y), and anterior chest/abdomen extends into negative Y (spanning `-thickness` to `0.0`)
   - Longitudinal axis (`Z` / `PT S-I`): Along the table. Superior head top is at `Z = 0.0` (max Z), and patient body extends along negative Z (spanning `-height` to `0.0`)
   - Patient orientation: Head-first supine along negative Z direction

2. **Mesh Quality**:
   - Watertight surface (no holes)
   - Consistent triangle winding (outward-facing normals)
   - Target face count: 3k-8k (pediatric: 3k-5k, adult/bariatric: 5k-8k)
   - No degenerate triangles

3. **File Format**:
   - Binary STL format
   - Naming convention: `{category}_{body_type}_{sex}.stl`
   - Example: `pediatric_5y_male.stl`, `bariatric_class3_female.stl`

4. **Validation**:
   - Load successfully in MyPySkinDose Phantom class
   - Normal recomputation works correctly
   - Scaling anchors function properly
   - Ray-casting produces valid entrance/exit classification

## Phase Structure

The phantom generation is organized into 5 sequential phases:

### Phase 1: MakeHuman Setup and Testing
**Goal**: Establish MakeHuman environment and generate test phantom
**Inputs**: None (starts from scratch)
**Outputs**: Working MakeHuman installation, test phantom, validation script
**Deliverables**: 
- MakeHuman installation guide
- Base phantom parameters
- Validation test suite
- Test phantom (`makehuman_test_male.stl`)

### Phase 2: Pediatric Phantom Generation
**Goal**: Generate pediatric phantoms (5y, 10y, both sexes)
**Inputs**: Phase 1 deliverables, pediatric age parameters
**Outputs**: 4 pediatric phantoms, parameter documentation
**Deliverables**:
- `pediatric_5y_male.stl`, `pediatric_5y_female.stl`
- `pediatric_10y_male.stl`, `pediatric_10y_female.stl`
- Pediatric parameter specifications
- Validation reports

### Phase 3: Adult Phantom Generation  
**Goal**: Generate adult ectomorph/mesomorph/endomorph phantoms (both sexes)
**Inputs**: Phase 1 deliverables, adult body type parameters
**Outputs**: 6 adult variant phantoms, parameter documentation
**Deliverables**:
- `adult_ectomorph_male.stl`, `adult_ectomorph_female.stl`
- `adult_mesomorph_male.stl`, `adult_mesomorph_female.stl`
- `adult_endomorph_male.stl`, `adult_endomorph_female.stl`
- Adult parameter specifications
- Validation reports

### Phase 4: Bariatric Phantom Generation
**Goal**: Generate bariatric phantoms across BMI classes I, II, III (both sexes)
**Inputs**: Phase 1 deliverables, bariatric BMI parameters
**Outputs**: 6 bariatric phantoms, parameter documentation
**Deliverables**:
- `bariatric_class1_male.stl`, `bariatric_class1_female.stl`
- `bariatric_class2_male.stl`, `bariatric_class2_female.stl`
- `bariatric_class3_male.stl`, `bariatric_class3_female.stl`
- Bariatric parameter specifications
- Validation reports

### Phase 5: Integration and Validation
**Goal**: Integrate all phantoms into MyPySkinDose and validate end-to-end
**Inputs**: All generated phantoms from Phases 2-4
**Outputs**: Integrated phantom library, comprehensive validation report
**Deliverables**:
- All phantoms in `phantom_data/` directory
- Updated AGENTS.md documentation
- Reduced-resolution variants (1k faces)
- Comprehensive validation report
- User guide for new phantoms

## Tools and Dependencies

### Required Software
- **MakeHuman 1.2.0**: Parametric human modeling software
  - Download: http://www.makehumancommunity.org/
  - License: AGPL3 (free, open source)
  - Python-based with GUI and command-line interface

- **Blender 3.6+**: Mesh processing and decimation
  - Download: https://www.blender.org/download/
  - License: GPL2 (free, open source)
  - Python API for automation

- **Python 3.11+**: For automation scripts
  - Libraries: `numpy-stl`, `trimesh` for STL processing

### MyPySkinDose Integration
- `src/mypyskindose/phantom_class.py`: Phantom loading and validation
- `src/mypyskindose/gui/helpers.py`: Automatic mesh discovery
- Test suite: `tests/unittests/test_phantom_scaling.py`

## Data Flow

```
Phase 1: Setup
  MakeHuman parameters → Test phantom → Validation script

Phase 2-4: Generation  
  Category parameters → MakeHuman → OBJ export → Blender → STL → Decimation → Validation

Phase 5: Integration
  Validated STLs → phantom_data/ → GUI discovery → Documentation → Final validation
```

## Success Criteria

1. **Completeness**: All 18 target phantoms generated and validated
2. **Quality**: All phantoms pass MyPySkinDose integration tests
3. **Documentation**: Complete parameter specifications for reproducibility
4. **Performance**: Ray-casting times < 5 seconds per event for all phantoms
5. **Usability**: GUI successfully discovers and displays all new phantoms
6. **Reproducibility**: Pipeline documented for future phantom generation

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| MakeHuman generates non-medical anatomy | Validate against existing medical phantoms; use conservative parameters |
| Triangle count too high for performance | Implement decimation pipeline; target 3k-8k faces |
| Coordinate system misalignment | Phase 1 establishes transformation pipeline; automated validation |
| Normal winding inconsistency | Blender repair tools; automated normal recomputation in MyPySkinDose |
| Parametric limits insufficient for bariatric | Test extreme parameters in Phase 1; fallback to TCIA segmentation if needed |

## Timeline Estimation

- Phase 1: 2-3 days (setup, testing, pipeline establishment)
- Phase 2: 2-3 days (4 phantoms × validation)
- Phase 3: 3-4 days (6 phantoms × validation)
- Phase 4: 3-4 days (6 phantoms × validation)
- Phase 5: 2-3 days (integration, documentation, final validation)

**Total**: 12-17 days for complete phantom library

## Handoff Criteria Between Phases

Each phase must complete before the next begins:

1. **Phase 1 → Phase 2**: Test phantom loads in MyPySkinDose, validation script passes
2. **Phase 2 → Phase 3**: All pediatric phantoms validated, parameter specifications documented
3. **Phase 3 → Phase 4**: All adult variants validated, parameter specifications documented
4. **Phase 4 → Phase 5**: All bariatric phantoms validated, parameter specifications documented

## Parallel Execution Opportunities

- Phase 2, 3, 4 could theoretically run in parallel once Phase 1 is complete
- Within each phase, male and female phantoms can be generated in parallel
- Validation can run concurrently with generation for subsequent phantoms

## References

- MakeHuman Documentation: http://www.makehumancommunity.org/wiki/
- MyPySkinDose Phantom Integration: `dev-docs/ADDITIONAL_PHANTOMS.md`
- Coordinate System Specs: `dev-docs/VENDOR_COORDINATE_SYSTEMS.md`
- Existing Phantom Analysis: `src/mypyskindose/phantom_class.py`
