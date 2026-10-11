# Custom Equipment Profiles — Execution Plan

Status: **Active — Phase 0 in progress; fallback and sparse-data rules agreed**
Design authority: [CUSTOM_EQUIPMENT_PROFILES_SPEC.md](CUSTOM_EQUIPMENT_PROFILES_SPEC.md) (reviewed 2026-10-10)
Contract lock reference: [EQUIPMENT_PROFILE_SCHEMA.md](../EQUIPMENT_PROFILE_SCHEMA.md) (common + coordinate domains)
Created: 2026-10-09 · plan updated 2026-10-10
Parent roadmap: [CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md](CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md)
Delivery: implement each slice on feature branches after its applicable Phase 0 locks; no direct-to-`main` work. Keep calculation,
GUI, and persistence slices independently reviewable, but do not split any atomicity or audit contract named below.

## Objective

Implement validated reusable profiles for (1) equipment coordinate conventions and (2) patient-support
transmission. Users can load JSON, CSV/TSV, or XLSX; enter both domains manually in the GUI; and save/version/
reload profiles in a separate local user-owned SQLite store. JSON remains canonical full-fidelity interchange.

Kerma-meter correction, backscatter/medium, HVL, `anode_angle_deg`, and individual-equipment profile keys remain
out of scope (spec decision 19). Bundled data stays immutable, and explicit `corrections_db_path` remains supported
as a distinct read-only legacy correction source (decision 17; current source resolution is
`src/guiskindose/corrections.py:33-46`).

## Delivery rules

- Coordinate selection remains once per homogeneous exam/frame (decision 1); canonical `manufacturer` joins the
  normalized contract (decision 2).
- Missing supported coordinate leaves and transmission rows inherit and notify. Unsupported, invalid, ambiguous,
  out-of-original-extent rows for an existing model/plane, or conflicting content fails closed (decisions 6, 7, and 15).
- Every source passes through one canonical model, validator, resolver, hashing implementation, and immutable
  activation snapshot. Source adapters cannot implement their own precedence or weaker validation.
- Dose-affecting activation and provenance are inseparable. Phase 4 cannot merge before Phase 3's atomic activation,
  result invalidation, and profile-aware cache key.
- Files created by implementation should respect repository modularity; split source modules before they approach
  the harness size limit. Update behavior docs in the phase that changes behavior, not only at release.

## Acceptance criteria

1. Every supported source can create/load a profile; GUI/database values persist and reload without package edits.
2. Effective coordinate leaves, inherited sources, transmission coverage, and evidence are visible per exam before calculation.
3. Missing coverage inherits with a concrete notice; bad or unresolved content cannot silently alter dose.
4. API, CLI, GUI, user store, run state, and exports agree on precedence, values, hashes, and provenance.
5. Runs without active custom profiles remain numerically unchanged.

## Phase 0 — Contract and schema lock

**Goal.** Turn the spec into signed schemas, examples, limits, and error codes before implementation.

Work:
- [x] Sign off all 20 decisions in spec §11 without changing their meaning implicitly in code. Record amendments in
      both documents before implementation. *(Resolution rules agreed 2026-10-10; amendments recorded in spec §11.)*
- [x] **Common + coordinate contract locked** — [EQUIPMENT_PROFILE_SCHEMA.md](../EQUIPMENT_PROFILE_SCHEMA.md) publishes
      the allowlisted field model for nested JSON, the flat 19-column tabular shape plus the optional
      `promote_coordinate_wildcard` column, alias-list shorthand vs explicit alias-to-model maps, types/enums/bounds,
      blank-cell semantics, canonical serialization and SHA-256 hash rules, cross-profile conflict rules, immutable
      per-leaf match-record shapes, the stable error-code catalog, and the coordinate activation capability gate.
      This is the applicable lock for the Phase 1 core package and the Phase 2 coordinate slice.
- [ ] Publish the canonical profile field table: required stable `profile_id`; manufacturer/models; separate explicit
      manufacturer alias lists and model alias-to-target maps; independently optional coordinate/transmission domains with at least one non-empty; partial coordinate
      leaves; transmission evidence/source/date; bounded notes; unknown fields rejected (decisions 3, 6, 8, 12, 16).
      *(Common/coordinate portion delivered by EQUIPMENT_PROFILE_SCHEMA.md §§1–6; store-persistence portion still open.)*
 - [ ] Lock source schemas (decision 4): nested JSON document; ONE flat tabular model shared by CSV/TSV and XLSX
      (strict `record_type` rows, one implicit-v1 shape, one selected sheet); explicit alias-to-model maps,
      single-model shorthand, and optional `promote_coordinate_wildcard` per spec §§3–5; canonical GUI/store values.
- [ ] Complete the packaged starting material under `example_data/equipment_profiles/`: filled examples and
      blank templates for JSON, CSV/TSV, and XLSX, plus a README with the field/column dictionary and planned
      CLI/GUI usage. The JSON/CSV files and README are authored; TSV/XLSX remain outstanding, and the schema
      is preliminary pending the Phase 0 lock. Real-loader validation follows in Phase 1.
      Mirror the kerma-meter precedent (`src/guiskindose/example_data/kerma_meter/`). Content is synthetic:
      fictional labels/factors/dates, no station, serial, paths, or site-identifying notes. XLSX needs
      hash-pinned human clearance in the approved-asset inventory before merge; CSV/TSV/JSON are text-scanned.
- [ ] Add packaging inclusion before the Phase 5 download actions and packaged-resource tests: `MANIFEST.in`
      currently has no `example_data/equipment_profiles/` patterns. A packaged `.xlsx` template additionally needs
      hash-pinned human clearance in `dev-docs/approved_asset_inventory.json`, which has **not** been added — no
      XLSX binary has been introduced. Phase 6 owns the final installed-wheel clean-directory proof; authoring
      files in this directory alone does not prove they ship.
 - [ ] Author invalid examples (malformed, wrong schema version, unknown fields, duplicate claim, out-of-extent
      row, unsupported suffix) with the stable error code each must produce.
 - [x] Lock the separate user-store schema and migration policy: record/revision IDs, canonical payload, profile/hash/
      active-set metadata, timestamps, transactions, uniqueness, and corruption handling (decision 5).
      *(Locked in [EQUIPMENT_PROFILE_SCHEMA.md](../EQUIPMENT_PROFILE_SCHEMA.md) §12: store schema version 1,
      four tables (records, revisions, tombstones, meta), immutable revisions with canonical payloads and
      content hashes, revision pointers, generation tokens, opaque store ID, no origin paths, and the locked
      revision-set source hash.)*
- [x] Set exact maximum file bytes, XLSX expanded/member/sheet limits, aggregate 10,000-row ceiling, profile/alias
      counts, ID lengths, and text lengths. The row ceiling follows `src/guiskindose/kerma_correction.py:42,324-362`.
      *(Locked for common/coordinate ingestion in [EQUIPMENT_PROFILE_SCHEMA.md](../EQUIPMENT_PROFILE_SCHEMA.md) §4;
      XLSX preflight follows `src/guiskindose/input_adapters/tabular_loader.py:29-33`.)*
- [x] Lock canonical serialization and SHA-256 rules for floats, key order, omitted values, per-profile hashes,
      exact-file-byte hashes, GUI snapshot hashes, and active-set hashes
      (decision 12). *(Delivered for the common/coordinate boundary in
      [EQUIPMENT_PROFILE_SCHEMA.md](../EQUIPMENT_PROFILE_SCHEMA.md) §7: negative-zero normalization, numeric
      equivalence across JSON and tabular sources, and the profile hash covering content/provenance but never source
      context. Stored selected-revision-set hashing is now locked (§12) and implemented by the store slice.)*
- [x] Lock coordinate leaf resolution and provenance: default candidate order; explicit wildcard promotion; nested
      x/y/z and angle leaves; `complete match` versus concrete `partial match` notice (decisions 6 and 9).
      *(Locked in [EQUIPMENT_PROFILE_SCHEMA.md](../EQUIPMENT_PROFILE_SCHEMA.md) §§2, 5, and 9, including the
      immutable per-leaf match-record shape with `inherited` flags.)*
- [ ] Lock the transmission key, extents, measured/estimated overlay, explicit-SQLite collision rule, one-interpolator
      composition, row fallback, and status/source dimensions (decisions 7, 8, 10, 11). The current key/interpolator is
      verified at `src/guiskindose/corrections.py:327-380`; the attenuation header has no manufacturer column
      (`src/guiskindose/table_data/correction_table_and_pad_attenuation.csv:1`).
- [x] Lock stable error codes, including malformed/oversized input, unsupported source/schema/capability, duplicate
      claim, alias ambiguity, wildcard acknowledgement required, existing-model out-of-extent row, explicit-SQLite collision,
      store conflict/corruption, and activation rollback. *(Common/coordinate catalog locked in
      [EQUIPMENT_PROFILE_SCHEMA.md](../EQUIPMENT_PROFILE_SCHEMA.md) §10. The two transmission-specific codes —
      existing-model out-of-extent row and explicit-SQLite collision — are confirmed alongside their Phase 4
      fixtures; store codes (`store_conflict`, `store_corruption`, `unsupported_store_version`, `store_not_found`,
      `store_unavailable`, `store_limit_exceeded`) are implemented by the Phase 1 store slice.)*
- [ ] Lock privacy/export fields (decision 13): manufacturer/model and canonical `matched_input_key` are default-safe;
      station/serial retain `include_identifiers` for per-event output and never enter logs; notes and profile paths are
      omitted by default. This intentionally replaces the current manufacturer/model gating at
      `src/guiskindose/gui/run_state.py:155-178`.
- [ ] Lock run-state/rich-export schema bumps and old-profile compatibility reader (decision 18).
- [ ] Define the exact pre-calculation, Calculate, Results, and export representations for field inheritance,
      transmission partial coverage, active/unused profiles, and structured immutable match records (decision 20).

### Resolution rules agreed 2026-10-10

The maintainer accepted these rules after clarifying that missing custom coverage must retain current
handling. They amend spec decisions 3, 4, 8, 9, 10, and 11; implementation must follow spec §§3–7.

1. **Original lookup table and new models.** The baseline grid means the existing packaged or explicit-SQLite
   transmission rows for a model/plane. Keep those rows intact for ordinary lookup. Extent restrictions apply
   only when that model/plane has original rows. New models accept valid custom exact rows and complete custom
   interpolation slices; uncovered or out-of-custom-range queries retain current unknown-model/plane handling.
2. **Sparse additions cannot damage usable lookup.** Existing-node replacements participate in interpolation.
   Additional rows are exact-match-only unless they complete a rectangular kVp × Cu slice. Never invent missing
   factors. Choose a complete interpolation grid before lookup; otherwise use the intact original table.
   Preserve Al snapping and the existing 2-D algorithm. The reproduced hole/NaN case is a regression fixture,
   not a reason to reject sparse profiles or silently discard usable original coverage.
3. **Evidence and validity are independent.** Original evidence is `measured`, `estimated`, or `unknown`, from
   reviewed provenance. Custom measured rows may replace packaged nodes; estimated rows may fill absent/invalid
   nodes or replace estimated nodes, but cannot replace valid measured/unknown nodes. Report ignored rows.
   Explicit-SQLite same-key collisions still error. Inventory/classify inherited evidence before Phase 4;
   unknown must remain available when provenance cannot be established.
4. **Identity and source shape.** Each model alias explicitly targets one canonical model; non-empty flat lists
   remain shorthand for a single exact model. Canonical maps use JSON objects; tabular cells may contain quoted
   JSON maps. Coordinate wildcard promotion requires `promote_coordinate_wildcard: true` plus GUI acknowledgement
   or CLI `--allow-equipment-profile-wildcard-promotion`. Reject conflicting enabled claimants and require
   disabling one; no extra conflict-override syntax. The current tabular shape is implicit v1; reject unsupported
   fields/versions. Missing transmission filtration values are invalid; explicit zero means no added filtration.

Remaining Phase 0 work is executable schema/limit/error/hash/store contracts and fixtures, not deciding those
four rules again. Lock the common and coordinate contracts before their Phase 1/2 slices. Transmission-specific
implementation fixtures, evidence classification, grid eligibility, and fallback provenance must be verified
before Phase 4; they do not block independent coordinate work. Unsupported transmission capabilities still
fail closed in the coordinate-only slice. Do not mark incomplete Phase 0 items signed off automatically.

**Common + coordinate lock delivered 2026-10-10.** [EQUIPMENT_PROFILE_SCHEMA.md](../EQUIPMENT_PROFILE_SCHEMA.md)
publishes the implementation field model, tabular column set, types/enums/bounds, blank-cell semantics, canonical
serialization and hash rules, conflict rules, match-record shapes, and error codes for the common and coordinate
boundary, so the Phase 1 core package and the Phase 2 coordinate slice can proceed. This is **not** full Phase 0
sign-off. Still outstanding for later slices: run-state and
rich-export schema version locks and backward readers, XLSX fixtures and their approved-asset inventory
evidence, transmission eligibility/evidence/grid fixtures, `MANIFEST.in` packaging inclusion, and the
invalid-example fixture set with each locked error code.

Exit criteria: the applicable schema, bounds, error catalog, hashes, privacy matrix, and fixtures are locked
for each implementation slice; no unresolved contract in that slice is hidden by fallback. All domains must
meet their locks before full v1 release.

## Phase 1 — Canonical model, source adapters, store, and identity contract

**Goal.** Parse every non-GUI source and produce immutable validated profile sets without changing calculations.

Work:
- [ ] Add the canonical model, validation, hashing, conflict detection, indexes, and stable errors after
      the applicable Phase 0 common/coordinate contracts are locked. Keep transmission eligibility/resolution
      separate so its later evidence/grid verification does not hold coordinate work. No calculation or GUI
      imports in the core; no activation of unsupported domains. **Unblocked: the common/coordinate contract is
      [EQUIPMENT_PROFILE_SCHEMA.md](../EQUIPMENT_PROFILE_SCHEMA.md) — implement it, do not re-derive it.**
      **Progress: the JSON/core slice of this item is partially implemented** — immutable models, JSON and
      in-memory parsing, structural validation, canonical serialization and hashes, duplicate/conflict
      validation, match-record types, and the capability gate exist under
      `src/guiskindose/equipment_profiles/` and are inert (no application wiring). **This item is not
      complete**: indexes and the normalized identity contract still remain; adapters and the user store
      are implemented below.
- [ ] Implement JSON, CSV/TSV, and XLSX adapters. Read bounded file bytes once, hash and parse the same snapshot;
      preflight XLSX container expansion/sheets/rows/text before materialization. Match the kerma loader's accepted
      suffix family (`src/guiskindose/kerma_correction.py:348-376`) without sharing kerma-specific factor rules.
      **Progress: JSON, CSV, TSV, and XLSX adapters are implemented and inert**
      (`json_source.py`, `tabular_common.py`, `csv_source.py`, `tsv_source.py`, `xlsx_source.py`,
      `xlsx_preflight.py`, `xlsx_xml.py`), covering bounded reads, strict headers and row widths, record-type
      applicability, ordering-independent grouping, and canonical equivalence with the JSON adapter.
      The XLSX path preflights the container before any worksheet is read (real-inflation counting,
      bounded entry list) and additionally validates every worksheet part with a bounded streaming `expat`
      parser that ignores the declared `<dimension>` for sizing and enforces the row, column, and cell budgets
      on the coordinates actually present, rejecting out-of-range, repeated, and malformed coordinates, DTDs,
      entity declarations, and external entity references. Because the real bounds are known first, the
      reader's own dimension is discarded so a workbook that understates its content is read in full and one
      that overstates it cannot allocate padding it does not hold — there is no silent truncation in either
      direction — and the budgets are re-enforced on the reader's actual iteration. Sheet counts come from the
      workbook's own worksheet catalog, never from archive part filenames. openpyxl is imported inside the
      adapter functions, so a JSON/CSV/TSV-only use never loads the spreadsheet stack, and a single documented
      boundary over the whole untrusted-container path normalizes any remaining library exception family to
      `malformed_container` with the cause suppressed and always closes the workbook. Sheet names, paths, cell
      text, and unknown keys never reach an error. (The user store landed separately; see below.)

- [ ] Implement an in-memory adapter for already-structured GUI/API values. It deep-copies and canonicalizes one
      submission before validation so later form mutation cannot alter an activation candidate.
- [x] Implement the local user-store repository: initialize/migrate in the per-user app-data area; transactional
      create/version/read/list/enable/delete; optimistic revision checks; payload/hash verification; bounded queries;
      no coupling to bundled tables or `corrections_db_path`. **Implemented and inert** (`profile_store.py` with
      `store_reads.py`/`store_writes.py` operation modules, `store_schema.py` contract, `store_types.py` types;
      stdlib `sqlite3` only): explicit initialize-or-verify with fresh-empty creation and rejection of
      unversioned-nonempty, future, and corrupt databases without mutation; `BEGIN IMMEDIATE` writes with rollback
      on *any* failure (unexpected errors close safely, cancellation preserved); required revision CAS on update
      plus tombstoned generations against ABA reuse; payload re-parse, re-validation, and re-hash on every read;
      new records start disabled; unsupported capabilities persist but are never activated; enabling validates the
      would-be enabled set atomically. **Still open in Phase 1:** per-exam match-record wiring and
      multi-source duplicate detection at activation time.
- [x] Load stored revisions in one read transaction and materialize an immutable selected-revision snapshot. Test that
      file → store → canonical JSON preserves profile hashes while source/revision provenance changes appropriately.
      **Implemented and inert**: `selected_snapshot()` loads in one read transaction (empty enabled store yields a
      valid empty snapshot), bounds selection and aggregate rows before materializing payloads, runs the canonical
      conflict check over the selection, and exposes the locked revision-set source hash with `source_kind: "store"`.
      File → store → canonical-JSON reload preserves profile hashes while the source hash changes appropriately.
- [x] Add canonical `manufacturer` to every raw-normalized frame and the normalized adapter contract; warn for legacy
      normalized data lacking it. Keep mixed coordinate identities split/rejected before matching. **Implemented**
      (`exam_identity.py` seam + `rdsr_normalizer` + `normalized`/`dosetrack` adapters, no activation/matching
      wiring): every raw-normalized frame carries a canonical `manufacturer` column with the exact per-event
      maker spelling (`None`, never `"none"`/`"nan"`, when the source carries none); the `normalized` schema
      recognizes an optional `manufacturer` column and materializes it as all-`None` with one count-only legacy
      warning when absent or entirely blank. One exam carries exactly one canonical (manufacturer, model) pair,
      both axes through the existing key normalizers with no vendor aliases: distinct makers, same-maker model
      variation, and known+unknown mixes all fail closed with value-free diagnostics (pair count plus
      missing-maker row count, never values), so no row borrows another row's identity and row-0 selection only
      runs on proven-homogeneous frames; key spelling variants collapse and all-unknown frames stay compatible.
      DoseTrack maps each row's Equipment Name through the established `MODEL2MANUF` rules (blank continuations
      repeat the row above; leading blanks stay missing; count-only unknown-name warning) and meets the same
      guard — no whole-column first-name overwrite. The seam runs inside `rdsr_normalizer()` before profile
      selection and per study-id group in the `normalized` adapter (opaque `Exam N` positions only; study IDs
      never enter errors). Export maker/model come from one consistent row. Vendor-coordinate selection,
      coordinates, dose, and all numeric goldens are unchanged; the full-frame digest regen adds only the
      `manufacturer` column. **Still open in Phase 1:** per-exam match-record wiring and multi-source duplicate
      detection at activation time.
- [ ] Add immutable per-exam coordinate/transmission match records with domain, profile/revision, source/level,
      canonical matched key, affected count, hashes, and leaf/row provenance—not mutable fields on
      `NormalizationSettings` (decision 20).
- [x] Compile coordinate indexes by canonical manufacturer/model and transmission indexes by canonical model/literal
  plane. Assert event resolution does not scan the full user table per event. **Implemented and inert**
  (`indexes.py`): entries are strictly bounded (real sequence, `MAX_PROFILES`, aggregate rows before
  expansion), each entry's context is strictly checked (exact-`str` source kind, exact-`int` bounded revision,
  lowercase-hex hash), and each profile — however built — is structurally gated and revalidated through the
  existing document boundary with its claimed hash verified (`conflicting_profile_metadata` on mismatch);
  coordinates resolve by canonical manufacturer/model and transmission by canonical model/literal plane with
  original numeric row keys; global conflicts detected via the canonical check before publishing; explicit
  aliases and manufacturer-scoped wildcards stored without activation; retrieval bisects sorted key tables
  with no profile traversal; immutable internals; compiled content identical for every source order, with only
  a conflict   diagnostic's `source_kind` following the lead entry; all public reprs value-free. **Still open in
  Phase 1:** per-exam match-record wiring and multi-source duplicate detection at activation time.
- [ ] Detect canonical duplicates and conflicts across all source kinds before activation. Input order may affect only
      deterministic diagnostics and serialization.
- [ ] Emit privacy-safe errors containing codes, source-kind tokens, row/sheet indices, field names, and counts. Paths,
      station/serial values, and notes never enter errors/logs; manufacturer/model may appear (decision 13).

Exit criteria: adapter/store/model tests cover versions, bounds, malformed containers, unknown fields, factors,
aliases, wildcards, duplicates, hashes, deterministic multi-source loading, revision conflicts/corruption, normalized
manufacturer compatibility, and privacy-safe diagnostics; existing tests remain green with no numerical change.
Validation, conflict detection, hashing, and match provenance land together.

Docs in this phase: schema/reference examples, normalized contract, architecture/data flow, store backup/migration notes,
and `CHANGELOG.md` for the new normalized column.

## Phase 2 — Coordinate-profile thin vertical slice

**Goal.** Exact custom coordinate matches, including leaf-level inheritance, work end to end. Initial activation is
import-before-data-load only.

Work:
- [ ] Wire canonical profile inputs into Python API, settings JSON, repeatable CLI file options, XLSX sheet selection,
      and stored profile IDs. Settings-relative and working-directory path rules follow spec §8; paths never serialize.
- [ ] Resolve every coordinate leaf independently through custom exact → bundled exact → custom wildcard → bundled
      wildcard → Default. In this slice only custom exact is enabled; reject alias/wildcard/transmission capabilities
      with `unsupported_profile_capability`, never ignore them. The capability gate itself is specified in
      [EQUIPMENT_PROFILE_SCHEMA.md](../EQUIPMENT_PROFILE_SCHEMA.md) §5: the parser represents full v1, activation
      checks capabilities separately.
      **Core preparation landed (no wiring):** `equipment_profiles/resolver.py` resolves all 15 leaves over the
      initial ladder (custom exact → bundled exact → bundled wildcard → Default) with the capability gate first,
      per-leaf inheritance preserving `False`/`0.0`, artifact/missing-maker Default bypass (a literally
      `"none"`/`"nan"`-named custom profile stays unreachable), closed fallbacks, once-validated compiled
      inputs (context, structure, hashes, claim references), immutable `CoordinateMatchRecord` reuse with
      correct `inherited` flags, structured complete/partial notices with permitted labels only, and safe
      counts/kinds-only reprs; `equipment_profiles/bundled.py` converts legacy settings entries to canonical
      profiles/indexes under `MAX_PROFILES` with order-independent deterministic IDs/hashes, per-entry
      materialized swap `False`, and a separate `Default`; `equipment_profiles/vendor_aliases.py` is the
      single alias home (settings re-exports). Shared stdlib missing-identity convention lives in
      `keys.clean_identity_text`, reused by the frame seam. No renderer/normalizer/settings mutation and no
      API/CLI/GUI/store activation wiring — that
      remains Phase 2 work, so Phase 2 is **not** complete.
- [ ] Preserve the dose distinction: `field_size_mode` is dose-affecting; `detector_side_length` is visualization-only
      (`src/guiskindose/geom_calc.py:20-83`, `src/guiskindose/beam_class.py:275-291`).
- [ ] Materialize per-leaf source provenance and issue the per-exam `partial match — fields inherited from
      bundled/Default` notice naming fields and sources. Show it before calculation and in Calculate, Results, dict/JSON,
      and rich exports. Fully specified profiles show `complete match` without the warning.
- [ ] Migrate the hidden run-configuration normalization list to the shared loader; bump run-state schema; read
      old documents; store IDs/schema/revisions/hashes/match/active values and manufacturer/model by default,
      never paths, notes, station, or serial.
- [ ] Own the **old run-state compatibility reader** here and nowhere else: this phase is the single place that
      reads pre-feature run-state normalization-profile documents and maps them into the shared loader
      (spec §10, decision 18). Phase 3 extends it only for newly supported capabilities.
- [ ] Refuse application to already-loaded exams in this slice. Importing or persisting a candidate is allowed, but
      Phase 3 owns safe post-load activation.
- [ ] Pin exact expected Tx/Ty/Tz, angle signs, swap, field size, detector size, structured match, inheritance notice,
      and export provenance across API/CLI/GUI test seams.

Exit criteria: coordinate-only partial and fully specified synthetic profiles produce identical values/provenance
across API, CLI, file formats, and stored reload; partial notices name every inherited leaf/source; no-profile golden
parity holds; unsupported capabilities fail closed; privacy-safe run-state round trips.

Docs in this phase: settings/CLI/API, run-configuration help, calculation review surfaces, feature inventory,
`AGENTS.md`, and `CHANGELOG.md`.

## Phase 3 — Matching lifecycle and atomic post-load activation

**Goal.** Complete coordinate matching and make activation safe for file, GUI-memory, and database sources.

Work:
- [ ] Add explicit manufacturer/model aliases and manufacturer-scoped model wildcards. A wildcard that outranks a
      bundled exact requires schema declaration plus GUI acknowledgement or CLI opt-in (decisions 3 and 9).
- [ ] Support multiple disjoint sources and enable/disable/remove. Resolve every conflict before any live mutation.
- [ ] Add the direct-`NormalizationSettings` compatibility adapter. Extend the Phase 2 run-state reader for
      newly supported capabilities as needed; its initial backward reader must already ship with the schema bump.
- [ ] Implement one atomic activation coordinator: freeze candidate source/revisions; validate; snapshot state;
      re-normalize every affected DICOM, single-tabular, and multi-file exam; rebuild pristine baselines; recompute
      detected origins; reapply session overrides exactly once; rebuild indexes; clear results/previews; include
      profile revision/active-set hash in cache keys; refresh tabs; commit—or restore everything.
- [ ] Reuse/extend the snapshot/restore principle already present at `src/guiskindose/gui/run_state.py:400-427`.
      Unavailable files, stale store revisions, unreadable records, and any later fault leave the old profiles, frames,
      origins, overrides, results, and caches unchanged.
- [ ] Block profile mutation while a calculation is busy and reject stale preview/calculation revisions.
- [ ] Fault-inject file read, store read, parse, conflict resolution, normalization, override reapplication, index/cache
      rebuild, tab refresh, commit, and rollback. Assert state always ends wholly old or wholly new.

Exit criteria: aliases/wildcards behave identically across sources; conflicts fail before mutation; every source kind
passes post-load success/rollback tests for DICOM, single-tabular, and multi-file sessions; overrides apply once;
mixed custom/bundled/Default exams and partial notices remain correctly attributed. Activation, re-normalization,
invalidation, and rollback are one merge unit.

Docs in this phase: lifecycle, wildcard acknowledgement, store recovery, and post-load activation help.

## Phase 4 — Custom patient-support transmission

**Goal.** Sparse measured/estimated rows compose with the selected baseline without changing no-profile behavior.

Work:
- [ ] Classify inherited evidence from reviewed provenance as measured/estimated/unknown; keep validity
      separate. Do not infer measurements from table presence. Test protected valid unknown nodes, replacement
      of invalid inherited nodes, and ignored custom estimated rows (decision 8).
- [ ] Build eligible exact matches and per-Al interpolation slices on canonical model + literal plane + kVp +
      Cu + Al. Measured custom rows may replace packaged nodes; estimated rows fill absent/invalid nodes or
      replace estimated packaged nodes, preserving valid measured/unknown values. Record eligibility and reasons.
- [ ] Retain the immutable original table. Existing-node replacements participate in its grid; additional rows
      participate only when their new axes form a complete usable rectangular slice. Otherwise keep them
      exact-match-only and use ordinary original lookup for uncovered queries. No synthesized factors or pivot
      holes; no loss of usable original interpolation from sparse additions (decisions 7 and 11).
- [ ] For an existing model/plane reject out-of-original-extent rows. For a new model/plane accept exact custom
      rows and complete custom slices, interpolate only within custom coverage, and preserve current unknown
      handling outside it. Keep explicit-SQLite same-key collisions as errors (decision 10).
- [ ] Select one eligible grid before calling the existing Al-snap + kVp × Cu interpolator. Preserve the original
      path where custom coverage is unusable; never add a 3-D interpolant or invent missing grid cells.
      Manufacturer never joins attenuation rows (decision 11).
- [ ] Keep all `k_tab_mode` states. Estimate mode ignores profile rows. Preserve plane A/B/single and application only
      to table-hit cells (`src/guiskindose/calculate_dose/add_correction_and_event_dose_to_output.py:99-102`).
- [ ] Preserve per-event `exact`/`interpolated`/`clamped` plus `estimated`/`no_device`/`invalid_inherited`/`fallback`
      (`src/guiskindose/corrections.py:54-66`). Add separate per-exam source
      `custom_measured`/`custom_estimated`/`baseline`/`mixed`.
- [ ] Show transmission partial coverage before calculation and in Calculate, Results, dict/JSON, and rich exports:
      custom versus inherited node/query counts, model/plane, evidence, statuses, and hashes. Loaded-but-unused rows are
      listed without a dose warning.
- [ ] Bump rich-export schema and preserve backward reading/additive public output fields.
- [ ] Prove custom factors change only table-hit cells and no-profile PSD goldens remain unchanged.

Exit criteria: transmission-only partial, fully specified, and mixed coordinate+transmission profiles are covered;
partial notices and exports agree; tests include measured/estimated/baseline/mixed, sparse grids, exact/interpolated/
clamped and every existing non-grid status, out-of-extent rejection, explicit-SQLite collision/coexistence, A/B/single,
mixed exams, and no-profile parity. Include a 2 × 2 original grid plus an isolated intermediate node:
exact custom lookup works, uncovered lookup retains original interpolation, and no non-finite factor escapes.
Also prove complete expanded slices affect interpolation, new-model range limits retain current handling,
and single-node profiles do not cover arbitrary beam qualities. Resolution, dose use, notices, status, and
provenance land together.

Docs in this phase: PSD algorithm, correction-data reference, calculation/results help, output schema, and `CHANGELOG.md`.

## Phase 5 — GUI authoring and persistence workflow

**Goal.** A physicist can complete every profile workflow without editing a file.

Work:
- [ ] Build a discoverable Equipment Profiles card with JSON/CSV/TSV/XLSX import, validation preview, active/unused/
      complete/partial/conflict states, per-exam use matrix, enable/disable/remove, and atomic activation.
- [ ] Build manual editors for every v1 coordinate leaf and for adding/editing/removing transmission rows, including
      measured/estimated evidence, source/date, bounded notes, inline validation, and inherited-field/coverage preview.
- [ ] Add local-store browsing, save-as-new/version, optimistic conflict handling, reload, enable, delete confirmation,
      and corruption/recovery messaging. Saving requires identity/provenance and may target store, canonical JSON export,
      or both.
- [ ] Limit “save session correction as profile” to equipment-design values (table origin baseline, translation/angle
      signs, axis swap). Never persist patient offsets or study-specific nudges; do not infer a reusable value silently.
 - [ ] Export canonical JSON through atomic native writes (`Path.replace()`) or browser download. Export is explicit;
      default run/rich exports remain path/note-free.
 - [ ] Add "Download example" and "Download blank template" actions to the Equipment Profiles card, browser mode via
      `ui.download()` and native mode via the OS save dialog, reusing the mechanism in
      `src/guiskindose/gui/tabs/corrections.py:174-188`. Serve the packaged files from `example_data/equipment_profiles/`.
 - [ ] Add in-app help for profile authoring: field/column dictionary, the filled example annotated, and the
      measured-vs-estimated evidence rule, matching the packaged README.
 - [ ] Before final activation show manufacturer/model, profile/source/match level, each coordinate value and inheritance
      source, transmission evidence/source/status, and interpolation/clamping/fallback/partial notices.

Exit criteria: NiceGUI tests cover every input source, manual coordinate and transmission entry, new model, alias,
wildcard acknowledgement, conflicts, active/unused, coordinate-only partial, transmission-only partial, fully specified,
mixed exams, store version/save/reload, JSON export/reload, post-load rollback, and browser download. Every packaged
example loads through the real loader and every invalid example fails with its locked error code. Patient-specific
values cannot enter a reusable profile.

Docs in this phase: GUI help and required UI-copy/help-registry/glossary/feature-matrix sources; run sync and registry checks.

## Phase 6 — Release proof and plan closure

**Goal.** Reconcile documentation, prove packaged behavior, and archive the completed plan.

Work:
 - [ ] Document explicit SQLite coexistence. A `k_tab`-only extraction utility remains deferred unless separately
      required; it must never claim to migrate custom HVL or medium data.
 - [ ] Reconcile behavior docs already updated by earlier phases; update release notes, maintenance evidence, support/
      privacy guidance, and the documentation catalog.
 - [ ] Run packaged-wheel clean-directory proof — including that `example_data/equipment_profiles/` ships in the wheel
      and its examples still load — and final API/CLI/GUI/store/export parity and no-profile numerical suites.
 - [ ] Record phase evidence, mark this plan complete, move it to `dev-docs/plans/archive/`, and update catalog links.

Exit criteria: all acceptance criteria have automated evidence; full validation and wheel proof pass; privacy gates pass;
user-only smoke tasks are recorded; the active plan is ready to archive.

## Manual smokes (tracked, not phase gates)

Automate browser-mode behavior in Phases 2–5. When implementation lands, add only the user-only passes to
`dev-docs/TO_DO.md` → Manual Smokes: native pywebview import/manual authoring/store activation and Windows native
open/save dialogs. Record completed automated browser evidence in this plan and the maintenance log, not as manual debt.

## Validation required for every code phase

Each code phase records the smallest targeted tests plus the applicable shared gates:

- targeted unit/integration tests and full `python -m pytest`;
- `python -m compileall src/guiskindose` and `python -m ruff check src tests`;
- `basedpyright` and `uv run --extra dev --extra gui --locked python scripts/check_complexity.py`;
- `python scripts/check_file_sizes.py`; GUI phases also run `pytest tests/gui -n auto`;
- privacy admission/sensitive-content checks and privacy-safe log/error tests;
- `python scripts/check_doc_freshness.py` plus affected help/UI-copy/feature-matrix/agent-guidance checks;
- `python -m build` and `python scripts/verify_distribution.py` when packaging changes.

Phase-specific tests must assert values and serialized forms, not only UI text. Cross-platform-sensitive native behavior
gets macOS/Linux and Windows manual evidence as applicable.

## Progress log

- 2026-10-11 — **Sonar validation cleanup (no behavior change).** Cleared the 172 equipment-profile
  branch findings: NaN idioms to `math.isnan`, negative-zero normalization to exact `+ 0.0` (bit-verified),
  complexity splits, unused-param/redundant-call removals, exception-test hoisting, specific exception
  types, split assertions, and explicit ASCII regex flags without suppressions. Parser/privacy limits,
  immutable records, capabilities, and exact scientific contracts preserved; full float-semantics check
  passes. No app wiring; Phase 2 remains open.
- 2026-10-11 — **Coordinate resolution core preparation landed (no wiring).** `resolver.py` (stdlib-only,
  immutable) resolves all 15 leaves over custom exact → bundled exact → bundled wildcard → Default with the
  capability gate first, per-leaf inheritance, artifact/missing-maker Default bypass, closed fallbacks with a
  once-validated preparation boundary, `CoordinateMatchRecord` reuse, and structured complete/partial notices;
  `bundled.py` converts legacy settings entries under `MAX_PROFILES` with order-independent deterministic
  IDs/hashes, per-entry materialized swap `False`, and bundled-only aliases; `vendor_aliases.py` is the single
  alias home (settings re-exports); safe reprs throughout. 63 targeted tests pin settings-selection parity
  (Siemens/Philips/GE-family/Default, all complete), miss paths, partial/zero/False behavior, all five
  capability tokens, store context, immutability, and privacy. No renderer/normalizer/settings
  mutation and no API/CLI/GUI/store activation — Phase 2 remains open.
- 2026-10-11 — **Normalized manufacturer identity landed** (no activation/matching wiring). One exam
  carries exactly one canonical (manufacturer, model) pair: new `src/guiskindose/exam_identity.py` seam
  (cleaning, raw/canonical pair listing, descriptive classification, fail-closed guard);
  `rdsr_normalizer()` emits a canonical `manufacturer` column with exact per-event spellings and rejects
  distinct makers, same-maker model variation, and known+unknown mixes before profile selection;
  `normalized` schema recognizes optional `manufacturer`, materializes all-`None` with a count-only
  legacy warning when absent/blank, and checks each study-id group individually with opaque positions;
  DoseTrack maps each row's Equipment Name per-row through `MODEL2MANUF` (no first-name overwrite);
  export identity comes from one consistent row. 63 targeted tests; full-frame digest regen adds only
  the `manufacturer` column; golden dose/k_tab, GUI (420), CLI, and export suites green. Phase 1 stays
  incomplete (per-exam match-record wiring and activation-time duplicate detection remain; Phase 2/3 own
  match-record application/activation).
- 2026-10-11 — **Index review fixes (still inert).** Corrected the index slice against review: entries are now
  strictly bounded (real-`Sequence` check with strings/bytes/iterables rejected, declared length capped by
  `MAX_PROFILES` before copying, bounded materialization against lying lengths, aggregate logical rows capped
  by `MAX_AGGREGATE_ROWS` before claim expansion); entry context is strictly checked (exact-`str` source kind
  rejecting subclasses and permissive-equality objects, exact-`int` revision in `1..MAX_REVISION` with
  booleans rejected, lowercase-64-hex hash); every profile is structurally gated (tuples not lists, exact
  `bool`, finite non-boolean numbers, exact nested model types) and re-run through the existing document
  validation boundary at compile time with the claimed hash verified (`conflicting_profile_metadata` on
  mismatch); profiles are ordered by exact ID before the canonical conflict check; all public types carry
  value-free reprs (counts, source-kind tokens, flags, hashes only); the wall-clock timing test is replaced by
  a deterministic no-traversal probe plus sorted-key assertions; permutation tests assert full compiled
  equality; lookups normalize each key once. 66 targeted tests. Phase 1 stays incomplete (per-exam
  match-record wiring, and activation-time duplicate detection remain).
- 2026-10-11 — **Compiled lookup indexes landed**, still inert. `indexes.py` compiles immutable coordinate and
  transmission indexes once from validated profiles with source-kind/hash/revision context: coordinates by
  canonical manufacturer/model (exact, alias, and manufacturer-scoped wildcard slots stored without activation),
  transmission by canonical model/literal plane with original numeric row keys in sorted node groups. Global
  conflicts are detected via the canonical check before anything is published; retrieval bisects sorted key
  tables so per-event lookups never scan profiles; internals are tuples only and results are identical
  regardless of source order. Phase 1 stays incomplete (per-exam match-record
  wiring, and activation-time duplicate detection remain).
- 2026-10-11 — **Store hardening round**: enabled-revision listing uses LEFT JOIN and rejects a missing
  revision instead of silently omitting it from conflict validation; growth caps run in every transaction with
  bounded single-integer queries, and total tracked identities (records plus tombstones) are capped at 1024;
  schema verification compares exact DDL text, forbids extra metadata keys and any trigger/view, and re-runs
  with a foreign-key violation check inside every transaction; stored payloads are byte-bounded before parsing
  and all payload failures normalize to `store_corruption`; `set_enabled`/`delete_record` accept an optional
  `expected_generation` alongside the content revision. Phase 1 stays incomplete.
- 2026-10-11 — **Store review fixes**: nine commit-blocking defects fixed in the inert store slice, each
  with a regression test. A matched save-CAS was rejected before the record lookup (now: validate the argument,
  then compare after lookup; updating requires `expected_current_revision`); re-enabling an enabled record
  double-counted its own claim (the candidate is now excluded before its current revision is appended); saving
  to an enabled record no longer commits a conflicting enabled set (the would-be enabled set is validated
  before commit); unexpected exceptions now roll back, close safely, and normalize closed instead of leaking a
  transaction (reads use plain `BEGIN`, cancellation is preserved); payload length and storage type are queried
  before the text is fetched and the parsed row count is rechecked; listings verify each payload; rows parse
  with no coercion; schema verification covers primary keys, foreign keys, types, constraints, and triggers;
  selections are length-checked before copying with duplicate IDs rejected and all integers range-checked
  before binding; and NUL paths fail closed. The contract now requires CAS on update, bumps a `generation`
  token on every mutation, and tombstones deletes so revision numbers are never reused. `profile_store.py`
  stays under the file-size gate via `store_reads.py`/`store_writes.py` operation modules.
- 2026-10-11 — **Local user profile store landed**, still inert. `profile_store.py` is a transactional
  stdlib-`sqlite3` repository plus `store_types.py` immutable types, implementing the §12 contract: explicit
  initialize-or-verify (fresh-empty creation at version 1; unversioned-nonempty, future, and corrupt databases
  rejected without mutation); `BEGIN IMMEDIATE` writes with rollback on any failure; optimistic
  `expected_current_revision` checks on save/enable/delete; payload re-parse, re-validation, and re-hash on every
  read; new records start disabled; unsupported capabilities persist but are never activated; enabling runs the
  canonical conflict check across the would-be enabled set atomically; snapshots load in one read transaction
  with selection/aggregate bounds checked before payloads are read. The revision-set source hash is locked and
  exposes `source_kind: "store"`. Phase 1 stays incomplete (per-exam match-record
  wiring, and activation-time duplicate detection remain).
- 2026-10-10 — **XLSX silent-loss fixes**: two defects in the inert XLSX adapter each produced a *successful*
  parse with missing content. A row conversion truncated to the header width, so a populated cell beyond the
  19-column header (including a formula or error cell) was discarded; populated extra cells now fail the whole
  load, while blank padding outside the header is still tolerated. And openpyxl's read-only parser is
  dimension-driven, so a workbook rewriting its declared `<dimension>` to `A1:S3` was read as one profile and
  two rows; the adapter now validates every worksheet part with a bounded streaming `expat` parser that ignores
  the declared dimension for sizing and enforces the row/column/cell budgets on the coordinates actually
  present, rejecting out-of-range, repeated, and malformed coordinates, DTDs, entities, and external entity
  references. With the real bounds known first, the reader's dimension is discarded so an understated workbook
  is read in full and an overstated one cannot allocate padding it does not hold — no silent truncation either
  way — and the budgets are re-enforced on the reader's actual iteration. Also added a typed-cell policy that
  accepts a number or boolean only where the schema's type allows it (never coercing to text or to `1`), with
  the coordinate `value` column resolved per leaf; a sheet-count ceiling read from the workbook's own worksheet
  catalog rather than part filenames; and one documented boundary over the whole untrusted-container path that
  normalizes any residual library exception family to `malformed_container` with the cause suppressed and
  always closes the workbook. The inaccurate "dimension truncation is a limitation" claim in the schema
  contract was removed. Tests cover both silent-loss regressions, understated and inflated dimensions, actual
  coordinate bounds and tampering, corrupt XML with a valid CRC, the typed-cell policy across every column
  kind, 20-column promotion headers, extra-cell rejection, and privacy.
- 2026-10-10 — **XLSX adapter landed**, still inert. `xlsx_preflight.py` preflights the OOXML container
  before any worksheet is read: the archive is opened from the in-memory byte snapshot, the entry list is
  bounded, duplicate and directory-spoofing entry names are rejected, and every member is inflated by
  *streaming real decompressed bytes* in chunks rather than trusting the central directory, so a forged
  `file_size` cannot smuggle a zip bomb. Worksheets are counted by iterating actual rows, and the sheet index
  defaults to the first worksheet, with an optional explicit index (spec §4). `xlsx_source.py` reads only the selected sheet with `read_only=True`, `data_only=False`,
  `keep_links=False`, converts typed cells to the flat text cells the shared CSV seam consumes (so there is no
  CSV round trip and no second flat parser), and routes the same canonical validation and hashing.
  Typed-cell policy: numbers stay numbers, booleans are accepted only where the schema expects one and
  normalize to `true`/`false` (never coerced into `1` for a numeric column), dates are valid only in the `date`
  column and must be exactly midnight rendering as strict ISO `YYYY-MM-DD`, formulas are rejected rather than
  read as their cached value, and spreadsheet error cells are rejected. openpyxl is imported inside the
  adapter functions, so a JSON/CSV/TSV-only use never loads the spreadsheet stack. Every failure carries
  source kind `xlsx` and an allowlisted column, `record_type`, or integer count; sheet names, paths, cell
  text, and library messages never appear, and raw causes are suppressed. Tests build workbooks in memory or
  under `tmp_path` (no tracked binary) and cover CSV-to-workbook canonical equivalence, sheet selection and
  its errors, typed cells, strict headers/rows/types, formulas, errors, bounded snapshots, zip-inflation
  lies, container corruption, and privacy. The schema contract gained §6B, and the plan now records the
  packaged XLSX/TSV variants and `MANIFEST.in` inclusion as outstanding with no clearance added.
  *(Superseded the same day: the "dimension truncation limitation" recorded here was wrong — it permitted silent
  loss, and see the silent-loss fixes entry below.)*
- 2026-10-10 — Design and execution documents aligned; implementation not started.
- 2026-10-10 — Phase 0 authoring started; core implementation blocked pending four contract decisions (new-model
  transmission bounds for a model with no baseline grid; sparse-overlay rectangular-grid completion/NaN policy
  with a reproduced `(nan, 'interpolated')` case; authoritative baseline measured/estimated classification
  including `invalid_inherited` nodes; multi-model alias mapping / wildcard promotion / override syntax /
  tabular version encoding). This initial broad hold is superseded by the agreement below. The Phase 2/Phase 3 contradiction over the
  old run-state compatibility reader was resolved by assigning it wholly to Phase 2.

- 2026-10-10 — Maintainer accepted the recommended fallback, new-model, sparse-grid, evidence, and schema
  rules. Updated spec decisions and Phase 4 proof obligations; replaced the blanket core hold with per-slice
  contract locks. Common/coordinate work can proceed after its own locks; runtime implementation remains pending.

- 2026-10-10 — **Common + coordinate contract corrected and its JSON/core slice implemented** as
  [EQUIPMENT_PROFILE_SCHEMA.md](../EQUIPMENT_PROFILE_SCHEMA.md) (registered in `dev-docs/index.md`, linked from
  the spec and this plan) plus the stdlib-only package `src/guiskindose/equipment_profiles/`. The contract was
  corrected on the parent's review: it is an implementation contract; the envelope carries only
  `schema_version` (exact integer `1`, boolean rejected) and a non-empty bounded `profiles` array; six
  coordinate blocks with 15 individually optional nested leaves; JSON duplicate keys rejected via an
  `object_pairs_hook`; `null` is not omission; strict UTF-8 with an optional BOM. Identity uses the existing
  normalized manufacturer/model key algorithms with no bundled alias inheritance, JSON alias shorthand is an
  array only (`|` separators stay a tabular spelling), alias-map targets must resolve to a listed model, and
  empty aliases normalize to absent. Duplicate rules: `profile_id` duplicates fail across logical profiles and
  sources even when identical; duplicate coordinate claims fail even when identical; duplicate transmission
  keys fail within and across profiles independent of manufacturer; only a tabular grouping may repeat
  metadata that agrees. Bounds gained `models` ≤ 32, XLSX ≤ 16 sheets, JSON depth 16, and an explicit logical-row
  definition for JSON/memory. Canonical serialization normalizes numeric leaves to float, keeps
  `schema_version` integer, omits empty optional texts/maps/arrays/blocks and `false` promotion, sorts models /
  alias sets / transmission rows / active profiles, and wraps profiles as `{"schema_version":1,"profile":…}`
  and active sets as `{"schema_version":1,"profiles":[…}` with provenance included and source context
  excluded; the stored revision-set hash is explicitly **not** locked. Per-leaf provenance carries revision,
  profile hash, and source kind (`memory` added), `inherited` includes lower-priority custom wildcards, and the
  illustrative match record now uses a partially supplied profile ID. Error field paths use allowlisted names
  only and never echo an unknown user key; raw exception causes are suppressed. `store_corruption`,
  `existing_model_out_of_extent`, and `explicit_sqlite_collision` are reserved codes, not implemented.

  The implementation slice landed: immutable typed frozen-dataclass canonical models; a closed value-free error
  type and code constants; bounded JSON byte/path and in-memory parsing; full-v1 structural validation;
  deterministic canonical serialization with profile/active-set/source-byte hashes; across-source
  duplicate/conflict validation; immutable match-record types; and a separate initial capability gate that
  rejects every alias, wildcard/promotion, and transmission domain while the parser still represents the full
  schema. **No application wiring was added and no normalization, calculation, GUI, or CLI behaviour changed.**
  Store schema and migrations, run-state and rich-export version locks, CSV/TSV/XLSX adapters and fixtures,
  transmission eligibility/evidence/grid work, the invalid-example fixture set, and `MANIFEST.in` packaging
  inclusion all remain outstanding, so Phase 0 stays incomplete.

- 2026-10-10 — **Commit-blocking defects fixed in the JSON/core slice** after review. Nine corrections:
  (1) canonical `model_aliases` now emits a real JSON object `{alias: target}` instead of a list of pairs, with
  map targets resolved to the *listed* model spelling so an equivalent normalized spelling hashes like the
  shorthand, plus an active-set serialize/reload hash-equality test covering aliases, provenance, partial
  coordinate fields, and transmission rows; (2) missing required transmission numeric fields return
  `missing_required_field` with their own field path instead of a `KeyError`; (3) integers too large for a
  double are caught and rejected as `invalid_number` instead of leaking `OverflowError`; (4) an empty
  `model_aliases` list means "no aliases" for multi-model and wildcard profiles, checked before the
  ambiguity rule, matching the packaged wildcard example; (5) models with an empty normalized key are rejected
  and wildcard variants such as `" * "` are treated as the wildcard consistently, while transmission rows may
  no longer target the wildcard; (6) file reads use one bounded `read(MAX_SOURCE_BYTES + 1)` instead of
  reading everything and then checking, closing the size-then-read race; (7) conflict detection now only lets
  non-empty coordinate profiles claim coordinate slots, expands claims across manufacturer and model aliases,
  rejects alias keys that would collide with a *different* model, and compares transmission keys on the
  normalized model key, so an alias equivalent to its own model stays allowed and coordinate-only versus
  transmission-only profiles may share an identity; (8) `ParsedDocument.profiles` is typed
  `tuple[Profile, ...]`, depth errors use the caller's source kind, every document enforces the aggregate
  logical-row ceiling itself, and early count checks plus a traversal node budget bound work before a deep or
  broad mapping is walked; (9) a `CHANGELOG.md` entry was added for the inert experimental core and the
  Phase 1 item is explicitly **not** checked off complete.

- 2026-10-10 — **CSV and TSV adapters landed** for the tabular slice, still inert. `tabular_common.py` holds the
  shared primitives (strict UTF-8 with optional BOM and no unpaired surrogates, strict header validation that
  never echoes a duplicate or unknown column name, row-width and record-type applicability checks, scalar/list/
  alias-map cell parsing) and `csv_source.py` / `tsv_source.py` are thin delegations that differ only in
  delimiter and accepted suffix. Both assemble the same canonical document mapping the JSON adapter produces, so
  the packaged CSV and the packaged JSON have identical profile hashes, leaf values, and transmission values
  while their raw source hashes differ. Grouping is two-pass so coordinate and transmission rows may precede
  their `profile` row; repeated `profile` metadata may agree and disagreement fails `conflicting_profile_metadata`
  while a repeated coordinate leaf fails `duplicate_json_key` even when identical. Tabular cells accept only the
  exact boolean forms `true`/`false`, reject `NaN`/`Infinity`/`1e999`/`8_0` and booleans as numbers, treat blank
  filtration as `blank_disallowed_cell`, and treat null-like strings as literal text. Every adapter failure
  carries source kind `csv`/`tsv`, never `json`, and no raw cell, unknown column, file path, or nested cause.
  Bounds run during row accumulation, before any profile object is built. Implemented with the standard library
  only — no third-party reader and no DataFrame materialization — reading the decoded byte snapshot once. The
  flat-column table and tabular rules are restored in
  [EQUIPMENT_PROFILE_SCHEMA.md](../EQUIPMENT_PROFILE_SCHEMA.md) §6A, with the packaged README named as the
  authoritative field dictionary. **Still outstanding at the time:** XLSX, the user store, indexes, normalization, API, CLI,
  GUI, store wiring, packaged TSV fixtures, and `MANIFEST.in` inclusion.

## Decision log

- 2026-10-10 — Phase 0 implements the authoritative 20 decisions in spec §11; later changes amend the spec first.
- 2026-10-10 — The four Phase 0 blockers above are recorded as **unresolved** pending owner decisions; this plan
  did not resolve policy or add baseline model mappings; this open status is superseded by the agreement below.

- 2026-10-10 — Rules agreed in spec §§3–7. Missing custom coverage retains original handling; sparse additions
  cannot corrupt usable original interpolation. Preserve valid unknown evidence and explicit-SQLite collision
  errors. Remaining Phase 0 engineering locks are tracked per slice, not waived.

- 2026-10-10 — Where the spec left a routine engineering value unspecified, the common/coordinate lock chose a
  conservative explicit value and recorded it in [EQUIPMENT_PROFILE_SCHEMA.md](../EQUIPMENT_PROFILE_SCHEMA.md)
  (file-byte and row ceilings, profile/alias/text/ID limits, numeric ranges) rather than leaving the choice
  implicit. No maintainer-approved scientific rule was changed, no fallback/grid/evidence policy was redesigned,
  and no baseline model mapping was added. Transmission matching key remains model + plane + kVp + Cu + Al.

## Risks and mitigations

- **Silent dose change:** independent coordinate/transmission ladders, concrete pre-calc partial notices, fail-closed
  conflicts/capabilities, table-hit proof, and serialized provenance.
- **Stale or mixed session:** import-before-load thin slice, then one atomic coordinator with immutable snapshots,
  profile-aware cache keys, busy guard, and fault-injected rollback.
- **Source changes after validation:** exact file bytes, GUI submission, or selected database revisions are frozen and
  hashed; calculation consumes only that snapshot.
- **Adapter drift:** every source maps to one canonical validator/resolver; parity fixtures compare canonical hashes,
  matches, notices, and outputs.
- **Store damage or concurrent edits:** transactions, schema migrations, optimistic revisions, bounded reads, payload
  hash verification, backups/recovery guidance, and no mutation of bundled or legacy correction data.
- **Privacy/path leakage:** manufacturer/model are explicitly safe; station/serial remain gated and absent from logs;
  paths/notes stay out of default exports and diagnostics.
- **Sparse-grid misunderstanding:** node ownership, mixed interpolation source, inherited counts, and per-event status
  remain separate and visible.
- **Lookup cost:** bounded rows, compiled model/plane indexes, cached composite pivots, and a no-full-scan assertion.
