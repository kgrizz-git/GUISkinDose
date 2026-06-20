# License compliance

MyPySkinDose is distributed under the **MIT License** (see [`LICENSE`](../LICENSE)). This document describes how we track and review licenses for third-party Python dependencies.

## Scope

License checks apply to the **full declared dependency set** (all extras), pinned by `uv.lock`:

```bash
uv sync --all-extras
```

That includes core runtime dependencies, GUI extras (`gui`, `gui-native`), dev/CI tooling
(`dev`: `basedpyright`, `pip-audit`, etc.), and the docs + notebook toolchains (`docs`, `notebooks`).
Syncing from the lockfile makes the inventory reproducible regardless of which extras a given
developer installed — the previous `pip install -e ".[dev,gui]"` surface drifted whenever a venv
also carried the docs/notebook packages.

## Policy

| Category | Examples | CI behavior |
|----------|----------|-------------|
| **Allowed** | MIT, BSD-2/3-Clause, Apache-2.0, ISC, PSF-2.0, MPL-2.0, Unlicense, Zlib | Pass |
| **Forbidden** | GPL-2.0, GPL-3.0, AGPL-3.0 (strong copyleft) | **Fail** |
| **Unknown** | Missing or unparseable `License` metadata | Warn locally; fail with `--strict` |
| **Review** | Non-allowlisted but non-GPL licenses (e.g. LGPL) | Printed for maintainer review |

**Rationale:** MIT-licensed application code should not pull in strong copyleft dependencies without explicit legal review. Permissive and weak-copyleft licenses (MPL-2.0) are acceptable for typical Python library use.

## Source-of-truth files

| File | Role |
|------|------|
| [`pyproject.toml`](../pyproject.toml) | Declared direct dependencies |
| [`dev-docs/THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) | Generated inventory (package, version, license) |
| [`scripts/check_licenses.py`](../scripts/check_licenses.py) | Audit script |
| This document | Policy and workflow |

## Commands

```bash
# Audit licenses in the current environment (matches CI)
python scripts/check_licenses.py

# Regenerate the tracked notices file after dependency changes
python scripts/check_licenses.py --write-notices

# Fail if THIRD_PARTY_NOTICES.md is stale (optional local/CI check)
python scripts/check_licenses.py --check-notices

# Treat unknown/review licenses as failures (stricter gate)
python scripts/check_licenses.py --strict
```

## When to update

Run `--write-notices` and commit `dev-docs/THIRD_PARTY_NOTICES.md` whenever you:

- Add, remove, or bump a dependency in `pyproject.toml`
- Change optional extras (`[gui]`, `[dev]`)
- Refresh lockfiles (`uv.lock`) after a dependency update

## Limitations

- License metadata on PyPI is not always accurate; classifiers and `License` fields are heuristically normalized.
- Transitive dependencies are included only after install (not from `pyproject.toml` alone).
- This is **not legal advice**; escalate ambiguous cases (LGPL, custom licenses, bundled native libs) before release.

## Related harness checks

| Check | What it covers |
|-------|----------------|
| `pip-audit` | Known CVEs in dependencies |
| `gitleaks` | Secrets in source/history |
| `bandit` | Python code patterns (SAST; medium+ severity in CI) |
| `check_licenses.py` | License classification and notices inventory |
