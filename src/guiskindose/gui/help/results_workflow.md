# Results

Use the Results tab after a calculation completes to review peak skin dose, procedure totals, dose map, and correction factors.

Single-exam results show:

- Peak skin dose in mGy.
- Total air kerma when available.
- Event count.
- Total DAP and fluoro time when the input source provides those fields.
- Interactive 3D dose map.
- Per-event correction-factor summary.
- A rotational-handling badge whenever rotational or moving events were
  detected (estimate-grade coverage envelope with event counts; static
  fallbacks are flagged). Per-event handling lives in the calculation
  warnings and rich-report ledger (DOCX “Rotational handling ledger”,
  XLSX “Rotational handling” sheet, dict/JSON `rotational_handling`).

### Dose by tube and the correction factors used

Results lists, for each tube of each exam, the reported kerma, the corrected kerma, the
kerma-meter correction factor that was applied, where that factor came from (`manual`,
`file`, `default`, or `mixed`), and the peak of that tube's own dose map. It appears
whenever kerma-meter correction is on, even for a single-plane exam, so you can always see
which factor was used. If a tube's events used more than one factor, the range and the
kerma-weighted value are shown, for example `1.1-1.3 (weighted 1.18)`. With correction off,
a study with more than one tube still shows the table and marks the factor `not applied`;
a single-plane study with correction off shows nothing.

The same table, with one row per exam and tube, appears in the HTML, XLSX, DOCX, and PDF
exports and in the dict/JSON output (`tube_summary`). A tube that never reaches the phantom
shows a peak of zero. Equipment names never appear in it, only the tube and the exam.

The headline peak skin dose is the peak of the combined map, which is the sum of all
tubes. Each tube's peak is the maximum of a different map, so **per-tube peaks do not
add up to the peak skin dose**.

### Reading the Peak Skin Dose band

Every peak skin dose readout — the sidebar status value, the single-exam and
aggregate Results values, and each per-exam accordion value — is coloured by
where the **modelled** peak sits, and the same bands are used everywhere:

| Band | Peak skin dose estimate |
| :--- | :--- |
| Not calculated yet | no value yet; the readout shows a dash |
| Low | below 5000 mGy |
| Elevated | 5000 mGy to just under 10000 mGy |
| High | 10000 mGy or above |

A value of exactly 5000 mGy is Elevated, and exactly 10000 mGy is High.

These bands are a **reading aid for a dose estimate, not a measurement and not
a clinical finding**. GUISkinDose models dose on a computational phantom from
an RDSR; the bands say which part of the skin-reaction discussion the estimate
falls into, and nothing more. They do not establish that a reaction will occur,
and they are not a substitute for review by a qualified medical physicist or
physician. Before any run the readouts show a dash in grey rather than a zero,
because a literal `0.00 mGy` reads as a measured result.

Colour is never the only signal. Each readout also shows a symbol for its band
(a tick for Low, a warning triangle for Elevated, an error mark for High, and
nothing when not calculated) and a tooltip naming the band and its range, so
the band is readable without relying on colour.

Multi-exam results show aggregate and per-exam values where the calculation output contains enough metadata:

- **Per-Exam Accordion**: Expand each exam to view its individual Peak Skin Dose, Air Kerma, and event count. Each exam's Peak Skin Dose is banded independently, so the accordion shows which exam in a multi-exam run drives the peak. Check **Show inline dose map** to inspect a 500px interactive 3D dose map inline within the accordion row (up to 5 inline maps simultaneously), or click **Show Dose Map** to open a modal popup dialog.
- **Visible Exams Subset Selector**: Select specific exams or use **All** / **None** to dynamically update the aggregate dose map and recompute Peak Skin Dose for only the selected subset of exams. The aggregate value bands on the **selected subset's** own maximum, not on the whole-run aggregate. Selecting no exams shows the pending band, because there is no subset peak to band.

Per-exam controls in Settings and Geometry affect the result before calculation; changing input, offsets, phantom settings, or corrections invalidates prior results.

If the dose map is not shown, confirm that the calculation completed successfully and that dose-map rendering was enabled in Settings. Warnings from calculation or import should be reviewed before exporting a report.

For reportable artifacts, use the Export tab after confirming the displayed PSD and warning state.
