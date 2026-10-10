# Custom Equipment Profiles — Execution Plan

Status: **Active — not started.** Derived from the reviewed design spec
[CUSTOM_EQUIPMENT_PROFILES_SPEC.md](CUSTOM_EQUIPMENT_PROFILES_SPEC.md)
Created: 2026-10-09 · design reviewed by kiro/gpt-5.6-sol 2026-10-09
Parent roadmap: [CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md](CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md)
Feature branch: `feat/custom-equipment-profiles` (to be created off `main` after Phase 0 lands on a
docs branch, or as this branch's continuation with maintainer approval).

## Objective

Implement user-supplied, validated equipment/model profiles that change two things and nothing else:
coordinate normalization (vendor table-origin and axis conventions) and patient-support transmission
(`k_tab`) rows. Kerma-meter correction factors, backscatter/medium data, and the HVL grid stay out of
scope; explicit custom SQLite is not deprecated.

## v1 scope cuts

- No `anode_angle_deg` profile field (waits for the angle-aware HVL lookup backlog item).
- No individual-equipment transmission key (privacy + precedence complexity, deferred to a later
  schema version).
- No CSV sidecar; one self-contained JSON document per file.
- Coordinate profile selection stays once per homogeneous exam/frame; no per-event transform redesign.
- No deprecation of `corrections_db_path`.

## Acceptance criteria

1. Users can add a model without editing package files or SQLite.
2. The active coordinate origin and transmission source are visible before dose calculation, per exam.
3. Invalid or ambiguous profiles cannot silently alter dose.
4. API, CLI, GUI, and exports agree on match and precedence.
5. A run without custom profiles remains numerically unchanged (golden parity).

## Phase 0 — Scope and schema lock

**Goal.** Resolve every semantic decision before code exists, so later phases never renegotiate the
format.

Work:
- [ ] Confirm or amend the 14 open questions recorded in the spec §10 (recommended answers are
      pre-filled; record the final answers in the decision log below).
- [ ] Lock the JSON schema: `schema_version`, `profiles[]`, `profile_id`, alias list, coordinate
      block, inline transmission rows, provenance block, unknown-field policy (reject in v1).
- [ ] Write the byte/row/text bounds and the exact error-code vocabulary.
- [ ] Write the two precedence tables (coordinates; transmission) including `k_tab_mode=estimate`,
      explicit SQLite, measured vs estimated rows, and session overrides.
- [ ] Write the field-level privacy/export matrix (safe audit metadata / sensitive identifier /
      never exported).
- [ ] Author one complete valid example profile and at least four invalid examples.
- [ ] Confirm the homogeneous-exam policy: split or reject inputs with conflicting equipment identity
      before normalization.

Exit criteria: decision log complete; example profiles load against a schema sketch by hand; no open
question blocks Phase 1. Dependencies: none (documentation phase; runs on a docs branch).

## Phase 1 — Core profile loader, identity contract, and match model

**Goal.** A strict, side-effect-free loader plus a compiled resolver. No calculation changes yet.

Work:
- [ ] New module (e.g. `equipment_profiles.py`): parse + validate the v1 JSON document; bounds;
      unknown-field rejection; canonical identifier normalization; duplicate/conflict detection
      across files; content hash; stable `profile_id` assignment.
- [ ] Add the canonical manufacturer field to the normalized contract (`input_adapters/normalized.py`
      schema) and every raw adapter, with a warned legacy compatibility path for normalized tables
      that predate it.
- [ ] Structured match record: `profile_id`, `source`, `level`, `matched_input_key`,
      `affected_event_count`; replace reliance on the `Matched` / `Fallback` string for profiles while
      leaving existing user-facing wording intact.
- [ ] Compile a transmission index by canonical manufacturer/model/plane (no per-event full scans).
- [ ] Privacy-safe errors: codes, row indices, field names, counts only.

Exit criteria: unit tests for schema versions, ranges, duplicates, aliases, wildcards, mixed
identities, unknown fields, content hashing, deterministic multi-file loading, and privacy-safe error
text. No numeric behavior change: full existing test suite green. **Do not split** validation,
conflict detection, and match provenance — they are one contract.

## Phase 2 — Coordinate-profile thin vertical slice

**Goal.** One exact custom manufacturer/model coordinate profile working end to end. This is the
first independently shippable slice.

Work:
- [ ] Wire the loader into `NormalizationSettings`/settings JSON (`equipment_profiles`) and a
      repeatable CLI flag (e.g. `--equipment-profile PATH`), preserving the coordinate precedence
      table.
- [ ] GUI: import **before data load** only; validation preview; matched-profile and match-level
      display; profile provenance (ID, schema version, content hash, active values) in run
      configuration and exports.
- [ ] Keep session transforms applied after the profile baseline, exactly once; no post-load
      activation in this phase.

Exit criteria: the same synthetic fixture produces identical normalized values and match records via
API, CLI, and GUI; no-profile golden parity; per-exam baseline vs override values visible; rich
export and run configuration carry privacy-safe profile provenance; CLI/GUI/export parity tests
green.

## Phase 3 — Profile lifecycle and compatibility

**Goal.** Aliases, deliberate wildcards, multiple files, enable/disable/remove, migration of the
hidden run-configuration route, and — carefully — post-load activation.

Work:
- [ ] Alias matching; custom wildcard with explicit override declaration + pre-calc acknowledgement
      before it may replace a bundled exact.
- [ ] Multiple disjoint files with deterministic load order; conflicts fail before any mutation.
- [ ] Migrate `gui/run_state.py` / `gui/settings_builder.py` normalization-profile handling onto the
      first-class loader.
- [ ] Post-load activation: atomically re-normalize affected exams, rebuild the pristine baseline,
      recompute detected origins, reapply session overrides, clear results/preview caches, refresh
      all tabs — or roll back.
- [ ] Compatibility adapter for callers passing custom `NormalizationSettings` directly.

Exit criteria: conflicts fail before mutation; post-load change either fully re-normalizes or rolls
back; session transforms reapplied exactly once; stale results/caches cleared; mixed
matched/fallback exams correctly attributed per exam. **Do not split** post-load activation,
re-normalization, rollback, and result invalidation.

## Phase 4 — Custom patient-support transmission

**Goal.** Overlay validated profile transmission rows on the selected baseline provider, preserving
every existing behavior.

Work:
- [ ] Row resolution order: custom measured rows → baseline provider (bundled table or explicit
      SQLite) → existing interpolation/clamping/fallback chain; custom estimated rows fill gaps only.
      Reject the profile + explicit-SQLite same-key combination (or the Phase 0 answer).
- [ ] Keep all three `k_tab_mode` states, plane identity (A/B/single), and the
      `check_table_hits()` application semantics exactly as they are.
- [ ] Structured per-exam transmission status and provenance in the Calculate tab, Results, and every
      export (rich export already stores per-exam `k_tab_statuses`; extend with profile provenance and
      a non-empty CLI `transform_meta`).
- [ ] Pre-calculation report of every active dose-affecting custom value; loaded-but-unused profiles
      listed without a dose warning.

Exit criteria: tests cover exact / interpolated / clamped / custom-measured / custom-estimated /
baseline / fallback / neutral outcomes, A/B/single, explicit SQLite coexistence, mixed exams, and
no-profile golden parity. **Do not split** row resolution, dose application, status propagation,
warnings, and export provenance — a hidden custom dose change without its audit trail is
unacceptable.

## Phase 5 — Full GUI authoring and persistence workflow

**Goal.** A discoverable Equipment Profiles card that a physicist can actually use.

Work:
- [ ] Import with validation preview; activation, removal, conflict UI; per-exam use matrix
      (custom/bundled/default coordinate match and custom/baseline/fallback transmission counts).
- [ ] Profile export/reload; constrained "save session correction as profile" limited to
      equipment-design decisions, with required identity/provenance fields.
- [ ] Browser and native download/import parity.

Exit criteria: GUI tests cover new model, wildcard, alias, conflict, active/unused rows, mixed exams,
save/reload, post-load activation, and download behavior. Patient offsets cannot accidentally become
reusable equipment properties.

## Phase 6 — Legacy migration, documentation, and release proof

**Goal.** Ship it cleanly and prove it.

Work:
- [ ] Document SQLite coexistence; optional `k_tab`-only extraction utility that states plainly it
      cannot migrate custom HVL or medium data.
- [ ] Update user help (`docs/source/gui_help/`), `ui_copy.json`, `help_registry.json`,
      `feature_doc_matrix.json`, `INPUT_SCHEMA_DETECTION.md` / input docs where relevant,
      `FEATURE_INVENTORY.md`, `CHANGELOG.md`, maintenance log.
- [ ] Packaged-wheel clean-directory proof; privacy/log tests containing no labels or paths.
- [ ] Manual smokes: import → preview → activation → correction source → save → reload, in browser and
      native modes plus Windows file dialogs (append to `TO_DO.md` Manual Smokes).

Exit criteria: API/CLI/GUI/export parity suite passes; no-profile numerical goldens pass; wheel proof
passes; privacy gates pass; this plan records its validation evidence and is ready to archive under
`dev-docs/plans/archive/`.

## Progress log

- 2026-10-09 — plan written from the reviewed spec; no implementation started.

## Decision log

- 2026-10-09 — Design review (kiro/gpt-5.6-sol) recorded the blocking findings this plan is built on:
  coordinate matching is per-frame, `manufacturer` is absent from the normalized contract, a single
  precedence ladder is wrong, post-load activation can leave data stale, the file format was
  undecided, privacy/export needed a field-level contract, and SQLite must not be deprecated in this
  feature. All seven are addressed by the phase structure above.
- Phase 0 decisions: pending maintainer sign-off on the spec §10 answers (record each here as decided).

## Risks

- A custom profile silently changing dose: mitigated by the dose-affecting pre-calc report, the
  two independent precedence ladders, and export provenance.
- Stale loaded data after a profile change: mitigated by import-before-load in Phase 2 and the atomic
  activation/invalidation rule in Phase 3.
- Privacy leakage through free-text notes or paths: mitigated by the field-level export matrix,
  bounded/sanitized notes, and code-only error text.
- Performance of transmission lookup with large user tables: mitigated by the compiled index in
  Phase 1 and the row bound.

## Delivery

Minor SemVer impact. Feature branch off `main` once Phase 0 is signed off; phases 2 and 4 each land
as their own PR behind green CI (no direct-to-`main` work).
