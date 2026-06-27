# Security tools CI/hooks plan

Adds semgrep (SAST) and safety (dependency scanning) to CI and pre-push hooks.
Gitleaks is already wired in both — no changes needed.

---

## Review notes (2026-06-27)

Plan reviewed against the live config (`pyproject.toml`, `.pre-commit-config.yaml`,
`.github/workflows/ci.yml`, `.github/workflows/gitleaks.yml`). Findings and fixes:

- **Safety has no API key yet → step must skip gracefully (not fail).** `safety scan`
  requires authentication; with no key in a non-interactive runner it drops to a
  `(R)egister/(L)ogin` prompt and dies on EOF — it does **not** silently no-op. Phase 2
  is rewritten to skip the step when `SAFETY_API_KEY` is absent. This is safe because
  `pip-audit` (already in CI) covers dependency scanning; safety is purely additive.
- **`if: secrets.X != ''` is invalid.** The `secrets` context cannot be used in `if:`.
  The supported pattern is a **job-level** `env:` mapping the secret, then
  `if: env.SAFETY_API_KEY != ''` on the step (step-level `env:` is not reliably visible
  to that same step's `if:`).
- **semgrep rule pack name.** Registry pack is `p/owasp-top-ten` (not `p/owasp-top-10`, which 404s).
- **semgrep scan scope.** Pre-push and CI scan `src scripts .github/workflows docs/source/conf.py`.
  The OWASP pack's `run-shell-injection` rule flagged `${{ github.* }}` interpolated directly
  into `run:` steps in `ci.yml`; these were fixed with env-var indirection (map the context to
  a job/step `env:` var, then reference `"$VAR"` in the shell) rather than excluded.
- **shellcheck (shell linting).** Added via the `shellcheck-py` pip wrapper — cross-platform,
  no Docker. Pre-commit hook (`shellcheck-py` repo, auto-detects shell files) + CI step on
  `run_gui.sh` and `scripts/type_baseline.sh`. `.bat` launchers are not covered (no mature
  batch linter). Fixing the initial findings also repaired latent `set -e` bugs in `run_gui.sh`
  where error handlers after bare commands were unreachable.
- **semgrep network + metrics.** `--config=p/owasp-top-ten` is fetched from the Semgrep registry,
  so pre-push/CI need internet (offline pushes fail). Add `--metrics=off` to avoid sending
  anonymized telemetry.
- **semgrep on Windows.** Native Windows support shipped (Fall 2025) but is beta and
  needs `PYTHONUTF8=1`. The pre-push hook should be documented as best-effort on
  Windows; CI runs on ubuntu so the gate itself is unaffected.
- Verified: bandit + gitleaks are in `pre-commit`; bandit + pip-audit are in the CI
  `static-analysis` job; gitleaks has its own workflow. The "Current state" table is
  accurate.

---

## Current state

| Tool | Pre-commit | Pre-push | CI |
|------|-----------|----------|----|
| bandit | `pre-commit` stage | — | `static-analysis` job |
| pip-audit | — | — | `static-analysis` job |
| gitleaks | `pre-commit` stage | — | `.github/workflows/gitleaks.yml` |
| semgrep | — | pre-push | `static-analysis` job |
| safety | — | — | `static-analysis` job (skipped without `SAFETY_API_KEY`) |
| shellcheck | `pre-commit` stage | — | `static-analysis` job |

---

## Phase 1: semgrep (pre-push + CI)

Add semgrep with OWASP Top 10 rules as a pre-push hook (slower than bandit, so not
pre-commit) and a CI job alongside bandit.

**Steps:**

1. **Add to dev dependencies** in `pyproject.toml`:
   ```toml
   dev = [
       ...
       "semgrep>=1.100",
   ]
   ```

2. **Add pre-push hook** in `.pre-commit-config.yaml` (under the `repo: local` hooks):
   ```yaml
   - id: semgrep
     name: semgrep (OWASP Top 10 SAST)
     entry: semgrep --config=p/owasp-top-ten --error --metrics=off src scripts .github/workflows docs/source/conf.py
     language: system
     pass_filenames: false
     always_run: true
     stages: [pre-push]
   ```
   > **Network + platform notes:** `--config=p/owasp-top-ten` is fetched from the Semgrep
   > registry, so the hook needs internet (offline pushes will fail). `--metrics=off`
   > disables anonymized telemetry. semgrep runs natively on Windows (beta, Fall 2025)
   > but expects `PYTHONUTF8=1`; treat the Windows pre-push hook as best-effort and note
   > this in `AGENTS.md` "Development setup".

3. **Add CI step** in `.github/workflows/ci.yml` under `static-analysis`:
   ```yaml
   - name: Semgrep (OWASP Top 10 SAST)
     run: semgrep --config=p/owasp-top-ten --error --metrics=off src scripts .github/workflows docs/source/conf.py
   ```
   Install is already handled by `pip install -e ".[dev,gui]"`. CI runs on
   `ubuntu-latest`, so the registry fetch and POSIX behavior are reliable there.

4. **Configure `.semgrepignore`** (optional, to exclude test dirs):
   ```
   tests/
   .venv/
   venv/
   build/
   dist/
   backups/
   ```

## Phase 2: safety (CI only, optional — skipped without an API key)

Safety scans dependency trees against Safety DB's advisory feed. Redundant with
pip-audit but catches some CVEs pip-audit misses (different advisory database).

Run in CI only — scanning dependencies on every commit is overkill.

> **No API key yet — and that's fine.** `safety scan` (>=3.0) requires authentication;
> with no key in a non-interactive runner it drops to a `(R)egister/(L)ogin` prompt and
> fails on EOF (it does *not* no-op). So the CI step is written to **skip itself when
> `SAFETY_API_KEY` is not set**. `pip-audit` already provides dependency-vuln coverage,
> so the build stays green until a key is added later. When a key is available, add it to
> [GitHub Actions secrets](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions)
> (free tier at [safetycli.com](https://safetycli.com)) and the step activates
> automatically — no workflow edit needed.

**Steps:**

1. **Add to dev dependencies** in `pyproject.toml`:
   ```toml
   dev = [
       ...
       "safety>=3.0",
   ]
   ```

2. **Map the secret at the job level** in `.github/workflows/ci.yml` (`secrets` cannot be
   referenced inside `if:`, so it must be exposed via `env` first):
   ```yaml
   jobs:
     static-analysis:
       runs-on: ubuntu-latest
       env:
         SAFETY_API_KEY: ${{ secrets.SAFETY_API_KEY }}
       steps:
         ...
   ```

3. **Add the conditional CI step** under `static-analysis`:
   ```yaml
   - name: Safety (dependency vulnerability scan — skipped without key)
     if: env.SAFETY_API_KEY != ''
     run: safety scan --detailed-output
   ```

   When the secret is unset, `env.SAFETY_API_KEY` is empty and the step is skipped
   (shown as a skipped step in the run log), keeping CI green.

## Phase 3: gitleaks (already done)

Gitleaks is fully wired:

- `.pre-commit-config.yaml`: `gitleaks` hook (rev `v8.24.2`) runs at `pre-commit` stage
- `.github/workflows/gitleaks.yml`: scans on every push and PR

No changes needed.

---

## Acceptance criteria

- [x] `pip install -e ".[dev]"` installs semgrep and safety without errors
- [x] `pre-commit run --hook-stage pre-push semgrep --all-files` passes on current code
- [x] `semgrep --config=p/owasp-top-ten --error --metrics=off src scripts .github/workflows docs/source/conf.py` passes in CI (workflow shell-injection findings fixed via env-var indirection)
- [x] **No key yet:** with `SAFETY_API_KEY` unset, the safety step is *skipped* and CI stays green (verify the step shows as skipped, not failed)
- [ ] **When a key exists (later):** set `SAFETY_API_KEY` in GitHub secrets; `safety scan --detailed-output` runs and passes (or known-ignores documented in a safety policy file)
- [x] Gitleaks already green in CI (verify current workflow passes)

---

## File checklist

| File | Change |
|------|--------|
| `pyproject.toml` | Add `semgrep>=1.100`, `safety>=3.0`, `shellcheck-py>=0.11` to `[project.optional-dependencies] dev` |
| `.pre-commit-config.yaml` | Add semgrep pre-push hook (under `repo: local`) with `--metrics=off`; add `shellcheck-py` hook |
| `.github/workflows/ci.yml` | Add semgrep + shellcheck steps + job-level `env: SAFETY_API_KEY` + conditional safety step to `static-analysis` |
| `run_gui.sh`, `scripts/type_baseline.sh` | Fix shellcheck findings (quoting, `read -r`, `set -e` error handling) |
| `.semgrepignore` | **Create** with test/build exclude patterns |
| GitHub repo secrets | **Optional / deferred:** add `SAFETY_API_KEY` (free tier) later to activate the safety step. Not required for this plan — the step skips cleanly without it. |
| `AGENTS.md` | Note semgrep pre-push needs network + `PYTHONUTF8=1` on Windows |
| `dev-docs/TO_DO.md` | Update OWASP implementation item → point to this plan |
| `dev-docs/index.md` | Add row for this plan under execution plans |
| `dev-docs/assessments/OWASP_SECURITY_TOOLS_ASSESSMENT.md` | Update gitleaks status (already wired), fix safety CLI syntax |
