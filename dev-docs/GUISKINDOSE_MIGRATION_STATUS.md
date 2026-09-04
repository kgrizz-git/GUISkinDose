# GUISKINDOSE_MIGRATION_STATUS.md

_Originally dated 2026-04-21. Corrected 2026-07-26 for current packaging._

## Migration Status Summary

**Goal:**
Enable this fork to be published on PyPI **alongside** the original project by
renaming the import/package identity from `pyskindose` → `mypyskindose` →
`guiskindose` while preserving upstream attribution and core behavior.

**Status:** Namespace migration is complete. Day-to-day development uses
`pyproject.toml` optional extras and `uv.lock` (when using `uv`). There are
**no** `requirements*.txt` files in this repository.

## What Has Been Completed

- **Namespace Migration:**
  - All source code migrated from `pyskindose` to `guiskindose` (via `mypyskindose`).
  - Imports and references updated throughout the codebase.
- **Testing & Validation:**
  - Unit and integration tests run under the project’s supported Python versions
    (see CI / `requires-python` in `pyproject.toml`).
  - Editable install and build validation are part of normal maintainer workflow.
- **Linting:**
  - Linter switched from deprecated `pylama` to `ruff`.
- **Project Metadata:**
  - `pyproject.toml` holds project URLs, dependencies, classifiers, and extras
    (`gui`, `dev`, `docs`, `notebooks`, …). Prefer
    `pip install -e ".[dev,gui]"` or `uv sync --all-extras`.
- **Cleanup:**
  - Legacy `requirements*.txt` files were **removed**; do not reintroduce them.
  - Legacy/unused build metadata artifacts removed where applicable.

## Related docs

- [README.md](../README.md) — install and intended use
- [PUBLISHING.md](../PUBLISHING.md) — PyPI Trusted Publishing (optional releases)
- [dev-docs/FORK_MAINTAINER_GUIDE.md](FORK_MAINTAINER_GUIDE.md) — fork stewardship
