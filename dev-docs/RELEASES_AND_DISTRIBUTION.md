# Releases and distribution

_Hub for how GUISkinDose is versioned, published, and (optionally) packaged for end users._  
_Created: 2026-07-30._

This page is the map. Detailed how-tos stay in the linked sources of truth.

## Distribution channels

| Channel | Status | Source of truth |
|---------|--------|-----------------|
| **Python package** (`pip install guiskindose`) | Primary path; **not yet published** to PyPI by this fork | [PUBLISHING.md](../PUBLISHING.md), `.github/workflows/release.yml` |
| **GitHub Release** (tag + notes + optional assets) | Maintainer-triggered; drives the PyPI workflow when a Release is created | This page § Cutting a release; [FORK_MAINTAINER_GUIDE.md](FORK_MAINTAINER_GUIDE.md) §6 |
| **Source / editable install** | Default for developers and most users today | [README.md](../README.md), [AGENTS.md](../AGENTS.md) |
| **Portable GUI executable** (PyInstaller / `nicegui-pack`) | Research / deferred — no freeze pipeline yet | [references/PORTABLE_EXECUTABLE_PACKAGING.md](references/PORTABLE_EXECUTABLE_PACKAGING.md) |

**Non-goals:** a single binary for all OSes; committing built executables to git; wrapping the stack for the JVM (call CLI/API from Java instead — see the portable-exec note).

## Changelogs vs Maintenance Log

These serve different audiences.

| Artifact | Audience | What goes in it |
|----------|----------|-----------------|
| **`CHANGELOG.md`** | Users | Curated **notable** user-facing changes for the version: features, fixes, UI updates, breaking changes. Keep a Changelog categories (`Added` / `Changed` / `Fixed` / …). |
| **`dev-docs/MAINTENANCE_LOG.md`** | Maintainers/contributors | Under-the-hood work: significant CI/harness/refactor/privacy work, testing, and documentation updates that do not directly affect end-users. |
| **GitHub Release notes** | People upgrading or downloading the release | **User-facing** summary: what they can do differently, upgrade steps, known limits, credits. Prefer features, bug fixes, and breaking changes. Generated from `CHANGELOG.md`. |

**Do not paste the entire Unreleased CHANGELOG into GitHub Release notes.** CI cleanups, coverage gates, Sonar remediations, and pure refactors belong in `dev-docs/MAINTENANCE_LOG.md` so the repo history stays honest, and they are usually noise for end users.

### Suggested Release notes recipe

1. Move `[Unreleased]` into a new versioned section in `CHANGELOG.md` (Keep a Changelog).
2. Draft GitHub Release body from that section:
   - Lead with **Added** / **Fixed** / user-visible **Changed** / **Removed** / **Security**.
3. Add upgrade notes, intended-use reminder (not FDA-cleared), and any privacy/validation caveats.

`GOVERNANCE.md` still expects calculation-, privacy-, security-, and release-affecting work to be recorded in `CHANGELOG.md` (or `MAINTENANCE_LOG.md` as appropriate).

## Versioning

- **SemVer** via `pyproject.toml` (source of truth for the package version).
- **Live package today:** GUISkinDose / `guiskindose` `1.0.0` (new distribution identity;
  formerly MyPySkinDose `25.2.0` / a fork of PySkinDose). Not yet published to PyPI.
- **First GUISkinDose / `guiskindose` version (locked): `1.0.0`.** New distribution identity;
  not `26.0.0`, not a patch on `25.2.0`, and not an imitation of upstream PySkinDose.
  Changelog `[1.0.0]` and GitHub Release notes must say it was formerly MyPySkinDose `25.2.0` / a fork
  of PySkinDose. Details: [plans/archive/GUISKINDOSE_RENAME_PLAN.md](plans/archive/GUISKINDOSE_RENAME_PLAN.md).
- Bump at release time (not on every docs PR). Document SemVer impact in Unreleased notes when shipping user-visible library/GUI changes.
- `scripts/check_changelog.py` requires an Unreleased touch when `src/` or `tests/` change (pre-push).

## Cutting a release (checklist)

Use a release PR or written checklist. Condensed from [FORK_MAINTAINER_GUIDE.md](FORK_MAINTAINER_GUIDE.md) §6:

1. Compare/sync upstream intent; record in the fork guide if you sync.
2. Confirm `main` is green for the exact commit you will tag.
3. Bump `pyproject.toml` version; fold `CHANGELOG.md` `[Unreleased]` into `## [x.y.z]`; update citation/support bits if needed.
4. Run full tests and documented privacy, secret, dependency, license, type, build, and doc checks.
5. Locally `uv build` (or equivalent); inspect wheel/sdist contents.
6. Privacy: no identifiers, private paths, or unapproved assets in fixtures, logs, or artifacts.
7. Create a **GitHub Release** on that commit (user-facing notes per above). That event runs `release.yml`.
8. Verify workflow: privacy gates → build → grype → PyPI publish (only after Trusted Publisher is registered — see `PUBLISHING.md`).

Until the first Trusted Publisher registration, the publish step is expected to fail rather than publish silently.

## Portable executables (deferred)

Frozen desktop apps are an optional future channel for non-Python users. Feasibility, bundle requirements (phantoms, `corrections.db`, help), size, and Java non-goals are documented in
[references/PORTABLE_EXECUTABLE_PACKAGING.md](references/PORTABLE_EXECUTABLE_PACKAGING.md). Tracked as Deferred in [TO_DO.md](TO_DO.md). Do not start a freeze pipeline until product OS priority and maintainer smoke bandwidth are explicit.

## Related docs

| Doc | Role |
|-----|------|
| [PUBLISHING.md](../PUBLISHING.md) | PyPI Trusted Publishing detail |
| [plans/archive/GUISKINDOSE_RENAME_PLAN.md](plans/archive/GUISKINDOSE_RENAME_PLAN.md) | In-repo package rename; first `guiskindose` version `1.0.0` |
| [plans/archive/GUISKINDOSE_GITHUB_RENAME_PLAN.md](plans/archive/GUISKINDOSE_GITHUB_RENAME_PLAN.md) | GitHub fork → `GUISkinDose`, then SonarCloud, then live URLs |
| [FORK_MAINTAINER_GUIDE.md](FORK_MAINTAINER_GUIDE.md) | Full maintainer release + monthly ops rhythm |
| [PRIVACY_INCIDENT_RESPONSE.md](PRIVACY_INCIDENT_RESPONSE.md) | Privacy release / history audit checklist |
| [HARNESS_ENGINEERING.md](HARNESS_ENGINEERING.md) | CI gates that must stay green before release |
| [GOVERNANCE.md](../GOVERNANCE.md) | Who owns releases |
| [CHANGELOG.md](../CHANGELOG.md) | Notable changes per version |
