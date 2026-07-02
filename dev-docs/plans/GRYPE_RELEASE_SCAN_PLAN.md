# Grype release-scan plan

> **Status:** NEEDS REVIEW

Adds [grype](https://github.com/anchore/grype) vulnerability scanning of the built wheel and
source distribution to the release workflow, providing supply-chain hardening for published
artifacts.

---

## Motivation

CI already runs `pip-audit`, `safety`, and `bandit` against the *source* tree (see [SECURITY_TOOLS_CI_PLAN.md](SECURITY_TOOLS_CI_PLAN.md)). Grype scans a
**built artifact** (wheel/sdist), which catches vulnerabilities introduced by the build process
itself (packaging metadata, included data files, transitive deps resolved at build time). This
closes a gap identified in the
[OWASP security tools assessment](../assessments/OWASP_SECURITY_TOOLS_ASSESSMENT.md) (line 122)
and complements our source-level static analysis and dependency scanning.

---

## Scope

- **In scope:** scan the wheel and sdist produced by `python -m build` in `.github/workflows/release.yml`, configure false-positive and fixed-only policy via `.grype.yaml`, and preserve scan logs via CI artifact upload.
- **Out of scope:** modifying `pyproject.toml` dev dependencies (Grype is a standalone container/artifact scanner, not a Python package), pre-commit or pre-push hooks (scanning every commit with Grype is unnecessary), Docker image scanning, and SBOM generation (deferred). Scheduled inter-release vulnerability scanning is noted as a future enhancement.

---

## Implementation

### 1. Create `.grype.yaml` configuration

Create a `.grype.yaml` configuration file in the repository root to define vulnerability thresholds, enforce actionable reporting, and document false-positive exclusions:

```yaml
# Grype configuration for release artifact scanning
# See: https://github.com/anchore/grype

# Only report/fail on vulnerabilities that have a known fix available
only-fixed: true

# Fail scan if any vulnerability at or above this severity is detected
fail-on: high

# Ignore documented false positives or accepted risks
ignore:
  - # Example format when excluding advisory mismatches:
    # vulnerability: CVE-YYYY-NNNN
    # reason: "Does not affect Python wheel distribution"
```

> **Note:** Do **not** add Grype to `pyproject.toml` `[dev]` dependencies. The PyPI `grype` package does not exist (it is a standalone Go binary). Keeping it out of `[dev]` avoids forcing local developers to download a ~20 MB binary for a release-only check.

### 2. Add scan and artifact upload steps to `.github/workflows/release.yml`

In `.github/workflows/release.yml`, insert two new steps **after** `Build a binary wheel and a source tarball` and **before** `Publish distribution to PyPI`:

```yaml
    - name: Scan built artifacts with grype
      uses: anchore/scan-action@v7
      id: grype-scan
      with:
        path: dist/
        fail-build: true
        severity-cutoff: high
        output-format: json
        output-file: grype-scan.json
        only-fixed: true

    - name: Upload grype scan results
      uses: actions/upload-artifact@v4
      if: always()
      with:
        name: grype-release-scan
        path: grype-scan.json
        retention-days: 30
```

- `anchore/scan-action@v7` is Anchore's official GitHub Action. It automatically installs the Grype binary, updates the vulnerability database, runs the scan against `path: dist/`, and evaluates exit codes.
- `fail-build: true` and `severity-cutoff: high` block publication if any high or critical vulnerability is found.
- `only-fixed: true` ensures the release is only blocked by actionable vulnerabilities that have a patch available.
- `if: always()` on `actions/upload-artifact@v4` ensures that if a release is blocked by a CVE, developers can download `grype-scan.json` from the workflow run to inspect the exact findings.

### 3. Add a policy comment in `release.yml`

At the top of `release.yml`, add a comment explaining the threshold and how to adjust it:

```yaml
# grype scan threshold: --fail-on high --only-fixed (blocks release on actionable high/critical CVEs).
# Thresholds and false-positive exclusions are configured in .grype.yaml at repository root.
```

### 4. Local usage & quick start

Developers should run Grype locally against fresh artifacts before tagging a release:

```bash
# 1. Clean previous build artifacts
rm -rf dist/ build/

# 2. Build fresh wheel and sdist
python -m build

# 3. Install Grype locally (choose one method):
# macOS via Homebrew:
brew install grype
# Linux/macOS official installer:
curl -sSfL https://get.anchore.io/grype | sudo sh -s -- -b /usr/local/bin
# Or via Docker without installing locally:
docker run --rm -v "$(pwd):/work" anchore/grype:latest /work/dist

# 4. Run scan against built artifacts (picks up .grype.yaml automatically):
grype dist/*.whl dist/*.tar.gz --fail-on high --only-fixed
```

### 5. Update documentation

| File | Change |
|------|--------|
| `dev-docs/plans/GRYPE_RELEASE_SCAN_PLAN.md` | This plan |
| `.grype.yaml` | Create root configuration file for false positives and policy |
| `dev-docs/TO_DO.md` | Add link to this plan |
| `dev-docs/index.md` | Add row for this plan under execution plans |
| `dev-docs/HARNESS_ENGINEERING.md` | Document local Grype command and `.grype.yaml` location |
| `dev-docs/assessments/OWASP_SECURITY_TOOLS_ASSESSMENT.md` | Update grype status from "Planned" to "Shipped" after merge, correct CLI syntax |

---

## Acceptance criteria

- [ ] `.grype.yaml` exists at repository root with `only-fixed: true` and `ignore:` block
- [ ] Local build (`rm -rf dist/ && python -m build`) and scan (`grype dist/*.whl --fail-on high`) pass without errors
- [ ] `.github/workflows/release.yml` scan step uses `anchore/scan-action@v7` and passes on tag-triggered release
- [ ] Scan results artifact (`grype-scan.json`) is uploaded and accessible in GH Actions run history
- [ ] A release with a synthetic or known high/critical CVE in a dependency **blocks** publication
- [ ] `dev-docs/index.md`, `TO_DO.md`, and `HARNESS_ENGINEERING.md` updated

---

## Risk / rollback

- **False positives:** Grype may flag advisory mismatches (e.g. CVE for a C library dependency that does not affect the Python wheel). Mitigate with `.grype.yaml` `ignore:` list and `only-fixed: true`.
- **Stale artifacts:** Scanning a dirty `dist/` directory may report vulnerabilities from old builds. Always clean `dist/` before building. In CI, clean checkout guarantees fresh artifacts.
- **Inter-release vulnerability disclosure:** A dependency CVE disclosed after a release will not be caught until the next build. As a future improvement, a scheduled weekly workflow or Dependabot integration should be added for continuous monitoring.
- **Network dependency:** Grype downloads its vulnerability database on first run; CI runners have high-speed internet access so this adds ~10 s.
- **Rollback:** Remove the scan and artifact upload steps from `.github/workflows/release.yml` and delete `.grype.yaml`.
