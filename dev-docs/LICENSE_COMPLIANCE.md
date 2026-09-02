# License compliance

GUISkinDose is distributed under the **MIT License** (see [`LICENSE`](../LICENSE)). This document describes how we track and review licenses for third-party Python dependencies.

## Scope

License checks use the same locked **dev + GUI** dependency set as CI static analysis:

```bash
uv run --extra dev --extra gui --locked python scripts/check_licenses.py
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

## Redistributed mesh assets (not Python deps)

Some **demo / non-clinical** STL phantoms under `src/guiskindose/phantom_data/` are third-party mesh
binaries redistributed under Creative Commons terms (e.g. **CC BY 4.0** Ramesses II). These are
**not** Python packages and must **not** be folded into `THIRD_PARTY_NOTICES.md` (that file is
generated from `uv.lock` / installed packages via `check_licenses.py`).

| Requirement | Where |
|-------------|--------|
| Attribution + license for BY / BY-SA meshes | `phantom_data/NOTICE_{id}.txt` beside the STLs |
| Retrieval dates, locked transforms, repair notes | [`references/fun_phantom_provenance.md`](references/fun_phantom_provenance.md) |
| Do not ship **NC** (NonCommercial) meshes | Plan policy — public MIT redistribution conflicts with NC |

The application source remains **MIT**. ShareAlike (BY-SA), when used, applies to **that mesh
derivative** only, not to the application code. Do **not** run
`python scripts/check_licenses.py --write-notices` solely because a mesh shipped.

## Commands

```bash
# Audit licenses in the locked CI-equivalent environment
uv run --extra dev --extra gui --locked python scripts/check_licenses.py

# Regenerate the tracked notices file after dependency changes
uv run --extra dev --extra gui --locked python scripts/check_licenses.py --write-notices

# Fail if THIRD_PARTY_NOTICES.md is stale (optional local/CI check)
uv run --extra dev --extra gui --locked python scripts/check_licenses.py --check-notices

# Treat unknown/review licenses as failures (stricter gate)
uv run --extra dev --extra gui --locked python scripts/check_licenses.py --strict
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
