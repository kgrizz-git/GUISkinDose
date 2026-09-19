# Phase B Execution Plan — Correction-Data Provider Swap

Status: Complete — implemented, merged as PR #102 (2026-09-18), CI green. Archived.
(Original pre-implementation status lines below are kept as history.)
Created: 2026-09-18
Parent (master) plan: [CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md](../CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md)
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
2. **Bare default collapses to packaged.** Unset/`None`/empty-or-whitespace/
   `"corrections.db"` (compared stripped) all resolve to the packaged provider.
   The string `"corrections.db"` can no longer mean "bootstrap here": an
   implicitly present root/CWD DB is ignored (with the §Step-5 warning when
   detected), never loaded, never treated as user data.
3. **Deprecate, don't remove.** The `corrections_db_path` interface stays;
   removal (if ever) is a separately announced breaking release per the master
   plan's SemVer note. This plan is patch-level behavior-preserving.
4. **Legacy explicit-DB policy (BLOCK fix).** The real bootstrap DB carries no
   `schema_version` table, so hard-requiring one would fail-closed every
   existing user DB — the opposite of legacy compatibility. Policy: an absent
   version table is classified as documented `legacy` and still gets full
   content validation (tables/columns/types/ranges/duplicates); refuse only on
   missing/malformed content. `expected_version` applies only when the table
   exists. Tested both ways.
5. **Value-free errors (BLOCK fix).** Phase A `ValidationIssue` messages embed
   `str(db_path)`; `check_explicit_db` itself stops embedding paths in its
   messages, and the adapter maps issues to value-free output (code + table/
   column only, never the path) via `safe_error_event`/`safe_warning`, with a
   test asserting the raised error contains no path.
6. **Warn-and-honor refined.** Non-default strings warn once (value-free) then
   honor read-only. `~` is NOT expanded: reject `~`-leading paths with a
   migration hint (sqlite behavior differs by OS; silent rewriting is worse).
   No traversal rejection (reads are read-only). Fail closed on: `file:`/URI
   values, embedded NUL, directory targets, nonexistent files, non-SQLite
   bytes, any content-validation failure. Windows: build the read-only URI via
   `Path.resolve().as_uri() + "?mode=ro"` (fixes Phase A's `f"file:…"` drive-
   letter bug in `correction_validation.py`).

## Open Design Questions (for reviewers — recommendations wanted)

- **Q1 (path semantics):** warn-and-honor for every non-default relative path
  — stress-test this. Is there a relative-path case that must fail closed
  instead (e.g. path traversal outside CWD, `"~/…"` unexpanded, empty-string
  vs unset)? What exact warning text/channel?
- **Q2 (provider shape):** `src/guiskindose/correction_data.py` (module of
  functions, codebase style): module-level `dict[str, DataFrame]` behind
  `threading.Lock` (double-checked fill; thundering-herd + `run.io_bound`
  concurrency), `get_table()` returns a deep `df.copy()` under a documented
  read-only contract, cache clearable for tests, isolation test included.
  `lru_cache` rejected (hands out the shared object; no clean invalidation).
  Load via `importlib.resources` with `as_file()`/`open_binary` (bare
  `Traversable` breaks for zipped installs; unpacked wheels work regardless).
  Explicit `dtype=` matching the SQLite schema + a provider-vs-bootstrap
  table-parity test (dtype-normalized frame equality for the three runtime
  tables) — closing the SQLite-REAL vs CSV-inference gap.
- **Q3 (warning placement):** centralized resolver at the provider boundary
  with a `_warned` flag keyed on source class (never path): `logger.warning`
  on `guiskindose` + `warnings.warn(DeprecationWarning, stacklevel=2)`,
  honoring `emit_warnings=False` (GUI preview dry-run must not spam); GUI
  surface reuses existing per-run `state.calc_warnings`, no new mechanism.
  Never in `PyskindoseSettings.__init__` (constructed constantly; also keeps
  settings free of `corrections`/`db_connect` per the layering test) and never
  at import. Ignored-DB probe (CWD + repo root) at first use, counts only.
- **Q4 (export descriptor):** keep `corrections_db_path` as a string
  (effective path, or `"packaged"` sentinel for the default) and add sibling
  `corrections_db_source: {"source": "packaged-csv" | "explicit-sqlite",
  "sha256": "<hex>"}` — overloading the key to dict would break
  `non_default_settings()` `!=` diffing and filename-expecting consumers.
  Bump `RICH_EXPORT_SCHEMA_VERSION` 1→2 (new payload content; cheap, unpinned
  by tests); `EXPORT_SCHEMA_VERSION` (=2) untouched (key absent from that
  path). Hash = SHA-256 over, in manifest order, each `runtime_lookup`
  table's filename + `b"\0"` + raw CSV bytes (result-affecting content only;
  cached lazily); explicit mode hashes the DB file bytes (documents file
  identity, not normal form).

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
  `check_explicit_db` validators under the decision-4 legacy policy;
  validation failures raise actionable value-free errors (decision 5) before
  calculation; never bootstrap a replacement.
- Deprecate the relative default in `PyskindoseSettings`
  (`pyskindose_settings.py:123`), `settings_example.json:59`, GUI settings
  construction; document explicit absolute opt-in. `db_connect.py`: hard-delete
  the `if not db_exist:` bootstrap branch (`:49-80`) and open read-only
  unconditionally — the explicit adapter is its only remaining caller and a
  latent create path is a footgun.
- Remove the repo-root discovery in `gui/settings_builder.py:109-112`
  outright (leaving it would silently reclassify every editable-checkout GUI
  run as explicit opt-in).
- Export descriptor + hash per Q4 resolution; update affected export tests.
- Ignored-DB warning diagnostic per Q3 resolution.
- Pre-existing bootstrap-dependent tests are enumerated and updated (they
  become legacy-policy coverage, NOT silently passing unmodified):
  `test_corrections.py` via absolute `tests/manual_tests/corrections.db`
  (unversioned → legacy policy) and its ad-hoc single-table tmp DB;
  `test_k_tab_transmission_characterization.py:48-52` and
  `test_tube_identity.py` repo-root DB references; `test_golden_k_tab.py:53`
  and `tests/gui/test_calculate_tab_coverage.py:241,310` legacy sentinels
  (transparent routing or explicit update — decided at implementation, stated
  in the PR); `test_export_payload.py` and `test_export_data_post_init.py`
  for the sibling-key + schema-bump export shape.

**Out of scope:** §4 guides (Phase C), §5 wheel proof (Phase D), custom
equipment profiles, support geometry, fixture-DICOM scrub (tracked TO_DO
deferral), `db_connect.py` removal (kept for the explicit adapter path).

## Global Constraints

- Numerical identity: all pre-existing golden/dose tests pass UNMODIFIED —
  the proof of behavior preservation (plus a new sentinel-DB test proving the
  packaged path ignores a seeded root DB).
- Provider imports stdlib + pandas + `importlib.resources` +
  `guiskindose.correction_validation` + `guiskindose.privacy` (for
  `safe_warning`/`safe_error_event`) only; `test_architecture_layers.py`
  stays green (new top-level module is unscanned; settings still imports
  neither `corrections` nor `db_connect`).
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
| `src/guiskindose/db_connect.py` | Hard-delete the bootstrap branch; always read-only |
| `src/guiskindose/settings/pyskindose_settings.py:123` | Default deprecation |
| `src/guiskindose/settings_example.json:59` | Template default |
| `src/guiskindose/gui/settings_builder.py:109-112` | Remove root discovery |
| `src/guiskindose/export/sections.py` (`_SETTINGS_KEYS`) | Descriptor + hash |
| `tests/unittests/test_correction_data_provider.py` (new) | Parity, sentinel, no-CWD-write, explicit, fail-closed, export descriptor |
| `tests/unittests/test_corrections.py`, `test_k_tab_transmission_characterization.py`, `test_tube_identity.py`, `test_golden_k_tab.py`, `tests/gui/test_calculate_tab_coverage.py`, `test_export_payload.py`, `test_export_data_post_init.py` | Updated to legacy-policy/explicit routing and export-descriptor shape (enumerated, not unmodified) |
| `dev-docs/CODEBASE_OVERVIEW.md`, `dev-docs/FEATURE_INVENTORY.md` | Update `corrections_db_path` default documentation |
| `CHANGELOG.md` | Migration note (default now packaged; explicit opt-in; root DB ignored) |
| `dev-docs/MAINTENANCE_LOG.md` | Detail entry |
| `dev-docs/index.md` | Catalog this plan (same PR) |

## Tasks

- [x] **Step 1: Provider module** — `importlib.resources` table loading +
  cache + isolation contract + `packaged_source_hash()`; unit tests (table
  identity vs CSVs, cache isolation, hash determinism).
- [x] **Step 2: Route the three call sites** — provider by default; explicit
  path → validated read-only adapter (Phase A `check_explicit_db`;
  `mode=ro`, never create). Keep `db_connect` for the explicit path; remove
  or gate its bootstrap-on-absent so default runs cannot write.
- [x] **Step 3: Settings + GUI construction** — deprecate relative default
  (warning, honor per decision 1); template + GUI docs updated; remove
  `settings_builder` root discovery.
- [x] **Step 4: Export descriptor + ignored-DB warning** — per Q3/Q4
  decisions; update export tests; value-free messages only.
- [x] **Step 5: Parity + transition tests** — table-parity test (provider
  frame vs legacy bootstrap frame, dtype-normalized, three runtime tables);
  golden suite green with the enumerated updates above; sentinel root DB AND
  CWD DB ignored with packaged result; explicit-DB parity vs source CSVs;
  malformed/drift DBs fail closed pre-calculation; raised errors contain no
  path (asserted); dedicated temp-CWD run asserts no file is created (the
  session guard excludes `corrections.db*`, so this must be its own test);
  export payload carries no absolute path in either mode.
- [x] **Step 6: Docs + verification ladder** — CHANGELOG migration note +
  MAINTENANCE_LOG detail; ladder: new tests → full `pytest -q` → `ruff` →
  `basedpyright` → `bandit` + semgrep → `check_doc_freshness` →
  `check_gui_test_placement` → `check_changelog` → `check_file_sizes` →
  `audit_dependencies` (lock untouched; expect green).
- [x] **Step 7: Push, PR, reviews** — push branch, open PR, request Kilo +
  Spark implementation reviews. Merge only on approval + green CI.

## Acceptance Criteria

- Default installed and editable runs do correction lookup with no CWD writes
  and ignore any root/CWD `corrections.db` (sentinel test proves it).
- Explicit SQLite use is read-only, validated, fails closed pre-calculation.
- Existing HVL / `k_med` / `k_tab` / PSD results unchanged (goldens green
  with the enumerated test updates; table-parity test proves CSV==SQLite).
- Exports identify the correction source with a hash and no absolute path.
- Diff: provider + call-site routing + settings/GUI/export + tests + changelog/
  maintenance-log/index docs. No lock changes; no §4/§5 work.
