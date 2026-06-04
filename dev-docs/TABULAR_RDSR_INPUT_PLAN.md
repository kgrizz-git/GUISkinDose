# Plan: tabular RDSR-derived inputs (`.csv`, `.tsv`, `.xlsx`)

_Date: 2026-06-04_

## Objective

Allow MyPySkinDose to run from exported irradiation-event tables in addition to current DICOM RDSR and normalized JSON inputs.
The target formats are:

- `.csv` — comma-separated event tables, such as Radimetrics exports.
- `.tsv` — tab-separated event tables, often produced by report tools or spreadsheet exports.
- `.xlsx` — workbook exports, such as DoseTrack-style event tables.

The goal is **not** to replace DICOM RDSR ingestion. DICOM RDSR remains the preferred high-fidelity source when available. Tabular import is an adapter layer for sites where dose-management software exports one row per irradiation event but direct DICOM SR access is difficult.

## Current ingestion behavior

The current primary entry point accepts either a DICOM RDSR file or a pre-parsed JSON file path. The helper `read_and_normalise_rdsr_data()` treats `.json` as already parsed/normalized tabular data and sends every other suffix through `pydicom.dcmread()`, followed by `rdsr_parser()` and `rdsr_normalizer()`.

For callers that already have a normalized `pandas.DataFrame`, the code can bypass file parsing and call `analyze_normalized_data_with_custom_settings_object()`.

## Existing fork to learn from

A related PySkinDose fork exists at `https://github.com/dhen2714/PySkinDose.git` and includes two modules worth studying before implementation:

- `src/pyskindose/radimetrics.py`
  - Defines a `RADIMETRICS2PSD` column map from Radimetrics CSV columns into PySkinDose/RDSR-like parsed columns.
  - Reads CSV via `pd.read_csv()`.
  - Converts units such as reference point dose from mGy to Gy, collimated field area from cm² to m², and exposure from mAs to µAs before reusing `rdsr_normalizer()`.
- `src/pyskindose/dosetrack.py`
  - Defines a `DOSETRACK2PSD` column map for DoseTrack Excel exports.
  - Reads XLSX via `pd.read_excel()`.
  - Contains vendor-specific transforms for Siemens and Philips, including filter parsing, plane-name normalization, and derived collimated field area.

These modules should be treated as a prototype/reference, not copied blindly. They are tightly coupled to specific export schemas and contain hard-coded assumptions that need validation, schema documentation, unit tests, and safer error reporting before inclusion in MyPySkinDose.

## Design principles

1. **Normalize all paths into one internal contract.**
   Every source should become either:
   - a raw RDSR-like parsed DataFrame compatible with `rdsr_normalizer()`, or
   - a fully normalized DataFrame compatible with `analyze_data()`.

2. **Separate format loading from source-schema mapping.**
   File suffix handling (`csv`/`tsv`/`xlsx`) should not be mixed with Radimetrics, DoseTrack, or future vendor mappings.

3. **Make units explicit and testable.**
   Every adapter must document the source column unit and the internal target unit.

4. **Prefer named schemas over guessing.**
   Auto-detection can be helpful, but the API and GUI should let users select a schema explicitly when detection is ambiguous.

5. **Keep core dependencies stable.**
   CSV/TSV support can rely on existing pandas. XLSX support may require an Excel engine such as `openpyxl`; if it is not already available transitively, add it as an optional extra rather than a hard core dependency unless project maintainers decide XLSX is core.

6. **Preserve provenance.**
   Outputs should record source type, selected schema, original filename, applied column map, unit conversions, and warnings so clinical users can audit the transformation.

## Proposed architecture

Create a new package:

```text
src/mypyskindose/input_adapters/
  __init__.py
  registry.py
  models.py
  tabular_loader.py
  normalized_json.py
  dicom_rdsr.py
  radimetrics.py
  dosetrack.py
```

### `models.py`

Define lightweight dataclasses for adapter results:

```python
@dataclass
class InputAdapterResult:
    normalized_data: pd.DataFrame
    raw_data: pd.DataFrame | None
    source_type: str
    schema_name: str
    provenance: dict[str, Any]
    warnings: list[str]
```

Optional intermediate model:

```python
@dataclass
class ParsedEventTable:
    parsed_data: pd.DataFrame
    source_type: str
    schema_name: str
    column_map: dict[str, str]
    unit_conversions: dict[str, str]
    warnings: list[str]
```

### `registry.py`

Expose a small adapter registry:

```python
def read_and_normalize_input(
    file_path: str | Path | None,
    settings: PyskindoseSettings,
    *,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
) -> InputAdapterResult:
    ...
```

Routing rules:

| Suffix | Default route |
|---|---|
| `.dcm`, `.dicom`, no recognized suffix | DICOM RDSR adapter |
| `.json` | normalized JSON adapter |
| `.csv` | tabular adapter with comma delimiter |
| `.tsv` | tabular adapter with tab delimiter |
| `.xlsx`, `.xlsm` | tabular Excel adapter |

### `tabular_loader.py`

Implement generic tabular reading only:

- `read_csv(path, delimiter=',')`
- `read_tsv(path, delimiter='\t')`
- `read_excel(path, sheet_name=0)`
- standard cleanup: strip column names, drop entirely empty rows, preserve original column order in provenance.

### Source-specific adapters

Each source adapter should own:

- required columns
- optional columns
- column aliases
- unit conversions
- derived columns
- source-specific validation
- emitted warnings

Initial schemas:

1. `normalized`
   - Input already uses MyPySkinDose normalized columns (`Ap1`, `Ap2`, `DSD`, `DSI`, `K_IRP`, `kVp`, etc.).
   - Goes straight to `analyze_data()` after validation.

2. `radimetrics`
   - Adapt from the `dhen2714/PySkinDose` prototype.
   - Start with Siemens AXIOM-Artis support only if that is the only validated mapping.
   - Require explicit schema selection until enough real exports exist for safe detection.

3. `dosetrack`
   - Adapt from the `dhen2714/PySkinDose` prototype.
   - Support XLSX first; CSV/TSV can work if users export the same columns from Excel.
   - Validate manufacturer/model mapping before normalization.

4. `generic_rdsr_like`
   - A schema for tables whose columns already match the raw parsed RDSR names used by `rdsr_normalizer()`.

## Public API changes

### Option A: extend `main()` minimally

```python
def main(
    file_path: str | Path | None = None,
    settings: str | dict | PyskindoseSettings | None = None,
    *,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
):
    ...
```

This is user-friendly but adds more responsibility to `main()`.

### Option B: add a new explicit input helper

```python
def analyze_input_file(
    file_path: str | Path,
    settings: str | dict | PyskindoseSettings,
    *,
    input_schema: str | None = None,
    sheet_name: str | int = 0,
    output_format: str = "dict",
) -> dict | str | None:
    ...
```

This keeps `main()` mostly backward compatible while providing a clearer API for tabular imports.

### Recommendation

Implement Option B first, then let `main()` call the same registry internally once the adapter behavior is stable.

## CLI changes

Add optional arguments:

```bash
python -m mypyskindose \
  --file-path exported_events.csv \
  --settings settings.json \
  --input-schema radimetrics

python -m mypyskindose \
  --file-path dose_track_export.xlsx \
  --settings settings.json \
  --input-schema dosetrack \
  --sheet-name "Event Data"
```

Suggested flags:

- `--input-schema {auto,normalized,generic_rdsr_like,radimetrics,dosetrack}`
- `--sheet-name SHEET`
- `--input-preview-only` to print detected columns, missing required columns, and unit assumptions without calculating dose.

## GUI changes

In the upload step:

- Accept `.dcm`, `.json`, `.csv`, `.tsv`, `.xlsx`, `.xlsm`.
- Add a source selector:
  - Auto-detect
  - Normalized MyPySkinDose table
  - Raw RDSR-like table
  - Radimetrics export
  - DoseTrack export
- For Excel, add a sheet selector after upload.
- Show an import preview with:
  - detected schema
  - missing/extra columns
  - unit conversions
  - first 10 normalized events
  - warnings requiring user confirmation before dose calculation.

## Validation requirements

Every adapter must validate at least:

- required source columns exist
- required internal columns exist after mapping
- numeric columns parse cleanly or report row-level failures
- source units are converted to PySkinDose expectations
- distances are positive and plausible
- `kVp` is non-negative and zero rows are handled consistently with `remove_invalid_rows`
- `K_IRP` / reference point dose has the expected unit and scale
- field size can be determined directly or derived with documented formulas
- manufacturer/model can be mapped to normalization settings or a safe fallback is selected explicitly

## Testing plan

1. Add small synthetic fixture files under `tests/fixtures/tabular_inputs/`:
   - `normalized_events.csv`
   - `normalized_events.tsv`
   - `normalized_events.xlsx`
   - `radimetrics_axiom_artis.csv`
   - `dosetrack_siemens.xlsx`
2. Unit-test every loader and schema mapper.
3. Add round-trip tests comparing equivalent DICOM-derived normalized JSON vs CSV/TSV/XLSX normalized table inputs.
4. Add failure tests for missing columns, wrong units, invalid numeric cells, unknown model, ambiguous schema, and unsupported sheets.
5. Add one end-to-end smoke test using `analyze_input_file()` and a small normalized fixture.

## Implementation phases

### Phase 1 — normalized tabular input

- Add generic CSV/TSV/XLSX loaders.
- Add `normalized` schema validation.
- Add API and CLI path for normalized tabular files.
- Add tests and documentation.

This phase unlocks users who can export/prepare MyPySkinDose-normalized event tables.

### Phase 2 — generic raw RDSR-like tabular input

- Add schema for columns matching `rdsr_parser()` output.
- Run through existing `rdsr_normalizer()`.
- Add validation and fixtures.

### Phase 3 — Radimetrics adapter

- Port/refactor the `RADIMETRICS2PSD` mapping from the `dhen2714/PySkinDose` fork.
- Document all unit conversions.
- Limit to validated models first.
- Add fixtures and error messages tailored to Radimetrics exports.

### Phase 4 — DoseTrack adapter

- Port/refactor the `DOSETRACK2PSD` mapping from the `dhen2714/PySkinDose` fork.
- Add XLSX sheet handling.
- Validate Siemens and Philips paths separately.
- Add fixtures and documentation.

### Phase 5 — GUI import workflow

- Extend upload accepted formats.
- Add schema and sheet selectors.
- Add preview/validation UI.
- Preserve provenance in exported JSON/HTML reports.

## Open questions

- Which Radimetrics export templates are actually used by intended users?
- Are exported values cumulative per event, cumulative per study, or event-local for every source?
- Do exported tables include enough geometry for all clinical use cases, especially table rotations and detector rotation?
- Should XLSX support be a core dependency or `mypyskindose[excel]`?
- Should adapter mappings be Python modules only, or should column maps live in editable JSON/YAML files for site customization?

## Acceptance criteria

The feature is complete when:

- Users can run a dose calculation from `.csv`, `.tsv`, and `.xlsx` normalized event tables.
- At least one Radimetrics CSV schema and one DoseTrack XLSX schema have validated adapters or are explicitly documented as unsupported until fixtures are available.
- The CLI, Python API, and GUI share the same adapter registry.
- Validation errors identify missing/invalid columns by name and include actionable remediation text.
- Output includes tabular-input provenance and adapter warnings.
- Tests cover success and failure paths for each supported format and schema.
