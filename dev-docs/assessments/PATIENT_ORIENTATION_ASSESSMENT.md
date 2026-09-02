> **NEEDS REVIEW** — This assessment has not yet been reviewed by a domain expert. Conclusions may be incomplete or incorrect.

# Patient Orientation Assessment

Investigated: 2026-06-26

## Summary

The codebase supports **two of eight** standard DICOM `PatientPosition` values:
- `head_first_supine` (HFS) — the default everywhere
- `feet_first_supine` (FFS)

**Prone and decubitus positions are entirely absent** from the code, settings, GUI, and constants.

---

## What exists

### Constants (`constants.py:269-270`)
```python
PATIENT_ORIENTATION_HEAD_FIRST_SUPINE = "head_first_supine"
PATIENT_ORIENTATION_FEET_FIRST_SUPINE = "feet_first_supine"
```

### Settings dataclass (`settings/phantom_settings.py:38-83`)
`patient_orientation` field on `PhantomSettings`, defaulting to `head_first_supine`.

### Geometry logic (`geom_calc.py:83-133`)
`position_patient_phantom_on_table()` applies a **180° Y-axis rotation** when `feet_first_supine` is selected. No other orientation has any logic.

### GUI (`gui/tabs/settings.py:89-90`)
A `ui.select` dropdown with two options, bound to `state.patient_orientation`.

### Export (`format_export_data.py:397,425`)
Orientation is recorded in the export's `Patient` dict.

### Documentation (`FEATURE_INVENTORY.md:142,385`, `CODEBASE_OVERVIEW.md:219`)
Listed as a feature supporting HFS and FFS.

---

## What is missing

### No prone or decubitus support
The six other DICOM `PatientPosition` values (HFP, FFP, HFDL, HFDR, FFDL, FFDR) have no constants, no geometry logic, no GUI controls, and no phantom transformations.

### No DICOM auto-detection
The `rdsr_parser` never reads `PatientPosition` (0018,5100) or `PatientOrientation` (0010,2120). Orientation is always manually set.

### No input-adapter handling
None of the four input adapters (`normalized`, `generic_rdsr_like`, `radimetrics`, `dosetrack`) parse or map patient orientation.

### Prone would require non-trivial geometry changes
- Phantom creation assumes head at z=0, feet extending negative-z.
- The skin-dose mapping, backscatter correction, and beam-to-patient geometric relationship all assume a supine patient (anterior exposure).
- A prone patient would expose the posterior, flipping the phantom's front/back relationship to the beam.
- Decubitus would add lateral orientation, further complicating the geometry.

### No GUI indicator on the Geometry plot
The 3D preview does not display or label the current patient orientation.

---

## Files examined

- `src/guiskindose/constants.py`
- `src/guiskindose/settings/phantom_settings.py`
- `src/guiskindose/settings_example.json`
- `src/guiskindose/user_defined_parameters.py`
- `src/guiskindose/dev_data.py`
- `src/guiskindose/geom_calc.py`
- `src/guiskindose/rdsr_normalizer.py`
- `src/guiskindose/rdsr_parser.py`
- `src/guiskindose/phantom_class.py`
- `src/guiskindose/calculate_dose/calculate_dose.py`
- `src/guiskindose/plotting/create_geometry_plot.py`
- `src/guiskindose/analyze_data.py`
- `src/guiskindose/format_export_data.py`
- `src/guiskindose/gui/constants.py`
- `src/guiskindose/gui/state.py`
- `src/guiskindose/gui/tabs/settings.py`
- `src/guiskindose/gui/settings_builder.py`
- `src/guiskindose/input_adapters/*`
