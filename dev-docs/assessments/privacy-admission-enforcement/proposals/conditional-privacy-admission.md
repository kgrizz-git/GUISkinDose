# Security Hardening Proposal: Conditional Privacy Admission

_Accepted and implemented on 2026-07-16. See the parent hardening review for residual validation work._

## Decision

Choose how the repository proves that protected output paths remain untrackable and that the correct secondary
privacy tools ran for the exact content being proposed.

## Executive Recommendation

The complete option set is:

- **Option 1: Strengthen guidance and current hooks.** Clarify trigger rules and keep the existing independent hooks
  and path-filtered workflows.
- **Option 2: Run every scanner on every push.** Make the complete scanner set mandatory regardless of changed paths.
- **Option 3: Route conditionally with content-bound receipts.** Centralize trigger policy, protect ignore/never-track
  rules, and require private receipts tied to the exact staged content and scanner configuration.

I recommend Option 3 under the current constraints. I inspected the current controls and found that the core problem
is not a lack of scanners; it is that scanner applicability and successful execution are not represented by one
machine-checkable decision. A tracked “last run” timestamp would preserve that weakness because it says nothing about
which staged bytes or tool configuration were evaluated.

## Evidence

| Evidence | Finding or document | What it establishes |
|---|---|---|
| `E1` | Current hook configuration | Deterministic gates are blocking, but expensive secondary tools are not centrally routed. |
| `E2` | Current ignore and ignored-asset controls | Risky artifacts are checked, but required ignore rules and never-track roots are not one protected policy. |
| `E3` | Current HoundDog wrapper | Findings fail, but missing/failed scans return success and therefore cannot prove execution. |
| `E4` | Presidio and phi-scan workflows | Public-runner-safe text tools already support changed-path and weekly execution. |
| `E5` | Agent playbook and privacy policy | Conditional routes are documented, but instructions alone cannot resist `--no-verify` or missing tools. |

`E1`–`E5` are observed from `.pre-commit-config.yaml`, `.gitignore`, `scripts/check_ignored_asset_files.py`,
`scripts/check_sensitive_content.py`, `scripts/run_hounddog_advisory.py`, `scripts/run_presidio_advisory.py`, the two
secondary scanner workflows, and the privacy guidance. We infer from their separate ownership that future routing can
drift even if each individual control remains correct.

## Current Design And Failure Mode

Today a contributor or agent reads the routing rules, stages content, and reaches several independent controls. The
blocking deterministic gate scans tracked content and requires hash-pinned review for risky assets. Presidio and
phi-scan have path-filtered CI workflows. HoundDog is a local pre-push advisory. OCR and a safe DICOM wrapper are
prerequisites in the active privacy/rename plan and are currently absent.

This is a solid baseline, but the proof chain has gaps. Removing an important `.gitignore` rule is not itself a policy
violation. A file can be force-added from an ignored output root. HoundDog can be absent and still return zero. Most
importantly, there is no artifact saying “scanner X, with configuration Y, evaluated staged blob set Z successfully.”
Written agent instructions improve behavior but cannot establish that fact.

## Desired Invariants

- Every required ignore pattern remains present unless the versioned privacy policy changes in the same reviewed
  commit.
- No file under a never-track root can be committed, even when force-added.
- Scanner selection is deterministic from the exact staged paths and diff categories.
- Every required expensive local scan has a clean or explicitly reviewed receipt bound to the exact staged blobs,
  scanner version, and configuration digest.
- Missing tools and incomplete scans are distinguishable from clean scans and fail closed when triggered.
- Receipts contain no raw paths, source values, OCR text, DICOM values, or reports.
- Required CI independently enforces the same policy and catches local-hook bypass.
- Findings are fixed or receive a narrow, expiring, content-bound disposition; they are never silently ignored.

## Constraints And Non-Goals

The design must remain cross-platform and keep clinical-looking input local. It must not add scanner reports to Git,
upload local-only data, or make a model result the authority that de-identifies an asset. It does not attempt to stop
the operating system from creating a file or Git from adding it to the index: standard Git has no reliable pre-add
hook. The enforcement boundary is commit, push, and merge.

No scanner latency, memory, or model-cache benchmark has been measured. Tradeoff directions below are source-derived
or hypothetical and must be validated during implementation.

## Before Architecture

[Before architecture](../diagrams/conditional-privacy-admission-before.mmd)

The current design has several useful enforcement points, but the guidance, hook routing, and CI path filters can
evolve independently. A successful local advisory skip is especially ambiguous because it looks like hook success.

## Options

### Option 1: Strengthen guidance and current hooks

This option keeps the current structure. We would add more precise trigger tables to agent/contributor documentation,
add a direct check for selected `.gitignore` lines, and tighten obvious wrapper exit codes. Its strongest case is low
implementation cost: the deterministic gate and CI workflows already provide substantial protection.

Its residual risk is human and configuration drift. There is still no content-bound proof that an expensive tool ran,
and every new scanner needs coordinated edits across documentation, pre-commit, CI, and workflow path filters.

[Option 1 architecture](../diagrams/conditional-privacy-admission-guidance-after.mmd)

| Change | Before | After | Security consequence | Cost |
|---|---|---|---|---|
| Routing guidance | Distributed prose | More explicit distributed prose | Fewer accidental omissions, no execution proof | Low |
| Ignore protection | Indirect asset checks | Selected line checks | Detects simple removal | Low |
| Scanner completion | Mixed exit semantics | Some tightened wrappers | Reduces ambiguous skips | Low–medium |

Rollback is a normal revert of documentation and focused checks. This option is appropriate as an interim step, but I
would not consider it the durable answer to the user's enforcement goal.

### Option 2: Run every scanner on every push

This option removes routing uncertainty by invoking deterministic checks, Presidio, phi-scan, HoundDog, OCR, and
DICOM scanning for every push. The attractive part is conceptual simplicity: applicability cannot be misclassified
because every tool always applies.

The cost mechanism is also straightforward. NLP model startup, OCR dependencies, DICOM tooling conflicts, model
caches, and repository-wide scans become part of every developer's critical path. A missing irrelevant tool blocks an
unrelated documentation or source-only change. That increases pressure to use `--no-verify` and makes cross-platform
reliability depend on the least portable scanner. CI could reproduce public-safe tools, but local-only DICOM or
HoundDog policy still creates asymmetry.

[Option 2 architecture](../diagrams/conditional-privacy-admission-run-all-after.mmd)

| Change | Before | After | Security consequence | Cost |
|---|---|---|---|---|
| Scanner routing | Conditional and distributed | All scanners always run | Eliminates false-negative routing | High latency/dependency burden |
| Missing tools | Some advisories skip | Any missing tool blocks | Strong completion semantics | Lower availability for unrelated work |
| CI parity | Tool-specific | All permitted tools run | Stronger bypass resistance | Higher CI time and model setup |

Rollback is simple configuration removal, but adoption would be disruptive until all scanners are pinned, portable,
and benchmarked. Option 2 becomes preferable if measured full-suite latency is small and every tool can be made a
supported default dependency.

### Option 3: Route conditionally with content-bound receipts

This option introduces one versioned privacy-admission policy and one router. The policy owns required ignore rules,
never-track roots, path/diff triggers, scanners, versions/configuration digests, and disposition requirements. The
router reads the Git index, computes the applicable scanner set, and explains the decision with value-safe path
tokens. Cheap checks may run immediately; expensive tools run through safe wrappers and create receipts below the
repository's Git metadata directory.

A receipt is not a mere timestamp. It binds the scanner ID/version, policy and scanner configuration digest, exact
relevant staged blob hashes, result state, and completion time. The pre-push verifier rejects a missing, expired,
failed, or content-mismatched receipt. If a staged blob or scanner configuration changes, the old receipt no longer
matches. A tracked disposition may close a reviewed false positive only when its fingerprint, content hash, reviewer,
reason, and expiry match.

This centralizes policy without placing raw scanner evidence in Git. It also lets CI use the same router against the
PR diff and rerun every public-runner-safe tool independently. Local-only receipts are useful developer enforcement,
not a substitute for CI. What gives me pause is implementation complexity: index semantics, renames, partial staging,
worktrees, and Windows Git paths all need synthetic tests. That cost is proportionate because the router becomes the
single place future scanners are added.

[Option 3 architecture](../diagrams/conditional-privacy-admission-receipts-after.mmd)

| Change | Before | After | Security consequence | Cost |
|---|---|---|---|---|
| Ignore/track policy | `.gitignore` plus separate scripts | Versioned required-ignore and never-track policy | Force-add and ignore-rule removal are blocked | Medium implementation |
| Scanner selection | Prose and independent filters | One staged-content router | Applicability is deterministic and testable | Medium migration |
| Execution proof | Console exit only | Private content/config-bound receipt | Stale or skipped scans cannot appear clean | Medium state management |
| Findings | Tool-specific triage | Expiring value-free dispositions | Findings cannot be silently ignored | Review workflow |
| Bypass resistance | Local hooks plus separate CI | Shared policy, independent CI execution | `--no-verify` cannot merge | CI integration |

Rollback can disable receipt requirements while retaining deterministic gates and CI scanners. The versioned policy
and wrappers should be introduced in report-only mode first, then promoted trigger class by trigger class after known
positive/negative tests and runtime measurements pass.

## Comparison

| Dimension | Option 1: Guidance/current hooks | Option 2: Run everything | Option 3: Conditional receipts |
|---|---|---|---|
| Security | Improves clarity; execution gaps remain | Strong applicability, strong completion | Strong applicability/completion with tested routing |
| Performance | Near current behavior | Highest recurring latency | Cost only for relevant changes |
| Memory | Near current behavior | All models/tools may load | Relevant model/tool only |
| Reliability | Few new failure modes | Least portable tool blocks all pushes | Router/state complexity; failures scoped by trigger |
| Operability | Distributed controls remain | Simple policy, expensive operation | One policy/receipt system to maintain |
| Migration | Lowest | High immediate disruption | Incremental report-only rollout |

## Recommendation

I recommend Option 3. It directly satisfies the requested enforcement property while preserving the project's useful
distinction between fast deterministic gates and heavyweight secondary review. Option 1 should be the tactical state
during implementation. We should switch to Option 2 only if benchmarks show its simplicity does not create material
developer or CI friction.

## Evidence Coverage And Residual Risk

| Evidence | Option 1 | Option 2 | Option 3 |
|---|---|---|---|
| `E1` — distributed hooks | Mitigates | Addresses routing | Addresses through central policy |
| `E2` — unprotected ignore rules | Mitigates selected lines | Unaffected unless separately added | Addresses with required-ignore/never-track gate |
| `E3` — ambiguous HoundDog skip | Mitigates with wrapper fix | Addresses | Addresses and proves exact-content execution |
| `E4` — path-filtered text workflows | Unaffected | Replaced by full runs | Consolidated under shared routing |
| `E5` — instruction-only agent routing | Mitigates | Addresses by removing conditions | Addresses with machine-checkable conditions |

Residual risks remain: hooks can be bypassed locally, scanner false negatives remain possible, receipts can be forged
by a malicious local developer, and public CI cannot safely reproduce every local-only scanner. Required CI, human
asset review, synthetic detector tests, and code review remain necessary. This proposal is aimed at accidental drift
and honest-agent enforcement, not hostile maintainer compromise.

## Migration And Rollout

Introduce the policy and router in report-only mode while current gates remain blocking. Add protected-ignore and
never-track checks first because they need no external scanner. Then give each wrapper explicit clean/finding/not-run
states, implement private receipt storage, and enable one trigger family at a time: tabular text, sensitive code,
DICOM, then rendered imagery. CI parity must exist before a trigger becomes required. Rollback disables the receipt
requirement for that family while retaining deterministic admission and scheduled scans.

## Validation Plan

- Unit-test staged additions, modifications, deletions, renames, partial staging, worktrees, and Windows-style paths.
- Prove required ignore patterns cannot be removed and forbidden roots cannot be force-added.
- Prove a receipt fails after any relevant blob, policy, config, scanner version, result, or expiry change.
- Prove unrelated changes do not require heavyweight tools.
- Exercise synthetic known-positive and known-negative DICOM, image, tabular, clinical-person, and code-dataflow cases.
- Measure wall time, peak memory, model-cache behavior, and false-positive review load per trigger family.
- Open a safe synthetic PR with local hooks bypassed and verify required CI blocks it.
- Capture hook/CI output and verify it contains no matched values, raw OCR, DICOM fields, raw reports, or default paths.

## Implementation Work Packages

- Define the policy schema and trigger taxonomy.
- Implement protected-ignore/never-track index checks and tests.
- Normalize scanner wrapper result contracts.
- Implement staged-snapshot routing and private receipt creation/verification.
- Implement value-free, expiring advisory dispositions.
- Wire pre-commit, pre-push, CI, and weekly full scans to the shared policy.
- Add OCR and safe DICOM wrappers before enabling those receipt requirements.
- Update contributor/agent documentation and hook setup help.

## Open Questions

- Which exact output roots should be permanently never-track versus allowed only through approved-asset inventory?
- Should HoundDog remain local-only, or can a reviewed public CI runner execute it without report upload?
- What receipt expiry is appropriate for each scanner after runtime/model-update measurements?
- Should targeted clinical-person scanning apply only to sensitive field names and clinical prose, or also selected GUI
  help and release text?
