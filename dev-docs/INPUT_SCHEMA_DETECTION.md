# Input schema detection

_How GUISkinDose decides which tabular adapter to use, and how DAP units are interpreted._

This document is **machine-checked**: `tests/unittests/test_input_schema_doc.py` asserts the
default mode, the ambiguity margin, the list of detectable schemas, and the marker columns cited
below all still match the code. If you add a schema, rename a fingerprint column, or change the
default, that test fails until this file is updated. See [Keeping this up to date](#keeping-this-up-to-date).

Source of truth in code:

- Detection & scoring — `src/guiskindose/input_adapters/registry.py`
  (`_detect_schema`, `_score_schema`, `_SCHEMA_KNOWN_NAMES`, `_AUTO_MIN_MARGIN`).
- Header-row location — `src/guiskindose/input_adapters/column_mapper.py` (`detect_header_row`).
- Per-schema fingerprints — each adapter's `*_COLUMN_NAMES` frozenset
  (`radimetrics.py`, `dosetrack.py`, `generic_rdsr.py`, `normalized.py`).

## Default: `auto`

Both entry points default to **auto-detection** of the tabular schema from the file's column
headers:

- **GUI** — the schema selector on the Upload tab defaults to `auto` (`gui/state.py`: `n = "auto"`).
- **CLI** — `--input-schema` defaults to `auto` (`main.py`). Pass an explicit value to override.

The library API `read_and_normalize_input(input_schema=None)` still defaults to `normalized` for
backward compatibility; only the two user-facing entry points default to `auto`. RDSR/DICOM
(`.dcm`) input never goes through schema detection — it is routed by file suffix to the RDSR parser.

## How detection works

1. **Find the header row.** `detect_header_row` scans the first **10** rows and picks the one whose
   cells match the most known column names (metadata/title rows above the table are skipped).
2. **Score each schema by recall.** For every candidate schema, `_score_schema` computes
   `matched / len(fingerprint)` — the fraction of that schema's known column names present in the
   header row. Recall (not precision) is used deliberately: a real Radimetrics export has ~87
   columns of which ~13 are recognised (poor precision, but perfect recall), so recall gives the
   correct schema ≈ 1.0 and the others ≈ 0.
3. **Pick the winner with a margin.** The highest scorer wins **only if** it beats the runner-up by
   at least `_AUTO_MIN_MARGIN` = **0.20**. If two schemas score within that margin, or nothing
   scores above zero, detection raises `SchemaDetectionError` telling the user to pass
   `--input-schema` explicitly rather than guessing.

Header matching normalises `_`, `-`, and whitespace to a single space (`_normalize_str`), so older
underscored exports compare equal to their spaced counterparts.

## Detectable schemas and their fingerprints

Auto-detection scores these four schemas (stubs for Qaelum, DoseMonitor, and DoseWatch exist but
are not yet in the scoring set — they need real export fixtures):

| Schema | What it is | Distinguishing marker columns |
|---|---|---|
| `normalized` | GUISkinDose's own canonical event table | `model`, `K_IRP`, `kVp`, `DSD`, `DSI` |
| `generic_rdsr_like` | A raw RDSR-parser-style dump (rdsr_parser column names) | `ManufacturerModelName`, `KVP_kV`, `DoseRP_Gy` |
| `radimetrics` | Bayer **Radimetrics** CSV export | `Device`, `kVp kV`, `DAP (Total) Gy-cm2` |
| `dosetrack` | Sectra **DoseTrack** CSV export | `Equipment Name`, `Tube Voltage Peak (kV)`, `Plane Code` |

The clearest human tells between the two aggregator exports:

- **Radimetrics** uses `(RF)` suffixes and bracketed units — `Primary Angle (RF) [°]`,
  `Source To Detector Distance (RF) [mm]`, `Reference Point Dose (Total) mGy`.
- **DoseTrack** uses spelled-out names with parenthesised units — `Positioner Primary Angle (deg)`,
  `Distance Source To Detector (mm)`, `Air Kerma (mGy)`.

The two fingerprints share **no** columns, so they separate cleanly.

### Adapter provenance and validation status

The `radimetrics` and `dosetrack` column maps and vendor transforms are derived from the
`dhen2714/PySkinDose` fork (`RADIMETRICS2PSD` / `DOSETRACK2PSD`, saved under
`dev-docs/references/dhen2714_*.py`), not from a vendor specification we authored. Both are validated
only against **Siemens AXIOM-Artis** exports. The DoseTrack **Philips** path (filter-string split,
lateral/longitudinal handling) is implemented but **untested against a real Philips DoseTrack export**.
Treat unvalidated manufacturer/model combinations as best-effort: the adapters warn on unknown models,
but the column mapping and unit assumptions may not hold. Verify results against known-good RDSR output.

### Overriding detection

If a file is misdetected or ambiguous, select the schema explicitly:

- CLI: `--input-schema radimetrics` (or `dosetrack`, `generic_rdsr_like`, `normalized`).
- GUI: the schema dropdown on the Upload tab.

## Unit handling

GUISkinDose has three input paths and they handle physical units differently. The goal in all three
is that no unit is silently assumed without either being read from the source or flagged.

### DICOM RDSR (reads + asserts)

`rdsr_parser.py` embeds each measured value's DICOM unit code
(`MeasurementUnitsCodeSequence`) into the column name — that is why parsed columns are named
`DoseRP_Gy`, `DistanceSourcetoDetector_mm`, `KVP_kV`. `rdsr_normalizer.py` then reads those
unit-suffixed columns with fixed factors (`DoseRP_Gy * 1000`, `_mm / 10`). Because access is by
unit-suffixed name, a report using a non-standard unit yields a differently-named column
(`DoseRP_mGy`), which would otherwise fail with an opaque `AttributeError`. `_verify_expected_units`
detects this up front and raises **`RdsrUnitError`** with a clear, unit-naming message; the GUI
(`gui/exam_loaders.py::load_rdsr`) surfaces that message instead of the generic
"Could not read this DICOM RDSR file". The RDSR path is not unit-*adaptive* — it recognises only the
standard DICOM unit — but it fails loud rather than mis-converting.

### Tabular adapters (read from header, flag when unreadable)

Every convertible tabular quantity reads its unit from the column header and converts to the internal
unit, recording a confident interpretation in the provenance `unit_conversions` (shown in the GUI
import preview and in rich exports). For quantities whose unit genuinely varies between vendors, an
unreadable token appends an import warning so no silent assumption reaches the report. Distances and
table positions (where mm is near-universal) fall back to mm silently — see the **Warns** column
below:

| Quantity | Internal unit | Recognised tokens | Assumed if unreadable | Warns |
|---|---|---|---|---|
| Reference point dose | Gy | Gy, mGy, µGy, cGy | mGy | yes |
| DAP (dose–area product) | Gy·m² | Gy·cm², mGy·cm², cGy·cm², µGy·cm², Gy·m², µGy·m² | Gy·cm² | yes |
| Collimated field area | m² | cm², m² | cm² | yes |
| Tube current | mA | µA, mA | µA | yes |
| Exposure | µAs | mAs, µAs | mAs | yes |
| Fluoro time | s | ms, s, min | ms | yes |
| Source–detector / source–isocenter distance, table positions | mm | mm, cm | mm | no (mm near-universal) |

Non-DAP quantities route through `convert_field_with_header_units` (`input_adapters/base.py`); DAP and
fluoro time keep their dedicated helpers (`convert_dap_series_to_gym2`, `_fluoro_to_seconds`). The
`radimetrics` and `dosetrack` adapters drive their conversions through these helpers, so a correctly-
or unlabelled export produces the same numbers as before, while a mislabelled/atypical export now
converts by its actual header unit instead of a hardcoded assumption. The `normalized` schema is
already in internal units and does not convert.

### DAP: a deeper caveat

**The true physical unit of DAP often depends on the acquisition equipment manufacturer more than
on the tabular exporter.** Different vendors report DAP natively in different units — e.g. Gy·cm²,
mGy·cm², cGy·cm², or µGy·m². An aggregator such as Radimetrics or DoseTrack labels a column with
*a* unit, but that label may be a relabel that does not reflect the modality's native unit, or an
unconverted passthrough. Consequences:

- A confident header match (`Gy-cm2`) is our best available signal, **not a guarantee** that the
  underlying modality reported in that unit.
- When DAP magnitudes look implausible (orders of magnitude off from the reference air kerma), the
  most likely cause is a unit mismatch introduced upstream by the manufacturer's DAP reporting, not
  by GUISkinDose.
- Fluoro time is assumed to be milliseconds (the near-universal export unit) and is likewise flagged
  if the header unit cannot be confirmed.

If you need per-manufacturer DAP unit handling, extend `_dap_to_gym2` in
`input_adapters/base.py` (unit token → factor) rather than special-casing individual exporters.

## Keeping this up to date

Docs like this drift unless a check ties them to code. Two mechanisms guard it:

1. **`tests/unittests/test_input_schema_doc.py`** (primary) — asserts against the live code
   constants that: the CLI and GUI defaults are `auto`; the ambiguity margin printed here equals
   `_AUTO_MIN_MARGIN`; every schema in `_SCHEMA_KNOWN_NAMES` is documented here; and every marker
   column cited in the table above is actually present in that schema's fingerprint frozenset. Any
   code change that contradicts this page turns the test red.
2. **`scripts/check_doc_freshness.py`** (secondary) — validates the relative links and forbids
   absolute filesystem paths in this file, as for all tracked Markdown.

When you change schema detection, update this file **and** the marker lists in the test in the same
commit — the test is the enforcement, this prose is the explanation.
