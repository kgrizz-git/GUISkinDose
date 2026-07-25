# Phase 5: Integration and Validation

> **SUPERSEDED (2026-07-21).** See [`AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](../AUTOMATED_PHANTOM_LIBRARY_PLAN.md).

## Objective

Integrate all generated phantoms from Phases 2-4 into the MyPySkinDose library, create reduced-resolution variants for fast calculations, update documentation, and perform comprehensive end-to-end validation to ensure the new phantom library is production-ready.

## Prerequisites

**Inputs from Phase 1**:
- Validation scripts and test infrastructure
- Coordinate system transformation workflow
- MyPySkinDose development environment

**Inputs from Phase 2**:
- 4 pediatric STL files
- 4 pediatric parameter documentation files
- Pediatric validation summary report

**Inputs from Phase 3**:
- 6 adult STL files
- 6 adult parameter documentation files
- Adult validation summary report

**Inputs from Phase 4**:
- 6 bariatric STL files
- 6 bariatric parameter documentation files
- Bariatric validation summary report
- TCIA fallback documentation (if applicable)

**Additional Requirements**:
- Phases 2-4 completion confirmed
- All generated phantoms pass individual validation
- MyPySkinDose repository current on main branch
- Write access to repository for integration

## Target Phantom Library

**Complete Phantom Inventory After Integration**:

| Category | Phantoms | New in This Project |
|----------|----------|---------------------|
| Pediatric | 4 | `pediatric_5y_male`, `pediatric_5y_female`, `pediatric_10y_male`, `pediatric_10y_female` |
| Junior | 2 | `junior_male`, `junior_female` (existing) |
| Adult | 8 | `adult_ectomorph_male`, `adult_ectomorph_female`, `adult_mesomorph_male`, `adult_mesomorph_female`, `adult_endomorph_male`, `adult_endomorph_female`, `adult_male` (existing), `adult_female` (existing) |
| Senior | 2 | `senior_male`, `senior_female` (existing) |
| Bariatric | 6 | `bariatric_class1_male`, `bariatric_class1_female`, `bariatric_class2_male`, `bariatric_class2_female`, `bariatric_class3_male`, `bariatric_class3_female` |
| Reference | 1 | `hudfrid` (existing) |

**Total**: 23 phantoms (16 new + 7 existing)

## Integration Workflow

### Step 1: File Organization

**Directory Structure**:
All `.stl` files must be placed directly in `src/mypyskindose/phantom_data/` (flat directory structure) so that `Phantom(human_mesh=...)` and `get_human_mesh_names()` load and discover them without path errors:

```
src/mypyskindose/phantom_data/
├── hudfrid.stl
├── hudfrid_reduced_1000t.stl
├── adult_male.stl
├── adult_male_reduced_1000t.stl
├── adult_female.stl
├── adult_female_reduced_1000t.stl
├── junior_male.stl
├── junior_male_reduced_1000t.stl
├── junior_female.stl
├── junior_female_reduced_1000t.stl
├── senior_male.stl
├── senior_male_reduced_1000t.stl
├── senior_female.stl
├── senior_female_reduced_1000t.stl
├── pediatric_5y_male.stl
├── pediatric_5y_male_reduced_1000t.stl
├── pediatric_5y_female.stl
├── pediatric_5y_female_reduced_1000t.stl
├── pediatric_10y_male.stl
├── pediatric_10y_male_reduced_1000t.stl
├── pediatric_10y_female.stl
├── pediatric_10y_female_reduced_1000t.stl
├── adult_ectomorph_male.stl
├── adult_ectomorph_male_reduced_1000t.stl
├── adult_ectomorph_female.stl
├── adult_ectomorph_female_reduced_1000t.stl
├── adult_mesomorph_male.stl
├── adult_mesomorph_male_reduced_1000t.stl
├── adult_mesomorph_female.stl
├── adult_mesomorph_female_reduced_1000t.stl
├── adult_endomorph_male.stl
├── adult_endomorph_male_reduced_1000t.stl
├── adult_endomorph_female.stl
├── adult_endomorph_female_reduced_1000t.stl
├── bariatric_class1_male.stl
├── bariatric_class1_male_reduced_1000t.stl
├── bariatric_class1_female.stl
├── bariatric_class1_female_reduced_1000t.stl
├── bariatric_class2_male.stl
├── bariatric_class2_male_reduced_1000t.stl
├── bariatric_class2_female.stl
├── bariatric_class2_female_reduced_1000t.stl
├── bariatric_class3_male.stl
├── bariatric_class3_male_reduced_1000t.stl
├── bariatric_class3_female.stl
└── bariatric_class3_female_reduced_1000t.stl
```

### Step 2: Copy STL Files to Repository

**Manual Steps**:
1. Copy all 16 generated STL files from Phases 2-4 directly into `src/mypyskindose/phantom_data/`
2. Verify file counts:
   - 23 full-resolution STL files
   - 23 reduced-resolution STL files (46 total STL files)

**Verification**:
```bash
cd src/mypyskindose/phantom_data/
ls -1 *.stl | grep -v _reduced_1000t | wc -l  # Should output 23
```

### Step 3: Generate Reduced-Resolution Variants

**Purpose**: Create 1,000-face versions for fast GUI preview and quick calculations.

**Script for Batch Decimation**:
```python
# generate_reduced_variants.py
import sys
from pathlib import Path
import subprocess
import trimesh

def generate_reduced_variant(input_stl: Path, output_stl: Path, target_faces: int = 1000) -> bool:
    """Generate a reduced-face variant of an STL using trimesh."""
    try:
        # Load mesh
        mesh = trimesh.load(str(input_stl))
        
        # Get current face count
        current_faces = len(mesh.faces)
        print(f"Processing {input_stl.name}: {current_faces} faces")
        
        # Calculate decimation ratio
        ratio = target_faces / current_faces
        
        # Decimate mesh
        simplified = mesh.simplify_quadric_decimation(target_faces)
        
        # Export
        simplified.export(str(output_stl))
        
        # Verify result
        result_faces = len(simplified.faces)
        print(f"  → {output_stl.name}: {result_faces} faces")
        
        return True
        
    except Exception as e:
        print(f"ERROR processing {input_stl.name}: {e}")
        return False

def main():
    phantom_data_dir = Path("src/mypyskindose/phantom_data")
    
    # Find all full-resolution STLs (not reduced variants)
    full_res_stls = [
        f for f in phantom_data_dir.rglob("*.stl") 
        if not f.stem.endswith("_reduced_1000t")
    ]
    
    print(f"Found {len(full_res_stls)} full-resolution STLs")
    
    success_count = 0
    for stl_path in full_res_stls:
        # Generate output filename
        reduced_path = stl_path.parent / f"{stl.stem}_reduced_1000t.stl"
        
        # Skip if already exists
        if reduced_path.exists():
            print(f"Skipping {stl.name} (reduced variant exists)")
            continue
        
        # Generate reduced variant
        if generate_reduced_variant(stl_path, reduced_path):
            success_count += 1
    
    print(f"\nGenerated {success_count} reduced variants")

if __name__ == "__main__":
    main()
```

**Execution**:
```bash
python generate_reduced_variants.py
```

**Expected Output**:
```
Found 23 full-resolution STLs
Processing pediatric_5y_male.stl: 4500 faces
  → pediatric_5y_male_reduced_1000t.stl: 1000 faces
Processing pediatric_5y_female.stl: 4200 faces
  → pediatric_5y_female_reduced_1000t.stl: 1000 faces
...
Generated 16 reduced variants (23 total reduced variants)
```

### Step 4: Verify GUI Discovery

**Test that GUI discovers all phantoms**:
```python
from mypyskindose.gui.helpers import get_human_mesh_names

all_meshes = get_human_mesh_names()
print(f"Total meshes discovered: {len(all_meshes)}")
print("\nAll meshes:")
for mesh in sorted(all_meshes):
    print(f"  - {mesh}")
```

**Expected Output**:
```
Total meshes discovered: 23

All meshes:
  - adult_ectomorph_female
  - adult_ectomorph_male
  - adult_endomorph_female
  - adult_endomorph_male
  - adult_female
  - adult_male
  - adult_mesomorph_female
  - adult_mesomorph_male
  - bariatric_class1_female
  - bariatric_class1_male
  - bariatric_class2_female
  - bariatric_class2_male
  - bariatric_class3_female
  - bariatric_class3_male
  - hudfrid
  - junior_female
  - junior_male
  - pediatric_10y_female
  - pediatric_10y_male
  - pediatric_5y_female
  - pediatric_5y_male
  - senior_female
  - senior_male
```

### Step 5: Update AGENTS.md Documentation

**Update the phantom section in AGENTS.md**:

```markdown
Available human meshes: `hudfrid`, `adult_male`, `adult_female`, `junior_male`, `junior_female`, `senior_male`, `senior_female`, `pediatric_5y_male`, `pediatric_5y_female`, `pediatric_10y_male`, `pediatric_10y_female`, `adult_ectomorph_male`, `adult_ectomorph_female`, `adult_mesomorph_male`, `adult_mesomorph_female`, `adult_endomorph_male`, `adult_endomorph_female`, `bariatric_class1_male`, `bariatric_class1_female`, `bariatric_class2_male`, `bariatric_class2_female`, `bariatric_class3_male`, `bariatric_class3_female`
```

**Add new section**:
```markdown
### Phantom Library Organization

The phantom library is organized into categories:

- **Reference**: `hudfrid` - Original phantom from PySkinDose
- **Pediatric**: `pediatric_5y_*`, `pediatric_10y_*` - Children aged 5 and 10 years
- **Junior & Senior**: `junior_*`, `senior_*` - Adolescent and elderly phantoms
- **Adult Standard**: `adult_male`, `adult_female` - Standard adult phantoms
- **Adult Variants**: `adult_ectomorph_*`, `adult_mesomorph_*`, `adult_endomorph_*` - Body habitus variants
- **Bariatric**: `bariatric_class1_*`, `bariatric_class2_*`, `bariatric_class3_*` - BMI class I, II, III

All phantoms have reduced-resolution variants (`*_reduced_1000t`) for fast calculations.
```

### Step 6: Update README.md

**Add phantom library section to README.md**:
```markdown
## Phantom Library

MyPySkinDose includes 23 anthropomorphic phantoms covering diverse patient populations:

### Categories
- **Pediatric**: 5-year and 10-year children (both sexes)
- **Junior & Senior**: Adolescent and elderly phantoms
- **Adult**: Standard adults plus ectomorph/thin, mesomorph/average, and endomorph/heavy variants
- **Bariatric**: BMI class I, II, and III phantoms for obese patient populations

### Usage
Select phantoms via `settings.phantom.human_mesh` in the API or the GUI dropdown in Settings → Phantom Settings.

### Phantom Generation
The pediatric, adult variant, and bariatric phantoms were generated using MakeHuman parametric modeling. See `dev-docs/plans/MAKEHUMAN_PHANTOM_GENERATION_MASTER_PLAN.md` for details on the generation pipeline.
```

### Step 7: Comprehensive Integration Testing

**Test Suite Creation**:
```python
# test_phantom_library_integration.py
import pytest
from pathlib import Path
from mypyskindose import Phantom, PyskindoseSettings, load_settings_example_json
from mypyskindose.gui.helpers import get_human_mesh_names

class TestPhantomLibraryIntegration:
    """Test that all phantoms integrate correctly with MyPySkinDose."""
    
    @pytest.fixture
    def all_mesh_names(self):
        """Get all discovered mesh names."""
        return get_human_mesh_names()
    
    @pytest.fixture
    def phantom_dim(self):
        """Phantom dimensions for testing."""
        settings = PyskindoseSettings(load_settings_example_json())
        return settings.phantom.dimension
    
    def test_all_phantoms_discoverable(self, all_mesh_names):
        """Test that all expected phantoms are discovered by GUI."""
        expected_count = 23
        assert len(all_mesh_names) == expected_count, f"Expected {expected_count} phantoms, found {len(all_mesh_names)}"
        
        expected_phantoms = [
            "hudfrid",
            "adult_male", "adult_female",
            "junior_male", "junior_female",
            "senior_male", "senior_female",
            "pediatric_5y_male", "pediatric_5y_female",
            "pediatric_10y_male", "pediatric_10y_female",
            "adult_ectomorph_male", "adult_ectomorph_female",
            "adult_mesomorph_male", "adult_mesomorph_female",
            "adult_endomorph_male", "adult_endomorph_female",
            "bariatric_class1_male", "bariatric_class1_female",
            "bariatric_class2_male", "bariatric_class2_female",
            "bariatric_class3_male", "bariatric_class3_female",
        ]
        
        for phantom in expected_phantoms:
            assert phantom in all_mesh_names, f"Expected phantom {phantom} not discovered"
    
    @pytest.mark.parametrize("phantom_name", [
        "hudfrid", "adult_male", "adult_female",
        "pediatric_5y_male", "pediatric_10y_female",
        "adult_ectomorph_male", "adult_endomorph_female",
        "bariatric_class3_male", "bariatric_class1_female"
    ])
    def test_phantom_loading(self, phantom_dim, phantom_name):
        """Test that representative phantoms load successfully."""
        phantom = Phantom(
            phantom_model="human",
            phantom_dim=phantom_dim,
            human_mesh=phantom_name
        )
        
        assert len(phantom.r) > 0, f"Phantom {phantom_name} has no vertices"
        assert len(phantom.n) > 0, f"Phantom {phantom_name} has no normals"
        assert phantom.human_model == phantom_name
    
    def test_phantom_scaling(self, phantom_dim):
        """Test that scaling works correctly across phantom types."""
        # Test pediatric
        pediatric = Phantom("human", phantom_dim, "pediatric_5y_male")
        pediatric._apply_human_scale((1.1, 1.0, 1.0))
        assert len(pediatric.r) > 0
        
        # Test bariatric
        bariatric = Phantom("human", phantom_dim, "bariatric_class3_male")
        bariatric._apply_human_scale((1.0, 1.1, 1.0))
        assert len(bariatric.r) > 0
    
    def test_reduced_variants_exist(self):
        """Test that all phantoms have reduced variants."""
        phantom_data_dir = Path("src/mypyskindose/phantom_data")
        full_res = [f for f in phantom_data_dir.glob("*.stl") if not f.stem.endswith("_reduced_1000t")]
        
        for stl in full_res:
            reduced_path = stl.parent / f"{stl.stem}_reduced_1000t.stl"
            assert reduced_path.exists(), f"Reduced variant missing for {stl.name}"
    
    def test_coordinate_system_consistency(self, phantom_dim):
        """Test that all phantoms have consistent coordinate systems."""
        test_phantoms = [
            "pediatric_5y_male", "adult_male", "senior_male",
            "adult_ectomorph_male", "bariatric_class3_male"
        ]
        
        for phantom_name in test_phantoms:
            phantom = Phantom("human", phantom_dim, phantom_name)
            
            # Check that max Y is approximately 0 (posterior back surface contact plane)
            y_max = phantom.r[:, 1].max()
            assert abs(y_max) < 1.0, f"Phantom {phantom_name} Y-max {y_max} too far from 0"
            
            # Check that max Z is approximately 0 (superior head top plane)
            z_max = phantom.r[:, 2].max()
            assert abs(z_max) < 1.0, f"Phantom {phantom_name} Z-max {z_max} too far from 0"
            
            # Check that Z range is reasonable (human height along Z)
            z_range = abs(phantom.r[:, 2].min() - phantom.r[:, 2].max())
            assert 50 < z_range < 220, f"Phantom {phantom_name} Z-range {z_range} unrealistic"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Execution**:
```bash
pytest tests/unittests/test_phantom_library_integration.py -v
```

### Step 8: End-to-End Dose Calculation Test

**Test dose calculation with representative phantoms**:
```python
# test_phantom_dose_calculation.py
from mypyskindose import main, PyskindoseSettings, load_settings_example_json
from mypyskindose import get_path_to_example_rdsr_files
from pathlib import Path

def test_dose_calculation_with_phantoms():
    """Test dose calculation with representative phantoms."""
    
    # Load example RDSR
    rdsr_dir = get_path_to_example_rdsr_files()
    rdsr_file = rdsr_dir / "siemens_axiom_example_procedure.dcm"
    
    # Test phantoms
    test_phantoms = [
        "pediatric_10y_male",
        "adult_male",
        "adult_ectomorph_male",
        "bariatric_class2_male"
    ]
    
    for phantom_name in test_phantoms:
        print(f"\nTesting with phantom: {phantom_name}")
        
        # Configure settings
        settings = PyskindoseSettings(settings=load_settings_example_json())
        settings.mode = "calculate_dose"
        settings.output_format = "dict"
        settings.phantom.model = "human"
        settings.phantom.human_mesh = phantom_name
        
        try:
            # Run calculation
            output = main(file_path=rdsr_file, settings=settings)
            
            # Validate output
            assert "psd" in output, f"No PSD in output for {phantom_name}"
            assert output["psd"] > 0, f"PSD is zero for {phantom_name}"
            assert "dose_map" in output, f"No dose_map in output for {phantom_name}"
            
            print(f"  ✓ PSD: {output['psd']:.2f} mGy")
            print(f"  ✓ Dose map size: {len(output['dose_map'])}")
            
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            raise

if __name__ == "__main__":
    test_dose_calculation_with_phantoms()
    print("\n✓ All dose calculation tests passed")
```

**Execution**:
```bash
python test_phantom_dose_calculation.py
```

### Step 9: Performance Benchmarking

**Benchmark ray-casting performance across phantom types**:
```python
# benchmark_phantom_performance.py
import time
from mypyskindose import Phantom
from mypyskindose.settings.phantom_dimensions import PhantomDimensions

def benchmark_phantom_performance():
    """Benchmark ray-casting performance for different phantom types."""
    
    phantom_dim = PhantomDimensions()
    test_phantoms = [
        ("pediatric_5y_male", "Pediatric"),
        ("adult_male", "Adult"),
        ("adult_ectomorph_male", "Adult Ectomorph"),
        ("bariatric_class3_male", "Bariatric Class III")
    ]
    
    print("Phantom Performance Benchmark")
    print("=" * 60)
    print(f"{'Phantom':<25} {'Faces':<10} {'Load Time (s)':<15}")
    print("-" * 60)
    
    for phantom_name, category in test_phantoms:
        # Measure load time
        start_time = time.time()
        phantom = Phantom("human", phantom_dim, phantom_name)
        load_time = time.time() - start_time
        
        face_count = len(phantom.r) // 3
        
        print(f"{category:<25} {face_count:<10} {load_time:<15.3f}")
    
    print("=" * 60)

if __name__ == "__main__":
    benchmark_phantom_performance()
```

**Execution**:
```bash
python benchmark_phantom_performance.py
```

**Expected Output**:
```
Phantom Performance Benchmark
============================================================
Phantom                   Faces      Load Time (s)  
------------------------------------------------------------
Pediatric                 4500       0.12
Adult                     26756      0.45
Adult Ectomorph           6500       0.18
Bariatric Class III       7500       0.22
============================================================
```

### Step 10: Documentation Integration

**Create comprehensive phantom library documentation**:
```markdown
# Phantom Library Documentation

## Overview

MyPySkinDose includes 21 anthropomorphic phantoms for dose estimation across diverse patient populations.

## Phantom Categories

### Reference Phantoms
- `hudfrid`: Original phantom from PySkinDose, serves as validation reference

### Pediatric Phantoms
- `pediatric_5y_male`, `pediatric_5y_female`: 5-year-old children
- `pediatric_10y_male`, `pediatric_10y_female`: 10-year-old children

**Use Cases**: Pediatric fluoroscopy, cardiac catheterization in children

**Notes**: Higher head-to-body ratio, smaller torso dimensions affect dose distribution

### Adult Phantoms
- `adult_male`, `adult_female`: Standard adult reference phantoms

**Use Cases**: General adult fluoroscopy, dose calibration

### Adult Variant Phantoms
- `adult_ectomorph_male`, `adult_ectomorph_female: Thin body habitus (BMI ~19)
- `adult_mesomorph_male`, `adult_mesomorph_female`: Average body habitus (BMI ~23.5)
- `adult_endomorph_male`, `adult_endomorph_female`: Heavy body habitus (BMI ~29)

**Use Cases**: Body habitus sensitivity studies, population dose assessment

**Notes**: Ectomorph patients have less tissue attenuation, endomorph patients have increased backscatter

### Senior Phantoms
- `junior_male`, `junior_female`: Adolescent patients (~15 years)
- `senior_male`, `senior_female`: Elderly patients (~65 years)

**Use Cases**: Age-specific dose assessment, geriatric fluoroscopy

### Bariatric Phantoms
- `bariatric_class1_male`, `bariatric_class1_female`: BMI class I (30-35)
- `bariatric_class2_male`, `bariatric_class2_female`: BMI class II (35-40)
- `bariatric_class3_male`, `bariatric_class3_female`: BMI class III (40+)

**Use Cases**: Bariatric procedure dose assessment, obesity dose research

**Notes**: Increased tissue attenuation, table positioning challenges, higher backscatter

## Generation Methods

### Existing Phantoms
- `hudfrid`, `adult_*`, `junior_*`, `senior_*`: Original phantoms from PySkinDose

### MakeHuman Generated Phantoms
- Pediatric, adult variants, and bariatric phantoms generated using MakeHuman 1.2.0
- See `dev-docs/plans/MAKEHUMAN_PHANTOM_GENERATION_MASTER_PLAN.md` for generation pipeline
- Parameters documented in individual phantom parameter files

## Technical Specifications

### Coordinate System
- Units: centimeters
- Origin: Back contact plane at Y = 0.0, Head top at Z = 0.0, Lateral center at X = 0.0
- Patient orientation: Head-first supine along negative Z direction

### Mesh Quality
- Full resolution: 3,000-26,756 faces (varies by phantom)
- Reduced resolution: 1,000 faces (`*_reduced_1000t.stl` for all phantoms)
- All meshes are watertight with consistent triangle winding
- Normals recomputed by MyPySkinDose on load

### Performance
- Load time: 0.1-0.5 seconds (varies by face count)
- Ray-casting: < 5 seconds per event for all phantoms
- Reduced variants: < 1 second per event

## Usage

### API Usage
```python
from mypyskindose import PyskindoseSettings, load_settings_example_json, main

settings = PyskindoseSettings(load_settings_example_json())
settings.phantom.model = "human"
settings.phantom.human_mesh = "bariatric_class2_male"
output = main(file_path="procedure.dcm", settings=settings)
```

### GUI Usage
1. Open MyPySkinDose GUI
2. Navigate to Settings → Phantom Settings
3. Select phantom from "Human mesh" dropdown

## Deliverables Checklist

- [ ] All 16 new STL files copied to `src/mypyskindose/phantom_data/` (flat layout)
- [ ] Reduced-resolution variants generated (16 new files, 23 total)
- [ ] GUI discovery verified (23 total phantoms)
- [ ] AGENTS.md updated with complete phantom list
- [ ] README.md updated with phantom library section
- [ ] Integration test suite created and passing
- [ ] End-to-end dose calculation tests passing
- [ ] Performance benchmarks completed
- [ ] Validation summary report completed

## Final Validation Summary Report

```markdown
# Phantom Library Integration - Final Validation Summary

## Integration Overview
- **Total phantoms**: 23 (16 new + 7 existing)
- **New phantoms**: 16 (4 pediatric + 6 adult variants + 6 bariatric)
- **Reduced variants**: 23 (all phantoms have 1k-face versions; 46 STL files total)

## Integration Status
- [x] Flat file organization in `phantom_data/` completed
- [x] Reduced variants generated
- [x] GUI discovery verified (23 phantoms)
- [x] Integration tests passing
- [x] Dose calculation tests passing
- [x] Performance benchmarks completed

## Test Results Summary
- Phantom discovery: PASS (23/23 phantoms)
- Phantom loading: PASS (representative phantoms)
- Phantom scaling: PASS (all phantom types)
- Reduced variants: PASS (all 23 phantoms)
- Coordinate consistency: PASS (back at Y=0, head top at Z=0)

## Conclusion
The phantom library has been successfully expanded from 7 to 23 phantoms, providing comprehensive coverage of patient populations from pediatric to bariatric. All phantoms integrate seamlessly with MyPySkinDose and pass validation tests.
```

## Success Criteria

Phase 5 is complete when:

1. All 16 new STL files are integrated flat into `src/mypyskindose/phantom_data/`
2. All 23 phantoms are discoverable by the GUI
3. Reduced-resolution variants exist for all 23 phantoms
4. All integration tests pass
5. End-to-end dose calculations work with representative phantoms
6. Performance benchmarks are within acceptable ranges
7. Documentation is updated (AGENTS.md, README.md)
8. Validation summary report is completed

## Project Completion

Upon Phase 5 completion:
1. Create comprehensive summary of the phantom generation project
2. Archive all phase plans in `dev-docs/plans/archive/`
3. Update `dev-docs/index.md` with references to phantom library documentation
4. Prepare repository for pull request/merge

This completes the MakeHuman phantom generation master plan and sub-plans.
