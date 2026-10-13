# Maintenance Log

This file records "under-the-hood" maintainer-facing changes, such as refactoring, test additions, CI/harness improvements, and documentation updates that do not directly affect end-users.

For user-facing changes (new features, bug fixes, UI updates), see [CHANGELOG.md](../CHANGELOG.md).

Sections follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) categories (`Added` / `Changed` / `Fixed` / `Removed` / `Security`).

## [Unreleased]

- Radimetrics unknown-model diagnostics report only the model count; raw equipment names remain local.

### Changed

- **Equipment-profile delivery consolidation** (2026-10-13) — grouped engine/session/API work into
  one prerequisite PR and capture/replay/configuration/GUI work into a second PR, preserving the
  implementation commits and independently checking each base. Carried forward scanner, Windows,
  and CodeQL corrections; empty direct API application now fails before changing settings.
  XLSX source-hash tests compare the exact byte snapshot parsed, avoiding ZIP timestamp races.

- **Run-state/export contract lock (docs only)** (2026-10-11) — new
  `dev-docs/EQUIPMENT_PROFILE_RUNSTATE_EXPORT_CONTRACT.md` locks SPEC decisions 13/18/20 from actual
  seams: run-state 1→2, rich-report 3→4, dict/JSON export stays 3 while additive; default-safe maker/model
  keys vs absent-by-construction station/serial and never-captured notes/paths; v1 readers retained with
  atomic trial validation and capture restore; coordinates-only captures; self-contained reproducibility. Schema §16, spec,
  plan, and index link to it. No run-state/export implementation is complete (§10 open list stands).
- **Equipment API application review** (2026-10-11) — receipts publish after successful geometry
  normalization, rebind after final zero-kVp filtering, and verify normalized numeric geometry plus
  a fresh session resolution before analysis. Added regressions for same-count geometry changes,
  well-typed forged notice text, failed normalization publication, and final retained counts.
- **API slice review fixes** (2026-10-11) — custom field-size mode resolves before required-concept
  validation; receipts carry final retained counts (empty frames fail closed); new
  `EquipmentApplicationReceipt` binding validated at analysis boundaries with per-exam restore and
  summary refresh; fixed a latent crash where negative direction signs emptied hardcoded zero
  angle lists (`sign * [0] * len`). Covered by new gap tests; goldens unchanged.
- **First API coordinate slice (import-before-load)** (2026-10-11) — added
  `src/guiskindose/equipment_resolution.py` (session binding, raw-identity resolution after
  filtering, all-15 application to live normalization settings, default-safe serialization);
  typed never-serialized session parameter on `PyskindoseSettings`; resolution threading through
  the normalizer, adapters, main flows, and dict/JSON outputs; closed refusals for pre-transformed
  inputs. 24 targeted tests; ruff, basedpyright, complexity, size, and freshness gates clean. No
  GUI/run-state/CLI-flag/export-catalog changes; Phase 2 remains open.
- **Equipment-profile session assembly (inert)** (2026-10-11) — added
  `src/guiskindose/equipment_profiles/session.py`: `FileSource` requests with SPEC §8 path rules,
  `assemble_session()` combining file/memory/store sources with bounds before copying, canonical
  cross-kind conflicts, capability gate, single index compile, active-set hash, default-safe
  provenance, and per-exam `resolve()` over a prepared custom context (bundled compiled or
  prepared); public prepare/resolve seam added to `resolver.py`/`preparation.py` with
  `resolve_coordinate_leaves` preserved as a thin wrapper. Request collections bounded before copying
  with incremental ceilings; closed path boundary; revalidated snapshots with compiler-output payloads;
  canonical payload/provenance ordering; validated `__post_init__` contexts gating at preparation.
  Schema §15 documents the session contract. 54 session and 9 seam targeted tests; ruff, basedpyright, complexity, size, and freshness gates clean. No renderer/
  normalizer/settings/API/CLI/GUI/store activation wiring.
- **Sonar validation cleanup (equipment profiles, no behavior change)** (2026-10-11) — cleared the 172
  branch findings from the equipment-profile review without altering parser/privacy limits, immutable
  records, capabilities, or scientific contracts: `math.isnan` for all NaN idioms; negative-zero
  normalization via exact `+ 0.0` addition (bit-verified, no approximate compares); cognitive-complexity
  splits in `resolver`/`json_source`/`store_writes`/`dosetrack`; removed unused params, the redundant
  re-raise, the redundant `list()` call, and the redundant `UnicodeEncodeError`; statement-form depth
  traversal; tuple-form `endswith`; 121 exception tests hoisted to a single invocation, 6 broad assertions
  narrowed to `FrozenInstanceError`, 22 composite assertions split. Two `[0-9]` XML-coordinate regexes
  keep ASCII through explicit `re.ASCII` flags (`\d` alone would admit Unicode digits
  that `int()` accepts but OOXML forbids). No app wiring; Phase 2 remains open.
- **Equipment-profile coordinate resolution core (inert)** (2026-10-11) — added
  `src/guiskindose/equipment_profiles/resolver.py` (stdlib-only, immutable custom-exact ladder with
  capability gate first, per-leaf inheritance preserving `False`/`0.0`, missing-maker Default bypass,
  closed fallbacks, `CoordinateMatchRecord` reuse, structured notices),
  `src/guiskindose/equipment_profiles/bundled.py` (legacy settings → canonical profiles/indexes under
  `MAX_PROFILES` with order-independent deterministic IDs/hashes, per-entry materialized swap `False`,
  separate Default), and
  `src/guiskindose/equipment_profiles/vendor_aliases.py` (single alias home; settings re-exports
  unchanged names). Shared stdlib missing-identity convention in `keys.clean_identity_text`. Schema §14 documents the resolver contract. 63 targeted tests pin
  settings-selection parity, miss paths, capability tokens, store context, immutability, and privacy;
  ruff, basedpyright, complexity, size, and freshness gates clean. No renderer/normalizer/settings
  mutation and no API/CLI/GUI/store activation wiring.
- **Normalized manufacturer identity (Phase 1, no activation)** (2026-10-11) — new
  `src/guiskindose/exam_identity.py` seam (cleaning, raw/canonical pair listing, descriptive
  classification, fail-closed guard); `rdsr_normalizer()` emits a canonical `manufacturer` column and
  rejects anything but one canonical (manufacturer, model) pair per frame before profile selection —
  distinct makers, same-maker model variation, and known+unknown mixes all fail closed value-free, so
  row-0 selection only runs on proven-homogeneous frames; `normalized` schema recognizes optional
  `manufacturer`, materializes all-`None` with a count-only legacy warning when absent/blank, and checks
  each study-id group individually with opaque positions; DoseTrack maps each row's Equipment Name
  per-row through `MODEL2MANUF` (no first-name overwrite; count-only unknown warning); export
  maker/model come from one consistent row; `manufacturer` added to the normalized detection
  fingerprint as score-only. 63 targeted tests in `tests/unittests/test_exam_identity.py`; full-frame
  digest regen adds only the `manufacturer` column; golden dose/k_tab, GUI, CLI, and export suites
  green; ruff, basedpyright, complexity, size, freshness, help-registry, and UI-copy gates clean.
- **Equipment-profile index review fixes (inert)** (2026-10-11) — hardened `indexes.py` against review:
  bounded sequence intake (`MAX_PROFILES` before copying, bounded materialization, aggregate rows before
  expansion), strict entry context (exact-`str` source kind, exact-`int` revision in `1..MAX_REVISION`,
  lowercase-hex hash), structural pre-checks plus compile-time re-validation through the existing document
  boundary with claimed-hash verification (`conflicting_profile_metadata` on mismatch), ID-ordered conflict
  check, value-free reprs on all public types, single-normalization lookups, and deterministic no-traversal
  and full-equality tests replacing the wall-clock timing test. 66 targeted tests; ruff, basedpyright,
  complexity, size, and freshness gates clean. No application, GUI, CLI, normalization, or calculation code
  was touched.
- **Equipment-profile compiled indexes (inert)** (2026-10-11) — added
  `src/guiskindose/equipment_profiles/indexes.py`: immutable coordinate/transmission lookup compiled once
  from validated profiles with source-kind/hash/revision context. Coordinates resolve by canonical
  manufacturer/model (exact, alias, and manufacturer-scoped wildcard slots stored without activation);
  transmission resolves by canonical model/literal plane with original numeric row keys in sorted groups.
  Global conflicts run through the canonical check before publishing; retrieval bisects sorted key tables;
  internals are tuples only and results are source-order independent. 22 targeted tests cover compilation,
  retrieval, conflicts, determinism, immutability, lookup cost, and value-free diagnostics. No application,
  GUI, CLI, normalization, or calculation code was touched.
- **Equipment-profile first-sheet default** (2026-10-11) — align the XLSX adapter with the source-format
  specification: use the first worksheet unless an index is selected. This supersedes the draft requirement
  for explicit multi-sheet selection; explicit invalid indices still fail closed.

### Changed
- **XLSX preflight boundaries** (2026-10-11) — resolve worksheet namespaces and content-type parts before
  reading; reject mismatched, unordered, and out-of-budget coordinates; bound reader padding; preserve
  CSV-compatible numeric/boolean text and reject populated extra columns. Regression tests cover prefixed
  XML, nonstandard worksheet paths, and typed/text canonical equivalence.

### Changed

### Changed

- **Equipment-profile store hardening** (2026-10-11) — closed five remaining gaps in the inert store slice:
  enabled-revision listing uses LEFT JOIN and rejects a missing revision instead of silently omitting it;
  growth caps run in every transaction via bounded single-integer queries with total identities capped at
  1024; schema verification compares exact DDL text, forbids extra metadata keys and any trigger/view, and
  re-runs with a foreign-key violation check inside every transaction; stored payloads are byte-bounded
  before parsing with all failures normalizing to `store_corruption`; `set_enabled`/`delete_record` accept
  an optional `expected_generation`. No application, GUI, CLI, normalization, packaging, example, asset, or
  baseline file was touched.
### Changed

- **Equipment-profile store review fixes** (2026-10-11) — fixed nine commit-blocking defects in the inert
  store slice: matched save-CAS now compares after the record lookup (and updating requires an expectation);
  re-enabling excludes the candidate before appending it; saves to enabled records validate the would-be
  enabled set before commit; unexpected exceptions roll back, close safely, and normalize closed (reads use
  plain `BEGIN`, cancellation preserved); payload length/type is queried before the text is fetched and the
  parsed row count is rechecked; listings verify each payload; rows parse with no coercion; schema verification
  covers keys, types, constraints, triggers, and views; selections are length-checked before copying with
  duplicate IDs rejected and all integers range-checked before binding; NUL paths fail closed. The contract now
  requires CAS on update, bumps a `generation` token on every mutation, and tombstones deletes against ABA
  reuse. `profile_store.py` stays under the gates via `store_reads.py`/`store_writes.py` operation modules.
  No application, GUI, CLI, normalization, packaging, example, asset, or baseline file was touched.
### Changed

- **Equipment-profile local user store (inert)** (2026-10-11) — added
  `src/guiskindose/equipment_profiles/profile_store.py` (transactional stdlib-`sqlite3` repository) and
  `store_types.py` (frozen record/revision/snapshot types plus the locked revision-set hash), implementing
  the new §12 store contract. Fresh-empty creation at store schema version 1 with rejection of
  unversioned-nonempty, future, and corrupt databases without mutation; `BEGIN IMMEDIATE` writes with
  rollback; optimistic revision checks; payload re-parse, re-validation, and re-hash on every read; new
  records start disabled; enable-time canonical conflict validation; one-transaction snapshots with
  pre-materialization bounds. Five new closed `store_*` codes; `store_corruption` leaves the reserved set.
  Tests use `tmp_path` only and cover CRUD, two-handle CAS races, rollback, snapshot stability and
  determinism, conflicts, corruption/version rejection with byte-identical files, privacy, bounds, and
  default-path purity. No application, GUI, CLI, normalization, packaging, example, asset, or baseline file
  was touched; Phase 1 stays incomplete.
### Changed

- **Equipment-profile XLSX silent-loss fixes** (2026-10-10) — fixed two silent-loss defects in the inert
  XLSX adapter, both of which produced a *successful* parse with missing content. First, a row conversion
  truncated to the header width, so a populated cell beyond the 19-column header — including a formula or a
  spreadsheet error cell — was silently discarded; populated extra cells now fail the whole load, while blank
  padding outside the header is still tolerated. Second, openpyxl's read-only parser is dimension-driven, so a
  workbook rewriting its declared `<dimension>` to `A1:S3` was silently read as one profile and two rows; the
  adapter now validates every worksheet part with a bounded streaming `expat` parser that ignores the declared
  dimension for sizing and enforces the row, column, and cell budgets on the coordinates actually present,
  rejecting out-of-range, repeated, and malformed coordinates, DTDs, entity declarations, and external entity
  references. With the real bounds known first, the reader's dimension is discarded so an understated workbook
  is read in full and an overstated one cannot allocate padding it does not hold — no silent truncation in
  either direction — and the budgets are re-enforced on the reader's actual iteration. Also added a typed-cell
  policy that accepts a number or boolean only in a column whose schema type is that type (never coercing one
  into text or into `1`), with the coordinate `value` column resolved per leaf; a sheet-count ceiling read from
  the workbook's own worksheet catalog rather than archive part filenames; and one documented boundary over the
  whole untrusted-container path that normalizes any remaining library exception family to
  `malformed_container` with the cause suppressed and always closes the workbook. The schema contract's
  inaccurate "dimension truncation is a limitation" claim was removed. Tests cover both silent-loss
  regressions, understated and inflated dimensions, actual coordinate bounds and tampering, corrupt XML with a
  valid CRC, the typed-cell policy across every column kind, 20-column promotion headers, extra-cell
  rejection, and privacy. No binaries, assets, baselines, packaging files, or application code were touched.

### Changed

- **Equipment-profile XLSX adapter (inert)** (2026-10-10) — added
  `src/guiskindose/equipment_profiles/xlsx_preflight.py` and `xlsx_source.py`. The container is preflighted
  before any worksheet is read: the archive is opened from the in-memory byte snapshot, the entry list is
  bounded, duplicate and directory-spoofing entry names are rejected, and every member is inflated by
  streaming real decompressed bytes in chunks rather than trusting the central directory, so a forged
  `file_size` cannot smuggle a zip bomb. Worksheets are counted by iterating actual rows, and the sheet index
  is resolved from an explicit selection (mandatory for a multi-sheet workbook, otherwise sheet `0`).
  Typed-cell policy: numbers stay numbers, booleans are accepted only where the schema expects one and
  normalize to `true`/`false` (never coerced into `1` for a numeric column), dates are valid only in the
  `date` column and must be exactly midnight rendering as strict ISO `YYYY-MM-DD`, formulas are rejected
  rather than read as their cached value, and spreadsheet error cells are rejected. Typed cells convert
  straight to the flat text cells the shared CSV seam consumes, so there is no CSV round trip and no second
  flat parser. openpyxl is imported inside the adapter functions, so a JSON/CSV/TSV-only use never loads the
  spreadsheet stack. Every failure carries source kind `xlsx` and an allowlisted column, `record_type`, or
  integer count; sheet names, paths, cell text, and library messages never appear, and raw causes are
  suppressed. Tests build workbooks in memory or under `tmp_path` so no tracked `.xlsx` binary is committed,
  and cover CSV-to-workbook canonical equivalence, sheet selection and errors, typed cells, strict
  headers/rows/types, formulas, errors, bounded snapshots, zip-inflation lies, container corruption, and
  privacy. Documented limitation: openpyxl's read-only parser is dimension-driven, so a lying declared
  `<dimension>` can only ever reduce the rows yielded; the budgets are enforced on actual iteration and are
  authoritative in the unsafe direction, and such a workbook fails closed. The schema contract gained §6B,
  the plan records the XLSX adapter as implemented-and-inert with the user store as the remaining Phase 1
  adapter, and the packaged README and index note that the adapter is inert. No application, normalization,
  calculation, GUI, CLI, store, or packaging file was touched, no `.xlsx` binary was introduced, and no
  approved-asset inventory or scan baseline edit was made.
- **Equipment-profile CSV and TSV adapters (inert)** (2026-10-10) — added
  `src/guiskindose/equipment_profiles/tabular_common.py` (shared primitives: strict UTF-8 with optional BOM and
  no unpaired surrogates, strict header validation that never echoes a duplicate or unknown column name,
  row-width and record-type applicability checks, scalar/list/alias-map cell parsing) plus thin CSV and TSV
  adapters differing only in delimiter and accepted suffix. Both assemble the same canonical document mapping
  the JSON adapter produces, so the packaged CSV and packaged JSON have identical profile hashes, leaf values,
  and transmission values while their raw source hashes differ. Grouping is two-pass so coordinate and
  transmission rows may precede their `profile` row; repeated `profile` metadata may agree and disagreement
  fails `conflicting_profile_metadata`, while a repeated coordinate leaf fails `duplicate_json_key` even when
  identical. Tabular cells accept only the exact boolean forms `true`/`false`, reject `NaN`, `Infinity`,
  `1e999`, `8_0` and booleans as numbers, treat blank filtration as `blank_disallowed_cell`, and treat
  null-like strings as literal text. Every adapter failure carries source kind `csv`/`tsv` rather than `json`,
  and no raw cell, unknown column, file path, or nested exception cause is included. Bounds are enforced during
  row accumulation, before any profile object is built. Implemented with the standard library only — no
  third-party reader and no DataFrame materialization — reading the decoded byte snapshot once.
  `dev-docs/EQUIPMENT_PROFILE_SCHEMA.md` §6A restores the flat-column record-type table and blank semantics,
  naming the packaged README as the authoritative field dictionary; the plan records the JSON/CSV/TSV adapters
  as implemented and inert with XLSX still outstanding. No application, normalization, calculation, GUI, CLI,
  store, or packaging file was touched, and no source value, example, or scan baseline changed.

- **Equipment-profile JSON/core fixes and CHANGELOG entry** (2026-10-10) — fixed nine commit-blocking
  defects in `src/guiskindose/equipment_profiles/` found on review, with no application or numerical
  change: canonical `model_aliases` now serializes as a JSON object `{alias: target}` (resolving map
  targets to the listed model spelling so equivalent normalized spellings hash like the shorthand)
  instead of a list of pairs, with an active-set serialize/reload hash-equality test; missing
  required transmission numeric fields raise `missing_required_field` with their own field path
  instead of a `KeyError`; integers too large for a double raise `invalid_number` instead of leaking
  `OverflowError`; an empty `model_aliases` list means "no aliases" for multi-model and wildcard
  profiles, checked before the ambiguity rule; models with an empty normalized key are rejected and
  wildcard variants such as `" * "` are treated as the wildcard consistently, while transmission rows
  can no longer target the wildcard; file reads use one bounded `read(MAX_SOURCE_BYTES + 1)` instead
  of a read-then-check, closing the size/read race; conflict detection only lets non-empty coordinate
  profiles claim coordinate slots, expands claims across manufacturer and model aliases, rejects
  alias keys that would collide with a different model, and compares transmission keys on the
  normalized model key, so an alias equivalent to its own model stays allowed and coordinate-only
  versus transmission-only profiles may share an identity; `ParsedDocument.profiles` is typed
  `tuple[Profile, ...]`, depth errors use the caller's source kind, every document enforces the
  aggregate logical-row ceiling itself, and early count checks plus a traversal node budget bound work
  before a deep or broad mapping is walked. Added the missing `CHANGELOG.md` entry describing the core
  as experimental and inert, and corrected the plan so the Phase 1 item is explicitly **not** checked
  off complete. The doc contract (`dev-docs/EQUIPMENT_PROFILE_SCHEMA.md`) was updated to match every
  one of these behaviours.

- **Equipment-profile JSON/core slice, no application wiring** (2026-10-10) — corrected
  [EQUIPMENT_PROFILE_SCHEMA.md](EQUIPMENT_PROFILE_SCHEMA.md) into a normative implementation contract and
  implemented the stdlib-only core package `src/guiskindose/equipment_profiles/` that satisfies it. The core
  provides immutable typed frozen-dataclass canonical models; a closed privacy-safe error type and code
  constants; bounded JSON byte/path and in-memory parsing; full-v1 structural validation; deterministic
  canonical serialization with profile, active-set, and exact source-byte SHA-256 hashes; across-source
  duplicate and conflict validation; immutable match-record types; and a separate initial capability gate.
  Nothing is wired into dose, normalization, GUI, CLI, or store paths — the slice is inert scaffolding.

  Contract corrections applied from review: it is an implementation contract rather than an executable
  reference; the root envelope holds only `schema_version` (exact integer `1`, a boolean is not an integer) and
  a non-empty bounded `profiles` array; six coordinate blocks with 15 individually optional nested leaves;
  unknown keys rejected at every level; duplicate JSON object keys rejected through an `object_pairs_hook`;
  `null` is not omission; strict UTF-8 with an optional BOM. Identity reuses the existing normalized
  manufacturer/model key algorithms with no bundled alias inheritance; JSON alias shorthand is an array only
  (`|` separators remain a tabular spelling); alias-map targets must resolve to a listed model and
  normalize-unique aliases; empty aliases normalize to absent. Duplicate rules: `profile_id` duplicates fail
  across logical profiles and sources even when identical; duplicate coordinate claims fail even when
  identical; duplicate transmission keys fail within and across profiles independent of manufacturer; only a
  tabular grouping may repeat metadata that agrees. Bounds now include `models` ≤ 32, XLSX ≤ 16 sheets, JSON
  depth 16, and an explicit logical-row definition for JSON/memory. Canonical serialization normalizes numeric
  leaves to float while `schema_version` stays integer, omits empty optional texts/maps/arrays/blocks and
  `false` promotion, sorts models / alias sets / transmission rows / active profiles by exact ID, and wraps
  profiles as `{"schema_version":1,"profile":…}` and active sets as
  `{"schema_version":1,"profiles":[…]}`, including provenance and excluding source context; the stored
  revision-set hash is explicitly not locked. Per-leaf provenance carries revision, profile hash, and source
  kind (`memory` added); `inherited` covers lower-priority custom wildcards; the illustrative match record
  uses a partially supplied profile ID because a complete example cannot claim a bundled inherited leaf. Error
  field paths use allowlisted names only and never echo an unknown user key; raw exception causes are
  suppressed; `store_corruption`, `existing_model_out_of_extent`, and `explicit_sqlite_collision` are reserved
  codes, not implemented.

  Store schema and migrations, run-state and rich-export version locks and backward readers, CSV/TSV/XLSX
  adapters and fixtures, transmission eligibility/evidence/grid work, the invalid-example fixture set, and
  `MANIFEST.in` packaging inclusion remain outstanding, so Phase 0 is not complete. No application code, test
  fixture, or packaging file was touched beyond the new package and its tests.

- **Equipment-profile common + coordinate contract lock** (2026-10-10) — added
  [EQUIPMENT_PROFILE_SCHEMA.md](EQUIPMENT_PROFILE_SCHEMA.md) as the executable Phase 0 reference for custom
  equipment profiles: allowlisted field model for nested JSON, the flat 19-column tabular shape plus the
  optional `promote_coordinate_wildcard` column with implicit v1, alias-list shorthand versus explicit
  alias-to-model maps, finite-number/boolean typing and sign/field-mode enums, ingestion bounds (8 MiB file
  bytes, 10,000 aggregate rows, 64 profiles, bounded aliases/text/IDs), blank-cell and unknown-field
  semantics, bounded value-free errors with a stable code catalog, canonical serialization (negative-zero
  normalization, numeric equivalence across JSON and tabular) with SHA-256 profile/active-set/source hashes that
  cover profile content and provenance but never source context, cross-profile conflict rules, immutable
  per-leaf match-record shapes, and the coordinate activation capability gate (exact-only; fail closed on
  aliases/wildcards/transmission while the canonical parser still represents full v1). Registered in
  `dev-docs/index.md`, linked from the spec and execution plan, and the applicable Phase 0 plan items are marked
  locked with delivery pointers. Explicitly **not** full Phase 0 sign-off: user-store schema and migrations,
  run-state/rich-export version locks, XLSX fixtures and approved-asset inventory evidence, transmission
  eligibility/evidence/grid fixtures, the invalid-example fixture set, and `MANIFEST.in` packaging inclusion
  remain for later slices. No application code changed and no scientific rule was reopened; where the spec left
  a routine engineering value unspecified, a conservative explicit value was chosen and recorded. Transmission
  matching key remains model + plane + kVp + Cu + Al.

- **Equipment-profile fallback decisions** (2026-10-10) — amended the spec and execution plan so missing
  custom coverage retains ordinary lookup, new-model rows work without an original table, and sparse
  additions cannot damage usable interpolation. Defined protected unknown evidence, alias targets,
  wildcard promotion and implicit-v1 tabular rules; replaced the blanket implementation hold with
  per-slice contract locks. Example README synchronized; runtime behavior is unchanged.

- **Equipment-profile design readiness** (2026-10-10) — reviewed the spec and execution phases,
  recorded unresolved Phase 0 contracts before calculation changes, and clarified the synthetic
  example documentation. Added guidance to split large PRs while preserving atomic audit and
  migration contracts. Accepted only the new synthetic CSV-header heuristic in the phi-scan
  baseline, preserving all earlier entries and expiry dates.

- **2026-10-07 manual smokes recorded** (2026-10-09) — the agent-run smoke pass for shipped features
  now lives in the plans instead of `TO_DO.md`: multi-exam upload/calculate/per-exam offsets
  ([plans/archive/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md](plans/archive/MULTI_EXAM_GEOMETRY_OFFSETS_PLAN.md),
  [plans/archive/multiple-exams.md](plans/archive/multiple-exams.md)), correction safety and tube
  identity, the Results table, Settings phantom preview
  ([plans/archive/SETTINGS_PHANTOM_PREVIEW_PLAN.md](plans/archive/SETTINGS_PHANTOM_PREVIEW_PLAN.md)),
  the rich-export browser modal ([plans/RICH_EXPORT_PLAN.md](plans/RICH_EXPORT_PLAN.md)), and the
  kerma-meter CF browser GUI
  ([plans/archive/KERMA_METER_CF_WORKFLOW_PLAN.md](plans/archive/KERMA_METER_CF_WORKFLOW_PLAN.md)).
  The pass found and fixed stale Results/sidebar totals after invalidation, a
  `--input-preview-only` run ignoring `--plane-code-map`, and the duplicated "Exam Exam 1" heading.
  `TO_DO.md` → Manual Smokes keeps only the user-only passes (native pywebview windows, Windows
  native file dialogs).

- **Upload auto-detect failure hint** (2026-10-09) — the GUI retry text names the marker, the
  two-column floor, and the two-source stop. `tests/gui/test_rdsr_unit_error.py` pins that
  wording and checks that the detector's header text is not shown.

- **Schema detection provenance + notice helper** (2026-10-09) — `InputProvenance` records
  `detection_mode` and `matched_column_count`; `schema_detection_notice_lines` drives import-preview
  copy from `ui_copy.json`.

- **generic_rdsr_like trigger exclusions** (2026-10-09) — `stationname` and `deviceserialnumber`
  join `manufacturer` and `kvp_kv` in `_TRIGGER_EXCLUSIONS`; user and maintainer docs updated.

- **Schema-detection prose matched to measured recall** (2026-10-09) — the maintainer page
  states the 24-name Radimetrics fingerprint and the 13- and 12-hit counts on the shipped
  examples. `stubs.py` no longer claims those vendors are `--input-schema` choices.

- **Auto-detect hit floor** (2026-10-09) — `_AUTO_MIN_HITS` is 2. `(rf)` matches only when the
  cell text through `(rf)` is the start of a known Radimetrics column. Tests cover a lone marker,
  `Modality (RF)` beside two plain Radimetrics names, and a two-column election. The user page
  and `INPUT_SCHEMA_DETECTION.md` state the floor.

- **Input-format docs checked against detection constants** (2026-10-09) —
  `test_input_schema_doc.py` requires the user page and `INPUT_SCHEMA_DETECTION.md` to mention
  the Radimetrics trigger substrings, the DoseTrack electors, `MODEL2MANUF`, and the stub
  vendor names.

- **Radimetrics detection triggers removed from the backlog** (2026-10-08) — auto-detect
  now requires a distinctive marker (`registry.py` trigger sets). The product-backlog item
  is done; the user-facing behavior is in `CHANGELOG.md`.

- **Tabular import CLI review fixes** (2026-10-08) — `TABULAR_SUFFIXES` is defined once in
  `import_options.py`; preview rejects non-tabular and mixed lists before load and expands globs;
  GUI plus `--export-format` still launches the GUI; preview override lines skip `swap_lat_lon` on
  the `normalized` schema; CLI dispatch tests cover glob preview, non-tabular preview, aggregate
  preview, GUI flags, export-plus-DICOM, `python -m guiskindose.main`, and an end-to-end
  `--swap-lat-lon` PSD change.

- **Schema detection confirmation plan archived** (2026-10-09) — execution plan moved to
  `plans/archive/SCHEMA_DETECTION_CONFIRMATION_PLAN.md`.

- **TabularImportOptions CLI plan archived** (2026-10-08) — Phases 0–3 complete; execution plan moved to
  `plans/archive/TABULAR_IMPORT_OPTIONS_CLI_PLAN.md`; vendor-coordinate and tabular-input docs updated.

### Fixed

- **Import-preview caption survives a partial provenance** (2026-10-09) —
  `schema_detection_notice_lines` reads `detection_mode` and `matched_column_count` with
  `getattr`, so a stand-in that only has `schema_name` hides the caption instead of raising.
  The import-preview coverage controller now stubs `schema_detection_caption`.

- **RDSR CodeQL cleanup** (2026-10-08) — explicitly mark the normalizer's input-error
  imports as public re-exports with an explicit `__all__` list and explain the characterization helper's missingness-check
  exception fallback, preserving existing behavior.

### Added

- **Native-window startup test moved to `tests/gui` and isolated from the shared NiceGUI app**
  (2026-10-07) — `test_run_gui_native_persists_normalized_macos_startup` failed intermittently with
  "Cannot add middleware after an application has started" when unit and GUI tests shared a worker,
  because `run_gui()` registers middleware on NiceGUI's process-wide app. The module now lives
  in `tests/gui`, whose autouse `_isolate_loopback_security` fixture already stubs
  `app.add_middleware`.

- **SonarCloud scan waits on the Quality Gate** (2026-10-05) — `sonar-scan` now passes
  `sonar.qualitygate.wait=true`, so a red gate on `main` fails the job and files a CI
  tracking issue. Before this, PR #134's S2083 false positive turned the gate red while
  the job stayed green and no issue was filed. `test_ci_scanner_security_policy.py`
  now pins the flag.

- **Complexity gate foundation** (2026-10-03) — added a Ruff C901 checker with
  AST-qualified function names, a reviewed baseline of 20 grandfathered caps,
  and focused tests. Follow-up added commands for cap reductions and reviewed
  rename migration, plus Git-history checks against committed cap increases.
- **Complexity gate enforcement** (2026-10-03) — wired `python scripts/check_complexity.py`
  as a pre-push hook (locked `uv run` entry) and a `static-analysis` CI step with
  PR base fetch and main-push `COMPLEXITY_BEFORE_SHA` context; documented in
  `dev-docs/HARNESS_ENGINEERING.md`. A local Sonar gate follow-up split cap-entry
  validation and a composite test assertion.
- **Complexity gate review fixes** (2026-10-03) — compare caps against the current
  PR base tip so stale branches cannot restore caps reduced on `main`; added
  regression cases for branches diverging before and after the baseline. CodeRabbit
  follow-up bounded Git history reads, kept cap blobs byte-accurate, and allowed
  migrated caps to decrease or move through a reviewed rename chain. Windows CI
  exposed Git CRLF conversion in synthetic repos, so `.gitattributes` now pins
  the canonical caps file to LF on checkout.
- **Complexity migration guard** (2026-10-04) — `--migrate` now rejects a move while
  the old function still scores above the limit, before changing the caps file.
- **Complexity gate correctness follow-up** (2026-10-04) — isolated Ruff C901
  measurement from lint suppressions, validated historical caps against their own
  Ruff version so upgrades remain possible, and allowed a cap lowered by `--update`
  to be migrated in the same change without weakening the non-increasing ratchet.
- **Complexity update records Ruff upgrades** (2026-10-04) — `--update` now rewrites
  `tool_version` to the locked Ruff version (still lowering or removing caps only), and the
  stale-cap error names `--update` as its repair command.
- **Local SonarQube issue review reminder** (2026-10-04) — the opt-in pre-push
  freshness hook now prompts review of newly introduced issues, especially bugs
  and vulnerabilities; agent guidance and the local runbook describe manual triage
  even when the quality gate passes.

### Security

- **Semgrep pin 1.178.0 to 1.179.0; PyJWT 2.13.0 to 2.15.1 in the scanner lock** (2026-10-07) — semgrep
  1.179.0 relaxes its pin to `pyjwt[crypto]>=2.15.0,<3`, so `tools/semgrep/uv.lock` now carries a patched
  PyJWT. This fixes the moderate PyJWT advisory reported against that lock and lets the older
  alerts that were dismissed as unreachable close. `click` and `mcp` pins are unchanged. The PyJWT
  TO_DO item is removed.

- **multidict 6.7.1 → 6.9.1** (2026-10-05) — lock bump for GHSA-54p9-h82j-f925
  (reference leak in `CIMultiDict`/`MultiDict` items-view set operations), which
  blocked the `pip-audit` pre-push hook.
- **Thirteenth PyJWT alert on the Semgrep lock dismissed** (2026-10-01) —
  Dependabot alert 32 (GHSA-gvp8-978c-rx2q) is the same family as alerts 20–31:
  PyJWT 2.13.0 in `tools/semgrep/uv.lock`, the isolated scanner, never a runtime
  dependency and never shipped. This one is specifically `jwt.decode()` mutating a
  reused `options` dict when `verify_signature` is false. The only `jwt.decode` in
  semgrep 1.178.0 is `IntrospectionTokenVerifier.verify_token`, reached only when
  `semgrep mcp` starts its server; the gates run `semgrep scan` only. `semgrep/cli.py`
  imports that module eagerly, so jwt loads on every invocation, and unreachability
  is the call, not the import. The copy-before-mutate fix is already in the pyjwt
  2.14.0 tag; semgrep still pins `pyjwt[crypto]~=2.13.0`, and GitHub had not yet
  stamped a patched version on the advisory. Dismissed `not_used`.

- **Loopback launch probe and bootstrap redirect** (2026-09-26) —
  `probe_own_server()` now sends a random `x-guiskindose-probe` nonce and
  requires `x-guiskindose-proof` = HMAC-SHA256(`probe_secret`, nonce) from
  the middleware's 403, so a process that races the chosen port and copies
  the public refusal body no longer receives the auto-opened token URL.
  `_redirect_location()` collapses leading `/` and `\` so a `//host` path
  cannot become a protocol-relative `Location`. Follow-up to the #118
  security reviews; both gaps predated that PR.

### Changed

- **TO_DO backlog refresh** (2026-10-08) — rewrote the stale *Biplane support and
  recognition* item to *Independent per-plane geometry* (A/B detection and combined
  maps already ship). Moved GUI network-exposure follow-on to Deferred Until Needed
  (loopback refusal shipped). Narrowed the docs-build notebook item to a Sphinx/RTD
  confirm after the plot/HTML and tqdm fixes. Noted Playwright is already in `[dev]`.
  Linked visual refinement to `gui-aesthetic-redesign.md`. Next Up now has
  Radimetrics detection triggers (TabularImportOptions CLI/API parity shipped and plan archived).
- **Archived finished execution plans** (2026-10-08) — moved shipped
  `NATIVE_WINDOW_GEOMETRY_PLAN`, `DEPENDENCY_AUDIT_PLAN`,
  `2026-07-12-GEOMETRY_PREVIEW_CONTROLS_AND_COMPOSITE_PLAN`, and
  `PR_CODE_REVIEW_FIXES_PLAN` under `plans/archive/`. Removed the leftover
  `NO_PATIENT_INTERSECTION_WARNING_PLAN` duplicate from `plans/` (archive copy
  kept, with `guiskindose` package names).
- **TabularImportOptions CLI plan** (2026-10-08) — added
  `TABULAR_IMPORT_OPTIONS_CLI_PLAN.md` for GUI-parity `swap_lat_lon` /
  `flip_ap1` / `flip_ap2`. Review tightened copy-based apply, full API
  threading, and non-tabular rejection before the RDSR branch.
- **Tabular import coordinate helper extracted to core** (2026-10-08) —
  `input_adapters/import_options.py` holds `TabularImportOptions` and the
  post-normalization Tx↔Tz / Ap1 / Ap2 apply path; GUI
  `_apply_transform_flags` delegates those three flags after local
  `flip_t*` and table-origin handling.
- **CLI coordinate flags wired through analyze/preview/export** (2026-10-08) —
  `--swap-lat-lon` / `--flip-ap1` / `--flip-ap2` reject non-tabular paths
  before RDSR parse. `python -m guiskindose.main` now delegates to
  `__main__.cli()`; that function dropped below the C901 cap of 14 so
  the grandfathered entry was removed.

- **Append-only history is exempt from the file-size cap** (2026-09-30) —
  `scripts/check_file_sizes.py` scans `src`, `scripts` and `dev-docs`, so `CHANGELOG.md` was
  already out of scope by sitting at the repository root, while this file was capped at 800 lines
  despite doing the identical append-only job. The difference was purely where each file lives.
  New `APPEND_ONLY_HISTORY` exempts this one by category rather than adding it to `WHITELIST`,
  whose own comment says outliers should be "eventually decomposed" — a log grows forever by
  design, so its number would need bumping forever.

  The cap was not a hypothetical nuisance here: fitting one new entry under it forced prose out
  of three existing, accurate, already-reviewed entries, so the gate degraded the record it
  exists to protect and charged the cost to whoever added the 801st line. That prose is restored
  in this commit. Archiving old entries remains worthwhile as gardening and stays in
  `dev-docs/TO_DO.md`, but it is no longer a push blocker. A test pins that the exemption is a
  named path rather than a blanket for `dev-docs/`.


- **The changelog gate accepts a comment-only source change** (2026-09-30) —
  `scripts/check_changelog.py` demanded a `CHANGELOG.md` entry for any `src/` diff, blocking a
  code comment. `CHANGELOG.md` scopes itself to notable *user-facing* changes and directs
  maintainer-facing work here, so a comment has no honest entry there. A `MAINTENANCE_LOG.md`
  entry now satisfies the gate when a Python source change touches only comments and blank
  lines.

  **How it decides, after getting it wrong twice.** The first version exempted any added line
  without a statement-like marker, so docstring prose qualified — and so did a bare
  `return None`. The second held added and removed lines to the same rule, which closed the
  "comment out the code" edit, but still classified the diff line by line: a real `++i` arrives
  as `+++i`, was mistaken for a `+++ b/path` file header and dropped, so `+# a note` beside
  `+++i` passed as comment-only. CodeRabbit found that one.

  The third version stops classifying lines. It reads the whole file at the base ref and at
  HEAD, lexes both with `tokenize`, discards COMMENT and NL tokens, and requires the remaining
  streams to be identical. That removes the bug class rather than patching it: a `#` inside a
  string is a STRING token, a docstring edit changes the stream and is refused, and anything
  unreadable or unlexable is refused rather than exempted. Two reviewers tried to construct a
  behaviour-changing counterexample and could not.

  Two consequences recorded deliberately. Comment directives that tooling honours
  (`# type: ignore`, `# noqa`, encoding cookies) are exempt, which is a judgement call pinned
  by a test — they change linter and type-checker outcomes, not what the program computes, and
  the required log entry records them anyway. And a *spacing-only* reformat now classifies as
  comment-only where the second version demanded a changelog entry — `x=1` to `x = 1`, added
  blank lines, backslash continuations. Review corrected an earlier draft of this sentence that
  said "a pure reformat", which was too broad: quote normalisation changes the STRING spelling,
  tab-to-space reindentation changes the INDENT token, and added parens add OP tokens, so all
  three are still refused. Verified all four. That means the gate would probably still have
  caught the accidental `ruff format` of `gui/app.py` earlier the same day, since real
  `ruff format` output touches quotes and parens — but probably is luck rather than
  enforcement, and `ruff format --check` remains the proper fix.

  The real root cause of both earlier failures was the tests, not the classifiers: each stubbed
  the layer above the bug and passed. The tests now stub only the git file read, so the
  production lexer runs. If a fourth version is ever needed, the policy recorded in the module
  is to delete the exemption instead and write the one changelog line.


- **Semgrep pin 1.168.0 to 1.178.0; the tool's Dependabot alerts triaged** (2026-09-30) —
  hash-locking the scanner in `tools/semgrep/uv.lock` made its dependencies visible to Dependabot
  and raised 15 alerts. That corrects a claim in the entry below: `dependabot.yml` scoping the pip
  ecosystem to `directory: /` governs Dependabot *updates*, not *alerts*, which come from the
  repository dependency graph and index every lockfile. So the alerts were the predicted
  consequence of hash-locking, arriving sooner and louder than described. They are not new
  exposure — they are the same advisories `[tool.uv.audit]` used to suppress.

  Three were mcp, needing 1.27.2/1.28.1, and are genuinely **fixed**: semgrep 1.178.0 pins
  `mcp==1.29.0`, and `click` moved 8.1.8 to 8.4.2 with it. Both gates were re-run on the new pin
  before the bump landed. The other twelve are PyJWT, all fixed only in 2.14.0 (one in 2.15.0),
  and semgrep still pins `pyjwt[crypto]~=2.13.0` in its newest release, so they are **not
  fixable** here without dropping the scanner. They are dismissed as not-used: the only
  `import jwt` anywhere in the installed scanner is `semgrep/mcp/utilities/token_verifier.py`,
  used by `IntrospectionTokenVerifier.verify_token()` and reachable only through `semgrep mcp`,
  which neither gate invokes. Review corrected an earlier claim here that named `semgrep login`
  as the JWT path: login validates an opaque 64-hex API token and contains no `jwt` reference at
  all. The conclusion held, but the stated mechanism was wrong, so the dismissal comments on the
  twelve alerts were rewritten too.

  Review also found that "no `SEMGREP_APP_TOKEN`" was an assumption rather than an enforced
  property: `tool_environment()` copied the ambient environment, and semgrep's `get_token()`
  prefers that variable and otherwise reads the settings file a past `semgrep login` wrote. So a
  developer who logged in once was sending their token from every local gate run. Both token
  channels are now closed by construction — the variable is popped and `SEMGREP_SETTINGS_FILE` is
  redirected into the gitignored tool venv — and `SEMGREP_SEND_METRICS=off` moved into the shared
  environment so both gates get it rather than only the OWASP one. Verified by running both gates
  with a token planted in the environment. Two further channels took another round to find; see
  below before reading "unauthenticated by construction" as complete.

  A second review round then found the wording still only *nearly* true: `SEMGREP_COOKIES_PATH`
  is read with `os.getenv` in semgrep's `app/session.py` rather than through its `Env` factory,
  so auditing the `SEMGREP_*` credential fields misses it, and an ambient value would replay a
  saved cookie jar to semgrep.dev from these gates. `MozillaCookieJar.load()` also raises an
  uncaught `LoadError`, so a stale path would abort a blocking gate for reasons unrelated to the
  scanned code. It is popped too, along with `SEMGREP_USER_AGENT_APPEND`, which appends an
  arbitrary string to the User-Agent of every request.

  A third round found the one that was not a credential at all and mattered more.
  `SEMGREP_URL` / `SEMGREP_APP_URL` is what `config_resolver` resolves `p/owasp-top-ten`
  against, so an ambient value decides **which rules the blocking gate enforces** — and the gate
  still passes. That is the same silent downgrade `semgrep_tool.py` already refuses for an
  unpinned `PATH` semgrep, undefended until now. It is *pinned* to `https://semgrep.dev` rather
  than dropped, with `SEMGREP_APP_URL` and `SEMGREP_FAIL_OPEN_URL` dropped so they cannot
  compete. The cost is real and accepted: pointing the gate at an internal mirror is now a
  deliberate code change instead of an environment variable.

  A fourth round, from CodeRabbit, found the one that was not Semgrep's variable at all.
  `AppSession` subclasses `requests.Session`, and `requests.utils.get_netrc_auth` reads `$NETRC`
  first and otherwise `~/.netrc`, attaching Basic auth from any entry whose machine matches the
  request host. A developer with a `machine semgrep.dev` line was therefore sending those
  credentials from every gate run — invisible to every audit so far, all of which looked at
  `SEMGREP_*` names and at Semgrep's own source. Demonstrated directly: with such an entry
  `get_netrc_auth` returns the login and password, and with `NETRC` forced to `os.devnull` it
  returns `None`. Forcing rather than dropping closes both sources at once, since a set `NETRC`
  stops requests consulting the home directory at all.

  The policy is declared once as `_DROPPED_TOOL_VARS` and `_FORCED_TOOL_VARS`, a reason per name
  — "tool", not "semgrep", because that blind spot was in the naming too. Four rounds of finding
  one variable at a time is evidence the ad-hoc pops were the wrong shape; a parametrised test
  covers every dropped name.

  Throughout, jwt unreachability never depended on any of this: the only use of the jwt API sits
  in `semgrep/mcp/utilities/token_verifier.py`, whose `PyJWKClient` and `jwt.decode` calls run
  only under `semgrep mcp`. A later review corrected the wording here — `semgrep/cli.py` imports
  that module eagerly, so jwt *is* loaded on every invocation. Unreachability turns on it never
  being executed, not on it never being imported; importing pyjwt runs none of the vulnerable
  paths. Revisit the pin when semgrep relaxes it.

  Two residuals recorded rather than closed. Ambient `HTTPS_PROXY` and the CA-bundle variables
  are neither dropped nor forced, so "fetches its rules from a known host" holds at the URL
  level and not against a TLS-intercepting proxy with an ambient-trusted CA. And the privacy
  runner forces `SSL_CERT_FILE` to the macOS system bundle while the OWASP runner does not,
  which predates this work but would matter to anyone behind a corporate CA.

- **Five code scanning alerts cleared** (2026-09-30) — four were genuine redundant imports in
  tests (`sqlite3` imported twice in two correction tests; `scripts.dump_sonar_issues` imported
  both ways, once module-level and once function-local) and are fixed. The fifth,
  `py/unused-global-variable` on `_STATIC_REGISTERED`, is a false positive: the variable is read
  at `app.py:98` on a *later* call, which is exactly what the idempotence guard is for, and
  CodeQL misses the cross-call read. It is dismissed rather than restructured, because
  `tests/gui/test_gui_security.py` monkeypatches that flag and `tests/gui/conftest.py` documents
  why it is deliberately not reset between tests — `functools.cache` would break both to satisfy
  a false alarm. None of the five carried a security severity.


- **No workflow persists the checkout token any more** (2026-09-30) — every
  `actions/checkout` across the seven workflows now sets `persist-credentials: false`, where
  only `sonar-scan` did. Without it the job's `GITHUB_TOKEN` stays in `.git/config` for the
  whole run, reachable by any third-party tool the job executes — and these jobs run plenty:
  semgrep with a registry-fetched ruleset, `uvx`-installed phi-scan and presidio, grype, and
  in `ci-latest` an entirely unpinned `pip install`. Two of those workflows can write
  (`issues: write` in `ci-latest`, `security-events: write` in codeql).

  Nothing needed the credential. No job pushes; `github-script`, the gitleaks action and
  `gh` all authenticate from their own token inputs or environment. Three jobs do run
  `git fetch` after checkout (`static-analysis`, `coverage-pr`, and the release gate), which
  still works unauthenticated because the repository is public — noted in a comment at each
  of those three checkouts, since that is the one thing a switch to private would break.

- **tornado 6.5.8 to 6.5.10** (2026-09-30) — clears GHSA-3hv7-mjh2-fv65 (unbounded query-string
  argument count stalls the event loop), GHSA-c2m8-h5v5-343r (`StaticFileHandler` follows symlinks
  outside the static root) and GHSA-chx6-46f5-w4vp (`CurlAsyncHTTPClient` enforces no
  response-size limit), all fixed in 6.5.9. Third instance today of the same pattern: published
  after the previous push, unrelated to the work it landed beside, already at the vulnerable
  version on `main`. Dev-only, reaching the lock through `ipykernel` and `jupyter-client` under
  the `docs` and `notebooks` extras — the GUI uses uvicorn, not tornado, so no user-facing path
  is involved.

- **virtualenv 21.4.2 to 21.14.1** (2026-09-30) — clears four advisories
  (GHSA-x78j-v8h9-3j2q, and PYSEC-2026-4011 / -4012 / -4013: unverified seed wheels,
  `pyvenv.cfg` prompt injection, and activation scripts executing commands embedded in
  paths). Same situation as the urllib3 bump below: published after the previous push,
  unrelated to the work it landed beside, and already pinned at the vulnerable version on
  `main`. Dev-only, reaching the lock through `pre-commit`. `python-discovery` moved 1.4.0
  to 1.6.1 with it as a transitive dependency.

- **urllib3 2.7.0 to 2.8.0** (2026-09-30) — clears GHSA-8988-9cw3-xx77 (HTTPS proxy TLS
  configuration may be ignored or overridden) and GHSA-vxq7-64xx-v4gw (`HTTPResponse.stream()`
  buffers an unbounded chunk-size line into memory), both fixed in 2.8.0. Published after the
  previous push and unrelated to the semgrep work it landed beside; `main` carried the same
  2.7.0 pin. Exposure was dev-only — urllib3 arrives through `requests` under the `dev`, `docs`
  and `notebooks` extras, not the `gui` runtime path — but the audit gate is blocking, and the
  fix is a clean single-package relock. `uv audit` now reports no known vulnerabilities.


- **Semgrep's isolated environment is now hash-locked, and the resolved version is asserted**
  (2026-09-29) — follow-up to the isolation entry below, which traded `uv sync --locked`'s
  sha256-pinned wheels for `uvx --from semgrep==<pin>`. That pin fixed the scanner's own version but
  re-resolved its ~68 transitive dependencies on every run with no recorded hashes, so a same-version
  re-upload would have been trusted. New `tools/semgrep/` is a standalone uv project — deliberately
  **not** a workspace member, since joining the workspace would merge those dependencies back into
  the root resolution and undo the isolation — and its `uv.lock` records 942 sha256 hashes.
  `scripts/semgrep_tool.py` now prefers `uv run --locked --project tools/semgrep`, falling back to
  `uvx` and then to a `PATH` semgrep. Verified: the locked run reports `1.168.0`, matching the
  inventory pin, and `semgrep` remains unimportable in the project environment.

  Two traps were specific to this repo's `.envrc`. It exports `UV_PROJECT_ENVIRONMENT=.venv`, and
  `uv run` honours it, so without redirecting it the hash-locked run would have installed semgrep and
  its pinned dependencies straight into the environment this design exists to keep them out of; the
  scanner environment is redirected to the gitignored `tools/semgrep/.venv`. That location is not
  arbitrary either: pytest's write-containment snapshot (`tests/conftest.py`) prunes directories named
  `.venv` at any depth but does **not** prune `tmp/`, and `tests/unittests/test_privacy_semgrep_rules.py`
  runs the scanner during the suite, so putting the environment under `tmp/` would have tripped the
  containment guard.

  Also closed the gap that nothing checked which version actually ran. A `semgrep` found only on
  `PATH` is now refused unless it reports the pinned version, because one that disagrees with CI makes
  the gate advisory without saying so, and a test runs the resolved command and asserts its
  `--version` output equals the inventory pin. The `--locked` flag is what makes the lock
  load-bearing: bumping the pin now requires editing the inventory *and* re-running
  `uv lock --project tools/semgrep`, and doing only one fails loudly. Review caught that
  `--locked` alone did not deliver that: it compares the tool manifest to its own lock and never
  reads the inventory, so an inventory-only bump gated green on the previous scanner and failed
  later in pytest. `semgrep_argv` now compares the two before returning the locked command, which
  puts the check where the security argument needs it.

  Three follow-up defects came out of review of that change, all fixed here. The
  privacy-rules test built its scan environment from `os.environ.copy()` rather than
  `tool_environment()`, so on any machine with direnv active it installed semgrep 1.168.0,
  `click 8.1.8`, `mcp 1.23.3` and `pyjwt 2.13.0` into the project `.venv` — reproduced
  directly, and invisible in CI because `.envrc` never runs there. `ci-latest.yml` had no
  `uv`, which is absent from the ubuntu runner image, so both weekly drift probes and the
  pytest step would have failed every Monday and opened a tracking issue that had nothing
  to do with drift. And an unpinned probe request with no `uvx` fell through to the pinned
  locked run, meaning a probe whose only question is "has the pin drifted?" would have
  answered "no" whatever upstream did; it now raises.

  **Not done, deliberately:** pinning the Semgrep *ruleset*. `--config=p/owasp-top-ten` is fetched
  from the registry on each run, so the rules are mutable and the gate needs network — a rule change
  upstream can turn a green local push into a red CI run. Vendoring the pack is not a plumbing task:
  all 559 rules in it carry `license: Semgrep Rules License v1.0`, none under the LGPL terms of the
  public `semgrep-rules` repository, so redistributing them in a public repo is a licensing question.
  The cheap alternative, if this ever bites, is a digest-drift check rather than a pin.

- **Semgrep isolated as a pinned `uvx` tool; all dependency-audit suppressions removed**
  (2026-09-29) — semgrep is no longer in the `dev` extra or `uv.lock`. Its own requirements
  (`click<8.2`, `mcp==1.23.3`, `pyjwt[crypto]~=2.13.0`) were the sole reason the project carried five
  `[tool.uv.audit]` suppressions (click PYSEC-2026-2132; mcp GHSA-jpw9-pfvf-9f58 /
  GHSA-hvrp-rf83-w775 / GHSA-vj7q-gjh5-988w; pyjwt GHSA-w6j9-cwv2-h6wq): it held those transitive
  packages below their fixed versions. Semgrep is only ever invoked as a CLI, never imported, so it now
  runs via `uvx --from semgrep==<pin>` (the pattern already used for `phi-scan`). Result: `click`
  upgraded 8.1.8 to 8.5.0, `mcp` and `pyjwt` left the lock entirely, `uv audit` reports zero
  vulnerabilities, and `ignore` is empty.

  **This is an audit-scope change, not remediation, and should not be read as one.**
  `semgrep==1.168.0` still declares `click~=8.1.8`, `mcp==1.23.3`, `pyjwt[crypto]~=2.13.0`, and its
  isolated environment installs exactly those versions — verified directly. The vulnerable code is
  still present and still executed by the scanner; it is simply outside the surface `uv audit`,
  `pip-audit`, Dependabot, and grype inspect. The genuine improvement is in the *project*
  environment, where `click` moved 8.1.8 to 8.5.0 — which reaches users, since uvicorn pulls click
  into the `gui` extra. For mcp and pyjwt, both dev-only before and after, only the audit scope
  changed. The tool environment was also unhashed at first, where `uv sync --locked` gave
  sha256-pinned wheels; that gap is closed by the `tools/semgrep` entry below.

  The pin lives in `dev-docs/privacy_tool_inventory.json` — already the tracked source of truth for
  scanner versions — and both entry points read it, so the hook and CI cannot drift. New
  `scripts/semgrep_tool.py` resolves the command (raising rather than skipping when nothing can run it),
  and new `scripts/run_semgrep_owasp.py` owns the OWASP ruleset, flags, and include-list for both the
  pre-push hook and the CI job. That unification fixed a real inconsistency: the CI job passed
  `--exclude` for `example_data` / `phantom_data` / `table_data` / `tests/fixtures` but the pre-push
  hook did not, so a local run scanned clinical-adjacent data the policy says not to feed a scanner.
  Both now exclude them (352 files scanned to 241) — which makes the local hook deliberately
  narrower than it was, not merely more consistent.

  **Trade-off, recorded deliberately:** Dependabot only sees `uv.lock`, so nothing auto-bumps the pin.
  The weekly `ci-latest` workflow now runs the OWASP scan against the newest semgrep
  (`GUISKINDOSE_SEMGREP_UNPINNED=1`) so drift and upstream breakage open a tracking issue; bumping the
  pin stays a human step, tracked in `dev-docs/TO_DO.md` alongside the same pre-existing gap for
  `phi-scan`.


- **Local interpreter pinned to Python 3.14** (2026-09-29) — `.envrc` now exports `UV_PYTHON=3.14`
  (deferring to an existing value) so the development environment matches the only version a pull
  request builds; 3.11–3.13 coverage still arrives on `main` pushes and the weekly sweep. Motivated by
  a real miss: Python 3.14 changed `PurePath.suffix` for leading-dot names, so a test passed on a local
  3.12 and failed both PR jobs. `uv sync --all-extras` resolves cleanly on 3.14 (including `nicegui`,
  `pywebview`, `pytest-asyncio`, `pytest-xdist`), and the full suite passes. The `>=3.11` floor stays
  guarded by `[tool.basedpyright] pythonVersion = "3.11"`, which is interpreter-independent; `AGENTS.md`
  documents a runtime floor check and warns that it must redirect `UV_PROJECT_ENVIRONMENT`, because a
  bare `uv run --python 3.11` rebuilds `.venv` itself as 3.11.

### Added

- **Debuggable write-containment failures** (2026-09-29) — the `tests/conftest.py` guard that fails a run
  when tests change the checkout used to print only a 12-hex SHA-256 token per path, which meant
  identifying the offending file required brute-forcing candidate paths through the same hash. The
  message now always adds *value-safe shape*: whether a tracked file was modified or a new file
  appeared, the top-level directory (named only when it is a conventional repository directory), the
  path depth, and the file suffix (only when it is an allowlisted extension). That is normally enough
  to locate the writer. Two opt-in levels go further for local debugging via
  `GUISKINDOSE_TEST_CONTAINMENT_HINT`: `masked` shows the first and last character of each name with an
  allowlisted suffix kept verbatim (`t…p/n…i.log`), and `full` shows the exact repo-relative path.
  Both are **refused when `CI` or `GITHUB_ACTIONS` is truthy** (and the footer says so, rather than
  appearing to ignore the request), and unset or unrecognized values fail
  closed to the token-only default, so neither a typo nor a workflow variable can widen disclosure in a
  world-readable log.

  Hardening found while reviewing the first draft of this change: `Path.suffix` is only "text after the
  last dot", so echoing it verbatim leaked the whole identifier for a name like
  `x.Lastname_Firstname_19700101`, and a shape pattern still admitted `.J` — a first initial dressed as
  an extension; the suffix is now an explicit extension allowlist. Short path segments were returned
  unmasked, which made masking the identity function for `tmp/J/D.dcm`; segments of one or two
  characters are now withheld entirely. Control, bidi, and line-separator characters are stripped so a
  crafted filename cannot forge log lines or reverse how the rest of the line renders. Report construction moved to a new pure `tests/containment_hint.py`, leaving the
  hook a thin adapter, with unit tests covering the disclosure contract, the CI refusal, injection,
  allowlist drift, cap boundaries, and the hook wiring itself.

- **Reliable local SonarQube coverage input** (2026-09-28) — `run_sonarqube_local.py --generate-coverage` now
  generates the same combined non-GUI + GUI coverage used by CI before analysis. Scan-only runs fail fast when
  `coverage.xml` is missing or older than Python inputs, preventing misleading 0% new-code gate failures.

- **Local SonarQube compose stack and weekly update check** (2026-09-26) —
  `compose.sonarqube.yaml` runs the local server with PostgreSQL, because the
  embedded H2 database does not support upgrades. It binds to loopback only
  and keeps data in named volumes. `scripts/sonar_update_check.py` lets
  `run_sonarqube_local.py` warn at most weekly when a newer server image or
  scanner exists. It is advisory and never updates anything. See
  `dev-docs/SONARQUBE_LOCAL.md`.

### Fixed

- **Order-dependent GUI auto-open tests** (2026-10-05) — three
  `test_browser_auto_open_*` tests failed under `pytest -n auto`, and when run alone, because
  conftest no-ops `_open_browser_when_ready` and they called that patched name. They now call
  the real function captured at import time, as the file already does for
  `_loopback_port_is_free`. CI ran `tests/gui/` serially, which hid the failure, so the
  `gui-smoke`, `coverage-pr`, and `sonar-scan` GUI runs now use `-n auto`.
  Parallel runs then exposed `test_import_updates_rendered_widget_values` (failed 3 of 11
  runs): its import re-parsed a nonexistent seeded file and rolled back, and the test only
  passed by catching the widget's transient value before the rollback. It now aligns
  schema/sheet first, as its sibling test does, and asserts the import kept `d_lon`.

- **SonarCloud security/reliability findings and SonarQube 26.9 test rules** (2026-09-26) —
  cleared the SonarCloud E security and C reliability drivers. `scripts/sync_ui_copy.py`
  drops its unused `--repo-root` option (the root is always the checkout) and mirrors with
  `shutil.copyfile`. `scripts/check_sonar_freshness.py` refuses a `--state` path outside
  the repository (`contained_path`: `os.path.realpath` + `startswith(root + os.sep)`).
  `scripts/dump_sonar_issues.py` confines the state file the same way and rebuilds it from
  known keys instead of echoing file content back to disk. Loopback `http://` origins carry
  a `# NOSONAR` (they must stay plain HTTP). Reliability: removed a redundant duplicate
  validation in `help_button.py`, added a generic fallback family to the bundled Material
  Symbols CSS, and replaced a self-comparison NaN assert. Test rules: split composite
  asserts (S9073), hoisted setup calls out of `pytest.raises` blocks (S5778), removed
  redundant fixture arguments and useless `yield`s (S9117/S9083/S9100), and moved
  non-singleton global mutations to `monkeypatch` (S8997). S8997 is suppressed for
  `tests/gui/**` in both Sonar property files because the autouse `_isolate_gui_state`
  fixture resets the `state` singleton around every test; `check_sonar_properties.py`
  now checks those suppression keys for parity.

- **Windows CI manifest-hash failure from CRLF checkouts** (2026-09-21) —
  scheduled `ci` failed only on `windows-latest` (issue #107):
  `correction_validation.py` hashes raw CSV bytes while Windows checkouts
  convert line endings without a `.gitattributes` policy. Added repo-wide
  `*.csv text eol=lf`, plus one `windows-latest` / 3.14 job on the push and
  PR build matrix so platform-specific failures surface before merge (the
  full OS matrix still runs on schedule). Note: `.gitattributes` governs fresh
  checkouts only — an existing Windows working tree keeps its CRLF copies
  until `git add --renormalize .` or a fresh clone. The new job immediately caught a
  second latent Windows-only failure: `test_resolve_explicit_and_warns_once`
  asserted the POSIX-only `/abs/custom.db` is absolute (drive-relative, not
  absolute, on Windows); it now builds the absolute path from `tmp_path`.

- **Correction-data Phase D: wheel/sdist distribution proof** (2026-09-19) —
  `tests/unittests/test_packaging.py` asserts every manifest-declared
  `runtime_lookup` CSV plus the manifest JSON in the wheel (sdist file-list
  parity; both skip when no `dist/` artifact exists). New
  `scripts/verify_distribution.py` builds, installs into a hermetic venv
  under `tmp/dist-proof/`, and reproduces checkout results from the install
  with a mandatory `site-packages` import guard (defeats editable-install
  shadowing), direct-comparison parity (PSD, dose sum, per-event k_med/k_tab
  arrays, packaged table bytes — no new hardcoded goldens), sentinel
  ignore, no CWD artifacts, and leak-free dict/JSON exports. Full `main()`
  on the bundled Siemens cylinder fixture. Plan:
  `dev-docs/plans/archive/CORRECTION_DATA_PHASE_D_DISTRIBUTION_PROOF_PLAN.md`.

- **Notebook plot-mode HTML guard** (2026-09-18) — `analyze_data()` raised on
  `output is None` for every html call, including plot modes that legitimately
  produce nothing (regression from June `803b748`; broke the getting-started
  notebook in docs builds). The raise is now gated on dose-producing modes,
  mirroring the adjacent dose-map guard; return type widened to include
  `None`. Mode/format matrix tests in new `test_analyze_data.py`; headless
  full-notebook execution clean. Plan:
  `dev-docs/plans/archive/NOTEBOOK_PLOT_HTML_FIX_PLAN.md`.

- **Correction-data Phase C guides + Phase A/B archival** (2026-09-18) — new
  user guide (`docs/source/user/correction_data.md`, in Sphinx nav) and
  maintainer reference (`dev-docs/CORRECTION_DATA_REFERENCE.md` with flow
  diagram and loader/consumer map); Phase A/B execution plans archived with
  Completed status; stale `corrections.db`/`db_connect` prose refreshed in
  `CODEBASE_OVERVIEW.md` and `FEATURE_INVENTORY.md`; notebook pointer added.

- **Correction-data Phase B: packaged provider swap** (2026-09-18) — new
  `correction_data.py` provider (`importlib.resources`, locked dict cache,
  deep copies, packaged hash); the three `db_connect` call sites route through
  it with per-function `emit_warnings`; `db_connect.py` is read-only-only
  (bootstrap branch deleted); repo-root discovery removed from
  `gui/settings_builder.py`; exports carry `packaged`/`explicit` labels plus
  a `corrections_db_source` descriptor and hash (`RICH_EXPORT_SCHEMA_VERSION`
  1→2); ignored-DB and relative-path warnings are once-per-process and
  value-free. Legacy unversioned DBs classify as `legacy` with full content
  validation. Full plan:
  `dev-docs/plans/archive/CORRECTION_DATA_PHASE_B_PROVIDER_SWAP_PLAN.md`.

- **Correction-data Phase A: manifest, validation, device_info substitution**
  (2026-09-18) — master §1+§2 with zero behavior change: new
  `correction_data_manifest.json` (schema/units/ranges/consumer/provenance/
  hashes per CSV; runtime vs build-input and read-vs-unread separation); new
  `correction_validation.py` (dataset checks with error/advisory split,
  support-transmission range policy with known-invalid zeros advisory,
  read-only explicit-DB validation + schema-drift matrix, manifest drift
  check); `device_info.csv` serials/labs substituted per the locked positional
  scheme (no mapping retained); `MANIFEST.in` ships the manifest JSON.
  Full plan: `dev-docs/plans/archive/CORRECTION_DATA_PHASE_A_MANIFEST_VALIDATION_PLAN.md`.

- **Issue #60 phantom-preview `monkeypatch` vs NiceGUI `sys.modules` purge**
  (2026-09-17) — the `ci-latest` canary's single deterministic pytest failure
  was cross-suite pollution, not dependency drift: NiceGUI's `user`-fixture
  teardown (`nicegui_reset_globals`) purges `guiskindose.gui` from
  `sys.modules`, so the string-path
  `monkeypatch.setattr("guiskindose.gui.phantom_preview._PHANTOM_DATA_DIR", …)`
  resolved against a fresh parent with no `phantom_preview` binding. Test-only
  fix: patch the already-imported module object
  (`tests/unittests/test_gui_phantom_preview.py`). Proven by a mixed-suite
  repro (GUI smoke + phantom test) failing pre-fix and passing post-fix on
  pinned deps; full `pytest -q` green. No `src/`, dep, lock, or changelog
  changes. Plan: `dev-docs/plans/archive/ISSUE_60_PHANTOM_PREVIEW_MONKEYPATCH_PLAN.md`.

- **Same-PR TO_DO cleanup rule + reminder hook** (2026-09-15) — backlog
  lifecycle is now part of the PR Definition of Done (remove completed items
  in the same PR, not post-merge); new advisory pre-push
  `scripts/check_todo_cleanup.py` flags open items touching branch files, with
  unit tests; PR template checklist line; removed the stale DSfloat item
  (impact in CHANGELOG + tests). *Migration note: the DSfloat work landed in
  PR #97 and its item was removed in the follow-up process PR #98 — the rule
  was adopted mid-flight, so this one removal is grandfathered post-merge.
  Removals after #98 follow the same-PR rule.*

- **Opus whole-branch review follow-ups** (2026-09-10) — Calculate preview
  broad exception guard + `emit_warnings=False` + `input_revision` fingerprint;
  plane-identity audit cache; `dicom_code` source kind for present non-DCM
  CodeValues; rich-export writers render audit/`k_tab` status counts;
  `k_tab_statuses` length validation; glossary terms; Unreleased heading cleanup.

- **Calculate `k_tab` preview cache + EventOutput NaN parity** (2026-09-10) — pre-calc
  Calculate-tab status summary caches dry-runs and suppresses
  `guiskindose.corrections` warnings during preview; invalid estimated
  `k_tab_val` is safe in UI bindings. Dict/JSON plane-identity lists now
  `fillna("unknown")` like rich export. Docstrings / `CODEBASE_OVERVIEW` /
  `FEATURE_INVENTORY` updated for `KTabResult` statuses and Calculate summary.

- **Documentation-assessment backlog closeout** (2026-09-08) — removed the completed documentation-assessment
  entries from `TO_DO.md`, updated the documentation-tooling evaluation now that its prerequisite has landed,
  and linked the backlog lifecycle rules directly from `TO_DO.md`.

- **Phase 3 cross-check §6 count correction** (2026-09-07) — an independent PR review of the
  Phase 4 record caught that the §6 (UI copy + glossary) verdict-summary row undercounted its
  own detail table (shown as `4 items / 3 ACC` when the detail table lists 5 rows:
  Catalog, Privacy, Per-exam, Settings-preview = ACC; Glossary = FIX). Corrected §6 to
  `5 / 4 ACC / 1 FIX` in `DOCUMENTATION_PHASE3_CROSSCHECK_CHECKLIST.md` and propagated the fix
  (grand total `47 / 26 ACC / 20 FIX / 0 GAP / 1 N/A`) into
  `DOCUMENTATION_ASSESSMENT_2026-09-07.md`.

- **Settings/Calculate Fallback badge visibility** (2026-09-10) — changed both
  tabs to bind the "Default profile active" badge to non-empty
  `state.normalization_warnings` (same pattern as the Upload tab) instead of
  `state.normalization_method == "Fallback"`. Updated
  `restore_globals_from_exam_meta` to also restore `normalization_method` from
  the sole remaining exam meta. Added tests for the binding logic and the
  restoration helper.

- **Measured `k_tab` exact-match duplicate rows warn once** (2026-09-10) — when
  the attenuation table contains multiple rows matching the same
  `(model, plane, kVp, Cu, Al)`, `calculate_k_tab()` emits a single
  `logger.warning` with the duplicate count and continues to use the first row
  (`iloc[0]`) so unique-row behavior is unchanged. Added a unit test with a
  tiny in-memory SQLite table containing duplicate rows.

### Added

- **Opt-in SonarQube freshness gate and issue dumps (local hooks)** (2026-09-25) —
  ported the WeekendDigest local-sonar conveniences without replacing the
  value-suppressed `scripts/run_sonarqube_local.py`: `scripts/check_sonar_freshness.py`
  (commit-budget / push-strict gate keyed off gitignored `tmp/sonar-state.json`,
  silent unless `SONAR_FRESHNESS_GATE=1`), `scripts/dump_sonar_issues.py`
  (timestamped `tmp/sonar-issues/` dumps with stable latest pointers and 30-day
  pruning), and the `scripts/run_sonar_freshness_check.sh` hook wrapper. The runner
  now records the scan commit, rewrites the gate state on success only, and passes
  `-Dsonar.projectVersion` from `pyproject.toml`. Wired as `sonar-freshness-commit`
  (pre-commit) and `sonar-freshness-push` (pre-push) hooks; see
  `dev-docs/SONARQUBE_LOCAL.md`. Added `tests/unittests/test_check_sonar_freshness.py`
  and `test_dump_sonar_issues.py`; extended `test_run_sonarqube_local.py`.

- **Structured `k_tab` result type and per-event status tracking** (2026-09-10) —
  replaced the `list[float]` return of `calculate_k_tab()` with a `KTabResult`
  dataclass carrying `.values` and `.statuses` (`estimated`, `exact`,
  `interpolated`, `clamped`, `no_device`, `invalid_inherited`). Logger warnings
  are preserved verbatim. Threaded statuses through `calculate_dose`,
  `format_export_data` (`corrections.table_statuses` and `events.k_tab_statuses`,
  additive), and `analyze_data` multi-exam output. Updated all unit-test call sites
  and mocks; added status-assignment regression tests and export-inclusion tests.
  GUI Calculate tab now shows a compact `k_tab:` counts summary after a successful
  run.

- **Plane-identity audit fields on the normalized DataFrame** (2026-09-09) — added
  ``acquisition_plane_source_kind`` and ``acquisition_plane_resolution`` to the
  ``rdsr_normalizer`` output. Source kinds: ``dicom_cid``, ``dicom_code``,
  ``tabular_raw_code``, ``meaning_only``, ``none``. Resolutions: ``code-backed``,
  ``inferred``, ``ambiguous`` (reserved), ``unknown``. Row-wise fallbacks: blank
  meanings are not ``meaning_only``; missing tabular raw codes fall back to
  meaning/none; ``inferred`` only when a tabular raw code resolves to CID
  identity. Present non-DCM CodeValues stay ``dicom_code``. Tests cover DCM+CID,
  non-DCM code, tabular raw, site-specific unknown raw, missing raw, meaning-only,
  blank meaning, absent identity, and mixed rows.

- **Plane-identity audit fields in export and GUI** (2026-09-10) — extended
  ``EventOutput`` and ``PySkinDoseOutput`` to include ``acquisition_plane_*``
  lists additively in dict/JSON events (no ``EXPORT_SCHEMA_VERSION`` bump);
  added ``plane_identity_audit`` / ``k_tab_statuses`` to rich-export
  ``ExamSection`` and rendered counts in HTML/DOCX/PDF/XLSX settings; Calculate
  tab now shows a compact per-kind/per-resolution count audit line. Tests pin
  dict, JSON, missing-column degradation, zero-event safety, and rich-export
  payload / writer-row coverage.

- **Phase 4 standing documentation-assessment record** (2026-09-07) — added
  `dev-docs/assessments/DOCUMENTATION_ASSESSMENT_2026-09-07.md` (durable per-doc verdict
  matrix, docstring coverage `0 missing`, accepted gaps, and event-driven re-assessment
  triggers), registered it in `dev-docs/index.md`, wired the pre-release trigger into
  `RELEASES_AND_DISTRIBUTION.md` step 4, marked the `TO_DO.md` Documentation Assessment item
  complete, and archived the execution plan to
  `dev-docs/plans/archive/documentation-assessment.md`. Closes the documentation-assessment
  plan (Phases 0–4).

- **Phase 3 cross-check checklist** (2026-09-06) — expanded
  `documentation-assessment.md` Phase 3 with §0–§7 workflow and seeded
  `dev-docs/assessments/DOCUMENTATION_PHASE3_CROSSCHECK_CHECKLIST.md` from
  `help_registry.json`, `feature_doc_matrix.json`, and `docs/source/` layout.

- **Phase 2 docstring sweep** (2026-09-06) — closed all 175 public docstring gaps under
  `src/guiskindose/` (137 modules, 0 missing per `check_docstring_inventory.py`). Four
  commits on `docs/phase-2-docstring-sweep`: settings/helpers/API, core pipeline/export,
  plotting, GUI. Split `geometry_builders.py` into `geometry_controller.py`,
  `geometry_layout_builders.py`, and `geometry_view_refs.py` (facade re-exports preserved)
  after Phase 2 docstrings pushed the monolith past the 800-line harness limit.

- **Docstring inventory script + tests** (2026-09-06) — `scripts/check_docstring_inventory.py`
  (stdlib-AST advisory inventory of undocumented public symbols under `src/`) plus
  `tests/unittests/test_check_docstring_inventory.py` (11 tests). Part of the phased
  documentation-assessment plan; restores the PR coverage gate that flagged the untested script.

## [1.0.0] - 2026-09-03

### Added

- **CI wheel packaging smoke** (2026-09-03) — the `build` matrix job now runs `uv build` before
  pytest, so `test_wheel_contains_guiskindose_package` (including the `gui/help/*.md` assertion)
  exercises a real wheel on every OS/Python matrix entry instead of skipping.
- **GUISkinDose rename PR 0 prerequisites** (2026-09-01) — green, mergeable helpers that did
  not yet rename the Python package: extract `cli()` from `__main__.py` (the `guiskindose`
  console script is wired in a later commit of this PR); dual-read `~/.guiskindose/` /
  `.guiskindose.local.json` / `GUISKINDOSE_SHOW_DEMO_PHANTOMS` while still writing the
  legacy mypyskindose paths at that slice (this PR now writes `~/.guiskindose/`);
  `scripts/rewrite_package_paths.py` (inventory `path` rewrite + leftover-brand report);
  `scripts/check_stale_brand.py` wired into pre-commit and CI (a no-op until this PR
  flipped `LIVE_PACKAGE_NAME`; fail-closed behavior is covered by tests).
- **GUISkinDose rename PR 1 test contract** (2026-09-02) — `dev-docs/plans/archive/GUISKINDOSE_RENAME_PLAN.md`
  now requires inverting PR 0 locks in the mechanical-rename PR: config load–modify–save must
  persist to `~/.guiskindose/` when that file exists, `LIVE_PACKAGE_NAME` must not remain
  `"mypyskindose"`, and `[project.scripts] guiskindose` needs an entry-point test. No extra
  tests-only PR between PR 0 and PR 1.
- **Kerma-meter Codecov patch coverage** (2026-07-26) — added CLI flag wiring tests plus
  settings/validation and table-loader edge cases so `codecov/patch` on the kerma-CF diff
  clears the ~84% target (was 83.87%).
- **Refactor patch coverage** (2026-07-26) — added `tests/unittests/test_refactor_coverage.py`
  exercising the GUI-free helpers extracted during the Sonar complexity refactor
  (`export/metrics.py` mean/scalar/acquisition helpers, `export/cli_source.py` multi/empty
  builders, `kerma_correction._rows_to_factor_dict` error paths) so the `coverage-pr`
  `diff-cover` gate clears 80% (was 78%).
- **Additional GUI coverage tests for Sonar new-code gate** (2026-07-26) — extended geometry /
  results / export / upload / import-preview coverage suites and added
  `tests/gui/test_data_tab_coverage.py`, `test_per_exam_coverage.py`, and
  `test_phantom_preview_controller_coverage.py` so main’s new-code coverage can clear Sonar
  way’s 80% threshold (was ~79% after PR #32 merge).
- **GUI coverage tests for Sonar** (2026-07-25) — added `tests/gui/test_*_coverage.py` suites for
  geometry/upload/results builders, import preview, calculate, and export tabs (P0/P1 modules).

### Changed

- **GUISkinDose rename and republication plans aligned** (2026-09-01) — mechanical in-repo rename
  (`mypyskindose` → `guiskindose`) is specified in `dev-docs/plans/archive/GUISKINDOSE_RENAME_PLAN.md` and
  catalogued in `dev-docs/index.md`. The privacy republication plan now points Phase 5A at that file,
  requires config-directory migration, keeps Semgrep rule IDs, and gates GitHub/Sonar URL rewrites
  on the actual external renames. The rename plan documents a green PR-0 prerequisite slice, one
  CI-green mechanical PR 1 (partial path splits would fail `privacy-gates`), and a local
  `privacy_admission.py run --mode staged` runbook (path-only inventory rewrite; unchanged hashes
  do not need a new human review). No runtime rename in this change.
- **`ci-latest` issue body now includes per-step triage guidance** (2026-08-30) —
  the tracking-issue body explains what each failure mode means and what action
  to take, instead of a bare failure list.
- **`ci.yml` now opens tracking issues on scheduled/dispatch failures**
  (2026-08-30) — mirrors the `ci-latest` pattern with a distinct
  `<!-- ci-failure -->` marker. Auto-closes when a later run is fully green.
  Only fires on scheduled/dispatch runs, not PR failures.
- **AGENTS.md: added git-hooks bypass convention** (2026-08-30) — agents must
  never bypass pre-commit/pre-push hooks with `--no-verify` without explicit
  user permission.
- **Ruff 0.16.2 development-tool upgrade** (2026-08-09) — refreshed the locked
  linter and pre-commit hook, then applied its safe modernization fixes. Ruff 0.16
  expands its implicit default rule set substantially, so the project's existing
  Flake8-compatible `E4`/`E7`/`E9`/`F` baseline is explicit and selectively extended
  with reviewed `B`, `C4`, `FURB`, `I`, `PYI`, `RUF`, `SIM`, and `UP` rules. The
  three `RUF` Unicode-confusables rules are excluded because mathematical symbols are
  intentional in clinical/scientific UI text and documentation; unsafe `SIM117`
  NiceGUI context-manager rewrites are also excluded pending dedicated GUI smoke tests.
  Broad exception and exception-type rules remain out of scope for this upgrade.
- **Locked dependency audit and license inventory** (2026-08-24) — upgraded the locked
  `pip` package to 26.2.1 to remediate PYSEC-2026-3721. License-notice generation now
  uses the same locked `dev` and `gui` environment as CI, preventing host Python
  packages from entering the third-party inventory.
- **ci-latest soft-fail + issue notify** (2026-08-03) — scheduled/manual `ci-latest`
  probe steps use `continue-on-error` so upstream dependency breakage no longer paints
  `main` red. Failures open (or comment on) a GitHub issue labeled `github_actions` /
  `dependencies`, @-mention and assign the repository owner, and include the Actions
  run URL; a later green run auto-closes open tracking issues with the same marker.
- **Dependabot weekly grouped minor/patch bumps** (2026-08-03) — `.github/dependabot.yml`
  still runs weekly (Monday) for `pip` and `github-actions`, but routine minor/patch
  updates are grouped into one PR per ecosystem (`python-minor-and-patch`,
  `github-actions-minor-and-patch`). Major version bumps stay ungrouped for individual
  review.
- **CI base-branch fetch for coverage/changelog** (2026-08-03) — `coverage-pr` and the
  changelog check fetch the PR base with full history instead of `--depth=1`, so
  `diff-cover` / range diffs keep a merge-base when `main` advances after the branch
  was opened.
- **Backlog / plan archive cleanup** (2026-07-30) — trimmed `dev-docs/TO_DO.md` completed items
  (already shipped in prior releases) and archived finished plans under `dev-docs/plans/archive/`:
  `AUTOMATED_PHANTOM_LIBRARY_PLAN`, `PHANTOM_QA_DEMO_GATE_AND_BARIATRIC_EXTREMITIES_PLAN`,
  `PHANTOM_MESH_NAMING_CONVENTION_PLAN`, `MULTI_EXAM_GEOMETRY_OFFSETS_PLAN`,
  `INTERACTIVE_TABLE_OFFSETS_PLAN` (Phases 0–2b; Phase 3 offset arrow deferred). Confirmed and
  removed from the active backlog: sensitive-asset baseline review (all inventory entries
  approved; CI already uses `--require-approved-assets`), HoundDog local PoC (advisory wrapper
  integrated), Upload-tab default example demoting `fake_scanner.dcm`, Geometry per-exam event
  stepper, multi-exam dose-map checkboxes, pediatric stature relabel, mesh naming, arms-down
  variants, kerma-meter CFs, and the fork-maintainer community baseline. Further phantom work
  and custom-mesh import remain open in `TO_DO.md`. Follow-up: rewrote partial backlog items
  (OCR/DICOM-phi wrappers already ship; Central Help / offset UX reduced to remaining gaps) and
  clarified the Results `K_IRP`/`—` open question against current Results vs Data Table UI.
  Also: moved Rich Export Phase 4.3/7 leftovers to Deferred; added
  `dev-docs/INPUT_FIELD_REFERENCE.md` and
  `dev-docs/references/PORTABLE_EXECUTABLE_PACKAGING.md`; marked multi-exam geometry
  assessments historical now that the plan is archived. Added
  `dev-docs/RELEASES_AND_DISTRIBUTION.md` as the release/distribution hub (changelog vs GitHub
  Release notes, PyPI, deferred portable executables).
- **SonarQube/Lizard Phase 4 — UI/CLI oversized functions** (2026-07-29) — decomposed three
  high-NLOC flagged functions: `gui/tabs/settings.py:build` (246 → 9 NLOC) into
  `_build_phantom_section` / `_build_physics_section` / `_build_visual_section`;
  `gui/exam_loaders.py:load_tabular` (162 NLOC / CCN 15 → 14 NLOC / CCN 3) into
  `_parse_tabular` / `_collect_preserved_flags` / `_append_multi_study_exams` /
  `_append_single_study_exam` / `_finalize_tabular_state` / `_wrap_tabular_schema_detection`;
  and `main.py:get_argument_parser` (158 NLOC) into a new `cli_args.py` module
  (`_add_top_level_args` / `_add_input_args` / `_add_export_args` / `_add_gui_args`),
  re-exported via `main.py` for API stability. No public API or `--help` output changes.
  `main.py` dropped from 820 → 631 lines (under the 800-line CI gate).
- **Protected scanner CI clarified** (2026-07-28) — renamed the token-gated SonarCloud step to state that it
  requires `SONAR_TOKEN`, added regression assertions for that guard and the privacy-gated CodeRabbit trigger, and
  corrected harness/privacy documentation for the protected-`main` Sonar and split PR-versus-`main` Gitleaks
  workflows. CodeRabbit requests now match the DICOMViewerV3 privacy-gated implementation: same-repository
  PRs (including drafts), a SHA attestation CodeRabbit recognizes, and `actions/github-script` v9.
- **Single 80% coverage standard** (2026-07-27) — removed the matrix `build` job's separate
  non-GUI `--fail-under=65` coverage step; it now runs the non-GUI suite for test-pass only
  (`pytest --ignore=tests/gui -n auto`, also faster). Coverage is enforced at one 80% standard by
  `coverage-pr` (PRs: combined ≥80% + `diff-cover` ≥80%) and `sonar-scan` (main: ≥80% new-code),
  eliminating the earlier 65%-vs-80% split and the GUI-0% package-scope workaround.
- **Faster CI test runs** (2026-07-27) — the `coverage-pr` and `sonar-scan` combined-coverage
  jobs migrated from `coverage run -m pytest` to `pytest --cov` (pytest-cov, so xdist worker
  processes are measured) with `pytest-xdist -n auto` on the non-GUI suite (GUI stays serial for
  asyncio/nicegui). ~2x faster locally with identical coverage; combined gate stays ≥80%. Added
  `pytest-xdist` to the `dev` extra and `uv.lock`. No tests removed.
- **SonarQube cognitive-complexity hotspots** (2026-07-26) — split the highest-complexity
  `src/` functions: correction-value handlers in `export/metrics.py`, native geometry tracking
  into `gui/native_geometry.py`, `run_gui` setup helpers, CLI export source builders, and
  exam coordinate-transform helpers (python:S3776).
- **Sonar + privacy-gated scans master plan** (2026-07-25) — `dev-docs/plans/archive/SONAR_PRIVACY_GATED_SCANS_PLAN.md`
  covers Sonar security fixes; keep GUI in coverage via combined `tests/gui/` coverage.xml + GUI
  tests; remove README Sonar badge when custom quality gates are unavailable (done on this
  branch); cloud analyzer path exclusions audit for Sonar / Semgrep / CodeRabbit (and a note that
  future DeepSource or similar SaaS SAST must use the same privacy-gate + exclusion pattern);
  Semgrep as local Actions CLI with Cloud App disabled; restore Sonar on PRs; run OWASP Semgrep /
  Sonar / CodeRabbit only after `privacy-gates`. Branch: `plan/sonar-privacy-gated-scans`.
- **PR coverage gate via GitHub Actions** (2026-07-26) — matrix `build` raises non-GUI
  `coverage report --fail-under` from 60→65. New `coverage-pr` job (PRs only) runs combined
  non-GUI + GUI coverage (≥80%) and `diff-cover` ≥80% vs the PR base. Codecov stays main-only
  upload with `codecov.yml` project/patch statuses set to **informational** so Free `codecov/patch`
  no longer blocks merges; the GHA gate is authoritative.
- **Sonar quality-gate README badge removed** (2026-07-25) — dropped the SonarCloud
  `alert_status` badge from `README.md`. On Free / read-only Sonar way the new-code coverage
  gate stays at 80% and cannot be lowered, so the badge was advertising a red status we cannot
  tune. Sonar analysis remains in CI per `SONAR_PRIVACY_GATED_SCANS_PLAN.md`; the badge may
  return only when the gate is green sustainably or a custom gate is available.
- **Sonar coverage now includes GUI tests** (2026-07-25) — cloud-scans coverage generation
  installs the `gui` extra and runs a two-pass `coverage` recipe (non-GUI then `tests/gui/`
  with `--append`) so Sonar measures `src/guiskindose/gui/`. Documented in `SONARQUBE_LOCAL.md`.
- **Cloud scanner exclusion audit** (2026-07-25) — Sonar exclusions add runtime output globs
  (`tmp/**`, `PlotOutputs/**`, `htmlcov/**`, `coverage.xml`); `.coderabbit.yaml` disables
  auto-review and path-filters sensitive surfaces; privacy docs record cloud-vs-local scope
  (OWASP Semgrep stays include-list; privacy Semgrep keeps `src`/`scripts`/`tests`).
- **Privacy-gated CI scans** (2026-07-25) — `privacy-gates` job runs admission + privacy
  Semgrep first; OWASP Semgrep, SonarCloud (PR+main), gui-smoke, and the build matrix wait on
  it. Codecov/Safety stay main-only. Automatic Analysis is off; Free/Sonar-way coverage gate
  remains untunable (no README badge).
- **CodeRabbit after privacy-gates** (2026-07-25) — auto-review disabled; CI posts
  `@coderabbitai review` on non-draft PRs once per head SHA only after reusable
  `privacy-gates` succeeds (does not wait for the full matrix).
- **SonarCloud Automatic Analysis disabled; Free gate untunable** (2026-07-25) — CI-based
  analysis is authoritative; Free/Sonar-way `new_coverage` stays at 80% (B2-B / no README badge).
- **CI locked installs** (2026-07-24) — the `ci.yml` test/coverage matrix (`build`) and the
  main-only `cloud-scans-after-gates` job now install via `uv sync --extra dev --locked` and run
  tools through `uv run --no-sync` (cross-OS) instead of unpinned `pip install`, and coverage
  upload uses the pinned `codecov/codecov-action` instead of `pip install codecov`. This clears
  the SonarCloud **S8544** (unpinned-dependency) findings on those jobs. The intentionally
  unpinned `ci-latest.yml` sweep is unchanged by design. Note: **S8541** ("omitting `--no-build`")
  still reports on `uv sync` lines — it is unavoidable when installing the local project and is a
  SonarCloud accept/disable-rule item, not a code fix.
- **Release pipeline hardening** (2026-07-24) — `release.yml` now builds with the pinned `uv`
  toolchain (`uv build`) instead of an unpinned `pip install setuptools wheel twine build`
  (clears SonarCloud S8544/S8541 on the release path), and publishes to PyPI via **Trusted
  Publishing (OIDC)** — removing the stored `PYPI_DEPLOY_API_KEY` secret in favor of a
  short-lived token (`id-token: write`). The workflow stays inert unless a GitHub Release is
  created; see `PUBLISHING.md` for the one-time PyPI trusted-publisher setup needed before any
  first real publish.
- **SonarCloud new-code Security Rating** (2026-07-24) — Confined the remaining CLI-derived
  filesystem paths in dev scripts through path validation and added git-ref / audit-arg
  allowlisting so SonarCloud stops rating new code below A. `mpfb_generate` and `run_catalog`
  now route catalog/report paths through `path_safety.resolve_under_roots`;
  `check_feature_doc_matrix` validates the changed-paths file stays under the repo root and
  its git ref against a conservative pattern; `audit_dependencies` rejects `uv audit` passthrough
  args containing control characters or surrounding whitespace (the call is already shell-less /
  list-form); `check_doc_freshness` matches link schemes without embedding a clear-text `http://`
  literal (S5332). Behavior unchanged; dev-tooling hardening only.
- **Push-harness fixes for phantom catalog branch** (2026-07-24) — Exclude `scripts/phantom_gen` from
  basedpyright (incomplete bpy/trimesh/numpy-stl stubs); type patient offsets as floats; require
  `jupyterlab>=4.6.2` for notebook extra advisory CVEs; GUI-placement `importorskip` on phantom
  unit tests that transitively import NiceGUI. Pin CI/`[dev]` ruff to `>=0.15,<0.16` so unpinned
  `pip install ruff` cannot pull 0.16 and fail the matrix on hundreds of newly-noisy findings.

### Fixed

- **CodeQL quality-alert cleanup** (2026-08-04) — removed dead assignments and imports,
  made intentional cleanup and fall-through paths explicit, and separated GUI table-origin
  coordinate utilities from offset handlers to break their import cycle. No user-facing
  behavior changed.
- **Locked dependency audit** (2026-08-04) — `uv.lock` bumps `aiohttp` 3.14.1→3.14.3 and
  `cryptography` 49.0.0→50.0.0 so `static-analysis` / `uv audit` clears newly published
  advisories (GHSA-mfx4-hv73-q22v, GHSA-cq5v-8q36-5273, GHSA-mq44-7p77-q5h7,
  GHSA-g6cj-pr64-35w5).
- **Main-push privacy gate on Dependabot / noreply Git trailers** (2026-08-03) —
  `check_ci_metadata.py` failed `main` CI after merging Dependabot or Cursor PRs
  because commit messages include Dependabot `Signed-off-by` and GitHub
  `Co-authored-by` noreply identity trailers. Those known GitHub automation /
  `users.noreply.github.com` trailers are now ignored for `EMAIL_ADDRESS` in
  commit-message and push-metadata scans only (helper:
  `scripts/git_identity_trailers.py`); institutional emails and PR title/body
  scans stay strict. Trailer display names must not contain `@`, so an
  institutional address cannot hide behind an allowlisted bracketed noreply.
- **ci-latest type error on `main`** (2026-07-27) — `check_table_hits` returned
  `hits.tolist()` from a bool ndarray; newer numpy stubs type `ndarray.tolist()` as not
  assignable to the declared `List[bool]`, failing basedpyright in the `latest-deps` job.
  Now builds an explicit `list[bool]` (`[bool(hit) for hit in hits]`); behavior unchanged.
- **SonarQube bugs and easy wins** (2026-07-26) — cleared the three open BUG findings in
  `gui/app.py` (propagate `asyncio` cancellation by not swallowing `CancelledError`; keep a
  strong reference to browser disconnect shutdown tasks). Also fixed confusing adjacent-string
  concatenations, duplicated string literals, dead/commented code, an empty help-button block,
  and preferred `{...}`/`[]` literals over `dict(...)`/`list()` across plot/export helpers
  (python:S7497, S7502, S5799, S1192, S125, S108, S1854, S7498).
- **Local Sonar smells on kerma-meter CF paths** (2026-07-26) — cleared BLOCKER S3516
  (`kerma_meter_prompt` no longer always-returns-bool; dialog is fire-and-continue),
  duplicated dialog CSS literals (S1192), unused warn-helper params (S1172), and cognitive
  complexity on CF table load / Calculate kerma readiness helpers. Behavior unchanged.
  Also tightened basedpyright types on CF table load and identity-adapter tests so
  pre-push typecheck passes.
- **Kerma CF duplicate-row test logging capture** (2026-07-26) — `test_duplicate_rows_first_wins`
  attaches a dedicated WARNING handler instead of relying on pytest `caplog` (flaky on
  CI Python 3.14 when suite logging state blocks root propagation).
- **CodeRabbit kerma-CF hardening** (2026-07-26) — broader fail-soft on CF file load errors;
  invalid in-memory/table factors fall back to `default_factor`; CF prompt keys honor
  `explicit_label`; header aliases for `device_serial_number` / `AcquisitionPlane`; no
  filenames in CF not-found errors/debug logs; export validates kerma list lengths;
  docstrings added across Calculate-tab / kerma tests and remaining branch-touched
  src helpers (export writers, analyze_data, adapters, settings).
- **STL Z-positioning unit test** (2026-07-24) — `test_stl_phantom_positioning_in_z_direction` now
  skips `*_reduced_*` preview companions (decimation can leave tiny +Z verts); full clinical meshes
  still require no vertices with Z > 0.

### Removed

- **`safety` and main-only CI cloud scan removed** (2026-09-03) — the `safety` package was the
  sole consumer of transitive `nltk` in the `dev` extra, so dropping it deletes the unpatched
  `GHSA-8mgp-746c-j5xp` / CVE-2026-81726 exposure at the root instead of ignoring it, along with the
  `nltk>=3.10.3` pin (PYSEC-2026-3726) and the `cloud-scans-main` CI job (`SAFETY_API_KEY` no longer
  needed). Dependency auditing remains covered by `uv audit` + `pip-audit` via
  `scripts/audit_dependencies.py` (same OSV/PyPA advisory data) in the PR-level `static-analysis`
  job and the local pre-push hook. User-facing summary stays in `CHANGELOG.md`.
- **Codecov integration** (2026-07-26) — dropped the `main`-only Codecov upload step from the
  `cloud-scans-main` CI job and deleted `codecov.yml`. Enforced PR coverage remains the GHA
  `coverage-pr` job (combined non-GUI+GUI ≥80% plus `diff-cover` ≥80% vs the PR base); the job
  then ran Safety only until the 2026-09-03 safety removal above deleted it outright.

### Security

- **PHI-like filename admission guard** (2026-07-26) — `scripts/privacy_admission.py check` (pre-commit,
  pre-push, and CI `privacy-gates`) now blocks committing files whose name/path resembles PHI: structural
  identifier patterns (`MRN_…`, SSN format, `patient_name`/`patient_id`, `dob…`, accession numbers) and
  whole-token matches against a curated common-name list. Configured under `phi_filename` in
  `dev-docs/privacy_admission_policy.json` (with an `allowlist_patterns` escape hatch); errors report a
  non-reversible `path_token=` instead of the sensitive name. Verified zero false positives across the
  current tree.
- **PR cloud-scanner boundary hardening** (2026-07-26) — tokenized SonarCloud analysis now
  runs only on `main` pushes and requires an explicit `SONAR_PROTECTED_MAIN_ENABLED=true`
  repository variable, keeping it fail-closed until branch protection is confirmed. Added
  regression tests that forbid `pull_request_target`, prevent PR-head Sonar execution, and
  preserve CI-requested CodeRabbit review after privacy gates. Sonar and CodeRabbit now share
  CI-enforced exclusions for `.dicom` and additional medical/image/document/binary formats;
  OWASP Semgrep remains local with telemetry disabled and asset fixtures excluded. CodeRabbit
  manual review commands remain a documented, accepted bypass of CI ordering.
- **Sonar S8707 catalog report write** (2026-07-26) — `write_text_under_roots()` confines the
  JSON report path then writes via `open().write` so Sonar does not treat CLI-derived report
  payload content as a path-injection sink on `Path.write_text` (clears remaining S8707 on
  `run_catalog.py` after PR #32).
- **Sonar S8707 / S8705 sanitizers** (2026-07-25) — `trusted_path_under_roots()` rebuilds catalog
  JSON report paths from allowlisted roots before write; `build_uv_audit_argv()` allowlists only
  `--frozen`/`--locked` for `uv audit` subprocess argv (clears SonarCloud new-code Security Rating C).
- **Notebook embedded-visual review checklist** (2026-07-25) — `notebook_embedded_visual` assets
  in `approved_asset_inventory.json` now require a `notebook_review` block with
  `embedded_images_reviewed` and `burned_in_text_reviewed` both `true`; an `approved` status alone
  no longer clears a notebook with rendered image/PDF outputs (`check_sensitive_content.py` emits
  `NOTEBOOK_REVIEW_FIELDS_INCOMPLETE` otherwise). This gives notebooks parity with the DICOM and
  container review checklists so embedded outputs get an explicit human PII/PHI review. The
  rendered inventory Markdown and `PRIVACY_AND_SENSITIVE_ASSETS.md` document the new fields.
- **SonarCloud analysis scope** (2026-07-25) — added `.sonarcloud.properties` (the file
  Automatic Analysis actually reads; `sonar-project.properties` is ignored by it) excluding
  directories/artifacts where private data is most likely to land (`example_data`, `phantom_data`,
  `table_data`, `dev-docs`, `**/*.dcm`, notebooks, `**/*.log`, `**/*.txt`, images) plus build
  noise, and mirrored the same exclusions into `sonar-project.properties`; the new
  `check_sonar_properties.py` pre-commit/CI check keeps the shared scope keys in parity. Also aligned the stale
  `sonar-project.properties` project key/name to the Sonar project key in use at the time (renamed to
  `kgrizz-git_GUISkinDose` / `GUISkinDose` after the 2026-09-04 GitHub repository rename) and
  added `sonar.organization` so the local/CI scanner file is actually usable. Scan hygiene and
  defense-in-depth only — the real PHI/PII guard remains the commit/CI privacy gates
  (`check_sensitive_content.py` forbids `*.log`, hash-gates images/DICOM/notebook outputs, and
  pattern-scans all UTF-8 text incl. `*.txt`/`*.ipynb`).
- **Blender subprocess argv allowlisting** (2026-07-24) — `run_catalog.py` validates Blender basename
  and catalog ids, then rebuilds argv from trusted components before `subprocess.run` (Sonar S8705).
- **Phantom_gen path confinement** (2026-07-24) — Shared `path_safety.resolve_under_roots` confines
  CLI/catalog-derived paths under allowlisted roots before open/mkdir/write (Sonar S2083), including
  `transform_to_psd_frame.py` and `validate_phantom.py` load/write helpers. Absolute catalog
  `pose_file` paths may also live under the process temp dir (pytest / local scratch).
