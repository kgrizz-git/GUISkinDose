# Equipment Profile Run-State & Rich-Export Contract Lock

Status: **Phase 0 contract lock (docs only).** This document locks the outstanding
run-state / rich-export versioning, privacy, backward-reader, and representation
contract for custom equipment profiles. **No run-state or export implementation is
complete** — §10 lists exactly what remains open. Design authority remains
[plans/CUSTOM_EQUIPMENT_PROFILES_SPEC.md](plans/CUSTOM_EQUIPMENT_PROFILES_SPEC.md)
decisions 13, 18, and 20; this lock supplies the coordinate persistence details needed to implement them and changes no agreed scientific or capability rule. Companion to
[EQUIPMENT_PROFILE_SCHEMA.md](EQUIPMENT_PROFILE_SCHEMA.md) (which stays under the
modularity cap by linking here instead of absorbing this section).

Execution tracking:
[plans/CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md](plans/CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md)
Phase 0 (privacy/export lock, run-state/rich-export bumps, representations).

## 1. Scope

Locked here: schema version bumps and migration behavior for run state and rich
reports; the default-safe vs gated vs never field matrix; old-document backward
readers; the four calculation-surface representations; normalized/preparsed
limitations; unsupported-domain behavior; and the self-contained reproducibility
rule (captured effective profiles/provenance/retained geometry — never reopening
mutable files or stores).

Not locked here and not implied: transmission evidence/grid/fallback (Phase 4
fixtures), GUI/CLI wiring and syntax, packaging, and any change to the 15-leaf
coordinate model, ladder order, capability gate, or hash rules.

## 2. Version bumps

| Document | Current | Locked next | Rule |
|---|---|---|---|
| Run state (`guiskindose.run_state`) | `schema_version` 1 (`src/guiskindose/gui/run_state.py:28`) | **2** | v2 adds the §3 `equipment` section; v1 documents keep today's reader (§5). |
| Rich report payload (`ExportPayload`) | `RICH_EXPORT_SCHEMA_VERSION` 3 (`src/guiskindose/export/models.py:34`) | **4** | v4 adds the §7 per-exam equipment block; v3 payloads stay valid (absent block = pre-feature report). |
| Dict/JSON result (`PySkinDoseOutput` / `MultiExamResult`) | `EXPORT_SCHEMA_VERSION` 3 (`src/guiskindose/format_export_data.py:45`) | **stays 3** | `equipment_profile_match` is additive-optional with the historical key set preserved (`format_export_data.py:638-640`); no bump while the change remains purely additive. A future incompatible change bumps to 4. |

Readers reject greater-than-supported versions loudly (run state already does at
`run_state.py:465-469`); older versions import best-effort with a warning
(`run_state.py:750-754` pattern retained).

## 3. Run-state v2 `equipment` section

v2 adds one top-level object with exactly `schema_version: 1`, `mode: "coordinates"`,
and `captures`: a positional list parallel to `gui_state.exams`. The envelope is
optional; `captures` contains one entry per exam, either `null` or a coordinate
capture. A present envelope must use supported versions/modes and match the exam
count before any state mutates. Reuse the core 64-profile, 10,000 aggregate-row,
and 8 MiB source limits; count capture recipes against those bounds before copying.

A coordinate capture has exactly these required keys:

- `match`: the API match mapping described in `equipment_resolution.py`, with all
  15 ordered leaf values and their source/revision metadata, notice, active-set hash,
  and session provenance. Validate its nested keys, scalar types, enums, and bounds.
- `effective_coordinates`: the complete 15-leaf coordinate object, using the common
  schema's eight fields, types, ranges, and nested shapes. It must equal `match.fields`.
  This is the executable recipe, with no inheritance left to consult at restore time.
- `input_identity`: `{manufacturer, model}` from the confirmed exam, text or null;
  compare canonical keys to the match and raw/loaded exam, never infer a maker.
- `matched_identity`: `{manufacturer, model}` display spellings captured from the applied
  receipt, both bounded nonempty text. Use the model label (manufacturer plus `*` for
  a wildcard) to rebuild complete notices; inherited labels come from validated entries.
- `event_count`: positive non-boolean integer, equal to the final retained frame count
  and `match.affected_event_count`.
- `geometry_hash_algorithm`: exactly `normalized-geometry-v1` (§6).
- `geometry_hash`: lowercase 64-hex checksum over confirmed retained numeric geometry.
- `capture_hash`: lowercase 64-hex SHA-256 over canonical serialization of this entire
  capture with `capture_hash` omitted, binding recipe, identity, geometry, and audit data.

Unknown envelope/capture/nested match keys are malformed. Captured notices must
match the deterministic renderer applied to validated structured fields/entries;
never trust saved free-text notice text as an output authority. Validation errors
use `RunStateError` with stable value-free codes: `invalid_equipment_capture`,
`unsupported_equipment_capture_version`, and `equipment_geometry_mismatch`;
these belong to the run-state reader, not the profile-source error enum. Existing unknown top-level
run-state passthrough remains outside this envelope. No file/store pointer is opened.
Original profile/source hashes and revisions are historical audit values: source content
is intentionally absent, so they cannot be independently re-derived on restore. The
capture checksum detects inconsistency; it is not an authenticity signature.

## 4. Privacy matrix (decision 13)

Default-safe (included without opt-in): manufacturer/model spellings, canonical
`matched_input_key`, profile IDs, match level/source, active leaf values,
inheritance/source summary, content hashes, session counters. This intentionally
replaces the current manufacturer/model gating at `run_state.py:155-178` in the
implementing slice — a v2 writer emits maker/model unconditionally.

Identifier-gated (existing `include_identifiers` / `include_source_identifiers`
only): source filenames, sheet-name strings, study IDs, kerma-table keys —
unchanged; input path exports remain basename-only when opted in. Station/serial values are **absent by construction**: the API receipt
and match mapping never carry them, so no equipment capture can leak them, gated
or otherwise; they stay confined to per-event exports behind the existing gate
and never enter logs.

Never captured, any gate: profile source paths (hashes only), bounded
free-text `notes`/`source` detail (explicit full-profile export only), absolute
paths, raw source text.

## 5. Migration and backward readers (decision 18)

- **v1 run-state documents** import exactly as today. A v1 document (no
  `equipment` section) applied while the live session holds custom profiles
  warns loudly that the document predates equipment capture; live session state
  is retained, never verified, never wiped.
- **v1 `normalization_settings` entries** keep the current compatibility reader
  (required keys checked at import, `run_state.py:712-729`): old vendor
  normalization profiles map into the shared loader as before. The Phase 2
  owner of the old run-profile compatibility reader stays the single place that
  reads pre-feature normalization-profile documents.
- **Absent or `null` v2 `equipment`** means "unspecified", never "clear": import
  skips equipment restore and leaves live equipment state untouched (same rule
  as the empty-`normalization_settings` guard at `run_state.py:774-777`).
- **Present v2 entries** are trial-validated as a complete candidate before any mutation.
  Validate schema/bounds/checksums, recipe/match agreement, identity and event count,
  then confirmed geometry. A malformed entry or mismatch rejects the whole import
  with an opaque exam position and value-free reason; retain previous frames, profiles,
  effective settings, receipts, results, and provenance. Never warn-and-skip one entry
  while applying the rest of the settings document.
- **Before raw load:** retain a validated pending capture and apply its full effective
  recipe during raw normalization before concept/field-size validation. Check retained
  count, canonical identity and resulting geometry checksum before publishing the exam.
- **Already loaded:** Phase 2 may restore only onto matching confirmed geometry. Changing
  loaded geometry requires the Phase 3 candidate re-normalization/rollback transaction
  from retained raw inputs. Missing raw inputs reject a requested change; never transform
  already-normalized coordinates a second time.
- **Future versions** (`schema_version` > supported) are rejected loudly; equal
  is accepted; older is accepted best-effort with a warning.

## 6. Self-contained reproducibility

A validated capture is a distinct **captured authority**, not a reconstructed live
`EquipmentProfileSession` and not a bare API application receipt. Its full effective
recipe can reproduce confirmed raw normalization without reopening profile files/stores
or consulting changed bundled leaf values. Original source provenance travels unchanged
as captured audit data, never as a claim that mutable sources were freshly verified.
The implementing slice must provide a typed captured context, validation and analysis
path; today's API live-session validator is insufficient and must not be bypassed.

`normalized-geometry-v1` locks column order to `Tx, Ty, Tz, Ap1, Ap2, Ap3, At1, At2,
At3, kVp, DSL, FS_lat, FS_long, DSD, DSI, DID, DSIRP`, in retained event order. Serialize
an object with `schema_version: 1`, this `columns` array, and `rows` (ordered arrays of
finite numeric values) using the common canonical JSON float rules (including +0.0 for
negative zero), then SHA-256 its UTF-8 bytes. Reject nonnumeric/nonfinite/missing values;
never include identifiers or DataFrame indices. The API's current private pandas-based
runtime fingerprint is not this persisted format. Implement explicit algorithm/version
validation and round-trip fixtures; do not persist an unversioned pandas fingerprint.

Import remains synchronous, GUI-light, and offline-safe; candidate normalization and
publication follow their phase's transaction boundary, not hidden I/O in the reader.

Geometry row counts at any boundary (checksum input, frame extraction, envelope
emission) are capped at the aggregate-row bound (10,000 retained rows); declared
lengths are checked before iterating and an actual counter binds iteration even
for lying lengths.

## 7. Representations (decision 20)

Match records are immutable snapshots at every surface, never mutable
`NormalizationSettings` fields. GUI rows are keyed by opaque exam position and show
selected source/profile ID, match level, each effective leaf and its inherited
source, the complete/partial notice, and active/unused profile IDs. Calculate uses
that confirmed capture; Results uses the capture attached to the completed result,
so a later settings change cannot rewrite old results. Transmission coverage and
status/source displays remain unlocked until Phase 4.

| Surface | Shape | State |
|---|---|---|
| Pre-calculation / Calculate / Results (GUI) | Effective leaves, inherited sources, notices, active/unused profiles per exam, before calculation | **OPEN** (Phase 2/3) |
| Python API results | `equipment_profile_match` mapping on dict/JSON (`analyze_data` → `receipt_to_mapping`); single-exam direct-capture analysis via `equipment_capture_context=` and multi-exam via positional `equipment_capture_contexts=` (clone, prepare, confirm, stored mapping); single-file replay with `equipment_capture_context=` via `analyze_input_file` (DICOM + raw vendor tabular) or `main` (DICOM only; run-state/GUI still open); multi-file replay with `equipment_capture_contexts=` via `analyze_multiple_input_files` (one capture or `None` per explicit file, ≤64 files, ≤10_000 aggregate retained events, splits refuse, loads private before calculation) | Implemented (7b8530e; direct-capture slices 2026-10-11; multi-file replay 2026-10-12) |
| Rich report (`ExportPayload` v4) | Per-exam equipment block: validated match, effective recipe, count and versioned geometry checksum; maker/model default-visible; provenance joins Settings & equipment | **OPEN** (Phase 5) |
| Run state v2 | §3 capture | **OPEN** (Phase 2) |

All four surfaces agree on values, precedence, hashes, and provenance per the
acceptance criteria; the API mapping shape in §3 is the canonical content every
surface carries.

## 8. Normalized / preparsed limitation

Coordinate sessions refuse `normalized` and preparsed-JSON inputs closed
(`check_session_input_compatible`; no raw fields to re-derive). Consequently
such exams never produce receipts, match mappings, or v2 captures: their
`equipment` entry is `null`, and rich reports omit their equipment block. This
is a limitation, not a fallback — silent application to already-transformed
geometry stays forbidden.

## 9. Unsupported future domains

The equipment capture carries **coordinates only**. Profiles with transmission
content are rejected by the current coordinate-only capability gate, including when
they also have coordinate leaves. No transmission row, factor, status, or evidence
value enters a capture until Phase 4 locks and implements those shapes. Unknown equipment sub-keys fail closed (§3); an
unsupported capture mode/capability is rejected during candidate validation before
any mutation or export.

## 10. Exact partial implementation (delivered stack vs still-open)

1. Run-state v2 `equipment` emission (`serialize_run_state`) and application
   (`apply_run_state` + trial-build coverage). Owner: Phase 2.
2. Rich-report v4 per-exam equipment block (collector + writer rows). Owner: Phase 5.
3. GUI pre-calculation / Calculate / Results equipment surfaces. Owner: Phase 2/3.
4. CLI wildcard-promotion flag. Owner: Phase 2. (CLI file-source syntax —
   repeatable `--equipment-profile` plus `--equipment-profile-sheet` — delivered
   2026-10-12; the promotion flag itself stays open.)
5. Old run-profile compatibility reader beyond today's `normalization_settings`
   handling. Owner: Phase 2 (single owner, nowhere else).
6. Typed captured authority, versioned geometry/capture checksums, strict validators,
   offline replay paths, and atomic pre-calculation validation (codec, confirmation,
   single/multi analysis, DICOM/tabular replay, single/multi-file public APIs) —
   **delivered**; open remainder: run-state v2 emission/application round-trip with
   rollback fixtures. Owner: Phase 2 at its boundary (see also item 1). Neither the
   phase nor items 1–5 are claimed complete by this lock.
7. Replacing the `run_state.py:155-178` maker/model gate with §4 default-safe
   emission. Owner: the v2 implementing slice.

Items 1–5 and 7 are still open, and no phase is marked complete by this lock;
item 6 records the delivered capture stack against its still-open run-state
remainder.
