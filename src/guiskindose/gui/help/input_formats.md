# How input formats are recognized

GUISkinDose reads two kinds of files. A DICOM radiation dose structured report (RDSR) is recognized by the `.dcm` extension. A table (`.csv`, `.tsv`, `.xlsx`, `.xlsm`) is recognized by its column headers. Auto-detect commits only when the header has at least **2** known columns for one source and one of them is a marker for that source.

After a table loads, the blue badge on the import preview, the name on the loaded-file card, and the Data tab line `Schema:` are the format that was used. The **Input schema** menu can stay on **Auto-detect schema** while that badge shows the result. The import preview also tells you that auto-detected format was read from this file's column headers and that changing **Input schema** re-reads the file; when only two columns matched, it asks you to confirm the format before calculating. Choosing a format in the menu forces that reader. Choosing the wrong one applies that reader's assumptions.

If auto-detect cannot see a marker, or it sees only one known column, the load stops and asks you to pick a format and upload again. Shared names such as `Device`, `kVp`, table position, or a bare reference-point dose are not enough.

## DICOM RDSR

A `.dcm` RDSR never goes through the table scorer. The parser reads each measurement's unit from the DICOM file. A dose reported in mGy, or a distance reported in cm or m, is converted. A missing source-to-isocenter distance, table position, beam angle, kVp, reference-point dose, or field size rejects the file. Those values are not guessed, because a guessed geometry would change the dose estimate.

The Upload tab's bundled examples are DICOM RDSR files plus two Radimetrics CSV exports.

## Radimetrics

Auto-detect calls a table Radimetrics when the header has at least **2** known columns and one cell is a known Radimetrics column containing `(rf)`, or a cell contains `dap (total)` or `reference point dose (total)`. Both exports shipped with GUISkinDose use `(rf)` on a known column, for example `Primary Angle (RF)` and `Primary Angle (RF) [°]`. `(rf)` on any other wording, such as `Modality (RF)`, does not count. One known column is not enough.

`Device`, `Equipment`, `kVp kV`, unsuffixed angles, distances, table positions, and a bare `Reference Point Dose` help recognize a real Radimetrics file and cannot elect it alone.

When that reader runs:

- `Device` is the model. `Equipment` is the room, and that room is the kerma-meter correction key.
- Units are read from the header. An unreadable dose is taken as mGy, area as cm², and distances as mm.
- A row that has both per-plane reference-point dose columns, with dose on plane B, is split into a Plane A event and a Plane B event.
- A missing event type becomes `Fluoroscopy`. With no biplane evidence, a missing plane becomes `Single Plane`.
- The model is checked against the Siemens Artis names this map was built from (`AXIOM-Artis`, `Artis`, `Artis Q`, `Artis Zee`). Any other model warns. Check the result against a known-good RDSR.

## DoseTrack

Auto-detect calls a table DoseTrack when the header has at least **2** known columns and one of them is exactly `Equipment Name`, `Plane Code`, or `Tube Voltage Peak (kV)`. `Air Kerma (mGy)`, positioner angles, distances, table positions, and `Filter Material` cannot elect it. Those labels also appear on ordinary DICOM-style tables. One of the electing columns on its own asks you to pick a format.

When that reader runs:

- `Equipment Name` is the model. Manufacturer comes from a short list: `AXIOM-Artis` is Siemens, and `Azurion` or `Allura Clarity` is Philips. Any other name warns, and that name is used as the manufacturer. The same column is the kerma-meter key. It is often the model, not a unique room.
- Blank cells are forward-filled from the row above. DoseTrack repeats the equipment name only on the first row of a group.
- `Plane Code` values `113620`, `113621`, and `113622` mean Plane A, Plane B, and Single Plane. Site codes such as `1` and `2` are not guessed. Set `dosetrack_plane_code_map` or pass `--plane-code-map`. Without a map, the load fails before dose calculation.
- A Philips filter cell is split on `;` into aluminium and copper (`Al;Cu`). Any other manufacturer copies the single thickness into both the minimum and the maximum, which is the Siemens pattern. The Philips path has not been checked against a real Philips DoseTrack export.
- Collimated field area is derived from DAP, reference-point dose, and the two distances when the export does not already provide it.
- An unreadable air-kerma unit is taken as mGy. An unreadable tube current is taken as µA.
- A missing event type becomes `Fluoroscopy`. A missing filter material becomes `Cu`.

## Raw RDSR-like table

This is a spreadsheet whose columns are already the names produced by the RDSR parser, such as `ManufacturerModelName` or `DoseRP_Gy`. It is not a DICOM file. Units are in those column names. Auto-detect needs at least **2** known columns, including one of those concatenated parser names. `StationName` and `DeviceSerialNumber` support the score only and do not elect this format by themselves; the same words written with a space as one header cell do not match. `Manufacturer` or `KVP_kV` alone does not elect this format, because Radimetrics uses those words too (`kVp kV`).

## Normalized table

This is GUISkinDose's own event table. Auto-detect needs at least **2** known columns, including an internal column such as `K_IRP`, `DSD`, `DSI`, `Tx`, or `acquisition_type_code`. `model`, `kVp`, and `acquisition_type` do not elect it. Values are already in internal units, and manufacturer coordinate corrections are not applied again.

## Qaelum, DoseMonitor, and DoseWatch

These three are not in the Upload menu and `--input-schema` does not accept them. They are not auto-detected. A Python caller can pass the name. The adapter is not yet implemented: no real export is available to build a column map. That call reports the gap, rather than guessing another format.

## Maintainer reference

Scoring, the unit table, and the DAP caveat are in `dev-docs/INPUT_SCHEMA_DETECTION.md`.
