# Local SonarQube Community Build

SonarQube is an optional, local-only quality and security second opinion. It is not part of public CI and must not be
configured to send this repository to SonarCloud or another remote server without a separate review.

The tracked [`../sonar-project.properties`](../sonar-project.properties) file contains only project analysis settings;
it contains no server URL or token. The runner defaults to `http://localhost:9000`, accepts `SONAR_HOST_URL` and
`SONAR_TOKEN` from the local environment, and refuses a non-loopback host unless `--allow-remote` is explicit.

## Server setup and upgrades

[`../compose.sonarqube.yaml`](../compose.sonarqube.yaml) runs the server with PostgreSQL. The embedded H2 database
does not support upgrades, so a server started with a bare `docker run sonarqube:community` can fail its migration
and lose projects and tokens. The compose file also pins the port to `127.0.0.1` and keeps data in named volumes,
so recreating the server cannot drop them by accident. It holds no secrets: set `SONAR_DB_PASSWORD` in `.env`.

One server serves every repository on the machine. Keep a single stack running; other repositories only need
their own `sonar.projectKey`, `SONAR_HOST_URL`, and token.

```bash
# macOS with Colima: brew install docker-compose, then add
#   "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"]  to ~/.docker/config.json
docker compose -f compose.sonarqube.yaml up -d
```

SonarQube's embedded Elasticsearch needs `vm.max_map_count` of at least 524288 and `nofile` of at least 131072 on the
Docker host (the Linux VM under Colima or Docker Desktop). If the server container exits during startup, check those
limits against SonarSource's Docker requirements.

Moving from an old H2 container: stop it (`docker stop sonarqube`) but keep it and its volumes as a fallback, start
the stack, log in at `http://localhost:9000` (default `admin`/`admin`, change it), create the projects, and put a
new token in each repository's `.env`. Remove the old container and its volumes once the new server works.

The runner checks at most weekly for a newer server image or scanner and prints a note; it never updates anything
(`--check-updates` forces the check, `--no-update-check` skips it). To upgrade the server, back up first:

```bash
docker compose -f compose.sonarqube.yaml exec -T db pg_dump -U sonar sonar > tmp/sonarqube-backup.sql
# Edit compose.sonarqube.yaml: set the new <version>-community tag and its digest.
docker compose -f compose.sonarqube.yaml up -d
```

The backup holds the server's user accounts and token hashes. Keep it under the gitignored `tmp/` directory, never
share it, and delete it once the upgrade works.

Both images are pinned to a release tag plus its immutable digest, so nothing changes until the pin is edited. The
digest for a tag is shown on Docker Hub, or by `docker buildx imagetools inspect sonarqube:<tag>`.

The server migrates its database on start. Open `http://localhost:9000/setup` if it asks for a manual upgrade step.
Rules ship inside the server's analyzers, so upgrading the server updates the rules.

## Coverage for Sonar (two-pass: non-GUI + GUI)

SonarCloud CI uploads a combined `coverage.xml` that includes NiceGUI tests so GUI modules count toward
new-code coverage. Locally, use the runner's explicit coverage mode so every quality-gate analysis has a current
combined report:

```bash
# Requires the dev and gui extras (pytest-cov, pytest-xdist, and NiceGUI tests).
python scripts/run_sonarqube_local.py --generate-coverage
```

With `uv`:

```bash
uv sync --extra dev --extra gui --locked
uv run --no-sync python scripts/run_sonarqube_local.py --generate-coverage
```

Without `--generate-coverage`, the runner accepts an existing `coverage.xml` only when it is newer than the Python
files under `src/`, `scripts/`, and `tests`; otherwise it stops with a privacy-safe regeneration instruction instead
of submitting a misleading zero-coverage analysis. Coverage generation mirrors CI: parallel non-GUI tests followed
by serial GUI tests with appended coverage.

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

### Freshness vs quality gate vs triage (do not conflate)

Three separate checks apply when `SONAR_FRESHNESS_GATE=1`:

| Check | What enforces it | Pass condition |
| --- | --- | --- |
| **Freshness** | `check_sonar_freshness.py` on commit/push | A successful local scan (`run_sonarqube_local.py` exit 0) re-anchored `tmp/sonar-state.json` within the commit budget |
| **Quality gate** | `run_sonarqube_local.py` (waits on the server QG) | Server reports gate **OK** (e.g. `new_violations` on new code ≤ 0, coverage thresholds met) |
| **Triage** | Human / agent policy (`AGENT_PLAYBOOK.md`) | Review **New Code** issues (bugs, vulnerabilities, hotspots) even when the gate is green |

A **failed quality gate** means the scan did **not** succeed: `last_scan_commit` is **not** updated, freshness still
blocks push, and you must **fix or explicitly get user approval to bypass** — not set `SONAR_FRESHNESS_GATE=0` or
`--no-verify` to push anyway. After a red gate, read the runner summary or SonarQube **New Code** / **Issues** for
the exact rule keys and paths (`new_violations` > 0 is the usual blocker on the default gate).

Before pushing (opt-in gate on): (1) run `python scripts/run_sonarqube_local.py --generate-coverage` until exit 0;
(2) optionally compare timestamped dumps from `dump_sonar_issues.py` (identities, not only totals); (3) triage bugs
and vulnerabilities in New Code even if counts look unchanged.

The pre-push hook prints a triage reminder when the opt-in gate is enabled; it does **not** compare issue counts or
run the quality gate for you.

### SonarCloud (main CI + local API check)

Protected-`main` CI runs `sonar-scan` when `SONAR_PROTECTED_MAIN_ENABLED=true` and `SONAR_TOKEN` is set in GitHub
secrets; the job waits on the cloud quality gate.

**Local Docker SonarQube and SonarCloud are not the same snapshot.** A green local gate means the working tree passed
your loopback server; SonarCloud still reflects the **last cloud analysis** (usually a `main` push). An open PR does
not update cloud new-code issues until that branch is analyzed (typically after merge and `sonar-scan`).

To inspect cloud gate status and new-code issues without the Docker server:

```bash
python scripts/check_sonarcloud_gate.py
python scripts/check_sonarcloud_gate.py --fail-on-error   # exit 1 when gate status != OK
```

Authentication uses `SONAR_CLOUD_TOKEN` or `SONAR_TOKEN` from the environment or repo-local `.env` (exported
`SONAR_CLOUD_TOKEN` wins for this script; see `.env.example`). Tokens are never printed. The report lists failing gate
conditions (for example `new_reliability_rating` is driven by **new-code bugs**, not only smell `new_violations`) and
a sample of unresolved `inNewCodePeriod` issues.

For a full unresolved-issue dump to gitignored `tmp/`, use `dump_sonar_issues.py --host-url https://sonarcloud.io
--allow-remote`.

| Helper | Default host | Token resolution |
| --- | --- | --- |
| `run_sonarqube_local.py` | `http://localhost:9000` | `SONAR_TOKEN` (export wins, else `.env`) |
| `dump_sonar_issues.py` | loopback | `SONAR_TOKEN`, else `SONAR_CLOUD_TOKEN` |
| `check_sonarcloud_gate.py` | `https://sonarcloud.io` | `SONAR_CLOUD_TOKEN`, else `SONAR_TOKEN` |

`.env` duplicate keys use **last assignment wins**. Loopback helpers also read `SONAR_HOST_URL` from the environment
(overridable via `--host-url`); the local runner falls back to `.env` so `python scripts/run_sonarqube_local.py` works
without an export dance.

```bash
# Enable the gate, then scan to create the baseline state:
#   SONAR_FRESHNESS_GATE=1 in .env
python scripts/run_sonarqube_local.py --generate-coverage  # start the local server first
```

## Timestamped issue dumps

`scripts/dump_sonar_issues.py` queries unresolved issues for the `sonar.projectKey` in
`sonar-project.properties` and writes `tmp/sonar-issues/<UTC>.json` plus a `.md` summary, with stable
`tmp/sonar-latest-issues.*` pointers the gate references. Dumps older than 30 days are pruned (always keeping
the 5 most recent). Tokens come from `SONAR_TOKEN` or `SONAR_CLOUD_TOKEN` (see table above) and are never printed;
non-200 API responses abort without touching state. When a state file exists, issue counts are refreshed in
place without changing `last_scan_commit`. A non-loopback `--allow-remote` host must use HTTPS, and the credentialed request refuses
redirects so the token is never forwarded to another URL. For SonarCloud snapshots, see **SonarCloud (main CI + local
API check)** above.

```bash
python scripts/dump_sonar_issues.py
python scripts/dump_sonar_issues.py --host-url https://sonarcloud.io --allow-remote
```

For a local comparison, keep the previous timestamped dump and run the command after the new scan. Compare issue
identities, not only totals: a resolved issue can offset a newly introduced bug or vulnerability without changing
the count. Dumps stay under gitignored `tmp/`; do not commit or paste raw issue details into a PR.

## Project version

The runner passes `-Dsonar.projectVersion` from the `version` in `pyproject.toml` so local analyses are labeled
with the working-tree release. The scanner omits the label when the version cannot be read; no action needed.

SonarQube findings require ordinary triage, but SonarQube does not replace Ruff, Basedpyright, Bandit, Semgrep,
HoundDog, dependency audits, tests, or the privacy admission controls. Keep a SonarQube change in a separate commit or
PR when it changes analysis scope, quality profiles, or gate policy independently of application behavior.
