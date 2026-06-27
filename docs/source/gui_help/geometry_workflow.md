# Using the Geometry Tab

The Geometry tab lets you visualize beam-patient geometry and verify positioning before running dose calculations.

## Coordinate Legend

Geometry plots currently use historical PySkinDose axis aliases: `X - LON`, `Y - VER`, and `Z - LAT`. These labels identify the plotted calculation frame, not every physical or DICOM naming convention. Vendor normalization and import correction toggles are applied before the Geometry preview is drawn.

`Tx`, `Ty`, and `Tz` are the normalized table-position columns that feed the plotted axes: `Tx` appears on `X/LON`, `Ty` on `Y/VER`, and `Tz` on `Z/LAT`. The Geometry and **Settings → Per-exam corrections** table-origin controls always display and edit this final plotted frame.

Internally, manual table-origin overrides are stored in the GUI transform source frame, before any expert-only `Tx ↔ Tz` correction toggle is applied. The app maps those stored values to the plotted frame for display and maps edits back before recalculating geometry, so the `X/LON` control moves plotted X even when a site-specific manual swap is enabled.

For GE inputs, the lateral/longitudinal swap is handled during normalization. The GUI `Tx ↔ Tz` swap is a manual expert override only. GE table travel has been confirmed from tabular export inspection as positive lateral = patient left, positive longitudinal = patient superior/cranial, and positive height = down for head-first supine positioning. A matched GE DICOM RDSR plus tabular export would be useful later only to pin exact regression fixture values.

Developer-level coordinate notes live in `dev-docs/VENDOR_COORDINATE_SYSTEMS.md`. That document distinguishes the physical/anatomical coordinate discussion from the current PySkinDose display aliases shown in the GUI.

## Workflow for Positioning Verification

### Step 1: Select an Event
1. Enter an event number in the **Event selection** field (0-based index into the current preview slice)
2. For a single exam, this indexes all events in the file. In **multi-exam** mode, the default slice is the **selected exam** only unless **Show all exams in preview** is enabled.

### Step 2: Visualize Single Event
1. Click **Single event** to render the beam and patient for that event
2. Observe:
   - Where the beam intersects the patient
   - The beam angle and direction
   - The patient position on the table

### Step 3: Adjust Settings (if needed)
1. If positioning looks incorrect, adjust patient offsets:
   - **Single exam:** Geometry tab sliders or **Settings → Phantom Settings**
   - **Multiple exams:** pick **Selected exam** on the Geometry tab (or click an exam card on the Upload tab), then use Geometry sliders or **Settings → Per-exam corrections**
2. Return to Geometry and click **Single event** again (sliders debounce ~250 ms)

### Step 4: Check Multiple Events
1. Test several events across the procedure
2. Verify correct anatomy is targeted for the procedure type:
   - **Cardiac**: Beams should cluster around chest
   - **Neurovascular**: Beams should cluster around head
   - **Abdominal**: Beams should cluster around torso

## Multi-exam mode

| Control | Behavior |
|---------|----------|
| **Selected exam** | Patient-offset and table-origin sliders edit this exam's `meta` entry |
| **Show all exams in preview** | Preview draws all exams' events; phantom stays at the selected exam's offset |
| **Table-origin scrub** | While adjusting table origin, preview temporarily shows all exams so you can see relative table motion |

Live preview may **pause** when a composite full-procedure view exceeds 30 events (performance guard).

## Controls

| Button | Action |
|--------|--------|
| **Setup view** | Phantom and table in starting orientation |
| **Single event** | Render one specific irradiation event |
| **Full procedure** | Render all events in the current preview slice (may pause when large in multi-exam composite mode) |

## Tips

- Use **Single event** for quick positioning checks
- Start with early events, then check middle and late events
- The patient phantom appears as a mesh; the beam is shown as a cone
- Zoom and rotate the plot to see the geometry from different angles
