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

The matrix `build` job still runs non-GUI only (`--ignore=tests/gui`, `fail-under=65`). PRs also get
`coverage-pr` (combined non-GUI+GUI ≥80% plus `diff-cover` ≥80% vs the PR base). `gui-smoke` remains the
dedicated NiceGUI job; the combined coverage pass is for Sonar (and Codecov on `main`).

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

SonarQube findings require ordinary triage, but SonarQube does not replace Ruff, Basedpyright, Bandit, Semgrep,
HoundDog, dependency audits, tests, or the privacy admission controls. Keep a SonarQube change in a separate commit or
PR when it changes analysis scope, quality profiles, or gate policy independently of application behavior.
