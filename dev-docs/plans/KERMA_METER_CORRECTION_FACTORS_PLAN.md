# Kerma-Meter Correction Factors (per equipment × tube)

Status: **Active — not started**
Plan type: Execution plan (input data & calculation)
Created: 2026-07-26
Owner: maintainer
Related: [TO_DO.md](../TO_DO.md) — *Input Data And Calculation*; [INPUT_DATA_FLOW_AND_OFFSETS.md](../INPUT_DATA_FLOW_AND_OFFSETS.md); [VENDOR_COORDINATE_SYSTEMS.md](../VENDOR_COORDINATE_SYSTEMS.md); [TABULAR_RDSR_INPUT_PLAN.md](TABULAR_RDSR_INPUT_PLAN.md).

---

## 1. Objective

Apply a user-supplied **kerma-meter correction factor** (CF) to each irradiation event so that the air kerma (K_IRP) used for dose calculation reflects the *true* air kerma the reporting unit would have produced, instead of the unit's reported (uncorrected) kerma.

Definition (for documentation, UI, and export):

> **CF = (real measured dose) / (unit reported dose)**

where "real measured dose" is the **NIST-traceable (or national-standard-traceable) reference air kerma** assigned
to the unit+tube during an external QC/ion-chamber calibration against a reference standard (i.e. an independent
measurement made outside the system's self-reporting meter), not the unit's own reported value. Equivalently, CF
is the multiplicative calibration that converts the unit's reported (uncalibrated) air kerma into the
laboratory-traceable air kerma for that individual tube.

A reported `K_IRP` is multiplied by CF to obtain the corrected air kerma:

```
K_IRP_corrected[ev] = K_IRP_reported[ev] × CF[ev]
```

CF is looked up by **specific individual unit** (not just model) **and** tube (A/B / single-plane). When the specific unit cannot be determined or is not present in the lookup table, **CF = 1.0** (no correction, dose unchanged) — identical fail-soft behavior to the existing `k_tab` model/plane fallback in `corrections.py:254`.

This is a **calibration correction to the meter/reporting chain**, conceptually distinct from the physics corrections (inverse-square, backscatter, medium, table attenuation) already applied in `corrections.py` and `calculate_dose/`.

## 2. Background / current behavior

- Per-event air kerma is stored in `data_norm[KEY_NORMALIZATION_AIR_KERMA]` (`"K_IRP"`, mGy), set in
  `rdsr_normalizer.py:345` from `data_parsed.DoseRP_Gy * 1000`.
- Dose is accumulated in
  `add_correction_and_event_dose_to_output.py:90` as
  `event_dose[hits] += normalized_data.K_IRP[event]`, then multiplied by the physics correction factors.
- `calculate_irradiation_event_result.py:152` copies the per-event kerma to `output[c.OUTPUT_KEY_KERMA][ev]`.
- Per-event tube A/B is already available as `acquisition_plane` (`"Single Plane" | "Plane A" | "Plane B"`), normalized at
  `rdsr_normalizer.py:238` from `AcquisitionPlane` (DICOM concept per event).
- Per-unit identification is **currently NOT captured**: `rdsr_parser.py:121` only stores
  `Manufacturer` and `ManufacturerModelName` per event. Station name / device serial number — both present on
  example RDSRs (see §5) — are dropped.
- The closest existing precedent is `k_tab` (`corrections.py:193`), which keys on **model × acquisition_plane**
  and fails soft to `1.0` for unknown devices. CF uses **individual unit × tube**, not model.

## 3. Key terminology

| Term | Meaning |
|---|---|
| Equipment | One specific physical X-ray unit (room). Identified by `StationName` (DICOM `0008,1010`) and/or `DeviceSerialNumber` (DICOM `0018,1000`). May also be tabulated by a user-chosen custom station label for tabular inputs that lack DICOM-level station identifiers. |
| Tube | A specific radiation source on the equipment (single-plane stations have one tube; biplane stations have A and B). Per event, captured by the `acquisition_plane` ("Single Plane" / "Plane A" / "Plane B"). |
| Model | `ManufacturerModelName` (DICOM `0008,1090`). A *model* may correspond to many individual units; CF is per-unit, never per-model. |
| Meter correction factor (CF) | `CF = (real measured dose) / (unit reported dose)`. Multiplied into the per-event K_IRP before physics corrections. Dimensionless. `CF = 1.0` means no correction. |

## 4. Acceptance criteria

1. Per-event air kerma used for dose is `K_IRP_reported[ev] × CF[ev]`, where CF is resolved per (equipment, tube).
2. When equipment or tube cannot be determined, or the (equipment, tube) pair is absent from the supplied
   lookup table, `CF = 1.0` (dose numerically unchanged) and a *per-event*/summary warning is logged, mirroring
   the existing `k_tab` warning style (`corrections.py:303`).
3. The corrected K_IRP (post-CF) is the value carried through dose accumulation, exported in the per-event kerma
   field, and reported in PSD — i.e. CF happens **before** inverse-square / backscatter / medium / table
   corrections, exactly once, with no double-application.
4. CF is surfaced as a first-class per-event correction factor in `output` and in the Rich-Export corrections table
   (separate column from `k_tab`/`k_med`/`k_bs`), with units "= dimensionless" and the resolved (equipment, tube)
   key logged next to it.
5. Two input mechanisms are supported, switchable via settings:
   - **Lookup file**: a CSV/TSV/XLSX (or simple JSON) table supplied at runtime; or
   - **Interactive prompt** (GUI only): before calculation, the GUI collects a CF for each detected
     (equipment, tube) and offers a default of `1.0`.
6. CLI: a `--kerma-meter-correction-file PATH` flag and a `--kerma-meter-correction-mode
   {file,prompt-off}` flag exist; non-interactive runs that lack a file fall back to CF = 1.0 with a warning
   (never block).
7. The original uncorrected K_IRP is retained in the **existing** `output[c.OUTPUT_KEY_KERMA]` field (unchanged for
   dict-mode consumers — no silent behavior break); the corrected value lives in a **new**
   `output[c.OUTPUT_KEY_KERMA_CORRECTED]` field, so the correction is auditable/reversible in exports and tests.
8. Unit and tabular inputs parse station identifiers cleanly and never PII-leak (station names can be free text;
   apply the project's runtime privacy rule — no raw identifiers in logs/exports beyond what the user has already
   chosen to load; see `PRIVACY_AND_SENSITIVE_ASSETS.md`).
9. Tests cover: unknown equipment → CF=1.0; per-event tube resolution on biplane data; file reload; prompt mode;
   CSV/TSV/XLSX/JSON schema acceptance; single-plane vs Plane A/B; and end-to-end PSD parity with CF=1.0.

## 5. Equipment identity reconnaissance (already verified on `example_data/RDSR/*.dcm`)

| File | Manufacturer | Model | StationName | DeviceSerialNumber |
|---|---|---|---|---|
| fake_scanner.dcm | FakeCorp | Mystery-X | AXIS01475 | 146278 |
| philips_allura_clarity_u104.dcm | Philips | Allura Clarity | INR Lab | 722013-362 |
| philips_allura_clarity_u601.dcm | Philips | Allura Clarity | U601 | 722010-564 |
| siemens_axiom_artis.dcm | Siemens | AXIOM-Artis | AXIS01475 | 146278 |
| siemens_axiom_example_procedure.dcm | Siemens | AXIOM-Artis | ⟨missing⟩ | ⟨missing⟩ |

Findings:

- `StationName` (DICOM `0008,1010`) and `DeviceSerialNumber` (DICOM `0018,1000`) are **top-level** attributes on the
  RDSR dataset (one value per study, constant across events). They are reachable via `data_raw.StationName` /
  `data_raw.DeviceSerialNumber` in `rdsr_parser`.
- They are **sometimes missing** (e.g. `siemens_axiom_example_procedure.dcm`) — the plan must handle absence gracefully
  and still fall back to CF=1.0.
- `AcquisitionPlane` per event resolves to `Single Plane` / `Plane A` / `Plane B` on the example fixtures.
- Tabular adapters (DoseTrack, Radimetrics) expose an "Equipment Name" column; the DoseTrack adapter already infers
  `ManufacturerModelName` from it (`input_adapters/dosetrack.py:185`). For tabular inputs, station identity will
  typically be the **Equipment Name** combined with the AcquisitionPlane (plane code → A/B).

## 6. Equipment key design (resolution & precedence)

A composite key identifies "which unit + tube" an event belongs to, resolved by a **single fixed order**
(first non-empty wins). If nothing resolves, the event goes to CF=1.0. There is no configurable strategy — the
order is baked in to keep the model simple and predictable; the lookup table does the matching.

1. Explicit user-label override (`settings.kerma_meter_correction.explicit_label`, a single string) — when set,
   every event gets this label as its equipment identity (useful for reprocessing an ambiguous export under a
   deliberate unit name).
2. `DeviceSerialNumber` (most stable per-unit identifier) when present.
3. `StationName` when present.
4. **Tabular fallback (per the user's requirement)** — when no DICOM station or serial is available (the normal
   case for CSV/TSV/XLSX exports, which carry no DICOM top-level attributes), resolve the equipment identity from
   the tabular column that names the unit. Specifically, in this order: DoseTrack's **"Equipment Name"** sentinel
   column (currently consumed by `input_adapters/dosetrack.py:185` to infer `ManufacturerModelName` and then
   *dropped* at `:206` — Phase 0 must persist its value as the per-unit identity *before* it is dropped),
   Radimetrics' **"Device"** column, then generic lowercase candidates `equipment`, `equipment name`, `station name`
   per `column_mapper.py:34`. Only the column *values* populate the equipment key; the existing model inference
   stays as a separate side effect for `ManufacturerModelName`.
5. Empty → unresolved → CF=1.0.

The effective event key is `(equipment_label, acquisition_plane_normalized)` where
`acquisition_plane_normalized ∈ {"single", "A", "B"}` (collapse "Single Plane" → "single"; keep "A"/"B" suffix).
The lookup table is queried with this `(equipment, tube)` pair. There is **no wildcard row matching**: an absent
`(equipment, tube)` row resolves to `default_factor` (1.0 by default), so the unresolved case and the
"per-model fallback" case collapse to one explicit knob.

Rationale: `DeviceSerialNumber` is more globally unique than `StationName` (which can be a friendly room label like
`"INR Lab"`). The order is fixed so the lookup-table author doesn't need to reason about per-run strategy settings.
For tabular exports — which never carry DICOM station/serial — the **"equipment"-style column is the *primary*
per-unit identifier**, not a last-resort hack: it is the only per-unit signal a tabular row has, and it must be
captured rather than collapsed into the model name as the adapters do today.

## 7. Lookup-table schema

Deliberately minimal and human-editable. Columns:

| Column | Type | Required | Notes |
|---|---|---|---|
| `equipment` | str | yes | Station name, device serial, or a user-defined label. Case-insensitive; whitespace-trimmed. |
| `tube` | str | yes | `"single"`, `"A"`, `"B"`. No wildcard sentinel. |
| `correction_factor` | float | yes | CF. No wildcard fallback row; an absent `(equipment, tube)` row
       resolves to `settings.kerma_meter_correction.default_factor` (1.0 by default). |
| `notes` | str | no | Free-text provenance / measurement date (never exposed as PHI; user responsibility).
| `source` | str | no | Optional short citation of the QC measurement (e.g. "QC 2026-06"). |

Example rows:

```csv
equipment,tube,correction_factor,notes,source
U601,single,1.03,Annual QC 2026-06,site QC lab
722013-362,A,0.97,Water calorimetry 2026-03,NMRO
722013-362,B,1.02,Water calorimetry 2026-03,NMRO
```

Accepted formats: `.csv`, `.tsv`, `.xlsx` (first sheet by default; sheet name configurable), and a JSON of the
form `{"factors": [{"equipment": "U601", "tube": "single", "correction_factor": 1.03}, ...]}`. Selection reuses the
existing `input_adapters/tabular_loader.py` machinery where possible; JSON is a thin additional loader.

Validation: non-empty required columns; `correction_factor` parses to finite float > 0 (warn on suspicious ranges, but
only reject ≤ 0 or NaN); duplicate `(equipment, tube)` rows → first wins + warning. Invalid files fail fast with a
clear message; non-existent optional fields do not.

## 8. Settings

Add to `PyskindoseSettings` (`settings/pyskindose_settings.py`) and `settings_example.json`:

```jsonc
"kerma_meter_correction": {
  "enable": false,
  "mode": "file",                 // "file" | "prompt"
  "file": null,                   // str | Path | null
  "file_sheet": null,             // optional XLSX sheet name
  "default_factor": 1.0,          // used for unresolved events and prompt-prefill
  "explicit_label": null,         // str | null — force one equipment label for this run
  "prompt_at_calc": false         // GUI only: open a CF collection modal before calculate_dose
}
```

Defaults are chosen so a freshly-loaded settings JSON (no key) is **behavior-preserving**: `enable: false` → CF=1.0
everywhere, identical to today. Raising `enable: true` with no file and `mode: "file"` → CF=1.0 *with* a one-time
summary warning that the correction feature is enabled but no table was supplied (so the user doesn't silently
believe a correction was applied). The key-resolution order (§6) is **not configurable** — there are no
`key_strategy` or `--kerma-meter-key-strategy` knobs, by design (see §6 rationale).

CLI (`main.py`):

- `--kerma-meter-correction` (flag): enable the feature.
- `--kerma-meter-correction-file PATH`
- `--kerma-meter-correction-mode {file,prompt}` (prompt only meaningful in `--mode gui`).
- `--kerma-meter-explicit-label TEXT`

`prompt_at_calc` is **GUI-only and defaults to `false`**: non-interactive / CLI / scripted workflows must never
block on a prompt; enabling it only affects GUI runs initiated from the Calculate tab.

## 9. Implementation phases

Each phase is independently shippable and leaves behavior unchanged when the feature is disabled.

### Phase 0 — Per-unit parsing (foundation; no behavior change)

- Extend `rdsr_parser.py:_parse_irradiation_event` to also capture `StationName` and `DeviceSerialNumber` from the
  top-level `data_raw` dataset (add `KEY_RDSR_STATION_NAME = "StationName"` and
  `KEY_RDSR_DEVICE_SERIAL = "DeviceSerialNumber"` to `constants.py`). Missing attributes store as `None`, not crash.
- Normalize into `data_norm` (new keys `KEY_NORMALIZATION_STATION_NAME = "station_name"`,
  `KEY_NORMALIZATION_DEVICE_SERIAL = "device_serial"`) in `rdsr_normalizer._normalize_machine_parameters`.
  These keys are reserved for the CF feature and **do not collide** with any current `KEY_NORMALIZATION_*`
  column today (verified: the only `*_NAME` column is `KEY_NORMALIZATION_MODEL_NAME = "model"`, distinct from
  `station_name`). If Phase 0 introduces a future collision risk, prefer appending a `_cf` suffix over renaming
  the existing column; collisions must fail typecheck (`basedpyright`) rather than silently overwrite.
- Tabular adapters: when station name / device serial are absent (the usual tabular case — no DICOM top-level
  attrs), the **"equipment" column becomes the per-unit identifier** and must be preserved into a
  `station_name`-equivalent column *before* any existing step drops it. Concretely:
  - **Generic** (`column_mapper.py`): add an "equipment" candidate list targeted at the per-unit column
    (distinct from the model column at `column_mapper.py:34`); first source-specific equipment-name candidate
    wins. Also recognize plain `equipment` and `equipment name`.
  - **DoseTrack** (`dosetrack.py:185`–`:206`): today the `_dt_equipment_name` sentinel is read only to derive
    `ManufacturerModelName`, then `data_df.drop(columns=["_dt_equipment_name"])` discards it. Persist its value
    into the new `station_name`/`device_serial`-equivalent column *before* the drop so the per-unit key survives.
  - **Radimetrics** (`column_mapper.py:70` lists `"device"` for `ManufacturerModelName`): the "Device" column is
    reused to infer the model; if it is the only per-unit signal available, copy it to the station-identity column
    rather than collapsing to model. Where the model column and a separate equipment/unit column both exist, keep
    the unit-specific one for identity and the model one for `ManufacturerModelName`.
  - **Generic RDSR tabular** (`generic_rdsr.py:57` "device model"/`"device"`): same split — the "device" column
    alone is treated as a per-unit identity when no DICOM station/serial is present.
- Add unit + characterization tests for missing vs present identifiers (DICOM RDSR with present/absent station and
  serial; each tabular adapter with/without an "equipment"-style column). **No dose change yet.**

### Phase 1 — Correction-factor engine (pure function, CF=… by key)

New module `src/mypyskindose/kerma_correction.py`:

```python
@dataclass(frozen=True)
class KermaMeterCorrection:
    factors: list[float]                # one per event, CF
    resolved_keys: list[tuple[str | None, str]]  # (equipment_label, tube) per event
    unresolved_event_indices: list[int]
    table_metadata: dict | None         # provenance, sheet name, etc.

def resolve_correction_keys(
    data_norm: pd.DataFrame,
    key_strategy: str,
    explicit_label: str | None,
) -> list[tuple[str | None, str]]: ...

def load_correction_table(path, sheet) -> dict[tuple[str, str], float]: ...

def resolve_correction_factors(
    data_norm: pd.DataFrame, table: dict | None, *, key_strategy, explicit_label, default_factor
) -> KermaMeterCorrection: ...
```

Semantics follow §6 and mirror `corrections.calculate_k_tab`'s warning style (per-event index lists via
`grid_interp.format_event_indices`). Lookups are exact-match on `(equipment, tube)`; an absent row resolves to
`default_factor` (1.0 by default). There is **no wildcard row**.
No dose math here — pure resolution. Fully unit-testable without a GUI or RDSR run.

### Phase 2 — Wire into dose pipeline (CF applied exactly once, before physics corrections)

- In the per-event dose accumulation, multiply `normalized_data.K_IRP[event]` by `factors[event]` at the point the
  kerma enters `event_dose` (`add_correction_and_event_dose_to_output.py:90`) — **once**, on the *internal* value
  used for dose accumulation only.
- **Backward compatibility (dict-mode consumers):** the existing `output[c.OUTPUT_KEY_KERMA]` field is **left
  as the untouched reported K_IRP** (the value stored today). The corrected value lives in a **new**
  `output[c.OUTPUT_KEY_KERMA_CORRECTED]` field. This is a purely additive change — dictionary consumers who already
  read `OUTPUT_KEY_KERMA` keep getting exactly what they get today; only the dose map and PSD silently move to
  the corrected air kerma when CF≠1. Call this out in `CHANGELOG.md` (under the release that ships CF) and in
  `CODEBASE_OVERVIEW.md`'s output-fields table, so consumers who want the dose-relevant value can switch to
  `OUTPUT_KEY_KERMA_CORRECTED`.
- Add `output[c.OUTPUT_KEY_CORRECTION_KERMA_METER][ev] = factors[event]` plus `resolved_keys` to support the
  corrections table (Rich Export) and tests.
- Gate everything behind `settings.kerma_meter_correction.enable`; when disabled, `factors` is all-ones and
  `OUTPUT_KEY_KERMA_CORRECTED == OUTPUT_KEY_KERMA` (both equal to the reported value).

### Phase 3 — CLI + Settings wiring

- Add the settings dataclass fields (§8) with validation (factor clamps, mode ∈ {file,prompt}).
- Wire CLI flags to settings in `main.py`.
- Add an "enabled but no table" summary warning when `mode == "file"` and `file is None`.

### Phase 4 — GUI prompt + file picker

- New helper under `src/mypyskindose/gui/tabs/` (or extend existing Settings section): a "Kerma-meter correction"
  card with: enable toggle, mode selector (file / prompt), file picker, key strategy selector, explicit-label
  optional text field.
- Pre-calc prompt (`prompt_at_calc: true`): before `calculate_dose`, enumerate the `(equipment, tube)` pairs
  detected in the loaded exam(s) and present a small table with a per-row float input, prefilled with
  `default_factor` (and with values from the loaded file if provided). Confirm applies the in-memory table for
  this session. Cancel keeps CF=1.0 (consistent with the "non-blocking, never fail-open" philosophy).
- Use a small new `ui_copy.json` / `help_registry.json` entry for help text; mirror help from
  `docs/source/gui_help/` per the GUI help rules.

### Phase 5 — Rich export & results UI

- Add CF to the Results-tab corrections table and to the Rich-Export corrections section (PDF/DOCX/HTML/XLSX); show
  `K_IRP (reported)` and `K_IRP (corrected)` columns per event where space permits.
- Record the resolved equipment label(s) and the table source in the export metadata (provenance only; never log
  raw station names beyond what the user already loaded — see §12).

### Phase 6 — Docs, glossary, feature matrix

- Update `dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md`, `CODEBASE_OVERVIEW.md`, `FEATURE_INVENTORY.md`,
  `VENDOR_COORDINATE_SYSTEMS.md` (note: DICOM station/serial lives at study level, not event level), `AGENTS.md`
  run-modes/output/phantom table if needed.
- Add glossary term "Kerma-meter correction factor" to `dev-docs/glossary.json`.
- Add a `feature_doc_matrix.json` row mapping the feature to its code/tests/docs/help.
- Archive this plan under `dev-docs/plans/archive/` once §4 acceptance passes and update `dev-docs/index.md`.

## 10. Phase ordering & dependencies

```
Phase 0 (parsing) ──┬─► Phase 1 (resolve) ──► Phase 2 (wire to dose) ──► Phase 3 (CLI/Settings)
                    └────────────────────────────────────────────────────► Phase 4 (GUI)
                                                                                      ► Phase 5 (export)
                                                                                      ► Phase 6 (docs)
```

Phases 0–3 are the minimum to ship the feature headlessly (CLI). 4–5 ship the user-facing experience. Each phase
keeps the prior behavior unchanged when disabled.

## 11. Out of scope (explicit)

- Per-frame adjustment, dynamic CF (e.g. CF as a function of kVp / HVL) — CF is a single calibration multiplier per
  (equipment, tube). Future hook: store optional kVp bands in the table; not in this plan.
- Inverse-calibration propagation into uncertainty estimates / confidence intervals.
- Vendor-controlled CF tables downloaded from a remote server — only local files / in-run input.
- Changing how `k_tab` resolves unknown models (CF and `k_tab` are independent: `k_tab` stays model/plane-keyed,
  CF is unit/tube-keyed).
- Automated population of CF from a QC database — manual entry only.

## 12. Risks & mitigations

| Risk | Mitigation |
|---|---|
| User mis-keys the table (wrong serial) → wrong dose applied silently | Per-event unresolved warnings + corrections table clearly shows resolved (equipment, tube, CF); prompt mode shows the resolved key next to each input. Acceptance §4.7 keeps reported K_IRP auditable. |
| Station names containing PII shipped in exports | Concrete export/log rules in §14: per-event tables never carry the station/serial column; only one-block provenance metadata lists the matched equipment labels, only when the user supplied a CF file; INFO logs use counts only. |
| Double-application of CF (in K_IRP and in corrections) | Apply exactly once at the K_IRP entry point; tests assert `OUTPUT_KEY_KERMA_CORRECTED == OUTPUT_KEY_KERMA × CF`. Existing tests run with CF=1.0 to preserve parity. |
| Different vendors / events setting `acquisition_plane` inconsistently ("Single Plane" on a biplane-station's single-plane acquisition) | Key normalization is on the event's plane string only — Tube A vs B is what matters; if a station has both A and B events but only an A CF supplied, B events resolve to `default_factor` (=1.0 by default). There is no wildcard row. |
| **Silent behavior break for dict-mode consumers** (the reviewer's #6) | **Reversed Phase 2 polarity:** `OUTPUT_KEY_KERMA` keeps reporting the *uncorrected* value (today's behavior); the *corrected* value is in a **new** `OUTPUT_KEY_KERMA_CORRECTED` field. CHANGELOG and `CODEBASE_OVERVIEW.md` call this out; zero existing consumers change behavior. |
| **Phase 0 adapter pipeline changes** (highest-risk phase, per reviewer #5) | New normalized column keys `station_name` / `device_serial` do **not** collide with any current `KEY_NORMALIZATION_*` (only `*_NAME` key is `model`). DoseTrack: persist `_dt_equipment_name` into `station_name` *before* the existing `drop(columns=["_dt_equipment_name"])` at `dosetrack.py:206`; the dropped sentinel stays dropped after the copy, so downstream consumers see no behaviour change. Any future name collision must trip `basedpyright` (typed dict keys), not silently overwrite. |
| Backwards compatibility of saved settings/example JSON | New settings block defaults preserve current behavior; `settings_example.json` only gets a commented block; old JSONs continue to load (absent block == disabled). |
| Tabular inputs without plane codes | DoseTrack's integer plane code already maps to "Single Plane" / "Plane A" / "Plane B" (`dosetrack.py:141`). Other adapters default to "Single Plane" — same as today; CF then keys as `single`. |

## 13. Test plan

- `tests/unittests/test_kerma_correction.py`: pure resolver tests (fixed key precedence serial → station → tabular
  "equipment" column → unresolved; missing IDs; deterministic factor application; parity `factors == [1.0] * n`
  when disabled or table empty; absence of wildcard matching).
  deterministic factor application, and parity `factors == [1.0] * n` when disabled or table empty).
- `tests/unittests/test_rdsr_parser_station.py`: assert `StationName` / `DeviceSerialNumber` parsing for each example
  RDSR; `None` when missing.
- `tests/unittests/test_dose_kerma_correction.py` (calculation): a small synthetic normalized frame where
  CF=1.0 reproduces the current PSD exactly, and CF≠1.0 scales K_IRP linearly into the dose map without affecting
  the physics corrections.
- `tests/gui`: prompt modal smoke (collect CFs for `(equipment, tube)` set, apply does not block calculation).
- Characterization: load all `example_data/RDSR/*.dcm` end-to-end with CF=1.0 and assert byte-identical PSD/dose map
  to the current main-branch output (guards against accidental double-application or K_IRP mutation).

## 14. Privacy / harness notes

Station names and device serial numbers are operator-controlled identifiers, not patient PHI, but they can
indirectly identify a site/room and are user-loaded (not filtered by the project). Concrete handling rules:

- **Logging:**
  - At INFO/WARNING: never print full raw station/serial strings. Use summary forms only: counts and buckets,
    e.g. `"kerma-meter correction: 3 unique equipment keys resolved, 2 unresolved → CF=1.0"`.
  - Per-event raw strings appear only at DEBUG, gated behind the standard `logging` module (never `print`),
    and only when the user explicitly raised verbosity (default runtime stays INFO).
- **Exports (HTML/PDF/DOCX/XLSX):**
  - **Body/event tables go only by index** (the per-event corrections table already keys by event index). Do
    **not** add a "Station" or "Serial" column to per-event tables.
  - The resolved equipment label appears **only in export metadata**, only as a single-block list
    ("Equipment matched in CF table: U601, 722013-362"), and only when the user has loaded a CF file
    (`mode == "file"`). The provenance block notes "Station/serial values are user-loaded; site responsibility
    for downstream sharing."
  - File-name and on-disk paths in exports keep the existing redaction policy (no source RDSR filename).
- **CF table files:** treat as user-supplied data; do **not** commit example CF tables with real-site station
  names (use placeholders like `U601` / `722013-362` or `<site-label>`). The in-repo example fixture, if any,
  uses synthetic station labels of the form `unit-NN` so the schema is self-explanatory without leaking a
  real identifier.
- **Tabular input:** the existing identifier-redaction logic on tabular columns is unchanged; the new
  `station_name`-equivalent column inherits the same logging redaction (no full value at INFO).
- **Harness:** keep new source files under the ~800-line modularity ceiling; keep `kerma_correction.py` cohesive.
  Run the harness checks called out in `HARNESS_ENGINEERING.md` (ruff, basedpyright, pytest, doc-freshness,
  help-registry, ui-copy) in the PR; add a UI-copy entry for any new user-visible CF string.

## 15. Open questions

- Do we want a per-model "default CF" row in the table (e.g. apply a model-level calibration to all units of that
  model unless overridden)? Current design treats model as out-of-scope; reconsider only if sites ask.
- Should prompt-mode persist entered CFs to a local per-station cache (gitignored) so the next run prefills them?
  Convenience vs. staleness tradeoff; defer to a follow-up.
- Naming: "Kerma-meter correction factor" vs industry terms "kerma calibration factor" / "K_AP correction".
  Glossary should alias all three; the settings/UI label uses "Kerma-meter correction factor".