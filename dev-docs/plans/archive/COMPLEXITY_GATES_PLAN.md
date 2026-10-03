# Complexity Gates with Grandfathered Caps and Ratchet

Status: Completed and archived 2026-10-03
Created: 2026-10-02
Original backlog: `dev-docs/TO_DO.md` → Next Up (removed on completion)

## Goal and metric decision

Enforce a complexity ceiling without refactoring every existing complex function
in one PR. New functions meet the default limit; grandfathered caps can only
decrease or disappear.

Use Ruff `C901` (McCabe cyclomatic complexity) with a maximum of **10**.
The preliminary inventory found Ruff's JSON output suitable for scores and
locations, but its function names are bare. Resolve full names with Python AST
as described below. Invoke the `uv.lock` Ruff version through the locked
environment, and check the separate `ruff-pre-commit` revision for drift.
`PLR0912` counts branches and is out of scope for v1. SonarQube `python:S3776`
measures cognitive complexity; retain it as a separate review signal. Its
snapshot finding count belongs in the linked TODO, not in the gate baseline.

Implementation decision record (2026-10-03):

| Decision | Result to record |
|---|---|
| Analyzer | Ruff `C901`, locked version 0.16.2; `uv run --locked ruff check --select C901 --output-format json src scripts` |
| Threshold | 10; new functions at 11 or above fail |
| Scope | 211 Python files under `src/` and `scripts/` after adding the checker and helper |
| Baseline | 20 findings (14 `src/`, 6 `scripts/`); maximum 25; review exact cap diff at bootstrap |
| Key grammar | AST-synthesized `Class.method`, `outer.nested`, decorated/async names unchanged; verify edge cases in tests |
| Runtime | Full checker cold run about 0.33-0.42 s on the target laptop (2026-10-03, two runs, incl. Ruff 0.16.2) |

The comparison inventory found lizard 1.23.0 reported 88 functions above
its CCN limit of 10, versus Ruff's 20; its scores are not interchangeable.
Lizard also requires class-name recovery from AST and does not offer JSON.
In a nested-function probe Ruff scored the outer function 12 and inner 11,
while lizard scored outer 3 and inner 11. Ruff's metric thus includes nested
branches in the enclosing score. This is the chosen attribution behavior;
do not reinterpret existing caps with lizard's metric.

## Scope and cap format

Scan every Python file under `src/` and `scripts/`, including the checker.
Exclude `tests/` for v1 because test helpers often encode scenario matrices;
assess expansion later. `tools/` contains the standalone Semgrep environment.
Generated help and UI-copy mirrors are non-Python and outside the metric.

Store exceptions in `dev-docs/complexity_caps.json`: UTF-8 JSON with a final
newline, metadata (`schema_version`, `metric`, `tool_version`, `threshold`),
`caps` entries of `{path, function, cap}`, and `migrations` for reviewed renames.
Use positive integer scores and caps. Sort by POSIX-style, case-sensitive,
repository-relative path and qualified function name. Reject duplicate keys and
noncanonical formatting; serializing twice must yield identical bytes. Key
methods as `Class.method`; nested names include lexical parents. Decorators do
not change identity, async functions follow the same rule, and line numbers are
never part of keys. Join each Ruff finding's `location.row` to a `def` or
`async def` in an AST walk of that file to synthesize the key; the row identifies
the definition even when decorated. Reject missing or ambiguous joins and
collisions **after** synthesis. The initial file lists
only functions above the default limit, using measured values, not Sonar scores.

## Checker and ratchet

Implement `scripts/check_complexity.py` with `--check` (default), `--update`,
one-time `--bootstrap`, and `--migrate OLD_PATH:OLD_FUNCTION
NEW_PATH:NEW_FUNCTION`. Give the module and each function concise docstrings;
factor validation rules so the checker itself passes the gate.

`--check` scans the full scope and rejects an unlisted over-limit function, a
listed function over cap, a stale entry, analyzer/version drift, or a cap above
the current measured score. For the last case print the exact `--update`
command. `--update` only lowers or removes entries; it never adds or raises
them. The developer inspects and stages its diff. CI reruns `--check` against
checked-in bytes. Decreases still require normal PR review so a mechanical
score drop does not conceal poor decomposition.

`--bootstrap` works only when neither the branch nor its base has a cap file;
it creates the initial reviewed baseline. It is not a routine escape hatch for
new complex code. A later new exception requires an explicit policy change and
reviewed reason. Renames are new functions by default. `--migrate` atomically
removes the old cap and adds the new key at no higher than the old cap or current
score. Record old/new keys and caps in the `migrations` array. CI compares each
new mapping with the base file, validates one-to-one old-key removal and
nonincreasing cap, and requires code review of the move. Only bootstrap writes
metric and tool-version metadata; update and migrate must preserve them.
Preserve migration records as provenance. Resolve concurrent cap-file conflicts
by retaining both reductions and canonical ordering.

## Base comparison and enforcement

Use portable `pathlib` and `subprocess` argument lists, without shell pipelines.
Live-tree validation runs even if base resolution fails. For cap history:

- Local pre-push compares with the current `origin/main` tip. Missing base or
  Git error fails closed: comparing only with `HEAD` cannot prove a committed
  cap change has not raised the limit. Print a command to update `origin/main`
  and rerun. A stale local ref may miss newer cap reductions; PR CI fetches the
  current base branch and is authoritative.
- PR CI reads `GITHUB_BASE_REF`, fetches `origin/$GITHUB_BASE_REF`, then
  compares with that branch's current tip; missing base fails closed. The
  checkout already has `fetch-depth: 0`. On a `main` push, the workflow sets
  `COMPLEXITY_BEFORE_SHA` from `${{ github.event.before }}`; compare against
  that SHA and fail closed if it is unavailable locally. Local pre-push leaves
  both CI context variables unset and uses `origin/main` as above.
- Reject raised caps, unexplained added entries, and unauthorized metric
  metadata changes, even in a caps-only commit. A decrease/removal passes only
  if live-tree `--check` also passes. The initial file is permitted only by the
  bootstrap rule.

Wire `--check` as a `language: system`, `pass_filenames: false`,
`always_run: true`, `stages: [pre-push]` hook and use the same command in the
`static-analysis` CI job. Pass base context with explicit environment variables.
Aim for a cold full-tree run under 10 seconds on a developer laptop; if it
misses that budget, revisit tool choice before introducing a cache. Errors name
the function and the exact repair command.

## Verification and completion

Add `tests/unittests/test_complexity_gates.py` using temporary synthetic Python
trees outside the scanned scope. Cover new over-limit, within-cap, above-cap,
reduced, deleted, and renamed functions; update and migration behavior; raised,
duplicate, stale, and newly added caps; tool-version mismatch; missing local/CI
bases; PR/main comparisons; caps-only changes; and byte-identical repeated runs.
Assert actionable messages and Windows-compatible path normalization.

Run focused tests, the full-tree checker, pre-push hook, and matching CI command.
Document the limit, schema, regeneration, review, and Sonar distinction in
`dev-docs/HARNESS_ENGINEERING.md`; register the script and caps file in
`dev-docs/index.md`. Update `AGENTS.md` if contributor workflow changes. Log
harness work in `dev-docs/MAINTENANCE_LOG.md`; if implementation changes `src/`
or `tests/`, satisfy the changelog gate too.

Record the final metric, version, threshold, measured baseline, key grammar,
and cold runtime above. Confirm pre-push and CI enforcement and ratcheting.
Remove the TODO item in the same PR, archive this plan, and update the index.
