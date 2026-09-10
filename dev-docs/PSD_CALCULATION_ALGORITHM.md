# PSD Calculation Algorithm

_Date: 2026-09-10_

Canonical description of how GUISkinDose turns irradiation-event data into peak
skin dose (PSD) and a 3D skin dose map. This is the **algorithm source of truth**;
`CODEBASE_OVERVIEW.md` describes architecture, `FEATURE_INVENTORY.md` lists
features, and this file describes the dose math in execution order.

Scope: single-exam (`analyze_data`) and multi-exam (`analyze_multiple_exams`)
paths share one per-exam core (`calculate_dose`). GUI and CLI run the same core;
only the settings source differs. Mode must be `calculate_dose`
(`plot_dosemap` reuses the same loop for rendering).

> **Units.** All geometry is in **cm**; dose in **mGy**; correction factors are
> dimensionless (≈ 0–1, backscatter slightly above 1). Coordinate-axis semantics
> are defined in [VENDOR_COORDINATE_SYSTEMS.md](VENDOR_COORDINATE_SYSTEMS.md) and
> are not redefined here. Input normalization and the DataFrame contract live in
> [INPUT_DATA_FLOW_AND_OFFSETS.md](INPUT_DATA_FLOW_AND_OFFSETS.md); schema
> detection in [INPUT_SCHEMA_DETECTION.md](INPUT_SCHEMA_DETECTION.md).

## 0. Entry points and orchestration

- `guiskindose.main.main()` → `analyze_data.analyze_data()` (single exam) or
  `analyze_multiple_exams()` (multi-exam). Settings are normalized via
  `initialize_settings()`; anything but `calculate_dose` / `plot_dosemap` mode
  returns no dose output.
- Per exam, in order: build table + pad `Phantom`s → `calculate_rotation_matrices`
  (per-event C-arm/table rotation matrices on the normalized frame) →
  `create_geometry_plot` → `calculate_dose.calculate_dose()` → export formatting
  (`format_analysis_result_for_export`, dict/JSON) or dose-map plotting (HTML).
- `calculate_dose` returns `(patient, output, export_data_norm)`: the patient
  phantom with the accumulated `dose_map`, the per-event output dict, and the
  post-below-floor-policy event frame so exports align event counts after a
  `skip` policy drops rows.

## 1. Read irradiation events

Each row of the normalized DataFrame is one irradiation event carrying tube
voltage (kVp), filtration (Cu/Al mm), reference-point air kerma (`K_IRP`),
geometry (`Tx/Ty/Tz`, `FS_lat/FS_long`, `Ap1–3`, `At1–3`), source distances
(`DSD`, `DSI`), acquisition type, and plane identity. Sources:

- **DICOM RDSR** (`.dcm`) via `rdsr_parser.py` + `rdsr_normalizer.py`.
- **Tabular exports** (`.csv`/`.tsv`/`.xlsx`) via `input_adapters/` (schemas:
  `normalized`, `generic_rdsr_like`, `radimetrics`, `dosetrack`).
- **Pre-parsed JSON** test fixtures bypass parsing (geometry edge cases only).

## 2. Vendor / unit / coordinate transforms and offsets

`rdsr_normalizer.py` maps the vendor frame into the internal cm frame using
`normalization_settings.json` matched on `Manufacturer` + `ManufacturerModelName`
(translation offsets, rotation/translation signs, field-size mode, detector
length). Table-position readouts become `Tx/Ty/Tz`; the `(0,0,0)` isocenter
coincides with the table head-end at zero readout.

Phantom placement (`geom_calc.position_patient_phantom_on_table`):

- Table + pad phantoms are built from `settings.phantom.dimension`
  (pad thickness included); the patient `Phantom` is built from
  `settings.phantom.model` (`plane` / `cylinder` / `human` mesh + `human_mesh`).
- The mesh is placed with `patient_offset` `[d_lon, d_ver, d_lat]` in cm and
  `patient_orientation`. Multi-exam runs use per-exam offsets
  (`analyze_data._effective_patient_offset`); globals are ignored for dose in
  multi-exam mode. Fresh table/pad objects are created per exam because
  positioning uses incremental translation.
- Human meshes accept directional habitus scales `scale_lat/scale_ap/scale_lon`
  (clamped to 0.5–2.0); geometry and dose use the scaled vertices and recomputed
  normals.

## 3. Correction-factor prerequisites (before the event loop)

Resolved once per exam, in this order (`calculate_dose`):

1. **Below-floor kVp policy** — `geom_calc.apply_below_floor_kvp_policy()`:
   events under the 25 kV HVL floor follow `below_floor_kvp_policy`
   (`exam_average` default / `snap` / `skip` / `manual`). `skip` drops rows
   (hence the post-policy frame return); `snap` is a no-op here because the HVL
   lookup clamps and flags.
2. **HVL** — `geom_calc.fetch_and_append_hvl()` from kVp + inherent + added
   filtration via the corrections DB. Off-grid queries interpolate; out-of-range
   queries clamp (never extrapolate), warning per event (`grid_interp.py`).
3. **Geometry-change flags** — `geom_calc.check_new_geometry()` compares
   `Tx/Ty/Tz`, `FS_lat/FS_long`, `Ap1–3`, `At1–3` row-to-row; `True` means the
   beam, hits, field areas, and `k_isq` must be recomputed for that event.
4. **Backscatter splines** — `corrections.calculate_k_bs()` builds one
   `CubicSpline` per event (Benmakhlouf et al., tabulated field side
   5/10/20/25/35 cm).
5. **Patient-support transmission** — `corrections.calculate_k_tab()` returns a
   `KTabResult` (values + per-event statuses):
   - *Estimated* (`estimate_k_tab=True`, default): every event gets `k_tab_val`
     (validated); the DB is not read.
   - *Measured*: DB lookup keyed by device model + **literal**
     `acquisition_plane` string (`"Single Plane"` / `"Plane A"` / `"Plane B"`),
     exact (kVp, Cu, Al) match first, else (kVp, Cu) interpolation with Al snap
     and edge clamping. Unknown device/plane or invalid cells resolve to a
     warned-neutral `1.0`, never silently to a real calibration.
6. **Kerma-meter correction** — `kerma_correction.resolve_correction_factors()`
   resolves one factor per event keyed by (equipment, tube), from an explicit
   label, correction file, prompt-time in-memory table, or default factor
   (fail-soft with warnings; disabled → all `1.0`). No special-casing of A/B
   geometry: identity comes from equipment × tube keys only.

## 4. Per-event field projection

`calculate_irradiation_event_result()` loops events; for each event with
`new_geometry=True`,
`perform_calculations_for_new_geometries()` runs:

1. `Beam(data_norm, event)` builds the source position and collimated pyramid
   from angles, SID/IRP distances, and field size / field-size mode.
2. Patient, table, and pad are positioned for this event; `beam.check_hit()`
   ray-casts source → each skin cell against the phantom triangle mesh,
   yielding boolean `hits` (entrance skin cells).
3. If any hits: `check_table_hits()` flags which hit paths intersect table/pad;
   `scale_field_area()` computes per-hit-cell field area at the skin;
   `calculate_k_isq()` corrects IRP air kerma to skin distance per hit cell
   (`dref` = source-to-IRP distance).
4. If geometry is unchanged since the previous event, the previous `hits`,
   `table_hits`, `field_area`, and `k_isq` arrays are **reused** verbatim
   (geometry-change reuse). A new-geometry event with no hits resets those
   arrays to empty instead of carrying stale values forward.

## 5. Intersections with table / pad and patient phantom

- The patient phantom is a triangle mesh (`Phantom.r` vertices); table and pad
  are box phantoms in the same cm frame. `check_hit` tests source→cell segments
  against mesh triangles; `check_table_hits` tests source→hit-cell segments
  against the table/pad boxes.
- Only entrance cells (`hits=True`) accumulate dose. `table_hits` selects which
  of those cells additionally receive the `k_tab` transmission factor; all other
  hit cells keep factor `1.0` for that term even when the event's `k_tab ≠ 1`.
- Beam-miss diagnostics: per-event warnings (`beam_miss_warn="per_event"`, naming
  kVp, filtration, field area) or a run summary (`"summary"`); all-miss runs warn
  that the map is all zeros. Missed indices are stored as
  `output["missed_event_indices"]` and surfaced per exam in multi-exam mode.
  Multi-exam runs downgrade `per_event` to `summary` to avoid warning floods.

## 6. Cumulative accumulation over exposures and exams

Per hit event (`add_corrections_and_event_dose_to_output()`):

```text
event_dose[hits] = K_IRP × kerma_cf × k_isq × k_med × k_bs × (k_tab where table_hits else 1.0)
output["dose_map"] += event_dose
```

where `k_bs` is the event spline evaluated at `sqrt(field_area)` and `k_med`
(air→water, from kVp/HVL/field via the corrections DB) is scalar per event.
Zero-hit events record empty `k_bs`, `k_med = 0.0` ("not applied"), the event's
`k_tab`, and add nothing. `K_IRP` in the frame is never mutated; the corrected
kerma is stored separately (`kerma_corrected`).

Single exam: `PSD = max(dose_map)` (`PySkinDoseOutput.psd`). Multi-exam: each
exam runs the full per-exam pipeline on the shared mesh topology; per-exam dose
maps are **summed element-wise** into `aggregate_dose_map` and
`aggregate_psd = max(aggregate_dose_map)` (0.0 when empty). Failed exams are
fail-soft: they contribute warnings (import warnings preserved) and are excluded
from the aggregate with an exclusion count header.

## 7. Reporting

- `format_analysis_result_for_export()` packages dose map, per-event corrections
  (`kerma`, `kerma_corrected`, `k_isq`, `k_bs`, `k_med`, `k_tab`,
  `kerma_meter_cf`), `k_tab_statuses`, `missed_event_indices`, air kerma, PSD,
  and warnings into `PySkinDoseOutput` (dict / JSON) or the interactive HTML
  dose-map plot.
- Rich exports add the plane-identity audit (`source_kind` / `resolution` /
  `canonical` per event) and `k_tab` status counts; the Calculate tab shows a
  pre-calc `k_tab` preview (cached dry-run, warnings suppressed) plus
  post-calc status summaries.

## Implementation deviations (GUISkinDose vs upstream PySkinDose)

The following are GUISkinDose extensions or intentional departures from the
upstream baseline; do not "simplify" them away as dead complexity:

- Measured `k_tab` DB lookup with interpolation + clamping and structured
  `KTabResult` statuses (upstream: fixed scalar only).
- Kerma-meter correction keyed by equipment × tube (`kerma_correction.py`).
- Below-floor kVp policy selection and HVL interpolation/clamping.
- Plane-identity audit fields and per-row DICOM/raw-code selection in the
  normalizer (lookup identity only — beam projection math stays plane-agnostic).
- Multi-exam pipeline with per-exam offsets, fail-soft exams, and map
  summation.
- Warned-neutral `1.0` convention for unresolvable/out-of-range transmission
  (explicit "no correction" signal, distinct from a measured full-transmission).

## Maintenance harness

- Dose-path code watched by this doc: `calculate_dose/`, `geom_calc.py`,
  `beam_class.py`, `corrections.py`, `kerma_correction.py`, `rdsr_normalizer.py`,
  `input_adapters/`, `analyze_data.py`, `format_export_data.py`.
- When changing those paths, run the doc-impact check and update this file in
  the same PR:
  `python scripts/check_feature_doc_matrix.py --against-ref origin/main --strict-impact`
- Machine-checked companion: `tests/unittests/test_psd_algorithm_doc.py`
  (doc exists; stage headings present; cited entry-point functions importable).
- `feature_doc_matrix.json` row: `psd_algorithm`. Sphinx/user pointer: link
  from `docs/source/user/user_guide.md` dose-calculation section (short pointer,
  no narrative duplication).
