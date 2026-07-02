# Grype release-scan plan

> **Status:** NEEDS REVIEW

Adds [grype](https://github.com/anchore/grype) vulnerability scanning of the built wheel and
source distribution to the release workflow, providing supply-chain hardening for published
artifacts.

---

## Motivation

CI already runs `pip-audit`, `safety`, and `bandit` against the *source* tree. Grype scans a
**built artifact** (wheel/sdist), which catches vulnerabilities introduced by the build process
itself (packaging metadata, included data files, transitive deps resolved at build time). This
closes a gap identified in the
[OWASP security tools assessment](../assessments/OWASP_SECURITY_TOOLS_ASSESSMENT.md) (line 122).

---

## Scope

- **In scope:** scan the wheel and sdist produced by `python -m build` in `.github/workflows/release.yml`.
- **Out of scope:** pre-commit or pre-push hooks (grype is heavier than bandit; scanning every
  commit is unnecessary), Docker image scanning, SBOM generation (deferred).

---

## Implementation

### 1. Add grype to dev dependencies

In `pyproject.toml`, under `[project.optional-dependencies] dev`:

```toml
dev = [
    ...
    "grype>=0.80",
]
```

> **Note:** grype is a Go binary distributed as a Python wrapper (`grype` on PyPI). It
> self-downloads the grype binary on first run. Pin a minimum version but let CI resolve
> the latest compatible release.

### 2. Add scan step to `.github/workflows/release.yml`

Insert a new step **after** `Build a binary wheel and a source tarball` and **before**
`Publish distribution to PyPI`:

```yaml
    - name: Scan built artifacts with grype
      run: |
        grype dir:dist --fail-on high
```

`dir:dist` tells grype to scan the `dist/` directory (containing the wheel and sdist).
`--fail-on high` fails the release if any **high** or **critical** CVE is found; medium/low
findings are reported but do not block publication.

### 3. Add a `--fail-on` policy comment

At the top of `release.yml`, add a comment explaining the threshold and how to adjust it:

```yaml
# grype scan threshold: --fail-on high (blocks release on high/critical CVEs only).
# To be more strict, change to --fail-on medium; to be more lenient, --fail-on critical.
```

### 4. Update documentation

| File | Change |
|------|--------|
| `dev-docs/plans/GRYPE_RELEASE_SCAN_PLAN.md` | This plan |
| `dev-docs/TO_DO.md` | Add link to this plan |
| `dev-docs/index.md` | Add row for this plan under execution plans |
| `dev-docs/assessments/OWASP_SECURITY_TOOLS_ASSESSMENT.md` | Update grype status from "Planned" to "Shipped" after merge |

---

## Acceptance criteria

- [ ] `pip install -e ".[dev]"` installs grype without errors
- [ ] `grype dir:dist --fail-on high` runs locally against a fresh `dist/` and reports results
- [ ] `.github/workflows/release.yml` scan step passes on the next tag-triggered release
- [ ] A release with a known high/CVE in a dependency **blocks** publication (manual test or
      synthetic fixture)
- [ ] `dev-docs/index.md` and `TO_DO.md` updated

---

## Risk / rollback

- **False positives:** grype may flag advisory mismatches (e.g. CVE for a C library dependency
  that doesn't affect the Python wheel). Mitigate with `--fail-on high` (only high/critical
  block) and `--ignore` file for documented false positives.
- **Network dependency:** grype downloads its vulnerability database on first run; CI has
  internet access so this is fine, but initial run adds ~10 s.
- **Rollback:** remove the scan step from `release.yml` and the `grype` line from
  `pyproject.toml`.
