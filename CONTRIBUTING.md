# Contributing to MyPySkinDose

Thanks for your interest in this fork of
[PySkinDose](https://github.com/rvbCMTS/PySkinDose).

Support is best-effort. Please read [SUPPORT.md](SUPPORT.md) and
[SECURITY.md](SECURITY.md) before contacting the project.

## Ideas and submissions welcome — prefer Issues / Discussions

I'm **open to hearing ideas and considering submissions** through GitHub
[Issues](https://github.com/kgrizz-git/MyPySkinDose/issues) and
[Discussions](https://github.com/kgrizz-git/MyPySkinDose/discussions). Please
describe the idea, bug, or proposed change there (synthetic / de-identified
examples only — no real patient data).

For the foreseeable future, please **do not open a cold pull request** expecting
a review queue. This is a solo-maintained project. If a submission looks like a
good fit, the maintainer may follow up and **invite** a PR or adopt the idea
another way.

Do not treat an unsolicited PR as the primary contribution path unless you were
asked to open one.

## Intended use (read first)

MyPySkinDose estimates peak skin dose and 3D skin dose maps for research,
education, development, and institutional quality-assurance workflows. It is
**not FDA-cleared** (or otherwise certified) as a medical device. Physicists and
physicians remain responsible for reviewing results and for any patient-care
decisions. Do not treat outputs as independently validated clinical truth.

## Privacy — what you must never submit

Do **not** attach, paste, commit, or upload:

- Real patient data, PHI/PII, or identified screenshots
- Raw clinical RDSR / DICOM files from live systems
- Credentials, API tokens, or private/institutional URLs
- Full unredacted logs that include identifiers, source filenames, or absolute paths

Use synthetic fixtures or documented de-identified examples only. Mistaken
commits of patient data are incidents — stop sharing, get help, and follow
[dev-docs/PRIVACY_INCIDENT_RESPONSE.md](dev-docs/PRIVACY_INCIDENT_RESPONSE.md).

## How to reach the maintainer on GitHub

| Channel | Use for |
|---|---|
| [Issues](https://github.com/kgrizz-git/MyPySkinDose/issues) | Bugs and concrete feature requests (forms required) |
| [Discussions](https://github.com/kgrizz-git/MyPySkinDose/discussions) | Questions, ideas, and contribution proposals |
| [Private vulnerability reporting](https://github.com/kgrizz-git/MyPySkinDose/security/advisories/new) | Security only — see [SECURITY.md](SECURITY.md) |
| Profile [@kgrizz-git](https://github.com/kgrizz-git) | Public profile link only — GitHub has **no** general private DM inbox |

Mentioning `@kgrizz-git` in an Issue or Discussion notifies the maintainer.
There is no separate GitHub messaging app for arbitrary users.

## Local development (forks / invited PRs)

If you are experimenting locally, or the maintainer has invited a PR:

```bash
# Recommended: uv
uv sync --all-extras

# Or pip
pip install -e ".[dev,gui]"
```

Optional local hooks:

```bash
bash scripts/setup-dev.sh   # macOS / Linux
scripts\setup-dev.bat       # Windows
```

Shared agent/maintainer workflow rules live in
[AGENTS.md](AGENTS.md) and [dev-docs/AGENT_PLAYBOOK.md](dev-docs/AGENT_PLAYBOOK.md).

When a PR is **explicitly invited**:

1. Start from current `main` (or a dedicated worktree).
2. Create a focused branch (`feat/…`, `fix/…`, `docs/…`).
3. Open a pull request into `main` and fill in the PR template.
4. Run the relevant checks (examples below).

```bash
python scripts/check_doc_freshness.py
python scripts/check_file_sizes.py
python scripts/check_changelog.py
pre-commit run --all-files
python -m pytest tests/ -q
```

Update [CHANGELOG.md](CHANGELOG.md) for user- or maintainer-visible behavior.
Version bumps belong in `pyproject.toml` at release time.

## Upstream attribution

Preserve the MIT license and upstream copyright. Credit original authors; do not
rebrand upstream code as solely authored here. See
[dev-docs/FORK_MAINTAINER_GUIDE.md](dev-docs/FORK_MAINTAINER_GUIDE.md).

General-purpose fixes may be offered **upstream** as a narrow PR against current
upstream `master`, without asking them to adopt fork-only product history. That
is separate from contributing to *this* fork.

## Code of conduct

Participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
