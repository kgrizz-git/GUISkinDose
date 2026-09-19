# Phase A Execution Plan — Correction-Data Manifest, Validation, device_info Substitution

Status: Complete — implemented, merged as PR #101 (2026-09-18), canary/CI green. Archived.
Created: 2026-09-18
Parent (master) plan: [CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md](../CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md)
 (§1 manifest + §2 validation only)
Branch: `fix/correction-data-phase-a`

## Objective

Ship the data-and-docs foundation of the correction-data overhaul with **zero
behavior change**: a machine-readable manifest beside the CSVs, dataset +
explicit-DB validators (unit-tested, not yet wired into runtime — wiring is
Phase B), the locked `device_info.csv` identifier substitution, and the
fixture-comment correction. All dose outputs must remain identical (existing
golden tests are the proof; no new goldens needed).

## Locked Decisions (2026-09-18; also recorded in the master plan §1)

1. **`device_info.csv` substitution spec** — deterministic positional rule in
   file order (header excluded): row N gets `SYN-SN-0N` for the serial and the
   lab token by first-appearance order (`U105`→`SYN-LAB-A`, `U106`→`SYN-LAB-B`,
   `U601`→`SYN-LAB-C`, `U104`→`SYN-LAB-D`). `PadThickness_mm` (74/74/101/68),
   `DateMeasured`, `PadMaterial` preserved; comment semantics preserved with the
   lab reference retokenized ("estimated from lab 105" → "estimated from
   SYN-LAB-A", resolving to the same token as that lab's own row — asserted by
   test). Schema, row order, column set unchanged. This removes the identifiers
   from the CSV only; they persist in the approved fixture DICOMs, the two
   asserting test files, and pre-existing git history (stated plainly — the
   substitution stops forward propagation, nothing more).
   **No original→synthetic mapping is retained anywhere** (it would defeat the
   substitution; originals persist only in pre-existing git history here and
   upstream). Substitution rationale lives in the manifest, never in the CSV
   (a `#` comment line would break the header parse — `db_connect` passes no
   `comment=` arg).
2. **Fixture DICOMs + asserting text stay.** The five `example_data/RDSR/`
   binaries are hash-pinned approved assets (KG 2026-07-16, "deliberately
   retained"); the text expectations in `test_rdsr_parser_station.py` /
   `test_dose_kerma_correction.py` assert values parsed from those binaries and
   cannot change independently. Rewriting binaries would invalidate clearance
   and risk golden tests for no propagation gain. A full binary scrub is a
   separately-tracked decision, explicitly out of Phase A.
3. **Comment correction** — `test_rdsr_parser_station.py:25` "Synthetic labels
   only" is misleading; reword to state the values are retained from upstream
   (no claim about synthetic or real; point at the asset-inventory approval).

## Scope

**In scope (master §1 + §2, implementation-shaped):**
- Manifest JSON beside the CSVs: per-table schema, units, physical ranges,
  runtime consumer, lookup behavior, source type, generation method, upstream
  history (2018 initial commit + HVL regeneration), literature identifiers,
  provenance confidence with explicit `unknown`s, runtime-vs-build-input and
  read-vs-unread column separation (vendor HVL CSVs, `backscatter`/`h`
  columns), SHA-256 content hashes with a drift check.
- Dataset validators: required columns/types/units, finite values, physical
  ranges, duplicate lookup keys, status values, expected grids; dose-changing
  errors vs advisory provenance gaps; support-transmission range check both
  sides (reject non-finite/negative; reject-or-flag > 1.0), zero/near-zero
  policy consistent with the archived safety plan (no new replacement values).
- Explicit-DB validators (Phase B wiring): readable-SQLite, schema-version
  policy, required tables/columns, per-column type/finite/range/duplicate
  checks; actionable privacy-safe errors naming table/column; never bootstrap
  a replacement. Schema-drift test matrix (valid / bad version / missing
  table-column / out-of-range-or-duplicate).
- `device_info.csv` substitution per spec + manifest entry.
- Fixture-comment correction per decision 3.

**Out of scope:** §3 provider/adapter/settings/export changes, §4 guides,
§5 wheel proof, fixture-binary scrub, custom equipment profiles, support
geometry redesign.

## Global Constraints

- Zero behavior change: no edits to runtime call sites (`corrections.py`,
  `geom_calc.py`, `db_connect.py` logic), no settings/export changes. Validators
  are test- and maintainer-invoked only in Phase A.
- New validation module imports stdlib + pandas (+ `guiskindose.privacy` for
  error paths) only, so `test_architecture_layers.py` stays green. Note the
  layering test scans only `settings/`, `gui/`, `input_adapters/` and
  `calculate_dose/` — it does not enforce the "nothing in `settings/` may
  import it" half of this constraint; that half is self-discipline, and Phase A
  needs no settings imports anyway (no runtime wiring).
- No PHI/PII, paths, or identifiers in logs, errors, or tests (value-free
  `safe_error_event` paths; synthetic tokens only in new fixtures).
- Files under ~800 lines; tests colocated per repo convention.
- Privacy receipts via the normal pre-commit path (`run --mode staged` after
  final `git add`; `run --mode range` before push — staged receipts do not
  satisfy push-time range checks).

## File Map

| File | Role in this plan |
|------|-------------------|
| `src/guiskindose/table_data/correction_data_manifest.json` (new) | §1 manifest |
| `MANIFEST.in` | Add `include src/guiskindose/table_data/*.json` so the manifest ships in the wheel (master §5 asserts manifest presence; without this it silently would not) |
| `src/guiskindose/correction_validation.py` (new, proposed name) | §2 validators |
| `src/guiskindose/table_data/device_info.csv` | Identifier substitution |
| `tests/unittests/test_correction_data_manifest.py` (new) | Manifest↔CSV consistency, hash drift |
| `tests/unittests/test_correction_validation.py` (new) | Dataset + explicit-DB drift matrix |
| `tests/unittests/test_rdsr_parser_station.py:25` | Comment correction |
| `CHANGELOG.md` | Brief entry (src/ data change ships; gate requires it) |
| `dev-docs/MAINTENANCE_LOG.md` | Detail entry |
| `dev-docs/index.md` | Catalog this plan (same PR) |

## Tasks

- [x] **Step 1: Manifest** — inventory all CSVs under `table_data/` (+2 vendor
  HVL build inputs, dev scripts flagged non-runtime); write the JSON manifest
  per scope; add hash + drift check; manifest test (every CSV covered, every
  hash matches, `unknown`s explicit, runtime/read flags match the master
  plan's verified state).
- [x] **Step 2: Dataset validators** — implement §2 dataset checks; unit tests
  over synthetic frames (valid, missing column, wrong type, non-finite,
  out-of-range, duplicates, >1.0 transmission); error-vs-advisory separation
  asserted. Classification rule: `k_patient_support == 0` is a
  known-invalid inherited class (advisory, consistent with the archived safety
  plan's warned-neutral `1.0` — the shipped CSV holds exactly 304 such rows,
  all AlluraClarity Plane B), NOT a hard dataset error; >1.0 and
  non-finite/negative are hard errors.
- [x] **Step 3: Explicit-DB validators + drift matrix** — implement §2 adapter
  checks against synthetic SQLite DBs in `tmp_path` (valid, bad version,
  missing table/column, out-of-range/duplicate); fail-closed errors name
  table/column and never create files. Note the real bootstrap DB
  (`db_connect.py:41-80`) carries no schema-version table, so the "bad
  version" matrix case uses synthetic DBs with a declared `schema_version`
  table and the validator takes the expected version as a parameter (Phase B
  sets the policy when wiring the adapter). No runtime wiring (Phase B).
- [x] **Step 4: device_info substitution + comment fix** — apply the locked
  spec; update manifest entry; reword the parser-test comment. Verify: full
  `pytest -q` green. The guarantee is "no consumer reads the swapped columns"
  (only `db_connect.py:67,77` loads the file; no test asserts its contents) —
  golden tests pass as a regression net, not as proof of the swap (the CSV is
  only read when a fresh DB is built, `db_connect.py:49`). Substitution test
  asserts: row order, preserved dates/comments modulo retokenization, no real
  identifiers remain, and the row-3 comment token matches that lab's row token.
- [x] **Step 5: Docs + verification ladder** — CHANGELOG brief entry +
  MAINTENANCE_LOG detail; `index.md` row (already added with this plan —
  update only if paths change). Ladder: file tests → full `pytest -q` →
  `ruff` → `basedpyright` → `check_doc_freshness` → `check_gui_test_placement`
  → `check_changelog` → `check_file_sizes` → `audit_dependencies` (lock
  untouched; expect green). Privacy: the `.csv` edit triggers the phi-scan
  route (`privacy_admission_policy.json`); verify the `.phi-scanbaseline`
  `device_info.csv` entry freshness post-substitution (refresh/remove per the
  scanner's stale-entry behavior, confirmed empirically — do not assume).
- [ ] **Step 6: Push, PR, reviews** — push branch, open PR, request DeepSeek +
  kilo reviews of the implementation. Merge only on approval + green CI.

## Acceptance Criteria

- Manifest covers every CSV; drift check fails on tampered content.
- Validators reject every drift-matrix case with table/column-naming errors.
- `device_info.csv` carries no real identifiers; row order, dates, and comment
  semantics preserved; the retokenized comment resolves to the correct lab
  token (all asserted by test, not by inspection).
- All pre-existing golden/dose tests pass unmodified (zero behavior change).
- Diff: manifest + `MANIFEST.in` line + validation module + tests + CSV swap +
  comment + changelog/maintenance-log/index docs. No runtime, settings,
  export, or lock changes.
