# TO DO

* run examples in jupyterlab and compare
- check what all the original flow uses for inputs
    - json files like beam_collimation, beam_rotations etc?
    - normalization settings?
    - should some of the example RDSRs use other data/settings from files in the repo?
    - examples are projecting dose onto strange parts of body - seems like maybe some offset (in a setting or in RDSR) isn't being applied
- K_IRP is all "-" in results table - took screenshot **These may supposed to be (originally were?) correction factors, not kerma?**
* show more details of irradiation events after loading, or have button for expanded rdsr browser (need to be able to see table lateral position, table height, collimated field area, etc - all fields)
* add sliders for patient offset parameters and show where patient is on the geometry plot in geometry tab. 
    - also allow setting max events for rendering patient as a box or slider (max_events_for_patient_inclusion)
    - maybe it will also be worth having some presets for patient position (e.g. cardiac, head/neck, abdominal, etc)
    - also when user adjusts sliders, have the patient position update in real time on the geometry plot in geometry tab
- [x] redesign GUI according to DESIGN.md
* add some debug/warning if any dose events have no intersection with patient
- download/export HTML button didn't work
    - not sure about others
- [ ] Implement tabular event-table inputs (`.csv`, `.tsv`, `.xlsx`) using the staged plan in `dev-docs/TABULAR_RDSR_INPUT_PLAN.md`.
    - Start with normalized tabular inputs.
    - Then add raw RDSR-like tables.
    - Then adapt Radimetrics and DoseTrack mappings from https://github.com/dhen2714/PySkinDose after fixtures and validation are available.
    - These files may have more/less data than DICOM RDSRs and will need explicit column mapping, unit conversion, and provenance.
- [ ] Add a doc-freshness/harness check so stale feature-status statements are easier to catch automatically.
- add help docs explaining what all the settings are in the GUI and how to use it
    - also use docstrings for all functions in the GUI (help button could show them)
- [x] move Geometry tab to position 3 instead of 2
- add support for multiple exams
- [x] is the rdsr table showing values straight out of the rdsr, or have they been processed/normalized in some way?
    - **Answer**: The table displays **Normalized Data**. The raw RDSR has been parsed, scaled, and translated (e.g., mm to cm, coordinate alignment) to match the internal physics engine's requirements.
- [x] make the native window appear on top when it opens
- institute semver
- institute trufflehog/gitleaks, dependabot, grype, basedpyright, etc
* allow manual interactive setting of table offsets in gui
- call it GUISkinDose?
- reduce spacing/padding around text elements in navigation section of left pane
- soften brutalist look? and make more sleek/modern
* refactor app.py
- change fonts?
* add a light mode
