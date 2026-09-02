# Using the Geometry Tab

The Geometry tab lets you visualize beam-patient geometry and verify positioning before running dose calculations.

## Coordinate Legend

Geometry plots use the normalized display labels `X - LON / PT L-R`, `Y - VER / PT A-P`, and `Z - LAT / PT S-I`. RDSR table-position fields are named `TableLongitudinalPosition`, `TableHeightPosition`, and `TableLateralPosition`; RDSRs do not call those fields `X`, `Y`, or `Z`.

`Tx`, `Ty`, and `Tz` are the normalized table-position columns that feed the plotted axes: `Tx` appears on `X/DICOM LON/PT L-R`, `Ty` on `Y/DICOM VER/PT A-P`, and `Tz` on `Z/DICOM LAT/PT S-I`. The Geometry and **Settings → Per-exam corrections** table-origin controls always display and edit this final plotted frame.

In this normalized frame, **+Y points down** (toward the floor) and the `(0, 0, 0)` origin is the beam isocenter — it coincides with the table head-end when the table-position readout is zero. Each vendor's raw readout zero sits at a different physical point; the automatic table offsets shift it onto this origin.

`LON`, `VER`, and `LAT` are retained because they match the historical PySkinDose/DICOM table-position naming after vendor normalization. `PT L-R`, `PT A-P`, and `PT S-I` are the patient-anatomy directions of the plotted axes for the standard head-first supine convention.

Siemens and Philips use the DICOM/operator table convention for table longitudinal and lateral. GE raw data uses patient-anatomy longitudinal and lateral naming instead; GUISkinDose handles that during GE normalization by swapping the raw lateral/longitudinal assignment into the common plotted frame.

Internally, manual table-origin overrides are stored in the GUI transform source frame, before any expert-only `Tx ↔ Tz` correction toggle is applied. The app maps those stored values to the plotted frame for display and maps edits back before recalculating geometry, so the `X/DICOM LON/PT L-R` control moves plotted X even when a site-specific manual swap is enabled.

Manual table-origin override metadata is tracked with `table_origin` keys so saved settings and exports can identify the correction source.

For GE inputs, the lateral/longitudinal swap is handled during normalization. The GUI `Tx ↔ Tz` swap is a manual expert override only. GE table travel has been confirmed from tabular export inspection as positive lateral = patient left, positive longitudinal = patient superior/cranial, and positive height = down for head-first supine positioning. A matched GE DICOM RDSR plus tabular export would be useful later only to pin exact regression fixture values.

Developer-level coordinate notes live in `dev-docs/VENDOR_COORDINATE_SYSTEMS.md`. That document distinguishes DICOM table-coordinate names, vendor conventions, patient/anatomical directions, and the current PySkinDose display aliases shown in the GUI. A patient-anatomy label mode should only be added with those mappings explicitly validated.

## Workflow for Positioning Verification

### Step 1: Select an Event
1. Click **Single event** under the geometry plot to enter single-event mode. The **Event selection** stepper (the number box with chevron buttons) becomes enabled; the small caption shows your position as `Event <n> / <count>` (single-exam) or `Event <n> / <count> · Exam #<m>` (multi-exam, or `· all exams` when **Show all exams in preview** is on). The caption is **1-based** — `Event 1 / 23` is the first of 23 events.
2. Use the chevron buttons to step forward or back, or type an event number into the box (the box accepts 1-based indices — `1` is the first event — matching the caption above it).
3. In **multi-exam** mode the default slice is the **selected exam** only unless **Show all exams in preview** is enabled. Use the exam selector above the preview controls to pick which exam you are stepping through.

**Live-preview pause:** for large procedures, the plot may show a **PAUSED** badge while you drag the procedure-mode slider — this is the performance guard described in [Trace-count guard](#). It fires above 30 events in **any** `Full procedure` path (single-exam or multi-exam, composite or not); you can still click **Full procedure** once and use the Plotly slider to step through the cached figure.

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

Live preview may **pause** when a full-procedure view exceeds 30 events (performance guard).

## Controls

| Button | Action |
|--------|--------|
| **Setup view** | Phantom and table in starting orientation |
| **Single event** | Render one specific irradiation event |
| **Full procedure** | Render all events in the current preview slice (may pause when large) |
| **Event selection stepper** | Jump to a specific event within the current preview slice (prev / next or typed number). Disabled unless **Single event** mode is active. The caption is 1-based; the typed number is 0-based. |

## Tips

- Use **Single event** for quick positioning checks
- Start with early events, then check middle and late events
- The patient phantom appears as a mesh; the beam is shown as a cone
- Zoom and rotate the plot to see the geometry from different angles
