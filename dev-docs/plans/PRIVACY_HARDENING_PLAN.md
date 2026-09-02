# Privacy and PHI/PII Hardening Plan

_Status: Implemented through Phase 9; Phase 10 private history/release-object audit requires an approved private environment_
_Created: 2026-07-15_
_Owners: Maintainers; coding agents may implement individual phases_
_Related policy: [PRIVACY_AND_SENSITIVE_ASSETS.md](../PRIVACY_AND_SENSITIVE_ASSETS.md)_
_Scanner reference: [LOCAL_PII_MODELS.md](../references/LOCAL_PII_MODELS.md)_
_Follow-on republication plan: [GUISKINDOSE_PRIVACY_REPUBLICATION_PLAN.md](GUISKINDOSE_PRIVACY_REPUBLICATION_PLAN.md)_

## 1. Objective

Prevent GUISkinDose application code, tests, tooling, exports, logs, temporary files, CI output, and tracked assets
from exposing unredacted filenames, paths, DICOM identifiers, study identifiers, or other PHI/PII without an explicit
and informed user action.

This plan strengthens several different boundaries. No single scanner is expected to cover all of them:

1. **Runtime dataflow:** sensitive values must not reach logs, tracebacks, stdout, UI error messages, or unintended files.
2. **Intentional exports:** clinical identifiers are excluded by default and require an explicit opt-in.
3. **Repository admission:** tracked content and filenames are scanned; opaque assets require hash-pinned human review.
4. **Test containment:** automated tests may write only to isolated temporary locations and must leave the checkout clean.
5. **Scanner safety:** advisory tools run locally or in CI only when their inputs and reports are value-safe.
6. **Historical exposure:** current-tree gates do not replace a private audit of Git history and released artifacts.

## 2. Non-negotiable privacy invariants

- Do not log or print raw source filenames, absolute paths, patient/study/accession/institution/physician identifiers,
  DICOM attribute values, or raw exception messages.
- Do not use `logger.exception`, `exc_info=True`, `traceback.format_exc()`, or equivalent in paths that may process
  clinical data. Diagnostics record an operation code and exception class only.
- Do not automatically create a persistent diagnostic log. File logging is an explicit user opt-in with its location,
  retention behavior, and sensitivity warning shown before creation.
- Use opaque internal exam labels (`Exam 1`, `Exam 2`, stable non-identifying tokens) instead of a study ID or filename.
- Exports exclude source identifiers by default. A separate, plainly labelled option may include them when the user
  deliberately needs an identified clinical record.
- Writes containing clinical or derived dose data require an explicit user action, a disclosed destination, safe file
  permissions where portable, atomic replacement, and overwrite protection.
- Application and test output must not target tracked files. Writes inside a Git checkout are refused unless the path
  is an explicitly approved ignored output root and the user opts in.
- Advisory findings are work items: fix them or record a narrow false-positive disposition with reason, owner, and
  review date. `continue-on-error` must not make findings invisible.
- Automated scanners never approve a DICOM/image/container asset. Human review remains mandatory.
- Removed assets stay removed. Reconcile their inventory entries; never restore a deleted asset merely to satisfy the
  inventory checker.

## 3. Current findings to close

The implementation phases must close these known findings before privacy SAST becomes blocking:

- `analyze_data.py` derives `exam_id` from `study_id` / `original_filename`, adds it to warnings, and logs raw
  filename plus exception text on multi-exam failure.
- `calculate_irradiation_event_result.py` includes `exam_id` in beam-miss warnings.
- `main.py` logs study identifiers, and input preview prints source filename, study ID, and row data.
- GUI calculation handling uses `logger.exception`; figure rendering logs formatted tracebacks.
- GUI save/export paths show raw exception messages to the user.
- Native GUI mode automatically writes a predictable log under the system temporary directory.
- Uploaded files use persistent system temporary files that may remain after a crash.
- Multi-exam stdout, JSON, rich reports, provenance, warning blocks, and download names may include filenames or study IDs.
- CLI rich export defaults beside the input and can overwrite a caller-selected path without an explicit force option.
- Static plot output may be created under `PlotOutputs/` without a pre-write privacy notice.
- The privacy Semgrep scan has known findings but is advisory in CI.
- HoundDog currently reports zero risky dataflows despite the known leaks; it cannot be the enforcement gate.
- Presidio is too noisy on Python source to run on every commit without calibration.
- The phi-scan workflow excludes `tests/fixtures/` and treats findings as an ignored step failure.
- Scanner and gate output normally prints repository paths; a sensitive tracked filename could therefore leak in CI.
- CI does not verify that tests left tracked, untracked, and ignored sensitive artifacts clean.
- Non-loopback GUI hosting has no runtime acknowledgement despite shared process-global clinical state and no auth.
- The baseline sensitive-asset inventory is not yet fully reviewed. Deleted assets may also leave stale entries.

## 4. Delivery order

Implement phases in order unless a phase explicitly says it can run in parallel. Each phase should be a reviewable PR
with tests and documentation. Do not make an advisory scanner blocking until its known findings are resolved and its
output has been proven value-safe.

### Phase 0 — Reconcile the asset baseline and establish fixtures

1. Run the ordinary and strict sensitive-content gates.
2. Compare `git ls-files` with `approved_asset_inventory.json`.
3. Remove inventory entries for assets that were deliberately deleted. Do not restore deleted files.
4. Regenerate `approved_asset_inventory.md` and verify no stale entries remain.
5. For every remaining DICOM:
   - confirm provenance and intended public purpose;
   - inspect all nested sequences and direct-identifier attributes;
   - inspect private tags and private sequences;
   - inspect pixel/graphic content for burned-in identifiers;
   - record reviewer and review date only after completion.
6. Create small synthetic positive and negative privacy fixtures containing fake identifiers. Keep them textual where
   possible; any DICOM/image fixture requires normal inventory admission.
7. Prove each scanner against those fixtures before relying on it.
8. Apply the reviewed fixture dispositions:
   - record that `siemens_axiom_artis.dcm` came from the original public PySkinDose repository and is believed to be
     a test examination acquired on a phantom rather than a patient; treat that provenance as supporting context,
     not as a substitute for the normal DICOM header/private-tag/pixel checklist;
   - approve the golden `.npy` dose-map fixture after confirming it remains a numeric-only NumPy array and its golden
     regression test passes;
   - replace the 21 `IrradiationEventUID` values copied into `generic_rdsr_events.csv` with deterministic test-only
     UIDs (for example, UUID-derived `2.25.*` UIDs), preserving uniqueness and any intended relationships;
   - record the targeted Presidio `PERSON` findings in `ReferencePointDefinition` and `XRayFilterType` as triaged
     categorical-field false positives rather than silently ignoring them.
9. Use reviewer initials or a stable public reviewer handle in the inventory instead of requiring a full legal name;
   `KG` is the reviewer identifier for the current maintainer review.

**Exit criteria**

- Inventory contains exactly the remaining tracked reviewable assets.
- Every remaining asset is approved or intentionally blocks strict mode.
- `python scripts/check_sensitive_content.py --require-approved-assets` passes before strict mode is enabled in CI.
- Synthetic known-positive fixtures demonstrate that each claimed rule actually fires.

### Phase 1 — Central value-safe diagnostics

Add a small privacy/diagnostics module owned by the core package. It should expose structured helpers such as:

- `safe_error_event(logger, operation, exc)` → operation code and exception class only;
- `safe_warning(logger, code, **non_sensitive_metrics)` → allowlisted scalar fields only;
- `opaque_exam_label(index)` → non-identifying label;
- optional path classification helpers that never return a raw clinical filename for logging.

Migrate every runtime log/print/error path:

- remove `logger.exception`, `exc_info=True`, raw exception interpolation, and formatted tracebacks;
- remove raw filenames, paths, study IDs, and DICOM-derived values from log messages;
- keep equipment values only where documented as non-identifying and needed for troubleshooting;
- ensure warning collectors and exported warning blocks receive value-safe messages;
- replace top-level unhandled CLI tracebacks with a generic error code and exception class;
- keep a developer traceback mode only if it is explicit, local, visibly sensitive, and never enabled by default.

Add regression tests that inject sensitive strings into filenames and exception messages and assert they are absent
from console handlers, file handlers, warning collectors, GUI messages, and serialized warnings.

**Exit criteria**

- A repository search finds no prohibited traceback/raw-exception logging in runtime code.
- Known sensitive sentinel values never appear in captured logs or user-facing errors.
- Privacy Semgrep rules for these sinks are clean.

### Phase 2 — Separate identifiers from internal calculation identity

1. Stop setting `exam_id` to `study_id` or `original_filename`.
2. Introduce opaque internal labels and, if needed, a separate in-memory `SourceIdentity` object.
3. Ensure dose calculation, beam-miss warnings, results tabs, geometry selectors, and aggregate calculations use opaque labels.
4. Keep source filenames visible in the upload UI only as an intentional local display, not in logs or calculation warnings.
5. Decide whether study IDs should be displayed at all. If retained, label the field as sensitive and keep it out of
   telemetry, logs, default exports, and error messages.
6. Review public Python result models so default `to_dict()` / `to_json()` output is de-identified. If compatibility
   requires retaining existing fields, add a schema-versioned de-identified default plus an explicit identified variant.

**Exit criteria**

- Internal exam labels cannot contain source-controlled or DICOM-derived text.
- Default dict/JSON/multi-exam stdout output contains no source filename or study identifier.
- Compatibility changes are documented in the changelog and export schema notes.

### Phase 3 — Privacy-aware exports and stdout

Implement a single export privacy policy shared by GUI, CLI, JSON, HTML, PNG, XLSX, PDF, and DOCX:

1. Default `include_source_identifiers=False`.
2. Identified export requires a separate GUI checkbox / CLI flag with a warning that the output may contain PHI.
3. Use privacy-safe default filenames that do not incorporate the input filename.
4. Show the exact destination before native/CLI filesystem writes.
5. Require `--export-path` for CLI filesystem reports, or require an explicit confirmation flag for the default path.
6. Refuse to overwrite an existing file unless `--force` is passed or the native OS dialog confirms replacement.
7. Detect Git worktrees. Refuse writes to tracked/staged paths and require an explicit override for approved ignored
   output roots inside a checkout.
8. Write atomically with restrictive permissions where supported.
9. Treat warnings and report titles as untrusted output: escape HTML, neutralize spreadsheet formulas, and keep them
   free of raw exception text.
10. Add a visible post-write message, but never print an absolute destination or a sensitive basename to logs.

Update Rich Export documentation so “complete audit trail” does not imply identifiers are included by default.

**Exit criteria**

- All default exports are de-identified with privacy-safe filenames.
- Identified export is separately and explicitly authorized.
- Existing/tracked-file overwrite tests cover POSIX and Windows-compatible behavior.

### Phase 4 — Logs, temporary uploads, and generated output lifecycle

1. Disable native GUI file logging by default.
2. Add an explicit diagnostics setting/flag with an in-app notice describing location, retention, and sensitivity.
3. Store opt-in logs under a private per-user application directory, not a predictable shared `/tmp` filename.
4. Use a private per-session upload directory with random filenames and directory permissions restricted to the user.
5. Never copy the original upload basename into the temporary path.
6. Delete uploads when an exam is removed, on clear, and on orderly shutdown.
7. Add startup cleanup for stale session directories after a documented retention limit; acknowledge that secure erase
   is not guaranteed on modern filesystems.
8. Require a user action before static plots or other derived clinical artifacts are written. Surface their destination
   and retention implications.
9. Audit caches, browser downloads, notebook outputs, crash dumps, and third-party logs for additional persistence.

**Exit criteria**

- Normal GUI use creates no persistent diagnostic log.
- Temp files have random non-identifying names, private permissions, bounded retention, and crash-recovery cleanup.
- No automatic derived-data write occurs without a user-visible action or notice.

### Phase 5 — Test and filesystem containment

Add both static and runtime protections:

1. A Semgrep/AST rule flags test writes not derived from `tmp_path`, `tmpdir`, `TemporaryDirectory`, or an approved helper.
2. A pytest session guard snapshots the real checkout and fails if tests modify tracked files or create risky artifacts
   outside approved cache/build directories.
3. Every CI test job runs a post-test cleanliness check covering:
   - `git diff` and staged changes;
   - untracked files;
   - ignored diagnostic/data artifacts, not only PNG/HTML;
   - tracked files accidentally overwritten with generated content.
4. Public CI reports path hashes/rule IDs for a sensitive filename instead of echoing the filename. Local verbose mode
   may reveal the path only on the approved developer machine.
5. Tests use synthetic identifiers only. Manual tests against clinical data live outside the repository and never
   write JUnit, coverage, snapshot, or failure artifacts into tracked paths.
6. Run tests with concise tracebacks and without locals; never use real clinical values in assertion messages.

**Exit criteria**

- A deliberately malicious test that writes a diagnostic file into the checkout fails CI without printing its content.
- All existing tests pass under the containment guard on Windows, macOS, and Linux.

### Phase 6 — Expand and promote project-owned privacy SAST

Extend `.semgrep/mypyskindose-privacy.yml` with focused rules for:

- identifier/path attributes reaching logging, stdout, stderr, UI errors, warnings, and exception constructors;
- `logger.exception`, `exc_info=True`, traceback formatting/printing, and raw exception interpolation;
- filenames/study IDs reaching exported warnings or default serializers;
- filesystem writes outside the approved output API;
- `NamedTemporaryFile(delete=False)` outside the private upload helper;
- direct `Path.cwd()/PlotOutputs` writes without a user-authorized boundary;
- sensitive values captured into warning collectors;
- tests writing outside temporary fixtures.

Use taint rules where they materially improve coverage, with sources including DICOM attributes, `InputProvenance`,
`study_id`, source file/path fields, upload names, and exception messages. Keep rules narrow enough that suppressions are
rare and reviewed.

After Phases 1–5 are clean:

- add `--error` to the privacy Semgrep pre-push and CI invocations;
- remove `continue-on-error`;
- add synthetic rule tests so future Semgrep upgrades cannot silently reduce coverage.

**Exit criteria**

- Privacy Semgrep is blocking locally and in CI with zero unexplained findings.
- Every suppression includes rule ID, reason, and review date.

### Phase 7 — Scanner integration and cadence

#### phi-scan

- Keep version pinned and AI review disabled.
- Continue weekly full tracked-text scanning and add PR diff scanning.
- Reconsider the blanket `tests/fixtures/` exclusion; include text-like fixtures or document narrow exclusions.
- Use baseline/fingerprint mode only for reviewed false positives; fail on new findings.
- Do not upload SARIF, HTML, PDF, JSON, or raw findings until output safety is verified.
- Configure any audit database into a private ephemeral location in CI and document local retention.

#### Presidio

- Do not add to pre-commit yet.
- Calibrate on synthetic docs/fixtures and representative source comments.
- Reduce Python-symbol `PERSON` noise with path scoping, per-entity thresholds, or reviewed recognizer configuration.
- Once useful, run a value-suppressed weekly advisory and on changes to text fixtures/docs likely to contain names.
- Keep model caches local; no hosted inference or report upload.

#### HoundDog

- Keep standalone and local-only; no API key, GitHub App, cloud, managed scans, report upload, PR comments, or AI review.
- Stop printing the absolute repository path from the wrapper.
- Run when logging, file-writing, export, ingestion, API, database, or third-party integration code changes, plus a
  periodic full-source scan.
- Validate it against synthetic project-specific sources/sinks and document its misses.
- Retain Semgrep as the blocking control because the free HoundDog rules cannot be assumed to recognize project fields.

#### dicom-phi-scan and OCR

- Pin a reviewed source commit in an isolated environment; do not depend on an unpublished floating main branch.
- Run locally whenever a DICOM asset is added or changed.
- Prefer a wrapper around the Python API that emits only counts, risk categories, and tag identifiers—not values,
  pixel text, source paths, or JSONL reports.
- If a raw report is unavoidable, write it only under an ignored private temp directory and delete it after review.
- Do not put DICOM pixel scanning in public CI until dependency, model-download, output, licensing, and runner-data
  reviews are complete.
- Evaluate local OCR for non-DICOM images, image-only PDFs, and Office previews using synthetic fixtures.

#### Required cadence

| Trigger | Required checks |
|---|---|
| Every commit / PR | Blocking deterministic gate; blocking privacy SAST after Phase 6 |
| Logging/write/export/ingestion/API code changes | Privacy Semgrep + local HoundDog; triage every finding |
| New/changed tracked text, docs, CSV/JSON/XML | phi-scan diff; Presidio when free text may contain identifiers |
| New/changed DICOM | Strict inventory review + local dicom-phi-scan + header/private-tag/pixel human review |
| New/changed image/PDF/Office/archive/opaque-binary asset | Strict inventory + rendered/container human review; local OCR when available |
| Weekly | Full phi-scan; calibrated value-safe Presidio advisory; review tool updates/findings |
| Monthly / before release | Strict asset gate, full source SAST, ignored-artifact sweep, hook verification |
| Before public release | Private history/tag/release-asset audit and response-runbook exercise |

**Exit criteria**

- Scheduled advisories produce visible, value-safe, triaged results.
- No scanner silently skips because its optional binary/model is missing; scheduled jobs distinguish “clean” from “not run.”

### Phase 8 — Repository admission and filename safety

1. Extend the deterministic gate to inspect tracked path components for contextual MRN/patient/accession/study patterns.
2. Never print a suspected sensitive path in public output; print a rule ID and stable digest.
3. Add `--local-verbose-paths` for approved local triage only.
4. Scan archive member names without echoing them.
5. Keep rejecting tracked logs, traces, pickles, caches, and similar diagnostic artifacts.
6. Expand ignored-artifact detection to JSONL/SARIF/scanner reports and generated clinical exports.
7. Enable strict approved-asset mode in pre-commit and CI once Phase 0 is complete.
8. Add CI checks for PR title/body and push commit messages, because local hooks are not universal.

**Exit criteria**

- A sensitive filename is rejected without appearing in CI logs.
- Strict asset admission is the default everywhere.

### Phase 9 — GUI privacy UX and network boundary

1. Add a concise privacy notice during onboarding and near upload/export actions:
   - processing is local by default;
   - filenames and source data may contain PHI;
   - temporary data lifetime;
   - exports may be clinical records and must be stored appropriately.
2. Clearly label identified-export opt-ins.
3. Keep loopback binding as default.
4. Require a separate `--allow-network` flag plus runtime warning before binding to a non-loopback host.
5. Explain that network mode has no built-in authentication and process-global state may be visible to connected clients.
6. Consider refusing non-loopback mode entirely until per-client state and authentication exist.
7. Register all new warnings/tooltips/help in `ui_copy.json`, `glossary.json`, `help_registry.json`, and the feature-doc matrix.

**Exit criteria**

- A user cannot accidentally expose the GUI on a network with only a host typo.
- Identifier-bearing exports and diagnostics require informed, explicit choices.

### Phase 10 — Historical audit and release gate

1. Create a private, isolated history-audit procedure covering every reachable commit, tag, release branch, LFS object,
   release artifact, and published package.
2. Validate the audit against synthetic known-positive history before trusting a clean result.
3. Keep raw evidence private and value-suppressed in public issues/logs.
4. Complete the response runbook: containment, maintainer notification, legal/privacy escalation, history rewrite,
   credential rotation where applicable, cache/fork limitations, and post-remediation verification.
5. Add a release checklist requiring:
   - strict asset gate;
   - privacy Semgrep;
   - scheduled scanner status reviewed;
   - test-output cleanliness;
   - no untriaged advisory findings;
   - hook/CI configuration current;
   - history audit completed or explicitly revalidated for the release delta.

**Exit criteria**

- The current public history and release artifacts have a documented private audit result.
- Maintainers have rehearsed the finding-response path without using real PHI.

## 5. Scanner finding disposition format

Do not store matched values. A reviewed disposition should contain only:

- scanner and pinned version;
- rule/entity ID;
- relative path or public-safe path digest;
- line/tag/member location when safe;
- status: fixed / synthetic fixture / false positive / accepted temporary risk;
- one-line reason;
- reviewer and review date;
- expiry or follow-up issue for temporary risk.

Prefer source-local suppressions for Semgrep and phi-scan only when the scanner requires them. Keep broader scanner
baselines machine-readable and reviewable, and fail on stale entries after the underlying finding disappears.

## 6. Verification matrix

Each implementation PR runs its narrow tests plus the applicable rows below:

```bash
python scripts/check_sensitive_content.py
python scripts/check_sensitive_content.py --require-approved-assets
python scripts/render_asset_inventory.py --check
semgrep --config=.semgrep/mypyskindose-privacy.yml --error --metrics=off src scripts tests
python scripts/run_hounddog_advisory.py
uv run --extra privacy-scan python scripts/run_presidio_advisory.py
python scripts/check_untracked_scratch.py
python scripts/check_ignored_asset_files.py --strict
python scripts/check_doc_freshness.py
python scripts/check_agent_guidance.py
python -m pytest -q
```

Additional phase-specific tests must cover:

- sensitive sentinel filename and exception-message suppression;
- warning collector and export serialization suppression;
- identified-export opt-in and de-identified default behavior;
- overwrite, tracked-path, and Git-worktree write refusal;
- private temp directory permissions and stale cleanup;
- post-test checkout cleanliness;
- scanner known-positive and known-negative fixtures;
- non-loopback GUI refusal without explicit authorization;
- Windows manual smoke for native dialogs, permissions fallbacks, and path handling.

## 7. Documentation and rollout requirements

Every behavior-changing phase updates the relevant sources of truth:

- `AGENTS.md` and `AGENT_PLAYBOOK.md` for agent triggers and non-negotiable rules;
- `PRIVACY_AND_SENSITIVE_ASSETS.md` for policy and commands;
- `LOCAL_PII_MODELS.md` for scanner versions, boundaries, and evaluation evidence;
- `HARNESS_ENGINEERING.md` for hooks/CI/release validation;
- `FEATURE_INVENTORY.md` for shipped/advisory/blocking status;
- GUI help/UI copy registries for new user notices;
- `CHANGELOG.md` for user-visible behavior, CLI flags, and output schema changes.

When all phases are complete, move this plan to `dev-docs/plans/archive/`, update `dev-docs/index.md`, and retain the
lasting policy and command details in the non-plan source-of-truth documents.
