# Phase 1: MakeHuman Setup and Testing

> **SUPERSEDED (2026-07-21).** See [`AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](../AUTOMATED_PHANTOM_LIBRARY_PLAN.md).

## Objective

Establish a working MakeHuman environment, create a test phantom, and develop the validation pipeline to ensure all subsequent phantoms will integrate correctly with MyPySkinDose.

## Prerequisites

- Python 3.11+ installed
- Git access to MyPySkinDose repository
- Administrative access for software installation
- 2-3 GB free disk space for software installations

## Required Tools Installation

### 1. Install MakeHuman 1.2.0

**Download**: http://www.makehumancommunity.org/

**Installation Steps**:
1. Download the appropriate version for your OS:
   - Windows: `makehuman-1.2.0-windows.zip`
   - macOS: `makehuman-1.2.0-macosx.dmg`
   - Linux: `makehuman-1.2.0-linux.tar.gz`

2. Extract/install to a convenient location (e.g., `~/tools/makehuman/`)

3. Launch MakeHuman and verify it opens correctly:
   ```bash
   # On macOS/Linux
   cd ~/tools/makehuman
   ./makehuman
   
   # On Windows
   cd tools/makehuman
   makehuman.exe
   ```

4. Navigate through the GUI to ensure basic functionality:
   - Click on different tabs (Modelling, Clothes, Pose)
   - Verify the 3D viewport renders the default human model
   - Test camera controls (rotate, zoom, pan)

### 2. Install Blender 3.6+

**Download**: https://www.blender.org/download/

**Installation Steps**:
1. Download Blender 3.6+ for your OS
2. Install to default location or `~/tools/blender/`
3. Launch Blender and verify:
   - 3D viewport opens with default cube
   - User preferences accessible
   - Python console available (View → Toggle System Console)

### 3. Install Python Dependencies

In your MyPySkinDose development environment:

```bash
cd MyPySkinDose
pip install numpy-stl trimesh
```

**Verification**:
```python
python -c "import stl; import trimesh; print('Dependencies installed successfully')"
```

## MyPySkinDose Integration Test Setup

### 1. Clone and Setup MyPySkinDose

```bash
git clone <repository-url>
cd MyPySkinDose
pip install -e ".[dev]"
```

### 2. Verify Existing Phantom Loading

```python
from mypyskindose import Phantom
from mypyskindose.settings.phantom_dimensions import PhantomDimensions

# Test loading an existing phantom
phantom_dim = PhantomDimensions()
phantom = Phantom(
    phantom_model="human",
    phantom_dim=phantom_dim,
    human_mesh="adult_male"
)

print(f"Phantom loaded: {len(phantom.r)} vertices")
print(f"Phantom normals: {len(phantom.n)} normals")
```

Expected output:
```
Phantom loaded: 80268 vertices
Phantom normals: 80268 normals
```

## MakeHuman Test Phantom Generation

### 1. Launch MakeHuman and Create Base Model

**Manual Steps**:
1. Open MakeHuman
2. Accept the default human model (this will be our starting point)
3. Navigate to the **Modelling** tab
4. Set the following parameters for a test adult male:
   - **Age**: 25 years
   - **Gender**: Male
   - **Weight**: 75 kg (average adult)
   - **Height**: 175 cm (average adult)
   - **Muscle**: 50% (mesomorph build)
   - **Body Proportions**: Keep defaults

5. Save the model:
   - File → Save As → `makehuman_test_male.mhm`

### 2. Export to OBJ Format

**Manual Steps**:
1. In MakeHuman, go to **Files → Export**
2. Choose **OBJ (Wavefront)** format
3. Ensure these export settings:
   - **Scale**: 1.0 (default)
   - **Export helpers**: Unchecked
   - **Export clothes**: Unchecked (we want skin surface only)
   - **Export rig**: Unchecked
4. Save as `makehuman_test_male.obj`

### 3. Import into Blender for Processing

**Manual Steps**:
1. Open Blender
2. File → Import → Wavefront (.obj)
3. Select `makehuman_test_male.obj`
4. Verify the mesh imports correctly:
   - Mesh should be visible in 3D viewport
   - Object should be selected
   - Scale should be reasonable (human-sized)

### 4. Coordinate System Transformation

**MyPySkinDose Coordinate Requirements**:
- Units: centimeters
- Lateral axis (`X` / `PT L-R`): Centered at `X = 0.0` (spanning `-width/2` to `+width/2`)
- Vertical axis (`Y` / `PT A-P`): Posterior skin back contact plane is at `Y = 0.0` (max Y), and anterior chest/abdomen extends into negative Y (spanning `-thickness` to `0.0`)
- Longitudinal axis (`Z` / `PT S-I`): Superior head top is at `Z = 0.0` (max Z), and patient body extends along negative Z (spanning `-height` to `0.0`)
- Patient orientation: Head-first supine along negative Z direction

**Blender Transformation Steps**:
1. With the mesh selected, press `N` to open the transform panel
2. Check the current dimensions in the **Item** section
3. If the mesh is in meters (MakeHuman default), scale it:
   - Right-click → Scale → Press `S`, then `0.01` (meters to centimeters)
   - Or set scale factors to 0.01 in the transform panel

4. Rotate for head-first supine orientation in MyPySkinDose frame:
   - MakeHuman default: Standing (Y-up, Z-front, X-right)
   - Rotate around X axis by -90° (lay supine with head toward Z)
   - Rotate around Y axis by 180° so head points along negative Z, back points toward Y=0 (upward in Blender frame)

5. Align mesh origins to MyPySkinDose reference planes:
   - Set X location so the mesh is centered laterally (`(min X + max X) / 2 = 0.0`)
   - Set Y location so the highest Y vertex (posterior back surface) sits at `Y = 0.0` (`Y_position = -max_Y`)
   - Set Z location so the highest Z vertex (superior top of head) sits at `Z = 0.0` (`Z_position = -max_Z`)

6. Apply transforms:
   - Right-click → Apply → Scale
   - Right-click → Apply → Rotation
   - Right-click → Apply → Location

### 5. Mesh Decimation

**Target**: 5,000-8,000 faces for test phantom

**Manual Steps**:
1. Switch to **Edit Mode** (Tab)
2. Press `A` to select all vertices
3. In the **Modifiers** panel (blue wrench icon), add **Decimate** modifier
4. Set these parameters:
   - **Ratio**: 0.1 (reduces to ~10% of original faces)
   - **Iterations**: 1
   - **Collapse Threshold**: 0.1
5. Click **Apply** on the modifier
6. Check face count in the **Stats** panel (top-right of viewport)
7. Adjust ratio if needed to achieve 5k-8k faces

### 6. Export to STL Format

**Manual Steps**:
1. File → Export → STL
2. Ensure these settings:
   - **Selection Only**: Checked
   - **Batch Mode**: Off
   - **Scale**: 1.0
   - **ASCII**: Unchecked (use binary STL)
3. Save as `makehuman_test_male.stl`

## Automated Validation Script

Create a Python script to validate the test phantom:

```python
# validate_phantom.py
import sys
from pathlib import Path
import numpy as np
from stl import mesh

def validate_phantom_stl(stl_path: Path) -> dict:
    """Validate an STL phantom against MyPySkinDose requirements."""
    
    results = {
        'file_exists': False,
        'loadable': False,
        'vertex_count': 0,
        'face_count': 0,
        'y_min': 0.0,
        'y_max': 0.0,
        'z_min': 0.0,
        'z_max': 0.0,
        'is_watertight': False,
        'coordinate_scale': 'unknown',
        'passed': False
    }
    
    # Check file exists
    if not stl_path.exists():
        print(f"ERROR: File not found: {stl_path}")
        return results
    
    results['file_exists'] = True
    
    try:
        # Load STL
        phantom_mesh = mesh.Mesh.from_file(str(stl_path))
        results['loadable'] = True
        
        # Count vertices and faces
        results['vertex_count'] = len(phantom_mesh.vectors) * 3
        results['face_count'] = len(phantom_mesh.vectors)
        
        # Check coordinate ranges
        all_vertices = phantom_mesh.vectors.reshape(-1, 3)
        results['y_min'] = float(all_vertices[:, 1].min())
        results['y_max'] = float(all_vertices[:, 1].max())
        results['z_min'] = float(all_vertices[:, 2].min())
        results['z_max'] = float(all_vertices[:, 2].max())
        
        # Check coordinate scale (if Z range is ~175cm, units are centimeters)
        z_range = abs(results['z_min'] - results['z_max'])
        if 50 < z_range < 220:  # Human height in cm
            results['coordinate_scale'] = 'centimeters'
        elif 0.5 < z_range < 2.2:  # Human height in meters
            results['coordinate_scale'] = 'meters (needs conversion)'
        
        # Check alignment: back surface at Y=0 and head top at Z=0
        y_at_origin = abs(results['y_max']) < 1.0  # Within 1cm tolerance
        z_at_origin = abs(results['z_max']) < 1.0  # Within 1cm tolerance
        
        # Basic watertight check
        try:
            import trimesh
            trimesh_mesh = trimesh.load(str(stl_path))
            results['is_watertight'] = trimesh_mesh.is_watertight
        except ImportError:
            print("WARNING: trimesh not available, skipping watertight check")
            results['is_watertight'] = 'unknown'
        
        # Determine if phantom passes basic checks
        results['passed'] = (
            results['loadable'] and
            results['coordinate_scale'] == 'centimeters' and
            y_at_origin and
            z_at_origin and
            (results['is_watertight'] is True or results['is_watertight'] == 'unknown') and
            3000 <= results['face_count'] <= 15000
        )
        
    except Exception as e:
        print(f"ERROR loading STL: {e}")
        return results
    
    return results

def main():
    if len(sys.argv) != 2:
        print("Usage: python validate_phantom.py <path_to_stl>")
        sys.exit(1)
    
    stl_path = Path(sys.argv[1])
    results = validate_phantom_stl(stl_path)
    
    print("\n=== Phantom Validation Results ===")
    print(f"File: {stl_path}")
    print(f"File exists: {results['file_exists']}")
    print(f"Loadable: {results['loadable']}")
    print(f"Face count: {results['face_count']}")
    print(f"Y range (AP): {results['y_min']:.2f} to {results['y_max']:.2f} cm")
    print(f"Z range (S-I): {results['z_min']:.2f} to {results['z_max']:.2f} cm")
    print(f"Coordinate scale: {results['coordinate_scale']}")
    print(f"Watertight: {results['is_watertight']}")
    print(f"Passed basic validation: {results['passed']}")
    
    if results['passed']:
        print("\n✓ Phantom passed basic validation")
        return 0
    else:
        print("\n✗ Phantom failed validation")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

## Run Validation

```bash
python validate_phantom.py makehuman_test_male.stl
```

Expected output:
```
=== Phantom Validation Results ===
File: makehuman_test_male.stl
File exists: True
Loadable: True
Face count: 5000
Y range (AP): -30.40 to 0.00 cm
Z range (S-I): -175.00 to 0.00 cm
Coordinate scale: centimeters
Watertight: True
Passed basic validation: True

✓ Phantom passed basic validation
```

## MyPySkinDose Integration Test

Test loading the phantom into MyPySkinDose:

```python
# test_mypyskindose_integration.py
from pathlib import Path
from mypyskindose import Phantom, PyskindoseSettings, load_settings_example_json

settings = PyskindoseSettings(load_settings_example_json())
phantom_dim = settings.phantom.dimension
test_stl = Path("makehuman_test_male.stl")

try:
    # Load as custom phantom (tuple format)
    phantom = Phantom(
        phantom_model="human",
        phantom_dim=phantom_dim,
        human_mesh=("makehuman_test_male", test_stl)
    )
    
    print(f"✓ Phantom loaded successfully")
    print(f"  Vertices: {len(phantom.r)}")
    print(f"  Normals: {len(phantom.n)}")
    print(f"  Mesh name: {phantom.human_model}")
    
    # Test scaling
    phantom._apply_human_scale((1.1, 1.0, 1.0))
    print(f"✓ Scaling test passed")
    
    # Test normal recomputation
    phantom._recompute_human_normals_from_triangles()
    print(f"✓ Normal recomputation test passed")
    
    print("\n✓ All MyPySkinDose integration tests passed")
    
except Exception as e:
    print(f"✗ Integration test failed: {e}")
    import traceback
    traceback.print_exc()
```

## Parameter Documentation Template

Create a template for documenting MakeHuman parameters:

```markdown
# Phantom Parameter Documentation: makehuman_test_male

## MakeHuman Parameters
- Age: 25 years
- Gender: Male
- Weight: 75 kg
- Height: 175 cm
- Muscle: 50%
- Body Proportions: Default

## Blender Processing
- Scale transformation: Meters to centimeters (×0.01)
- Y alignment: Lowest point to Y=0
- Rotation: 90° around X axis (supine orientation)
- Decimation ratio: 0.1 (10% of original faces)
- Final face count: ~5,000

## Validation Results
- Coordinate scale: Centimeters
- Y range: 0.00 to 180.00 cm
- Watertight: Yes
- MyPySkinDose integration: Passed

## Notes
- This is a test phantom to validate the pipeline
- Used to establish coordinate system transformation workflow
- Serves as reference for subsequent phantom generation
```

## Troubleshooting Common Issues

### Issue: Phantom is too small/large in MyPySkinDose
**Solution**: Check coordinate scale in validation script. If in meters, re-export from Blender with proper scaling.

### Issue: Phantom floats above table or sinks into it
**Solution**: Verify Y alignment step. The lowest Y coordinate must be 0.0 after transformation.

### Issue: Normal orientation is incorrect
**Solution**: In Blender, use Mesh → Normals → Recalculate Outside before exporting.

### Issue: Mesh is not watertight
**Solution**: In Blender, use Mesh → Clean Up → Merge By Distance, then check for holes with 3D Print Toolbox addon.

### Issue: Face count is too high/low
**Solution**: Adjust decimation ratio in Blender. Target 3k-5k for pediatric, 5k-8k for adult/bariatric.

## Deliverables Checklist

- [ ] MakeHuman 1.2.0 installed and tested
- [ ] Blender 3.6+ installed and tested  
- [ ] Python dependencies installed (numpy-stl, trimesh)
- [ ] Test phantom generated: `makehuman_test_male.stl`
- [ ] Validation script created: `validate_phantom.py`
- [ ] MyPySkinDose integration test created: `test_mypyskindose_integration.py`
- [ ] Test phantom passes validation script
- [ ] Test phantom loads in MyPySkinDose
- [ ] Parameter documentation template created
- [ ] Coordinate system transformation documented
- [ ] Troubleshooting guide completed

## Success Criteria

Phase 1 is complete when:

1. MakeHuman and Blender are installed and functional
2. Test phantom (`makehuman_test_male.stl`) is generated
3. Validation script confirms:
   - File is loadable
   - Coordinates are in centimeters
   - Lowest Y is at 0 (table contact plane)
   - Mesh is watertight
   - Face count is in target range (3k-8k)
4. MyPySkinDose successfully loads the test phantom
5. Scaling and normal recomputation work correctly
6. Parameter documentation template is established
7. Coordinate system transformation workflow is documented

## Handoff to Phase 2

Upon Phase 1 completion, provide:
- Test phantom file (`makehuman_test_male.stl`)
- Validation script (`validate_phantom.py`)
- Integration test script (`test_mypyskindose_integration.py`)
- Parameter documentation template
- Coordinate system transformation notes
- This phase plan with any lessons learned

These artifacts will be used as the foundation for pediatric phantom generation in Phase 2.
