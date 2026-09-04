# Results

Use the Results tab after a calculation completes to review peak skin dose, procedure totals, dose map, and correction factors.

Single-exam results show:

- Peak skin dose in mGy.
- Total air kerma when available.
- Event count.
- Total DAP and fluoro time when the input source provides those fields.
- Interactive 3D dose map.
- Per-event correction-factor summary.

Multi-exam results show aggregate and per-exam values where the calculation output contains enough metadata:

- **Per-Exam Accordion**: Expand each exam to view its individual Peak Skin Dose, Air Kerma, and event count. Check **Show inline dose map** to inspect a 500px interactive 3D dose map inline within the accordion row (up to 5 inline maps simultaneously), or click **Show Dose Map** to open a full-screen popup dialog.
- **Visible Exams Subset Selector**: Select specific exams or use **All** / **None** to dynamically update the aggregate dose map and recompute Peak Skin Dose for only the selected subset of exams.

Per-exam controls in Settings and Geometry affect the result before calculation; changing input, offsets, phantom settings, or physics settings invalidates prior results.

If the dose map is not shown, confirm that the calculation completed successfully and that dose-map rendering was enabled in Settings. Warnings from calculation or import should be reviewed before exporting a report.

For reportable artifacts, use the Export tab after confirming the displayed PSD and warning state.
