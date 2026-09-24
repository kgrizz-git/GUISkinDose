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
3. **Source identifiers omitted by default** — `rdsr_filename`, `file_path`,
   `file_name`, kerma-meter `file`/`file_sheet`, exam `study_id`/`sheet` names,
   `input_sheet_name` (named sheets embed source text), per-exam
   `input_manufacturer`/`input_model` (raw vendor strings), and
   `corrections_db_path` are run-scoped identifiers or filesystem paths
   (runtime-privacy rule). They export as `null`/absent by default and are
   included only behind an explicit include-identifiers checkbox, mirroring
   the rich-export policy (`export.include_identifiers`). When identifiers are
   included, path-valued fields (`file_path`, kerma `file`) export as the
   user-facing **basename only** — never an absolute path. `file_path` is a
   `pathlib.Path` at runtime: the serializer must stringify-or-null it.

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
    "input_source_type": "dicom",
    "input_sheet_name": null,
    "swap_lat_lon": false,
    "flip_ap1": false,
    "flip_ap2": false,
    "kerma_meter_in_memory_table": { "equipment_key": { "tube_key": 1.02 } },
    "exams": [
      { "label": "Exam 1", "d_lon": 0.0, "d_ver": 0.0, "d_lat": 0.0,
        "table_origin_override": null, "table_origin_detected": null,
        "swap_lat_lon": false, "flip_ap1": false, "flip_ap2": false,
        "flip_tx": false, "flip_ty": false, "flip_tz": false,
        "source_type": "dicom", "schema": "dicom_rdsr", "sheet": null,
        "normalization_method": "Matched", "study_id": null,
        "file_name": null, "file_path": null,
        "input_manufacturer": null, "input_model": null }
    ]
  }
}
```

Notes on the example: `label` uses `guiskindose.privacy.opaque_exam_label`
("Exam 1"); `input_sheet_name`, `sheet`, `study_id`, `file_name`, `file_path`,
`input_manufacturer`, `input_model` show their **default (redacted) `null`** —
with include-identifiers they carry real values (`file_name` verbatim,
`file_path` **basename only**, never an absolute path). `kerma_meter_in_memory_table`
serializes the runtime `dict[tuple[str, str], float]` as a nested
`{"equipment": {"tube": factor}}` mapping (tuple keys are not JSON-serializable).
`input_source_type` ("dicom" | "csv" | "tsv" | "xlsx" | "") is included at the
`gui_state` root so `AppState` reconstruction does not have to derive it.

- `settings` covers every `settings_example.json` key — all selectable options
  (mode, `estimate_k_tab`, `k_tab_val`, `inherent_filtration`, `remove_invalid_rows`,
  below-floor policy + manual kVp, `beam_miss_warn`, `rotational_handling`,
  `include_static_pose`, `angular_step_deg`, plot prefs), **elliptic-cylinder/plane/
  table/pad dimensions** (`cylinder_length`, `cylinder_radii_a`/`cylinder_radii_b`
  semi-axes, resolutions, all length/width/thickness fields), phantom choice +
  habitus scales (`scale_lat`/`scale_ap`/`scale_lon`) + patient offset + orientation,
  the full `kerma_meter_correction` block (**correction factors**: `default_factor`,
  `explicit_label`, mode/file pointers — paths basename-only when identifiers are
  included, else `null`), `corrections_db_path` (redacted — filesystem path), and
  **`dosetrack_plane_code_map`**.
  Export-source caveats (Phase 3 mapping table records these as
  constant-vs-state-backed):
  - `plot_dosemap` is GUI state (`AppState.plot_dosemap`, Settings-tab checkbox);
    `build_settings()` force-writes `False` ("we handle plotting ourselves"), so
    the export reads the **AppState** value and import restores it to state.
  - `include_static_pose` / `angular_step_deg` have no GUI widgets (documented
    deferral) but are restorable import targets: each gets an `AppState` home
    (`None` = example-JSON default), `build_settings()` reads the home, the
    serializer reads the same home, and import writes it — so an imported
    non-default survives re-export. True constants stay out:
    `silence_pydicom_warnings` and the `build_settings`-forced plot constants
    (`plot.interactivity` / `plot.notebook_mode`) are emitted as constructed
    values and never applied.
  - `dosetrack_plane_code_map` is CLI-only today (`--plane-code-map`) but gets
    the same `AppState`-home treatment (`None` = `null` in GUI exports, set on
    import): the API path (`to_settings_dict()` of a settings object that has
    it) still preserves it, and the GUI path now round-trips it too.
  - `rdsr_filename` is a **legacy API field with no GUI source** (`build_settings`
    never sets it; the GUI tracks inputs per exam): GUI exports always emit
    `null` for it — even with include-identifiers — and import treats it as a
    constant. Per-exam `file_name`/`file_path` carry the real input identity.
    (The API path round-trips whatever the object holds.)
  - `kerma_meter_correction.explicit_label` is user/site equipment text: it
    rides the **include-identifiers gate** (`null` by default).
  - `colorscale` is bound in the GUI but **dropped by the `Plotsettings`
    constructor today** — Phase 1 must add it to `Plotsettings` or
    `to_settings_dict()` silently loses it.
  - `settings_example.json` carries a dead root-level `plot_event_index` key
    (ignored by the constructor in favor of `plot.plot_event_index`) — Phase 1
    removes it, so the dict-equality test is not poisoned by a key the object
    model never round-trips.
- `normalization_settings` is embedded because it is a separate constructor arg
  today yet materially changes results (vendor translation/rotation/field-size).
  Serialization contract: **Phase 2 deliverable** `NormalizationSettings.to_profile_list()`
  emits a profile-dict list round-trippable through its constructor input
  (`normalization_settings_list`), i.e. the on-disk JSON keys
  `translation_offset`, `translation_direction`, `rotation_direction`,
  manufacturer/models matching keys, `field_size_mode`, `detector_side_length`,
  `swap_lateral_longitudinal` — **not** runtime attribute abbreviations.
  Runtime-matched per-exam outcomes live in `gui_state.exams[]` instead
  (`normalization_method`, `source_type`, `schema`). The DICOM loader's meta
  dict lacks a `study_id` key today (tabular loaders set it) — the serializer
  reads `meta.get("study_id")` and Phase 2 does **not** patch the loader
  (uniformity is tested via `.get()` semantics, not new keys).
- `gui_state.exams[]` mirrors `loaded_exam_meta` **user-editable + reconstruction
  fields**: offsets (`d_lon`/`d_ver`/`d_lat`), `table_origin_override` +
  `table_origin_detected` (runtime type is a `{"x","y","z"}` dict populated at
  load, zeroed for tabular; the example's `null` is the export default while
  recompute-vs-cache remains an open question — handle the dict form if cached),
  coordinate toggles (`swap_lat_lon`, `flip_ap1`,
  `flip_ap2`, **`flip_tx`/`flip_ty`/`flip_tz`** — GUI-editable per-exam axis
  flips; omitting them silently changes reconstruction geometry), import context
  (`source_type`, `schema`, `sheet`), and `normalization_method`.
  Never serialized (runtime-derived or transient, rebuilt on load):
  `base_data` (pandas DataFrame), `loaded_exams` (`InputAdapterResult`), Plotly
  figures on `AppState`, `import_provenance`, `multi_exam_result`, and meta's
  `provenance` / `warnings` keys. Dialog-suppression flags
  (`below_floor_prompt_suppressed`, `rotational_prompt_suppressed`) are
  transient session UX state (auto-reset when the loaded data changes) and are
  an explicit **non-goal** — they are not exported and not restored.
- `gui_state.input_sheet_name` records the selected XLSX sheet (name or index)
  and rides the **include-identifiers gate** when it is a **string name** (named
  sheets embed source text; default export stores `null`, matching the redaction
  decision). **Integer sheet indices are positional and opaque — they are
  preserved even in redacted exports** (only string names are gated). The same
  rule applies to per-exam `sheet`: string names ride the gate, integer indices
  are preserved — re-export comparison after import must see the same policy on
  both sides.
- `gui_state.kerma_meter_in_memory_table` serializes session CF overrides
  (`AppState.kerma_meter_in_memory_table`, applied at calc time and omitted by
  `KermaMeterCorrectionSettings.to_dict()`): nested
  `{"equipment": {"tube": factor}}` JSON form.
- `schema_version` is a **single integer** (the example shows `1`): documents
  whose `schema_version` is **greater than the supported integer are rejected**
  with a clear error; **equal** versions are accepted, unknown keys are ignored
  (forward tolerance) and preserved on re-export. No major/minor split — there
  is no second component to gate on.

## Components

**Settings-slice assembly rule (normative):** the exported `settings` object is
built exactly as `to_settings_dict(build_settings(...))` **plus a documented
AppState-override overlay** — today only `plot.plot_dosemap` (source
`AppState.plot_dosemap`; `build_settings` force-writes `False`). Everything
else comes from the constructed `PyskindoseSettings`; forced constants
(`silence_pydicom_warnings`, `plot.interactivity`, `plot.notebook_mode`) and
the legacy `rdsr_filename` are emitted as their constructed values and are not
restorable choices (GUI always exports `rdsr_filename` `null`). State-backed
fields (`include_static_pose`, `angular_step_deg`, `dosetrack_plane_code_map`,
`normalization_profiles`, `corrections_db_path`) are read from their
`AppState` homes by **both** `build_settings()` and the serializer — one
source of truth per field. The applier inverts exactly this rule. Acceptance compares
**exports through this assembly path** (re-export comparison), never raw
`build_settings()` output — see acceptance #1.

| Piece | Location | Notes |
|---|---|---|
| `PyskindoseSettings.to_settings_dict()` | `settings/pyskindose_settings.py` | Emit the `settings_example.json` shape from the live object; `to_json()` convenience. Sub-object handling: `KermaMeterCorrectionSettings.to_dict()` **already exists** — reuse it; `PhantomDimensions` already has `to_dict_pad()`/`to_dict_cylinder()` — the `dimension` block composes those (no new colliding `to_dict()`); `PhantomSettings`/`Plotsettings`/`PatientOffset` gain focused `to_dict()`. Round-trip: `PyskindoseSettings(settings=s.to_settings_dict())` reproduces `s`, **including `dosetrack_plane_code_map`**. |
| Run-state serializer | `gui/run_state.py` (new, <300 lines; **not** `gui/helpers.py`, already ~634 lines) | Assemble document from `build_settings()` + `AppState`; redact identifiers unless opted in; never serialize `base_data` (DataFrame) or other runtime objects. |
| Run-state applier | same module | Validate schema/version, apply settings → widget-bound state fields (inverse of the assembly rule above), normalization → wrap `document["normalization_settings"]` in `NormalizationSettings(...)` first, then pass via the public `normalization_settings=` argument on `PyskindoseSettings` (the kwarg does **not** accept a bare list — it takes `Path | str | dict | NormalizationSettings | None`), gui_state → per-exam meta/toggles. **Import follows a three-tier rule. Tier 1 — derived data facts (never
  written):** `file_name`, `file_path`, `input_manufacturer`, `input_model`,
  and `study_id` describe the currently loaded files (rebuilt by every
  load/re-parse); the applier uses them for pairing verification and display
  only. **Tier 2 — picker-owned file handles (never downgraded):**
  `state.file_path`, kerma `file`, and per-exam absolute paths hold working
  absolute locations from user file-picking. Imported `null`s and basename-only
  values **never overwrite** them — a basename cannot restore a file location,
  and writing one over a working path would break the live session (so kerma
  `file` basenames are deliberately not written back; the same-inputs
  prerequisite requires the same kerma workbook to be loaded). Divergence warns
  loudly instead — loaded-file basename differs from the document's, or the
  document references a file that is not loaded — naming expected vs live,
  leaving the live value untouched. **Tier 3 — configuration (skip-if-null,
  apply-if-present):** every other non-null value applies — integer sheet
  indices (preserved even in redacted exports), real sheet names and kerma
  `file_sheet`/`explicit_label` when identifiers were included, and the
  AppState-homed keys (`normalization_profiles`, `dosetrack_plane_code_map`,
  `include_static_pose`, `angular_step_deg`, `corrections_db_path`). Absent
  keys equal redacted `null`s; sheet index `0` is guarded by `None`-check,
  never falsiness. An imported custom `corrections_db_path` that does not
  resolve fails loudly at calculation (honest failure beats silently using the
  default DB). **Restore `kerma_meter_in_memory_table`:** un-nest the JSON `{"equipment": {"tube": factor}}` form back to `dict[tuple[str, str], float]` on `AppState`. **Sequencing:** apply `input_schema`/`input_sheet_name` first and complete any required tabular **re-parse before** writing per-exam offsets/toggles — an async re-parse rebuilds `loaded_exam_meta` and would wipe restored offsets (race). **Dual-write couplings (both required):** coordinate toggles (global `swap_lat_lon`/`flip_ap1`/`flip_ap2` ↔ `loaded_exam_meta[0]` in single-exam sessions, per `import_preview` behavior) **and patient offsets** (global `d_lon`/`d_ver`/`d_lat` ↔ `loaded_exam_meta[0]` via the existing `offset_handlers.sync_global_patient_offset_to_single_exam_meta` / `restore_globals_from_exam_meta` helpers). **Import prerequisite (user-facing):** the same inputs must already be loaded in the same order/count; import applies corrections positionally and its error message names the diverging exam; when identifiers were included, `study_id` may be used to verify pairing before positional apply. **Import must trigger an explicit UI refresh (`reset_results()` + tab/per-exam rebuild) — mutating `AppState` alone does not reliably update already-rendered NiceGUI widgets.** |
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
   `KermaMeterCorrectionSettings` (reuse existing `to_dict()`), `PatientOffset`;
   `PhantomDimensions` `dimension` block composes existing
   `to_dict_pad()`/`to_dict_cylinder()` (no colliding new `to_dict()`).
   Add `colorscale` to `Plotsettings` (dropped by its constructor today).
   Remove the dead root `plot_event_index` key from `settings_example.json`
   (ignored by the constructor; poisons dict-equality tests otherwise).
   Tests (idempotence-based, **not** byte equality to the example file):
   load example → construct `PyskindoseSettings` → `to_settings_dict()` →
   reconstruct → assert second `to_settings_dict()` identical; table-driven key
   inventory vs the normalized example key set;
   `dosetrack_plane_code_map` round-trip on the API path (set it on a settings
   object, assert it survives); `--settings` accepts the **extracted
   `document["settings"]` slice** (not the whole run-state envelope).
2. **Phase 2 — run-state document.** Serializer + applier + schema validation
   (integer `schema_version` gate, key tolerance, redaction default). Adds
   `NormalizationSettings.to_profile_list()` (constructor-input key shape —
   `translation_offset`/`translation_direction`/`rotation_direction`).
   Serializes `kerma_meter_in_memory_table` in nested JSON form. `study_id`
   resolution: the serializer reads `meta.get("study_id")` (no loader patch —
   the DICOM loader's meta lacks the key by design). Unit tests with synthetic
   state (no fixture files): redaction on/off (incl.
   `input_sheet_name`, `input_manufacturer`/`input_model`, basename-only
   paths), `file_path` stringify-or-null, `base_data`/runtime-object exclusion,
   exam-count mismatch behavior, `schema_version` rejection.
3. **Phase 3 — GUI surface.** Export/import controls, include-identifiers
   checkbox, dialogs/notifications; `build_settings()` stays the single mapping
   point (import inverts it field-by-field via a constants-vs-state-backed
   mapping table kept next to `build_settings` so the two cannot drift).
   Phase 3 adds the five new `AppState` homes (`normalization_profiles`,
   `dosetrack_plane_code_map`, `include_static_pose`, `angular_step_deg`,
   `corrections_db_path`) and wires them through `build_settings()`; the
   serializer reads the same homes, so builder, applier, and serializer share
   one source of truth per field. Explicit post-import UI refresh
   (tab/per-exam rebuild). GUI tests mirroring
   `test_gui_rotational_prompt.py` style, asserting rendered widget values.
4. **Phase 4 — docs + closeout.** Help page (`docs/source/gui_help/` + sync),
   `feature_doc_matrix.json` entry, `CHANGELOG.md`, `TO_DO.md` item removal
   (impact logged first), plan archival when accepted slices ship.

## Acceptance criteria

- Export → clear GUI state → re-import (the same inputs already loaded in the
  same order/count — **including the kerma correction workbook when the
  document references one**) → export again: the two documents are **identical
  through the serializer's assembly path** (export → import → export
  comparison — never raw `build_settings()` output, which forces
  `plot.plot_dosemap` `False`), modulo redacted fields and the `created`
  timestamp. The exported per-exam fields (`gui_state.exams[]` key set)
  survive exactly, modulo redacted fields. Import never fabricates file
  locations: picker-owned paths round-trip as document values (identical
  basenames/`null`s on re-export under this prerequisite), and any divergence
  surfaces as a loud mismatch warning — never a silent overwrite or a blind
  basename write.
- Default export contains no source filenames, absolute paths, or exam labels
  beyond `opaque_exam_label` ordinals ("Exam N"); string sheet/study
  identifiers ride the gate (integer sheet indices are positional and exempt).
  Include-identifiers restores the gated values; path-valued fields
  (`file_path`, kerma `file`) are **basename-only** even then.
- All physics/phantom/correction fields listed under "document schema" survive
  the round trip — **explicitly including `normalization_settings`,
  `dosetrack_plane_code_map` (API and GUI paths via its `AppState` home),
  `include_static_pose`, `angular_step_deg`, `corrections_db_path`,
  per-exam `flip_tx`/`flip_ty`/`flip_tz`, `plot_dosemap`, `colorscale`, and
  `kerma_meter_in_memory_table`** (table-driven test enumerates them — no
  silent drops). `input_sheet_name` string names survive **when identifiers are
  included** (they are `null` in redacted exports by design); **integer sheet
  indices survive in both modes**.
- Import of a document whose `schema_version` exceeds the supported integer
  fails loudly; equal-version documents import with unknown extras preserved on
  re-export.
- After import, rendered GUI widgets reflect the imported values (Phase 3 test
  exercises the refresh path on live widgets — state-only assertions do not
  satisfy this criterion), and schema/sheet changes take effect without wiping
  restored per-exam offsets (re-parse sequencing).
- Existing runs unchanged: golden dose tests and `settings_example.json` behavior
  untouched when no export/import is used (the only example-JSON change is
  removing the dead root `plot_event_index` key).

## Testing

- `tests/unittests/test_settings_export.py` (new): Phase 1–2 coverage, table-driven
  field inventory (includes `dosetrack_plane_code_map` API round-trip, per-exam
  flips, `plot_dosemap`, `colorscale`, `kerma_meter_in_memory_table` nested
  form), redaction matrix (filenames, paths, study/sheet identifiers,
  `input_manufacturer`/`input_model`), basename-only paths when identifiers are
  included, `file_path` stringify-or-null, absent keys treated exactly like
  redacted `null`s on import, explicit falsy-guard test that sheet index `0`
  survives (`0 or None` collapse is a bug — `None`-check only), runtime-object exclusion
  (`base_data`, `loaded_exams`, figures, `import_provenance`,
  `multi_exam_result`), schema_version rejection, file-handle mismatch warnings
  (loaded basename differs from the document's; document references an unloaded
  file — live value untouched in both cases), imported custom
  `corrections_db_path` applied to its `AppState` home and read back by the
  serializer, `build_settings()` wiring for all five new homes
  (`normalization_profiles`, `dosetrack_plane_code_map`,
  `include_static_pose`, `angular_step_deg`, `corrections_db_path`).
- `tests/gui/test_run_state_roundtrip.py` (new): Phase 3 — export state → mutate
  every bound field → import → assert restoration **and widget-visible refresh**
  (rendered tab values, not just `AppState`); exam-count mismatch message names
  the diverging exam; schema/sheet change re-parse completes **before** per-exam
  offsets apply (no wipe); **both** single-exam dual-write couplings preserved
  (global toggles ↔ `loaded_exam_meta[0]`; global offsets ↔ `loaded_exam_meta[0]`
  via `offset_handlers` helpers); round-trip compares exports through the
  assembly path (export → import → export); file-handle mismatch warnings
  surface as user-visible notifications on import.
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

Round 1 (kimi-k3, step-3.7-flash, 2026-09-24): per-exam `flip_tx/flip_ty/flip_tz`
omission, `dosetrack_plane_code_map`, `input_sheet_name`, redaction gaps
(`corrections_db_path`/`study_id`/`kerma_meter_file_sheet`), `base_data`
DataFrame hazard, `build_settings()` return type in the acceptance criterion,
`NormalizationSettings` serialization contract,
`PhantomDimensions.to_dict_pad/cylinder` naming, NiceGUI refresh-on-import
risk — incorporated.

Round 2 (gemini-3.8-flash-high, composer-2.5, 2026-09-24): `colorscale` dropped
by `Plotsettings` constructor; dead root `plot_event_index` poisoning dict-equality
tests; `input_sheet_name` redaction contradiction; tabular re-parse vs per-exam
offset wipe race on import; `plot_dosemap` forced `False` by `build_settings`;
`kerma_meter_in_memory_table` (tuple-keyed, dose-affecting) missing;
`include_static_pose`/`angular_step_deg` not GUI state (mapping-table constants);
`dosetrack_plane_code_map` GUI-null semantics; normalization on-disk keys
(`translation_offset`/`translation_direction`/`rotation_direction`); import
prerequisite (same inputs, same order/count; `study_id` verify when present);
`input_manufacturer`/`input_model` redaction; single-exam dual-write coupling;
`opaque_exam_label` casing; `dicom_rdsr` schema example; never-serialized
runtime-object list; integer schema-version rejection rule; kerma basename-only
paths; `--settings` slice testing — all incorporated.

Round 3 (gemini-3.8-flash-high, composer-2.5, 2026-09-24): `schema_version`
major/minor language vs single-integer schema; `file_name`/`file_path` missing
from `exams[]` and the schema example; `rdsr_filename` has no GUI source (now a
documented legacy constant, GUI emits `null`); `kerma_meter_explicit_label`
gated; prompt-suppression flags declared non-goal; `study_id` key gap in the
DICOM loader meta; `input_source_type` added to `gui_state` root; `provenance`/
`warnings` never-serialized; `plot.interactivity`/`notebook_mode` constants;
`gui/run_state.py` placement — all incorporated.

Round 4 (gemini-3.8-flash-high **APPROVE** with 2 cosmetic; composer-2.5
REQUEST CHANGES, 2026-09-24): normative settings-slice **assembly rule**
(`build_settings` + AppState-override overlay) and acceptance switched to
export→import→export comparison (`plot_dosemap` conflict); single-exam
**offset** dual-write via `offset_handlers` helpers added to applier + tests;
`table_origin_detected` runtime dict type noted; integer sheet indices exempt
from redaction; Phase 1 tests made idempotence-based; `study_id` fork resolved
(serializer `.get()`, no loader patch); leftover "major-version" wording
removed — all incorporated.

Round 5 (gemini-3.8-flash-high + composer-2.5, 2026-09-24): applier
identifier fields skip-if-null (redacted `null`s/basename-only paths never
overwrite live state; non-null values apply); `kerma_meter_in_memory_table`
un-nests to
`dict[tuple[str, str], float]` on restore; serializer renamed to
`NormalizationSettings.to_profile_list()` (returns a list); `study_id` fork
closed to serializer-only; `exams[].sheet` inherits the integer exemption;
cosmetic fixes ("schema-version" test label, backtick typo, public
constructor-arg naming) incorporated.

Round 6 (gemini-3.8-flash-high **APPROVE** with 1 cosmetic; composer-2.5
REQUEST CHANGES, 2026-09-24): applier identifier rules rewritten as
skip-if-null; kerma `file`/`file_sheet`/`explicit_label` added to the skip
list; acceptance reworded for the integer exemption; review-notes wording
aligned.

Round 7 (gemini-3.8-flash-high + composer-2.5, 2026-09-24): identifiers split
into **derived data facts** (`file_name`, `file_path`,
`input_manufacturer`/`input_model`, `study_id` — never applied, pairing and
display only) vs **skipped-if-null configuration** (kerma paths/labels, sheet
selections, `corrections_db_path` — `null`s skipped, non-`null`s apply);
normalization applier wraps the list in `NormalizationSettings(...)` (the
`PyskindoseSettings` kwarg rejects bare lists); acceptance names the integer
sheet exemption; skip list covers per-exam paths too; absent keys equal
redacted `null`s; explicit falsy guard for sheet index `0`.

Round 8 (gemini-3.8-flash-high + composer-2.5, 2026-09-24): both reviewers hit
the same structural gap from opposite sides — cursor (REQUEST CHANGES) showed
imported `normalization_settings` and other non-widget restorable keys had no
`AppState` home, so `build_settings()` silently dropped them; agy showed kerma
`file` / `corrections_db_path` never restored. Import rules reworked into three
tiers: derived facts (never written), picker-owned file handles (never
downgraded — mismatch warns loudly instead of blind basename writes, which
would break live sessions since a basename cannot restore a location),
configuration via five new `AppState` homes (`normalization_profiles`,
`dosetrack_plane_code_map`, `include_static_pose`, `angular_step_deg`,
`corrections_db_path`) wired through `build_settings()` with the serializer
reading the same source; `include_static_pose` / `angular_step_deg` /
`dosetrack_plane_code_map` promoted from import-constants to restorable state;
round-trip prerequisite extended to the kerma workbook; unresolvable imported
`corrections_db_path` fails loudly at calculation.
