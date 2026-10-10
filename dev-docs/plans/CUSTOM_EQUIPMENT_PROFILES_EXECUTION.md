# Custom Equipment Profiles — Execution Plan

Status: **Active — not started.** Derived from the design spec
[CUSTOM_EQUIPMENT_PROFILES_SPEC.md](CUSTOM_EQUIPMENT_PROFILES_SPEC.md) (reviewed twice by
kiro/gpt-5.6-sol, 2026-10-09).
Created: 2026-10-09 · spec review applied 2026-10-09 · plan review applied 2026-10-09
Parent roadmap: [CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md](CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md)
Delivery: feature branch off current `main` once Phase 0 is signed off; Phases 2, 4, and 5 each land as
their own PR with green CI. No direct-to-`main` work.

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
- Coordinate post-load import is out of the coordinate-only slice (Phase 2); the full feature adds it
  atomically in Phase 3.

## Acceptance criteria

1. Users can add a model without editing package files or SQLite.
2. The active coordinate origin and transmission source are visible before dose calculation, per exam.
3. Invalid or ambiguous profiles cannot silently alter dose — including a profile whose contents the
   running build cannot yet apply.
4. API, CLI, GUI, and exports agree on match and precedence.
5. A run without custom profiles remains numerically unchanged (golden parity).

## Phase 0 — Scope and schema lock

**Goal.** Resolve every semantic decision before code exists, so later phases never renegotiate the
format. Dependencies: none (documentation phase, runs on a docs branch).

Work:
- [ ] Sign off (or amend) each of the 20 decisions in spec §10 and copy the final wording into the
      decision log below. No "recommended" or "or the Phase 0 answer" language may remain.
- [ ] Lock the JSON schema: `schema_version`, bounded `profiles[]`, required unique stable
      `profile_id`, `manufacturer_aliases` / `model_aliases`, coordinate block, inline transmission
      rows, provenance block; unknown fields rejected; coordinate and transmission blocks
      independently optional with at least one required.
- [ ] Define `profile_id` ownership (required, user-supplied, unique, stable), per-profile content
      hash, and whole-document hash semantics.
- [ ] Rename "manufacturer wildcard" to **manufacturer-scoped model wildcard** everywhere; define
      alias structures and their collisions with the bundled hardcoded manufacturer aliases.
- [ ] Lock transmission grid composition: custom measured nodes overlay baseline nodes before one
      interpolation pass; custom nodes never extend the baseline range; custom estimated nodes fill
      only unmeasured coordinates; two orthogonal status dimensions (source + resolution).
- [ ] Define profile path resolution (settings-relative; CLI working-directory) and the CLI wildcard
      acknowledgement mechanism (opt-in flag, else hard error).
- [ ] Confirm the Phase 3 post-load strategy: coordinate-only slice is import-before-load; full v1
      supports atomic post-load re-normalization with rollback (revise spec decision 11 to match).
- [ ] Write the byte/row/text bounds and the exact error-code vocabulary (including
      `unsupported_profile_capability`).
- [ ] Author one complete valid example profile plus four invalid examples, and the signed schema
      field table.

Exit criteria: decision log complete; schema field table and example JSON checked syntactically
(executable loader tests begin in Phase 1); no open question blocks Phase 1.

## Phase 1 — Core profile loader, identity contract, and match model

**Goal.** A strict, side-effect-free loader plus a compiled resolver. No calculation changes yet.

Work:
- [ ] New module (e.g. `equipment_profiles.py`): validate the required stable `profile_id`; parse and
      validate the v1 JSON document; bounds; unknown-field rejection; canonical identifier
      normalization; duplicate/conflict detection across files; per-profile and document hashes.
- [ ] Read bounded bytes once, hash and parse those same bytes, and retain an immutable snapshot for
      the run.
- [ ] Add the canonical manufacturer field to the normalized contract
      (`input_adapters/normalized.py` schema) and every raw adapter; emit it for every raw-normalized
      frame; accept a missing manufacturer only through the warned legacy-normalized path.
- [ ] Structured, immutable per-exam match records (`profile_id`, `source`, `level`,
      `matched_input_key`, `affected_event_count`, `domain = coordinate | transmission`) — not mutable
      fields on `NormalizationSettings`.
- [ ] Compile a transmission index by canonical manufacturer/model/plane, with a performance
      assertion that event resolution never executes a full frame filter per event.
- [ ] Distinguish syntax validation of aliases/wildcards/transmission blocks from whether the running
      build supports applying them; capability errors are stable and testable.
- [ ] Privacy-safe errors: codes, row indices, field names, counts only.

Exit criteria: unit tests for schema versions, ranges, duplicates, aliases, wildcards, mixed
identities, unknown fields, content hashing, deterministic multi-file loading, and privacy-safe error
text; the existing suite is green with no numeric change. **Do not split** validation, conflict
detection, and match provenance — they are one contract.

Docs in this phase: normalized-contract description, architecture/data-flow references, schema
examples.

## Phase 2 — Coordinate-profile thin vertical slice

**Goal.** One exact custom manufacturer/model coordinate profile working end to end. This is the
first independently shippable slice.

Work:
- [ ] Wire the loader into settings JSON (`equipment_profiles`) and a repeatable CLI flag (e.g.
      `--equipment-profile PATH`), preserving the coordinate precedence table.
- [ ] Fail closed with `unsupported_profile_capability` when a loaded profile relies on aliases,
      manufacturer-scoped model wildcards, or non-empty transmission rows — those land in Phases 3
      and 4, so they must not load-and-ignore.
- [ ] CLI coordinate `transform_meta` is non-empty (ID, schema version, hashes, match level, active
      values) in this phase, not Phase 4.
- [ ] Migrate the hidden run-configuration route (`gui/run_state.py`, `gui/settings_builder.py`) onto
      the first-class loader in this phase; bump `RUN_STATE_SCHEMA_VERSION` with a compatibility
      reader for old normalization-profile documents; store a privacy-safe active-value snapshot plus
      expected profile hashes, never profile paths.
- [ ] Settings serialization for `equipment_profiles`: default settings exports and run configs
      contain no profile paths; CLI settings-path round-trip tests.
- [ ] GUI: import **before data load** only; validation preview; matched profile and structured match
      level per exam; profile provenance in run configuration and rich exports.
- [ ] Pin the synthetic fixture's exact expected `Tx/Ty/Tz`, angle, field-size, match-record, and
      export-provenance values, and assert them via API, CLI, and GUI.

Exit criteria: identical normalized values and match records through API, CLI, and GUI for the shared
fixture; no-profile golden parity; capability fail-closed tests; per-exam baseline and override values
asserted in a named UI surface and in export payloads; privacy-safe run-state round-trip tests.

Docs in this phase: settings/CLI/API references, run-configuration help, feature inventory,
`AGENTS.md`, `CHANGELOG.md`.

## Phase 3 — Profile lifecycle and compatibility

**Goal.** Aliases, deliberate wildcards, multiple files, enable/disable/remove, and atomic post-load
activation.

Work:
- [ ] Alias matching (`manufacturer_aliases`, `model_aliases`); manufacturer-scoped model wildcards
      with an explicit override declaration plus pre-calculation acknowledgement (GUI) or the CLI
      opt-in flag, before they may replace a bundled exact.
- [ ] Multiple disjoint files with deterministic load order affecting diagnostics/serialization only;
      conflicts fail before any mutation.
- [ ] Compatibility adapter for callers passing custom `NormalizationSettings` directly.
- [ ] Post-load activation: read profile bytes once, hash, parse, and re-normalize atomically —
      DICOM, single-tabular, and multi-file sessions each covered; rebuild the pristine baseline,
      recompute detected origins, reapply session overrides exactly once, clear results and preview
      caches (profile revision/hash in the Calculate preview cache key), and refresh all tabs — or
      roll back. An unavailable or unreadable source leaves profile state, normalized frames,
      overrides, and results unchanged.
- [ ] Busy-state guard blocks profile mutation while a calculation runs.
- [ ] Fault-injection tests for each rollback point (read, parse, normalize, override reapplication,
      tab refresh, rollback), asserting `base_data`, detected origin, overrides, result state,
      input/profile revision, and preview caches always end fully old or fully new — never mixed.

Exit criteria: conflicts fail before mutation; fault injection covers read/parse/normalize/override/
refresh/rollback for DICOM, single-tabular, and multi-file sessions; post-load change either fully
re-normalizes or rolls back; session transforms reapplied exactly once; mixed matched/fallback exams
correctly attributed per exam. **Do not split** post-load activation, re-normalization, rollback, and
result invalidation.

Docs in this phase: persistence schema/migration notes, post-load activation help.

## Phase 4 — Custom patient-support transmission

**Goal.** Overlay validated profile transmission rows on the selected baseline provider with a
documented grid-composition rule, preserving every existing behavior.

Work:
- [ ] Effective-grid construction per the Phase 0 decision: custom measured nodes overlay baseline
      nodes before one interpolation pass; custom nodes never extend the baseline range (out-of-range
      clamps at the nearest baseline node, labelled clamped); custom estimated nodes fill only
      unmeasured coordinates; single pass labelled `source: mixed` when both contribute.
- [ ] Row resolution order: custom measured → baseline provider (bundled table or explicit SQLite) →
      existing interpolation/clamping/fallback chain; `k_tab_mode: estimate` ignores profile rows;
      reject profile rows plus explicit SQLite claiming the same key (Phase 0 decision).
- [ ] Keep all three `k_tab_mode` states, plane identity (A/B/single), and the `check_table_hits()`
      application semantics exactly as they are.
- [ ] Report both status dimensions per exam (source; exact/interpolated/clamped) in the Calculate
      tab, Results, and every export; extend rich export's per-exam `k_tab_statuses` with profile
      provenance and structured match records; bump `RICH_EXPORT_SCHEMA_VERSION` with a compatibility
      test; add additive public dict/JSON fields with object- and serialized-form tests.
- [ ] Pre-calculation report of every active dose-affecting custom value; loaded-but-unused profiles
      listed without a dose warning.
- [ ] Numerical proof: a custom transmission row changes only cells where `table_hits` is true and
      no-profile PSD goldens are unchanged.

Exit criteria: tests cover exact / interpolated / clamped / custom-measured / custom-estimated /
baseline / mixed / fallback outcomes, sparse and partial grids, outside-range queries, mixed-source
interpolation, same-node collisions with bundled and explicit-SQLite nodes, A/B/single, explicit
SQLite coexistence, mixed exams, and no-profile golden parity. **Do not split** row resolution, dose
application, status propagation, warnings, and export provenance — a hidden custom dose change
without its audit trail is unacceptable.

Docs in this phase: `PSD_CALCULATION_ALGORITHM.md`, correction-data reference, calculation help,
output schema, `CHANGELOG.md`.

## Phase 5 — Full GUI authoring and persistence workflow

**Goal.** A discoverable Equipment Profiles card a physicist can actually use.

Work:
- [ ] Import with validation preview; activation, removal, conflict UI; per-exam use matrix
      (custom/bundled/default coordinate match and custom/baseline/fallback transmission counts).
- [ ] Profile export/reload with atomic native writes (`Path.replace()`) and the browser download
      fallback; export is a distinct explicit action.
- [ ] "Save session correction as profile" limited to the exact reusable field list — table origin,
      `Tx/Ty/Tz` directions, `Tx↔Tz` swap, angle signs — with patient offsets and session-only
      field-size settings explicitly excluded; required identity/provenance fields.

Exit criteria: automated NiceGUI GUI tests cover new model, wildcard, alias, conflict, active/unused
rows, mixed exams, save/reload, post-load activation, and download behavior; patient offsets cannot
become reusable equipment properties. Native (pywebview) and Windows file-dialog checks are manual
smokes (below), not this phase's gate.

Docs in this phase: Equipment Profiles GUI help plus `dev-docs/ui_copy.json`,
`dev-docs/help_registry.json`, `dev-docs/feature_doc_matrix.json`, and `dev-docs/glossary.json`
updates (run both sync scripts and the help/UI-copy/feature-matrix checks).

## Phase 6 — Legacy migration, documentation, and release proof

**Goal.** Ship cleanly and prove it.

Work:
- [ ] Document SQLite coexistence; the `k_tab`-only extraction utility is **deferred to
      `TO_DO.md`** unless the maintainer makes it required for this release (then it needs its own
      tests and docs).
- [ ] Final documentation reconciliation only — behavior docs already landed with their phases.
- [ ] Packaged-wheel clean-directory proof via `scripts/verify_distribution.py` (name the expected
      assertions in the PR); privacy/log tests containing no labels or paths.

Exit criteria: API/CLI/GUI/export parity suite passes; no-profile numerical goldens pass; wheel proof
passes; privacy gates pass; each phase's validation evidence recorded in the maintenance log when that
phase lands; this plan records its own evidence and is ready to archive under
`dev-docs/plans/archive/`.

## Manual smokes (tracked, not phase gates)

Browser-mode smokes are automated NiceGUI tests inside their phases. The user-only passes are added to
`TO_DO.md` → Manual Smokes when the code lands: native (pywebview) import/activation and the Windows
native file dialogs. Completed browser evidence is recorded in this plan and the maintenance log, not
in `TO_DO.md`.

## Validation required for every code phase

Each code phase (1–5) runs and records:

- targeted unit/integration tests plus the full `python -m pytest` suite;
- `python -m compileall src/guiskindose`;
- `python -m ruff check src tests`;
- `basedpyright`;
- `uv run --extra dev --extra gui --locked python scripts/check_complexity.py`;
- `python scripts/check_file_sizes.py`;
- `pytest tests/gui -n auto` for GUI-touching phases;
- privacy and doc-impact checks (`check_sensitive_content.py`, `privacy_admission.py`,
  `check_doc_freshness.py`, help/UI-copy/feature-matrix checks, agent guidance);
- `python -m build` plus `scripts/verify_distribution.py` where packaging changes.

## Progress log

- 2026-10-09 — plan written from the reviewed spec; Phase 0 checklist expanded after the plan review;
  no implementation started.

## Decision log

- 2026-10-09 — spec review (kiro/gpt-5.6-sol): per-frame coordinate matching, the
  manufacturer/`profile_id` contract, two precedence ladders, atomic activation/invalidation, a
  JSON-only format, the privacy/export matrix, and SQLite coexistence are now encoded in the spec.
- 2026-10-09 — plan review (kiro/gpt-5.6-sol), verdict "approve with edits", encoded here:
  (1) coordinate and transmission blocks are independently optional and the coordinate slice fails
  closed on unsupported capabilities; (2) Phase 3 owns atomic post-load activation, reconciled with
  spec decision 11; (3) transmission grid composition is a single interpolation pass with two status
  dimensions; (4) `profile_id`, alias structures, manufacturer-scoped model wildcard terminology,
  hashes, path resolution, and immutable per-exam match records are Phase 0 locks; (5) run-state and
  rich-export schema bumps belong to Phases 2 and 4; (6) every phase gets objective exit criteria and
  the shared validation block; (7) docs/changelog move to the phase that changes behavior; (8) race,
  source-snapshot, cache-key, and CLI-acknowledgement risks are covered; (9) this file is named as an
  execution plan (not `_PLAN.md`), gets its own catalog row, keeps only unperformed user-only smokes
  in `TO_DO.md`, and defers the SQLite extraction utility instead of marking it optional.
- Phase 0 decisions: pending maintainer sign-off (record each here as decided).

## Risks

- A custom profile silently changing dose: mitigated by the dose-affecting pre-calc report, the two
  independent precedence ladders, capability fail-closed errors, and export provenance.
- Stale loaded data after a profile change: mitigated by import-before-load in Phase 2 and the atomic
  activation/invalidation rule with fault injection in Phase 3.
- A source changing between validation and calculation: mitigated by read-once/hash/parse of the same
  bytes and the immutable run snapshot.
- Privacy leakage through free-text notes or paths: mitigated by the field-level export matrix,
  bounded/sanitized notes, code-only error text, and never-serialized profile paths.
- Performance of transmission lookup with large user tables: mitigated by the compiled index in
  Phase 1, the row bound, and the per-event performance assertion.
