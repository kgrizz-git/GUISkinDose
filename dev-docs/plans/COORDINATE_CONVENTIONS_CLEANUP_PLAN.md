# Coordinate Conventions Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make coordinate conventions understandable and consistent across documentation, GUI labels, code comments, and vendor-validation backlog without changing dose geometry unless matched fixtures prove a behavioral bug.

**Architecture:** Treat `dev-docs/VENDOR_COORDINATE_SYSTEMS.md` as the canonical coordinate reference. Keep calculation behavior stable first, add characterization tests around the current DICOM-to-`Tx/Ty/Tz` mapping, then update user-facing and agent-facing docs to distinguish physical axes, DICOM attribute names, PySkinDose display aliases, and GUI post-normalization correction toggles.

**Tech Stack:** Python, pandas, pytest, NiceGUI help markdown, Sphinx markdown sources, `scripts/sync_gui_help.py`, `scripts/check_doc_freshness.py`.

---

## Context And Decision Record

The current repo has three overlapping coordinate descriptions:

| Layer | Current state | Cleanup decision |
|---|---|---|
| Physical mesh/world geometry | X is across table/lateral, Y is vertical, Z is along table/longitudinal. | Document as physical geometry. Do not rename calculation columns in this plan. |
| DICOM table coordinate attributes | `TableLongitudinalPosition` maps to DICOM X/lateral motion; `TableLateralPosition` maps to DICOM Z/longitudinal motion. The names are misleading. | Document explicitly with DICOM tag numbers and a worked example. |
| PySkinDose display aliases | Existing plot labels are `X - LON`, `Y - VER`, `Z - LAT`; these aliases follow historical PySkinDose naming, not physical direction. | Keep for compatibility until a separately validated relabel/refactor exists; add explanatory labels/help. |
| Normalized DataFrame | `Tx`, `Ty`, `Tz` are consumed directly by geometry and dose code. | Characterize current behavior with tests before editing comments/docs. |
| GUI tabular corrections | `swap_lat_lon` swaps `Tx <-> Tz` after normalization for tabular imports. | Keep as a manual expert override only; GE is handled in normalization to avoid double-correction. |

GE convention confirmed by inspection for head-first positioning:

- positive GE lateral table travel means patient left
- positive GE longitudinal table travel means cranial
- positive GE height table travel means down

High-confidence implementation assumption: GE lateral/longitudinal handling is baked in at the RDSR level, so GE needs a `Tx <-> Tz` correction before or inside normalization. Keep one validation gap open: compare a matched GE DICOM RDSR and GE tabular export from the same case to pin exact fixture values and confirm whether the export preserves the same RDSR-level frame.

## File Structure

- Modify: `dev-docs/VENDOR_COORDINATE_SYSTEMS.md`
  - Canonical coordinate reference: terminology, DICOM definitions, physical/world axes, display aliases, vendor validation matrix, GE confirmed convention.
- Modify: `dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md`
  - Short link-out to canonical coordinate reference; keep offset hierarchy here.
- Modify: `dev-docs/COORD_TRANSFORM_COMPARISON.md`
  - Mark as comparison/history, not canonical; fix stale axis claims.
- Modify: `AGENTS.md`
  - Replace one-line coordinate shorthand with a nuanced pointer to the canonical doc.
- Modify: `docs/source/gui_help/positioning_offsets.md`
  - Fix stale `X/Y/Z = lateral/longitudinal/vertical` quick reference.
- Modify: `docs/source/gui_help/geometry_workflow.md`
  - Add a short coordinate legend for the Geometry tab.
- Generated: `src/mypyskindose/gui/help/positioning_offsets.md`
- Generated: `src/mypyskindose/gui/help/geometry_workflow.md`
  - Produced only by `python scripts/sync_gui_help.py`.
- Modify: `src/mypyskindose/rdsr_normalizer.py`
  - Update docstring language and apply `swap_lateral_longitudinal` before table translations.
- Modify: `src/mypyskindose/settings/normalization_settings.py`
  - Load the optional `swap_lateral_longitudinal` flag and support manufacturer wildcard models.
- Modify: `src/mypyskindose/normalization_settings.json`
  - Add a GE Healthcare wildcard entry with zero offsets/signs and `swap_lateral_longitudinal: true`.
- Modify: `src/mypyskindose/constants.py`
  - No default axis relabel in this plan. Optional only if paired with tests and docs explaining display aliases.
- Create: `tests/unittests/test_coordinate_conventions.py`
  - Characterization tests for normalizer mapping and GUI transform helpers.
- Modify: `dev-docs/TO_DO.md`
  - Replace contradictory coordinate backlog text with this plan link.
- Modify: `dev-docs/index.md`
  - Add this plan and update assessment descriptions.

## Task 1: Characterize Current DICOM Mapping

**Files:**
- Create: `tests/unittests/test_coordinate_conventions.py`
- Read: `src/mypyskindose/rdsr_normalizer.py`
- Read: `src/mypyskindose/settings/pyskindose_settings.py`

- [ ] **Step 1: Write the failing characterization tests**

Add this file:

```python
import pandas as pd

from mypyskindose import PyskindoseSettings, load_settings_example_json
from mypyskindose.rdsr_normalizer import rdsr_normalizer


def _settings() -> PyskindoseSettings:
    settings = PyskindoseSettings(settings=load_settings_example_json())
    return settings


def _parsed_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Manufacturer": ["Default"],
            "ManufacturerModelName": ["Default"],
            "DistanceSourcetoDetector_mm": [1000.0],
            "FinalDistanceSourcetoDetector_mm": [1000.0],
            "DistanceSourcetoIsocenter_mm": [700.0],
            "IrradiationEventType": ["Fluoroscopy"],
            "AcquisitionPlane": ["Single Plane"],
            "TableLongitudinalPosition_mm": [100.0],
            "TableHeightPosition_mm": [200.0],
            "TableLateralPosition_mm": [300.0],
            "FilterMaterial": [["Copper", "Aluminum"]],
            "FilterThicknessMinimum_mm": [[0.1, 1.0]],
            "FilterThicknessMaximum_mm": [[0.1, 1.0]],
            "PositionerPrimaryAngle_deg": [10.0],
            "PositionerSecondaryAngle_deg": [20.0],
            "CollimatedFieldArea_m2": [0.01],
            "KVP_kV": [80.0],
            "DoseRP_Gy": [0.5],
        }
    )


def test_dicom_table_position_attributes_map_to_tx_ty_tz_without_axis_relabeling():
    normalized = rdsr_normalizer(_parsed_frame(), _settings())

    assert normalized.loc[0, "Tx"] == 10.0
    assert normalized.loc[0, "Ty"] == 20.0
    assert normalized.loc[0, "Tz"] == 30.0


def test_current_plot_axis_titles_are_historical_pyskindose_aliases():
    from mypyskindose.constants import PLOT_AXIS_TITLE_X, PLOT_AXIS_TITLE_Y, PLOT_AXIS_TITLE_Z

    assert PLOT_AXIS_TITLE_X == "X - LON [cm]"
    assert PLOT_AXIS_TITLE_Y == "Y - VER [cm]"
    assert PLOT_AXIS_TITLE_Z == "Z - LAT [cm]"
```

- [ ] **Step 2: Run tests to verify the current behavior**

Run:

```bash
pytest tests/unittests/test_coordinate_conventions.py -q
```

Expected: PASS. If this fails because the synthetic frame misses a required parser column, add only the missing column with a neutral value and rerun.

- [ ] **Step 3: Commit**

```bash
git add tests/unittests/test_coordinate_conventions.py
git commit -m "test: characterize coordinate convention mapping"
```

## Task 2: Make `VENDOR_COORDINATE_SYSTEMS.md` Canonical

**Files:**
- Modify: `dev-docs/VENDOR_COORDINATE_SYSTEMS.md`

- [ ] **Step 1: Replace the opening coordinate section**

Replace the current "Unified Internal Coordinate System" section with this structure:

```markdown
## Coordinate Frames And Names

This document is the canonical coordinate reference for MyPySkinDose.

### Physical world geometry

For the default head-first supine patient orientation:

| World axis | Physical direction | Positive direction |
|---|---|---|
| X | Lateral, across the table | Patient left |
| Y | Vertical / table height | See vendor-normalized `Ty`; GE confirmed positive height travel is down |
| Z | Longitudinal, along the table | Cranial / toward patient head |

The table mesh width is along X and table length is along Z.

### DICOM table coordinate attributes

DICOM RDSR table-position concept names are easy to misread:

| DICOM attribute | DICOM table axis | Physical direction for HFS |
|---|---|---|
| `(0018,9329) Table Longitudinal Position` | X | Lateral |
| `(0018,932A) Table Lateral Position` | Z | Longitudinal |
| `(0018,9328) Table Height Position` | Y | Vertical |

The attribute names are not the same thing as the physical direction labels used in the mesh.

### Normalized DataFrame columns

`rdsr_normalizer.py` maps raw parsed RDSR values into centimeters:

```python
Tx = offset.x + direction.x * TableLongitudinalPosition_mm / 10
Ty = offset.y + direction.y * TableHeightPosition_mm / 10
Tz = offset.z + direction.z * TableLateralPosition_mm / 10
```

`Tx`, `Ty`, and `Tz` are calculation columns. They should not be renamed without a separate fixture-backed refactor.

### PySkinDose display aliases

Existing plots label axes as `X - LON`, `Y - VER`, and `Z - LAT`. These are historical PySkinDose display aliases tied to normalized table-position names. They are not a reliable statement of physical direction. When precision matters, write both forms, for example `Tx / X display axis / physical lateral`.
```

- [ ] **Step 2: Add the GE convention subsection**

Add this under the vendor-specific section:

```markdown
### GE Healthcare

Status: convention confirmed by inspection; matched DICOM/export validation still pending.

For head-first positioning, confirmed GE table-travel convention:

| GE table travel | Positive direction |
|---|---|
| Lateral | Patient left |
| Longitudinal | Cranial |
| Height | Down |

GE RDSR-level lateral/longitudinal handling is high-confidence: GE appears to encode table lateral/longitudinal values in the opposite convention from the current `rdsr_normalizer()` mapping and therefore needs a `Tx <-> Tz` correction at, or before, normalization. Open validation item: inspect one matched GE DICOM RDSR and one tabular export from the same case to pin exact raw values and confirm whether the tabular export preserves the same RDSR-level frame.
```

- [ ] **Step 3: Replace stale GE swap wording**

Find any text claiming GE swap handling is only export-path dependent. Replace it with:

```markdown
GE DICOM RDSR lateral/longitudinal handling is a high-confidence RDSR-level convention: GE needs a `Tx <-> Tz` correction before or inside normalization. GE tabular exports are expected to inherit that frame unless the export tool transforms coordinates. The current GUI post-normalization `swap_lat_lon` toggle is a tabular workaround, not the final GE DICOM architecture.
```

- [ ] **Step 4: Run doc freshness**

```bash
python scripts/check_doc_freshness.py
```

Expected: no broken links introduced.

- [ ] **Step 5: Commit**

```bash
git add dev-docs/VENDOR_COORDINATE_SYSTEMS.md
git commit -m "docs: clarify canonical coordinate conventions"
```

## Task 3: Fix Stale Agent And Developer Docs

**Files:**
- Modify: `AGENTS.md`
- Modify: `dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md`
- Modify: `dev-docs/COORD_TRANSFORM_COMPARISON.md`
- Modify: `dev-docs/ADDITIONAL_PHANTOMS.md`

- [ ] **Step 1: Replace the AGENTS.md shorthand**

Replace the one-line coordinate convention with:

```markdown
- Coordinate conventions are nuanced: physical world geometry uses X=lateral, Y=vertical, Z=longitudinal for head-first supine positioning, while historical PySkinDose plot aliases show `X - LON`, `Y - VER`, `Z - LAT`. DICOM table-position attribute names are misleading; see `dev-docs/VENDOR_COORDINATE_SYSTEMS.md` before changing normalization, plotting labels, or vendor coordinate handling.
```

- [ ] **Step 2: Add link-out notes to secondary docs**

In `INPUT_DATA_FLOW_AND_OFFSETS.md`, add near the top:

```markdown
Coordinate terminology lives in `VENDOR_COORDINATE_SYSTEMS.md`. This file explains data flow and offset hierarchy; it should not redefine axis semantics independently.
```

In `COORD_TRANSFORM_COMPARISON.md`, add near the top:

```markdown
This comparison is historical and diagnostic. The canonical coordinate terminology is `VENDOR_COORDINATE_SYSTEMS.md`.
```

- [ ] **Step 3: Update `ADDITIONAL_PHANTOMS.md` references**

Replace any statement that says AGENTS.md is the coordinate authority with a pointer to `VENDOR_COORDINATE_SYSTEMS.md`. Keep mesh-authoring advice focused on physical geometry: X width/lateral, Y vertical, Z length/longitudinal.

- [ ] **Step 4: Run checks**

```bash
python scripts/check_agent_guidance.py
python scripts/check_doc_freshness.py
```

Expected: no new strict failures. Advisory findings that predate this work can be left for separate cleanup if they are unrelated.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md dev-docs/COORD_TRANSFORM_COMPARISON.md dev-docs/ADDITIONAL_PHANTOMS.md
git commit -m "docs: centralize coordinate guidance"
```

## Task 4: Fix GUI Help And Sync Mirrors

**Files:**
- Modify: `docs/source/gui_help/positioning_offsets.md`
- Modify: `docs/source/gui_help/geometry_workflow.md`
- Generated: `src/mypyskindose/gui/help/positioning_offsets.md`
- Generated: `src/mypyskindose/gui/help/geometry_workflow.md`

- [ ] **Step 1: Replace stale quick reference in positioning help**

Use this table:

```markdown
| Control | Calculation field | Existing plot alias | Physical effect for HFS |
|---|---|---|---|
| Lateral | `d_lat` / `Tz`-related patient placement | `Z - LAT` | Side-to-side placement after normalized geometry is built |
| Longitudinal | `d_lon` / `Tx`-related patient placement | `X - LON` | Head-foot placement after normalized geometry is built |
| Vertical | `d_ver` / `Ty`-related patient placement | `Y - VER` | Up-down placement |
| Rotation | patient rotation setting | about vertical axis | Rotates patient around the table-height axis |
```

Add this note immediately below it:

```markdown
The `LON` and `LAT` plot aliases are historical PySkinDose labels. For developer-level details, including the DICOM attribute-name mismatch, see `dev-docs/VENDOR_COORDINATE_SYSTEMS.md`.
```

- [ ] **Step 2: Add a coordinate legend to geometry workflow help**

Add a short section:

```markdown
## Coordinate Legend

Geometry plots currently use historical PySkinDose axis aliases: `X - LON`, `Y - VER`, and `Z - LAT`. These labels identify the plotted calculation frame, not every physical/DICOM naming convention. Vendor normalization and import correction toggles are applied before the Geometry preview is drawn.

For GE inputs, the lateral/longitudinal swap is expected at the RDSR level and is handled during normalization. The GUI `Tx <-> Tz` swap is a manual expert override only. GE table travel has been confirmed by inspection as positive lateral = patient left, positive longitudinal = cranial, and positive height = down for head-first positioning. A matched GE DICOM RDSR plus tabular export is still needed to pin fixture values and tabular parity.
```

- [ ] **Step 3: Sync mirrored GUI help**

```bash
python scripts/sync_gui_help.py
```

Expected: the two files under `src/mypyskindose/gui/help/` match their `docs/source/gui_help/` sources.

- [ ] **Step 4: Run checks**

```bash
python scripts/check_doc_freshness.py
```

Expected: no broken links introduced.

- [ ] **Step 5: Commit**

```bash
git add docs/source/gui_help/positioning_offsets.md docs/source/gui_help/geometry_workflow.md src/mypyskindose/gui/help/positioning_offsets.md src/mypyskindose/gui/help/geometry_workflow.md
git commit -m "docs: explain GUI coordinate aliases"
```

## Task 5: Clarify Code Comments Without Changing Behavior

**Files:**
- Modify: `src/mypyskindose/rdsr_normalizer.py`
- Modify: `src/mypyskindose/beam_class.py`
- Modify: `src/mypyskindose/phantom_class.py`

- [ ] **Step 1: Update `rdsr_normalizer.py` docstring**

Replace the `Tx`, `Ty`, `Tz` docstring bullets with wording in this style:

```python
            - Tx (float)
                Normalized table translation column in cm. It is populated from
                DICOM TableLongitudinalPosition_mm after vendor offset/sign
                handling. In DICOM table coordinates this value corresponds to
                table X motion; for head-first supine positioning this is
                physical lateral motion.
            - Ty (float)
                Normalized table height translation column in cm, populated from
                DICOM TableHeightPosition_mm after vendor offset/sign handling.
            - Tz (float)
                Normalized table translation column in cm. It is populated from
                DICOM TableLateralPosition_mm after vendor offset/sign handling.
                In DICOM table coordinates this value corresponds to table Z
                motion; for head-first supine positioning this is physical
                longitudinal motion.
```

- [ ] **Step 2: Update comments that call X "longitudinal" or Z "lateral"**

In `beam_class.py` and `phantom_class.py`, replace bare comments such as `x-axis (LON)` or `z-axis (LAT)` with comments that say `historical display alias` when that is what the code means. Do not alter arrays, rotations, field-size math, or normalized column names in this task.

- [ ] **Step 3: Run characterization tests**

```bash
pytest tests/unittests/test_coordinate_conventions.py -q
```

Expected: PASS, proving comment changes did not affect behavior.

- [ ] **Step 4: Commit**

```bash
git add src/mypyskindose/rdsr_normalizer.py src/mypyskindose/beam_class.py src/mypyskindose/phantom_class.py tests/unittests/test_coordinate_conventions.py
git commit -m "docs: clarify coordinate comments"
```

## Task 6: Clarify TODO And Index Tracking

**Files:**
- Modify: `dev-docs/TO_DO.md`
- Modify: `dev-docs/index.md`

- [ ] **Step 1: Replace the contradictory TODO item**

Replace the current Y/Z item with:

```markdown
- [ ] **Coordinate conventions cleanup** — centralize physical axes, DICOM table-coordinate definitions, PySkinDose plot aliases, vendor normalization signs, GE confirmed table-travel convention, and tabular `Tx <-> Tz` correction behavior. Plan: `plans/COORDINATE_CONVENTIONS_CLEANUP_PLAN.md`. Assessment: `assessments/YZ_AXIS_INCONSISTENCY_ASSESSMENT.md`. Validation still needed: one matched GE DICOM RDSR plus tabular export.
```

Keep the separate vendor-coordinate-validation item if it points to fixture validation. If both items become redundant, make the vendor item a sub-bullet under coordinate cleanup instead of leaving two competing sources of truth.

- [ ] **Step 2: Update `dev-docs/index.md`**

Add this row under execution plans:

```markdown
| `plans/COORDINATE_CONVENTIONS_CLEANUP_PLAN.md` | Centralizes coordinate terminology across physical axes, DICOM table-coordinate attributes, PySkinDose plot aliases, vendor conventions, GE validation, GUI help, and agent guidance. |
```

Update the `YZ_AXIS_INCONSISTENCY_ASSESSMENT.md` row to avoid saying "the entire codebase uses X=longitudinal/Y=vertical/Z=lateral" as settled truth. Use:

```markdown
| `assessments/YZ_AXIS_INCONSISTENCY_ASSESSMENT.md` | Audit of coordinate naming contradictions: physical geometry, DICOM attribute names, and historical PySkinDose plot aliases differ; current recommendation is documentation/comment cleanup plus fixture-backed validation before behavior changes. |
```

- [ ] **Step 3: Run checks**

```bash
python scripts/check_doc_freshness.py
python scripts/check_agent_guidance.py
```

Expected: no broken links introduced. Existing advisory backlog warnings can remain if unrelated.

- [ ] **Step 4: Commit**

```bash
git add dev-docs/TO_DO.md dev-docs/index.md dev-docs/plans/COORDINATE_CONVENTIONS_CLEANUP_PLAN.md
git commit -m "docs: plan coordinate convention cleanup"
```

## Task 7: Matched GE DICOM And Export Validation

**Files:**
- Modify: `dev-docs/VENDOR_COORDINATE_SYSTEMS.md`
- Create or modify: `dev-docs/references/ge_coordinate_validation.md`
- Optional private local files: `test_data_gitignored/ge_coordinate_case/`

- [ ] **Step 1: Prepare a private validation folder**

Do not commit PHI or restricted data. If local files are used, keep them under a gitignored path:

```bash
mkdir -p test_data_gitignored/ge_coordinate_case
```

- [ ] **Step 2: Record non-sensitive validation metadata**

Create `dev-docs/references/ge_coordinate_validation.md` with this template:

```markdown
# GE Coordinate Validation Notes

No source data is committed here.

## Confirmed By Inspection

For head-first positioning:

| GE table travel | Positive direction |
|---|---|
| Lateral | Patient left |
| Longitudinal | Cranial |
| Height | Down |

## Matched Case Validation

Status: pending matched GE DICOM RDSR plus tabular export from the same case.

When available, record only de-identified aggregate values:

| Source | Table longitudinal range | Table lateral range | Table height range | Notes |
|---|---:|---:|---:|---|
| DICOM RDSR | pending | pending | pending | pending |
| Tabular export | pending | pending | pending | pending |

Validation questions:

1. What exact raw DICOM table-position values appear in a known GE motion direction?
2. Does the tabular export preserve the same RDSR-level frame or transform the coordinates?
3. Does the implemented normalizer-level GE `Tx <-> Tz` correction produce the expected Geometry preview?
4. Does applying a second GUI `Tx <-> Tz` correction produce an obviously wrong Geometry preview?
```

- [ ] **Step 3: Update canonical doc validation matrix**

Add a row to `VENDOR_COORDINATE_SYSTEMS.md`:

```markdown
| GE DICOM RDSR plus matched tabular export | pending matched fixture | GE positive lateral=patient left, longitudinal=cranial, height=down confirmed by inspection; RDSR-level `Tx`/`Tz` correction expected; exact fixture values and tabular parity still pending |
```

- [ ] **Step 4: Commit docs only**

```bash
git add dev-docs/VENDOR_COORDINATE_SYSTEMS.md dev-docs/references/ge_coordinate_validation.md
git commit -m "docs: track GE coordinate validation"
```

## Acceptance Criteria

- `dev-docs/VENDOR_COORDINATE_SYSTEMS.md` is the only canonical coordinate terminology reference.
- `AGENTS.md`, GUI help, and secondary dev docs point to the canonical doc instead of restating stale shorthand.
- Documentation distinguishes physical axes, DICOM attribute names, normalized `Tx/Ty/Tz`, historical plot aliases, and tabular import corrections.
- The confirmed GE convention is recorded exactly: positive lateral is patient left, positive longitudinal is cranial, positive height is down for head-first positioning.
- GE matched-case validation remains explicitly open until one DICOM RDSR and one tabular export from the same case are inspected.
- Characterization tests protect the current normalizer mapping and current plot-axis titles before any comment or label edits.
- No calculation behavior changes in this plan unless a later fixture-backed plan proves a mismatch.
- `dev-docs/TO_DO.md` and `dev-docs/index.md` point to this plan and no longer describe the issue as a settled severe geometry bug.

## Verification Commands

Run after implementation:

```bash
pytest tests/unittests/test_coordinate_conventions.py -q
python scripts/sync_gui_help.py
python scripts/check_doc_freshness.py
python scripts/check_agent_guidance.py
```

If code comments touch modules imported by broader tests, also run:

```bash
pytest tests/unittests -q
```
