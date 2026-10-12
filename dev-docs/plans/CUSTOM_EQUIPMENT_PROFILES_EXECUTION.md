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
- [x] Lock privacy/export fields (decision 13): manufacturer/model and canonical `matched_input_key` are default-safe;
      station/serial retain `include_identifiers` for per-event output and never enter logs; notes and profile paths are
      omitted by default. *(Contract locked 2026-10-11 in
      [EQUIPMENT_PROFILE_RUNSTATE_EXPORT_CONTRACT.md](../EQUIPMENT_PROFILE_RUNSTATE_EXPORT_CONTRACT.md) §§3–4, 8–9.
      Implementation — including replacing the current manufacturer/model gating at
      `src/guiskindose/gui/run_state.py:155-178` — remains open.)*
- [x] Lock run-state/rich-export schema bumps and old-profile compatibility reader (decision 18).
      *(Contract locked 2026-10-11 in [EQUIPMENT_PROFILE_RUNSTATE_EXPORT_CONTRACT.md](../EQUIPMENT_PROFILE_RUNSTATE_EXPORT_CONTRACT.md)
      §§2–3, 5–6: run-state 1→2, rich-report 3→4, dict/JSON export stays 3 while additive, v1 readers retained,
      self-contained reproducibility without reopening stores/files. Emission and application remain open.)*
- [ ] Define the exact pre-calculation, Calculate, Results, and export representations for field inheritance,
      transmission partial coverage, active/unused profiles, and structured immutable match records (decision 20).
      *(Contract locked 2026-10-11 in [EQUIPMENT_PROFILE_RUNSTATE_EXPORT_CONTRACT.md](../EQUIPMENT_PROFILE_RUNSTATE_EXPORT_CONTRACT.md)
      §7: coordinate API shape implemented; coordinate capture contract locked; GUI surfaces, rich-report v4,
      and run-state v2 implementation remain open. Transmission representations remain unlocked until Phase 4.)*

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

Remaining Phase 0 work is the still-open per-slice contracts and fixtures, not deciding those
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
      API/CLI/GUI/store activation wiring.
- [ ] Assemble a frozen multi-source session (files/memory/store) with import-before-load semantics as
      core preparation (no wiring): bounded snapshot factory, canonical cross-kind conflicts, capability
      gate before usability, compiled index + prepared resolver context once, active-set hash, default-safe
      provenance, per-exam resolution without recompiling. **Landed as core preparation**
      (`equipment_profiles/session.py` + public prepare/resolve seam in `resolver.py`/`preparation.py`,
      no renderer/normalizer/settings/API/CLI/GUI/store-activation wiring): request collections bounded
      before copying with incremental profile/row ceilings and short-circuit; file byte snapshots with
      SPEC §8 path rules and a closed path boundary; revalidated store snapshots with compiler-output
      payloads; canonically ordered payload/provenance with input-order diagnostics; validated
      `__post_init__` prepared contexts with the gate at preparation; per-exam `resolve()` with bundled
      compiled or prepared and zero recompilation. Phase 2 is **not** complete.
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

Implementation history is preserved in [CUSTOM_EQUIPMENT_PROFILES_PROGRESS.md](CUSTOM_EQUIPMENT_PROFILES_PROGRESS.md).

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
