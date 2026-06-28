# Running Dose Calculations

The Calculate tab uses the normalized event table and the current per-exam positioning settings. If you changed patient offsets, table-origin overrides, or manual coordinate corrections, run the calculation again before trusting the dose map.

## Coordinate Labels

RDSR table-position fields are named `TableLongitudinalPosition`, `TableHeightPosition`, and `TableLateralPosition`; RDSRs do not name these fields `X`, `Y`, or `Z`. MyPySkinDose maps those vendor-specific table-position fields into a common plotted/calculation frame:

| Plot label | Calculation column | Patient direction for head-first supine |
|---|---|---|
| `X - LON / PT L-R` | `Tx` | Patient left-right |
| `Y - VER / PT A-P` | `Ty` | Patient anterior-posterior / table height |
| `Z - LAT / PT S-I` | `Tz` | Patient superior-inferior |

The `LON`, `VER`, and `LAT` text in the GUI is retained because it matches the historical PySkinDose/DICOM table-position naming after vendor normalization. The `PT` text is the patient-anatomy meaning of the plotted axis for a head-first supine patient.

Siemens and Philips use the DICOM/operator table convention for longitudinal and lateral table positions. GE uses patient-anatomy longitudinal and lateral naming in the raw data; MyPySkinDose handles that with the GE normalizer-level lateral/longitudinal swap before the Geometry and Calculate tabs use the data.

The manual `Tx ↔ Tz` import toggle is an expert correction for non-DICOM tabular inputs. It is not normally needed for GE DICOM RDSR data because GE handling is already applied during normalization.

## Before Running

1. Use the Geometry tab to check a few representative events.
2. Confirm any warning banners about fallback normalization, manual swaps, or axis flips.
3. In multi-exam mode, make sure the selected exam's offsets are intentional; Calculate uses every exam's own stored offsets and table-origin settings.
