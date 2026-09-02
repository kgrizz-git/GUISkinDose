# Data Table

Use the Data tab to inspect the irradiation event stream after loading an exam.

The normalized view is the table passed into geometry preview and dose calculation. It uses the internal coordinate and unit contract shared by DICOM RDSR and tabular inputs. The raw view shows the source parser output when available, which is useful for checking vendor fields before normalization.

In multi-exam mode, the normalized table includes an `Exam` label so rows can be traced back to the source file. Calculation still uses each exam's normalized data and per-exam settings rather than the display label.

Export buttons save or download the currently selected table view:

- CSV for quick inspection or spreadsheet import.
- XLSX with normalization metadata on a separate sheet.
- TXT for a plain-text event dump.

Review the source, schema, manufacturer, model, and table-offset metadata before relying on exported data. Coordinate labels follow the normalized display frame described in [Vendor Coordinate Systems](../../../dev-docs/VENDOR_COORDINATE_SYSTEMS.md).
