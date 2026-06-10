# Plan: tabular RDSR-derived inputs (`.csv`, `.tsv`, `.xlsx`)

_Last updated: 2026-06-09_

> See also: [INPUT_DATA_FLOW_AND_OFFSETS.md](INPUT_DATA_FLOW_AND_OFFSETS.md) | [FEATURE_INVENTORY.md](FEATURE_INVENTORY.md) | [CODEBASE_OVERVIEW.md](CODEBASE_OVERVIEW.md) | [TO_DO.md](TO_DO.md) | [AGENTS.md](../AGENTS.md)

**Status: pre-implementation — no code written yet. Phase 1 is the active target.**

---

## Objective

Allow MyPySkinDose to run from exported irradiation-event tables in addition to current DICOM RDSR and normalized JSON inputs.
The target formats are:

- `.csv` — comma-separated event tables (e.g. Radimetrics exports)
- `.tsv` — tab-separated event tables (report tool or spreadsheet exports)
- `.xlsx` — workbook exports (e.g. DoseTrack-style event tables)

The goal is **not** to replace DICOM RDSR ingestion. DICOM RDSR remains the preferred high-fidelity source when available. Tabular import is an adapter layer for sites where dose-management software exports one row per irradiation event but direct DICOM SR access is difficult.

---

## Conceptual data flow

All sources converge on the same internal contract before dose calculation. The **normalized DataFrame** (internal units, unified coordinate frame) is the contract consumed by `analyze_data()`; its columns and units are defined in [INPUT_DATA_FLOW_AND_OFFSETS.md](INPUT_DATA_FLOW_AND_OFFSETS.md).

```text
                                      ┌─ DICOM RDSR ──→ rdsr_parser() ─┐
                                      │                                │
raw vendor table (CSV/TSV/XLSX) ──→ column map ──→ unit convert ──→ vendor coordinate
   (Radimetrics, DoseTrack, etc.)                                   normalize ──┐
                                                                                 ▼
                                                          raw-RDSR-like DataFrame ──→ rdsr_normalizer()
                                                                                                 │
already-normalized table (CSV/TSV/XLSX) ─────────────────────────────────────────┐              ▼
   (typically produced by MyPySkinDose itself)                                    └──→ normalized DataFrame ──→ analyze_data()
```

The substantive work for real vendor data is **column mapping + unit conversion + vendor coordinate normalization** (the left/middle of the diagram). Reading an already-normalized table (bottom-left) is the trivial endpoint — few users have such files; it is primarily an internal/test contract and the target every vendor adapter produces.

## Phase sequencing rationale

The build order is **infrastructure-first**, then schemas from simplest to most vendor-specific. This is deliberate and partly forced by external constraints:

1. **Shared infrastructure** (loader, column mapper, registry, models) is a hard prerequisite for every schema, so it lands first regardless of which schema delivers user value.
2. **The `normalized` schema is the walking skeleton** — it exercises loader → registry → `analyze_data()` end-to-end with zero unit/coordinate complexity, de-risking the plumbing before vendor quirks are added. It is *not* a major user-facing unlock (most users lack normalized tables); it is the contract the vendor adapters target.
3. **The first real read-and-normalize path is the generic raw RDSR-like schema** (Phase 2), which can be built now from RDSR-shaped fixtures synthesized from existing test RDSRs — no proprietary vendor exports required.
4. **Vendor adapters (Radimetrics, DoseTrack) are gated on real export samples**, which are not yet available. We therefore build everything that does *not* need samples first, and slot vendor adapters in when samples land.

In short: the order reflects dependency layering and sample availability, not a claim that normalized-table import is the priority deliverable. User value arrives with Phases 2–4.

---

## Typical input file structure

> **Scope note:** this section describes **raw vendor exports** (Phases 2–4). The Phase 1 `normalized` schema instead expects columns already matching the internal contract in [INPUT_DATA_FLOW_AND_OFFSETS.md](INPUT_DATA_FLOW_AND_OFFSETS.md) — already in internal units and coordinate frame, with no `manufacturer`/`model` dependence and no vendor coordinate correction (normalization has already been applied).

Tabular exports from dose-management systems (Radimetrics, DoseTrack, vendor-native exports, etc.) share a common structure:

- **One header row** containing column names, followed by **one data row per irradiation event.**
- The header row is usually the first row, but some exports include metadata rows above it (system name, export date, filter criteria, etc.). The header must be located dynamically.
- Column names vary significantly across vendors and software versions. Examples of the same field across sources:

| Field (internal name) | Example column names seen in the wild |
|---|---|
| Manufacturer | `Manufacturer`, `Vendor`, `Make` |
| Model | `Model`, `Station Name`, `Device Model` |
| Primary angle | `Primary Angle`, `C-Arm Primary`, `Positioner Primary Angle`, `Angle 1` |
| Secondary angle | `Secondary Angle`, `C-Arm Secondary`, `Positioner Secondary Angle`, `Angle 2` |
| Table lateral | `Table Lateral`, `Lateral Position`, `Table Pos Lat`, `Isocenter Y` |
| Table longitudinal | `Table Longitudinal`, `Longitudinal Position`, `Table Pos Long`, `Isocenter X` |
| Table height | `Table Height`, `Cradle Height`, `Table Pos Height`, `Isocenter Z` |
| kVp | `kVp`, `KVP`, `Tube Voltage` |
| Reference dose (total) | `Reference Point Dose`, `Air Kerma`, `KAP`, `Dose (mGy)` |
| Reference dose tube A | `Dose A`, `Tube A Dose`, `Reference Dose A` |
| Reference dose tube B | `Dose B`, `Tube B Dose`, `Reference Dose B` |

Because names vary, column mapping uses **substring pattern matching** rather than exact-name lookup (see §Column mapping architecture below).

---

## Column mapping architecture

The column mapper is a shared mechanism used by all **raw/vendor** schemas (Phases 2–4). The Phase 1 `normalized` schema uses near-exact internal column names and does **not** rely on fuzzy matching beyond case/whitespace normalization (see Phase 1).

### Header-row detection

Scan the first `N` rows (default 10) and score each row by how many cells match the **selected schema's** column patterns (or the union of all schemas' patterns when `--input-schema auto`). The highest-scoring row is the header. This handles metadata-row prefixes common in Excel exports. If no row scores above a minimum threshold, fail with a clear "could not locate a header row" message rather than guessing row 0.

### Substring pattern dictionary and best-match resolution

Each normalized internal variable maps to a list of lowercase patterns. Matching is **not** naive `in` containment — that silently mismaps. The rules:

1. **Word-boundary aware.** Normalize the source column (lowercase, collapse whitespace/underscores) and match patterns on token/word boundaries, so a 2-letter pattern like `kv` does not match inside unrelated words.
2. **Best (most-specific) match wins.** When a source column matches patterns for more than one variable, assign it to the variable whose matched pattern is **longest/most specific**, not the first one tried. When a variable has several candidate columns, keep the best-scoring column.
3. **Concrete collision to guard against:** a `Dose Area Product` (DAP/KAP) column contains the substring `dose a` and would naively mismap to `reference_dose_a` (tube A dose) — a *silent wrong result*, worse than a loud error. Word-boundary matching plus a more specific `air kerma`/`dose area product` pattern for the total-dose/KAP variable must take precedence. This case has a dedicated regression test (see testing plan).

```python
COLUMN_PATTERNS: dict[str, list[str]] = {
    "manufacturer":       ["manufacturer", "vendor", "make"],
    "model":              ["model", "station name", "device model"],
    "primary_angle":      ["primary angle", "positioner primary angle", "c-arm primary"],
    "secondary_angle":    ["secondary angle", "positioner secondary angle", "c-arm secondary"],
    "table_lateral":      ["table lateral", "lateral position", "table pos lat"],
    "table_longitudinal": ["table longitudinal", "longitudinal position", "table pos long"],
    "table_height":       ["table height", "cradle height", "table pos height"],
    "kvp":                ["kvp", "tube voltage"],   # not bare "kv"
    "reference_dose_total": ["reference point dose", "air kerma", "dose area product", "kap"],
    "reference_dose_a":   ["tube a dose", "reference dose a", "dose tube a"],
    "reference_dose_b":   ["tube b dose", "reference dose b", "dose tube b"],
    # ... extend as validated exports are seen
}
```

### Duplicate mapping detection

After best-match resolution, check that no two source columns are assigned to the same normalized variable. If duplicates remain, **fail loudly** listing both source column names and the variable — do not silently pick one. The user resolves the ambiguity via an explicit override map passed at call time.

### Unmapped required columns

Verify all required normalized columns are present. Report missing ones by normalized name, with the patterns that were tried, so the user knows what column name would satisfy the requirement.

### Schema auto-detection (`--input-schema auto`)

Auto-detection scores each candidate schema by the fraction of its **required** patterns that find a matching column, and picks the highest. It must require a **margin** over the runner-up (e.g. ≥ 0.2); if two schemas tie or no schema clears a minimum required-coverage threshold, it **errors and asks the user to pass `--input-schema` explicitly** rather than guessing. Auto-detection is **deferred past Phase 1** — Phase 1 ships with explicit schema selection only; `auto` is wired once at least two schemas exist (Phase 3+).

### Source encoding, delimiter, and decimal separator

Clinical exports — especially from European sites — frequently use a `;` delimiter with `,` as the decimal separator, and may carry a UTF-8 BOM or non-UTF-8 encoding. The tabular loader must:

- detect/handle a BOM and fall back across common encodings (utf-8, utf-8-sig, cp1252, latin-1);
- sniff the delimiter for `.csv` (comma vs semicolon) rather than assuming comma;
- detect decimal-comma numeric formatting and normalize to `.` before numeric parsing.

Failures here surface as garbled columns or all-string numerics, so they must be validated explicitly with fixtures.

### Multiple procedures / devices in one file

A tabular export can contain rows spanning several studies, patients, or devices, whereas a single RDSR is one procedure. **Phase 1 assumes a single procedure.** If the loader detects more than one distinct study/accession/device identifier (when such a column is present), it **warns and, by default, errors** asking the user to filter the export to one procedure. Multi-procedure splitting is out of scope here and tracked under the "support for multiple exams" item in [TO_DO.md](TO_DO.md).

### Vendor-specific coordinate normalization

Raw vendor schemas need post-mapping coordinate transforms:

- **Philips** — table height uses a different sign convention or origin than the internal model.
- **GE** — lateral and longitudinal axes are swapped relative to the internal model.
- Other vendors likely have similar issues, discovered as real exports are validated.

These are a **separate step after column mapping**, applied per detected manufacturer, and are **deferred to the vendor adapter phases** (3–4) or added as TO_DO items as discovered. The Phase 1 `normalized` schema does **not** apply them (data is already normalized). See [TO_DO.md](TO_DO.md) for tracking items.

---

## Current ingestion behavior

The current primary entry point accepts either a DICOM RDSR file or a pre-parsed JSON file path. `read_and_normalise_rdsr_data()` treats `.json` as already parsed/normalized tabular data and sends every other suffix through `pydicom.dcmread()` → `rdsr_parser()` → `rdsr_normalizer()`.

For callers that already have a normalized `pandas.DataFrame`, the code can bypass file parsing via `analyze_normalized_data_with_custom_settings_object()`.

---

## Existing fork to learn from

A related PySkinDose fork at `https://github.com/dhen2714/PySkinDose.git` includes two modules worth studying before implementation:

- `src/pyskindose/radimetrics.py` — `RADIMETRICS2PSD` column map; reads CSV via `pd.read_csv()`; converts units (mGy→Gy, cm²→m², mAs→µAs) before `rdsr_normalizer()`.
- `src/pyskindose/dosetrack.py` — `DOSETRACK2PSD` column map for DoseTrack Excel exports; vendor-specific transforms for Siemens and Philips; filter parsing, plane-name normalization, derived collimated field area.

These are prototypes/references — not to be copied blindly. They use exact-name column matching (not the substring approach described above), are tightly coupled to specific export schemas, and lack unit tests and safe error reporting.

---

## Design principles

1. **Normalize all paths into one internal contract.**
   Every source should become either a raw RDSR-like parsed DataFrame compatible with `rdsr_normalizer()`, or a fully normalized DataFrame compatible with `analyze_data()`.

2. **Separate format loading, column mapping, and source-schema normalization.**
   File suffix handling (`csv`/`tsv`/`xlsx`), substring-based column mapping, and vendor coordinate transforms are three distinct steps — do not mix them.

3. **Make units explicit and testable.**
   Every adapter must document the source column unit and the internal target unit in code, not just comments.

4. **Prefer named schemas over guessing.**
   Auto-detection can assist, but the API and GUI must let users select a schema explicitly when detection is ambiguous.

5. **Keep core dependencies stable.**
   CSV/TSV support relies on existing pandas. XLSX requires `openpyxl`, which is a **core dependency** (added to `pyproject.toml` `dependencies`).

6. **Preserve provenance.**
   Outputs record source type, selected schema, original filename, detected header row, applied column map, unit conversions, and warnings so clinical users can audit the transformation.

7. **Fail loudly on ambiguity.**
   Duplicate column mappings, missing required columns, and unrecognized manufacturer/model must produce clear, actionable error messages — not silent fallbacks.

---

## Layer placement

`input_adapters/` sits at **L2 — Helpers & input** (same layer as `rdsr_parser.py` and `rdsr_normalizer.py`). It may import from:

- L0 (`constants.py`, `debug.py`)
- L1 (`settings/`)
- L2 siblings (`helpers/`)

It must **not** import from L3+ (domain models, dose pipeline, plotting, GUI, orchestration). The structural tests in `tests/unittests/test_architecture_layers.py` should be extended to assert this once the package exists.

---

## Proposed architecture

```text
src/mypyskindose/input_adapters/
  __init__.py
  models.py           — InputAdapterResult, ParsedEventTable dataclasses
  column_mapper.py    — header detection, substring pattern dict, duplicate check
  tabular_loader.py   — generic CSV / TSV / XLSX file reading
  registry.py         — read_and_normalize_input() routing function
  normalized.py       — 'normalized' schema adapter (Phase 1)
  generic_rdsr.py     — 'generic_rdsr_like' schema adapter (Phase 2)
  radimetrics.py      — Radimetrics schema adapter (Phase 3)
  dosetrack.py        — DoseTrack schema adapter (Phase 4)
```

Only `models.py`, `column_mapper.py`, `tabular_loader.py`, `registry.py`, and `normalized.py` are needed for Phase 1. The remaining modules are stubs or added later.

### `models.py`

```python
@dataclass
class InputProvenance:
    """Typed audit trail (preferred over a free-form dict for testability)."""
    source_type: str                 # "csv" | "tsv" | "xlsx" | "dicom" | "json"
    schema_name: str                 # "normalized" | "generic_rdsr_like" | "radimetrics" | ...
    original_filename: str
    header_row_index: int
    detected_encoding: str
    detected_delimiter: str | None   # None for xlsx
    sheet_name: str | int | None     # None for non-Excel
    column_map: dict[str, str]       # source col → normalized var
    unit_conversions: dict[str, str] # normalized var → "source_unit → target_unit"
    warnings: list[str]

@dataclass
class InputAdapterResult:
    normalized_data: pd.DataFrame
    raw_data: pd.DataFrame | None
    provenance: InputProvenance
    warnings: list[str]

@dataclass
class ParsedEventTable:
    parsed_data: pd.DataFrame
    provenance: InputProvenance
```

### `registry.py`

```python
def read_and_normalize_input(
    file_path: str | Path | None,
    settings: PyskindoseSettings,
    *,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
) -> InputAdapterResult: ...
```

Routing by suffix:

| Suffix | Default route |
|---|---|
| `.dcm`, `.dicom`, unrecognized | DICOM RDSR adapter |
| `.json` | normalized JSON adapter |
| `.csv` | tabular adapter, comma delimiter |
| `.tsv` | tabular adapter, tab delimiter |
| `.xlsx`, `.xlsm` | tabular Excel adapter |

---

## Public API changes

### New helper (Option B — recommended)

```python
def analyze_input_file(
    file_path: str | Path,
    settings: str | dict | PyskindoseSettings,
    *,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
    output_format: str = "dict",
) -> dict | str | None: ...
```

Keeps `main()` backward compatible. Once adapter behavior is stable, let `main()` call the same registry internally.

---

## CLI changes

```bash
python -m mypyskindose \
  --file-path exported_events.csv \
  --settings settings.json \
  --input-schema normalized

python -m mypyskindose \
  --file-path dose_track_export.xlsx \
  --settings settings.json \
  --input-schema dosetrack \
  --sheet-name "Event Data"
```

Flags to add:
- `--input-schema {normalized,generic_rdsr_like,radimetrics,dosetrack}` in Phase 1; `auto` added in Phase 3+ once ≥2 schemas exist.
- `--sheet-name SHEET`
- `--input-preview-only` — print detected header row, encoding/delimiter, column map, missing required columns, and unit assumptions without calculating dose.

---

## GUI changes (Phase 5)

- [ ] Extend upload accepted formats to `.csv`, `.tsv`, `.xlsx`, `.xlsm`.
- [ ] Add schema selector (Auto-detect / Normalized / Raw RDSR-like / Radimetrics / DoseTrack).
- [ ] For `.xlsx`/`.xlsm`: show sheet names after upload; let user pick the data sheet.
- [ ] Show import preview after upload:
  - Detected header row index (flag if not row 0).
  - Column mapping table: source column → normalized variable → unit conversion (or "unmapped").
  - List of required columns that could not be mapped (block proceed if any).
  - Duplicate-mapping warnings (block proceed).
  - First 10 normalized events in a table.
  - Any adapter warnings requiring user confirmation.
- [ ] Preserve tabular-input provenance (schema, column map, warnings) in exported JSON/HTML reports.
- [ ] Show schema/source type in the Data Table tab header so users know what they loaded.

---

## Validation requirements

Every adapter must validate:

- [ ] Required source columns exist (post-mapping).
- [ ] No duplicate column mappings.
- [ ] Required internal normalized columns are present after mapping.
- [ ] Numeric columns parse cleanly; report row-level failures with row index.
- [ ] Source units are converted to PySkinDose internal expectations.
- [ ] Distances are positive and within plausible clinical ranges.
- [ ] `kVp` is non-negative; zero-kVp rows handled consistently with `remove_invalid_rows`.
- [ ] Reference point dose has expected unit and scale.
- [ ] Field size is present directly or derivable with a documented formula.
- [ ] Manufacturer/model can be mapped to normalization settings, or a safe fallback is selected explicitly with a warning.

---

## Testing plan

Fixture files under `tests/fixtures/tabular_inputs/`:
- `normalized_events.csv`
- `normalized_events.tsv`
- `normalized_events.xlsx`
- `normalized_events_metadata_header.xlsx` — metadata rows above the data header
- `normalized_events_semicolon_decimalcomma.csv` — European `;`-delimited, decimal-comma
- `normalized_events_multistudy.csv` — rows spanning >1 study/device
- `generic_rdsr_events.csv` (Phase 2; synthesized from an existing test RDSR)
- `radimetrics_axiom_artis.csv` (Phase 3)
- `dosetrack_siemens.xlsx` (Phase 4)

Tests to write:
- Header-row detection, including offset headers and the "no header found" error.
- Column matching: word-boundary correctness; **`Dose Area Product` must map to total dose/KAP, not `reference_dose_a`** (regression test for the substring collision); best-match resolution when one column matches multiple variables.
- Duplicate-mapping detection (two columns resolve to same var → error).
- Missing-required-column reporting (names the variable and tried patterns).
- Encoding/delimiter: semicolon + decimal-comma fixture parses to correct numerics; BOM handled.
- Multi-study detection: multistudy fixture warns and errors by default.
- Per-schema adapter tests (column map, unit conversions where applicable).
- Round-trip: DICOM-derived normalized JSON vs CSV/TSV/XLSX normalized input; and (Phase 2) generic-RDSR CSV vs its source RDSR.
- Schema auto-detection (Phase 3+): correct pick with margin; tie/low-coverage → error asking for explicit schema.
- Failure tests: wrong units, invalid numeric cells, unknown model, unsupported sheet.
- End-to-end smoke test via `analyze_input_file()` with a normalized fixture.
- Architecture layer test: `input_adapters/` must not import L3+.

---

## Implementation phases

### Phase 1 — Shared infrastructure + normalized schema (active target)

Foundational plumbing plus the simplest schema as a walking skeleton (see Phase sequencing rationale). Builds everything that does not require vendor samples. The `normalized` schema expects columns already matching the internal contract in [INPUT_DATA_FLOW_AND_OFFSETS.md](INPUT_DATA_FLOW_AND_OFFSETS.md) — do not invent a column list; anchor to that doc.

- [ ] Add `openpyxl` to core `dependencies` in `pyproject.toml`.
- [ ] Create `src/mypyskindose/input_adapters/__init__.py`.
- [ ] Create `models.py` with `InputProvenance`, `InputAdapterResult`, `ParsedEventTable`.
- [ ] Create `column_mapper.py`:
  - [ ] Implement `detect_header_row(df_raw, patterns, n=10) -> int` (error if no row clears the threshold).
  - [ ] Define initial `COLUMN_PATTERNS` (for raw/vendor schemas in later phases; Phase 1 normalized schema uses near-exact internal names).
  - [ ] Implement word-boundary, best-match `map_columns(df, patterns) -> tuple[dict[str, str], list[str]]`.
  - [ ] Implement `check_duplicate_mappings(column_map) -> list[str]` (error messages).
- [ ] Create `tabular_loader.py`:
  - [ ] `read_csv` / `read_tsv` with **encoding fallback** (utf-8, utf-8-sig, cp1252, latin-1) and **delimiter sniffing** (comma vs semicolon).
  - [ ] Decimal-comma detection and normalization to `.` before numeric parsing.
  - [ ] `read_excel(path, sheet_name=0)`.
  - [ ] Strip column names, drop wholly-empty rows, record encoding/delimiter/order in provenance.
- [ ] Create `normalized.py` — `normalized` schema adapter:
  - [ ] Define required/optional columns and units **by reference to the internal contract** (`INPUT_DATA_FLOW_AND_OFFSETS.md`); no manufacturer/model dependence, no vendor coordinate correction.
  - [ ] Validate required columns present; validate numeric columns with row-level failure reporting.
  - [ ] Detect multiple study/accession/device IDs (if present) → warn and error by default (single-procedure assumption).
  - [ ] Return `InputAdapterResult` with a populated `InputProvenance`.
- [ ] Create `registry.py` with `read_and_normalize_input()` routing by suffix (explicit schema only; `auto` raises "not yet supported" in Phase 1).
- [ ] Add `analyze_input_file()` to `src/mypyskindose/__init__.py` public API.
- [ ] Add `--input-schema` (explicit values only) and `--sheet-name` CLI flags to `__main__.py` / `main.py`.
- [ ] Add `--input-preview-only` CLI flag (prints header row, encoding/delimiter, column map, missing required columns, unit assumptions; no dose calc).
- [ ] Add fixtures: `normalized_events.csv`, `normalized_events.tsv`, `normalized_events.xlsx`, `normalized_events_metadata_header.xlsx`, `normalized_events_semicolon_decimalcomma.csv`, `normalized_events_multistudy.csv`.
- [ ] Write unit tests for all of the above (see testing plan).
- [ ] Add `input_adapters/` to architecture layer test (must not import L3+).
- [ ] Update `FEATURE_INVENTORY.md` Phase 1 row to `Shipped`.
- [ ] Update `AGENTS.md` and `CHANGELOG.md`.

### Phase 2 — Generic raw RDSR-like tabular input

**First real read-and-normalize path.** Exercises column map → `rdsr_normalizer()` with vendor-agnostic raw columns. Can be built now: synthesize RDSR-shaped fixtures from existing test RDSRs (`rdsr_parser()` output dumped to CSV) — no proprietary vendor exports required.

- [ ] Add `COLUMN_PATTERNS` entries for raw `rdsr_parser()` output column names.
- [ ] Create `generic_rdsr.py` adapter: map → `rdsr_normalizer()` → `InputAdapterResult`.
- [ ] Add fixture `generic_rdsr_events.csv` (synthesized from an existing test RDSR).
- [ ] Add tests: column map, normalization round-trip vs the source RDSR, failure cases.
- [ ] Extend `registry.py` routing for `generic_rdsr_like` schema.
- [ ] Enable `--input-schema auto` once a second schema exists (with margin/threshold per the auto-detection rules).

### Phase 3 — Radimetrics adapter

- [ ] Study `dhen2714/PySkinDose` `radimetrics.py`; document differences from our column-mapping approach.
- [ ] Add Radimetrics-specific `COLUMN_PATTERNS` entries.
- [ ] Create `radimetrics.py` adapter:
  - [ ] Unit conversions: reference dose mGy→Gy, field area cm²→m², exposure mAs→µAs.
  - [ ] Document each conversion with source unit and target unit in code.
  - [ ] Limit to validated models only; unknown models produce an explicit warning, not a silent fallback.
- [ ] Add fixture `radimetrics_axiom_artis.csv`.
- [ ] Add tests: column map, unit conversions, unknown-model error.
- [ ] **Philips coordinate normalization** — table height sign/origin correction: see TO_DO.md.
- [ ] Update `FEATURE_INVENTORY.md`, `AGENTS.md`, `CHANGELOG.md`.

### Phase 4 — DoseTrack adapter

- [ ] Study `dhen2714/PySkinDose` `dosetrack.py`; document differences.
- [ ] Create `dosetrack.py` adapter:
  - [ ] XLSX sheet handling (auto-detect data sheet or require user selection).
  - [ ] Filter parsing, plane-name normalization, derived collimated field area.
  - [ ] Siemens and Philips paths validated and tested separately.
- [ ] Add fixture `dosetrack_siemens.xlsx`.
- [ ] Add tests: column map, sheet handling, vendor-path failures.
- [ ] **GE lateral/longitudinal swap** — see TO_DO.md.
- [ ] Update inventory and docs.

### Phase 5 — GUI import workflow

See GUI changes section above for the full checklist. Key tasks:

- [ ] Extend upload accepted formats.
- [ ] Add schema selector and sheet picker.
- [ ] Implement import preview panel (column map, warnings, event sample).
- [ ] Block dose calculation on unresolved mapping errors.
- [ ] Preserve provenance in exports.
- [ ] GUI smoke test covering CSV/XLSX upload path.

---

## Open questions

All resolved.

| Question | Decision |
|---|---|
| XLSX engine — `[excel]` extra or core dependency? | **Core.** Add `openpyxl` as a core dependency in `pyproject.toml`. No optional extra needed. |
| Which Radimetrics export templates do intended users have? | **Deferred.** Real export samples will be provided before Phase 3 begins; do not start Phase 3 without them. |
| Are exported values event-local or cumulative? | **Primarily event-local** (one row = one irradiation event). Some exports may include a running-total column for a handful of fields (e.g. cumulative dose). Adapters should detect and skip or ignore running-total rows/columns rather than treating them as events; document the handling per source. |
| Do exports include enough geometry for clinical use? | **Yes, generally.** Exports from dose-management systems are expected to carry the same geometric fields as the underlying RDSR (angles, table position, field size, etc.). Gaps should be treated as data-quality issues and reported per event, not as a design limitation. |
| Column-pattern overrides — Python-only or JSON/YAML? | **Python-only first.** JSON/YAML site-customization is tracked as a future TO_DO item. |

---

## Acceptance criteria

### Phase 1 done-bar (no vendor samples required)

- Users can run a dose calculation from `.csv`, `.tsv`, and `.xlsx` **normalized** event tables via the Python API and CLI.
- The loader handles UTF-8/BOM/cp1252, comma and semicolon delimiters, and decimal-comma numerics.
- Header detection finds offset headers and errors clearly when none is found.
- Multiple-procedure files warn and error by default.
- Column mismatches, duplicate mappings, and missing required columns produce clear, named, actionable errors.
- Output includes a typed `InputProvenance`.
- `input_adapters/` passes the architecture layer test (no L3+ imports).
- The `Dose Area Product`→tube-A regression test and the encoding/multi-study tests pass.

### Full-feature done-bar

- At least one Radimetrics CSV schema and one DoseTrack XLSX schema have validated adapters, or are explicitly documented as unsupported until fixtures are available.
- Vendor coordinate normalization (Philips height, GE lat/lon swap, others as found) is applied and tested per adapter.
- `--input-schema auto` selects correctly with a margin and errors on ambiguity.
- The CLI, Python API, and GUI share the same adapter registry, with the GUI import preview blocking on unresolved mapping errors.
- Tests cover success and failure paths for each supported format and schema.
