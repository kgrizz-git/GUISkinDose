# Using the Geometry Tab

The Geometry tab lets you visualize beam-patient geometry and verify positioning before running dose calculations.

## Workflow for Positioning Verification

### Step 1: Select an Event
1. Enter an event number in the **Event Number** field
2. Events are numbered from 1 to the total number of irradiation events in the RDSR

### Step 2: Visualize Single Event
1. Click **Single Event** to render the beam and patient for that event
2. Observe:
   - Where the beam intersects the patient
   - The beam angle and direction
   - The patient position on the table

### Step 3: Adjust Settings (if needed)
1. If positioning looks incorrect, go to the **Settings** tab
2. Adjust phantom positioning offsets
3. Return to Geometry tab and click **Single Event** again

### Step 4: Check Multiple Events
1. Test several events across the procedure
2. Verify correct anatomy is targeted for the procedure type:
   - **Cardiac**: Beams should cluster around chest
   - **Neurovascular**: Beams should cluster around head
   - **Abdominal**: Beams should cluster around torso

## Controls

| Button | Action |
|--------|--------|
| **Single Event** | Render one specific irradiation event |
| **All Events** | Render all events (may be slow for large procedures) |
| **Clear Plot** | Reset the visualization |

## Tips

- Use **Single Event** for quick positioning checks
- Start with early events, then check middle and late events
- The patient phantom appears as a mesh; the beam is shown as a cone
- Zoom and rotate the plot to see the geometry from different angles
