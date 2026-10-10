# Custom Equipment Profiles — Execution Plan

Status: **Active — not started**
Design authority: [CUSTOM_EQUIPMENT_PROFILES_SPEC.md](CUSTOM_EQUIPMENT_PROFILES_SPEC.md) (reviewed 2026-10-10)
Created: 2026-10-09 · plan updated 2026-10-10
Parent roadmap: [CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md](CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md)
Delivery: implement on feature branches after Phase 0 sign-off; no direct-to-`main` work. Keep calculation,
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
  out-of-extent, or conflicting content fails closed (decisions 6, 7, and 15).
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
- [ ] Sign off all 20 decisions in spec §11 without changing their meaning implicitly in code. Record amendments in
      both documents before implementation.
- [ ] Publish the canonical profile field table: required stable `profile_id`; manufacturer/models; separate explicit
      aliases; independently optional coordinate/transmission domains with at least one non-empty; partial coordinate
      leaves; transmission evidence/source/date; bounded notes; unknown fields rejected (decisions 3, 6, 8, 12, 16).
- [ ] Lock source schemas (decision 4): nested JSON document; ONE flat tabular model shared by CSV/TSV and XLSX
      (strict `record_type` rows, same column set, one sheet, sheet selectable for multi-sheet workbooks);
      canonical in-memory GUI submission; canonical JSON payload per stored revision. Provide one valid example per
      file format and invalid cross-format examples.
- [ ] Lock the separate user-store schema and migration policy: record/revision IDs, canonical payload, profile/hash/
      active-set metadata, timestamps, transactions, uniqueness, and corruption handling (decision 5).
- [ ] Set exact maximum file bytes, XLSX expanded/member/sheet limits, aggregate 10,000-row ceiling, profile/alias
      counts, ID lengths, and text lengths. The row ceiling follows `src/guiskindose/kerma_correction.py:42,324-362`.
- [ ] Lock canonical serialization and SHA-256 rules for floats, key order, omitted values, per-profile hashes,
      exact-file-byte hashes, GUI snapshot hashes, stored selected-revision-set hashes, and active-set hashes
      (decision 12).
- [ ] Lock coordinate leaf resolution and provenance: default candidate order; explicit wildcard promotion; nested
      x/y/z and angle leaves; `complete match` versus concrete `partial match` notice (decisions 6 and 9).
- [ ] Lock the transmission key, extents, measured/estimated overlay, explicit-SQLite collision rule, one-interpolator
      composition, row fallback, and status/source dimensions (decisions 7, 8, 10, 11). The current key/interpolator is
      verified at `src/guiskindose/corrections.py:327-380`; the attenuation header has no manufacturer column
      (`src/guiskindose/table_data/correction_table_and_pad_attenuation.csv:1`).
- [ ] Lock stable error codes, including malformed/oversized input, unsupported source/schema/capability, duplicate
      claim, alias ambiguity, wildcard acknowledgement required, out-of-extent row, explicit-SQLite collision,
      store conflict/corruption, and activation rollback.
- [ ] Lock privacy/export fields (decision 13): manufacturer/model and canonical `matched_input_key` are default-safe;
      station/serial retain `include_identifiers` for per-event output and never enter logs; notes and profile paths are
      omitted by default. This intentionally replaces the current manufacturer/model gating at
      `src/guiskindose/gui/run_state.py:155-178`.
- [ ] Lock run-state/rich-export schema bumps and old-profile compatibility reader (decision 18).
- [ ] Define the exact pre-calculation, Calculate, Results, and export representations for field inheritance,
      transmission partial coverage, active/unused profiles, and structured immutable match records (decision 20).

Exit criteria: signed decision list; schemas and examples parse mechanically; limits/error catalog/privacy matrix are
complete; no open semantic question blocks Phase 1.

## Phase 1 — Canonical model, source adapters, store, and identity contract

**Goal.** Parse every non-GUI source and produce immutable validated profile sets without changing calculations.

Work:
- [ ] Add a small core package for canonical profile/domain records, source provenance, validation, hashing, conflict
      detection, compiled match indexes, and stable errors. No calculation or GUI imports in the core.
- [ ] Implement JSON, CSV/TSV, and XLSX adapters. Read bounded file bytes once, hash and parse the same snapshot;
      preflight XLSX container expansion/sheets/rows/text before materialization. Match the kerma loader's accepted
      suffix family (`src/guiskindose/kerma_correction.py:348-376`) without sharing kerma-specific factor rules.
- [ ] Implement an in-memory adapter for already-structured GUI/API values. It deep-copies and canonicalizes one
      submission before validation so later form mutation cannot alter an activation candidate.
- [ ] Implement the local user-store repository: initialize/migrate in the per-user app-data area; transactional
      create/version/read/list/enable/delete; optimistic revision checks; payload/hash verification; bounded queries;
      no coupling to bundled tables or `corrections_db_path`.
- [ ] Load stored revisions in one read transaction and materialize an immutable selected-revision snapshot. Test that
      file → store → canonical JSON preserves profile hashes while source/revision provenance changes appropriately.
- [ ] Add canonical `manufacturer` to every raw-normalized frame and the normalized adapter contract; warn for legacy
      normalized data lacking it. Keep mixed coordinate identities split/rejected before matching.
- [ ] Add immutable per-exam coordinate/transmission match records with domain, profile/revision, source/level,
      canonical matched key, affected count, hashes, and leaf/row provenance—not mutable fields on
      `NormalizationSettings` (decision 20).
- [ ] Compile coordinate indexes by canonical manufacturer/model and transmission indexes by canonical model/literal
      plane. Assert event resolution does not scan the full user table per event.
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
      with `unsupported_profile_capability`, never ignore them.
- [ ] Preserve the dose distinction: `field_size_mode` is dose-affecting; `detector_side_length` is visualization-only
      (`src/guiskindose/geom_calc.py:20-83`, `src/guiskindose/beam_class.py:275-291`).
- [ ] Materialize per-leaf source provenance and issue the per-exam `partial match — fields inherited from
      bundled/Default` notice naming fields and sources. Show it before calculation and in Calculate, Results, dict/JSON,
      and rich exports. Fully specified profiles show `complete match` without the warning.
- [ ] Migrate the hidden run-configuration normalization list to the shared loader; bump run-state schema; read old
      documents; store IDs/schema/revisions/hashes/match/active values and manufacturer/model by default, never paths,
      notes, station, or serial.
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
- [ ] Add the direct-`NormalizationSettings` compatibility adapter and old run-state profile reader.
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
- [ ] Build the effective grid on canonical model + literal plane + kVp + Cu + Al. Packaged custom measured nodes may
      replace same-key packaged nodes; custom estimated nodes fill only in-extent nodes with no measured value.
- [ ] Preserve row-level fallback: uncovered nodes remain baseline; uncovered model/plane queries retain current
      interpolation/clamping/fallback. Reject out-of-extent rows. For explicit `corrections_db_path`, reject every
      same-key custom/SQLite collision and allow only non-overlapping in-extent rows (decisions 7, 8, 10).
- [ ] Overlay first, then call one existing Al-snap + kVp × Cu clamp-interpolator. Do not create a second pass or 3-D
      interpolant. Manufacturer never joins attenuation rows (decision 11).
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
mixed exams, and no-profile parity. Resolution, dose use, notices, status, and provenance land together.

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
- [ ] Before final activation show manufacturer/model, profile/source/match level, each coordinate value and inheritance
      source, transmission evidence/source/status, and interpolation/clamping/fallback/partial notices.

Exit criteria: NiceGUI tests cover every input source, manual coordinate and transmission entry, new model, alias,
wildcard acknowledgement, conflicts, active/unused, coordinate-only partial, transmission-only partial, fully specified,
mixed exams, store version/save/reload, JSON export/reload, post-load rollback, and browser download. Patient-specific
values cannot enter a reusable profile.

Docs in this phase: GUI help and required UI-copy/help-registry/glossary/feature-matrix sources; run sync and registry checks.

## Phase 6 — Release proof and plan closure

**Goal.** Reconcile documentation, prove packaged behavior, and archive the completed plan.

Work:
- [ ] Document explicit SQLite coexistence. A `k_tab`-only extraction utility remains deferred unless separately
      required; it must never claim to migrate custom HVL or medium data.
- [ ] Reconcile behavior docs already updated by earlier phases; update release notes, maintenance evidence, support/
      privacy guidance, and the documentation catalog.
- [ ] Run packaged-wheel clean-directory proof and final API/CLI/GUI/store/export parity and no-profile numerical suites.
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

- 2026-10-10 — Design and execution documents aligned; implementation not started.

## Decision log

- 2026-10-10 — Phase 0 implements the authoritative 20 decisions in spec §11; later changes amend the spec first.

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
