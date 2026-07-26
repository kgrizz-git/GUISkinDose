# Kerma-meter correction factors

Apply a calibration factor so dose uses laboratory-traceable air kerma instead of
the unit's uncorrected reported `K_IRP`.

**Definition:** `CF = (real measured dose) / (unit reported dose)`.

## Lookup keys

CF is resolved per **individual unit × tube** (Plane A / Plane B / Single Plane):

1. Explicit equipment label (optional override for the whole run)
2. Device serial number (DICOM)
3. Station name (DICOM)
4. Tabular unit/room column when DICOM identity is absent

## Vendor column roles

- **Radimetrics:** `Equipment` is the room/unit (CF key); `Device` is the model.
- **DoseTrack:** `Equipment Name` is often the **model**, not a unique room. Sites with
  multiple rooms of the same model should set an explicit label or supply a custom
  station column.

## Fail-soft behavior

When equipment or tube cannot be resolved, or the `(equipment, tube)` pair is missing
from the table, CF falls back to the configured default factor (usually `1.0`).

Reported `K_IRP` in the Data table stays uncorrected. Corrected kerma appears in
Results and exports as `K_IRP (corrected)` / `AirKermaCorrected`.
