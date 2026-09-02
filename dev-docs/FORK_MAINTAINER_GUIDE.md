# Maintaining an ethical, healthy fork of PySkinDose

_Reviewed: 2026-07-26. This is practical maintainer guidance, not legal, regulatory, or medical-device advice._

## Purpose

MyPySkinDose is a continuing, independent fork of
[PySkinDose](https://github.com/rvbCMTS/PySkinDose). A fork may evolve
independently, but responsible stewardship means clearly crediting its origin,
preserving the upstream license, respecting contributors and users, and keeping
a reliable release process.

This guide explains the habits and GitHub settings that make that manageable,
especially for a solo or new maintainer. It also records review findings for
the main branch so future maintainers can distinguish an intentional decision
from an accidental omission.

## Review snapshot

The following are already in good shape:

| Area | Observed state | Why it matters |
|---|---|---|
| Fork relationship | GitHub identifies MyPySkinDose as a fork of rvbCMTS/PySkinDose. | Preserves the connection to the original project and its history. |
| Git remotes | origin points to MyPySkinDose and upstream points to PySkinDose. | This is the conventional remote layout for a maintained fork. |
| Upstream divergence | 2026-07-26: main was 346 commits ahead of upstream/master and 0 commits behind it. | There is no urgent upstream merge; continue to monitor upstream. |
| License and credit | The upstream MIT license and original copyright notice remain, and README links to PySkinDose and names the original author. | MIT requires preservation of its notice; this is the respectful approach too. |
| Distinct package identity | The distribution and import package are named mypyskindose. | Avoids impersonating or colliding with the upstream PyPI package. |
| Engineering hygiene | CI, tests, a changelog, Dependabot, dependency license checks, and secret scanning are present. | These provide a solid foundation for safe contributions. |
| Community files | CONTRIBUTING, SECURITY, SUPPORT, CODE_OF_CONDUCT, GOVERNANCE, CITATION.cff, issue forms, and PR template are present (2026-07-26). | Contributors and reporters have clear, privacy-aware channels. |
| Intended use | README / SUPPORT state research–education–QA use, not FDA-cleared, clinician responsibility. | Reduces misuse risk for clinical-looking dose software. |
| Issues | Enabled with no-PHI issue forms; Bug Tracker URL matches. | Package metadata and support policy stay coherent. |
| Main ruleset | Active ruleset requires PRs; blocks force-push and branch deletion. | Protects the integration branch. |
| Private vulnerability reporting | Enabled; SECURITY.md points reporters there. | Avoids public disclosure of security issues. |
| Release publishing | release.yml uses PyPI Trusted Publishing (OIDC); no `PYPI_DEPLOY_API_KEY` secret present. | Prefer short-lived credentials; register a PyPI trusted publisher before the first real publish. |

### Fork baseline (record syncs here)

```text
Upstream: https://github.com/rvbCMTS/PySkinDose
Upstream branch followed: master
Fork distribution/import name: mypyskindose
Last assessed upstream comparison: 2026-07-26 — 0 behind / 346 ahead of upstream/master
Local policy: upstream syncs arrive through a reviewed PR; main is never force-pushed.
```

Full Git history is retained from the fork. Begin recording each verified upstream sync
below after the next sync PR.

| Date | Upstream revision | Sync branch / PR | Notes |
|---|---|---|---|
| 2026-07-26 | (comparison only; no merge) | — | Still 0 commits behind upstream/master. |

## Highest-priority actions

Status as of 2026-07-26 (priorities 1–4 and most of 5–6 addressed in-repo; remaining
ops notes below).

| Priority | Action | Status |
|---|---|---|
| 1 | Public support route (Issues + templates, or alternate URL) | Done — Issues enabled with privacy-aware forms; Bug Tracker URL valid. |
| 2 | Protect main; use PRs | Done — active ruleset; keep using PRs for your own work. |
| 3 | CONTRIBUTING / SECURITY / SUPPORT / CODE_OF_CONDUCT | Done (plus GOVERNANCE, CITATION.cff, PR template). |
| 4 | Intended-use boundary | Done — README / SUPPORT / issue templates. |
| 5 | PyPI Trusted Publishing | Mostly done — OIDC in release.yml; register publisher on PyPI before first publish; revoke any leftover PyPI token if one still exists on the PyPI account. |
| 6 | Stale README / migration-status docs | Done — docs extra install path; migration status corrected. |

### Remaining maintainer ops (not blocking community files)

- Confirm delete-branch-on-merge stays enabled in GitHub settings.
- Optionally require named CI checks in the main ruleset if CodeQL/coverage alone are not enough.
- Before first PyPI publish: register trusted publisher; delete any legacy PyPI API token.
- Monthly: re-check upstream per §3 and §8.

### Do not over-correct

Do not detach this repository from the GitHub fork network, rewrite the original
history, delete upstream author credit, or replace the MIT license just to make
the project look more independent. None is necessary for an independently
maintained fork, and each makes attribution and future upstream comparison
harder.

## 1. Project identity and user safety

### Name the relationship accurately

Keep a short origin-and-maintenance section in README. It should say:

- MyPySkinDose is an independently maintained fork of PySkinDose.
- Link to the upstream repository.
- The original authors retain credit for the upstream work.
- MyPySkinDose is not presented as an official or endorsed PySkinDose release
  unless the upstream maintainers explicitly say so.
- Name the current maintainer or provide a durable maintainer contact route.

The current README already covers much of this. Adding a current maintenance
contact and a short statement of how this fork differs from upstream would make
it more useful to newcomers.

### Separate authorship, maintenance, and contribution

| Term | Meaning | Practical treatment here |
|---|---|---|
| Authors | People who created the original work or substantial new work. | Preserve original authors in LICENSE, history, and appropriate package metadata. |
| Maintainers | People currently making release and governance decisions. | Identify current maintainers in README, SUPPORT.md, GOVERNANCE.md, or PEP 621 maintainer metadata. |
| Contributors | People whose accepted patches improved the project. | Credit through Git history, pull requests, release notes, and optionally an AUTHORS file. |

Do not remove upstream people from the license or history. If package metadata
needs a current contact, add a maintainer entry rather than replacing historical
authors. Avoid publishing an email address that the person has not agreed to use
for this fork; a GitHub profile or dedicated project contact is often better.

### State the intended-use boundary

Because this software estimates radiation skin dose from medical imaging records,
plain language about intended use is especially important.

- If it is a research, educational, development, or quality-assurance tool, say
  so prominently and say that results are not independently validated for
  patient-care decisions.
- If the project is intended for clinical deployment, do not treat a README
  disclaimer as sufficient. Define intended use, validation evidence, data
  controls, user training, release approval, and applicable regulatory and
  institutional review with qualified clinical, regulatory, and legal
  stakeholders.
- Never promise diagnostic accuracy, certification, regulatory clearance, or
  clinical suitability unless that claim is documented and supported.
- Release notes should identify calculation-affecting changes, validation
  limits, migration concerns, and whether results can change.

The best wording depends on the actual intended use, so make this an explicit
maintainer decision rather than copying a disclaimer from another project.

### Protect patient data and sensitive assets

For this project, privacy is not just a generic security concern. RDSR files,
screenshots, exports, filenames, and logs can reveal patient or institutional
information.

- Never ask users to attach real patient data to a public issue, pull request,
  discussion, or chat transcript.
- Put a visible no-PHI/no-PII instruction in CONTRIBUTING.md, issue forms,
  SUPPORT.md, and SECURITY.md.
- Use synthetic or documented de-identified fixtures. Preserve provenance and
  human approval records for DICOM, images, PDFs, meshes, and other opaque
  assets.
- Treat a mistaken commit of patient data or a credential as an incident. Stop
  sharing it, revoke or rotate exposed credentials, obtain privacy/security
  help, and remove it from Git history with an appropriate reviewed procedure.
  Merely deleting the file in a new commit does not remove it from earlier
  history or clones.
- Review the privacy guardrails work on security/phi-pii-repo-guardrails
  normally and merge it only after its tests and documentation meet the project
  standard.

## 2. Attribution and licensing

### The minimum legal and ethical baseline

The upstream project is MIT licensed. Keep the complete LICENSE file and all
copyright notices in copies or substantial portions of upstream code. Do not
relabel upstream code as solely authored by this fork.

When copying code, assets, documentation, or algorithms from anywhere else:

1. Record where it came from and its license before committing it.
2. Confirm that the license permits the proposed use and redistribution.
3. Preserve required notices, attribution, source availability, or share-alike
   obligations.
4. Record non-code asset provenance separately. A mesh, image, data table, logo,
   documentation excerpt, and Python dependency can all have different licenses.
5. Ask for qualified legal review when a license is custom, unclear, commercial,
   research-only, privacy-restricted, or incompatible with the project policy.

The dependency license inventory is helpful, but it does not license third-party
data, meshes, screenshots, or copied source snippets. Check those separately.

### Suggested attribution record

Keep the upstream URL in README and add a small, maintained record if upstream
syncing becomes regular. It can be a section in this guide, README, or a new
FORK_BASELINE.md:

~~~text
Upstream: https://github.com/rvbCMTS/PySkinDose
Upstream branch followed: master
Fork distribution/import name: mypyskindose
Last assessed upstream revision/date: <commit or release/date>
Local policy: upstream syncs arrive through a reviewed PR; main is never force-pushed.
~~~

Do not invent a baseline commit later. If the original fork point is uncertain,
state that the full Git history is retained and begin recording syncs from the
next verified upstream comparison.

### Contributing improvements back upstream

A fork can send useful fixes upstream. That is considerate when a change is
general-purpose rather than specific to MyPySkinDose branding, packaging,
privacy policy, or local product direction.

- Read the upstream contribution instructions first.
- Start from the current upstream branch, not from a large fork-only feature
  branch.
- Make the pull request narrowly focused and include tests and documentation.
- Explain the problem and rationale without asking upstream to adopt unrelated
  fork history.
- Respect a declined pull request. Maintaining the change locally is normal.

Do not submit code that contains patient data, internal information, proprietary
logic, or work you lack authority to share.

## 3. Synchronize safely with upstream

GitHub describes the normal fork workflow in its
[Working with forks guide](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks).
This repository already has the recommended origin and upstream remotes.

### When to check

Check upstream at least monthly, before releases, after a relevant security
alert, and before starting a large change that might overlap with upstream. At
the review date, upstream had no commits missing from this fork, so a sync pull
request is not currently needed.

### Safe synchronization workflow

Use a new branch and pull request; never merge upstream directly into main from
an unreviewed terminal session.

~~~bash
# Update remote information without changing your current branch.
git fetch upstream --prune --tags

# Compare histories. Left-only commits are upstream-only; right-only are fork-only.
git log --left-right --graph --cherry-pick upstream/master...main

# Start from current fork main in a clean worktree or checkout.
git switch main
git pull --ff-only origin main
git switch -c sync/upstream-YYYY-MM-DD

# Preserve both histories and make the integration visible.
git merge --no-ff upstream/master

# Run normal tests and documentation checks, then open a PR.
git push -u origin sync/upstream-YYYY-MM-DD
~~~

If conflicts occur, resolve them deliberately and record any behavioral decision
in the pull request. For calculation, parsing, dependency, or clinical
interpretation changes, add regression tests and explain whether output changes.

Do not force-push main to make history look cleaner. For a highly divergent fork,
a merge-based sync is usually easier to audit than repeatedly rebasing public
history. Either policy can work; document one and apply it consistently.

### Use worktrees for parallel work

A worktree is a second folder attached to the same Git repository, with a
different branch checked out. It is a good fit when an agent or collaborator is
already working on another branch.

~~~bash
# From any clean checkout, create a sibling worktree from main.
git worktree add ../MyPySkinDose-fork-docs -b docs/fork-maintainer-guide main

# See every active worktree before removing anything.
git worktree list
~~~

One worktree should normally have one branch. Do not switch the branch in
another person's or agent's worktree, and do not use cleanup commands until you
know no one is still working there. The worktree used for this guide is separate
from security/phi-pii-repo-guardrails for precisely that reason.

## 4. Make collaboration expectations visible

GitHub's community profile highlights the conventional public-project files:
README, license, contribution guidance, code of conduct, security policy, and
issue templates. See GitHub's
[community profile documentation](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories).

### Files to add

| File | What it should cover | Project-specific note |
|---|---|---|
| CONTRIBUTING.md | Setup, branch/pull-request workflow, test commands, changelog and docs expectations, review process. | Link to AGENTS.md and dev-docs/AGENT_PLAYBOOK.md; say no real RDSRs, patient data, or credentials may be submitted. |
| CODE_OF_CONDUCT.md | Expected respectful behavior and reporting route. | A maintained template such as Contributor Covenant is reasonable if its reporting route is real. |
| SECURITY.md | Supported versions, private reporting route, embargo expectations, response process. | Tell reporters not to disclose vulnerabilities or patient data in public issues. Do not promise response times you cannot meet. |
| SUPPORT.md | Where usage questions, bugs, feature requests, and security reports belong. | State whether support is best-effort and which channel to use while Issues remain disabled. |
| .github/ISSUE_TEMPLATE/ | Bug and feature forms with version, environment, and reproduction fields. | Prominently prohibit patient data, raw RDSRs, identified screenshots, credentials, and full sensitive logs. |
| .github/pull_request_template.md | A short pull-request checklist. | Include tests, documentation/changelog, privacy/assets, license/provenance, and compatibility checks. |
| CITATION.cff | A machine-readable citation for research users. | Credit the fork correctly and cite upstream papers or software according to their requested citation guidance. |
| GOVERNANCE.md, optional | Who maintains the project, how decisions/releases happen, and how maintainership changes. | A short solo-maintainer statement is enough; avoid elaborate governance before it is needed. |

GitHub explains how a CONTRIBUTING file is surfaced in its
[contribution-guidelines documentation](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/setting-guidelines-for-repository-contributors).

If several repositories need the same policies, a public account-level .github
repository can provide defaults. Keep a repository-specific file whenever its
privacy or clinical-data rules differ.

### Choose a support channel deliberately

**Decision (2026-07-26):** GitHub Issues and Discussions are **enabled**. Issue
forms are privacy-aware. The maintainer is open to ideas and considering
submissions via Issues/Discussions; prefer those over cold PRs
([CONTRIBUTING.md](../CONTRIBUTING.md)). The Bug Tracker URL in `pyproject.toml`
matches Issues. SECURITY.md points security reporters to private vulnerability
reporting. SUPPORT.md states best-effort support and the no-PHI rule. GitHub has
no general private DM channel; the maintainer profile link is for identity, not
inbox messaging.

### Use a small repeatable pull-request checklist

For every change, ask:

- Is the change focused and does its title say what users experience?
- Did I work from a feature branch or dedicated worktree rather than directly
  on main?
- Did I run the relevant tests, linters, and documentation checks?
- Did I update CHANGELOG.md for user- or maintainer-visible behavior?
- Could it affect calculated dose, input interpretation, exports, privacy, or
  backwards compatibility? If yes, is that stated and tested?
- Did I avoid real clinical data, credentials, private URLs, and unlicensed
  assets?
- Did I record any new third-party license, notice, citation, or asset
  provenance?

Use a pull request for your own work too. It creates an auditable discussion,
runs CI, and lets you read the diff one more time before main changes.

## 5. Configure GitHub for a small but serious project

### Repository settings to review now

| Setting | Review finding | Recommended decision |
|---|---|---|
| Fork relationship | Enabled and correct. | Keep it; do not detach just because the project has diverged. |
| Default branch | main. | Keep main as the protected integration branch. |
| Branch protection/ruleset | Main was not protected at review. | Add a main ruleset requiring a pull request and passing CI. |
| Delete head branches | Disabled at review. | Enable after merge unless a branch has an intentional long-lived role. |
| Issues | Disabled at review. | Enable safe templates, or fix the broken Bug Tracker URL and document another route. |
| Wiki | Enabled while repository docs are version-controlled. | Use intentionally for non-versioned community material or disable it to prevent documentation drift. |
| Dependabot | Version and security updates are enabled. | Keep enabled; review updates in small batches with CI. |
| Secret scanning | Scanning and push protection are enabled. | Keep enabled; consider generic-pattern detection only after assessing false positives and capacity. |
| Private vulnerability reporting | Not verified in this review. | Enable it if available and point SECURITY.md to it. |

### A reasonable main ruleset

In GitHub Settings, Rules, Rulesets, create a rule for the default branch.
GitHub's [ruleset documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
has current UI details.

For a solo maintainer, begin with:

- Require a pull request before merging.
- Require the CI workflow, GUI smoke test, and secret scan to pass.
- Block force pushes and branch deletion.
- Require branches to be up to date before merge only if the added CI time is
  acceptable.
- Let administrators bypass the rule only for an urgent, documented recovery.

Require a human approval only when there is a real second reviewer. A rule that
you always self-bypass adds friction without meaningful review. As soon as there
is a trusted co-maintainer, require one approving review for calculation,
release, security, and privacy-sensitive changes.

### GitHub Actions and release hardening

The repository already pins most Actions by commit SHA, which is a good
supply-chain practice. Make two improvements through a dedicated, tested pull
request:

1. Declare least-privilege permissions in each workflow or job. The scheduled
   ci-latest workflow declares `contents: read` and `issues: write` (failure
   opens/updates a tracking issue instead of failing the branch check), and
   ci.yml, release.yml, phi-scan.yml, and presidio.yml all declare job/workflow
   permissions. As of 2026-07-18, gitleaks.yml now declares `contents: read` and
   `pull-requests: write` (the latter is required by gitleaks-action v2 to post
   PR review comments via `pulls.createReviewComment`). Confirm post-merge that
   PR commenting still works and that GitHub Code Scanning alert #3
   (`actions/missing-workflow-permissions` on gitleaks.yml) auto-closes.
2. Move PyPI publication from a stored PYPI_DEPLOY_API_KEY to
   [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/), which
   uses short-lived OpenID Connect credentials. Pin the PyPI publishing Action
   to an immutable reviewed release or commit instead of the mutable master
   reference. After a successful Trusted Publishing release, revoke the old API
   token.

For a workflow that can publish, create releases, write comments, or access a
secret, also review:

- Who may trigger it.
- Whether pull requests from forks run untrusted code with secrets available.
- Whether release tags are protected and created only from reviewed main commits.
- Whether artifacts, logs, and generated reports might contain sensitive data.

## 6. Packaging, releases, and documentation

**Hub:** [RELEASES_AND_DISTRIBUTION.md](RELEASES_AND_DISTRIBUTION.md) — channels (PyPI, GitHub Release,
source install, deferred portable GUI), changelog vs user-facing Release notes, and the condensed
checklist. PyPI Trusted Publishing detail: [PUBLISHING.md](../PUBLISHING.md).

### Package metadata

Before each release, review pyproject.toml:

- Distribution name and import package remain distinct from upstream.
- Version follows the project SemVer policy and agrees with CHANGELOG.md.
  **First GUISkinDose / `guiskindose` version is `1.0.0`** (new identity; live package
  remains MyPySkinDose `25.2.0` until the rename packaging commit). See
  [plans/GUISKINDOSE_RENAME_PLAN.md](plans/GUISKINDOSE_RENAME_PLAN.md).
- Homepage, documentation, and bug-tracker URLs work. After the GitHub fork is renamed,
  follow [plans/GUISKINDOSE_GITHUB_RENAME_PLAN.md](plans/GUISKINDOSE_GITHUB_RENAME_PLAN.md)
  (Sonar key before `sonar-project.properties`; then live URLs and `origin`).
- Python support matches the tested CI matrix.
- Authors, maintainers, license, classifiers, and project description are
  accurate.
- Dependencies and uv.lock change together; regenerate required third-party
  notices after dependency changes.

The current Bug Tracker URL leads to disabled Issues. Fix that with the
support-channel decision, not as an unrelated cosmetic edit.

### Documentation items to repair

Resolved 2026-07-26:

- README docs build now uses `pip install -e ".[docs]"` (no `requirements*.txt`).
- `dev-docs/MYPYSKINDOSE_MIGRATION_STATUS.md` corrected for extras / `uv.lock` packaging.

When changing behavior, settings, exports, or GUI help, follow the documented
checks. In particular, update dev-docs/index.md whenever adding or retiring a
maintainer document.

### Release checklist

Prefer the hub checklist in [RELEASES_AND_DISTRIBUTION.md](RELEASES_AND_DISTRIBUTION.md). Summary:

1. Sync or explicitly compare upstream and record the result.
2. Confirm main is green and every included pull request has a clear review trail.
3. Update pyproject.toml version, CHANGELOG.md, citations, and supported-version
   policy where applicable.
4. Run full tests and the documented privacy, secret, dependency, licensing,
   type, build, and documentation checks.
5. Build the wheel and source distribution locally; inspect their contents and
   validate package metadata.
6. Verify no fixture, report, screenshot, release artifact, log, or Action
   output contains identifiers, private paths, credentials, or unapproved assets.
7. Create a reviewed GitHub Release from the exact main commit with **user-facing**
   notes (not a dump of every CI/refactor CHANGELOG line — see the hub). Verify
   `release.yml` published the expected version and retained expected artifacts.
8. Publish concise release notes: changes, upgrade notes, validation limits,
   known issues, and contributor credit.

Avoid silent releases. Users of scientific or clinical-adjacent software need to
know which version produced a result and why behavior changed.

## 7. Daily Git and GitHub habits

### Start a change

~~~bash
git switch main
git pull --ff-only origin main
git switch -c feat/short-description
~~~

Use a branch name that explains the goal: feat/tabular-preview, fix/dap-units, or
docs/contributing-guide. Keep one conceptual change per branch. A documentation
fix should not include an unrelated dependency upgrade or physics change.

### Before committing

~~~bash
git status --short
git diff --check
git diff
~~~

Then run the smallest meaningful checks. Typical documentation work should at
least run:

~~~bash
python scripts/check_doc_freshness.py
python scripts/check_file_sizes.py
python scripts/check_agent_guidance.py
~~~

For code, input, calculation, packaging, security, or privacy changes, run the
broader checks named in dev-docs/AGENT_PLAYBOOK.md and
dev-docs/HARNESS_ENGINEERING.md.

### Create a pull request

Push the branch, open a pull request into main, and write:

- What problem does this solve?
- What changed for users or maintainers?
- How was it tested?
- Does it affect calculations, input data, exports, privacy, license
  obligations, or compatibility?
- What follow-up work remains?

Read the rendered diff before merging. This often catches surprising generated
files, unrelated formatting, accidental data, or missing documentation.

### After merge

- Confirm the merged commit appears on main and its CI is green.
- Let GitHub delete the merged branch if it is no longer needed.
- Update the changelog, release milestone, or project board only if you use it;
  avoid duplicate sources of truth.
- Keep local worktrees only while active. Check their status before removal.

## 8. Monthly maintenance rhythm

Once a month, or before every release:

- Check upstream commits, releases, and security notices.
- Review Dependabot pull requests and dependency-audit suppressions.
- Review open security reports, Action failures, and untriaged support requests.
- Run document pruning and freshness checks.
- Confirm the issue/support policy still matches what you can maintain.
- Check branch rules, protected tags, and PyPI publishing access still belong to
  the right people.
- Review new assets and external code for provenance, license, and privacy.
- Read the CHANGELOG.md Unreleased section as if you were a user deciding
  whether to upgrade.

This modest routine is more valuable than a one-time burst of configuration.

## Further reading

- [GitHub: Working with forks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks)
- [GitHub: Healthy contribution files](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions)
- [GitHub: Community profile for public repositories](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories)
- [GitHub: Quickstart for securing a repository](https://docs.github.com/en/code-security/getting-started/quickstart-for-securing-your-repository)
- [GitHub: Repository rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
- [PyPI: Trusted Publishers](https://docs.pypi.org/trusted-publishers/)

