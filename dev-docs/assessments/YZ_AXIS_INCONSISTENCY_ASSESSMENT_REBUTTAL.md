# Y/Z Axis Inconsistency Assessment Rebuttal

**Status:** Resolved — original bug claim withdrawn based on DICOM Table Coordinate System definitions.  
**Scope:** `src/guiskindose/`, `AGENTS.md`, related dev-docs

This document serves as a rebuttal to `YZ_AXIS_INCONSISTENCY_ASSESSMENT.md`. The original assessment concluded that "The code is internally consistent — every file in the codebase uses the same convention. The bug is purely in AGENTS.md's documentation" and dismissed the table mesh orientation as a "visual paradox."

However, this is incorrect. The codebase is actually **severely internally inconsistent**, maintaining two mutually exclusive geometric conventions that actively contradict each other. This causes a critical geometric bug where DICOM translation and collimation are applied perpendicularly to the patient's physical orientation.

## 1. Convention A: Physical 3D Geometry (X = Lateral, Y = Vertical, Z = Longitudinal)
The physical math that places meshes and rotates the C-arm treats **Z as the longitudinal (head-to-foot) axis** and **X as the lateral (left-to-right) axis**:

* **Mesh Orientation**: In `phantom_class.py`, the table is drawn with its width along X (`x_tab = ... table_width`) and its length along Z (`z_tab = ... table_length`). The human phantom is similarly scaled with `scale_lon` applied to the Z-axis and `scale_lat` applied to the X-axis.
* **Patient Placement**: In `geom_calc.py`, when the patient is oriented "feet-first", they are rotated 180° around the Y-axis, and the code uses the Z-axis (`patient.r[:, 2].min()`) to find the longitudinal center of the patient.
* **C-arm Rotations**: In `beam_class.py`, `Ap1` (DICOM Primary Angle, representing LAO/RAO) correctly rotates around the Z-axis (swinging around the patient's sides). `Ap2` (DICOM Secondary Angle, representing CRAN/CAUD) correctly rotates around the X-axis (tilting head-to-foot).

## 2. Convention B: Translations, Collimation, and Labels (X = Longitudinal, Y = Vertical, Z = Lateral)
The code that normalizes DICOM data, applies translations, sets collimator blades, and labels the UI treats **X as the longitudinal axis** and **Z as the lateral axis**:

* **DICOM Translation**: In `rdsr_normalizer.py`, `TableLongitudinalPosition` is explicitly mapped to `Tx` (translating the table along the X-axis) and `TableLateralPosition` is mapped to `Tz` (translating along the Z-axis).
* **Collimation**: In `beam_class.py`, longitudinal field size (`FS_long`) scales the X-axis of the beam, and lateral field size (`FS_lat`) scales the Z-axis.
* **Labels & Comments**: `constants.py` explicitly dictates `PLOT_AXIS_TITLE_X = "X - LON"` and `PLOT_AXIS_TITLE_Z = "Z - LAT"`. The angle comments in `beam_class.py` incorrectly label the Z-axis as `(LAT)` and the X-axis as `(LON)`.

## 3. The Resulting Bug
Because PySkinDose physically places the patient's length along Z, but translates the `TableLongitudinalPosition` along X, **longitudinal table motion in the simulation causes the patient to translate sideways (laterally) across the X-ray beam.** 

Similarly, lateral table motion moves the patient head-to-foot, and the X-ray collimator blades (`FS_long` vs `FS_lat`) are rotated 90 degrees relative to the patient's body. The prior assessment's claim that *"no dose calculation depends on axis labels, only on the geometry"* is flawed because the translation and collimator variables are applied to the wrong geometric axes.

## 4. Note on AGENTS.md
`AGENTS.md` is also technically incorrect. It claims `X = lateral, Y = longitudinal, Z = vertical`, which gets Y and Z backwards relative to both conventions (Y is definitively the vertical/anterior-posterior axis everywhere in the code).

## 5. Action Items
This issue requires deep architectural investigation and broad clarification in the repository's documentation. The coordinate system discrepancy needs to be formally resolved to fix the geometric translation and collimation bugs.

## 6. Evaluation of the Response (Post-Review)
The updated `YZ_AXIS_INCONSISTENCY_ASSESSMENT.md` clarifies that the DICOM standard (PS3.3, C.8.7.2) natively defines the Table Coordinate System such that:
- **X-axis = Lateral** (increases to patient's left)
- **Y-axis = Vertical** (increases upward)
- **Z-axis = Longitudinal** (increases toward patient's head)

Crucially, the standard's attributes are named counter-intuitively relative to the axes they translate along:
- `TableLongitudinalPosition` measures translation along the DICOM X-axis (Lateral).
- `TableLateralPosition` measures translation along the DICOM Z-axis (Longitudinal).

**Conclusion Revision:**
The response successfully proves that there is **no geometric calculation bug**. PySkinDose correctly maps the DICOM X-axis (`TableLongitudinalPosition`) to its simulation X-axis (`Tx`), which is physically the lateral dimension of the patient. The physical mapping is completely accurate. 

The confusion stems entirely from the fact that PySkinDose's comments and plot labels (e.g., `X - LON`) inherited the misleading *names* of the DICOM attributes, rather than describing the physical axes they represent. The "Convention B" listed in Section 2 above is a labeling convention problem, not a physical geometry problem.

The action item for `AGENTS.md` should be updated exactly as recommended in the response, capturing this nuance rather than continuing to use oversimplified and misleading labels.
