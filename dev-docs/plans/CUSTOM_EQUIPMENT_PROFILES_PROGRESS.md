# Custom Equipment Profiles — Progress History

Implementation history for the active [execution plan](CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md).
Scientific requirements and phase acceptance gates remain in that plan and its linked contracts.

- 2026-10-12 — **CLI store review hardening (same chunk).** Hostile path hooks
  collapse closed at the store boundary; read-only handles carry a lifetime flag
  (`initialize` refuses coded pre-filesystem, writes refuse before any statement,
  flag survives close); `_open_read_only` normalizes unexpected failures, preserves
  cancellation, and always cleans up safely. WAL/aux-files wording corrected (no
  `immutable=1`; committed WAL reads; aux effects follow platform behavior). 5 new
  regressions (hostile path, ro-initialize, pre-BEGIN writes via trace callback,
  verify-failure cleanup, cancellation); 2 unneeded test ignores removed.

- 2026-10-12 — **CLI existing-store selection (experimental).** `--equipment-profile-store`
  opens an explicit existing database read-only (new `ProfileStore.open_read_only`: `mode=ro`
  URI plus `query_only`, no creation/migration/writes, existing verify before payloads) with
  repeatable `--equipment-profile-id` (current revisions regardless of enable flag; without
  IDs, all enabled currents); one frozen candidate composes files plus a single snapshot
  with all gates preserved and nothing bound on late failure. 15 tests (read-only contract,
  ID semantics incl. disabled/current-revision, order/hash/dose parity vs frozen Python
  snapshots, closed failures with zero exam reads and private stderr, caller/GUI guards).
  Schema §12 lock, packaged README store status. No migrations, GUI, settings-JSON,
  store commands, capture, run-state, or export scope.

- 2026-10-12 — **CLI profile-file parent review hardening.** Numeric sheet selectors
  beyond the 16-sheet ceiling fail before profile reads, including arbitrarily long
  numeric arguments; non-numeric names retain exact whitespace. The canonical reader
  checks its actual catalog count before traversing titles, and direct selection rejects
  bool/subclass coercion. Regression tests cover private early refusals and exact-title
  selection. No store selection/settings-JSON/GUI or transmission activation added.

- 2026-10-12 — **CLI coordinate profile file review fixes (same chunk).** Named
  sheet selection moved into the canonical XLSX/session seam (`FileSource.sheet`
  takes an exact title or 0-based index; resolution runs inside the guarded
  adapter against the opened catalog on the same bounded bytes — one file read,
  preflight before open, duplicates fail closed, names never retained); exact
  builtin list/tuple paths with declared/bounded ≤64 checks before any copy or
  I/O, strict `os.fspath` entries, single-try CLI error conversion; pre-bound
  sessions refused before mutations/I/O with caller-owned homes staged on an
  isolated copy; strict digit-only indexes with pre-IO negative refusal. 17 CLI
  tests plus 12 sheet tests (9 canonical seam, 3 CLI sheet selection); schema §6B updated.

- 2026-10-12 — **CLI coordinate profile file inputs (experimental).** Repeatable
  `--equipment-profile PATH` plus optional global `--equipment-profile-sheet` (name or
  0-based index; refused with no applicable XLSX file) in `cli_args`; new
  `cli_equipment_profiles` helper assembles one candidate via canonical `FileSource`
  (JSON/CSV/TSV/XLSX, CWD-relative, ≤64 requests before profile I/O) and binds it in
  `prepare_cli_settings` before any exam read — never replacing a bound session, never
  partially mutating on failure. `EquipmentProfileError` converts at the boundary to
  fixed value-free `UserFacingInputError` (code/source-kind/row/count only); refused in
  `--mode gui` before UI launch or profile reads. `prepare_cli_settings` moved verbatim
  to `cli_settings` (`main.py` 748 lines, re-export keeps the public surface). 17 CLI tests
  (DICOM full/partial and tabular CFA/ASD parity vs Python sessions, repeats with
  order-independent hashes, four-format parity, closed failures with zero exam reads
  and private stderr, strict shapes/bounds, staging, GUI refusal, preview smoke, CWD
  paths) plus 12 sheet tests (canonical seam + CLI sheet selection).
  Packaged README stale claims corrected. No wildcard promotion, transmission, store,
  settings-JSON, GUI, or rich-report scope.

- 2026-10-11 — **Captured multi-file parent review hardening.** File/context counts
  are checked before copying; per-exam baseline snapshots require bounded positional
  list/tuple containers, correct home types, and null capture entries. Baseline clones
  must isolate their own coordinate vectors and the caller's settings before any
  offset or production. Regression tests reject malformed containers, captured-entry
  baselines, and self-returning/shared-vector copy hooks. No run-state/CLI/GUI wiring.

- 2026-10-12 — **Captured multi-file review fixes (same chunk).** Capture mode
  takes explicit paths only — no glob resolution, existence probes, or reads before
  every authority validates (generators, bare strings, non-path entries, glob syntax,
  and >64 files fail closed with zero filesystem probes); retained normalized events
  accumulate across loaded frames including nulls against the aggregate cap before the
  next load; the caller shield enforces the full established isolation boundary
  (shared-child deepcopies fail closed); null files load on private per-file copies
  with per-exam baseline snapshots installed at preparation, matching individual
  baseline runs across vendors and orders (legacy no-context path unchanged);
  non-null captured entries never contact bundled/store/resolver while nulls
  intentionally run standard baseline selection; JSON refuses for every entry;
  the options-conflict check is a public shared seam. 22 tests.

- 2026-10-12 — **Captured multi-file input through the public API.**
  `analyze_multiple_input_files` takes keyword-only `equipment_capture_contexts=` (one
  validated capture or `None` per resolved file position, exact builtin list/tuple, ≤64
  files, ≤10_000 aggregate events); a new `equipment_captured_multi` helper owns the
  captured-only orchestration (shield → parse → resolve → prevalidate all authorities
  and session/plot conflicts → options policy → private per-file loads → existing
  `analyze_multiple_exams` capture path), leaving the legacy path untouched. Set import
  options on non-tabular paths fail closed pre-I/O; multi-study splits refuse closed
  including null entries so one file stays one exam; a bad later source/context leaves
  no partial output and no calculation runs. Single-file raw loading refactored into
  the shared no-calculation `load_captured_exam` seam with identical errors (20
  single-file tests intact). 17 tests (mixed Siemens-CFA/Philips-ASD parity, ordering,
  nulls, offsets, mixed formats, options, offline, late-failure atomicity, shape/caps,
  conflicts, purity). Contract §7 API row and §10 item 6 updated (capture stack
  delivered; run-state round-trip still open). No run-state version/wiring, GUI/CLI,
  rich reports, transmission, or filter expansion.

- 2026-10-11 — **Single-file captured input through the public API.**
  `analyze_input_file` and `main` take keyword-only `equipment_capture_context=` for one raw
  file (`main`: DICOM only; `analyze_input_file`: DICOM or raw vendor tabular); a new `equipment_captured_input` helper module owns the
  captured-only orchestration (validate → reject plot setup → route → analyze with the same
  capture), leaving legacy paths untouched. JSON, normalized, multi-study, and plot-setup
  inputs fail closed; tabular schema/sheet/options are carried. 14 tests (DICOM/tabular
  parity, `main`, import options, offline, purity, conflicts, refusals). No aggregation,
  multi-file, CLI flags, run-state, GUI, rich reports, version bumps, settings-bound fields,
  or transmission.

- 2026-10-11 — **Single-file captured input review fixes (same chunk).** Set import
  options on a non-tabular path fail closed pre-I/O in capture mode; `main` refuses tabular
  pre-I/O through `analyze_captured_main_input` (DICOM-only historical wrapper, fixed
  schema/options) while `analyze_input_file` stays the raw-table API; caller-owned settings
  are deep-copied via `shielded_settings_for_capture` so output-format assignment cannot leak
  on success or failure; source dispatch/read failures neutralize to a closed `CaptureError`
  from `None`; README/module dose-reproducibility claims corrected by parent review. 20 tests (new main
  tabular refusal with zero source reads, non-tabular options refusal, caller output-format
  preservation, self-returning copy rejection, private missing/malformed DICOM errors) plus a pre-existing possibly-unbound loop binding fix; `main.py` at 794
  lines with orchestration in the helper. Ruff, basedpyright, complexity, and size gates
  clean.

- 2026-10-11 — **Generic shutter columns for tabular ASD (no wiring).** `generic_rdsr_like`
  maps four optional canonical shutter edges (`Left/Right/Top/BottomShutter_mm`, self-match
  spellings only) with numeric coercion, enabling `field_size_mode: "ASD"` on raw tabular
  input; absent or non-numeric edges fail closed under ASD via existing required-concept
  enforcement, CFA paths are unchanged. Proven by Philips-DICOM-derived fixtures with
  numeric geometry parity to the DICOM run (dual-material filtration stays DICOM-only, so dose
  parity is asserted within the tabular chain). 8 tests. No Radimetrics/DoseTrack guessing,
  no metadata expansion, no raw columns in normalized output; calibration, profile hashes,
  and auto-election unchanged.
- 2026-10-11 — **Tabular replay review fixes (same chunk).** Live import-options receipts
  are rebound to the final post-options frame in production (single preparation shared by
  dispatch and confirmation); the normalizer hook keeps receipt rejection with the pipeline
  passing `None` in capture mode; capture-mode enforcement and upstream failures surface as
  closed codes; explicit `normalized` refuses before source I/O with instance-checked
  settings and closed suffix/schema errors; ASD tabular coverage uses a real Philips
  DICOM-produced capture failing closed on shutterless data (current shutterless fixtures lack ASD inputs; numeric shutter coercion
  is not supported by these adapters — no schema expansion). 18 tests.
- 2026-10-11 — **Raw tabular replay from captures (no wiring).** `read_and_normalize_input()`
  takes keyword-only `equipment_capture_context=` for raw vendor schemas
  (`generic_rdsr_like`, `radimetrics`, `dosetrack`): full pre-load validation with bound
  sessions rejected and settings required; explicit/auto `normalized` refusal; recipe applied
  on a private clone through the shared pipeline into the checked normalizer hook (bundled
  selection, session resolution, and receipt publication bypassed); final confirmation on the
  returned frame after import options with no live receipt attached. Proven on synthetic
  CSV/TSV/in-memory-XLSX canonical frames with per-schema PSD/dose-map/match parity, offline
  with bundled selection and resolution forcibly broken, plus options, drop-count, tamper,
  bounds, and caller-purity regressions. 14 tests. Main, run-state, GUI/CLI, rich reports,
  version bumps, settings-bound fields, and transmission remain open.
- 2026-10-11 — **Tabular replay review fixes (same chunk).** Live import-options receipts are
  rebound to the final post-options frame in production (one preparation shared by dispatch
  and confirmation, so no muted clone can slip between); the normalizer hook keeps receipt
  rejection with the pipeline passing `None` in capture mode; capture-mode enforcement and
  upstream failures surface as closed codes; explicit `normalized` refuses before source I/O
  with instance-checked settings and closed suffix/schema errors; ASD tabular coverage uses a
  real Philips DICOM-produced capture failing closed on shutterless data (current shutterless fixtures lack ASD inputs; these adapters
  do not support numeric shutter coercion — no schema expansion). 18 tests.

- 2026-10-11 — **DICOM replay review fixes (same chunk).** Loader validates the full context
  before any read (forged counts fail with zero source reads); the normalizer hook enforces
  the validated context plus the applied recipe/label precondition via reusable
  `check_captured_candidate` before any geometry runs, so unapplied homes fail closed with no
  publication; the original field/unit/angle docstring stands restored with a concise capture
  note appended. 20 tests.
- 2026-10-11 — **DICOM loader replay from captures (no wiring).** `read_and_normalise_rdsr_data()`
  takes keyword-only `equipment_capture_context=` for raw DICOM only: conflicts (live session,
  receipt list, bad types) and preparsed-JSON refusal all fail closed before any I/O; the
  captured recipe lands on a verified private settings clone before concept validation while
  live bundled selection, session resolution, and receipt publication are bypassed in a narrow
  normalizer hook; final confirmation runs only after the existing zero-kVp removal policy.
  Proven on real Siemens-CFA/Philips-ASD loaders with byte/numeric geometry and PSD/dose-map
  parity, offline with bundled selection and resolution forcibly broken, plus filter ordering,
  mode enforcement, tamper, bounds, and caller-preservation regressions. 17 tests. Existing
  `prepare_replay_settings` lives in `equipment_confirmation.py`; no new module was needed.
  Main/registry/tabular, run-state, GUI/CLI, rich exports, version bumps, settings-bound
  fields, and scientific policies remain open.

- 2026-10-11 — **Direct-capture review fixes, multi-exam (same chunk).** Capture preflight now
  prebuilds every exam's final work settings (offsets/downgrade included) with isolation
  verified across root, normalization vectors, phantom, dimension, and patient offset before
  any setter or calculation — covering null entries and the audited plot-mode dimension
  writes; shared-offset/self-returning/stateful clone hooks fail closed with zero production
  and unchanged callers. Event totals revalidate through the public constructor validator;
  shared limit constants replace magic bounds; annotation honestly accepts exact list/tuple.
  24 tests. Orchestration split keeps `analyze_data.py` (659) and `equipment_confirmation.py`
  (~770) under the file cap.
- 2026-10-11 — **Direct capture analysis, multi-exam (no wiring).** `analyze_multiple_exams()`
  takes keyword-only `equipment_capture_contexts=` (exact list/tuple aligned with exams, ≤64
  entries, ≤10k aggregate events): live sessions/receipts reject up front, every capture
  prepares/confirms against its own frame with isolated settings before any production, per-exam
  offsets and warning downgrades layer onto each prepared candidate without borrowing fields,
  and each `ExamResult` carries its stored match. 14 tests (Siemens CFA + Philips ASD parity,
  reversed order, offsets, partial/default/missing-identity, null mix, offline, bad-late-exam
  spy, bounds, caller preservation). Run-state, GUI/CLI, rich export, version bumps, and
  settings-bound capture fields remain open.
- 2026-10-11 — **Direct capture analysis, single-exam (no wiring).** `analyze_data()` takes a
  keyword-only `equipment_capture_context=` (`CapturedCoordinates | None`): with a capture it
  rejects any live session/receipt, privately clones caller settings, prepares the captured
  candidate into the clone, and confirms frame and candidate before any calculation, plot, or
  cache mutation, reporting the stored validated match mapping. Proven PSD/dose-map parity with
  the live raw run (full/partial/default, zero/False), offline after source removal and bundle
  changes, and closed rejections before calculation. 17 tests. Multi-exam, run-state, GUI/CLI,
  rich export, version bumps, and settings-bound capture fields remain open.
- 2026-10-11 — **Direct-capture review fixes (same chunk).** Working-copy isolation verified
  (root plus normalization vectors, phantom, and dimension — the plot-mode dimension writes
  found by audit are covered) before the candidate lands: self-returning/raising deepcopies
  and shared-child hooks fail closed with no calculation and caller state byte-equivalent;
  ordinary subclasses keep working. ASD parity proven on the real Philips loader; identity
  rejection strengthened to row-2 variation; all throwing invocations hoisted out of
  `pytest.raises` blocks. 23 tests.
- 2026-10-11 — **Captured-application preparation/confirmation (app prep, no wiring).**
  New `src/guiskindose/equipment_confirmation.py` (381 lines): pure
  `prepare_captured_candidate` (validates context, deep-copies the settings home, applies the
  full 15 stored leaves via public setters plus captured labels/method/summary) and
  `confirm_captured_application` (frame identity/count/geometry-v1, all 15 live fields plus
  labels, then frozen receipt + context-identical match mapping; closed codes throughout).
  Touched `equipment_capture.py` only to publish the bounded `frame_geometry_rows` helper.
  30 tests on real DICOM/CSV captures (full/partial/default/wildcard/missing-maker, offline
  reuse, stale frames, per-leaf mismatches, immutability, zero/False). No session binding,
  replay, analyze/run-state/GUI/CLI/export wiring, or version bumps; restore stays open.
- 2026-10-11 — **Confirmation review fixes (same chunk).** All-rows identity via shared
  `canonical_identity_pairs` (row-2 variation and known/unknown mixes reject; spelling variants
  pass; count enforced before traversal); exact live types (bool swap, ±1 int multipliers,
  finite non-bool numerics, exact strings — no truthiness/coercion); receipt exact-str method
  and pre-normalization key length bounds; clone shared-handle verification with closed
  deepcopy failures and documented factory-vs-authenticity semantics. 48 tests.
- 2026-10-11 — **Capture codec parent review.** Corrected input-vs-selected identity checks so
  bundled wildcard and Default fallback captures round-trip. Bounded actual row width and frame
  columns, guard JSON bytes/depth/tokens before tree allocation, canonicalize public leaf values,
  and validate inherited/root/source-manifest coherence. Added independent regressions; codec
  remains standalone with restore, run-state/export versions, and GUI/CLI wiring still open.

- 2026-10-11 — **Capture codec foundation, review-hardened (standalone, no wiring).**
  Producer moved to the application layer (`src/guiskindose/equipment_capture.py`) and validates
  the current receipt/frame/settings through the public bridge before any digest — stale geometry,
  identity, counts, sessions, live fields, and forged notices all reject; the core codec no longer
  imports bridge/frame/settings code. Immutable construction fully validates (strict tuples, nested
  types, recipe/provenance/bounds, checksum recomputation) with value-only-safe reprs; geometry,
  frame, and envelope paths enforce declared-then-actual length caps; JSON/numeric boundaries cover
  overflow, surrogates, depth, and node budgets; session provenance enforces kind/format/hash/
  revision coherence with aggregate totals; notices cross-check entries against inherited leaves.
  Producer regressions run on real DICOM/CSV normalizer receipts. 36 tests across one test
  file. Modules: `equipment_profiles/capture.py` (types + construction validation),
  `capture_checks.py` (scalars, JSON/budget boundary), `capture_codec.py` (parsing),
  `src/guiskindose/equipment_capture.py` (producer, emission, geometry). No run-state/GUI/
  export/CLI wiring, no version bumps; restore/calculation remain open (§10 stands).
- 2026-10-11 — **Run-state/export contract locked (docs only).** [EQUIPMENT_PROFILE_RUNSTATE_EXPORT_CONTRACT.md](../EQUIPMENT_PROFILE_RUNSTATE_EXPORT_CONTRACT.md)
  locks decisions 13/18/20 from actual seams: run-state 1→2 (positional per-exam captures with a full effective recipe,
  validated audit mapping, retained count and versioned geometry checksum), rich-report 3→4, dict/JSON export stays 3 while additive; default-safe maker/model keys vs
  absent-by-construction station/serial and never-captured notes/paths; v1 readers retained, atomic trial validation and before-load/confirmed-frame
  restoration; coordinates-only captures; self-contained reproducibility. No run-state/export implementation is complete
  (§10 open list stands). Phase 2 remains open.

- 2026-10-11 — **Parent API application hardening.** Receipts publish only after geometry
  normalization succeeds, then rebind after final zero-kVp filtering. Analysis verifies normalized
  numeric geometry and equality with a fresh resolution, including notices and source/revision
  metadata, before calculation/output. Per-exam output uses the original validated input frame,
  keeping dose-loop exclusions separate from application coverage. Added four regressions and
  updated the no-session formatter test seam. Phase 2 remains open.

- 2026-10-11 — **API slice review fixes (import-before-load only).** Effective custom field-size mode
  now resolves before required-concept validation (ASD↔CFA both directions covered); published
  records carry final retained counts with empty frames failing closed; `EquipmentApplicationReceipt`
  binds record/session/identity/count/effective-settings with full boundary validation (wrong
  session, changed frame/identity/count, forged records, stale settings all fail closed); per-exam
  restore from validated receipts with cached-summary refresh; latent `sign * [0] * len` crash on
  negative table/detector angles fixed (values identically zero). Phase 2 remains open.
- 2026-10-11 — **First API coordinate slice landed (import-before-load only).**
  `equipment_resolution.py` bridges bound sessions into raw normalization (resolve after filtering,
  apply all 15 leaves before geometry, records on results — never on `NormalizationSettings`);
  `PyskindoseSettings` accepts a typed, never-serialized session; dict/JSON results carry
  `equipment_profile_match`; pre-transformed inputs refuse closed. 24 targeted tests (DICOM/tabular
  application, all-15, filtering, fallback, parity, notices, reuse, refusals, goldens, privacy).
  Phase 2 remains open (CLI/settings-source syntax, run-state reader + schema locks, GUI notices,
  rich reports).
- 2026-10-11 — **Multi-source session assembly landed (core preparation, no wiring).**
  `equipment_profiles/session.py` freezes file/memory/store sources into one conflict-checked,
  capability-gated session with a compiled index prepared once; per-exam `resolve()` reuses the
  prepared custom side with bundled compiled or prepared, no recompiling or re-reading. Request
  collections bounded before copying with incremental ceilings and short-circuit; closed path
  boundary; revalidated snapshots with compiler-output payloads; canonical payload/provenance order;
  validated `__post_init__` contexts with the gate at preparation. 54 targeted tests (hashes,
  determinism, store stability, conflicts, bounds, gate rollback, paths, sheets, tampering, forged
  contexts, path attacks, order equality, privacy) plus 9 seam tests. Schema §15 locks the session
  contract. No renderer/normalizer/settings/API/CLI/GUI/store activation — Phase 2 remains open.
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
