# SonarQube Quality Gate Remediation Plan

**Status:** High-severity remediation complete; historical MAJOR/MINOR backlog
remains separately scoped. The live local Quality Gate is currently a
**new-code** gate; its status is useful evidence, but neither a passing gate nor
complete historical-backlog removal is a delivery prerequisite for this programme.

**2026-08-05 execution note:** the HelpButton unreachable-branch fix and the
`PySkinDoseOutput` case-collision remediation are implemented on the dedicated
remediation branch with focused regression tests. The object API is now
deliberately lowercase-only; the serialized dict/JSON schema is unchanged. An
authenticated loopback scan (run through `direnv exec .`) confirms those two
target rules are absent. The first scan of the configured repository project
(`kgrizz-git_MyPySkinDose`, rather than the obsolete `GUISkinDose` project) found
22 unresolved current `python:S3776` findings. The final scan on this branch
reports zero `python:S3776`, zero `python:S6729`, and zero BLOCKER/CRITICAL
findings. Its local quality gate still fails from 20 MAJOR and 54 MINOR
historical findings; these are follow-up code-quality debt, not a claim that
the high-severity plan is unfinished. The historical inventory and candidate
locations below should therefore be remapped against the configured project
before each subsequent tranche; do not claim Cloud resolution from a
branch-local scan.

This plan addresses the local-only SonarQube findings for
`kgrizz-git_MyPySkinDose`. SonarQube remains an optional second opinion: it does not replace the repository's tests,
Ruff, Basedpyright, Bandit, Semgrep, dependency audits, or privacy-admission
controls. See [SONARQUBE_LOCAL.md](../SONARQUBE_LOCAL.md) and
[HARNESS_ENGINEERING.md](../HARNESS_ENGINEERING.md) for the operational policy.

---

## 1. Baseline, Evidence, and Scope

The latest recorded local analysis indexed **297 inputs** and had **292 open
issues**. The input count is not an issue count. The rule/severity facets below
come from the API query made against that analysis; `.git/sonarqube/last-run.json`
only records a privacy-safe receipt (status, counts, and digests), not the issue
list.

| Severity | Count | Rule breakdown |
|---|---:|---|
| CRITICAL | 82 | `python:S3776` cognitive complexity: 50; `python:S1192` duplicated literals: 31; `python:S6729` NumPy: 1 |
| MAJOR | 74 | `python:S6546`: 32; `python:S8786`: 8; `python:S1172`: 7; `python:S5799`: 7; `python:S1244`: 4; `python:S3358`: 3; `python:S6395`: 2; `python:S7497`: 2; `python:S107`: 2; `python:S1854`: 2; five one-off rules |
| MINOR | 136 | `python:S7498`: 79; `python:S117`: 20; `python:S116`: 11; `python:S8521`: 8; `python:S6353`: 7; `python:S5713`: 4; `python:S1481`: 3; four one-off rules |

The live API also reports **284 Code Smells**, **7 Bugs**, **1 Vulnerability**, and
**0 Security Hotspots**. The vulnerability is `python:S5332` in
`scripts/check_doc_freshness.py:166`, where an external-link recognizer contains
the literal `http://`; it requires explicit false-positive triage or a reviewed
code change. Reconfirm all results at Phase 0 because the server, profile, and
new-code period can change.

### Analysis boundaries

- `src` and `scripts` are analysed as source code. `src/**/example_data/**`,
  `src/**/phantom_data/**`, and `src/**/table_data/**` are excluded.
- `tests` is analysed as test scope, and `tests/**` plus `scripts/**` are excluded
  from the Sonar coverage measure. Thus the coverage work is about executable
  code under `src`, not the scripts that also carry complexity findings.
- `sonar-project.properties` does **not** contain a Quality Gate definition. The
  server-side gate, profile, and whether a condition applies to overall or new
  code must be captured before using any count as a pass/fail claim.
- At the latest live check, coverage was **60.8%** overall, but coverage was not a
  configured Quality Gate condition. The gate has `new_duplicated_lines_density
  > 3` (currently 0.0, OK) and `new_violations > 0` (currently 1, ERROR).

### Phase 0: Re-establish a reproducible baseline

1. Supply `SONAR_HOST_URL` and `SONAR_TOKEN` through the shell environment for
   the local, loopback server. `scripts/run_sonarqube_local.py` reads environment
   variables; it does not load `.env` itself. Do not send this repository to a
   remote SonarQube/SonarCloud instance without the separate review required by
   [SONARQUBE_LOCAL.md](../SONARQUBE_LOCAL.md).
2. Generate coverage and submit one analysis:

   ```bash
   uv run coverage run -m pytest --ignore=tests/gui
   uv run coverage xml
   uv run python scripts/run_sonarqube_local.py
   ```

   A non-zero result with `quality_gate_failed` is expected at this point; the
   receipt must still be written below Git metadata.
3. Query the authenticated local API for the project gate status, its exact
   conditions, and unresolved-issue facets. Record the issue key, rule,
   component, and line in a private working artifact alongside the receipt's
   `source_sha256`, `settings_sha256`, and scanner-version digest. Do not commit
   scanner logs, API exports, tokens, source excerpts, absolute paths, or a
   machine-specific report.
4. Record the current measures and all server-side conditions. Do not describe an
   overall coverage percentage as a gate requirement unless the authenticated API
   shows that condition. The latest measured coverage is 60.8%; 80% is a possible
   maintainability objective, not the current Quality Gate.

**Phase-0 acceptance:** the private receipt and issue inventory have matching
analysis inputs, the exact gate conditions are known, and the listed issue
counts below reconcile with the API facets.

### Immediate Quality-Gate unblock

The live new-code query identifies one blocking issue: `python:S1192` in
`scripts/run_sonarqube_local.py:47`, where the same validation message is repeated
four times. Extract a semantically named module constant, retain the exact
privacy-safe message, and run `tests/unittests/test_run_sonarqube_local.py`.
Then run the local analysis and confirm `new_violations` is zero and
`new_duplicated_lines_density` remains at or below 3.

In the same small PR, triage `python:S5332` at
`scripts/check_doc_freshness.py:166`. This code recognizes external-link schemes;
it does not make an insecure network request. The project owner must either mark
the Sonar finding as a reviewed false positive with that rationale or replace the
recognition implementation without weakening link detection. Do not suppress it
without a recorded reason.

**Immediate acceptance:** the one new-code issue is absent; the vulnerability has
an explicit, reviewed disposition; and the authenticated local-gate result is
recorded. A non-OK result is diagnostic evidence to investigate, not a reason to
stop the wider remediation programme.

---

## 2. Baseline-Debt Scope and Accounting

The first remediation tranche deliberately covers **17 of 50** `S3776` findings:
four core functions, nine GUI functions/components, and four privacy-scanner
functions. This is a quality-debt reduction programme separate from the immediate
new-code gate unblock above. Its expected historical CRITICAL accounting is:

| Milestone | `S3776` | `S1192` | `S6729` | CRITICAL remaining |
|---|---:|---:|---:|---:|
| Baseline | 50 | 31 | 1 | 82 |
| After Phases 1–2 | 50 | 0 | 0 | 50 |
| After Phases 3–5 | 33 | 0 | 0 | 33 |
| After Phase 8 | 0 | 0 | 0 | 0 |

The table is not a claim about the current gate: existing overall CRITICAL issues
do not presently fail it. Recheck the server conditions after every analysis;
future profile or gate changes may make this backlog gate-relevant.

### Residual `S3776` inventory for Phase 8

The 33 residual functions are not a vague follow-up. Re-query them at Phase 0,
then retain the following grouped backlog unless the component/line moved:

- **Scripts (18):** `render_privacy_tool_inventory.py:41`,
  `run_dicom_phi_advisory.py:44`, `run_hounddog_advisory.py:51`,
  `run_image_privacy_advisory.py:122` and `:188`,
  `run_presidio_advisory.py:226`, `check_doc_freshness.py:191`, `:301`, and
  `:479`, `check_feature_doc_matrix.py:72`, `check_help_registry.py:41` and
  `:86`, `check_ui_copy.py:88` and `:137`, `audit_dependencies.py:40`,
  `sync_gui_help.py:70`, `check_file_sizes.py:13`, and `check_licenses.py:149`.
- **Core (3):** `corrections.py:193`, `phantom_class.py:55`, and
  `safe_output.py:35`.
- **GUI application helpers (5):** `app.py:339` and `:431`,
  `exam_loaders.py:197`, `exam_transforms.py:36`, and `export_source.py:28`.
- **Input adapters (3):** `registry.py:147`, `dosetrack.py:173`, and
  `column_mapper.py:128`.
- **Export (3):** `cli_source.py:29`, `metrics.py:127`, and
  `writers/docx.py:41`.
- **Dose calculation (1):** `calculate_irradiation_event_result.py:25`.

The two largest residual script findings (`audit_dependencies.py`, complexity 50,
and `check_help_registry.py`, complexity 43) are significant quality debt despite
not being shipped package code. Do not describe them as minor simply because they
are development tools.

---

## 3. Remediation Phases

### Phase 1: Targeted correctness, clarity, and type cleanup

- **Task 1.1 — `S6729` (1 CRITICAL):** In
  [beam_class.py](../../src/mypyskindose/beam_class.py#L214), replace
  `np.where(hits)` indexing with direct boolean indexing (`hits[hits] =
  bool_entrance`) or an equally clear `np.nonzero` form. This is an API clarity
  cleanup, not a claim that the current one-dimensional indexing is functionally
  incorrect. Preserve the entrance-cell result for plane and non-plane phantoms.
- **Task 1.2 — `S1244` (4 MAJOR):** Triage the equality checks in
  [summary_formatters.py](../../src/mypyskindose/gui/summary_formatters.py#L56),
  [images.py](../../src/mypyskindose/export/images.py#L36),
  [metrics.py](../../src/mypyskindose/export/metrics.py#L167), and
  [registry.py](../../src/mypyskindose/input_adapters/registry.py#L94).
  Do not mechanically replace every equality with `isclose`: zero may be a
  sentinel or an exact division-by-zero guard. For each finding, either make a
  semantics-preserving code change with a regression test, or have the project
  owner mark it a reviewed false positive with a concise rationale in SonarQube.
  A source comment alone does not resolve a Sonar finding.
- **Task 1.3 — `S6546` (32 MAJOR) and `S1172` (7 MAJOR):** Replace legacy
  `typing.Union` expressions with PEP 604 syntax where runtime compatibility is
  preserved by the Python 3.10+ support policy, and remove or deliberately
  consume unused parameters. Keep public call signatures/backward compatibility
  intact; do not rename an externally used keyword argument merely to satisfy a
  linter.

**Acceptance:** the API inventory shows the targeted 1 `S6729`, 4 `S1244`, 32
`S6546`, and 7 `S1172` findings resolved or formally triaged as above, with no
new findings in their changed components.

### Phase 2: Duplicate-literal extraction

- **Task 2.1 — remaining `S1192` (expected 30 CRITICAL after the immediate
  unblock):** Extract repeated literals into the narrowest useful scope: a
  module-level semantic constant for implementation strings, or the existing
  UI-copy mechanism for user-facing, catalogued copy. Do not create a catch-all
  constants module or turn every visual class name into shared configuration.
  Preserve exact labels, class ordering, event names, and help/copy registry
  requirements.

**Acceptance:** all 31 baseline `S1192` findings, including the immediate
gate-unblock finding, are resolved; existing UI-copy and help checks pass; and the
historical CRITICAL count is reduced by 31 from the baseline.

### Phase 3: Core parsing and orchestration

- **Task 3.1 — `S3776` (3):** Refactor `analyze_multiple_exams` in
  [analyze_data.py](../../src/mypyskindose/analyze_data.py#L99), plus
  `analyze_input_file` and `preview_input_file` in
  [main.py](../../src/mypyskindose/main.py#L71), into narrow loading,
  normalization, calculation, and result-formatting helpers. Keep public entry
  points and keyword parameters unchanged. In particular, preserve opaque
  labels, warning counts, HTML-to-dict coercion for multi-exam input, explicit
  sensitive-preview opt-in, and the rule that a failed exam does not discard
  completed exams.
- **Task 3.2 — `S3776` (1):** Refactor
  [rdsr_parser.py](../../src/mypyskindose/rdsr_parser.py#L20) by separating DICOM
  traversal, tag extraction, and DataFrame construction. Preserve the normalized
  DataFrame contract and warning behaviour; this parser is clinical-data
  ingestion code, so characterization tests precede structural changes. Preserve
  the current duplicate-value representation (direct repeated measured values
  use a list and remove dots from their unit code; nested repeated measured
  values use a tuple and retain their unit code) unless a separately reviewed
  compatibility change deliberately alters it. Keep Siemens detector-size
  extraction from acquisition comments intact.

**Acceptance:** these four functions and every extracted helper are at or below
the configured `S3776` threshold, with the RDSR parser, normalizer, multi-exam,
and CLI/integration tests passing.

**Completed 2026-07-18:** extracted the loading, per-exam settings, calculation,
formatting, and preview helpers; added parser and value-suppressed preview
regression coverage; and confirmed via the authenticated local API that there
are zero unresolved `S3776` findings in the three Phase-3 components. Focused
Ruff, Basedpyright, parser/normalizer/multi-exam tests, and the file-size guard
passed. The local gate remained non-OK because of unrelated in-scope backlog.

### Phase 4: GUI decomposition

- **Task 4.1 — `S3776` (1):** Implement the
  [Geometry Tab Refactoring Plan](archive/refactor_geometry_tab_complexity.md)
  (**completed** 2026-07-18).
- **Task 4.2 — `S3776` (1):** Implement the
  [Results Tab Refactoring Plan](archive/refactor_results_tab_complexity.md)
  (**completed** 2026-07-18).
- **Task 4.3 — `S3776` (1):** Implement the
  [Upload Tab Refactoring Plan](archive/refactor_upload_tab_complexity.md)
  (**completed** 2026-07-18).
- **Task 4.4 — `S3776` (6):** Implement the
  [Remaining GUI Components Refactoring Plan](archive/refactor_other_gui_tabs_complexity.md)
  for `export.py`, `_per_exam.py`, `calculate.py`, `data.py`,
  `geometry_preview.py` (`geometry_vendor_notice`), and
  `widgets/import_preview.py` (**completed** 2026-07-18).

**Acceptance:** all nine GUI findings (`geometry`, `results`, `upload`, `export`,
`build_per_exam_section`, `calculate`, `data`, `geometry_vendor_notice`, and
`import_preview.build`) and every newly extracted helper are at or below the
threshold. The affected NiceGUI user tests run with the `[gui]` extra; unit tests
alone are not sufficient for timer, binding, and event-handler changes.

### Phase 5: Privacy scanner decomposition

- **Task 5.1 — `S3776` (4):** Implement the
  [Privacy Scan Refactoring Plan](archive/refactor_check_sensitive_content_plan.md) for
  `has_notebook_embedded_visual_output`, `_pdf_text`, `_container_text`, and
  `run_checks` (**completed** 2026-07-18).

**Acceptance:** all four named functions and every extracted helper are at or
below the threshold; archive/container/PDF/notebook and privacy-admission tests
prove that findings, approval requirements, and failure handling are unchanged.

### Phase 6: Coverage hardening

- **Task 6.1:** Treat coverage as a maintainability objective, not a current gate
  requirement. Use the live 60.8% measure as the starting point unless Phase 0
  records a newer baseline, and agree any numeric target separately before
  implementation. Add tests for observable behaviour and previously untested
  branches introduced or exposed by the refactors; do not add tests that only
  execute layout code for a percentage.
- **Task 6.2:** Use the coverage XML consumed by SonarQube to measure progress,
  and keep GUI interaction tests in `tests/gui/` where a NiceGUI client context
  is required. `scripts/**` cannot raise the Sonar coverage measure because it is
  configured as coverage-excluded.

**Acceptance:** the authenticated local analysis reports the measured coverage,
the agreed maintainability target is met if one was set, and meaningful regression
tests cover the relevant contracts.

### Phase 7: Minor constructor and naming cleanup

- **Task 7.1 — `S7498` (79 MINOR):** Preview then review each constructor-literal
  rewrite. Ruff's `C408` fix is marked unsafe because it can affect comments, so
  use an explicit unsafe-fix review rather than claiming a routine autofix:

  ```bash
  uv run ruff check --select=C408 --fix --unsafe-fixes src scripts tests
  git diff --check
  ```

  Run focused tests for changed code before accepting the diff.
- **Task 7.2 — `S117` (20 MINOR) and `S116` (11 MINOR):** Rename variables and
  fields manually in small, behaviour-preserving batches. Ruff's `N803`, `N806`,
  and `N815` rules diagnose naming violations but do not provide autofixes;
  update references, serialized/public names, and tests intentionally.

**Acceptance:** 79 `S7498`, 20 `S117`, and 11 `S116` findings are resolved with
reviewed diffs and no API/serialization regressions.

### Phase 8: Complete the remaining cognitive-complexity backlog

Work through the 33-function inventory in Section 2 in small, cohesive PRs:

1. **Clinical/core and input/output code:** the three core, three input-adapter,
   three export, and one dose-calculation functions. Characterize calculations,
   normalization, and serialization before extraction.
2. **GUI application helpers:** the five application/load/transform/export-source
   functions, with NiceGUI interaction tests for changed wiring.
3. **Harness and advisory scripts:** the 18 scripts, grouping each scanner or
   documentation harness with its existing unit tests. Preserve privacy-safe
   diagnostics and every command-line exit-code contract.

For every PR, record the baseline issue key/rule/component/line, name the
extracted helpers and their complexity budget, and add tests before declaring the
finding closed. Re-run the local analysis after each batch so line movement does
not hide an unresolved issue.

**Acceptance:** all 33 residual baseline `S3776` issues are resolved with no new
`S3776` findings, leaving zero unresolved historical CRITICAL findings from the
recorded baseline. Re-run the server-side gate after every batch; its status must
be checked rather than inferred from arithmetic.

---

## 4. Verification Gate

Run the smallest relevant tests in each PR and the following full verification
before declaring the programme complete:

```bash
uv run ruff check src scripts tests
uv run basedpyright
uv run bandit -r src
uv run semgrep --config p/owasp-top-ten src
uv run pip-audit
shellcheck scripts/*.sh
uv run pytest
uv run coverage run -m pytest --ignore=tests/gui
uv run coverage xml
uv run python scripts/check_doc_freshness.py
uv run python scripts/check_file_sizes.py
pre-commit run --all-files
uv run python scripts/run_sonarqube_local.py
```

Run the `[gui]` user tests separately when GUI code changed:

```bash
uv run pytest tests/gui/
```

Every changed batch should produce a receipt and record its result against the
exact Phase-0 gate conditions. Investigate unexpected regressions, but do not
block the programme solely because the server reports a non-OK gate while
historical findings remain in scope.
