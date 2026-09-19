# Correction data

GUISkinDose corrects the reported air kerma with physics factors for beam
quality (HVL), medium, backscatter, and patient-support (table/pad)
transmission. This page explains where those numbers come from and which
controls are supported, legacy, or advanced.

## The packaged default (recommended)

Correction tables ship inside the package and are used automatically — no
setup, no downloads, no extra files. Every calculation reads the same
versioned data, so results are reproducible across machines. You can verify
what shipped in
`src/guiskindose/table_data/correction_data_manifest.json` (table schemas,
units, sources, and SHA-256 hashes).

## Custom databases (legacy / advanced)

If you have your own SQLite correction database, point `corrections_db_path`
at it **explicitly, preferably with an absolute path**:

- The file is validated read-only before any calculation (schema version where
  present, then the requested table's schema, columns, ranges, duplicates) and
  fails closed with an actionable error.
  Nothing is ever written to it, and no working-directory database is created.
- Relative paths still work but are deprecated and warn once per process — prefer
  absolute paths.
- A `corrections.db` file sitting in the working directory is **ignored** (you
  will see a one-time notice); it is never loaded silently. This replaces the
  old behavior where such a file was bootstrapped and read automatically.

Exports record the correction source (`packaged-csv` or `explicit-sqlite`)
plus a content hash instead of a filesystem path, so reports stay portable
and free of local paths.

## Supported, legacy, and future controls

- **Supported:** packaged correction data (default); explicit absolute SQLite
  path with validation; `k_tab_val` estimated transmission; kerma-meter
  correction tables (see the in-app kerma-meter help).
- **Legacy / advanced:** relative `corrections_db_path` values (warn, still
  honored read-only); hand-rolled SQLite databases without a schema-version
  table (accepted as `legacy` with full content validation).
- **Not yet available:** reusable custom equipment/model profiles (per-model
  coordinate and transmission presets) — tracked in the development backlog.
  They will live in versioned profile files, not in SQLite.

## Background reference

For the per-table loader/consumer map, lookup behavior, and provenance
(inherited literature, SpekCalc simulation, measured/approximated tables),
see `dev-docs/CORRECTION_DATA_REFERENCE.md` in the repository.
