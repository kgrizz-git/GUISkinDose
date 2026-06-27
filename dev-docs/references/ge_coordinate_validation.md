# GE Coordinate Validation Notes

No source data is committed here.

## Confirmed By Inspection

For head-first positioning:

| GE table travel | Positive direction |
|---|---|
| Lateral | Patient left |
| Longitudinal | Cranial |
| Height | Down |

## Current Implementation

GE lateral/longitudinal handling is implemented at normalization level:

- `normalization_settings.json` contains a `GE Healthcare` manufacturer wildcard entry.
- The entry sets `swap_lateral_longitudinal: true`.
- `rdsr_normalizer()` swaps raw `TableLongitudinalPosition_mm` and `TableLateralPosition_mm` before deriving `Tx` and `Tz`.
- The GUI `Tx`/`Tz` swap toggle is a manual expert override only, not a GE default.

## Matched Case Validation

Status: pending matched GE DICOM RDSR plus tabular export from the same case.

When available, record only de-identified aggregate values:

| Source | Table longitudinal range | Table lateral range | Table height range | Notes |
|---|---:|---:|---:|---|
| DICOM RDSR | pending | pending | pending | pending |
| Tabular export | pending | pending | pending | pending |

Validation questions:

1. What exact raw DICOM table-position values appear in a known GE motion direction?
2. Does the tabular export preserve the same RDSR-level frame or transform the coordinates?
3. Does the implemented normalizer-level GE `Tx`/`Tz` correction produce the expected Geometry preview?
4. Does applying a second GUI `Tx`/`Tz` correction produce an obviously wrong Geometry preview?
