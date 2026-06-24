# Positioning Help Implementation Plan

## Overview

Users often need to determine appropriate phantom positioning offsets (latitude, longitude, rotation) when they are not known from the RDSR data or when the default values don't produce correct beam-patient geometry. This plan adds documentation and in-app help to guide users through an iterative positioning workflow.

## User Workflow to Document

1. **Try various event numbers** in the Geometry tab and click "Single Event" to visualize where that event falls on the patient with current settings.

2. **If position does not look correct**, go back to Settings tab and edit offset values:
   - Negative "latitude" typically moves the beam superior on the patient (or equivalently, moves the patient/table inferior/foot-ward)
   - Positive "latitude" moves the beam inferior on the patient
   - Longitude offsets shift the patient along the table (longitudinal axis)
   - Rotation adjusts patient orientation

3. **Return to Geometry tab** and click "Single Event" again to see the updated positioning.

4. **Check several events** across the procedure to ensure positioning works for all irradiation events.

5. **Repeat** as necessary until the beam-patient geometry looks correct across representative events.

## Implementation Plan

### Phase 1: Documentation ✅ COMPLETE

Create a user-facing documentation file that explains the positioning workflow.

**File:** `docs/source/user_guide/positioning_offsets.md` ✅ Created

**Content:**
- Overview of the coordinate system (X=lateral, Y=longitudinal, Z=vertical)
- Explanation of each offset parameter
- Step-by-step iterative positioning workflow
- Visual examples (if possible, screenshots from the GUI)
- Common scenarios and troubleshooting

**Dependencies:** None

### Phase 2: Help Button Infrastructure ✅ COMPLETE

Add a reusable help button component to the GUI that can display markdown-formatted help content.

**Location:** `src/mypyskindose/gui/components/help_button.py` ✅ Created

**Design:**
- Small `?` icon button next to section headers or in tab toolbars
- Opens a NiceGUI `ui.dialog` with scrollable markdown content
- Content can be loaded from bundled markdown files or inline strings
- Consistent styling across all tabs

**API:**
```python
from .components.help_button import HelpButton

HelpButton(title="Positioning Offsets", content_path="positioning_help.md")
# or
HelpButton(title="Positioning Offsets", content="Inline markdown text...")
```

### Phase 3: Add Help to Settings Tab ✅ COMPLETE

**Location:** `src/mypyskindose/gui/app.py` (Settings tab panel)

**Placement:**
- Help button in the "Phantom Settings" section header ✅ Added
- Content focuses on offset parameters (latitude, longitude, rotation)

**Content source:** `help/positioning_offsets.md` ✅ Created

### Phase 4: Add Help to Geometry Tab ✅ COMPLETE

**Location:** `src/mypyskindose/gui/app.py` (Geometry tab panel)

**Placement:**
- Help button near the tab header ✅ Added
- Content focuses on the iterative workflow using the Geometry tab

**Content source:** `help/geometry_workflow.md` ✅ Created

### Phase 5: Help Content Files ✅ COMPLETE

Create markdown files for help content that can be loaded at runtime.

**Directory:** `src/mypyskindose/gui/help/` ✅ Created

**Files:**
- `positioning_offsets.md` ✅ Created — detailed explanation of offset parameters and their effects
- `geometry_workflow.md` ✅ Created — step-by-step guide for using the Geometry tab to refine positioning
- (future) `dose_calculation.md`, `export_results.md`, etc.

### Phase 6: Integration with Main Docs

Link the in-app help content with the main documentation so they stay in sync.

**Approach options:**
1. **Single source of truth:** Help content lives in `docs/source/` and is bundled into the package
2. **Duplicate content:** Separate files for docs and in-app help (risk of divergence)
3. **Generated:** Build step copies relevant docs into the GUI package

**Recommendation:** We have selected option 1.

**Detailed Plan:** See [PHASE_6_DOC_INTEGRATION_PLAN.md](PHASE_6_DOC_INTEGRATION_PLAN.md) for the detailed implementation plan.

**Status:** Planned
## File Structure After Implementation

```
src/mypyskindose/gui/
├── components/
│   └── help_button.py          # Reusable help dialog component
├── help/
│   ├── positioning_offsets.md  # Offset parameter explanations
│   └── geometry_workflow.md    # Iterative positioning workflow
├── tabs/
│   ├── settings_tab.py         # Updated with help button
│   └── geometry_tab.py         # Updated with help button
└── ...

docs/source/user_guide/
└── positioning_offsets.md      # Full user guide (optional, links to in-app help)
```

## Priority

1. ~~**Phase 1** — Documentation (provides reference even before GUI updates)~~ ✅
2. ~~**Phase 3 & 4** — Help buttons in Settings and Geometry tabs (highest user impact)~~ ✅
3. ~~**Phase 2** — Help button component (enables 3 & 4)~~ ✅
4. ~~**Phase 5** — External help content files (cleaner, enables reuse)~~ ✅
5. **Phase 6** — Doc integration (maintenance concern, lower priority)

## Open Questions

1. ~~Should help content be inline strings or external markdown files?~~
   - **Decision:** External markdown files (cleaner, easier to update)

2. ~~Should the help dialog be a modal dialog or a side drawer?~~
   - **Decision:** Modal dialog (focuses attention, dismissible)

3. Should we add a general "Getting Started" help section accessible from all tabs?
   - **Status:** Future consideration
