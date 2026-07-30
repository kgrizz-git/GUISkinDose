# Input field reference

Standalone cheat sheet for fields expected after import. **Code remains the source of truth** —
if this page and the adapters disagree, trust the adapters and update this file.

| Deeper docs | Role |
|-------------|------|
| [INPUT_DATA_FLOW_AND_OFFSETS.md](INPUT_DATA_FLOW_AND_OFFSETS.md) | End-to-end input paths, units, offsets, DataFrame contract narrative |
| [INPUT_SCHEMA_DETECTION.md](INPUT_SCHEMA_DETECTION.md) | How tabular schemas are auto-detected |
| [VENDOR_COORDINATE_SYSTEMS.md](VENDOR_COORDINATE_SYSTEMS.md) | Vendor frames and `Tx`/`Ty`/`Tz` meaning |
| `src/mypyskindose/input_adapters/*.py` | Per-schema column name patterns and required sets |
| `src/mypyskindose/constants.py` (`KEY_NORMALIZATION_*`) | Canonical string keys used in code |

---

## Internal normalized event columns (required)

These **23** names are what `rdsr_normalizer()` produces and what the `normalized` tabular schema
requires (`NORMALIZED_COLUMN_NAMES` / `NORMALIZED_REQUIRED_COLUMNS` in
`input_adapters/normalized.py`). Case in the DataFrame matches the “Proper” column.

| Proper | Meaning (short) | Typical unit in contract |
|--------|-----------------|---------------------------|
| `model` | Equipment model string | — |
| `DSD` | Source → detector distance | cm |
| `DSI` | Source → isocenter distance | cm |
| `DID` | Isocenter → detector distance | cm |
| `DSIRP` | Source → IRP distance | cm |
| `acquisition_type` | Fluoro / acquisition label | — |
| `acquisition_plane` | Plane A / B / Single Plane | — |
| `Tx`, `Ty`, `Tz` | Table translation (normalized frame) | cm |
| `At1`, `At2`, `At3` | Table angles | deg |
| `Ap1`, `Ap2`, `Ap3` | Beam / positioner angles | deg |
| `filter_thickness_Cu` | Added Cu filtration | mm |
| `filter_thickness_Al` | Added Al filtration | mm |
| `DSL` | Detector side length (field-size path) | cm |
| `FS_lat`, `FS_long` | Field size at detector (when used) | cm |
| `kVp` | Tube voltage | kV |
| `K_IRP` | Air kerma at IRP (reported) | mGy |

### Optional identity columns (kerma-meter CF)

Not required for dose geometry, but used when kerma-meter correction is enabled:

| Proper | Source examples |
|--------|-----------------|
| `station_name` | DICOM `StationName`; tabular equipment/room labels when preserved |
| `device_serial` | DICOM `DeviceSerialNumber` |

---

## How inputs map into that contract

| Input | What the user supplies | Where names are defined |
|-------|------------------------|-------------------------|
| **DICOM RDSR** | Irradiation-event content items | `rdsr_parser.py` → `rdsr_normalizer.py` |
| **`normalized` table** | Columns already matching the table above | `input_adapters/normalized.py` |
| **`generic_rdsr_like`** | RDSR-like export headers (often with unit suffixes) | `REQUIRED_COLUMNS` + `VENDOR_COLUMN_NAMES` in `generic_rdsr.py` |
| **`radimetrics`** | Radimetrics event-table headers | `radimetrics.py` column map |
| **`dosetrack`** | DoseTrack export headers | `dosetrack.py` column map |
| **Qaelum / DoseMonitor / DoseWatch** | Stub adapters only (empty column maps); need real export fixtures | See Phase 5+ in `TABULAR_RDSR_INPUT_PLAN.md` |

### Generic RDSR-like required headers (pre-normalizer)

Minimum set the `generic_rdsr_like` adapter insists on before calling `rdsr_normalizer()`
(names as in the parsed/mapped frame — see `generic_rdsr.REQUIRED_COLUMNS`):

`Manufacturer`, `ManufacturerModelName`, `IrradiationEventType`, `AcquisitionPlane`,
`DistanceSourcetoDetector_mm`, `DistanceSourcetoIsocenter_mm`,
`TableLongitudinalPosition_mm`, `TableLateralPosition_mm`, `TableHeightPosition_mm`,
`XRayFilterMaterial`, `XRayFilterThicknessMinimum_mm`, `XRayFilterThicknessMaximum_mm`,
`PositionerPrimaryAngle_deg`, `PositionerSecondaryAngle_deg`, `KVP_kV`, `DoseRP_Gy`.

Vendor adapters accept many header aliases; use `--input-preview-only` or the GUI import
preview to see the resolved map and any missing required columns for a given file.

---

## Related GUI / CLI checks

- GUI **Upload → import preview**: detected schema, column map, missing required fields.
- CLI: `--input-preview-only`, `--input-schema`, `--sheet-name`.
