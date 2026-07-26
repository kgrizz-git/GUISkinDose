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
7. The original uncorrected K_IRP is **also** retained in `output` (e.g. `kerma_reported`), so the correction is
   auditable/reversible in exports and tests.
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

A composite key identifies "which unit + tube" an event belongs to, resolved with the following precedence
(first non-empty wins). If nothing resolves, the event goes to CF=1.0.

1. Explicit user-label override (settings) — exact-match label the user types in the GUI/passes via setting.
2. `DeviceSerialNumber` (most stable per-unit identifier) when present.
3. `StationName` when present.
4. Tabular-only escape hatch: the raw "Equipment Name" / "device" column when neither DICOM field is available.
5. Empty → unresolved → CF=1.0.

The effective event key is `(equipment_label, acquisition_plane_normalized)` where
`acquisition_plane_normalized ∈ {"single", "A", "B"}` (collapse "Single Plane" → "single"; keep "A"/"B" suffix).
The lookup table is queried with this `(equipment_label, tube)` pair. Wildcard rows (`equipment_label="<any>"` or
`tube="<any>"`) are supported as user-authored fallbacks (lower precedence than exact match) so a site can ship a
per-model default and override specific units.

Rationale: `DeviceSerialNumber` is more globally unique than `StationName` (which can be a friendly room label like
`"INR Lab"`). Both are offered because sites may publish lookup tables keyed the way their physicists maintain them.

## 7. Lookup-table schema

Deliberately minimal and human-editable. Columns:

| Column | Type | Required | Notes |
|---|---|---|---|
| `equipment` | str | yes | Station name, device serial, or a user-defined label. Case-insensitive; whitespace-trimmed. |
| `tube` | str | yes | `"single"`, `"A"`, `"B"`, or `"<any>"`. |
| `correction_factor` | float | yes | CF. Default-fallback rows may be `<any>`; exact match wins over `<any>`. |
| `notes` | str | no | Free-text provenance / measurement date (never exposed as PHI; user responsibility). |
| `source` | str | no | Optional short citation of the QC measurement (e.g. "QC 2026-06"). |

Example rows:

```csv
equipment,tube,correction_factor,notes,source
U601,single,1.03,Annual QC 2026-06,site QC lab
722013-362,A,0.97,Water calorimetry 2026-03,NMRO
722013-362,B,1.02,Water calorimetry 2026-03,NMRO
<any>,<any>,1.0 default fallback if neither header row matches,,
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
  "key_strategy": "serial_then_station",  // "serial_then_station" | "station_then_serial" | "label_only"
  "explicit_label": null,         // str | null — force an equipment label for this run
  "prompt_at_calc": true          // GUI: open a CF collection modal before calculate_dose
}
```

Defaults are chosen so a freshly-loaded settings JSON (no key) is **behavior-preserving**: `enable: false` → CF=1.0
everywhere, identical to today. Raising `enable: true` with no file and `mode: "file"` → CF=1.0 *with* a one-time
summary warning that the correction feature is enabled but no table was supplied (so the user doesn't silently
believe a correction was applied).

CLI (`main.py`):

- `--kerma-meter-correction` (flag): enable the feature.
- `--kerma-meter-correction-file PATH`
- `--kerma-meter-correction-mode {file,prompt}` (prompt only meaningful in `--mode gui`).
- `--kerma-meter-key-strategy {serial_then_station,station_then_serial,label_only}`
- `--kerma-meter-explicit-label TEXT`

## 9. Implementation phases

Each phase is independently shippable and leaves behavior unchanged when the feature is disabled.

### Phase 0 — Per-unit parsing (foundation; no behavior change)

- Extend `rdsr_parser.py:_parse_irradiation_event` to also capture `StationName` and `DeviceSerialNumber` from the
  top-level `data_raw` dataset (add `KEY_RDSR_STATION_NAME = "StationName"` and
  `KEY_RDSR_DEVICE_SERIAL = "DeviceSerialNumber"` to `constants.py`). Missing attributes store as `None`, not crash.
- Normalize into `data_norm` (new keys `KEY_NORMALIZATION_STATION_NAME = "station_name"`,
  `KEY_NORMALIZATION_DEVICE_SERIAL = "device_serial"`) in `rdsr_normalizer._normalize_machine_parameters`.
- Tabular adapters: ensure the "Equipment Name"/"device" column is preserved into a `station_name`-equivalent
  column when present (DoseTrack already surfaces it; Radimetrics may need a column mapping).
- Add unit + characterization tests for missing vs present identifiers. **No dose change yet.**

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
`grid_interp.format_event_indices`). Lookups are exact-match-first, then `<any>` fallback, else `default_factor`.
No dose math here — pure resolution. Fully unit-testable without a GUI or RDSR run.

### Phase 2 — Wire into dose pipeline (CF applied exactly once, before physics corrections)

- In the per-event dose accumulation, multiply `normalized_data.K_IRP[event]` by `factors[event]` at the point the
  kerma enters `event_dose` (`add_correction_and_event_dose_to_output.py:90`) — **once**.
- Keep the *reported* K_IRP in `output[c.OUTPUT_KEY_KERMA_REPORTED]` (new key) and store *corrected* in
  `output[c.OUTPUT_KEY_KERMA]` — note audit clarity: the existing kerma field becomes the corrected value used for
  dose; PSD and exports reference the corrected value. Document this in `OUTPUT_*` constants and `CODEBASE_OVERVIEW.md`.
- Add `output[c.OUTPUT_KEY_CORRECTION_KERMA_METER][ev] = factors[event]` plus `resolved_keys` to support the
  corrections table (Rich Export) and tests.
- Gate everything behind `settings.kerma_meter_correction.enable`; when disabled, `factors` is all-ones and
  `reported == corrected`.

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

## 8'. Phase ordering & dependencies

```
Phase 0 (parsing) ──┬─► Phase 1 (resolve) ──► Phase 2 (wire to dose) ──► Phase 3 (CLI/Settings)
                    └────────────────────────────────────────────────────► Phase 4 (GUI)
                                                                                      ► Phase 5 (export)
                                                                                      ► Phase 6 (docs)
```

Phases 0–3 are the minimum to ship the feature headlessly (CLI). 4–5 ship the user-facing experience. Each phase
keeps the prior behavior unchanged when disabled.

## 9'. Out of scope (explicit)

- Per-frame adjustment, dynamic CF (e.g. CF as a function of kVp / HVL) — CF is a single calibration multiplier per
  (equipment, tube). Future hook: store optional kVp bands in the table; not in this plan.
- Inverse-calibration propagation into uncertainty estimates / confidence intervals.
- Vendor-controlled CF tables downloaded from a remote server — only local files / in-run input.
- Changing how `k_tab` resolves unknown models (CF and `k_tab` are independent: `k_tab` stays model/plane-keyed,
  CF is unit/tube-keyed).
- Automated population of CF from a QC database — manual entry only.

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| User mis-keys the table (wrong serial) → wrong dose applied silently | Per-event unresolved warnings + corrections table clearly shows resolved (equipment, tube, CF); prompt mode shows the resolved key next to each input. Acceptance §4.7 keeps reported K_IRP auditable. |
| Station names containing PII shipped in exports | Treat station/serial as user-loaded data; the existing Rich-Export policy already defers sanitization to the user. Add a *short* de-identification note in the export metadata doc and ensure logs use truncated/summary form, not full raw strings. |
| Double-application of CF (in K_IRP and in corrections) | Apply exactly once at the K_IRP entry point; tests assert `corrected == reported × CF`. Existing tests run with CF=1.0 to preserve parity. |
| Different vendors / events setting `acquisition_plane` inconsistently ("Single Plane" on a biplane-station's single-plane acquisition) | Camera-ready key normalization is on the event's plane string only — Tube A vs B is what matters; if a station has both A and B events but only an A CF supplied, B events resolve to a `<any>` row or `default_factor` (=1.0 by default). Documented in-table. |
| Backwards compatibility of saved settings/example JSON | New settings block defaults preserve current behavior; `settings_example.json` only gets a commented block; old JSONs continue to load (absent block == disabled). |
| Tabular inputs without plane codes | DoseTrack's integer plane code already maps to "Single Plane" / "Plane A" / "Plane B" (`dosetrack.py:141`). Other adapters default to "Single Plane" — same as today; CF then keys as `single`. |

## 11. Test plan

- `tests/unittests/test_kerma_correction.py`: pure resolver tests (key precedence, `<any>` fallback, missing IDs,
  deterministic factor application, and parity `factors == [1.0] * n` when disabled or table empty).
- `tests/unittests/test_rdsr_parser_station.py`: assert `StationName` / `DeviceSerialNumber` parsing for each example
  RDSR; `None` when missing.
- `tests/unittests/test_dose_kerma_correction.py` (calculation): a small synthetic normalized frame where
  CF=1.0 reproduces the current PSD exactly, and CF≠1.0 scales K_IRP linearly into the dose map without affecting
  the physics corrections.
- `tests/gui`: prompt modal smoke (collect CFs for `(equipment, tube)` set, apply does not block calculation).
- Characterization: load all `example_data/RDSR/*.dcm` end-to-end with CF=1.0 and assert byte-identical PSD/dose map
  to the current main-branch output (guards against accidental double-application or K_IRP mutation).

## 12. Privacy / harness notes

- Station names and serial numbers are operator-controlled identifiers, not patient PHI, but can indirectly identify
  a site/room. Follow `PRIVACY_AND_SENSITIVE_ASSETS.md`: never log full raw station strings at INFO; use summary
  forms ("equipment resolved: 3 unique units, 0 unresolved") at summary level and per-event at DEBUG only, gated
  behind `logging` — never `print`.
- Treat the CF file as user-supplied data; do not commit example CF tables with real site identifiers.
- Keep new source files under the ~800-line modularity ceiling; keep `kerma_correction.py` cohesive.
- Run the harness checks called out in `HARNESS_ENGINEERING.md` (ruff, basedpyright, pytest, doc-freshness,
  help-registry, ui-copy) in the PR.

## 13. Open questions

- Do we want a per-model "default CF" row in the table (e.g. apply a model-level calibration to all units of that
  model unless overridden)? Current design treats model as out-of-scope; reconsider only if sites ask.
- Should prompt-mode persist entered CFs to a local per-station cache (gitignored) so the next run prefills them?
  Convenience vs. staleness tradeoff; defer to a follow-up.
- Naming: "Kerma-meter correction factor" vs industry terms "kerma calibration factor" / "K_AP correction".
  Glossary should alias all three; the settings/UI label uses "Kerma-meter correction factor".