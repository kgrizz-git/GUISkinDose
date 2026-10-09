# Schema detection confirmation

Short follow-on to the marker and two-column auto-detect rule. Two changes. Do not compare hit counts instead of recall.

## Out of scope

- Replacing the 0.20 recall margin with a hit-count comparison. No shipped file is in that gap, and the current failure is already an ambiguity error that asks the user to choose.
- A warning on every confident Radimetrics or DoseTrack load.
- Re-reading every loaded file when **Input schema** changes. That control re-reads only the current file (`state.file_path`). The new copy must say so.

## 1. Shared identity columns must not elect a raw RDSR-like table

`stationname` and `deviceserialnumber` are in both the normalized and raw RDSR-like fingerprints. Normalized already excludes them. Raw RDSR-like does not, so `StationName, Manufacturer, kVp` is called `generic_rdsr_like` and then fails on missing dose and geometry columns.

Add both names to `_TRIGGER_EXCLUSIONS["generic_rdsr_like"]`. They still count toward recall. A real parser dump still elects through names such as `DoseRP_Gy` and `ManufacturerModelName`.

Tests:

- `StationName, Manufacturer, kVp` and `DeviceSerialNumber, Manufacturer, kVp` raise `SchemaDetectionError` (no distinctive marker).
- `DoseRP_Gy` plus `ManufacturerModelName` still elects `generic_rdsr_like`.
- `StationName` plus `DoseRP_Gy` still elects, because `DoseRP_Gy` is a marker and the header has two known columns.

Rewrite the sentences at `docs/source/gui_help/input_formats.md` and `dev-docs/INPUT_SCHEMA_DETECTION.md` that name `StationName` and `DeviceSerialNumber` as electors. Add a doc test asserting every name in `_TRIGGER_EXCLUSIONS["generic_rdsr_like"]` appears in that row's score-only cell. Then run `scripts/sync_gui_help.py`. Changelog Unreleased and `MAINTENANCE_LOG.md`. Package version stays `1.0.0`.

## 2. Say what the badge means, and warn only on a two-column match

The import-preview badge is the first place a detected schema is shown. The **Input schema** menu stays on **Auto-detect schema**, so the badge is not itself a control.

Record two fields on `InputProvenance` when `read_and_normalize_input` runs. Both fields default to `None`. `detection_mode` is `"auto"` only when `input_schema == "auto"`. A `None` schema, which defaults to normalized, counts as `"explicit"`.

- `detection_mode`: `"auto"` or `"explicit"`.
- `matched_column_count`: the winning schema's known-column hit count when mode is `"auto"`; `None` when the caller named the schema.

Do not put header text in these fields or in warnings. Keep `_detect_schema` returning a name. Add a sibling that returns `(name, hits)`. Fold `sheet_name` and the new fields into one `_stamp_provenance(result, **fields)` helper.

On the import preview, next to the badge, the lines come from a helper that takes `(provenance, input_source_type)` and returns no lines unless the source is tabular. A DICOM load leaves the previous tabular `import_provenance` in place, so a provenance-only check would show a false sentence. The helper lives in a NiceGUI-free module that owns the `copy_text` keys (`scripts/check_ui_copy.py` requires the owner file to call `copy_text("key")` literally, and `tests/unittests` cannot import `import_preview.py`).

When the helper does return lines:

- Always: “Read from this file's column headers. Change Input schema above to re-read this file.”
- When `matched_column_count` equals `_AUTO_MIN_HITS` (2): also “Only two recognized columns matched. Confirm the format above before calculating.”

Put the sentences in `dev-docs/ui_copy.json` and sync with `scripts/sync_ui_copy.py`. One sentence in `docs/source/gui_help/input_formats.md` should say the preview tells you the format was read from the headers and that a two-column match asks you to confirm.

Cover the copy with a unit test of the helper that chooses the lines. Do not assert on a live NiceGUI widget.

## Checks

`pytest tests/unittests/test_input_adapters.py tests/unittests/test_input_schema_doc.py`, ruff, and `scripts/check_complexity.py`. Functions stay at complexity 10 or under. Also `scripts/check_ui_copy.py`, `scripts/sync_ui_copy.py --check`, and `scripts/sync_gui_help.py --check`.
