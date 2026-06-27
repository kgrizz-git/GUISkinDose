# GE Coordinate Validation Notes

No source data is committed here.

## Confirmed By Tabular Export Inspection

For head-first supine positioning, which is the standard convention assumed in
interventional radiology / cardiac cath geometry references:

| GE table travel | Positive direction |
|---|---|
| Lateral | Patient left |
| Longitudinal | Patient superior / cranial |
| Height | Down |

This is a consistent right-handed coordinate convention when patient left is
`+x`, down is `+y`, and superior/cranial is `+z`.

## Current Implementation

GE lateral/longitudinal handling is implemented at normalization level:

- `normalization_settings.json` contains a `GE Healthcare` manufacturer wildcard entry.
- The entry sets `swap_lateral_longitudinal: true`.
- `rdsr_normalizer()` swaps raw `TableLongitudinalPosition_mm` and `TableLateralPosition_mm` before deriving `Tx` and `Tz`.
- The GUI `Tx`/`Tz` swap toggle is a manual expert override only, not a GE default.

## Matched Case Validation

Status: deferred fixture confirmation only. The GE table-travel convention is
not an open live question; it has been confirmed from a tabular export. A
matched GE DICOM RDSR plus tabular export from the same case would still be
useful to create stable regression fixtures and verify exact raw value parity.

When available, record only de-identified aggregate values:

| Source | Table longitudinal range | Table lateral range | Table height range | Notes |
|---|---:|---:|---:|---|
| DICOM RDSR | pending | pending | pending | pending |
| Tabular export | pending | pending | pending | pending |

Validation questions:

1. What exact raw DICOM table-position values correspond to the confirmed GE tabular values?
2. Does the tabular export match the RDSR values byte-for-byte or only after trivial field-name/unit formatting?
3. Does the implemented normalizer-level GE `Tx`/`Tz` correction produce the expected Geometry preview?
4. Does applying a second GUI `Tx`/`Tz` correction produce an obviously wrong Geometry preview?
