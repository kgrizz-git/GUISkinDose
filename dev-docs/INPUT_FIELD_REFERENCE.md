# Input field reference

Standalone cheat sheet for fields expected after import. **Code remains the source of truth** —
if this page and the adapters disagree, trust the adapters and update this file.

| Deeper docs | Role |
|-------------|------|
| [INPUT_DATA_FLOW_AND_OFFSETS.md](INPUT_DATA_FLOW_AND_OFFSETS.md) | End-to-end input paths, units, offsets, DataFrame contract narrative |
| [INPUT_SCHEMA_DETECTION.md](INPUT_SCHEMA_DETECTION.md) | How tabular schemas are auto-detected |
| [VENDOR_COORDINATE_SYSTEMS.md](VENDOR_COORDINATE_SYSTEMS.md) | Vendor frames and `Tx`/`Ty`/`Tz` meaning |
| `src/guiskindose/input_adapters/*.py` | Per-schema column name patterns and required sets |
| `src/guiskindose/constants.py` (`KEY_NORMALIZATION_*`) | Canonical string keys used in code |

---

## Internal normalized event columns (required)

These **23** names are what `rdsr_normalizer()` produces and what the `normalized` tabular schema
requires (`NORMALIZED_COLUMN_NAMES` / `NORMALIZED_REQUIRED_COLUMNS` in
`input_adapters/normalized.py`). Case in the DataFrame matches the “Proper” column.
`rdsr_normalizer()` additionally emits a canonical `manufacturer` column (see below), so
raw-normalized frames carry **24** columns; the `normalized` schema accepts `manufacturer` as an
optional 24th column and materializes it as all-`None` with a count-only legacy warning when absent.

| Proper | Meaning (short) | Typical unit in contract |
|--------|-----------------|---------------------------|
| `manufacturer` | Equipment maker string, exact per-event spelling (optional on `normalized` input; always emitted by `rdsr_normalizer()`) | — |
| `model` | Equipment model string | — || `DSD` | Source → detector distance | cm |
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

### Equipment identity contract (Phase 1, custom profiles)

Coordinate identity is canonical manufacturer/model for one homogeneous exam: one exam carries
exactly one canonical pair, both axes through the existing key normalizers (no vendor aliases).
`rdsr_normalizer()` always emits `manufacturer` with the exact per-event maker spelling (`None`
when the source carries none — never the strings `"none"`/`"nan"`). The `normalized` schema
recognizes an optional `manufacturer` column (case-insensitive); a missing or entirely blank
column loads as all-`None` with one count-only warning giving the event count. Anything but one
canonical pair fails closed with a value-free error (pair count, plus the count of rows without
maker identity when nonzero — never maker/model text): distinct canonical makers, same-maker
model variation, and known+unknown mixes are all rejected, so no row silently borrows another
row's identity. Key spelling variants (case, punctuation, spacing) collapse to one pair; distinct
canonical keys (e.g. `Siemens` vs `Siemens Healthcare`) are mixed. An all-unknown frame stays
compatible (legacy model-only path). Study-id groups are checked individually, so pairs may differ
*across* exams, never *within* one. DoseTrack maps each row's Equipment Name through the
established `MODEL2MANUF` rules (blank continuations repeat the row above; leading blanks stay
missing) and is subject to the same guard. Validation and classification live in
`src/guiskindose/exam_identity.py`. No custom coordinates are applied: this is identity only.

### Custom equipment sessions (API slice)

A frozen `EquipmentProfileSession` (built with `assemble_session()` from profile files, in-memory
documents, and/or store snapshots) can be bound on settings (`PyskindoseSettings(...,
equipment_profile_session=...)` or attribute assignment; never serialized into configs). Raw
inputs (DICOM plus raw-shaped tabular) then resolve the exam identity against it during
normalization and apply all 15 effective leaves before geometry calculation; dict/JSON results
carry `equipment_profile_match` (match record, complete/partial notice, active-set hash, session
provenance). Pre-transformed inputs — the `normalized` schema, preparsed `.json` frames, or a
bare DataFrame via `analyze_data()` — refuse closed with a nonempty session, since there are no
raw fields to re-derive from. Bridging logic lives in `src/guiskindose/equipment_resolution.py`;
per-exam records travel on `InputAdapterResult`/`ExamResult` and `PySkinDoseOutput`, never on
`NormalizationSettings`. Analysis checks a typed application receipt against the active session,
canonical identity, retained event count, normalized numeric geometry, and effective settings.
Receipts are published only after normalization succeeds; each exam restores its own settings.
Well-typed records and notices must equal a fresh resolution of the bound session before output.

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

Optional collimator shutters (millimetres, exact parser spellings) enable
`field_size_mode: "ASD"` on raw tabular input. These columns are optional for
CFA and required for ASD; absent or blank edges fail closed under ASD: `LeftShutter_mm`,
`RightShutter_mm`, `TopShutter_mm`, `BottomShutter_mm` (see
`generic_rdsr.py` patterns).

Vendor adapters accept many header aliases; use `--input-preview-only` or the GUI import
preview to see the resolved map and any missing required columns for a given file.

---

## Related GUI / CLI checks

- GUI **Upload → import preview**: detected schema, column map, missing required fields.
- CLI: `--input-preview-only`, `--input-schema`, `--sheet-name`.
