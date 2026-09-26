# Local SonarQube Community Build

SonarQube is an optional, local-only quality and security second opinion. It is not part of public CI and must not be
configured to send this repository to SonarCloud or another remote server without a separate review.

The tracked [`../sonar-project.properties`](../sonar-project.properties) file contains only project analysis settings;
it contains no server URL or token. The runner defaults to `http://localhost:9000`, accepts `SONAR_HOST_URL` and
`SONAR_TOKEN` from the local environment, and refuses a non-loopback host unless `--allow-remote` is explicit.

## Coverage for Sonar (two-pass: non-GUI + GUI)

SonarCloud CI uploads a combined `coverage.xml` that includes NiceGUI tests so GUI modules count toward
new-code coverage. Locally, mirror the CI recipe when coverage metrics are wanted:

```bash
# Prefer the project venv / uv environment with the gui extra installed.
coverage erase
coverage run -m pytest --ignore=tests/gui
coverage run --append -m pytest tests/gui/
coverage xml
python scripts/run_sonarqube_local.py
```

With `uv`:

```bash
uv sync --extra dev --extra gui --locked
uv run --no-sync coverage erase
uv run --no-sync coverage run -m pytest --ignore=tests/gui
uv run --no-sync coverage run --append -m pytest tests/gui/
uv run --no-sync coverage xml
```

The matrix `build` job runs the non-GUI suite for test-pass only (`--ignore=tests/gui -n auto`, no
coverage gate). Coverage uses a single 80% standard: PRs get `coverage-pr` (combined non-GUI+GUI
≥80% plus `diff-cover` ≥80% vs the PR base), and `sonar-scan` enforces ≥80% new-code coverage on
`main`. `gui-smoke` remains the dedicated NiceGUI job; the combined coverage pass is for Sonar on `main`.

## README Quality Gate badge

On the plain Free / read-only **Sonar way** quality gate, Coverage on New Code stays at **80%** and cannot be
lowered (**confirmed 2026-07-25** — Free tier cannot edit the gate). The public README Quality Gate badge was
**removed** so the repo does not advertise a failed gate we cannot tune. Sonar analysis remains in CI.
**Automatic Analysis was disabled** so CI-based scans are authoritative. Re-add the badge only when
`alert_status=OK` is sustainable, or when a custom gate (OSS/Team/Enterprise) allows a temporary lower
threshold (see `plans/SONAR_PRIVACY_GATED_SCANS_PLAN.md` B2).

The runner suppresses raw scanner output because it can contain filesystem paths or source excerpts. It waits for the
quality gate by default and records only status, time, counts, and content/configuration/version digests below
`.git/sonarqube/last-run.json`. That receipt is clone-local and never tracked. `.scannerwork/`, `.sonar/`, and an
optional `sonar-project.properties.local` are protected ignored paths and may not be committed.

## Freshness gate (opt-in local hooks)

The commit hook blocks once pending commits since the last successful local scan reach `SONAR_GATE_MAX_COMMITS`
(default 10, counting the in-flight commit); the push hook blocks on any commit since the last scan. Both are
enforced by `scripts/check_sonar_freshness.py` (via `scripts/run_sonar_freshness_check.sh`) and stay silent
unless `SONAR_FRESHNESS_GATE=1` is set in the repo-local `.env` (see `.env.example`). The gate keys off
`tmp/sonar-state.json`, which `scripts/run_sonarqube_local.py` rewrites after each successful analysis (failures
leave the prior state so the budget is not reset by a red scan). After history rewrites (rebase/amend) the gate
blocks until a fresh scan re-anchors the state. Note: the push stage evaluates the checked-out HEAD, not the
pushed refspecs — pushing another branch from this checkout is judged against HEAD's freshness.

`SONAR_TOKEN` is read from the exported environment or the repo-local `.env` by all three helpers
(exported wins; the file is parsed, never sourced). `SONAR_HOST_URL` comes from the exported environment
in the gate and dump helpers (overridable per-invocation via `--host-url`); the runner additionally falls
back to `.env`, so a plain `python scripts/run_sonarqube_local.py` works in any shell on any OS — no
`export` dance needed.

```bash
# Enable the gate, then scan to create the baseline state:
#   SONAR_FRESHNESS_GATE=1 in .env
colima start default && python scripts/run_sonarqube_local.py
```

## Timestamped issue dumps

`scripts/dump_sonar_issues.py` queries unresolved issues for the `sonar.projectKey` in
`sonar-project.properties` and writes `tmp/sonar-issues/<UTC>.json` plus a `.md` summary, with stable
`tmp/sonar-latest-issues.*` pointers the gate references. Dumps older than 30 days are pruned (always keeping
the 5 most recent). The token comes from `SONAR_TOKEN` (exported or repo-local `.env`) and is never printed;
non-200 API responses abort without touching state. When a state file exists, issue counts are refreshed in
place without changing `last_scan_commit`. A non-loopback `--allow-remote` host must use HTTPS, and the credentialed request refuses
redirects so the token is never forwarded to another URL.

```bash
python scripts/dump_sonar_issues.py
```

## Project version

The runner passes `-Dsonar.projectVersion` from the `version` in `pyproject.toml` so local analyses are labeled
with the working-tree release. The scanner omits the label when the version cannot be read; no action needed.

SonarQube findings require ordinary triage, but SonarQube does not replace Ruff, Basedpyright, Bandit, Semgrep,
HoundDog, dependency audits, tests, or the privacy admission controls. Keep a SonarQube change in a separate commit or
PR when it changes analysis scope, quality profiles, or gate policy independently of application behavior.
