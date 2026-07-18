# Local SonarQube Community Build

SonarQube is an optional, local-only quality and security second opinion. It is not part of public CI and must not be
configured to send this repository to SonarCloud or another remote server without a separate review.

The tracked [`../sonar-project.properties`](../sonar-project.properties) file contains only project analysis settings;
it contains no server URL or token. The runner defaults to `http://localhost:9000`, accepts `SONAR_HOST_URL` and
`SONAR_TOKEN` from the local environment, and refuses a non-loopback host unless `--allow-remote` is explicit.

Generate current coverage first when coverage metrics are wanted:

```bash
coverage run -m pytest --ignore=tests/gui
coverage xml
python scripts/run_sonarqube_local.py
```

The runner suppresses raw scanner output because it can contain filesystem paths or source excerpts. It waits for the
quality gate by default and records only status, time, counts, and content/configuration/version digests below
`.git/sonarqube/last-run.json`. That receipt is clone-local and never tracked. `.scannerwork/`, `.sonar/`, and an
optional `sonar-project.properties.local` are protected ignored paths and may not be committed.

SonarQube findings require ordinary triage, but SonarQube does not replace Ruff, Basedpyright, Bandit, Semgrep,
HoundDog, dependency audits, tests, or the privacy admission controls. Keep a SonarQube change in a separate commit or
PR when it changes analysis scope, quality profiles, or gate policy independently of application behavior.
