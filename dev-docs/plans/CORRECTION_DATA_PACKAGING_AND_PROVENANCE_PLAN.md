# Correction Data Packaging and Provenance Plan

Status: Active — follow after immediate safety work
Created: 2026-09-08
Parent roadmap:
[CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md](CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md)
Dependency:
[CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md](CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md)

## Objective

Make inherited correction data scientifically traceable and eliminate the
working-directory-created SQLite default while preserving numerical behavior and
legacy explicit-database compatibility.

This plan does not add custom equipment profiles or redesign support attenuation
geometry.

## Verified Current State

- The authoritative tracked data are CSVs under `src/guiskindose/table_data/`.
- `MANIFEST.in` already includes the correction CSVs and HVL CSVs.
- A root `corrections.db` can exist locally but is gitignored and derived.
- The default `corrections_db_path` is the relative string `"corrections.db"`.
  `db_connect()` creates it in the process CWD when absent.
- HVL, `k_med`, and `k_tab` consumers read complete SQLite tables into pandas.
  Default SQLite bootstrap provides no selective-query advantage.
- Existing wheel tests do not assert correction-data contents or execute correction
  lookup from an installed wheel in a clean working directory.
- Medium/backscatter literature is identifiable. Support-transmission rows have
  limited measured/estimated comments, but exact derivation of every inherited
  value is not known.
- `device_info.csv` is loaded into SQLite but has no runtime consumer.

## Scope

### 1. Build a correction-data inventory

- [ ] Add a machine-readable manifest beside the CSVs with table schema, units,
  physical ranges, runtime consumer, lookup behavior, source type, generation
  method, upstream history, literature identifiers, and provenance confidence.
- [ ] Use explicit `unknown` fields rather than inferring undocumented provenance.
- [ ] Document that the inherited tables first appear in the upstream 2018 initial
  commit and identify later HVL regeneration history.
- [ ] Determine and document whether `device_info.csv` should be retained as
  provenance, connected to equipment profiles, or removed in a later migration.
- [ ] Add hashes or deterministic content checks so manifest and CSV drift is
  detected.

### 2. Add data validation

- [ ] Validate required columns, types, units, finite values, physical ranges,
  duplicate lookup keys, supported status values, and expected grids.
- [ ] Distinguish errors that can change dose from advisory provenance gaps.
- [ ] Validate that a generated SQLite database, when requested by maintainers,
  exactly represents the authoritative CSVs.
- [ ] Keep the immediate Plane B invalid-value behavior in the safety plan; this
  plan validates the whole dataset but does not invent replacement values.
- [ ] For the explicit legacy SQLite adapter, validate before any calculation:
  the file is readable SQLite, its schema version matches an exact or declared
  compatible policy, all required tables and columns are present, and each
  required column is type-checked with finite, in-range, and duplicate-free values.
- [ ] Fail explicit-adapter validation with an actionable, privacy-safe error
  naming the offending table or column; never create or bootstrap a blank replacement.
- [ ] Add schema-drift tests covering a valid DB, a missing or incompatible schema
  version, missing tables/columns, and out-of-range or duplicate data.

### 3. Replace the default SQLite bootstrap

- [ ] Introduce a small correction-data provider that reads package resources with
  `importlib.resources` and caches pandas tables.
- [ ] Route `fetch_and_append_hvl()`, `calculate_k_med()`, and `calculate_k_tab()`
  through the provider.
- [ ] Default operation must not create files in the CWD or mutate installed
  package resources.
- [ ] After migration, default runs ignore any root/CWD `corrections.db` and read
  only the packaged authoritative CSVs via the provider. An implicitly present root
  DB must not be loaded and must not be treated as user-customized data.
- [ ] Only an explicitly configured SQLite `corrections_db_path` invokes the
  temporary read-only compatibility adapter, gated by the §2 validation checks.
- [ ] Deprecate the relative default in `PyskindoseSettings`,
  `settings_example.json`, GUI settings construction, and export metadata; document
  that users with an intentional custom DB must opt in explicitly via an absolute
  SQLite path.
- [ ] Where feasible without reintroducing implicit loading, emit an observable
  warning or migration diagnostic when a root/CWD `corrections.db` is detected but
  deliberately ignored.

### 4. Document factor locations and behavior

- [ ] Add a user-facing correction guide under `docs/source/user/`.
- [ ] Add a maintainer reference under `dev-docs/` that maps each formula/table to
  its loader, consumer, output field, fallback, and tests.
- [ ] Add a source-to-lookup-to-dose/export diagram.
- [ ] Link the guides from Sphinx navigation, `dev-docs/index.md`, feature inventory,
  relevant GUI help, and the getting-started notebook.
- [ ] Explain which controls are supported, which are legacy/advanced, and which
  require the custom-profile plan.
- [ ] Document the migration path for users with an intentional custom DB: how to
  re-point `corrections_db_path` to an explicit absolute SQLite path (or a future
  custom profile) and that default runs now ignore a root/CWD `corrections.db`.

### 5. Verify distribution behavior

- [ ] Extend `tests/unittests/test_packaging.py` to assert all required correction
  CSVs and the manifest are present in the wheel.
- [ ] Build a wheel and install it in a clean environment under a gitignored
  repo-local temporary directory.
- [ ] Run HVL, `k_med`, `k_tab`, and a golden dose calculation without a root DB.
- [ ] Assert no `corrections.db` or other artifact appears in the CWD.
- [ ] Compare wheel/sdist contents and numerical outputs with the source checkout.
- [ ] Assert that a default run ignores a seeded root/CWD `corrections.db` (populated
  with a sentinel value) and returns the packaged-CSV golden result with no CWD writes.
- [ ] Assert explicit custom SQLite parity: a validated explicit DB yields the same
  HVL/`k_med`/`k_tab` as its source CSVs.
- [ ] Assert malformed or schema-drift explicit DBs fail closed with the §2
  validation errors before any calculation.

## Acceptance Criteria

1. Packaged CSVs are explicitly verified as the correction-data source of truth.
2. Default installed and editable runs perform correction lookup without CWD writes.
3. Legacy explicit SQLite use is read-only, validated, and documented.
4. Every table has schema/use/provenance documentation, including explicit unknowns.
5. Existing valid HVL, `k_med`, `k_tab`, and PSD results are unchanged.
6. A default run ignores any root/CWD `corrections.db` and reads only the packaged CSVs.
7. An explicitly configured SQLite path is read-only and fails closed on schema drift
   or malformed content before calculation.

## Delivery

Expected SemVer impact: patch-level packaging/runtime fix. If the legacy
`corrections_db_path` interface is removed rather than deprecated, defer removal to
a separately announced breaking release.

Record user-visible behavior in `CHANGELOG.md`, maintainer-facing validation in
`dev-docs/MAINTENANCE_LOG.md`, and run packaging, correction, golden-dose,
documentation, privacy, lint/type, and full test checks. Note the ignored-root-DB
transition and explicit opt-in requirement as a migration note in the user and
maintainer guides.
