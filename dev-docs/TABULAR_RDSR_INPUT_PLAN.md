# Plan: tabular RDSR-derived inputs (`.csv`, `.tsv`, `.xlsx`)

_Last updated: 2026-06-09_

> See also: [FEATURE_INVENTORY.md](FEATURE_INVENTORY.md) | [CODEBASE_OVERVIEW.md](CODEBASE_OVERVIEW.md) | [TO_DO.md](TO_DO.md) | [AGENTS.md](../AGENTS.md)

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

## Typical input file structure

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

### Header-row detection

Scan the first `N` rows (default 10) of the file and score each row by how many cells match any known column pattern. The row with the highest score is used as the header. This handles metadata-row prefixes common in Excel exports.

### Substring pattern dictionary

Each normalized internal variable maps to a list of lowercase substrings. A source column matches a normalized variable if its lowercased, stripped name contains any of the listed substrings. Example structure:

```python
COLUMN_PATTERNS: dict[str, list[str]] = {
    "manufacturer":       ["manufacturer", "vendor", "make"],
    "model":              ["model", "station name"],
    "primary_angle":      ["primary angle", "primary_angle", "positioner primary", "angle 1"],
    "secondary_angle":    ["secondary angle", "secondary_angle", "positioner secondary", "angle 2"],
    "table_lateral":      ["table lateral", "lateral position", "table pos lat", "isocenter y"],
    "table_longitudinal": ["table longitudinal", "longitudinal position", "table pos long", "isocenter x"],
    "table_height":       ["table height", "cradle height", "table pos height", "isocenter z"],
    "kvp":                ["kvp", "kv", "tube voltage"],
    "reference_dose_total": ["reference point dose", "air kerma", "dose (mgy)", "kap"],
    "reference_dose_a":   ["dose a", "tube a dose", "reference dose a"],
    "reference_dose_b":   ["dose b", "tube b dose", "reference dose b"],
    # ... extend as validated exports are seen
}
```

### Duplicate mapping detection

Before ingesting any file, check that no two source columns map to the same normalized variable. If duplicates are found, **fail loudly** with a message listing both source column names and the normalized variable they both matched — do not silently pick one. The user must resolve the ambiguity (e.g. via an explicit override map passed at call time).

### Unmapped required columns

After mapping, verify that all required normalized columns are present. Report any missing ones by normalized name, with the list of patterns that were tried, so the user knows what column name would satisfy the requirement.

### Vendor-specific coordinate normalization

Several vendors use different coordinate conventions that require post-mapping transforms:

- **Philips** — table height uses a different sign convention or origin than the internal model.
- **GE** — lateral and longitudinal axes are swapped relative to the internal model.
- Other vendors likely have similar issues; these will be discovered as real exports are validated.

**These transforms are deferred to later phases** (Phase 3+ per vendor, or added as TO_DO items as they are discovered). The column mapper produces a raw-mapped DataFrame; coordinate normalization is a separate step applied per detected manufacturer. See [TO_DO.md](TO_DO.md) for the tracking items.

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
class InputAdapterResult:
    normalized_data: pd.DataFrame
    raw_data: pd.DataFrame | None
    source_type: str
    schema_name: str
    provenance: dict[str, Any]
    warnings: list[str]

@dataclass
class ParsedEventTable:
    parsed_data: pd.DataFrame
    source_type: str
    schema_name: str
    column_map: dict[str, str]      # source col → normalized var
    unit_conversions: dict[str, str] # normalized var → "source_unit → target_unit"
    header_row_index: int
    warnings: list[str]
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
- `--input-schema {auto,normalized,generic_rdsr_like,radimetrics,dosetrack}`
- `--sheet-name SHEET`
- `--input-preview-only` — print detected header row, column map, missing required columns, and unit assumptions without calculating dose.

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
- `radimetrics_axiom_artis.csv` (Phase 3)
- `dosetrack_siemens.xlsx` (Phase 4)

Tests to write:
- Unit tests for header-row detection (including offset headers).
- Unit tests for the substring pattern dictionary (each pattern maps correctly).
- Unit tests for duplicate-mapping detection (two columns match same var → error).
- Unit tests for missing-required-column reporting.
- Unit tests for each schema adapter (column map, unit conversions).
- Round-trip tests: equivalent DICOM-derived normalized JSON vs CSV/TSV/XLSX normalized input.
- Failure tests: missing columns, wrong units, invalid numeric cells, unknown model, ambiguous schema, unsupported sheet.
- One end-to-end smoke test via `analyze_input_file()` with a normalized fixture.
- Architecture layer test: `input_adapters/` must not import L3+.

---

## Implementation phases

### Phase 1 — Normalized tabular input (active target)

- [ ] Add `openpyxl` to core `dependencies` in `pyproject.toml`.
- [ ] Create `src/mypyskindose/input_adapters/__init__.py`.
- [ ] Create `models.py` with `InputAdapterResult` and `ParsedEventTable`.
- [ ] Create `column_mapper.py`:
  - [ ] Implement `detect_header_row(df_raw, n=10) -> int`.
  - [ ] Define initial `COLUMN_PATTERNS` dict for the normalized schema's required columns.
  - [ ] Implement `map_columns(df, patterns) -> tuple[dict[str, str], list[str]]` (column map + warnings).
  - [ ] Implement `check_duplicate_mappings(column_map) -> list[str]` (returns error messages).
- [ ] Create `tabular_loader.py`:
  - [ ] `read_csv(path, delimiter=',') -> pd.DataFrame` (raw, no header applied yet).
  - [ ] `read_tsv(path, delimiter='\t') -> pd.DataFrame`.
  - [ ] `read_excel(path, sheet_name=0) -> pd.DataFrame`.
  - [ ] Strip column names, drop wholly-empty rows, preserve original column order in provenance.
- [ ] Create `normalized.py` — `normalized` schema adapter:
  - [ ] Define required and optional normalized columns with expected units.
  - [ ] Validate all required columns present post-mapping.
  - [ ] Validate numeric columns; collect row-level failures.
  - [ ] Return `InputAdapterResult` with provenance dict.
- [ ] Create `registry.py` with `read_and_normalize_input()` routing by suffix.
- [ ] Add `analyze_input_file()` to `src/mypyskindose/__init__.py` public API.
- [ ] Add `--input-schema` and `--sheet-name` CLI flags to `__main__.py` / `main.py`.
- [ ] Add `--input-preview-only` CLI flag.
- [ ] Add fixtures: `normalized_events.csv`, `normalized_events.tsv`, `normalized_events.xlsx`, `normalized_events_metadata_header.xlsx`.
- [ ] Write unit tests for all of the above (see testing plan).
- [ ] Add `input_adapters/` to architecture layer test (must not import L3+).
- [ ] Update `FEATURE_INVENTORY.md` Phase 1 row to `Shipped`.
- [ ] Update `AGENTS.md` and `CHANGELOG.md`.

### Phase 2 — Generic raw RDSR-like tabular input

- [ ] Add `COLUMN_PATTERNS` entries for raw `rdsr_parser()` output column names.
- [ ] Create `generic_rdsr.py` adapter: map → `rdsr_normalizer()` → `InputAdapterResult`.
- [ ] Add fixture `generic_rdsr_events.csv`.
- [ ] Add tests: column map, normalization round-trip, failure cases.
- [ ] Extend `registry.py` routing for `generic_rdsr_like` schema.

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

The feature is complete when:

- Users can run a dose calculation from `.csv`, `.tsv`, and `.xlsx` normalized event tables.
- At least one Radimetrics CSV schema and one DoseTrack XLSX schema have validated adapters, or are explicitly documented as unsupported until fixtures are available.
- The CLI, Python API, and GUI share the same adapter registry.
- Duplicate column mappings and missing required columns produce clear, actionable error messages.
- Validation errors identify columns by name with actionable remediation text.
- Output includes tabular-input provenance and adapter warnings.
- Tests cover success and failure paths for each supported format and schema.
- `input_adapters/` passes the architecture layer test (no L3+ imports).
