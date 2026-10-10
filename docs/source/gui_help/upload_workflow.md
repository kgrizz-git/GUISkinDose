# Upload And Import

## Privacy and temporary storage

Source filenames and file contents may contain PHI. GUISkinDose copies browser uploads into a private per-session
directory under a random name; it does not reuse the original basename. Files are removed when cleared or during an
orderly shutdown, and stale crash leftovers are removed after 24 hours. Secure erase is not guaranteed on modern
filesystems. Keep source files and temporary storage within your approved clinical-data boundary.

Use the Upload tab to load one or more DICOM RDSR files or supported tabular event-table exports.

Accepted inputs:

- DICOM RDSR files with `.dcm` extension.
- Tabular exports with `.csv`, `.tsv`, `.xlsx`, or `.xlsm` extension.
- Example RDSR files bundled with the package. Selecting an example auto-loads it.

After a file loads, the app normalizes events into the internal event table used by geometry preview, calculation, results, and export. Multi-exam uploads keep each exam separate and add an `Exam` label in the Data tab.

For tabular files, the schema selector controls how columns are interpreted. The info icon beside **Input schema** opens the full explanation: what elects Radimetrics, DoseTrack, a raw RDSR-like table, or a normalized table, what a DICOM `.dcm` RDSR does instead, and that Qaelum, DoseMonitor, and DoseWatch are not yet implemented. `auto` accepts a table only when a marker specific to that source is present and the header has at least **2** known columns for that source. One matching column is not enough. A table that only shares ordinary names such as `Device` or `kVp` is not labeled for you; choose the format and upload again. XLSX workbooks can expose a sheet picker when multiple sheets are available.

Warnings in the loaded-exam list mean the importer made an assumption or found a condition that should be reviewed before clinical use. Examples include assumed DAP units, unsupported equipment names, missing optional fields, or manual table-origin overrides.

## When a file is rejected

Some reports cannot be placed in the room. A report may leave out the source-to-isocenter distance, table positions,
beam angles, kVp, or the field size. GUISkinDose then rejects the file with one message listing every missing item
and how many events lack it. It does not fill in defaults, because a guessed geometry would change the dose estimate.
Other rejections cover a report with no X-ray irradiation events, a quantity reported twice with different values,
and a unit GUISkinDose does not convert.

Some differences are handled without rejecting the file:

- A dose reported in mGy, or a distance reported in cm or m, is converted.
- A value repeated within one event is used once when every copy agrees.
- An event with zero reference-point dose and missing geometry is dropped, because it adds no dose. A log warning
  gives the count.

A report whose manufacturer or model matches no normalization profile uses the `Default` profile. That profile cannot
know vendor coordinate conventions (for example the GE lateral/longitudinal swap), so verify the geometry preview
before relying on the result.

## Coordinate corrections

Coordinate correction toggles apply to single-exam, non-normalized tabular uploads. They are unavailable for DICOM files, the `normalized` schema, and multi-exam mode. Use them only when a site export is known to need the correction; vendor-level normalizations documented in [Vendor Coordinate Systems](../../../dev-docs/VENDOR_COORDINATE_SYSTEMS.md) are already applied by the adapter.

Technical references:

- [Input schema detection](../../../dev-docs/INPUT_SCHEMA_DETECTION.md)
- [Input data flow and offsets](../../../dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md)
