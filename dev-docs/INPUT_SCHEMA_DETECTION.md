# Input schema detection

_How MyPySkinDose decides which tabular adapter to use, and how DAP units are interpreted._

This document is **machine-checked**: `tests/unittests/test_input_schema_doc.py` asserts the
default mode, the ambiguity margin, the list of detectable schemas, and the marker columns cited
below all still match the code. If you add a schema, rename a fingerprint column, or change the
default, that test fails until this file is updated. See [Keeping this up to date](#keeping-this-up-to-date).

Source of truth in code:

- Detection & scoring — `src/mypyskindose/input_adapters/registry.py`
  (`_detect_schema`, `_score_schema`, `_SCHEMA_KNOWN_NAMES`, `_AUTO_MIN_MARGIN`).
- Header-row location — `src/mypyskindose/input_adapters/column_mapper.py` (`detect_header_row`).
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
| `normalized` | MyPySkinDose's own canonical event table | `model`, `K_IRP`, `kVp`, `DSD`, `DSI` |
| `generic_rdsr_like` | A raw RDSR-parser-style dump (rdsr_parser column names) | `ManufacturerModelName`, `KVP_kV`, `DoseRP_Gy` |
| `radimetrics` | Bayer **Radimetrics** CSV export | `Device`, `kVp kV`, `DAP (Total) Gy-cm2` |
| `dosetrack` | Sectra **DoseTrack** CSV export | `Equipment Name`, `Tube Voltage Peak (kV)`, `Plane Code` |

The clearest human tells between the two aggregator exports:

- **Radimetrics** uses `(RF)` suffixes and bracketed units — `Primary Angle (RF) [°]`,
  `Source To Detector Distance (RF) [mm]`, `Reference Point Dose (Total) mGy`.
- **DoseTrack** uses spelled-out names with parenthesised units — `Positioner Primary Angle (deg)`,
  `Distance Source To Detector (mm)`, `Air Kerma (mGy)`.

The two fingerprints share **no** columns, so they separate cleanly.

### Overriding detection

If a file is misdetected or ambiguous, select the schema explicitly:

- CLI: `--input-schema radimetrics` (or `dosetrack`, `generic_rdsr_like`, `normalized`).
- GUI: the schema dropdown on the Upload tab.

## A caveat on DAP units

MyPySkinDose reads the **DAP (dose–area product) unit from the column header** (e.g. `DAP (Total)
Gy-cm2`), converts to internal `Gy·m²`, and records the interpretation in the provenance
unit-conversions. If the header carries no recognisable unit token, the value is **assumed to be
Gy·cm² and flagged with an import warning** (surfaced in the rich report's alert block and the GUI)
so the operator can verify it before clinical use. This is **uniform across all tabular adapters** —
Radimetrics, DoseTrack, and the generic capture path all route DAP through the same
`convert_dap_series_to_gym2` helper (`input_adapters/base.py`); none silently assumes a unit without
either reading it from the header or flagging the assumption.

**The true physical unit of DAP often depends on the acquisition equipment manufacturer more than
on the tabular exporter.** Different vendors report DAP natively in different units — e.g. Gy·cm²,
mGy·cm², cGy·cm², or µGy·m². An aggregator such as Radimetrics or DoseTrack labels a column with
*a* unit, but that label may be a relabel that does not reflect the modality's native unit, or an
unconverted passthrough. Consequences:

- A confident header match (`Gy-cm2`) is our best available signal, **not a guarantee** that the
  underlying modality reported in that unit.
- When DAP magnitudes look implausible (orders of magnitude off from the reference air kerma), the
  most likely cause is a unit mismatch introduced upstream by the manufacturer's DAP reporting, not
  by MyPySkinDose.
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
