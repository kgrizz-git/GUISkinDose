# Enable semgrep & pip-audit pre-push by default

Make semgrep pre-push run automatically for all devs (without requiring `pre-commit install --hook-type pre-push`) and add pip-audit as a pre-push hook.

---

## Current state

| Tool | pre-commit stage | pre-push stage | CI |
|------|-----------------|---------------|----|
| semgrep | — | ✅ defined (needs `--hook-type pre-push`) | `static-analysis` job |
| pip-audit | — | — | `static-analysis` job |
| basedpyright | — | ✅ defined (needs `--hook-type pre-push`) | `static-analysis` job |
| bandit | ✅ | — | ✅ |
| gitleaks | ✅ (separate workflow too) | — | ✅ |
| safety | — | — | ✅ (conditional on API key) |

A dev who runs only `pre-commit install` (without `--hook-type pre-push`) gets bandit, gitleaks, ruff, shellcheck, and the repo-scripts but **not** semgrep, basedpyright, or the changelog check — those only fire if they also run `pre-commit install --hook-type pre-push`.

---

## Options

### Option A: Move semgrep to pre-commit stage

Change `stages: [pre-push]` to `stages: [pre-commit]`. It then runs on every commit
alongside bandit. This is the simplest change but adds ~5–30 s to every commit
(semgrep downloads the rule pack on first run, then caches it).

### Option B: Install both hook types automatically

Keep semgrep as a pre-push hook but make the repo's setup script run
`pre-commit install --hook-type pre-push` automatically. This way semgrep still
only runs at push time (when you're about to ship) but devs don't need a manual
second install step.

### Option C: Accept the manual step but document it prominently

No config change — just update `AGENTS.md` "Development setup" and `CONTRIBUTING.md`
to say `pre-commit install --hook-type pre-push` is required. Lowest effort, but
semgrep stays opt-in.

---

This plan implements **Option B** (recommended): semgrep stays at pre-push cadence
(fast commits), pip-audit joins it there, and the setup is one script call.

---

## Changes

### 1. Add `pre-commit install --hook-type pre-push` to setup

There's no dedicated `setup-dev.sh` yet. The closest is the "Development setup"
section in `AGENTS.md`. Two sub-options:

- **1a.** Add a `scripts/setup-dev.sh` that runs `pre-commit install && pre-commit install --hook-type pre-push`.
- **1b.** Update `AGENTS.md` to show both commands (two lines). Document that
  `pre-commit install` alone installs only `pre-commit` stage hooks; semgrep,
  basedpyright, pip-audit, and changelog check require the pre-push type.

**Recommendation: 1a** — a dedicated script is discoverable, documents itself,
and keeps `AGENTS.md` shorter. `AGENTS.md` then just says `bash scripts/setup-dev.sh`.

**`scripts/setup-dev.sh` content** (must pass the pre-commit shellcheck hook, which
auto-detects shebangs; note also that the CI shellcheck step currently covers only
`run_gui.sh` and `scripts/type_baseline.sh` — the CI step must be expanded to include
`scripts/setup-dev.sh` so the file is also gated in CI):
```bash
#!/usr/bin/env bash
set -euo pipefail

# Verify pre-commit is available (requires pip install -e ".[dev,gui]" first)
if ! command -v pre-commit > /dev/null 2>&1; then
    echo "ERROR: pre-commit not found." >&2
    echo "Activate your venv or install dependencies first:" >&2
    echo "  pip install -e \".[dev,gui]\"" >&2
    exit 1
fi

pre-commit install
pre-commit install --hook-type pre-push
echo "Git hooks installed (pre-commit + pre-push)."
```
The shebang explicitly invokes `bash`, so `set -euo pipefail` is safe regardless of the
user's login shell (e.g. zsh on macOS). No `.git` guard needed — `pre-commit install`
already errors outside a git repo.

> **Effect of `setup-dev.sh`:** Running both install commands activates **all** existing
> pre-push hooks, not just the new `pip-audit` one — this includes `semgrep`,
> `basedpyright`, and `check-changelog` which are already defined in
> `.pre-commit-config.yaml` but silently skipped without `--hook-type pre-push`.
> The only net-new hook this plan adds is `pip-audit`; the rest are newly automatic.

**Windows parity:** The repo already ships `run_gui.bat` and `build_documentation.bat`,
so create `scripts/setup-dev.bat` for consistency. Use `call` to invoke pre-commit
(on Windows, calling a `.bat`/`.cmd` wrapper without `call` terminates the parent script
immediately, so `pre-commit install --hook-type pre-push` would never run without it):
```bat
@echo off
setlocal enabledelayedexpansion

where pre-commit >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] pre-commit not found.
    echo Activate your venv or install dependencies first:
    echo   pip install -e ".[dev,gui]"
    exit /b 1
)

call pre-commit install
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
call pre-commit install --hook-type pre-push
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
echo Git hooks installed (pre-commit + pre-push).
```
Document both launchers in `AGENTS.md`, pointing Windows users to `scripts\setup-dev.bat`
(not the raw two-command form).

### 2. Add pip-audit as a local pre-push hook

```yaml
- id: pip-audit
  name: pip-audit (dependency vulnerabilities)
  entry: pip-audit --desc on
  language: system
  pass_filenames: false
  always_run: true
  stages: [pre-push]
```

This matches the CI invocation (`pip-audit --desc on`). It scans the current
environment's installed packages, so it's fast for incremental runs.

> **Dependency note:** `language: system` means pre-commit runs whatever `pip-audit`
> is on `PATH`. `pip-audit` is already a `[dev]` extra in `pyproject.toml`, so
> `pip install -e ".[dev,gui]"` (the prerequisite step) guarantees it is present.
> No additional dependency changes are needed.
>
> **Pre-push strictness:** With `stages: [pre-push]`, a pip-audit CVE will block every
> push until the vulnerability is resolved or exempted. This matches the CI gate behavior.
> If a dev-dependency CVE needs a temporary exemption, use
> `pip-audit --ignore-vuln <VULN-ID>` in a local override or open an issue to track
> resolution. No `--ignore-vuln` file is added by default — treat unresolved CVEs as
> genuine blockers.

### 3. Update AGENTS.md

**Scope: amend the hook-install subsection only.** The surrounding content must be
**preserved**, including:
- The `pip install -e ".[docs,notebooks]"` line and extras/pyproject paragraph
- The semgrep network note ("fetches `p/owasp-top-ten` ... offline pushes will fail")
- The Windows `PYTHONUTF8=1` note
- The notebook/RDSR/GUI run commands

Replace only the "Optional local git hooks" block (identified by the text
`Optional local git hooks (fast subset of CI):`):

```markdown
Optional local git hooks (fast subset of CI):

```bash
# macOS / Linux
bash scripts/setup-dev.sh

# Windows
scripts\setup-dev.bat
```

To run hooks manually:

```bash
pre-commit run --all-files                           # pre-commit stage hooks
pre-commit run --hook-stage pre-push --all-files     # pre-push hooks (semgrep, pip-audit, basedpyright, changelog)
```
```

### 4. Update `.pre-commit-config.yaml` header comment

Replace the current header comment with one that reflects the new setup.
Keep both manual-run variants (the current header already has them; the
replacement must not drop the pre-push line). This consolidates the current
two per-hook pre-push examples into a single combined command — a deliberate
simplification that also covers the new `pip-audit` hook:

```yaml
# Local git hooks (fast subset of CI). Install once per clone:
#   pip install -e ".[dev,gui]"
#   bash scripts/setup-dev.sh          # macOS/Linux
#   scripts\setup-dev.bat              # Windows
#
# Run manually:
#   pre-commit run --all-files
#   pre-commit run --hook-stage pre-push --all-files
#
# CI runs the full matrix (pytest, basedpyright, bandit, pip-audit, gui-smoke, etc.).
```

### 5. Update TO_DO.md

No stale semgrep/pip-audit items remain in `TO_DO.md` — the OWASP items already
show semgrep as done and pip-audit is CI-only. **No edit required** unless a new
backlog entry is desired for `setup-dev.sh` discoverability.

### 6. Update SECURITY_TOOLS_CI_PLAN.md

Update the "Current state" table **in-place** in `SECURITY_TOOLS_CI_PLAN.md` once this
plan is implemented. Update only the `pip-audit` and `semgrep` rows; preserve all other
rows (`bandit`, `gitleaks`, `safety`, `shellcheck`) unchanged:

| Tool | Pre-commit | Pre-push | CI |
|------|-----------|----------|----|
| bandit | `pre-commit` stage | — | `static-analysis` job |
| pip-audit | — | ✅ (via `setup-dev.sh`) | `static-analysis` job |
| gitleaks | `pre-commit` stage | — | `.github/workflows/gitleaks.yml` |
| semgrep | — | ✅ (via `setup-dev.sh`) | `static-analysis` job |
| safety | — | — | `static-analysis` job (skipped without `SAFETY_API_KEY`) |
| shellcheck | `pre-commit` stage | — | `static-analysis` job |

No acceptance-criteria changes are needed in that plan (its criteria are
already met).

### 7. Update CHANGELOG.md

Add an entry under `[Unreleased]` (or the next version) covering:
- `scripts/setup-dev.sh` (+ `setup-dev.bat`) created — one-command hook setup for new clones
- `pip-audit` added as a pre-push hook alongside `semgrep` and `basedpyright`
- `AGENTS.md` Development setup simplified; both run variants documented

### 8. Archive this plan

This plan is **not yet listed** in `dev-docs/index.md`. The correct two-step workflow:

1. **When implementing:** add a row to the **Execution plans** table in `dev-docs/index.md`.
2. **When complete:** move this file to `dev-docs/plans/archive/ENABLE_SECURITY_HOOKS_DEFAULT_PLAN.md`
   and update `dev-docs/index.md` — remove the Execution plans row and add an Archived plans
   row marked `**Completed (YYYY-MM-DD)**`.

---

## File checklist

| File | Change |
|------|--------|
| `scripts/setup-dev.sh` | **Create** with shebang + `set -euo pipefail` + two `pre-commit install` calls |
| `scripts/setup-dev.bat` | **Create** Windows equivalent (`@echo off` + `call` prefix on both `pre-commit install` calls + `where pre-commit` pre-check) |
| `.github/workflows/ci.yml` | Expand shellcheck step to include `scripts/setup-dev.sh` |
| `.pre-commit-config.yaml` | Add `pip-audit` pre-push hook; update header comment (deliberate consolidation of pre-push run variants) |
| `AGENTS.md` | Replace hook-install block only (preserve semgrep network note + Windows `PYTHONUTF8=1` note + other content); show `scripts\setup-dev.bat` for Windows; show both manual-run commands |
| `dev-docs/HARNESS_ENGINEERING.md` | (a) Update hook-install commands block (~lines 291–292) to reference `setup-dev.sh`/`setup-dev.bat`; (b) add `pip-audit` row to the pre-push hook table (lines 312–316); (c) remove `pip-audit` from the "Not in local hooks" list (line 318) |
| `dev-docs/TO_DO.md` | No edit needed — no stale semgrep/pip-audit items remain |
| `dev-docs/plans/SECURITY_TOOLS_CI_PLAN.md` | Update "Current state" table: add `pip-audit` pre-push row; annotate semgrep row as now automatic |
| `CHANGELOG.md` | Add entry: `setup-dev.sh`/`.bat`, `pip-audit` pre-push hook, CI shellcheck expansion, `AGENTS.md` simplification |
| `dev-docs/index.md` | **Add row** under Execution plans now; move to Archived plans on completion |
| `dev-docs/plans/archive/ENABLE_SECURITY_HOOKS_DEFAULT_PLAN.md` | **Move** this plan here on completion |

---

## Acceptance criteria

- [ ] `bash scripts/setup-dev.sh` exits 0, prints success message, and installs both hook types; pre-commit shellcheck hook passes on it; CI shellcheck step also covers it
- [ ] `scripts/setup-dev.bat` exists with `call` prefix on both `pre-commit install` calls and a `where pre-commit` pre-check
- [ ] `pre-commit run pip-audit --hook-stage pre-push` passes on current code (no CVEs, or exits non-zero only for real findings)
- [ ] `pre-commit run semgrep --hook-stage pre-push --all-files` passes on current code
- [ ] _(Manual verification)_ A fresh-clone dev who runs `pip install -e ".[dev,gui]" && bash scripts/setup-dev.sh` sees semgrep + pip-audit fire on `git push`
- [ ] `AGENTS.md` hook-install block is updated (`scripts\setup-dev.bat` for Windows, both manual-run forms); semgrep network note and `PYTHONUTF8=1` note are preserved
- [ ] `.pre-commit-config.yaml` header retains both manual-run variants
- [ ] `dev-docs/HARNESS_ENGINEERING.md` hook-install lines updated to reference `setup-dev.sh`/`setup-dev.bat`
- [ ] `CHANGELOG.md` has an entry for this change
- [ ] This plan is archived under `dev-docs/plans/archive/` and `dev-docs/index.md` updated accordingly
