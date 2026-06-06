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

### Phase 1: Documentation

Create a user-facing documentation file that explains the positioning workflow.

**File:** `docs/source/user_guide/positioning_offsets.md`

**Content:**
- Overview of the coordinate system (X=lateral, Y=longitudinal, Z=vertical)
- Explanation of each offset parameter
- Step-by-step iterative positioning workflow
- Visual examples (if possible, screenshots from the GUI)
- Common scenarios and troubleshooting

**Dependencies:** None

### Phase 2: Help Button Infrastructure

Add a reusable help button component to the GUI that can display markdown-formatted help content.

**Location:** `src/mypyskindose/gui/components/help_button.py`

**Design:**
- Small `?` icon button next to section headers or in tab toolbars
- Opens a NiceGUI `ui.dialog` or `ui.drawer` with scrollable markdown content
- Content can be loaded from bundled markdown files or inline strings
- Consistent styling across all tabs

**API:**
```python
from .components.help_button import HelpButton

HelpButton(title="Positioning Offsets", content_path="positioning_help.md")
# or
HelpButton(title="Positioning Offsets", content="Inline markdown text...")
```

### Phase 3: Add Help to Settings Tab

**Location:** `src/mypyskindose/gui/tabs/settings_tab.py`

**Placement:**
- Help button in the "Phantom Positioning" section header
- Content focuses on offset parameters (latitude, longitude, rotation)

**Content source:** Inline or `help/positioning_offsets.md`

### Phase 4: Add Help to Geometry Tab

**Location:** `src/mypyskindose/gui/tabs/geometry_tab.py`

**Placement:**
- Help button near the event controls (top of the tab)
- Content focuses on the iterative workflow using the Geometry tab

**Content source:** Inline or `help/geometry_workflow.md`

### Phase 5: Help Content Files

Create markdown files for help content that can be loaded at runtime.

**Directory:** `src/mypyskindose/gui/help/`

**Files:**
- `positioning_offsets.md` — detailed explanation of offset parameters and their effects
- `geometry_workflow.md` — step-by-step guide for using the Geometry tab to refine positioning
- (future) `dose_calculation.md`, `export_results.md`, etc.

### Phase 6: Integration with Main Docs

Link the in-app help content with the main documentation so they stay in sync.

**Approach options:**
1. **Single source of truth:** Help content lives in `docs/source/` and is bundled into the package
2. **Duplicate content:** Separate files for docs and in-app help (risk of divergence)
3. **Generated:** Build step copies relevant docs into the GUI package

**Recommendation:** Start with option 2 for simplicity, migrate to option 1 if content grows.

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

1. **Phase 1** — Documentation (provides reference even before GUI updates)
2. **Phase 3 & 4** — Help buttons in Settings and Geometry tabs (highest user impact)
3. **Phase 2** — Help button component (enables 3 & 4)
4. **Phase 5** — External help content files (cleaner, enables reuse)
5. **Phase 6** — Doc integration (maintenance concern, lower priority)

## Open Questions

1. Should help content be inline strings or external markdown files?
   - Inline: simpler, no packaging concerns
   - External: cleaner code, easier to update, but requires `include_package_data=True`

2. Should the help dialog be a modal dialog or a side drawer?
   - Modal: focuses attention, dismissible
   - Drawer: can stay open while user interacts with controls

3. Should we add a general "Getting Started" help section accessible from all tabs?
