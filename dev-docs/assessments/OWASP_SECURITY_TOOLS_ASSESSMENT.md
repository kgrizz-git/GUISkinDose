# OWASP security tools — assessment and recommendations

_Date: 2026-06-27_

Investigates SAST, dependency-scanning, and secret-detection tools for OWASP Top 10
compliance, evaluating what is already in place and what would add the most value.

---

## Current tooling

| Tool | Type | Scope | CI | Pre-commit | Notes |
|------|------|-------|----|-----------|-------|
| **bandit** | SAST (AST-level) | Python code | `ci.yml` `static-analysis` job | Yes | `--severity-level medium` on `src/guiskindose` + `scripts`; configured in `pyproject.toml` |
| **pip-audit** | Dependency vuln scan | Python packages | `ci.yml` `static-analysis` job | — | `--desc on`; checks against PyPI advisory feed |
| **gitleaks** | Secret detection | Git history | `.github/workflows/gitleaks.yml` on push/PR | Yes (pre-commit stage) | Wired in both pre-commit and CI |

### OWASP Top 10 (2021) coverage gap

| Category | Bandit | pip-audit | Gap |
|----------|--------|-----------|-----|
| A01: Broken Access Control | Partial (hardcoded perms) | — | Logic-level access control not detected |
| A02: Cryptographic Failures | Partial (weak crypto) | — | Protocol-level issues |
| A03: Injection | Partial (SQL, shell) | — | No template/SSTI, no OS-command flow analysis |
| A04: Insecure Design | — | — | **Not covered** by bandit's AST-only approach |
| A05: Security Misconfiguration | Partial | — | Flask/Django config not checked |
| A06: Vulnerable Components | — | Yes | pip-audit covers this |
| A07: Auth Failures | — | — | **Not covered** |
| A08: Data Integrity Failures | — | — | Deserialization, supply-chain not checked |
| A09: Logging & Monitoring | — | — | **Not covered** |
| A10: SSRF | — | — | **Not covered** |

Bandit's AST-only approach cannot catch logic-level flaws, injection paths through
multiple functions, or configuration issues — gaps that a dataflow-capable SAST can fill.

---

## Recommended additions

### 1. semgrep (high priority)

Multi-language SAST with dataflow analysis and [official OWASP Top 10 rule packs](https://semgrep.dev/rule-lists). Catches most of what bandit misses.

**Pros:**
- OWASP Top 10, CWE, and Python-specific rulesets available out of the box
- Dataflow tracking (A01, A03, A10)
- Runs locally (`pip install semgrep`) and in CI
- Suppress-per-finding with code comments; no noisy baseline needed

**Cons:**
- Slower than bandit (100–200 files takes ~5–10s)
- ~30 MB install; optional `[dev]` dependency

**Suggested CI config:**
```yaml
- name: Semgrep OWASP Top 10
  uses: semgrep/semgrep-action@v1
  with:
    config: p/owasp-top-ten
    audit_on: push
```

Or run locally:
```bash
pip install semgrep safety
semgrep --config=p/owasp-top-ten --error src/guiskindose
safety scan
```

### 2. safety (medium priority — CI optional)

Alternative/complement to pip-audit. Checks against Safety DB's broader advisory feed
(not just PyPI). Catches some CVEs pip-audit misses (and vice versa — both is ideal).

> **API key required for `safety scan`:** Safety >=3.0 requires authentication (`safety auth` or
> `SAFETY_API_KEY` env var). Free tier available at [safetycli.com](https://safetycli.com).
> CI skips the step when the secret is unset; `pip-audit` remains the no-key dependency gate.
> See [SECURITY_TOOLS_CI_PLAN.md](../plans/SECURITY_TOOLS_CI_PLAN.md).

```bash
pip install safety
export SAFETY_API_KEY=...   # or safety auth locally
safety scan --detailed-output
```

### 3. grype (medium priority) — **Shipped**

SBOM-based vulnerability scanner (Anchore). Scans the built wheel/sdist rather than the source tree — catches dependency issues at release time. **Wired into `.github/workflows/release.yml`** via `anchore/scan-action v7.4.0`; policy (`fail-on: high`, `only-fixed: true`) is in `.grype.yaml` at the repository root. See [`dev-docs/plans/GRYPE_RELEASE_SCAN_PLAN.md`](../plans/GRYPE_RELEASE_SCAN_PLAN.md).

Note: grype is a standalone Go binary — **`pip install grype` does not work** (no PyPI package exists). Install locally via:

```bash
brew install grype                                                    # macOS
curl -sSfL https://get.anchore.io/grype | sudo sh -s -- -b /usr/local/bin  # Linux/macOS
grype dist/*.whl dist/*.tar.gz --fail-on high --only-fixed
```

### 4. OWASP Dependency-Check (low priority)

Most useful for Java/.NET projects. The Python support (`pip install dependency-check`)
is a community plugin with less coverage than pip-audit or safety. Not recommended given
existing coverage.

---

## Secret detection

| Tool | Pros | Cons | Status |
|------|------|------|--------|
| **gitleaks** | Fast, zero-config, pre-commit native | Git-history only | **Wired** (pre-commit + CI) |
| **Trufflehog** | Filesystem + Git + S3; entropy detection | Slower, heavier | Not evaluated |

**Recommendation:** Gitleaks is already wired in pre-commit and CI. No action needed.

---

## Recommendation summary

| Action | Effort | Impact | Priority | Status |
|--------|--------|--------|----------|--------|
| Add **semgrep** (OWASP Top 10 rules) to CI `static-analysis` job | Low | High (fills biggest SAST gap) | **High** | **Shipped** (CI + pre-push) |
| Add **safety** alongside pip-audit in CI | Low | Medium (broader advisory coverage) | Medium | **Shipped** (CI; skipped without `SAFETY_API_KEY`) |
| Add **grype** to release workflow | Medium | Low (supply-chain hardening) | Low | **Shipped** (`anchore/scan-action v7.4.0`; `.grype.yaml`) |
| Add **shellcheck** (`shellcheck-py`) for shell scripts | Low | Medium (catches quoting/`set -e` bugs) | Medium | **Shipped** (pre-commit + CI) |

### Quick start (local)

```bash
# Already installed (dev deps):
bandit -c pyproject.toml -r src/guiskindose scripts --severity-level medium
pip-audit --desc on

# To add (pip install):
pip install semgrep safety
semgrep --config=p/owasp-top-ten --error src/guiskindose
safety scan
```
