# Phase B Execution Plan — Correction-Data Provider Swap

Status: Active — awaiting DeepSeek + Kilo plan review BEFORE implementation.
Reviewers are additionally asked for recommendations and analysis on the open
design questions (§Open Design Questions) — see the review request.
Created: 2026-09-18
Parent (master) plan: [CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md](CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md)
 (§3 only; §4 guides and §5 wheel proof stay out)
Depends on: Phase A (manifest + validators, merged as PR #101)
Branch: `fix/correction-data-phase-b`

## Objective

Eliminate the working-directory-created SQLite default while preserving
numerical behavior and legacy explicit-database compatibility: route the three
`db_connect` call sites through a packaged-CSV provider, make the legacy
SQLite path explicit/validated/read-only, remove the repo-root discovery, and
stop emitting raw filesystem paths in exports.

## Locked Decisions (2026-09-18)

1. **No hard errors for path shapes.** Relative paths (including a user's
   intentional CWD-relative custom DB) warn and are honored as explicit custom
   DBs (validated, read-only) — never a hard error. Rationale: erroring
   strands users with working setups and no recourse; a deprecation warning
   migrates them. (Author's earlier error proposal withdrawn on challenge.)
2. **Bare default collapses to packaged.** Unset/`None`/empty/`"corrections.db"`
   all resolve to the packaged provider. The string `"corrections.db"` can no
   longer mean "bootstrap here": an implicitly present root/CWD DB is ignored
   (with the §Step-5 warning when detected), never loaded, never treated as
   user data.
3. **Deprecate, don't remove.** The `corrections_db_path` interface stays;
   removal (if ever) is a separately announced breaking release per the master
   plan's SemVer note. This plan is patch-level behavior-preserving.

## Open Design Questions (for reviewers — recommendations wanted)

- **Q1 (path semantics):** warn-and-honor for every non-default relative path
  — stress-test this. Is there a relative-path case that must fail closed
  instead (e.g. path traversal outside CWD, `"~/…"` unexpanded, empty-string
  vs unset)? What exact warning text/channel?
- **Q2 (provider shape):** proposed `src/guiskindose/correction_data.py` with
  `get_table(name) -> pd.DataFrame` (module-level dict cache, shallow copy per
  call under a documented no-mutation contract + isolation test) and
  `packaged_source_hash()` (SHA-256 over concatenated packaged CSV bytes in
  manifest order). Better as a class? Different caching (lru_cache)?
- **Q3 (warning placement):** proposed warn-at-calculate (once per process via
  `warnings.warn` + value-free logger line — never the path itself). Better at
  settings construction, import, or GUI load? GUI toast as well as log?
- **Q4 (export descriptor):** proposed replacing the verbatim path value with
  `{"source": "packaged-csv" | "explicit-sqlite", "sha256": "<hex>"}` under the
  existing `corrections_db_path` key (`export/sections.py` `_SETTINGS_KEYS`
  snapshot is `getattr`-verbatim today). Does the value-type change force an
  `EXPORT_SCHEMA_VERSION` bump, or do export consumers tolerate it? Which bytes
  exactly feed the hash (concatenated CSVs vs manifest hashes)?

## Scope

**In scope (master §3):**
- Provider module (`importlib.resources`: `resources.files("guiskindose") /
  "table_data" / <file>` — no `__init__.py` or packaging-config changes needed;
  `table_data/` ships as package data already). Cache pandas tables.
- Route `fetch_and_append_hvl()` (`geom_calc.py:353`), `calculate_k_med()`
  (`corrections.py:142`), `calculate_k_tab()` (`corrections.py:374`) through
  the provider. Default runs create no files and ignore any root/CWD DB.
- Explicit absolute (or warned-relative, per decision 1) SQLite path →
  temporary read-only compatibility adapter gated by the Phase A
  `check_explicit_db` validators; validation failures raise actionable
  privacy-safe errors before calculation; never bootstrap a replacement.
- Deprecate the relative default in `PyskindoseSettings`
  (`pyskindose_settings.py:123`), `settings_example.json:59`, GUI settings
  construction; document explicit absolute opt-in.
- Remove the repo-root discovery in `gui/settings_builder.py:109-112`
  outright (leaving it would silently reclassify every editable-checkout GUI
  run as explicit opt-in).
- Export descriptor + hash per Q4 decision; update affected export tests.
- Ignored-DB warning diagnostic per Q3 decision.

**Out of scope:** §4 guides (Phase C), §5 wheel proof (Phase D), custom
equipment profiles, support geometry, fixture-DICOM scrub (tracked TO_DO
deferral), `db_connect.py` removal (kept for the explicit adapter path).

## Global Constraints

- Numerical identity: all pre-existing golden/dose tests pass UNMODIFIED —
  the proof of behavior preservation (plus a new sentinel-DB test proving the
  packaged path ignores a seeded root DB).
- Provider imports stdlib + pandas + `importlib.resources` +
  `guiskindose.correction_validation` only; `test_architecture_layers.py`
  stays green.
- No PHI/PII, source filenames, or absolute paths in logs, warnings, errors,
  or exports (value-free messages; `safe_error_event` / `safe_warning` paths).
- Files under ~800 lines; tests colocated per convention.
- Privacy receipts via the normal pre-commit path (`run --mode staged` after
  final `git add`; `run --mode range` before push).

## File Map

| File | Role in this plan |
|------|-------------------|
| `src/guiskindose/correction_data.py` (new, proposed name) | Provider + hash |
| `src/guiskindose/corrections.py` (`calculate_k_med`, `calculate_k_tab`) | Route through provider / explicit adapter |
| `src/guiskindose/geom_calc.py` (`fetch_and_append_hvl`) | Route through provider / explicit adapter |
| `src/guiskindose/db_connect.py` | Retained for the explicit path only; bootstrap-on-absent removed or gated |
| `src/guiskindose/settings/pyskindose_settings.py:123` | Default deprecation |
| `src/guiskindose/settings_example.json:59` | Template default |
| `src/guiskindose/gui/settings_builder.py:109-112` | Remove root discovery |
| `src/guiskindose/export/sections.py` (`_SETTINGS_KEYS`) | Descriptor + hash |
| `tests/unittests/test_correction_data_provider.py` (new) | Parity, sentinel, no-CWD-write, explicit, fail-closed, export descriptor |
| `CHANGELOG.md` | Migration note (default now packaged; explicit opt-in; root DB ignored) |
| `dev-docs/MAINTENANCE_LOG.md` | Detail entry |
| `dev-docs/index.md` | Catalog this plan (same PR) |

## Tasks

- [ ] **Step 1: Provider module** — `importlib.resources` table loading +
  cache + isolation contract + `packaged_source_hash()`; unit tests (table
  identity vs CSVs, cache isolation, hash determinism).
- [ ] **Step 2: Route the three call sites** — provider by default; explicit
  path → validated read-only adapter (Phase A `check_explicit_db`;
  `mode=ro`, never create). Keep `db_connect` for the explicit path; remove
  or gate its bootstrap-on-absent so default runs cannot write.
- [ ] **Step 3: Settings + GUI construction** — deprecate relative default
  (warning, honor per decision 1); template + GUI docs updated; remove
  `settings_builder` root discovery.
- [ ] **Step 4: Export descriptor + ignored-DB warning** — per Q3/Q4
  decisions; update export tests; value-free messages only.
- [ ] **Step 5: Parity + transition tests** — golden suite unmodified and
  green; sentinel root DB ignored with packaged result; explicit-DB parity vs
  source CSVs; malformed/drift DBs fail closed pre-calculation; no CWD writes
  asserted (repo-root artifact guard); export payload carries no absolute path
  in either mode.
- [ ] **Step 6: Docs + verification ladder** — CHANGELOG migration note +
  MAINTENANCE_LOG detail; ladder: new tests → full `pytest -q` → `ruff` →
  `basedpyright` → `bandit` + semgrep → `check_doc_freshness` →
  `check_gui_test_placement` → `check_changelog` → `check_file_sizes` →
  `audit_dependencies` (lock untouched; expect green).
- [ ] **Step 7: Push, PR, reviews** — push branch, open PR, request Kilo +
  Spark implementation reviews. Merge only on approval + green CI.

## Acceptance Criteria

- Default installed and editable runs do correction lookup with no CWD writes
  and ignore any root/CWD `corrections.db` (sentinel test proves it).
- Explicit SQLite use is read-only, validated, fails closed pre-calculation.
- Existing HVL / `k_med` / `k_tab` / PSD results unchanged (goldens unmodified).
- Exports identify the correction source with a hash and no absolute path.
- Diff: provider + call-site routing + settings/GUI/export + tests + changelog/
  maintenance-log/index docs. No lock changes; no §4/§5 work.
