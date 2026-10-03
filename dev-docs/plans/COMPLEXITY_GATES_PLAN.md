# Complexity Gates with Grandfathered Caps and Ratchet

Status: Active execution plan
Created: 2026-10-02
Backlog: [TO_DO.md](../TO_DO.md) → Next Up

## Goal

Enforce a local and CI complexity ceiling without requiring all existing complex
functions to be refactored in one PR. Existing exceptions receive exact,
function-specific caps. New functions must meet the default threshold. When an
exception becomes simpler, its cap decreases automatically and cannot rebound.

## Current state and metric decision

- SonarQube reports 26 `python:S3776` findings, but it is not a local pre-push gate.
- Ruff currently selects neither `C901` nor `PLR0912`; no lizard gate runs in
  pre-push or CI. Ruff `C901` and lizard measure cyclomatic complexity, while
  SonarQube `S3776` measures cognitive complexity. Their counts and thresholds
  must not be compared as if they were the same metric.
- First run a reproducible inventory on `src/` and `scripts/` using the candidate
  tools. Choose **one pinned metric and implementation** based on whether it
  gives stable per-function identifiers, nested-function coverage, and usable
  diagnostics. Record the chosen version, scope, threshold, and observed
  baseline in this plan before enabling enforcement. Keep SonarQube as a separate
  review signal; this gate need not eliminate the existing S3776 findings.

## Design

1. Create a checked-in, machine-readable cap file keyed by normalized repository
   path plus qualified function name. Record only functions over the default
   threshold, with the measured cap and metric/version metadata. Generate its
   initial values from the chosen tool, then review the list and counts. Do not
   hand-copy SonarQube values into it.
2. Implement one deterministic checker that scans the full scoped tree. Reject
   duplicate keys, invalid caps, stale paths/functions, and tool/version drift.
   A function without an exception must meet the default threshold. A listed
   function must stay at or below its cap. New or renamed functions cannot inherit
   an old exception implicitly.
3. Make the ratchet automatic: when measured complexity drops, the checker
   rewrites/removes the exception to the lower measured value. Check mode fails
   with a clear regeneration command when the checked-in file is stale. Compare
   cap-file changes against the merge base in CI and the pre-push range locally:
   existing caps may only decrease or disappear. Adding a cap requires an
   explicit baseline/bootstrap procedure, not a routine regeneration. A file
   rename or function rename must be treated as a new function unless a reviewed
   migration maps the old key to the new key without raising the cap.
4. Wire the same check command into `.pre-commit-config.yaml` at pre-push and the
   `static-analysis` CI job. Run it on the full scoped tree so a high-complexity
   function cannot evade the gate through path selection. Pin the analysis tool
   in `pyproject.toml` / `uv.lock` or use the already pinned Ruff installation.
   Keep runtime and diagnostics short enough for a routine push.
5. Document the threshold, cap format, regeneration command, review procedure,
   and relationship to SonarQube in `dev-docs/HARNESS_ENGINEERING.md`; update
   `AGENTS.md` if the contributor workflow changes. Register new script/data
   files in `dev-docs/index.md`.

## Verification

- Test a new function above the threshold, a grandfathered function above its
  cap, and an unchanged grandfathered function: only the last passes.
- Test a reduced function: check mode requests the lower cap, update mode lowers
  it, and a later increase fails. Test deletion and rename behavior.
- Test cap-file manipulation: raised cap, duplicate entry, stale key, added
  exception, and metric-version mismatch fail with actionable messages.
- Run the checker locally, its focused tests, pre-push hook, and the matching CI
  command. Verify behavior on the PR base comparison, including a changed cap
  file with no Python changes.

## Completion

The same pinned checker blocks new or increased complexity in pre-push and CI;
the exception inventory reflects the current baseline and tightens after every
measured reduction. Log the harness change in `dev-docs/MAINTENANCE_LOG.md`,
remove the completed TODO item in the same PR, archive this plan, and update
`dev-docs/index.md`.
