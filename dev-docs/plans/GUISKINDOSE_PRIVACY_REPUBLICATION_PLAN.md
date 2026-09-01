# GUISkinDose Privacy, Fixture Sanitization, Full Rename, and Fork-Preserving Publication Plan

_Status: Proposed_
_Created: 2026-07-16_
_Owners: Maintainers; coding agents may implement individual phases_
_Predecessor: [PRIVACY_HARDENING_PLAN.md](PRIVACY_HARDENING_PLAN.md)_
_Mechanical rename: [GUISKINDOSE_RENAME_PLAN.md](GUISKINDOSE_RENAME_PLAN.md) — execute that file for Phase 5A; do not duplicate replacement tables here._
_Policy: [PRIVACY_AND_SENSITIVE_ASSETS.md](../PRIVACY_AND_SENSITIVE_ASSETS.md)_
_Incident response: [PRIVACY_INCIDENT_RESPONSE.md](../PRIVACY_INCIDENT_RESPONSE.md)_

## 1. Objective

Finish the current privacy hardening, replace the public DICOM regression fixtures with conservatively sanitized
derivatives, add targeted person-name and image/DICOM review tooling, complete the **GUISkinDose** / `guiskindose`
identity change (mechanical steps live in [GUISKINDOSE_RENAME_PLAN.md](GUISKINDOSE_RENAME_PLAN.md)), and publish
the renamed project by updating the existing GitHub fork without rewriting its history.

The result should remain fully attributed to PySkinDose and retain GitHub's technical fork-network relationship.

## 2. Current evidence and assumptions

- The working tree contains the implemented privacy hardening from `PRIVACY_HARDENING_PLAN.md`, but it has not yet
  been staged or committed.
- The approved-asset inventory currently contains 55 SHA-256-pinned assets, including five DICOM RDSR fixtures.
- All five DICOM fixtures are Radiation Dose Structured Reports and contain no `PixelData`; image OCR therefore does
  not add coverage for these particular files.
- The five DICOMs contain recognizable patient/study/device/date/UID fields and between five and eight private
  elements each. Their recorded provenance is synthetic or public upstream PySkinDose test/regression data, likely
  including phantom exams, but that context is not treated as proof of de-identification.
- An in-memory characterization removed private elements, blanked direct identifiers, and consistently replaced
  non-class UIDs. For all five files, `rdsr_parser()` retained the same shape and columns; only the
  `IrradiationEventUID` column changed.
- `tests/fixtures/tabular_inputs/generic_rdsr_events.csv` already contains deterministic synthetic irradiation-event
  UIDs. The current tracked XLSX fixtures contain no UID columns.
- The phi-scan baseline contains 21 reviewed, hash-only synthetic/table false-positive fingerprints expiring on
  2026-10-14.
- No unresolved reportable privacy finding is currently known in the candidate tree. This plan is additional
  risk reduction, not a declaration that actual patient PHI was previously published.
- The approved-asset inventory is a current-tree admission allowlist, not an inventory of every blob ever reachable
  from Git history.
- A preliminary value-suppressed audit of the 390 commits and 19 locally available refs found six historical DICOM
  blobs whose hashes are not in the current inventory: four earlier byte versions of current fixtures and two removed
  RDSRs. All six contain direct-identifier-capable fields and private elements, and none contains `PixelData`. The
  maintainer has reviewed their filenames/history and identified all six as expected-safe upstream test fixtures.
- The same preliminary audit found three old `file://` documentation links containing the maintainer's local username
  and project directory, plus a generic test path and a literal URI-prefix assertion. It did not find
  deterministic matches for SSNs, phone numbers, private-network/PACS addresses, contextual patient IDs, or sensitive
  path names. Historical author/contact emails appear in source metadata and commit trailers; these require an
  attribution/contact review, not PHI incident treatment.
- Historical-only notebooks had no saved visual outputs or attachments. Historical-only meshes and compressed binary
  assets produced no meaningful text/privacy matches; byte-regex email-like matches in binary STL data were classified
  as random binary false positives.
- These are low-risk historical hygiene observations, not evidence that real patient PHI was committed. The available
  evidence does not justify rewriting the fork's history; Phase 6 still records the audit scope and limitations.

## 3. Decisions and boundaries

### 3.1 Public identity

The public product, application, documentation title, GitHub repository, command name, PyPI distribution name, and
canonical Python import namespace will be **GUISkinDose** / `guiskindose`, subject to confirming external namespace
availability before publication.

The first GUISkinDose release is an intentional breaking identity change:

- `pip install guiskindose` installs the `guiskindose` import package;
- supported code uses `import guiskindose`, `from guiskindose ...`, and `python -m guiskindose`;
- the console command is `guiskindose`;
- source moves mechanically from `src/mypyskindose/` to `src/guiskindose/`;
- GUI/config/cache/application directories migrate privately to the new name without logging raw paths;
- no permanent `mypyskindose` compatibility package is included in the renamed distribution by default, avoiding
  duplicate module identities and an old namespace that never goes away;
- a migration guide gives exact import, command, extra, configuration, and API substitutions;
- old names remain only in provenance, license/copyright, historical attribution, and clearly marked migration text.

If a `mypyskindose` distribution already exists on PyPI under maintainer control, its disposition is a separate
release decision. A final deprecation-only release may point users to `guiskindose`, but it must not be published until
ownership, dependency-confusion implications, and package-index policy have been reviewed. PyPI distribution names
and Python import names are distinct concepts even though using the same canonical name is the clearest choice here.

### 3.2 GitHub fork relationship

GitHub's fork banner is a property of membership in a fork network, not an attribution label.

The selected publication choice is to rename the existing public fork to `GUISkinDose` without rebasing, squashing,
filtering, orphaning, or force-pushing its history. GitHub should therefore preserve the “forked from PySkinDose”
relationship, repository redirects, issues, pull requests, stars, and other repository metadata.

This decision is supported by the current review: the historical DICOMs are expected-safe upstream test fixtures,
and the only non-test local-path disclosure was the maintainer's own macOS username/project directory in three
documentation links. No confirmed PHI, secret, release asset, tag, or LFS object requires history remediation. If a
later audit validates genuinely sensitive data, activate the incident runbook and reconsider targeted history
rewriting; do not restart history merely as a cosmetic measure.

### 3.3 Privacy tooling

- Automated detection supplements human review and never certifies de-identification.
- Scanners must be local-first, version-pinned, value-suppressing, and unable to upload source or reports.
- OCR is a detection/admission aid, not an automatic in-place redactor.
- New or changed clinical-looking assets must be scanned before staging; CI is a second line of defense because a PR
  branch may already be publicly accessible.
- Sentry remains out of scope.

## 4. Delivery order

Do not publish intermediate DICOMs, OCR reports, scanner reports, UID mappings, or unsanitized fixture bytes.
The in-repo package rename ([GUISKINDOSE_RENAME_PLAN.md](GUISKINDOSE_RENAME_PLAN.md)) **may merge to the public
`MyPySkinDose` GitHub repository** before Phase 7; that is an identity change in code, not a GitHub rename.
Do not rename the GitHub repository or publish to PyPI until Phase 7 / 5B exit criteria pass.
Work on fixture sanitization locally or in an approved private environment until those artifacts are admitted.

### Phase 0 — Freeze, recoverability, and decision lock

1. Pause public pushes while the plan is active.
2. Record the current branch, HEAD, remotes, tags, Git LFS status, release inventory, and dirty-tree status without
   emitting sensitive filenames into a public log.
3. Create a private, access-controlled recovery bundle or clone outside the future publication tree. Do not add it to
   this repository or a cloud-synced scratch directory.
4. Record the selected publication choice: retain and rename the existing GitHub fork without rewriting history.
5. Lock the breaking rename boundary (details in [GUISKINDOSE_RENAME_PLAN.md](GUISKINDOSE_RENAME_PLAN.md)): product
   `GUISkinDose`; distribution, import namespace, module launcher, and CLI `guiskindose`; no permanent old-namespace
   shim by default; private migration from `~/.mypyskindose/` settings. The GitHub repository rename remains Phase 7
   and is not a prerequisite for the in-repo package rename.
6. Check availability and ownership of the `GUISkinDose` GitHub name, `guiskindose` distribution name, documentation
   hostname, and any package-publishing identities. Do not reserve or mutate external services without explicit
   maintainer authorization. Re-check immediately before Phase 5A if other work delayed execution.
7. Capture the current passing test and scanner results as counts/status codes only.

**Exit criteria**

- Recovery is possible without relying on the public remote.
- Fork-network and import-namespace decisions are written into this plan or a linked decision record.
- No external repository or package name has been changed prematurely.

### Phase 1 — Stabilize the existing privacy-hardening work

1. Review the complete working-tree diff and separate unrelated user work if necessary.
2. Resolve the temporary `.phi-scanbaseline` inventory/tracking mismatch as part of the reviewed change set.
3. Run the full unit and GUI/security test suites, privacy scanners, type checking, linting, documentation checks,
   inventory renderer, and strict ignored-artifact gate.
4. Confirm all scanner output is value-safe and all temporary scanner data is removed.
5. Make a local/private checkpoint commit if needed for recoverability. Do not push it merely to create a checkpoint.

**Exit criteria**

- The current privacy hardening passes its documented verification suite.
- The standard strict gate passes without prospective-path workarounds.
- No unexpected tracked, untracked, or ignored diagnostic artifact remains.

### Phase 2 — Deterministically sanitize the DICOM RDSR fixtures

1. Add a reviewed sanitizer/validator such as `scripts/sanitize_public_rdsr_fixtures.py`. It must accept an explicit
   source directory and output directory; it must not download upstream data or retain original values/mappings.
2. Record upstream repository URL, upstream revision when recoverable, original public SHA-256, sanitized SHA-256,
   and a value-free description of each transformation.
3. Apply the DICOM Basic Application Level Confidentiality Profile conservatively to every top-level and nested
   data set:
   - remove private elements recursively unless a specific safe-private exception is proven necessary;
   - blank or replace patient, accession, institution, personnel, station, device serial, study, and other identity
     fields with DICOM-valid, unmistakably synthetic values;
   - replace dates/times deterministically while preserving event order and required intervals;
   - replace Study, Series, SOP Instance, referenced-instance, irradiation-event, observer, and other instance UIDs
     with consistent synthetic `2.25.*` UIDs;
   - preserve standard class/transfer-syntax UIDs and coded terminology identifiers;
   - preserve Manufacturer, ManufacturerModelName, physics, geometry, exposure, filtration, dose, and required SR
     content;
   - regenerate File Meta Information and the preamble so upstream implementation/network metadata cannot survive;
   - set `PatientIdentityRemoved` and an accurate `DeidentificationMethod`; claim a standard profile/code only after
     every required action has been validated.
4. Generate UID replacements from file logical identity and ordinal, not by publishing a reversible or stable hash
   of an upstream UID. Maintain old-to-new consistency only in memory during transformation.
5. Ensure the dataset `SOPInstanceUID`, file-meta `MediaStorageSOPInstanceUID`, and all internal references agree.
6. Validate each result with pydicom and an independent DICOM structural validator when practical.
7. Compare pre/post parser frames:
   - identical rows, columns, and non-sensitive values;
   - only approved identifier/date/UID fields may differ.
8. Compare normalized geometry and dose results, including the existing golden dose output. No numerical dose or
   geometry difference is acceptable without a separately reviewed explanation.
9. Run the deterministic sensitive-content gate and the safe DICOM scanner wrapper from Phase 3.
10. Review the final headers manually without copying values into issues, commit messages, or reports.
11. Replace the tracked DICOMs, update their inventory hashes/review records, and state that they are conservatively
    modified derivatives of the public upstream fixtures.

**Exit criteria**

- No private element remains unless it has an explicit, hash-pinned safe-private justification.
- No upstream instance/event UID or direct identifier remains.
- File meta is regenerated and internally consistent.
- RDSR parsing, geometry, and dose regression tests pass unchanged except for explicitly synthetic metadata.
- All five DICOM inventory entries have new hashes and completed review checklists.

### Phase 3 — Align tabular fixtures with sanitized DICOM provenance

1. Regenerate `generic_rdsr_events.csv` from the selected sanitized RDSR or document why it is intentionally an
   independent synthetic fixture.
2. Ensure its 21 `IrradiationEventUID` values are unique, deterministic, DICOM-valid `2.25.*` values and, when it is
   derived from a specific RDSR, match that sanitized source's event UIDs.
3. Add a regression test that prevents upstream UIDs from being reintroduced.
4. Assert that current XLSX fixtures contain no UID columns. If a future XLSX fixture gains an identifier/UID column,
   require the same synthetic-value and inventory review.
5. Run phi-scan, targeted Presidio structured scanning, formula-injection checks, and the deterministic gate on all
   tabular fixtures.
6. Rebuild the phi-scan baseline only after triage. Every entry needs reviewer, date, reason, and expiry; store no raw
   matched value.

**Exit criteria**

- Tabular identifiers are synthetic and their relationship to source fixtures is tested.
- No XLSX/container metadata or embedded member introduces an unreviewed identifier.
- There are no new or silently ignored phi-scan/Presidio findings.

### Phase 4 — Add targeted Presidio PERSON and image/DICOM admission checks

#### 4A. Context-qualified PERSON detection

1. Extend the Presidio runner with two explicit modes:
   - `structured`, retaining the current blocking direct-identifier entities;
   - `clinical-person`, enabling PERSON only for selected prose and sensitive-schema fields.
2. Build the clinical-person candidate set from:
   - changed CSV/TSV/XLSX string fields whose headers imply patient, name, physician, operator, referring,
     performing, institution, personnel, or related clinical identity;
   - changed DICOM-derived fixtures and dose-management export samples;
   - changed user-facing prose, GUI help, examples, release notes, and issue templates.
3. Promote a PERSON result only when it meets the calibrated confidence threshold and has clinical context or a
   sensitive field name. Do not block on generic proper nouns in source code.
4. Add exact allowlist entries only for deliberate public names/attribution, with reason and review date.
5. Create synthetic positive and negative fixtures covering real names, device names, anatomical phrases,
   `ReferencePointDefinition`, `XRayFilterType`, and public author attribution.
6. Keep clinical-person advisory until measured fixtures and repository results demonstrate an acceptable false
   positive/negative profile; then make only context-qualified results blocking.

#### 4B. Local OCR/image analysis

1. Add a value-safe wrapper such as `scripts/run_image_privacy_advisory.py` around pinned local Tesseract/Presidio
   image analysis. Do not use a network OCR service.
2. Trigger it for every new or changed PNG/JPEG/TIFF, rendered notebook output, PDF page, Office preview, and DICOM
   containing `PixelData` or graphics/overlays.
3. Use private temporary directories, restrictive permissions, no persistent report, no OCR text in output, hashed
   path labels by default, and reliable cleanup after success/failure/interruption.
4. Report only entity type, confidence, bounding-box count, scanner status, and path token.
5. Never redact or overwrite the source automatically. A human decides whether to remove, recreate, or explicitly
   approve an asset.
6. Generate known-positive/negative images during tests rather than checking in unnecessary binary fixtures.
7. Run the changed-asset check locally at commit/pre-push time and run a weekly full approved-inventory scan in CI.
   CI scans only already-tracked public assets and uploads no report.

#### 4C. Safe `dicom-phi-scan` integration

1. Pin the installed `dicom-phi-scan` version and source/wheel hash in an isolated optional tool environment.
2. Record that version 0.1.0 is an early secondary scanner and not the repository's de-identification authority.
3. Wrap it so JSON/JSONL, filenames, header values, and OCR text exist only in a private ephemeral directory. Print
   only safe counts, risk levels, path tokens, and stable errors.
4. Require it locally for every changed DICOM before staging, regardless of whether `PixelData` exists.
5. Prove header detection against a generated DICOM with synthetic direct identifiers and prove OCR detection against
   a generated image DICOM. Also prove clean synthetic controls exit successfully.
6. Retain the deterministic private-tag/nested-sequence checks and human checklist as the authoritative admission
   boundary. A clean secondary scan cannot approve an asset.
7. Do not add raw scanner reports, cloud/AI review, or a GitHub App.

#### 4D. Agent and contributor routing

Update `AGENTS.md`, `dev-docs/AGENT_PLAYBOOK.md`, setup docs, and hook help with these mandatory routes:

- DICOM change → sanitizer/validator, safe `dicom-phi-scan`, deterministic gate, human review, inventory update.
- Image/PDF/Office/notebook visual change → local OCR wrapper, human visual review, inventory update.
- CSV/TSV/XLSX or clinical prose change → structured Presidio/phi-scan plus clinical-person mode when applicable.
- Logging/export/upload/API/database change → privacy Semgrep and HoundDog.
- Advisory result → fix or record a narrow reviewed disposition; never ignore it.

#### 4E. Enforce conditional scanner routing and protected output paths

Use the content-bound receipt design recommended in
[`../assessments/privacy-admission-enforcement/hardening.md`](../assessments/privacy-admission-enforcement/hardening.md):

1. Add one versioned privacy-admission policy file defining:
   - `.gitignore` patterns that must remain present;
   - directories and globs that must never be tracked, including local output, logs, scanner reports/state, scratch,
     caches, coverage/build output, and private sample-data roots;
   - staged-path and staged-diff triggers for DICOM, images/rendered documents, tabular/clinical text, and
     logging/write/export/ingestion/API/database code;
   - required scanner IDs, versions/configuration digests, receipt lifetimes, and allowed reviewed dispositions.
2. Add a blocking policy checker that inspects the Git index, not only the working tree. It must fail when a protected
   ignore rule is removed or weakened, a forbidden path is staged/tracked, scanner state/report output is staged, or
   the policy and hook/CI routing disagree. Diagnostics remain value-safe and path-tokenized by default.
3. Keep a broad `.gitignore` for local containment, but do not rely on ignore behavior as the security boundary:
   ignored files can still be force-added and ignore rules can be deleted. Run the same policy checker in pre-commit,
   pre-push, and required CI.
4. Add a single privacy-routing command that evaluates the exact staged snapshot and prints which scanner classes are
   required. It may run cheap checks automatically; expensive tools may be run separately through the same wrapper.
5. Store local scanner receipts below the repository's Git metadata directory, never in the tracked tree. Bind each
   receipt to the scanner/version, policy/configuration digest, exact relevant staged blob hashes, result status, and
   time. Store no matched value, OCR text, DICOM value, raw path, or scanner report.
6. Do not use a tracked `last_run` timestamp as proof. A receipt is valid only while its content/configuration digest
   matches the staged snapshot; time is a secondary expiry control for tool/model updates and weekly full scans.
7. Require matching receipts at pre-push for conditionally expensive local tools:
   - changed DICOM → deterministic gate, safe `dicom-phi-scan`, and inventory/human-review evidence;
   - changed image/PDF/Office/notebook visual → local OCR plus inventory/human-review evidence;
   - changed CSV/TSV/XLSX or clinical prose → phi-scan and structured/context-qualified Presidio;
   - changed logging/write/export/ingestion/API/database code → privacy Semgrep and HoundDog.
8. Change local wrappers so `clean`, `findings`, and `not_run/error` are distinct exit states. When a triggered tool is
   required, missing installation, model, report, or successful completion must block receipt creation rather than be
   reported as a successful advisory skip.
9. For DICOM and rendered-asset findings, use the existing exact-hash approved inventory and its reviewer/checklist
   evidence as the reviewed disposition; changing the file or inventory reopens the finding. Keep non-asset findings
   fix-or-fail unless measured false-positive evidence justifies a separate narrow, expiring, value-free disposition
   manifest keyed by scanner/rule/finding fingerprint and relevant content hash.
10. CI independently reruns every scanner suitable for public ephemeral runners and checks the same routing policy;
    local-only scanner receipts protect developer/agent pushes but are not accepted as substitutes for CI. Continue
    weekly full-inventory workflows to catch model/rule updates even when repository content is unchanged.
11. Add synthetic routing, missing-tool, stale-receipt, policy-tamper, ignored-directory, and known-positive/negative
    tests. Verify that `--no-verify` is caught by required CI and that raw matches never appear in hook output.

Standard Git has no reliable pre-`git add` hook, so the enforceable boundary is commit/push/merge rather than the
moment a path enters the index. An optional `git add` wrapper may warn earlier, but it must not be the only control.

**Exit criteria**

- Synthetic known positives prove every claimed scanner path fires.
- Scanner failures are distinguishable from clean results and fail closed where required.
- No scanner emits raw matched values, sensitive filenames, or persistent reports.
- Agent instructions name the exact trigger conditions and commands.

### Phase 5 — Rename the product, import package, and distribution to GUISkinDose

The in-repo mechanical rename **may land before Phases 1–4** (fixture sanitization) and **does not require** the
GitHub repository rename in Phase 7. Prefer completing it before the first PyPI publish. If other commits land first,
re-run the inventories in [GUISKINDOSE_RENAME_PLAN.md](GUISKINDOSE_RENAME_PLAN.md) § Re-count before execution.

#### 5A. Mechanical and behavioral rename

Execute [GUISKINDOSE_RENAME_PLAN.md](GUISKINDOSE_RENAME_PLAN.md) in full. That file is the source of truth for
directory/import replacement, Semgrep rule-ID exceptions, config/env migration, tests to add, commit grouping,
and GitHub/Sonar URL gating. Do not copy replacement tables here.

Exit criteria that this phase still owns (must be true after the rename PR merges):

1. PySkinDose and original-author attribution are preserved; copyright is not rewritten for branding.
2. Only one source tree ships (`src/guiskindose/`). Editable-checkout smokes are not accepted as packaging proof —
   the rename plan's wheel-install tests must pass.
3. The stale-brand allowlist check from the rename plan is wired into pre-commit/CI.
4. Privacy path rules cover both old and new config/cache locations without logging raw paths.
5. A migration document (README plus changelog Unreleased) covers imports, CLI/module/console script, extras,
   configuration migration, environment variables, output metadata, and the absence of a permanent compatibility shim.
6. Live `github.com/kgrizz-git/MyPySkinDose` URLs and the SonarCloud project key are left unchanged until Phase 7
   actually renames those external projects.

#### 5B. Python packaging and release hygiene

1. Treat this as a Python/PyPI project. Do not add npm metadata, a JavaScript package, or an npm publication workflow
   unless independently developed frontend code later creates a real Node package boundary.
2. Confirm the normalized `guiskindose` name is available and appropriate on PyPI and TestPyPI, and confirm ownership
   or nonexistence of any prior `mypyskindose` project. A pending trusted publisher does not reserve a name.
3. Decide and record the first GUISkinDose version (the rename plan Phase 0 records the same decision). Prefer a
   clearly documented breaking bump of the current `25.2.0` line; do not choose a version solely to imitate upstream
   history.
4. Modernize and verify `pyproject.toml` (the rename plan already requires name, `guiskindose*` package discovery,
   and `[project.scripts] guiskindose`). This phase still verifies before publish:
   - accurate description, Python requirement, license expression/files, maintainers, classifiers, keywords,
     dependencies/extras, and current project URLs (GitHub URLs still match the live repo name until Phase 7);
   - package data explicitly includes required JSON, database, help, mesh, and example assets and excludes caches,
     `.DS_Store`, generated egg-info, tests, scanner output, and original unsanitized fixture bytes.
5. Remove obsolete source-root packaging artifacts such as an unnecessary `src/__init__.py`; confirm generated
   `*.egg-info`, `__pycache__`, build output, and platform metadata remain ignored and absent from distributions.
6. Build both wheel and source distribution in a clean environment. Inspect their complete file lists and metadata,
   run metadata validation, install each into fresh isolated environments, and smoke-test imports, CLI, GUI extras,
   resources, privacy defaults, and uninstall behavior without relying on the checkout.
7. Test publishing and installation through TestPyPI, accounting for dependencies that TestPyPI may not host. Publish
   production releases from a protected GitHub environment with PyPI Trusted Publishing/OIDC and attestations; do not
   store a long-lived PyPI token in repository secrets.
8. Require tag/version/changelog consistency, immutable artifacts built once by CI, checksums, provenance, and a
   post-publication install smoke test from PyPI.

#### 5C. Fork etiquette, governance, and project identity

1. Preserve the MIT license and upstream copyright notices. Add a concise `NOTICE` or provenance section naming
   PySkinDose, its repository URL, the revision/lineage used, substantial local changes, and fixture sanitization.
2. Review author versus maintainer metadata rather than replacing upstream authorship. Add current maintainers only
   with their consent; use role-appropriate public contact information.
3. Add or refresh `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`, support/release policy, issue
   and pull-request templates, and dependency-update configuration. Add `AUTHORS` only if it improves attribution
   beyond Git history and the notice.
4. Explain prominently that GUISkinDose is a maintained fork derived from PySkinDose. Preserve GitHub's fork banner;
   do not imply upstream endorsement or erase upstream authorship.
5. Review all badges, screenshots, documentation domains, issue links, citation metadata, container/application IDs,
   and release artifact names. Copy no issue, release, Actions log, or attachment without privacy admission review.

**Exit criteria**

- User-facing identity is GUISkinDose everywhere except intentional provenance/migration text.
- Wheel/sdist installation, `guiskindose` imports, CLI/module launch, GUI launch, resources, and documentation examples
  behave as documented from clean environments.
- Attribution and license checks pass.

### Phase 6 — Final candidate verification and private history audit

1. Run the complete test matrix on every supported Python version and OS available in CI.
2. Run:
   - strict sensitive-content and approved-asset gates;
   - ignored/untracked artifact checks;
   - privacy and OWASP Semgrep;
   - HoundDog;
   - phi-scan with baseline expiry validation;
   - structured and targeted clinical-person Presidio;
   - image OCR inventory scan;
   - safe DICOM scan and DICOM structural validation;
   - Gitleaks, dependency audits, type checking, linting, docs/link checks, and release build checks.
3. Verify tests leave the checkout byte-for-byte clean outside documented caches.
4. Inspect built wheels, source distributions, documentation output, native bundles, and release artifacts as fresh
   candidate assets. Confirm they do not contain the old DICOM bytes, old Git metadata, absolute paths, reports,
   scanner caches, or unexpected identifiers.
5. In an approved private environment, finish the preliminary history audit across all old reachable branches, tags,
   pull-request refs available locally/remotely, LFS objects, release assets, commit messages/trailers, GitHub issue and
   Actions attachments, and any archived bundles using value-suppressed output.
6. Individually review and record provenance/disposition for the four earlier DICOM fixture versions and two removed
   RDSRs found outside the current inventory. Do not promote their raw values, paths, or hashes into public logs.
7. Distinguish public attribution/contact emails from accidental local-path PII and clinical identifiers; remove or
   retain each category according to purpose and consent rather than treating every email as PHI.
8. Classify the result:
   - no validated exposure: retain the existing fork history and record the reviewed historical observations;
   - possible/validated exposure: activate the incident runbook, preserve evidence privately, and coordinate history,
     fork/cache, and GitHub Support actions before publication claims.

**Exit criteria**

- Current tree and distributable artifacts are clean under every configured gate.
- Historical audit status and limitations are recorded privately and summarized publicly without identifiers.
- A maintainer signs off on the exact filesystem tree to republish.

### Phase 7 — Verify and rename the existing fork

1. Confirm the in-repo product/import/package rename from
   [GUISKINDOSE_RENAME_PLAN.md](GUISKINDOSE_RENAME_PLAN.md) is merged (or complete it here) and that remaining
   privacy changes are on the existing branch without rewriting any parent commit, tag, or ref.
   After the GitHub rename, update live `github.com/kgrizz-git/MyPySkinDose` links, `CITATION.cff` URLs,
   `sonar.projectKey` / `sonar.projectName` (only after the SonarCloud project is renamed to match), and
   ReadTheDocs if that project is renamed.
2. Create reviewed commits with value-safe messages; do not force-push, orphan, squash the public lineage, or run a
   history filter unless a newly validated incident specifically requires it.
3. Before the GitHub rename, verify the complete gate from a fresh clone of the existing fork and inspect build/release
   artifacts independently of the dirty development checkout.
4. With explicit maintainer approval, rename the existing GitHub repository from `MyPySkinDose` to `GUISkinDose`.
5. Verify GitHub still reports the repository as a fork of PySkinDose and preserves issues, pull requests, settings,
   default branch, stars/watchers, and redirects from the old URL.
6. Update the local `origin` URL explicitly even though GitHub redirects old URLs. Retain the PySkinDose `upstream`
   remote for future comparisons and document the expected pull/merge policy.
7. Re-run privacy, build, install, link, badge, clone, and fork-relationship checks using the new repository URL.

**Exit criteria**

- The renamed repository retains its history and GitHub fork relationship without a force-push.
- All privacy, build, test, license, attribution, redirect, and fresh-clone checks pass.

### Phase 8 — Publish GUISkinDose deliberately

1. Configure branch protection/rulesets, required CI, secret scanning/push protection where available, dependency
   alerts, least-privilege Actions permissions, environments, and trusted publishing.
2. Run all CI and release dry runs before creating the first GUISkinDose release.
3. Review repository description, topics, README attribution, issue templates, Pages/docs output, Actions logs, and
   generated artifacts for sensitive content.
4. Review existing issue bodies, comments, attachments, and workflow logs before linking them from new documentation
   or release notes; do not duplicate them into new artifacts without privacy admission.
5. Publish a migration note explaining:
   - GUISkinDose is derived from PySkinDose;
   - public DICOM fixtures were conservatively sanitized from upstream regression fixtures;
   - the existing fork history and GitHub upstream relationship were intentionally retained.
6. Have a second maintainer/reviewer confirm the exact remote tree, rulesets, workflows, and release settings.
7. Create the PyPI project through a reviewed pending Trusted Publisher or attach a normal Trusted Publisher to an
   existing maintainer-owned project. Use a protected `pypi` environment and least-privilege OIDC permissions.
8. Publish the first GUISkinDose package/release from reviewed CI, not by copying an old release asset.

**Exit criteria**

- Public GitHub and package artifacts derive from the renamed, reviewed fork revision.
- Required privacy gates block merges/releases.
- Upstream attribution is prominent and accurate.

### Phase 9 — Post-rename and post-publication verification

1. Confirm old GitHub URLs redirect to the renamed fork and that package metadata, documentation hosts, citations,
   downstream links, local remotes, and installation instructions use the new identity.
2. If actual sensitive data is later validated, follow GitHub's sensitive-data removal process, including
   `git-filter-repo` where appropriate, collaborator/fork coordination, and GitHub Support for cached/PR/LFS refs.
3. Perform fresh-clone verification on Windows, macOS, and Linux where available.
4. Monitor the first scheduled phi-scan, Presidio, OCR, dependency, and release runs; triage every advisory.
5. Verify the protected-ignore and conditional-receipt gates against a safe synthetic pull request and confirm missing
   local hooks are still caught by required CI.
6. After a stable observation period, archive this completed plan and the superseded portions of
   `PRIVACY_HARDENING_PLAN.md`, updating `dev-docs/index.md` in the same change.

**Exit criteria**

- Redirects, fork metadata, and downstream links resolve to GUISkinDose.
- Fresh users receive correct install/import/migration guidance.
- Scheduled scanners and release gates pass from the renamed public fork.

## 5. Verification matrix

| Boundary | Required evidence |
|---|---|
| DICOM headers/private data | Deterministic transformation manifest, zero unapproved private tags, value-safe scanner results, human review |
| DICOM structure | pydicom read/write, file-meta/UID consistency, independent structural validation where practical |
| Physics behavior | Parser comparison, normalized geometry equality, dose/golden regression equality |
| Tabular fixtures | Synthetic UID uniqueness/relationship tests, phi-scan, structured and targeted Presidio |
| Images/rendered documents | Local OCR known-positive proof, changed-asset scan, human visual review, inventory hash |
| Runtime privacy | Privacy Semgrep, HoundDog, sentinel log/UI/export tests |
| Repository admission | Strict sensitive-content gate, commit/CI metadata checks, ignored/untracked artifact gate |
| Rename | Stale-brand allowlist check, canonical-import/CLI/GUI/API tests, configuration migration test |
| Python packaging | Wheel/sdist inventory and metadata review, clean install/import/resource/uninstall tests, TestPyPI dry run |
| Project etiquette | License/provenance, author/maintainer roles, security/contribution/citation files, reviewed project URLs |
| Fork-preserving rename | Existing ancestry/fork banner preserved, no force-push, redirects and fresh-clone gate verified |
| Conditional scanner enforcement | Protected ignore policy, index-bound routing receipts, missing-tool failure, required CI parity |
| Publication | Private CI pass, settings review, newly built release artifacts, second reviewer approval |

## 6. Rollback and stop conditions

- Stop DICOM replacement if any physics/geometry value changes unexpectedly; retain private source material only in
  the approved recovery location while the transform is corrected.
- Stop OCR/Presidio promotion to blocking if known negatives produce unmanageable noise or known positives are missed.
- Stop the rename if distribution/repository namespace ownership cannot be established safely; do not publish under
  an ambiguous or impersonating name.
- Stop publication if any scanner fails to run, reports raw values, leaves persistent output, or returns an
  untriaged finding.
- Stop public migration if the historical audit validates an exposure; switch to incident-response coordination.
- Before the GitHub rename, roll back ordinary commits normally. After the rename, use GitHub's supported repository
  rename and redirect behavior; never use a force-push merely to repair branding or packaging mistakes.

## 7. Completion definition

This plan is complete only when GUISkinDose is publicly available from the verified, renamed GitHub fork and PyPI as
the `guiskindose` distribution and canonical import package, the current DICOM/tabular fixtures contain only reviewed
synthetic identifiers, targeted text/image/DICOM admission checks are operational, attribution to PySkinDose is
prominent, old-repository disposition matches the private audit outcome, and the first scheduled/release privacy
checks have completed successfully.
