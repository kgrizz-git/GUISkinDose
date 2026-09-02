# Governance

GUISkinDose is maintained by a **solo maintainer** on a best-effort basis.

| Role | Who | Notes |
|---|---|---|
| Maintainer | [@kgrizz-git](https://github.com/kgrizz-git) | Release, governance, and merge decisions for this fork |
| Upstream authors | Max Hellström and PySkinDose contributors | Original work; credited in `LICENSE` and history |

## Decisions

- Product direction is decided by the maintainer after considering Issues and
  Discussions.
- The maintainer is **open to ideas and considering submissions** via Issues and
  Discussions. Prefer those channels over cold pull requests; a PR is welcome
  when the maintainer explicitly invites one. See [CONTRIBUTING.md](CONTRIBUTING.md).
- The maintainer’s own changes still land through pull requests into `main`
  (branch rules).
- Calculation-affecting, privacy, security, and release changes should be
  documented in the PR and `CHANGELOG.md`. User-facing GitHub Release notes are
  a shorter subset — see [RELEASES_AND_DISTRIBUTION.md](dev-docs/RELEASES_AND_DISTRIBUTION.md).
- There is no formal steering committee.

## Releases

Releases are maintainer-triggered. See
[dev-docs/RELEASES_AND_DISTRIBUTION.md](dev-docs/RELEASES_AND_DISTRIBUTION.md) (hub),
[PUBLISHING.md](PUBLISHING.md) (PyPI), and
[dev-docs/FORK_MAINTAINER_GUIDE.md](dev-docs/FORK_MAINTAINER_GUIDE.md). The
project may or may not publish to PyPI depending on maintainer readiness; the
release workflow stays inert until a GitHub Release is created.

Record calculation-, privacy-, security-, and release-affecting work in
`CHANGELOG.md`. GitHub Release notes should stay **user-facing** (see the hub);
do not paste every CI/refactor changelog bullet into the Release body.

## Changing maintainership

If maintainership needs to change, update this file, [SUPPORT.md](SUPPORT.md),
[CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md),
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) enforcement contact, and package
maintainer metadata in `pyproject.toml` in the same change.
