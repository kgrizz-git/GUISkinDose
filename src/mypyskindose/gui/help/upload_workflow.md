# Upload And Import

Use the Upload tab to load one or more DICOM RDSR files or supported tabular event-table exports.

Accepted inputs:

- DICOM RDSR files with `.dcm` extension.
- Tabular exports with `.csv`, `.tsv`, `.xlsx`, or `.xlsm` extension.
- Example RDSR files bundled with the package.

After a file loads, the app normalizes events into the internal event table used by geometry preview, calculation, results, and export. Multi-exam uploads keep each exam separate and add an `Exam` label in the Data tab.

For tabular files, the schema selector controls how columns are interpreted. `auto` scores the available schemas from the header row; explicit schemas are useful when an export has ambiguous or site-customized column names. XLSX workbooks can expose a sheet picker when multiple sheets are available.

Warnings in the loaded-exam list mean the importer made an assumption or found a condition that should be reviewed before clinical use. Examples include assumed DAP units, unsupported equipment names, missing optional fields, or manual table-origin overrides.

Coordinate correction toggles apply to the loaded tabular event data before calculation. Use them only when a site export is known to need the correction; vendor-level normalizations documented in [Vendor Coordinate Systems](../../../dev-docs/VENDOR_COORDINATE_SYSTEMS.md) are already applied by the adapter.

Technical references:

- [Input schema detection](../../../dev-docs/INPUT_SCHEMA_DETECTION.md)
- [Input data flow and offsets](../../../dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md)
