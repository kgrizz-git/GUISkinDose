# Input schema detection

_How GUISkinDose decides which tabular adapter to use, and how DAP units are interpreted._

This document is **machine-checked**: `tests/unittests/test_input_schema_doc.py` asserts the
default mode, the ambiguity margin, the list of detectable schemas, and the marker columns cited
below all still match the code. If you add a schema, rename a fingerprint column, or change the
default, that test fails until this file is updated. See [Keeping this up to date](#keeping-this-up-to-date).

Source of truth in code:

- Detection & scoring — `src/guiskindose/input_adapters/registry.py`
  (`_detect_schema`, `_score_schema`, `_SCHEMA_KNOWN_NAMES`, `_SCHEMA_TRIGGERS`,
  `_RADIMETRICS_TRIGGER_SUBSTRINGS`, `_AUTO_MIN_MARGIN`, `_AUTO_MIN_HITS`).
- Header-row location — `src/guiskindose/input_adapters/column_mapper.py` (`detect_header_row`).
- Per-schema fingerprints — each adapter's `*_COLUMN_NAMES` frozenset
  (`radimetrics.py`, `dosetrack.py`, `generic_rdsr.py`, `normalized.py`).

## Default: `auto`

Both entry points default to **auto-detection** of the tabular schema from the file's column
headers:

- **GUI** — the schema selector on the Upload tab defaults to `auto` (`gui/state.py`: `input_schema: str = "auto"`).
- **CLI** — `--input-schema` defaults to `auto` (`cli_args.py`). Pass an explicit value to override.

The library API `read_and_normalize_input(input_schema=None)` still defaults to `normalized` for
backward compatibility; only the two user-facing entry points default to `auto`. RDSR/DICOM
(`.dcm`) input never goes through schema detection — it is routed by file suffix to the RDSR parser.

## How detection works

1. **Find the header row.** `detect_header_row` scans the first **10** rows and picks the one whose
   cells match the most known column names (metadata/title rows above the table are skipped).
2. **Score each schema by recall.** For every candidate schema, `_score_schema` computes
   `matched / len(fingerprint)` — the fraction of that schema's known column names present in the
   header row. Recall (not precision) is used so extra unrelated columns do not pull the score
   down. The Radimetrics fingerprint has 24 names. The shipped newer example matches 13 of them
   and the older example matches 12 of them. `Manufacturer` and `kVp kV` on those files also
   match the raw RDSR-like fingerprint, and that overlap does not elect it. A header that
   contains every fingerprint name still scores 1.0 however many extra columns it carries.
3. **Require a distinctive marker.** Recall ranks schemas, but it does not elect one. A schema is
   eligible only when the header contains a marker that is specific to that source (below).
   Ordinary shared names — `Device`, `Manufacturer`, `kVp`, `Reference Point Dose`, table
   positions — still raise the score of a real export, and they cannot win on their own. This
   is deliberate: the Radimetrics and DoseTrack corpora in this repo are a handful of exports,
   and the DICOM RDSRs we have are the upstream PySkinDose examples plus the OpenREM test set.
   Those DICOM files never enter this scorer. Guessing a vendor from a few familiar column
   names would mis-label the next unseen table.
4. **Require at least 2 known columns, then apply the margin.** A schema is eligible only when
   step 3's marker is present **and** the header contains at least **2** known columns for that
   schema. When **exactly one** schema is eligible, that schema wins even if its recall is small
   (two columns out of a long fingerprint is enough). One known column, even a distinctive one,
   raises `SchemaDetectionError`. The CLI tells the user to pass `--input-schema`. The GUI asks
   them to choose Radimetrics, DoseTrack, Raw RDSR-like, or Normalized and upload again. When
   **two or more** schemas are eligible, the highest scorer wins **only if** it beats the
   runner-up by at least `_AUTO_MIN_MARGIN` = **0.20**; otherwise detection raises
   `SchemaDetectionError`. If **nothing** is eligible — no overlap, or only shared names — the
   error says the header had no distinctive marker.

Header matching normalises `_`, `-`, and whitespace to a single space (`_normalize_str`), so older
underscored exports compare equal to their spaced counterparts.

## Detectable schemas and their fingerprints

Auto-detection scores these four schemas (stubs for Qaelum, DoseMonitor, and DoseWatch exist but
are not yet in the scoring set — they need real export fixtures):

| Schema | What it is | Example columns the fingerprint recognizes |
|---|---|---|
| `normalized` | GUISkinDose's own canonical event table | `model`, `K_IRP`, `kVp`, `DSD`, `DSI` |
| `generic_rdsr_like` | A raw RDSR-parser-style dump (rdsr_parser column names) | `ManufacturerModelName`, `KVP_kV`, `DoseRP_Gy` |
| `radimetrics` | Bayer **Radimetrics** CSV export | `Device`, `kVp kV`, `DAP (Total) Gy-cm2` |
| `dosetrack` | Sectra **DoseTrack** CSV export | `Equipment Name`, `Tube Voltage Peak (kV)`, `Plane Code` |

These example columns are names the fingerprint can match. They do not elect a schema by themselves. Election is the distinctive-marker rule below. In particular, `Device` and `kVp kV` appear in the Radimetrics fingerprint and cannot elect Radimetrics on their own.

**DoseTrack Plane Code:** integer codes that match DICOM CID 10003 (`113620` /
`113621` / `113622`) map automatically to Plane A / Plane B / Single Plane. Typical
DoseTrack site codes such as `1`/`2` are **not** inferred from sort order anymore
(that mislabeled one-tube subsets of biplane exports). Provide an explicit map:

- Settings JSON: `"dosetrack_plane_code_map": {"1": "Single Plane"}` or
  `{"1": "Plane A", "2": "Plane B"}`
- CLI: `--plane-code-map '1:Single Plane'` or `'1:Plane A,2:Plane B'`

Without a map, non-CID integer codes raise `ValueError` before dose calculation.

The clearest human tells between the two aggregator exports:

- **Radimetrics** uses `(RF)` suffixes and bracketed units — `Primary Angle (RF) [°]`,
  `Source To Detector Distance (RF) [mm]`, `Reference Point Dose (Total) mGy`.
- **DoseTrack** uses spelled-out names with parenthesised units — `Positioner Primary Angle (deg)`,
  `Distance Source To Detector (mm)`, `Air Kerma (mGy)`.

The two fingerprints share **no** columns, so they separate cleanly once a distinctive marker
is present. Shared *words* are a different matter: the older Radimetrics export spells several
fields in plain English (`Reference Point Dose`, `Table Longitudinal Position`), and those
same words appear on other dose tables.

### Distinctive markers

Eligibility uses the header cells after the same `_normalize_str` collapse as scoring.

| Schema | May elect the schema | Supports the score only |
|---|---|---|
| `radimetrics` | A cell whose text through `(rf)` is the start of a known Radimetrics column (older `Primary_Angle_(RF)`, newer `Primary Angle (RF) [°]`, including a later unit the fingerprint does not list). `(rf)` on any other wording, such as `Modality (RF)`, does not count. A cell containing `dap (total)` or `reference point dose (total)` also counts. | `Device`, `Equipment`, `kVp kV`, unsuffixed angles, distances, table positions, and a bare `Reference Point Dose` |
| `dosetrack` | Exact fingerprint names `Equipment Name`, `Plane Code`, or `Tube Voltage Peak (kV)` | `Air Kerma (mGy)`, positioner angles, distances, table positions, `Filter Material` — DICOM-style tables use those labels too |
| `generic_rdsr_like` | A concatenated parser-dump name such as `ManufacturerModelName` or `DoseRP_Gy`. The same words with a space (`Station Name`) do not match. | `Manufacturer` and `KVP_kV` (Radimetrics also uses `kVp kV`), plus `StationName` and `DeviceSerialNumber`, which count toward the score but do not elect |
| `normalized` | An internal column such as `K_IRP`, `DSD`, `DSI`, `Tx`, or `acquisition_type_code` (also `acquisition_type_coding_scheme` and `acquisition_type_meaning`) | `model`, `kVp`, `acquisition_type`, `acquisition_plane`, and the optional station/serial names (`station_name`, `stationname`, `device_serial`, `deviceserialnumber`) |

DICOM RDSR (`.dcm`) is not in this table. The loader routes it by suffix to `rdsr_parser` /
`rdsr_normalizer`. Auto-detect never sees it. A spreadsheet that happens to use DICOM concept
names is not treated as an RDSR; if it also lacks a DoseTrack or Radimetrics marker, detection
stops and asks for an explicit schema.

### What a detected schema changes

The Upload import-preview badge, the exam-card caption, and the Data tab `Schema:` line are
`provenance.schema_name` after a successful parse. The dropdown can stay on Auto-detect while
the badge shows the winner. That name is the adapter that ran:

| Schema | Effect |
|---|---|
| `radimetrics` | Maps `Device` to the model and `Equipment` to the room used as the kerma-meter key. Reads units from the header; an unreadable dose is taken as mGy, area as cm², distances as mm. Splits a row into Plane A and Plane B when both per-plane reference-point dose columns are present and plane B is not empty (see [INPUT_DATA_FLOW_AND_OFFSETS.md](INPUT_DATA_FLOW_AND_OFFSETS.md)). Fills a missing event type with `Fluoroscopy` and, without biplane evidence, a missing plane with `Single Plane`. Then runs `rdsr_normalizer`. Warns when the model is outside the Siemens Artis names this map was checked against. |
| `dosetrack` | See [DoseTrack processing](#dosetrack-processing) below. |
| `generic_rdsr_like` | Treats the table as `rdsr_parser` output. Units are already in the column names (`DoseRP_Gy`, `_mm`). `rdsr_normalizer` applies the manufacturer coordinate profile. |
| `normalized` | The table is already in internal units and the GUISkinDose coordinate frame. No vendor unit conversion and no manufacturer coordinate correction. |

Choosing the wrong schema in the dropdown applies that row of the table. Auto-detect abstains
instead of guessing when the marker is missing or fewer than **2** known columns match.

The same explanation is written for users in
[docs/source/gui_help/input_formats.md](../docs/source/gui_help/input_formats.md). That page is
what the Upload tab's info icon opens, and it is included in the Sphinx user guide.

### DoseTrack processing

`Equipment Name` is the model. Manufacturer is inferred from this fixed map (`MODEL2MANUF`):

| Equipment Name | Manufacturer |
|---|---|
| `AXIOM-Artis` | Siemens |
| `Azurion` | Philips |
| `Allura Clarity` | Philips |

Any other name warns and is used as the manufacturer string. The same column is copied to the
station name, which is the kerma-meter key. DoseTrack has no separate room column. Blank cells
are forward-filled from the row above, because the export repeats the equipment name only on
the first row of a group.

`Plane Code` uses the CID 10003 map above. A Philips filter cell is split on `;` into
aluminium and copper (`Al;Cu`). Any other manufacturer copies that single thickness into both
the minimum and the maximum (the Siemens pattern). Collimated field area is derived from DAP,
reference-point dose, and the two distances when the export does not already provide it. An
unreadable air-kerma unit is taken as mGy, and an unreadable tube current as µA. A missing
event type becomes `Fluoroscopy`. A missing filter material becomes `Cu`.

### Qaelum, DoseMonitor, and DoseWatch

Qaelum, DoseMonitor, and DoseWatch are not choices of `--input-schema` and they are not in the
Upload menu. A Python caller can pass the name to `read_and_normalize_input`, and they are not
in the scoring set. Each raises `NotImplementedError`: the adapter is not yet implemented,
because no real export is available to build a column map.

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

### DICOM RDSR (reads, converts scale-only variants, asserts)

`rdsr_parser.py` embeds each measured value's DICOM unit code
(`MeasurementUnitsCodeSequence`) into the column name — that is why parsed columns are named
`DoseRP_Gy`, `DistanceSourcetoDetector_mm`, `KVP_kV`. `rdsr_normalizer.py` then reads those
unit-suffixed columns with fixed factors (`DoseRP_Gy * 1000`, `_mm / 10`).

Before any read, `rdsr_input_checks.convert_scale_only_units` folds known scale-only variants into
the canonical column: `mGy` → `Gy` for reference-point dose (DICOM TID 10003 specifies Gy, but some
vendors emit mGy), and `cm` / `m` → `mm` for linear distances, table positions, shutters and filter
thicknesses. Area units are never rescaled. The merge is per event: a populated canonical value
wins, a variant fills a blank, and two populated values that disagree raise `RdsrInputError`.
Any other unit raises **`RdsrUnitError`**, which names the quantity and the expected unit but never
echoes the file's unit text. Both errors are `UserFacingInputError`s (value-free by contract), so
the GUI loaders and the CLI show their message instead of the generic error.

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
