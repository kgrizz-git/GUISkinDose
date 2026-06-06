# TO DO

Short-term task list for MyPySkinDose. Harness principles, validation commands, and the phased remediation roadmap live in:

- [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md)
- [HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md)

---

## Harness / docs

Repository hygiene, documentation, semver, and CI alignment. Harness-phase tags reference [HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md).

- [x] Clean this file up and apply consistent formatting and prioritization.
- [x] Align with harness engineering principles, semver, and CI.
- [x] Add a doc-freshness/harness check so stale feature-status statements are easier to catch automatically. **Harness Phase 1** — `python scripts/check_doc_freshness.py`
- [ ] Institute semver. **Harness Phase 2–3**
  - [x] Add root `CHANGELOG.md` (Keep a Changelog; version from `pyproject.toml`) — **Harness Phase 2**
- [ ] Institute trufflehog/gitleaks, dependabot, grype, basedpyright, etc. **Harness Phase 2–3**
  - [x] Dependabot configured for pip and GitHub Actions (2026-06-06)
- [ ] Add coordinate system diagrams to `VENDOR_COORDINATE_SYSTEMS.md` showing:
  - Unified internal coordinate system (axes, rotations, origin)
  - Visual comparison of Siemens vs Philips coordinate origins
  - Right-hand rule illustrations for rotations
  - Table position and beam angle conventions
  - Field size calculation geometry
  - [x] Initial mermaid diagrams added (2026-06-06); expand as vendor data is validated

---

## Input data & calculation

RDSR/tabular inputs, normalization, offsets, and dose-calculation behavior.

- [ ] Run examples in JupyterLab and compare.
- [ ] Check what all the original flow uses for inputs:
  - JSON files like `beam_collimation`, `beam_rotations`, etc.?
  - Normalization settings?
  - Should some of the example RDSRs use other data/settings from files in the repo?
  - Examples are projecting dose onto strange parts of body — seems like maybe some offset (in a setting or in RDSR) isn't being applied.
- [ ] K_IRP is all "-" in results table — took screenshot. **These may supposed to be (originally were?) correction factors, not kerma?**
- [ ] Implement tabular event-table inputs (`.csv`, `.tsv`, `.xlsx`) using the staged plan in `dev-docs/TABULAR_RDSR_INPUT_PLAN.md`. **Feature track** (not a harness phase; status in `FEATURE_INVENTORY.md`)
  - Start with normalized tabular inputs.
  - Then add raw RDSR-like tables.
  - Then adapt Radimetrics and DoseTrack mappings from https://github.com/dhen2714/PySkinDose after fixtures and validation are available.
  - These files may have more/less data than DICOM RDSRs and will need explicit column mapping, unit conversion, and provenance.
- [ ] Add some debug/warning if any dose events have no intersection with patient.
- [ ] Add support for multiple exams.
- [x] Is the RDSR table showing values straight out of the RDSR, or have they been processed/normalized in some way?
  - **Answer**: The table displays **Normalized Data**. The raw RDSR has been parsed, scaled, and translated (e.g., mm to cm, coordinate alignment) to match the internal physics engine's requirements.

---

## GUI / UX

NiceGUI workflow, geometry/positioning controls, exports, and in-app help.

- [ ] Show more details of irradiation events after loading, or have button for expanded RDSR browser (need to be able to see table lateral position, table height, collimated field area, etc. — all fields).
- [ ] Add sliders for patient offset parameters and show where patient is on the geometry plot in geometry tab.
  - Also allow setting max events for rendering patient as a box or slider (`max_events_for_patient_inclusion`).
  - Maybe it will also be worth having some presets for patient position (e.g. cardiac, head/neck, abdominal, etc).
  - Also when user adjusts sliders, have the patient position update in real time on the geometry plot in geometry tab.
- [x] Redesign GUI according to DESIGN.md.
- [ ] Download/export HTML button didn't work.
  - Not sure about others.
- [ ] Add help docs explaining what all the settings are in the GUI and how to use them.
  - Also use docstrings for all functions in the GUI (help button could show them).
  - Add help menu item in GUI to access `VENDOR_COORDINATE_SYSTEMS.md` and other technical documentation.
  - Make vendor coordinate system documentation accessible to users through GUI help system.
  - Clearly explain the two offset systems (Table vs Patient) in user-facing help documentation.
- [ ] Complete Phase 6 of `POSITIONING_HELP_PLAN.md` — integrate in-app help content with main documentation to maintain single source of truth.
  - **Further develop positioning help content as we gather more vendor-specific coordinate system information.**
- [x] Move Geometry tab to position 3 instead of 2.
- [ ] Allow manual interactive setting of table offsets in GUI.
- [ ] Collect and make available to users typical offsets for some systems — may depend on manufacturer/model but also table type — although there will probably usually be a limited number of tables commonly used with a given model.
- [ ] In Settings tab, show both Table Offsets (vendor-specific, read-only initially) and Patient Offsets (user-adjustable).
  - Eventually expose Table Offsets as user-adjustable as well (advanced feature).
  - Make it clear that Table Offsets are applied automatically during normalization.
  - Distinguish between machine coordinate transformation (Table) and patient positioning (Patient).
- [ ] Reduce spacing/padding around text elements in navigation section of left pane.
- [ ] Soften brutalist look? and make more sleek/modern.
- [ ] Refactor `app.py`.
- [ ] Change fonts?
- [ ] Add a light mode.
- [ ] Reduce color effects in GUI background slightly.
- [ ] Make native window for GUI launch larger.
- [ ] Make 'fake-scanner' not the default initially loaded RDSR in the upload tab.
- [x] Make the native window appear on top when it opens.

---

## Backlog / research

Ideas and naming not yet scheduled.

- [ ] Call it GUISkinDose?
