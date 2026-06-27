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

> **Windows note:** The project targets Windows, macOS, and Linux. `setup-dev.sh`
> covers macOS/Linux. For Windows devs, document the equivalent PowerShell/cmd
> one-liner in `AGENTS.md` alongside the script reference:
> ```
> pre-commit install && pre-commit install --hook-type pre-push
> ```
> A `scripts/setup-dev.bat` is optional but not required if `AGENTS.md` shows both paths.

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

### 3. Update AGENTS.md

The "Development setup" section:

```markdown
## Development setup

```bash
pip install -e ".[dev,gui]"
bash scripts/setup-dev.sh   # installs git hooks (pre-commit + pre-push)
```

Optionally run hooks manually:

```bash
pre-commit run --all-files
```
```

### 4. Update `.pre-commit-config.yaml` header comment

Replace the current header comment with one that reflects the new setup:

```yaml
# Local git hooks. Install once per clone:
#   pip install -e ".[dev,gui]"
#   bash scripts/setup-dev.sh
#
# Run manually:
#   pre-commit run --all-files
#
# CI runs the full matrix (pytest, basedpyright, bandit, pip-audit, gui-smoke, etc.).
```

### 5. Update TO_DO.md

No stale semgrep/pip-audit items remain in `TO_DO.md` — the OWASP items already
show semgrep as done and pip-audit is CI-only. **No edit required** unless a new
backlog entry is desired for `setup-dev.sh` discoverability.

### 5b. Update SECURITY_TOOLS_CI_PLAN.md

Update the "Current state" table in `SECURITY_TOOLS_CI_PLAN.md` to add a
`pip-audit` pre-push row once this plan is implemented:

| Tool | Pre-commit | Pre-push | CI |
|------|-----------|----------|----|
| pip-audit | — | ✅ (via `setup-dev.sh`) | `static-analysis` job |

No acceptance-criteria changes are needed in that plan (its criteria are
already met).

### 6. Update CHANGELOG.md

Add an entry under `[Unreleased]` (or the next version) covering:
- `scripts/setup-dev.sh` created — one-command hook setup for new clones
- `pip-audit` added as a pre-push hook alongside `semgrep` and `basedpyright`
- `AGENTS.md` Development setup simplified

### 7. Archive this plan

Once all acceptance criteria pass, move this file to
`dev-docs/plans/archive/ENABLE_SECURITY_HOOKS_DEFAULT_PLAN.md` and update
`dev-docs/index.md`:
- Remove the row from **Execution plans**
- Add a row to **Archived plans** marked `**Completed**` with the completion date

---

## File checklist

| File | Change |
|------|--------|
| `scripts/setup-dev.sh` | **Create**: `pre-commit install && pre-commit install --hook-type pre-push` |
| `.pre-commit-config.yaml` | Add `pip-audit` pre-push hook; update header comment |
| `AGENTS.md` | Point to `scripts/setup-dev.sh`; add Windows one-liner note |
| `dev-docs/TO_DO.md` | No edit needed — no stale semgrep/pip-audit items remain |
| `dev-docs/plans/SECURITY_TOOLS_CI_PLAN.md` | Update "Current state" table to add `pip-audit` pre-push row |
| `CHANGELOG.md` | Add entry: `setup-dev.sh`, `pip-audit` pre-push hook, `AGENTS.md` simplification |
| `dev-docs/index.md` | Move row from Execution plans → Archived plans (`**Completed**`) |
| `dev-docs/plans/archive/ENABLE_SECURITY_HOOKS_DEFAULT_PLAN.md` | **Move** this plan here on completion |

---

## Acceptance criteria

- [ ] `bash scripts/setup-dev.sh` installs both `pre-commit` and `pre-push` hooks without errors
- [ ] `pre-commit run pip-audit --hook-stage pre-push --all-files` passes on current code (no CVEs, or exits non-zero only for real findings)
- [ ] `pre-commit run semgrep --hook-stage pre-push --all-files` passes on current code
- [ ] A fresh-clone dev who runs only `pip install -e ".[dev,gui]" && bash scripts/setup-dev.sh` has semgrep + pip-audit fire on `git push`
- [ ] `AGENTS.md` Development setup is updated: `bash scripts/setup-dev.sh` replaces the two-command hook install; Windows one-liner is noted
- [ ] `CHANGELOG.md` has an entry for this change
- [ ] This plan is archived under `dev-docs/plans/archive/` and `dev-docs/index.md` updated accordingly
