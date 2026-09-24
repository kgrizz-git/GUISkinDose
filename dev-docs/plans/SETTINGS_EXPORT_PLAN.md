# Settings Export / Import Plan — reproducible run state

Status: **planned** (not started). Backlog: `TO_DO.md` → "Reproducible settings export"
(GUI/UX). Scope decisions recorded below are settled; implementation phases are not begun.

## Objective

Export the complete GUI run state as a single JSON document that can be re-imported
to reproduce a run exactly — same physics, phantom geometry, corrections, and
import corrections — and load it back through the GUI, the API, or the CLI.

Today `PyskindoseSettings` accepts a dict or JSON string, and the CLI has
`--settings <file>`, but nothing serializes a live configuration back out, the GUI
cannot import one, and GUI-only state (per-exam offsets, tabular coordinate
toggles, input schema) is not representable at all.

## Scope decisions (settled)

1. **Full GUI run state** — not just the `settings_example.json` shape. The export
   embeds: (a) the settings dict, (b) `normalization_settings`, (c) GUI-only state:
   per-exam offsets and table-origin overrides, tabular coordinate toggles
   (`swap_lat_lon`, `flip_ap1`, `flip_ap2`), and `input_schema`.
2. **Export + GUI import** — round-trip is the acceptance bar. A Settings-tab (or
   Export-tab) "Save run configuration" / "Load run configuration" pair, plus API
   `PyskindoseSettings.to_settings_dict()` for programmatic use. CLI keeps
   `--settings` for the settings slice; a whole-document CLI flag is follow-up.
3. **Source filenames omitted by default** — `rdsr_filename`, `file_path`,
   `file_name`, kerma-meter `file`/`file_sheet`, exam `study_id`/`sheet` names,
   and `corrections_db_path` are run-scoped identifiers or filesystem paths
   (runtime-privacy rule). They export as `null`/absent by default and are
   included only behind an explicit include-identifiers checkbox, mirroring
   the rich-export policy (`export.include_identifiers`). Note `file_path` is a
   `pathlib.Path` at runtime: the serializer must stringify-or-null it (JSON
   serializability + no absolute paths even in memory dumps).

## Document schema (v1)

```json
{
  "schema": "guiskindose.run_state",
  "schema_version": 1,
  "app_version": "1.0.0",
  "created": "2026-09-24T00:00:00Z",
  "settings": { "...": "settings_example.json shape (PyskindoseSettings.to_settings_dict())" },
  "normalization_settings": [ { "...": "profile dicts as accepted by NormalizationSettings()" } ],
  "gui_state": {
    "input_schema": "auto",
    "input_sheet_name": 0,
    "swap_lat_lon": false,
    "flip_ap1": false,
    "flip_ap2": false,
    "exams": [
      { "label": "exam 1", "d_lon": 0.0, "d_ver": 0.0, "d_lat": 0.0,
        "table_origin_override": null, "table_origin_detected": null,
        "swap_lat_lon": false, "flip_ap1": false, "flip_ap2": false,
        "flip_tx": false, "flip_ty": false, "flip_tz": false,
        "source_type": "dicom", "schema": "auto", "sheet": null,
        "normalization_method": "Matched", "study_id": null }
    ]
  }
}
```

- `settings` covers every `settings_example.json` key — all selectable options
  (mode, `estimate_k_tab`, `k_tab_val`, `inherent_filtration`, `remove_invalid_rows`,
  below-floor policy + manual kVp, `beam_miss_warn`, `rotational_handling`,
  `include_static_pose`, `angular_step_deg`, plot prefs), **elliptic-cylinder/plane/
  table/pad dimensions** (`cylinder_length`, `cylinder_radii_a`/`cylinder_radii_b`
  semi-axes, resolutions, all length/width/thickness fields), phantom choice +
  habitus scales (`scale_lat`/`scale_ap`/`scale_lon`) + patient offset + orientation,
  the full `kerma_meter_correction` block (**correction factors**: `default_factor`,
  `explicit_label`, mode/file pointers — paths redacted per decision 3),
  `corrections_db_path` (redacted — filesystem path), and **`dosetrack_plane_code_map`**
  (accepted by `PyskindoseSettings`, settable via `--plane-code-map`, absent from
  `settings_example.json` — the serializer must emit it explicitly and Phase 1
  tests must cover it, since example-JSON equality cannot catch its loss).
  Note `silence_pydicom_warnings` is not GUI state (`build_settings` hard-codes
  `True`); the Phase 3 mapping table records which fields are constants vs.
  state-backed so import does not treat constants as restorable user choices.
- `normalization_settings` is embedded because it is a separate constructor arg
  today yet materially changes results (vendor translation/rotation/field-size).
  Serialization contract: `NormalizationSettings.to_dict()` emits profile dicts
  round-trippable through its constructor, preserving per-profile manufacturer /
  models matching keys, `field_size_mode`, `detector_side_length`,
  `swap_lateral_longitudinal`, `trans_offset`/`trans_dir`, and `rot_dir`;
  runtime-matched per-exam outcomes live in `gui_state.exams[]` instead
  (`normalization_method`, `source_type`, `schema`).
- `gui_state.exams[]` mirrors `loaded_exam_meta` **user-editable + reconstruction
  fields**: offsets (`d_lon`/`d_ver`/`d_lat`), `table_origin_override` +
  `table_origin_detected`, coordinate toggles (`swap_lat_lon`, `flip_ap1`,
  `flip_ap2`, **`flip_tx`/`flip_ty`/`flip_tz`** — GUI-editable per-exam axis
  flips; omitting them silently changes reconstruction geometry), import context
  (`source_type`, `schema`, `sheet`), and `normalization_method`.
  `base_data` (pandas DataFrame in meta) is **runtime-derived and never
  serialized** — import rebuilds it from the reloaded files; `study_id` is an
  identifier and rides the include-identifiers gate.
- `gui_state.input_sheet_name` records the selected XLSX sheet (name or index)
  so multi-sheet workbooks reload against the same sheet.
- `schema_version` gates import: unknown keys ignored (forward tolerance),
  newer-major rejected with a clear error; extras preserved on re-export.

## Components

| Piece | Location | Notes |
|---|---|---|
| `PyskindoseSettings.to_settings_dict()` | `settings/pyskindose_settings.py` | Emit the `settings_example.json` shape from the live object; `to_json()` convenience. Sub-object handling: `KermaMeterCorrectionSettings.to_dict()` **already exists** — reuse it; `PhantomDimensions` already has `to_dict_pad()`/`to_dict_cylinder()` — the `dimension` block composes those (no new colliding `to_dict()`); `PhantomSettings`/`Plotsettings`/`PatientOffset` gain focused `to_dict()`. Round-trip: `PyskindoseSettings(settings=s.to_settings_dict())` reproduces `s`, **including `dosetrack_plane_code_map`**. |
| Run-state serializer | `gui/helpers.py` or `gui/run_state.py` (new, <300 lines) | Assemble document from `build_settings()` + `AppState`; redact identifiers unless opted in; never serialize `base_data` (DataFrame) or other runtime objects. |
| Run-state applier | same module | Validate schema/version, apply settings → widget-bound state fields (inverse of `build_settings`, table-marked constants vs state-backed), normalization → `_initialize_normalization_settings` path, gui_state → per-exam meta/toggles. **Import must trigger an explicit UI refresh (`reset_results()` + tab/per-exam rebuild) — mutating `AppState` alone does not reliably update already-rendered NiceGUI widgets.** Positional exam matching errors name the diverging exam index/label. |
| GUI export/import controls | `gui/tabs/settings.py` (or export tab) | "Save run configuration…" / "Load run configuration…" using the existing `_write_or_download` native/browser pattern and an upload dialog; include-identifiers checkbox on export. |
| API/CLI | `pyskindose_settings.py`, `cli_args.py` | `to_settings_dict()` is the API surface; `--settings` already loads the settings slice — document that exported documents' `settings` key is accepted there. |

## Non-goals (explicit)

- Exporting calculation results (rich export / JSON export already exist).
- Capturing input file contents — the export references *corrections*, not data;
  the same input files are reloaded by the user.
- Per-client/server settings stores.
- `plot_event_index`-style run-command args beyond `mode` stay settings-resident only.

## Phases

1. **Phase 1 — settings round-trip (API).** `to_settings_dict()`/`to_json()` for
   `PyskindoseSettings`, `PhantomSettings`, `Plotsettings`,
   `KermaMeterCorrectionSettings`, `PatientOffset`, `PhantomDimensions`.
   Tests: dict equality against `settings_example.json` loaded defaults;
   `to_settings_dict() -> PyskindoseSettings -> to_settings_dict()` idempotence;
   `--settings` accepts the emitted document's settings slice.
2. **Phase 2 — run-state document.** Serializer + applier + schema validation
   (version gate, key tolerance, redaction default). Unit tests with synthetic
   state (no fixture files): redaction on/off, exam-count mismatch behavior,
   schema-version rejection.
3. **Phase 3 — GUI surface.** Export/import controls, include-identifiers
   checkbox, dialogs/notifications; `build_settings()` stays the single mapping
   point (import inverts it field-by-field via a constants-vs-state-backed
   mapping table kept next to `build_settings` so the two cannot drift);
   explicit post-import UI refresh (tab/per-exam rebuild). GUI tests mirroring
   `test_gui_rotational_prompt.py` style, asserting rendered widget values.
4. **Phase 4 — docs + closeout.** Help page (`docs/source/gui_help/` + sync),
   `feature_doc_matrix.json` entry, `CHANGELOG.md`, `TO_DO.md` item removal
   (impact logged first), plan archival when accepted slices ship.

## Acceptance criteria

- Export → clear GUI state → import reproduces the **`to_settings_dict()` output of
  the reconstructed `PyskindoseSettings`** (`build_settings()` returns a settings
  object, not a dict — compare its serialized form) and the exported per-exam
  fields (`gui_state.exams[]` key set) exactly, modulo redacted fields.
- Default export contains no source filenames, absolute paths, sheet/study
  identifiers, or exam labels beyond ordinal "exam N"; include-identifiers
  restores them; `file_path` is never emitted as an absolute path even when
  identifiers are included (stringify to the user-facing name only).
- All physics/phantom/correction fields listed under "document schema" survive
  the round trip — **explicitly including `dosetrack_plane_code_map`, per-exam
  `flip_tx`/`flip_ty`/`flip_tz`, and `input_sheet_name`** (table-driven test
  enumerates them — no silent drops).
- Import of a newer `schema_version` fails loudly; import of unknown extra keys
  succeeds and preserves them for future phases (re-export keeps extras).
- After import, rendered GUI widgets reflect the imported values (Phase 3 test
  exercises the refresh path on live widgets — state-only assertions do not
  satisfy this criterion).
- Existing runs unchanged: golden dose tests and `settings_example.json` behavior
  untouched when no export/import is used.

## Testing

- `tests/unittests/test_settings_export.py` (new): Phase 1–2 coverage, table-driven
  field inventory (includes `dosetrack_plane_code_map` and per-exam flips),
  redaction matrix (filenames, paths, study/sheet identifiers), `file_path`
  stringify-or-null, `base_data` exclusion.
- `tests/gui/test_run_state_roundtrip.py` (new): Phase 3 — export state → mutate
  every bound field → import → assert restoration **and widget-visible refresh**
  (rendered tab values, not just `AppState`); exam-count mismatch message names
  the diverging exam.
- No fixture files required (synthetic dicts only) — privacy gate unaffected.

## Open questions (resolve during Phase 3)

- Placement: Settings tab header vs. Export tab card — decide by which tab users
  reach for first during a smoke; default to Settings tab (state-centric).
- Whether `created` timestamps should be suppressed in a `--deterministic` test
  mode (nice for golden-file tests of the document itself).
- Whether `table_origin_detected` (computed, not user-set) should round-trip as
  a cache or be recomputed on import — recompute is safer unless divergence
  shows up in smokes.

## Review notes

Two plan reviews (kimi-k3, step-3.7-flash) requested changes 2026-09-24; their
findings (per-exam `flip_tx/flip_ty/flip_tz` omission, `dosetrack_plane_code_map`,
`input_sheet_name`, redaction gaps incl. `corrections_db_path`/`study_id`/
`kerma_meter_file_sheet`, `base_data` DataFrame hazard, `build_settings()` return
type in the acceptance criterion, `NormalizationSettings` serialization contract,
`PhantomDimensions.to_dict_pad/cylinder` naming, NiceGUI refresh-on-import risk)
are incorporated above.
