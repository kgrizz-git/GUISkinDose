# Y/Z Axis Convention Inconsistency Assessment

**Date:** 2026-06-26 (updated after rebuttal review)  
**Status:** Reviewed — rebuttal integrated, analysis revised, recommendation updated  
**Scope:** `src/mypyskindose/`, `AGENTS.md`, related dev-docs

> AGENTS.md line 150 documents the coordinate system as `X = lateral, Y = longitudinal, Z = vertical`. This does not match the code.

---

## 1. The Inconsistency

| Convention | X | Y | Z |
|------------|---|---|---|
| **AGENTS.md** (documented) | lateral | longitudinal | vertical |
| **Code reality** | **longitudinal (LON)** | **vertical (VER)** | **lateral (LAT)** |

The codebase uses a single convention in its comments and plot labels (X=longitudinal, Y=vertical, Z=lateral), but this convention is *physically wrong* — it derives from the misleading DICOM attribute names (see §7 for full analysis). The physical mesh geometry tells a different story: the table width runs along x (lateral) and table length runs along z (longitudinal). AGENTS.md is wrong on all three axes. However, the **data mapping is correct** — DICOM tags flow to the right world axes for dose calculation. See §7.2 for the detailed explanation.

---

## 2. Evidence

### 2.1 Authoritative axis labels in `constants.py:164-166`

```python
PLOT_AXIS_TITLE_X = "X - LON [cm]"
PLOT_AXIS_TITLE_Y = "Y - VER [cm]"
PLOT_AXIS_TITLE_Z = "Z - LAT [cm]"
```

These labels are used throughout all plotting code. X=longitudinal, Y=vertical, Z=lateral.

### 2.2 RDSR normalizer — definitive DICOM mapping (`rdsr_normalizer.py:196-200`)

```python
data_norm["Tx"] = norm.trans_offset.x + norm.trans_dir.x * data_parsed.TableLongitudinalPosition_mm / 10
data_norm["Ty"] = norm.trans_offset.y + norm.trans_dir.y * data_parsed.TableHeightPosition_mm / 10
data_norm["Tz"] = norm.trans_offset.z + norm.trans_dir.z * data_parsed.TableLateralPosition_mm / 10
```

DICOM `TableLongitudinalPosition` → Tx (x-axis). DICOM `TableHeightPosition` → Ty (y-axis). DICOM `TableLateralPosition` → Tz (z-axis). This is the unambiguous ground truth.

The docstring at `rdsr_normalizer.py:64-81` explicitly states:
- Tx = "Table offset in x-direction (longitudinal direction)"
- Ty = "Table offset in y-direction (vertical direction)"
- Tz = "Table offset in z-direction (lateral direction)"

### 2.3 Beam class angle comments (`beam_class.py:60-70`)

```python
# Positioner isocenter primary angle (Ap1) — rotation about the z axis (LAT)
# Positioner isocenter secondary angle (Ap2) — rotation about the x axis (LON)
# Positioner isocenter detector rotation angle (Ap3) — rotation about the y axis (VERT)
```

### 2.4 Beam collimation axes (`beam_class.py:116-117`)

```python
r[1:, 0] *= data_norm.FS_long[event]  # longitudinal collimation -> x-axis
r[1:, 2] *= data_norm.FS_lat[event]   # lateral collimation -> z-axis
```

The beam fires in the negative y direction (`beam_class.py:103`):
```python
delta_r = np.array([0, data_norm.DSI[event], 0])
```
Source-to-isocenter distance is along y, confirming Y=vertical.

### 2.5 Patient placement on table (`geom_calc.py:126`)

```python
patient.translate(dr=[0, -pad_thickness, 0])
```

The patient is lowered vertically onto the pad by translating in y. Confirms Y=vertical.

### 2.6 Phantom vertex comments (`phantom_class.py:234-259`)

Table and pad vertex arrays are labeled:
```python
x_tab = [...]  # Longitudinal position
y_tab = [...]  # Vertical position
z_tab = [...]  # Lateral position
```

### 2.7 Scale parameter mapping (`phantom_class.py:281-293`)

```python
def _apply_human_scale(self, scale: tuple[float, float, float]) -> None:
    scale_array = np.asarray(scale, dtype=float)
    anchor = np.array([
        (self.r[:, 0].min() + self.r[:, 0].max()) / 2.0,  # x center
        self.r[:, 1].max(),                                 # y max
        self.r[:, 2].max(),                                 # z max
    ])
    self.r = anchor + (self.r - anchor) * scale_array
```

Called with `human_scale=(scale_lat, scale_ap, scale_lon)`. So `scale_lat` scales x (longitudinal), `scale_lon` scales z (lateral). The scale parameter names are inconsistent with the code's convention — they reflect the raw STL mesh orientation, not the working coordinate system.

### 2.8 Patient offset mapping (`settings/patient_offset.py:19-24`, `constants.py:240-242`)

```python
# Settings field names
d_lat: int  # lateral offset
d_lon: int  # longitudinal offset
d_ver: int  # vertical offset

# Constants
OFFSET_LATERAL_KEY = "d_lat"
OFFSET_VERTICAL_KEY = "d_ver"
OFFSET_LONGITUDINAL_KEY = "d_lon"
```

Used as `patient_offset = [d_lon, d_ver, d_lat]` which maps to `[Tx, Ty, Tz]` → x (longitudinal), y (vertical), z (lateral).

### 2.9 Plotting hover text (`plotting/create_geometry_plot_texts.py`)

Every hover reads `r[ind, 0]` as "LON", `r[ind, 1]` as "VER", `r[ind, 2]` as "LAT".

### 2.10 GUI labels

`gui/tabs/settings.py:159-167` and `gui/tabs/geometry.py:161-164` label the offset controls as Longitudinal/Vertical/Lateral mapping to `d_lon`/`d_ver`/`d_lat` respectively. Consistent with code convention.

---

## 3. The Table Axis Paradox

There is one subtlety: in `phantom_class.py:237`, the table's `z_tab` is labeled "Lateral" but uses `phantom_dim.table_length` — the table's longest physical dimension. Similarly, `Phantom.position()` offsets the rotation center by `table_length/2` along z (`phantom_class.py:379`).

This means the table's physical long axis (head-to-foot direction) runs along the z-axis, which the code labels "LAT" (lateral). While the DICOM `TableLongitudinalPosition` maps to Tx (x-axis), the table mesh itself is oriented with its length along z.

This creates a visual paradox when viewing the 3D plot: the table extends along the axis labeled "Z - LAT [cm]". This is confusing but is a label problem, not a geometric error — the dose calculations are internally consistent. The `VENDOR_XZ_CLARIFICATION_PLAN.md` proposes more explicit axis labels (e.g., `X/LON`, `Y/VER`, `Z/LAT`) to help users map between the plotted geometry and clinical directions.

---

## 4. What Needs to Change

### Mandatory

- **AGENTS.md line 150.** Replace:
  ```
  - The coordinate system: X = lateral, Y = longitudinal, Z = vertical
  ```
  with:
  ```
  - The coordinate system: X = longitudinal (LON), Y = vertical (VER), Z = lateral (LAT)
  ```

### Optional / lower priority

- **Scale parameter names** (`scale_lat`, `scale_lon`): These are user-facing in the GUI and the JSON settings file. They are misleading — `scale_lat` scales x (longitudinal), `scale_lon` scales z (lateral). Renaming would be a breaking change to the settings schema. Consider at least adding a comment in `phantom_settings.py` documenting the axis mapping.

- **Table axis orientation:** The table mesh has its long dimension along z (labeled "LAT"). This is safe because no dose calculation depends on axis labels, only on the geometry. However, the plotting labels are confusing. The `VENDOR_XZ_CLARIFICATION_PLAN.md` proposes a UI-level fix.

- **Other documentation files** referencing the stale convention:
  - `dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md` — check for stale axis references
  - `dev-docs/CODEBASE_OVERVIEW.md` — check for stale axis references
  - `ADDITIONAL_PHANTOMS.md` lines 56-57 and 84 — these already describe the correct convention but should be cross-checked after AGENTS.md is fixed

---

## 5. Files Audited

| File | Lines inspected | Axis evidence |
|------|----------------|---------------|
| `constants.py` | 164-166 | PLOT_AXIS_TITLE constants: X=LON, Y=VER, Z=LAT |
| `rdsr_normalizer.py` | 64-81, 196-200 | Tx=longitudinal, Ty=vertical, Tz=lateral |
| `beam_class.py` | 60-70, 103, 116-117, 181-214 | Angle comments, DSI along y, FS collimation |
| `phantom_class.py` | 107-123, 234-259, 281-293, 336-392 | Vertex labels, scale anchor, translate/position |
| `geom_calc.py` | 88, 107-108, 126, 509, 576-654 | Pad lowering in y, table orientation |
| `settings/patient_offset.py` | 19-24 | Field names (d_lat, d_lon, d_ver) |
| `plotting/create_geometry_plot_texts.py` | all | Hover text column labels |
| `gui/tabs/settings.py` | 159-167 | GUI offset labels |
| `gui/tabs/geometry.py` | 161-164 | GUI slider labels |
| `create_geometry_plot.py` | 51, 60-64 | Scale+offset mapping |
| `calculate_dose.py` | 70-74 | Offset mapping |

No file was found using the AGENTS.md documented convention (X=lateral, Y=longitudinal, Z=vertical). The inconsistency is a documentation error in AGENTS.md, but the code's own comment convention (x=longitudinal, z=lateral) is itself physically misleading — see §7 for the full DICOM-based analysis.

---

## 6. Related

- `dev-docs/plans/VENDOR_XZ_CLARIFICATION_PLAN.md` — proposes explicit axis labels in the GUI
- `dev-docs/ADDITIONAL_PHANTOMS.md` § "Corrections and clarifications" — first flag of this inconsistency
- `dev-docs/TO_DO.md` — tracking item (linked to this assessment)


## 7. Response to Rebuttal (`YZ_AXIS_INCONSISTENCY_ASSESSMENT_REBUTTAL.md`)

### 7.1 Areas of agreement

The rebuttal correctly observes that **code comments and plot labels say one thing while the physical mesh geometry says another**. The table mesh has its width along x and its length along z (`phantom_class.py:234-259`). Yet `constants.py` labels the x-axis "LON" and the z-axis "LAT." This label-vs-geometry contradiction is real and confusing. The rebuttal also correctly notes that AGENTS.md line 150 is wrong under any interpretation — it gets Y and Z backward relative to all conventions in the codebase.

### 7.2 The claimed geometric bug — does it exist?

The rebuttal's central claim is:

> Because PySkinDose physically places the patient's length along Z, but translates the TableLongitudinalPosition along X, **longitudinal table motion in the simulation causes the patient to translate sideways**.

This claim is incorrect. The data mapping is actually right, but the DICOM attribute naming is deeply misleading. Here is why.

#### 7.2.1 The DICOM Table Coordinate System

DICOM PS3.3, section C.8.7.2, defines the Table Coordinate System for isocenter-based fluoroscopy equipment as follows:

| Axis | Direction | Physical meaning |
|------|-----------|-----------------|
| Table X | Increases to patient's **left** | Lateral (across the table) |
| Table Y | Increases **upward** | Vertical |
| Table Z | Increases toward patient's **head** | Longitudinal (along the table) |

The DICOM *attributes* that report table position:
- **(0018,9329) Table Longitudinal Position**: measured in the **X direction** of the Table CS → *lateral* (left-right)
- **(0018,932A) Table Lateral Position**: measured in the **Z direction** of the Table CS → *longitudinal* (head-foot)

The DICOM attribute names are **backward** from intuition: "Table Longitudinal Position" actually measures lateral movement, and "Table Lateral Position" actually measures longitudinal movement. This is a known wrinkle in the DICOM standard.

#### 7.2.2 The data flow is correct

`rdsr_parser.py` extracts these concept-name values verbatim from the RDSR, producing `data_parsed.TableLongitudinalPosition_mm` and `data_parsed.TableLateralPosition_mm`. Then `rdsr_normalizer.py:196-200` maps them:

```python
data_norm["Tx"] = ... + data_parsed.TableLongitudinalPosition_mm / 10   # DICOM X (lateral)
data_norm["Tz"] = ... + data_parsed.TableLateralPosition_mm / 10        # DICOM Z (longitudinal)
```

Finally `Phantom.position()` applies `[Tx, Ty, Tz]` to `self.r[:, 0]`, `self.r[:, 1]`, `self.r[:, 2]` respectively.

**Tracing a concrete example:** A real C-arm procedure shifts the table 10 cm toward the patient's left. In DICOM, this is reported as `TableLongitudinalPosition = 10` (because DICOM's X increases to the left). The normalizer puts this into `Tx = 10`. `Phantom.position()` translates the phantom by +10 along world x. The table mesh has its width along x, so the patient moves 10 cm across the table — **lateral movement, correct**.

Now the table shifts 20 cm toward the patient's head. DICOM reports `TableLateralPosition = 20` (because DICOM's Z increases toward the head). The normalizer puts this into `Tz = 20`. `Phantom.position()` translates by +20 along world z. The table mesh has its length along z, so the patient moves 20 cm along the table — **longitudinal movement, correct**.

**The mapping is correct.** The rebuttal's "sideways translation" bug does not exist because the DICOM attribute names are the wrong way around relative to their physical meaning.

#### 7.2.3 Why the code comments are misleading

The code's comment convention (x="longitudinal", z="lateral") appears to derive from the DICOM *attribute names*, not the physical direction:

> "TableLongitudinalPosition goes into Tx (x-axis), so x must be longitudinal."

This is a category error — the DICOM attribute is named "Longitudinal" but measures lateral movement. The code's comment convention propagates this mislabeling throughout the plotting code (`constants.py:164-166`, `beam_class.py:60-70`, `phantom_class.py:234-259`). The dose calculation is unaffected because it works with raw data, not comment labels.

#### 7.2.4 The GE/Philips vendor convention

Update after GE inspection: the GE lateral/longitudinal issue should be treated
as a high-confidence RDSR-level convention, not as a tabular export-only quirk.
GE table travel has been confirmed by inspection as positive lateral = patient
left, positive longitudinal = cranial, and positive height = down for
head-first positioning. MyPySkinDose now handles this through the
normalization-layer `swap_lateral_longitudinal` setting for the GE manufacturer
wildcard, before deriving `Tx` and `Tz`.

The GUI `swap_lat_lon` mechanism remains useful, but it is now a manual expert
override for tabular imports rather than the default GE architecture. A matched
GE DICOM RDSR plus tabular export from the same case is still needed to pin
exact fixture values and confirm tabular parity.

### 7.3 Revised assessment of AGENTS.md

The original assessment stated "the bug is purely in AGENTS.md's documentation." This was an oversimplification. The full picture is:

| Layer | X axis represents | Z axis represents | Status |
|-------|------------------|-------------------|--------|
| Physical mesh geometry (table/patient) | Lateral (across table) | Longitudinal (along table) | Ground truth |
| DICOM attribute naming | "Table Longitudinal Position" | "Table Lateral Position" | Misleading (names are swapped vs. physical direction) |
| Code comments and plot labels | "LON" | "LAT" | Wrong — inverted relative to physical geometry, derived from DICOM attribute names rather than physical direction |
| Data mapping (DICOM tags → Tx/Ty/Tz → Phantom.position) | Lateral movement | Longitudinal movement | **Correct** |
| AGENTS.md line 150 | "lateral" | "vertical" | Wrong on all three axes |

**Recommendation for AGENTS.md:** Replace line 150 with a more nuanced statement that acknowledges the complexity, e.g.:

```
- The coordinate system: X = lateral (across-table), Y = vertical, Z = longitudinal (along-table).
  Plot axis labels use X/LON, Y/VER, Z/LAT — where "LON" and "LAT" reflect the DICOM attribute
  names mapped to those axes (rdsr_normalizer.py:196-200), not the physical direction. See
  dev-docs/assessments/YZ_AXIS_INCONSISTENCY_ASSESSMENT.md for the full analysis.
```

### 7.4 Verdict

- **No geometric bug.** The data flow from DICOM tags through `rdsr_normalizer.py` to `Phantom.position()` applies translations in the correct physical directions.
- **Real confusion.** DICOM attribute naming is misleading (TableLongitudinalPosition measures lateral movement). The code's comment convention inherits this misleading naming.
- **Code works.** This is consistent with the user's observation that "the code basically seems to work" — it does, because the mapping is correct.
- **AGENTS.md fix needed.** The one-line fix should be applied, but the documentation should capture the nuance rather than replacing one oversimplification with another.
