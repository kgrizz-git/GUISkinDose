# Kerma-Meter Correction Factors (per equipment × tube)

Status: **Shipped** (Phases 0–6)
Plan type: Execution plan (input data & calculation)
Created: 2026-07-26
Updated: 2026-07-26 (implemented; archive candidate)
Owner: maintainer
Related: [TO_DO.md](../../TO_DO.md) — *Input Data And Calculation*; [INPUT_DATA_FLOW_AND_OFFSETS.md](../../INPUT_DATA_FLOW_AND_OFFSETS.md); [VENDOR_COORDINATE_SYSTEMS.md](../../VENDOR_COORDINATE_SYSTEMS.md); [TABULAR_RDSR_INPUT_PLAN.md](../TABULAR_RDSR_INPUT_PLAN.md); AAPM TG-190 (industry calibration context).

> **Implementation complete.** Core module: `src/mypyskindose/kerma_correction.py`.
> Archive under `plans/archive/` after the shipping PR merges and acceptance §4 is signed off.

---

## 0. Review notes (2026-07-26)

Plan review against the live dose pipeline, settings, adapters, and exports. Changes in this revision:

| Issue | Resolution in this plan |
|---|---|
| Acceptance §4.6 said `{file,prompt-off}`; §8 said `{file,prompt}` | Unified on `{file,prompt}`; CLI/non-GUI + `mode=prompt` → fail-soft to `default_factor` with a warning (never block). |
| Phase 1 / Phase 4 still mentioned configurable `key_strategy` | Removed. Precedence is fixed (§6); no GUI selector, no CLI flag, no resolver parameter. |
| `settings_example.json` cannot carry JSONC comments | Ship a real default block (`enable: false`, …); absent key still means disabled. |
| Applying CF only at `add_correction…:90` leaves `AirKerma` / `Events.kerma` / kerma-weighted export stats on the *reported* value while PSD moves | Resolve factors once in `calculate_dose` (like `k_tab`); use corrected kerma for dose + dose-relevant exports; keep reported K_IRP in `OUTPUT_KEY_KERMA` / `Events.kerma`; add parallel corrected fields (§9 Phase 2). |
| DoseTrack "Equipment Name" is usually the *model*, not a unique unit | Documented as a first-class caveat (§6.1); sites with one unit per model can still key on it; multi-unit sites use `explicit_label` or a custom station column. |
| Radimetrics unit vs model columns | **Equipment** = unit/room (CF key); **Device** = model. Plan previously mis-stated Device as the unit key — corrected (§5, §6, Phase 0). |
| Dual identity (same room as `StationName` in one file, `DeviceSerialNumber` in another) | Documented; table authors must match the identifier that wins for their input; optional alias column deferred (§15). |
| Multi-exam + `explicit_label` | Label applies to every event in the run; **GUI multi-exam requires a blocking confirmation** (not only a log warning) when it would collapse distinct auto-resolved units; CLI stays warn-only. |
| Kerma-weighted export basis when CF enabled | Weight by corrected kerma; call out in CHANGELOG + an export footnote so the silent basis change is auditable. |
| GUI Data Table `K_IRP` (`event_table.py`) | Always **reported** (input `rdsr_df`); corrected kerma lives in Results / export — pinned in Phase 4. |
| `normalized.py` in Phase 0 | Explicit adapter bullet alongside DoseTrack / Radimetrics / generic (pass-through `station_name` / `device_serial`). |
| Test plan incomplete vs acceptance | Expanded phase-mapped checklist in §13 (unit, adapter, dose, CLI, GUI, export, privacy, characterization). |
| Leftover duplicated sentence in old §13 | Removed. |

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

Aligns with the correction-coefficient concept in AAPM TG-190 / related KAP-meter literature
(`CC = measured / reported`). This plan implements a **single scalar CF per (equipment, tube)** — not
beam-quality-dependent CCs (out of scope; see §11).

A reported `K_IRP` is multiplied by CF to obtain the corrected air kerma:

```
K_IRP_corrected[ev] = K_IRP_reported[ev] × CF[ev]
```

CF is looked up by **specific individual unit** (not just model) **and** tube (A/B / single-plane). When the specific unit cannot be determined or is not present in the lookup table, **CF = `default_factor`** (1.0 by default — no correction, dose unchanged) — identical fail-soft philosophy to the existing `k_tab` model/plane fallback in `corrections.py:254`.

This is a **calibration correction to the meter/reporting chain**, conceptually distinct from the physics corrections (inverse-square, backscatter, medium, table attenuation) already applied in `corrections.py` and `calculate_dose/`.

## 2. Background / current behavior

- Per-event air kerma is stored in `data_norm[KEY_NORMALIZATION_AIR_KERMA]` (`"K_IRP"`, mGy), set in
  `rdsr_normalizer.py:345` from `data_parsed.DoseRP_Gy * 1000`.
- Dose is accumulated in
  `add_correction_and_event_dose_to_output.py:90` as
  `event_dose[hits] += normalized_data.K_IRP[event]`, then multiplied by the physics correction factors.
- `calculate_irradiation_event_result.py:152` copies the per-event kerma to `output[c.OUTPUT_KEY_KERMA][ev]`.
- Downstream consumers that read the **reported** sum today:
  - `format_export_data.py` → `AnalysisResult.AirKerma = data_norm[K_IRP].sum()` and `EventOutput.kerma`
  - Rich-export kerma-weighted correction stats (`export/metrics.py`) weight by per-event kerma
  - GUI `state.air_kerma` from `output["air_kerma"]` / `ExamResult.AirKerma`
- Per-event tube A/B is already available as `acquisition_plane` (`"Single Plane" | "Plane A" | "Plane B"`), normalized at
  `rdsr_normalizer.py:238` from `AcquisitionPlane` (DICOM concept per event).
- Per-unit identification is **currently NOT captured**: `rdsr_parser.py:121` only stores
  `Manufacturer` and `ManufacturerModelName` per event. Station name / device serial number — both present on
  example RDSRs (see §5) — are dropped.
- The closest existing precedent is `k_tab` (`corrections.py:193`), which keys on **model × acquisition_plane**
  and fails soft to `1.0` for unknown devices. CF uses **individual unit × tube**, not model.
- `calculate_dose` already runs **once per exam** (multi-exam loops outside); CF resolution is naturally
  per-exam DataFrame, matching `k_tab` / below-floor kVp policy.

## 3. Key terminology

| Term | Meaning |
|---|---|
| Equipment | One specific physical X-ray unit (room). Identified by `StationName` (DICOM `0008,1010`) and/or `DeviceSerialNumber` (DICOM `0018,1000`). May also be tabulated by a user-chosen custom station label for tabular inputs that lack DICOM-level station identifiers. |
| Tube | A specific radiation source on the equipment (single-plane stations have one tube; biplane stations have A and B). Per event, captured by the `acquisition_plane` ("Single Plane" / "Plane A" / "Plane B"). |
| Model | `ManufacturerModelName` (DICOM `0008,1090`). A *model* may correspond to many individual units; CF is per-unit, never per-model. |
| Meter correction factor (CF) | `CF = (real measured dose) / (unit reported dose)`. Multiplied into the per-event K_IRP before physics corrections. Dimensionless. `CF = 1.0` means no correction. Industry aliases: kerma calibration factor, KAP/K_a,r correction coefficient (TG-190). |

## 4. Acceptance criteria

1. Per-event air kerma used for dose is `K_IRP_reported[ev] × CF[ev]`, where CF is resolved per (equipment, tube).
2. When equipment or tube cannot be determined, or the (equipment, tube) pair is absent from the supplied
   lookup table, `CF = default_factor` (1.0 by default — dose numerically unchanged when default is 1.0) and a
   *summary* warning is logged (counts + event-index list via `grid_interp.format_event_indices`), mirroring
   the existing `k_tab` warning style (`corrections.py:303`). Distinguish **unresolved identity** vs
   **table miss** in the message text.
3. The corrected K_IRP (post-CF) is the value carried through dose accumulation, PSD, and dose-relevant
   export metrics — i.e. CF happens **before** inverse-square / backscatter / medium / table corrections,
   exactly once, with no double-application. Reported K_IRP columns are never mutated in place on
   `data_norm`.
4. CF is surfaced as a first-class per-event correction factor in `output` and in the Rich-Export corrections table
   (separate column from `k_tab`/`k_med`/`k_bs`/`k_isq`), with units "= dimensionless". Resolved (equipment, tube)
   keys appear only in export provenance metadata (not per-event table columns — §14).
5. Two input mechanisms are supported, switchable via settings:
   - **Lookup file**: a CSV/TSV/XLSX (or simple JSON) table supplied at runtime; and/or
   - **Interactive prompt** (GUI only): before calculation, the GUI collects a CF for each detected
     (equipment, tube) and offers a default of `default_factor`. An optional in-memory table (from the
     prompt or tests) overrides / supplements file lookup for the session.
6. CLI: `--kerma-meter-correction` (enable), `--kerma-meter-correction-file PATH`,
   `--kerma-meter-correction-mode {file,prompt}`, and `--kerma-meter-explicit-label TEXT`.
   Non-interactive runs never block: `mode=prompt` outside GUI → CF = `default_factor` + warning;
   enabled + `mode=file` + missing file → CF = `default_factor` + warning.
7. The original uncorrected K_IRP is retained in the **existing** `output[c.OUTPUT_KEY_KERMA]` field (unchanged for
   dict-mode consumers — no silent behavior break); the corrected value lives in a **new**
   `output[c.OUTPUT_KEY_KERMA_CORRECTED]` field, so the correction is auditable/reversible in exports and tests.
   Parallel additive fields for `AnalysisResult` / rich export: keep `AirKerma` as the **reported** sum;
   add `AirKermaCorrected` (and corrected per-event kerma for dose-weighted metrics). Document in CHANGELOG.
8. Unit and tabular inputs parse station identifiers cleanly and never PII-leak (station names can be free text;
   apply the project's runtime privacy rule — no raw identifiers in logs/exports beyond what the user has already
   chosen to load; see `PRIVACY_AND_SENSITIVE_ASSETS.md` and §14).
9. Tests cover the checklist in §13 (unknown equipment → default; biplane tube resolution; file formats;
   single-plane vs A/B; enable-off / CF=1.0 PSD parity; CLI fail-soft; GUI prompt smoke; export columns;
   privacy log assertions).

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
  and still fall back to `default_factor`.
- `AcquisitionPlane` per event resolves to `Single Plane` / `Plane A` / `Plane B` on the example fixtures.
- Tabular adapters expose vendor-specific unit/model columns (roles differ by vendor — do not conflate):
  - **DoseTrack:** `"Equipment Name"` → today used only to infer `ManufacturerModelName` then dropped
    (`dosetrack.py:185`–`:206`); often the *model*, not a unique room (§6.1).
  - **Radimetrics:** `"Equipment"` → room/unit name (per-unit identity for CF); `"Device"` → model
    (`ManufacturerModelName`). Confirmed by site practice and
    `dev-docs/references/psdcalcrework_io_utils.py` (keeps Device separate from Equipment for calibration lookup).
    Today's `RADIMETRICS_PATTERNS` maps `"device"` / `"equipment name"` → `ManufacturerModelName` and does **not**
    yet capture bare `"equipment"` as a station identity — Phase 0 must fix that split.
  For tabular CF keys, combine the vendor's **unit** column with AcquisitionPlane (plane → A/B/single).

## 6. Equipment key design (resolution & precedence)

A composite key identifies "which unit + tube" an event belongs to, resolved by a **single fixed order**
(first non-empty wins). If nothing resolves, the event goes to `default_factor`. There is no configurable strategy —
the order is baked in to keep the model simple and predictable; the lookup table does the matching.

1. Explicit user-label override (`settings.kerma_meter_correction.explicit_label`, a single string) — when set,
   every event gets this label as its equipment identity (useful for reprocessing an ambiguous export under a
   deliberate unit name). **Multi-exam / multi-unit safety:**
   - If more than one distinct auto-resolved equipment key would have existed without the override, **CLI**
     logs a warning that `explicit_label` forces one label onto all events.
   - In **GUI multi-exam mode** (or any GUI run where >1 distinct auto-resolved key would collapse), do **not**
     apply the override on Confirm until the user accepts a **blocking confirmation dialog** that names the
     count of distinct keys being collapsed and restates the forced label. Cancel/dismiss leaves
     `explicit_label` unset for that calc (or keeps the previous confirmed value — do not silently apply).
   - Single-exam / single-key runs: no extra dialog.
2. `DeviceSerialNumber` (most stable per-unit identifier) when present.
3. `StationName` when present.
4. **Tabular fallback (per the user's requirement)** — when no DICOM station or serial is available (the normal
   case for CSV/TSV/XLSX exports, which carry no DICOM top-level attributes), resolve the equipment identity from
   the tabular column that names the **unit** (not the model). Vendor order:
   - **Radimetrics `"Equipment"`** — usual per-unit / room label; prefer this over `"Device"` (which is the model).
   - **DoseTrack `"Equipment Name"`** sentinel (currently consumed by `dosetrack.py:185` to infer
     `ManufacturerModelName` and then *dropped* at `:206` — Phase 0 must persist its value as the per-unit
     identity *before* it is dropped; see §6.1 caveat that this value is often the model).
   - Generic lowercase candidates: `equipment`, `equipment name`, `station name` (dedicated equipment-identity
     pattern list in `column_mapper` / per-adapter patterns — **distinct** from the model list).
   Only the unit-column *values* populate the equipment key; model inference (`Device` / model columns →
   `ManufacturerModelName`) stays a separate side effect.
5. Empty → unresolved → `default_factor`.

The effective event key is `(equipment_label, acquisition_plane_normalized)` where
`acquisition_plane_normalized ∈ {"single", "A", "B"}` (collapse "Single Plane" → "single"; keep "A"/"B" suffix;
matching is **case-insensitive** on both equipment and tube after `str.strip()` + Unicode NFKC +
`casefold()`). The lookup table is queried with this `(equipment, tube)` pair. There is **no wildcard row
matching**: an absent `(equipment, tube)` row resolves to `default_factor` (1.0 by default), so the unresolved
case and the "unknown unit" case share one knob.

Rationale: `DeviceSerialNumber` is more globally unique than `StationName` (which can be a friendly room label like
`"INR Lab"`). The order is fixed so the lookup-table author doesn't need to reason about per-run strategy settings.
For tabular exports — which never carry DICOM station/serial — the **"equipment"-style column is the *primary*
per-unit identifier**, not a last-resort hack: it is the only per-unit signal a tabular row has, and it must be
captured rather than collapsed into the model name as the adapters do today.

### 6.1 DoseTrack / model-as-equipment caveat

DoseTrack's **"Equipment Name"** column is consumed today to infer `ManufacturerModelName` via `MODEL2MANUF`.
In many site exports that value is the **model name** (e.g. `"Allura Clarity"`), not a unique room/unit label.
Consequences for CF:

- Sites with **one physical unit per model name** in their CF table can key rows on that Equipment Name value —
  it works as a de-facto unit key.
- Sites with **multiple rooms of the same model** cannot disambiguate from DoseTrack alone: they must set
  `explicit_label` per run, or supply a custom station column in a site-specific export / normalized schema.
- Phase 0 still persists the Equipment Name into `station_name` (or equivalent); the caveat is documented in
  GUI help, glossary, and the CF-file template `notes` header comment / README snippet — not silently assumed
  to be a unique serial.

**Do not confuse with Radimetrics:** despite similar names, Radimetrics **`"Equipment"`** is the room/unit
identity for CF, while Radimetrics **`"Device"`** is the model. DoseTrack **`"Equipment Name"`** is often the
model. Phase 0 pattern lists must keep these vendor roles separate.

### 6.2 Dual-identity (serial vs station)

The same physical room may appear as `StationName="U601"` in one RDSR and only
`DeviceSerialNumber="722010-564"` in another. Because precedence prefers serial when both exist, table authors
should either:

- Prefer **device serial** as the `equipment` column value when available, or
- Duplicate rows for both identifiers if both are used across their archive (same CF twice).

Optional `alias` / multi-label rows are deferred (§15).

## 7. Lookup-table schema

Deliberately minimal and human-editable. Columns:

| Column | Type | Required | Notes |
|---|---|---|---|
| `equipment` | str | yes | Station name, device serial, or a user-defined label. Matched after strip + NFKC + casefold. |
| `tube` | str | yes | `"single"`, `"A"`, `"B"` (case-insensitive). No wildcard sentinel. |
| `correction_factor` | float | yes | CF. Absent `(equipment, tube)` → `default_factor`. |
| `notes` | str | no | Free-text provenance / measurement date (never exposed as PHI; user responsibility). |
| `source` | str | no | Optional short citation of the QC measurement (e.g. "QC 2026-06"). |

Example rows:

```csv
equipment,tube,correction_factor,notes,source
U601,single,1.03,Annual QC 2026-06,site QC lab
722013-362,A,0.97,Water calorimetry 2026-03,NMRO
722013-362,B,1.02,Water calorimetry 2026-03,NMRO
```

Accepted formats: `.csv`, `.tsv`, `.xlsx` (first sheet by default; `file_sheet` configurable), and a JSON of the
form `{"factors": [{"equipment": "U601", "tube": "single", "correction_factor": 1.03}, ...]}`. Selection reuses the
existing `input_adapters/tabular_loader.py` machinery where possible; JSON is a thin additional loader.

Validation / resilience:

- Required columns non-empty after strip.
- `correction_factor` must parse to a **finite float > 0**; reject ≤ 0, NaN, ±Inf (fail the file load).
- **Warn** (do not reject) when any factor falls outside a suspicious band `[0.5, 2.0]` (configurable later if needed;
  constants in `kerma_correction.py`). Absurd values like `> 10` still warn; only ≤0 / non-finite reject.
- Duplicate `(equipment, tube)` after normalization → **first wins + warning** (deterministic).
- Empty file / zero data rows / missing sheet → fail fast with a clear message (do not silently enable CF=1.0
  while claiming a file was loaded).
- Encoding: UTF-8 with BOM tolerated; other encodings follow tabular_loader defaults.
- Soft size guard: refuse tables with >10 000 data rows (QC tables are tiny; oversized files are almost certainly
  the wrong file). Path must exist and be a regular file.
- Invalid files fail fast with a clear message; optional columns may be absent.

In-memory override (GUI prompt / tests): a `dict[tuple[str, str], float]` (or list of row dicts) may be passed
into the resolver without writing a file. Precedence when both file and in-memory exist: **in-memory wins for
overlapping keys**; keys only in the file still apply. Document this for the GUI "Confirm" path.

## 8. Settings

Add a nested settings object (mirror `PhantomSettings` / `NormalizationSettings` style) on
`PyskindoseSettings`, plus a real block in `settings_example.json` (strict JSON — no comments):

```json
"kerma_meter_correction": {
  "enable": false,
  "mode": "file",
  "file": null,
  "file_sheet": null,
  "default_factor": 1.0,
  "explicit_label": null,
  "prompt_at_calc": false
}
```

Suggested dataclass: `KermaMeterCorrectionSettings` in `settings/kerma_meter_correction_settings.py`
(or nested in `pyskindose_settings.py` if still small). Validation:

- `mode ∈ {"file", "prompt"}`
- `default_factor` finite and `> 0` (warn if outside `[0.5, 2.0]`)
- `file` coerced to `Path | None`
- Absent top-level key → construct defaults (`enable=false`) so old settings JSON keeps current behavior

Defaults are **behavior-preserving**: `enable: false` → CF=1.0 everywhere, identical to today (skip file I/O
entirely). Raising `enable: true` with `mode: "file"` and `file is null` (and no in-memory table) →
CF=`default_factor` *with* a one-time summary warning that the feature is enabled but no table was supplied.
The key-resolution order (§6) is **not configurable** — there are no `key_strategy` or
`--kerma-meter-key-strategy` knobs, by design.

CLI (`main.py`):

- `--kerma-meter-correction` (flag): enable the feature.
- `--kerma-meter-correction-file PATH`
- `--kerma-meter-correction-mode {file,prompt}` (prompt only meaningful in `--mode gui`; elsewhere warn +
  treat as default_factor).
- `--kerma-meter-explicit-label TEXT`

`prompt_at_calc` is **GUI-only and defaults to `false`**: non-interactive / CLI / scripted workflows must never
block on a prompt; enabling it only affects GUI runs initiated from the Calculate tab. Semver: additive
settings + optional behavior → **minor** bump when the feature ships; document in `CHANGELOG.md`.

## 9. Implementation phases

Each phase is independently shippable and leaves behavior unchanged when the feature is disabled.

### Phase 0 — Per-unit parsing (foundation; no behavior change)

- Extend `rdsr_parser.py:_parse_irradiation_event` to also capture `StationName` and `DeviceSerialNumber` from the
  top-level `data_raw` dataset (add `KEY_RDSR_STATION_NAME = "StationName"` and
  `KEY_RDSR_DEVICE_SERIAL = "DeviceSerialNumber"` to `constants.py`). Missing attributes store as `None`, not crash.
  Use getattr / `in` checks — do not assume pydicom raises.
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
    (distinct from the model column); first source-specific equipment-name candidate wins. Also recognize plain
    `equipment` and `equipment name`.
  - **DoseTrack** (`dosetrack.py:185`–`:206`): today the `_dt_equipment_name` sentinel is read only to derive
    `ManufacturerModelName`, then `data_df.drop(columns=["_dt_equipment_name"])` discards it. Persist its value
    into the new `station_name`/`device_serial`-equivalent column *before* the drop so the per-unit key survives.
  - **Radimetrics** (`radimetrics.py` `RADIMETRICS_PATTERNS`): today `"device"` / `"device model"` /
    `"equipment name"` all map to `ManufacturerModelName`, and bare `"equipment"` is not a CF identity column.
    Phase 0 must **split** roles to match real exports and `psdcalcrework_io_utils.py`:
    - `"Equipment"` / `"equipment"` → per-unit identity (`station_name` equivalent) for CF
    - `"Device"` / `"device"` / `"device model"` → `ManufacturerModelName` only
    - Remove `"equipment name"` from the *model* pattern list (or keep only as a last-resort model hint when
      no `Device` column exists — prefer never collapsing Equipment into model when both columns are present).
  - **Generic RDSR tabular** (`generic_rdsr.py`): prefer an `"equipment"`-style column for unit identity when
    present; do not treat `"device"` / `"device model"` as the unit key when a separate equipment column exists.
  - **Normalized schema** (`normalized.py`): first-class Phase 0 target alongside the vendor adapters. If the
    normalized CSV/TSV/XLSX already carries `station_name` and/or `device_serial` (or agreed aliases such as
    `StationName` / `DeviceSerialNumber`), pass them through into `data_norm` unchanged — do not drop or
    rename them during model mapping. Add pattern aliases so a site-authored normalized export can supply
    the CF identity columns without a vendor adapter. Round-trip test: normalized fixture with both columns
    survives load → `data_norm` with identical values.
- Add unit + characterization tests for missing vs present identifiers (DICOM RDSR with present/absent station and
  serial; each tabular adapter — DoseTrack, Radimetrics, generic, **normalized** — with/without an
  "equipment"-style / station column). **No dose change yet.**

### Phase 1 — Correction-factor engine (pure function, CF by key)

New module `src/mypyskindose/kerma_correction.py` (keep under ~400 lines; split loaders if needed):

```python
@dataclass(frozen=True)
class KermaMeterCorrection:
    factors: list[float]                # one per event, CF
    resolved_keys: list[tuple[str | None, str]]  # (equipment_label, tube) per event
    unresolved_event_indices: list[int]          # identity could not be resolved
    table_miss_event_indices: list[int]          # identity ok, no table row
    table_metadata: dict | None         # provenance, sheet name, path stem (not full path), etc.

def normalize_equipment_label(raw: str | None) -> str | None: ...
def normalize_tube(acquisition_plane: str | None) -> str: ...  # → "single" | "A" | "B"

def resolve_correction_keys(
    data_norm: pd.DataFrame,
    *,
    explicit_label: str | None,
) -> list[tuple[str | None, str]]: ...

def load_correction_table(path: Path, sheet: str | None) -> dict[tuple[str, str], float]: ...

def resolve_correction_factors(
    data_norm: pd.DataFrame,
    table: dict[tuple[str, str], float] | None,
    *,
    explicit_label: str | None,
    default_factor: float,
) -> KermaMeterCorrection: ...
```

Semantics follow §6 and mirror `corrections.calculate_k_tab`'s warning style (per-event index lists via
`grid_interp.format_event_indices`). Lookups are exact-match on normalized `(equipment, tube)`; an absent row
resolves to `default_factor`. There is **no wildcard row**. No dose math here — pure resolution. Fully
unit-testable without a GUI or RDSR run.

### Phase 2 — Wire into dose pipeline (CF applied exactly once, before physics corrections)

Recommended application point (cleaner than only patching line 90):

1. In `calculate_dose`, after HVL fetch / alongside `calculate_k_tab`, call `resolve_correction_factors`
   when `settings.kerma_meter_correction.enable` (else all-ones).
2. Pass `kerma_cf: list[float]` into `calculate_irradiation_event_result` →
   `add_correction_and_event_dose_to_output`.
3. At the K_IRP entry point:
   `event_dose[hits] += normalized_data.K_IRP[event] * kerma_cf[event]`
   (**do not** mutate `normalized_data.K_IRP`).
4. Populate output:
   - `OUTPUT_KEY_KERMA[ev]` = reported `K_IRP[ev]` (unchanged behavior)
   - `OUTPUT_KEY_KERMA_CORRECTED[ev]` = reported × CF
   - `OUTPUT_KEY_CORRECTION_KERMA_METER[ev]` = CF
5. **AnalysisResult / rich export polarity (additive):**
   - Keep `AirKerma` / `Events.kerma` / dict `"air_kerma"` as the **reported** sum (backward compatible).
   - Add `AirKermaCorrected` / corrected per-event kerma list used for **dose-weighted** correction stats and
     Results-tab display of the dose-relevant kerma when CF ≠ 1.
   - When `enable=false`, corrected fields equal reported fields.
6. Extend `_build_output_template` with the new keys.
7. CHANGELOG + `CODEBASE_OVERVIEW.md` output-fields table: call out that PSD/dose map use corrected kerma when
   enabled, while `OUTPUT_KEY_KERMA` / `air_kerma` remain reported.

Gate everything behind `settings.kerma_meter_correction.enable`; when disabled, skip file load, `factors` is
all-ones, and corrected == reported.

### Phase 3 — CLI + Settings wiring

- Add `KermaMeterCorrectionSettings` (§8) with validation.
- Wire CLI flags to settings in `main.py`.
- Add "enabled but no table" and "prompt mode outside GUI" summary warnings.
- Settings round-trip test: example JSON with the new block loads; old JSON without the block loads with defaults.

### Phase 4 — GUI prompt + file picker

- New helper under `src/mypyskindose/gui/tabs/` (or extend Settings): a "Kerma-meter correction" section with:
  enable toggle, mode selector (**file / prompt only** — no key-strategy control), file picker + optional sheet,
  explicit-label optional text field, short DoseTrack / Radimetrics column-role help link.
- Pre-calc prompt (`prompt_at_calc: true` or `mode == "prompt"`): before `calculate_dose` /
  `run_calculation`, enumerate unique `(equipment, tube)` pairs across **all loaded exams**, present a small
  table with per-row float inputs prefilled from `default_factor` and any loaded file. Confirm stores an
  in-memory table for the session. Cancel → CF = `default_factor` for all (never blocks calculation).
- Multi-exam: one prompt covering the union of keys.
- **`explicit_label` blocking confirmation (required task):** when the override would collapse >1 distinct
  auto-resolved equipment key, show a modal that must be accepted before calc proceeds with the override;
  dismiss/cancel does not apply the collapse. Wire a GUI test for accept vs dismiss.
- **Data Table `K_IRP` display (required task — pin polarity):**
  `gui/widgets/event_table.py` reads input `state.rdsr_df["K_IRP"]` (reported unit kerma). **Leave it as
  reported always** — the Upload/Data table is an input audit view, not a post-CF results view. Do **not**
  rewrite rows to corrected values after calc. When CF is enabled for the session, optionally add a short
  caption under the table: "K_IRP values are as reported by the unit (uncorrected)." Corrected kerma belongs
  in Results / export (`K_IRP (corrected)` / `AirKermaCorrected`). Document this in GUI help.
- Use a small new `ui_copy.json` / `help_registry.json` entry; mirror help from `docs/source/gui_help/` per GUI
  help rules. Update `feature_doc_matrix.json`.

### Phase 5 — Rich export & results UI

- Add CF (`k_meter` or `k_kerma_meter` — pick one constant name and stick to it; prefer
  `OUTPUT_KEY_CORRECTION_KERMA_METER = "k_meter"` for short table headers) to Results-tab corrections table and
  Rich-Export corrections section (PDF/DOCX/HTML/XLSX).
- Show `K_IRP (reported)` and `K_IRP (corrected)` where space permits; always show CF column when feature was
  enabled for the run (even if all CF=1.0).
- Record matched equipment labels and table source **only** in export provenance metadata (§14).
- Kerma-weighted cumulative correction stats: weight by **corrected** kerma when CF was enabled for that exam
  (falls back to reported when disabled).
- **CHANGELOG + export footnote (required task):** when CF is enabled, the weighting basis for cumulative
  correction stats changes from reported → corrected kerma. Call this out explicitly in:
  1. `CHANGELOG.md` under the release that ships CF (one bullet under Changed/Notes), and
  2. a short footnote under the Rich-Export corrections section when CF was enabled for the run
     (e.g. "Dose-weighted means use kerma-meter-corrected K_IRP when a correction table/prompt was applied.").
  Without both, the basis change is silent and easy to misread in multi-exam exports.

### Phase 6 — Docs, glossary, feature matrix

- Update `dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md`, `CODEBASE_OVERVIEW.md`, `FEATURE_INVENTORY.md`,
  `VENDOR_COORDINATE_SYSTEMS.md` (note: DICOM station/serial lives at study level, not event level), `AGENTS.md`
  if output-fields summary needs a row.
- Add glossary term "Kerma-meter correction factor" (aliases: kerma calibration factor, K_a,r / KAP correction
  coefficient) to `dev-docs/glossary.json`.
- Add a `feature_doc_matrix.json` row mapping the feature to its code/tests/docs/help.
- Add a synthetic example CF fixture under `tests/` or `example_data/` with placeholders only (`unit-01`, …) —
  never real-site names (§14).
- Archive this plan under `dev-docs/plans/archive/` once §4 acceptance passes and update `dev-docs/index.md`.

## 10. Phase ordering & dependencies

```
Phase 0 (parsing) ──┬─► Phase 1 (resolve) ──► Phase 2 (wire to dose) ──► Phase 3 (CLI/Settings)
                    └────────────────────────────────────────────────────► Phase 4 (GUI)
                                                                                      ► Phase 5 (export)
                                                                                      ► Phase 6 (docs)
```

Phases 0–3 are the minimum to ship the feature headlessly (CLI). 4–5 ship the user-facing experience. Each phase
keeps the prior behavior unchanged when disabled. Prefer landing Phase 0+1 with tests before touching the dose
loop (Phase 2).

## 11. Out of scope (explicit)

- Per-frame adjustment, dynamic CF as a function of kVp / HVL / filtration (TG-190 beam-quality CCs) — CF is a
  single calibration multiplier per (equipment, tube). Future hook: optional kVp/filter bands in the table; not
  in this plan.
- Inverse-calibration propagation into uncertainty estimates / confidence intervals.
- Vendor-controlled CF tables downloaded from a remote server — only local files / in-run input.
- Changing how `k_tab` resolves unknown models (CF and `k_tab` are independent: `k_tab` stays model/plane-keyed,
  CF is unit/tube-keyed).
- Automated population of CF from a QC database — manual entry only.
- Alias / multi-label rows mapping serial↔station in one table row (defer; duplicate rows work today).
- Mutating reported `data_norm.K_IRP` in place.

## 12. Risks & mitigations

| Risk | Mitigation |
|---|---|
| User mis-keys the table (wrong serial) → wrong dose applied silently | Unresolved / table-miss warnings + corrections table shows CF; prompt shows resolved key next to each input; §4.7 keeps reported K_IRP auditable. |
| Station names containing site identifiers shipped in exports | Concrete export/log rules in §14: per-event tables never carry station/serial columns; provenance metadata only when user supplied a CF file; INFO logs use counts only. |
| Double-application of CF | Apply exactly once via `kerma_cf[event]` at the K_IRP entry point; never mutate `data_norm.K_IRP`; tests assert `KERMA_CORRECTED == KERMA × CF` and CF=1.0 PSD parity vs main. |
| `AirKerma` vs PSD diverge when CF≠1 | Intentional and documented: `AirKerma` stays reported; `AirKermaCorrected` / PSD use corrected. Results UI labels make both visible. |
| DoseTrack model-as-equipment mis-keying | §6.1 caveat in help + template notes; `explicit_label` escape hatch. |
| Dual identity serial vs station | §6.2 guidance; prefer serial in tables; duplicate rows if needed. |
| Inconsistent `acquisition_plane` strings | Tube normalization is case-insensitive on the event plane string only; missing B row → `default_factor` for B events. |
| Silent dict-mode break | `OUTPUT_KEY_KERMA` / `air_kerma` stay reported; new fields are additive. |
| Phase 0 adapter regressions | Persist equipment name *before* drop; characterization tests per adapter; no dose change in Phase 0. |
| Multi-exam `explicit_label` stomps distinct units | GUI: **blocking confirmation** before apply when >1 auto-resolved key would collapse; CLI: warn-only. Test accept vs dismiss. |
| Kerma-weighted export basis shifts when CF on | CHANGELOG bullet + Rich-Export corrections footnote (§9 Phase 5). |
| Users confuse Data Table K_IRP with corrected dose kerma | Data Table always shows **reported** `rdsr_df` values; optional caption when CF enabled; corrected only in Results/export. |
| Wrong file / huge spreadsheet selected as CF table | Fail fast on missing sheet, empty data, >10k rows; clear error — never silent CF=1.0 while claiming success. |
| Prompt mode in CLI | Warn + `default_factor`; never block. |
| Backwards compatibility of saved settings | Absent block == disabled defaults; example JSON ships explicit `enable: false` block. |

## 13. Test plan

Tests **will be added** in each phase (not deferred to the end). Map:

### Phase 0 — parsing / adapters
- `tests/unittests/test_rdsr_parser_station.py`: `StationName` / `DeviceSerialNumber` present on example RDSRs that
  have them; `None` for `siemens_axiom_example_procedure.dcm`.
- Extend `tests/unittests/test_input_adapters.py` (or sibling): DoseTrack / Radimetrics / generic / **normalized**
  preserve equipment identity into `station_name` (or agreed column) without changing existing model inference.
  **Radimetrics-specific:** when both `Equipment` and `Device` columns exist, `station_name` comes from
  `Equipment` and `ManufacturerModelName` from `Device` (never swap or collapse Equipment into model).
  **Normalized-specific:** fixture with `station_name` / `device_serial` round-trips unchanged.
- Characterization: normalized columns exist; dose path untouched (no CF module yet).

### Phase 1 — pure resolver (`tests/unittests/test_kerma_correction.py`)
- Precedence: explicit_label → serial → station → tabular equipment → unresolved.
- Tube normalize: `"Single Plane"` / `"Plane A"` / `"plane b"` / None → `single` / `A` / `B` / `single`.
- Casefold / whitespace / NFKC matching on equipment + tube.
- Missing IDs → `default_factor`; table miss vs unresolved index lists distinct.
- No wildcard matching; duplicate table rows → first wins + warning.
- File loaders: CSV / TSV / XLSX / JSON happy path; reject ≤0 / NaN; warn outside `[0.5, 2.0]`; empty file /
  missing sheet / oversized table fail; sheet name selection.
- In-memory table overrides overlapping file keys.
- `enable`-equivalent path: empty/None table → all `default_factor`.

### Phase 2 — dose pipeline (`tests/unittests/test_dose_kerma_correction.py`)
- Synthetic normalized frame: CF=1.0 → PSD and dose map match baseline (bit-identical within float tol).
- CF=c (constant) → PSD scales by c; physics correction vectors (`k_isq`, `k_bs`, `k_med`, `k_tab`) unchanged.
- `OUTPUT_KEY_KERMA` == reported; `OUTPUT_KEY_KERMA_CORRECTED` == reported × CF;
  `OUTPUT_KEY_CORRECTION_KERMA_METER` == CF.
- `data_norm.K_IRP` unchanged after `calculate_dose`.
- Characterization: load all `example_data/RDSR/*.dcm` end-to-end with feature disabled (or CF=1.0) and assert
  PSD/dose-map parity with current main-branch output (guards double-application / accidental K_IRP mutation).

### Phase 3 — settings / CLI
- Settings round-trip: with and without the new JSON block.
- CLI flag wiring (parser defaults + enable/file/mode/explicit-label).
- Non-GUI `mode=prompt` → warning path + default factors (unit-test the branch; no GUI).

### Phase 4 — GUI (`tests/gui/` or `tests/unittests/test_gui_*`)
- Prompt modal smoke: unique `(equipment, tube)` across multi-exam fixtures; Confirm applies in-memory table;
  Cancel leaves default factors; calculation still completes.
- `explicit_label` collapse: multi-exam fixture with two distinct keys → blocking confirm required; dismiss does
  not apply override; accept applies.
- Data Table: after calc with CF≠1, `event_table` `K_IRP` column still equals reported `rdsr_df` values (not
  corrected); caption present when CF enabled (if implemented).
- Settings section: no key-strategy control present; file picker path stored on state/settings.

### Phase 5 — export / results
- Corrections table includes `k_meter` (or chosen key) when enabled.
- Provenance metadata lists matched equipment labels only when a CF file/prompt table was used; per-event
  tables have no Station/Serial column.
- Kerma-weighted stats use corrected kerma when enabled; export footnote present when CF was applied.
- CHANGELOG entry for the weighting-basis change exists in the shipping PR checklist (manual doc check).

### Privacy / harness (any phase that logs or exports)
- Assert INFO/WARNING log messages do not contain raw station/serial strings (use `caplog` + synthetic labels).
- New UI strings registered in `ui_copy.json` / help registry checks.
- Synthetic CF fixture only (`unit-NN` placeholders).

## 14. Privacy / harness notes

Station names and device serial numbers are operator-controlled identifiers, not patient PHI, but they can
indirectly identify a site/room and are user-loaded (not filtered by the project). Concrete handling rules:

- **Logging:**
  - At INFO/WARNING: never print full raw station/serial strings. Use summary forms only: counts and buckets,
    e.g. `"kerma-meter correction: 3 unique equipment keys resolved, 2 unresolved → default_factor=1.0"`.
  - Per-event raw strings appear only at DEBUG, gated behind the standard `logging` module (never `print`),
    and only when the user explicitly raised verbosity (default runtime stays INFO).
- **Exports (HTML/PDF/DOCX/XLSX):**
  - **Body/event tables go only by index** (the per-event corrections table already keys by event index). Do
    **not** add a "Station" or "Serial" column to per-event tables.
  - The resolved equipment label appears **only in export metadata**, only as a single-block list
    ("Equipment matched in CF table: U601, 722013-362"), and only when the user has loaded a CF file or
    confirmed a prompt table. The provenance block notes "Station/serial values are user-loaded; site
    responsibility for downstream sharing."
  - File-name and on-disk paths in exports keep the existing redaction policy (no source RDSR filename; CF
    table path stored as stem only, never absolute path).
- **CF table files:** treat as user-supplied data; do **not** commit example CF tables with real-site station
  names (use placeholders like `unit-01` / `unit-02`). In-repo test fixtures use synthetic labels only.
- **Tabular input:** the existing identifier-redaction logic on tabular columns is unchanged; the new
  `station_name`-equivalent column inherits the same logging redaction (no full value at INFO).
- **Harness:** keep new source files under the ~800-line modularity ceiling; keep `kerma_correction.py` cohesive.
  Run the harness checks in `HARNESS_ENGINEERING.md` (ruff, basedpyright, pytest, doc-freshness, help-registry,
  ui-copy) in the PR; add a UI-copy entry for any new user-visible CF string. Semgrep privacy rules apply to any
  new logging in Phase 1–5.

## 15. Open questions

- Do we want a per-model "default CF" row in the table (e.g. apply a model-level calibration to all units of that
  model unless overridden)? Current design treats model as out-of-scope; reconsider only if sites ask.
- Should prompt-mode persist entered CFs to a local per-station cache (gitignored) so the next run prefills them?
  Convenience vs. staleness tradeoff; defer to a follow-up.
- Optional `alias` column / multi-label matching for serial↔station dual identity? Defer; duplicate rows suffice.
- Should Results-tab primary "Air kerma" tile show reported, corrected, or both when CF≠1? **Recommendation:**
  show corrected as primary when enabled and CF any ≠1, with reported as secondary line — confirm at Phase 4/5
  implementation. (Upload Data Table `K_IRP` is separately pinned to **reported** — not open.)
- Constant name: `k_meter` vs `k_kerma_meter` vs `k_cf`? **Recommendation:** `k_meter` (short, parallel to
  `k_tab` / `k_med`) with UI label "Kerma-meter (k_meter)".

Resolved by this review (no longer open):

- Key strategy configurability → **no** (fixed precedence).
- CLI mode naming → `{file,prompt}` with non-GUI prompt fail-soft.
- `OUTPUT_KEY_KERMA` polarity → **reported**; corrected is additive.
- `AirKerma` polarity → **reported**; add `AirKermaCorrected`.
- Tests → **yes, phase-mapped** (§13), not optional.
- GUI Data Table `K_IRP` → **always reported**; corrected only in Results/export.
- Multi-exam `explicit_label` collapse → **blocking GUI confirmation** (CLI warn-only).
- Kerma-weighted export basis change → **CHANGELOG + export footnote**.
- `normalized.py` Phase 0 → **explicit adapter bullet + round-trip test**.
