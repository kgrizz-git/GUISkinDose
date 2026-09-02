# Publishing to PyPI

> **Status:** This project is **not currently published to PyPI** by this fork. The
> `release.yml` workflow was inherited from upstream [PySkinDose](https://github.com/rvbCMTS/PySkinDose)
> and stays **inert** unless you deliberately create a GitHub Release. You do not need
> to do anything here for normal development.

For the full release map (changelog vs GitHub notes, SemVer, portable executables, checklist), see
[dev-docs/RELEASES_AND_DISTRIBUTION.md](dev-docs/RELEASES_AND_DISTRIBUTION.md).

**First GUISkinDose / `guiskindose` version is `1.0.0`** (new distribution identity; live package
is still GUISkinDose `25.2.0`). Do not publish `guiskindose` as `1.0.0`. Details:
[dev-docs/plans/GUISKINDOSE_RENAME_PLAN.md](dev-docs/plans/GUISKINDOSE_RENAME_PLAN.md).

## How releasing works now

`.github/workflows/release.yml` runs only on a **GitHub Release (`created`)** event. It:

1. Verifies the release commit is on `main` with a successful CI run.
2. Builds the sdist + wheel with `uv build` (pinned toolchain — no unpinned `pip install`).
3. Scans the built artifacts with grype (fails on actionable high/critical CVEs).
4. Publishes to PyPI via **Trusted Publishing (OIDC)** — no stored API token.

The publish step authenticates with a short-lived OpenID Connect token minted by GitHub
Actions (`permissions: id-token: write`), so there is **no `PYPI_*` secret to leak or rotate**.

## One-time PyPI setup (only if you ever want to publish)

Trusted Publishing needs a one-time registration on PyPI so it will trust this repo:

1. Sign in at <https://pypi.org> (create an account if needed).
2. **If the `guiskindose` project does not exist on PyPI yet**, add a *pending* publisher:
   PyPI → your account → **Publishing** → *Add a new pending publisher* with
   - PyPI Project Name: `guiskindose`
   - Owner: `kgrizz-git`
   - Repository name: `GUISkinDose`
   - Workflow name: `release.yml`
   - Environment: *(leave blank)*
3. **If the project already exists**, do the same under
   Project → **Settings → Publishing → Add a trusted publisher**.
4. **One-time cleanup of the legacy token.** Removing `password:` from the workflow does *not*
   delete or revoke the old credential. After a first release confirms Trusted Publishing works,
   delete the GitHub repository secret `PYPI_DEPLOY_API_KEY` (Settings → Secrets and variables →
   Actions) **and** revoke that token on PyPI (Account → API tokens). Only after this is the
   "no `PYPI_*` secret" state actually true.

That's it — no long-lived secret once the cleanup above is done. To cut a release afterward: bump
the version in `pyproject.toml`, fold `CHANGELOG.md`, write **user-facing** GitHub Release notes
(see [RELEASES_AND_DISTRIBUTION.md](dev-docs/RELEASES_AND_DISTRIBUTION.md) — do not dump every CI/refactor
bullet), create the GitHub Release, and the workflow builds, scans, and publishes.

## If you never plan to publish

You can safely leave this as-is (the workflow never runs on its own), or delete
`.github/workflows/release.yml` and this file. Nothing else in the project depends on them.
