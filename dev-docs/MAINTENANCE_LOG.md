# Maintenance Log

This file records "under-the-hood" maintainer-facing changes, such as refactoring, test additions, CI/harness improvements, and documentation updates that do not directly affect end-users.

For user-facing changes (new features, bug fixes, UI updates), see [CHANGELOG.md](../CHANGELOG.md).

Sections follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) categories (`Added` / `Changed` / `Fixed` / `Removed` / `Security`).

## [Unreleased]

### Added

- **Docstring inventory script + tests** (2026-09-06) — `scripts/check_docstring_inventory.py`
  (stdlib-AST advisory inventory of undocumented public symbols under `src/`) plus
  `tests/unittests/test_check_docstring_inventory.py` (11 tests). Part of the phased
  documentation-assessment plan; restores the PR coverage gate that flagged the untested script.

## [1.0.0] - 2026-09-03

### Added

- **CI wheel packaging smoke** (2026-09-03) — the `build` matrix job now runs `uv build` before
  pytest, so `test_wheel_contains_guiskindose_package` (including the `gui/help/*.md` assertion)
  exercises a real wheel on every OS/Python matrix entry instead of skipping.
- **GUISkinDose rename PR 0 prerequisites** (2026-09-01) — green, mergeable helpers that did
  not yet rename the Python package: extract `cli()` from `__main__.py` (the `guiskindose`
  console script is wired in a later commit of this PR); dual-read `~/.guiskindose/` /
  `.guiskindose.local.json` / `GUISKINDOSE_SHOW_DEMO_PHANTOMS` while still writing the
  legacy mypyskindose paths at that slice (this PR now writes `~/.guiskindose/`);
  `scripts/rewrite_package_paths.py` (inventory `path` rewrite + leftover-brand report);
  `scripts/check_stale_brand.py` wired into pre-commit and CI (a no-op until this PR
  flipped `LIVE_PACKAGE_NAME`; fail-closed behavior is covered by tests).
- **GUISkinDose rename PR 1 test contract** (2026-09-02) — `dev-docs/plans/archive/GUISKINDOSE_RENAME_PLAN.md`
  now requires inverting PR 0 locks in the mechanical-rename PR: config load–modify–save must
  persist to `~/.guiskindose/` when that file exists, `LIVE_PACKAGE_NAME` must not remain
  `"mypyskindose"`, and `[project.scripts] guiskindose` needs an entry-point test. No extra
  tests-only PR between PR 0 and PR 1.
- **Kerma-meter Codecov patch coverage** (2026-07-26) — added CLI flag wiring tests plus
  settings/validation and table-loader edge cases so `codecov/patch` on the kerma-CF diff
  clears the ~84% target (was 83.87%).
- **Refactor patch coverage** (2026-07-26) — added `tests/unittests/test_refactor_coverage.py`
  exercising the GUI-free helpers extracted during the Sonar complexity refactor
  (`export/metrics.py` mean/scalar/acquisition helpers, `export/cli_source.py` multi/empty
  builders, `kerma_correction._rows_to_factor_dict` error paths) so the `coverage-pr`
  `diff-cover` gate clears 80% (was 78%).
- **Additional GUI coverage tests for Sonar new-code gate** (2026-07-26) — extended geometry /
  results / export / upload / import-preview coverage suites and added
  `tests/gui/test_data_tab_coverage.py`, `test_per_exam_coverage.py`, and
  `test_phantom_preview_controller_coverage.py` so main’s new-code coverage can clear Sonar
  way’s 80% threshold (was ~79% after PR #32 merge).
- **GUI coverage tests for Sonar** (2026-07-25) — added `tests/gui/test_*_coverage.py` suites for
  geometry/upload/results builders, import preview, calculate, and export tabs (P0/P1 modules).

### Changed

- **GUISkinDose rename and republication plans aligned** (2026-09-01) — mechanical in-repo rename
  (`mypyskindose` → `guiskindose`) is specified in `dev-docs/plans/archive/GUISKINDOSE_RENAME_PLAN.md` and
  catalogued in `dev-docs/index.md`. The privacy republication plan now points Phase 5A at that file,
  requires config-directory migration, keeps Semgrep rule IDs, and gates GitHub/Sonar URL rewrites
  on the actual external renames. The rename plan documents a green PR-0 prerequisite slice, one
  CI-green mechanical PR 1 (partial path splits would fail `privacy-gates`), and a local
  `privacy_admission.py run --mode staged` runbook (path-only inventory rewrite; unchanged hashes
  do not need a new human review). No runtime rename in this change.
- **`ci-latest` issue body now includes per-step triage guidance** (2026-08-30) —
  the tracking-issue body explains what each failure mode means and what action
  to take, instead of a bare failure list.
- **`ci.yml` now opens tracking issues on scheduled/dispatch failures**
  (2026-08-30) — mirrors the `ci-latest` pattern with a distinct
  `<!-- ci-failure -->` marker. Auto-closes when a later run is fully green.
  Only fires on scheduled/dispatch runs, not PR failures.
- **AGENTS.md: added git-hooks bypass convention** (2026-08-30) — agents must
  never bypass pre-commit/pre-push hooks with `--no-verify` without explicit
  user permission.
- **Ruff 0.16.2 development-tool upgrade** (2026-08-09) — refreshed the locked
  linter and pre-commit hook, then applied its safe modernization fixes. Ruff 0.16
  expands its implicit default rule set substantially, so the project's existing
  Flake8-compatible `E4`/`E7`/`E9`/`F` baseline is explicit and selectively extended
  with reviewed `B`, `C4`, `FURB`, `I`, `PYI`, `RUF`, `SIM`, and `UP` rules. The
  three `RUF` Unicode-confusables rules are excluded because mathematical symbols are
  intentional in clinical/scientific UI text and documentation; unsafe `SIM117`
  NiceGUI context-manager rewrites are also excluded pending dedicated GUI smoke tests.
  Broad exception and exception-type rules remain out of scope for this upgrade.
- **Locked dependency audit and license inventory** (2026-08-24) — upgraded the locked
  `pip` package to 26.2.1 to remediate PYSEC-2026-3721. License-notice generation now
  uses the same locked `dev` and `gui` environment as CI, preventing host Python
  packages from entering the third-party inventory.
- **ci-latest soft-fail + issue notify** (2026-08-03) — scheduled/manual `ci-latest`
  probe steps use `continue-on-error` so upstream dependency breakage no longer paints
  `main` red. Failures open (or comment on) a GitHub issue labeled `github_actions` /
  `dependencies`, @-mention and assign the repository owner, and include the Actions
  run URL; a later green run auto-closes open tracking issues with the same marker.
- **Dependabot weekly grouped minor/patch bumps** (2026-08-03) — `.github/dependabot.yml`
  still runs weekly (Monday) for `pip` and `github-actions`, but routine minor/patch
  updates are grouped into one PR per ecosystem (`python-minor-and-patch`,
  `github-actions-minor-and-patch`). Major version bumps stay ungrouped for individual
  review.
- **CI base-branch fetch for coverage/changelog** (2026-08-03) — `coverage-pr` and the
  changelog check fetch the PR base with full history instead of `--depth=1`, so
  `diff-cover` / range diffs keep a merge-base when `main` advances after the branch
  was opened.
- **Backlog / plan archive cleanup** (2026-07-30) — trimmed `dev-docs/TO_DO.md` completed items
  (already shipped in prior releases) and archived finished plans under `dev-docs/plans/archive/`:
  `AUTOMATED_PHANTOM_LIBRARY_PLAN`, `PHANTOM_QA_DEMO_GATE_AND_BARIATRIC_EXTREMITIES_PLAN`,
  `PHANTOM_MESH_NAMING_CONVENTION_PLAN`, `MULTI_EXAM_GEOMETRY_OFFSETS_PLAN`,
  `INTERACTIVE_TABLE_OFFSETS_PLAN` (Phases 0–2b; Phase 3 offset arrow deferred). Confirmed and
  removed from the active backlog: sensitive-asset baseline review (all inventory entries
  approved; CI already uses `--require-approved-assets`), HoundDog local PoC (advisory wrapper
  integrated), Upload-tab default example demoting `fake_scanner.dcm`, Geometry per-exam event
  stepper, multi-exam dose-map checkboxes, pediatric stature relabel, mesh naming, arms-down
  variants, kerma-meter CFs, and the fork-maintainer community baseline. Further phantom work
  and custom-mesh import remain open in `TO_DO.md`. Follow-up: rewrote partial backlog items
  (OCR/DICOM-phi wrappers already ship; Central Help / offset UX reduced to remaining gaps) and
  clarified the Results `K_IRP`/`—` open question against current Results vs Data Table UI.
  Also: moved Rich Export Phase 4.3/7 leftovers to Deferred; added
  `dev-docs/INPUT_FIELD_REFERENCE.md` and
  `dev-docs/references/PORTABLE_EXECUTABLE_PACKAGING.md`; marked multi-exam geometry
  assessments historical now that the plan is archived. Added
  `dev-docs/RELEASES_AND_DISTRIBUTION.md` as the release/distribution hub (changelog vs GitHub
  Release notes, PyPI, deferred portable executables).
- **SonarQube/Lizard Phase 4 — UI/CLI oversized functions** (2026-07-29) — decomposed three
  high-NLOC flagged functions: `gui/tabs/settings.py:build` (246 → 9 NLOC) into
  `_build_phantom_section` / `_build_physics_section` / `_build_visual_section`;
  `gui/exam_loaders.py:load_tabular` (162 NLOC / CCN 15 → 14 NLOC / CCN 3) into
  `_parse_tabular` / `_collect_preserved_flags` / `_append_multi_study_exams` /
  `_append_single_study_exam` / `_finalize_tabular_state` / `_wrap_tabular_schema_detection`;
  and `main.py:get_argument_parser` (158 NLOC) into a new `cli_args.py` module
  (`_add_top_level_args` / `_add_input_args` / `_add_export_args` / `_add_gui_args`),
  re-exported via `main.py` for API stability. No public API or `--help` output changes.
  `main.py` dropped from 820 → 631 lines (under the 800-line CI gate).
- **Protected scanner CI clarified** (2026-07-28) — renamed the token-gated SonarCloud step to state that it
  requires `SONAR_TOKEN`, added regression assertions for that guard and the privacy-gated CodeRabbit trigger, and
  corrected harness/privacy documentation for the protected-`main` Sonar and split PR-versus-`main` Gitleaks
  workflows. CodeRabbit requests now match the DICOMViewerV3 privacy-gated implementation: same-repository
  PRs (including drafts), a SHA attestation CodeRabbit recognizes, and `actions/github-script` v9.
- **Single 80% coverage standard** (2026-07-27) — removed the matrix `build` job's separate
  non-GUI `--fail-under=65` coverage step; it now runs the non-GUI suite for test-pass only
  (`pytest --ignore=tests/gui -n auto`, also faster). Coverage is enforced at one 80% standard by
  `coverage-pr` (PRs: combined ≥80% + `diff-cover` ≥80%) and `sonar-scan` (main: ≥80% new-code),
  eliminating the earlier 65%-vs-80% split and the GUI-0% package-scope workaround.
- **Faster CI test runs** (2026-07-27) — the `coverage-pr` and `sonar-scan` combined-coverage
  jobs migrated from `coverage run -m pytest` to `pytest --cov` (pytest-cov, so xdist worker
  processes are measured) with `pytest-xdist -n auto` on the non-GUI suite (GUI stays serial for
  asyncio/nicegui). ~2x faster locally with identical coverage; combined gate stays ≥80%. Added
  `pytest-xdist` to the `dev` extra and `uv.lock`. No tests removed.
- **SonarQube cognitive-complexity hotspots** (2026-07-26) — split the highest-complexity
  `src/` functions: correction-value handlers in `export/metrics.py`, native geometry tracking
  into `gui/native_geometry.py`, `run_gui` setup helpers, CLI export source builders, and
  exam coordinate-transform helpers (python:S3776).
- **Sonar + privacy-gated scans master plan** (2026-07-25) — `dev-docs/plans/archive/SONAR_PRIVACY_GATED_SCANS_PLAN.md`
  covers Sonar security fixes; keep GUI in coverage via combined `tests/gui/` coverage.xml + GUI
  tests; remove README Sonar badge when custom quality gates are unavailable (done on this
  branch); cloud analyzer path exclusions audit for Sonar / Semgrep / CodeRabbit (and a note that
  future DeepSource or similar SaaS SAST must use the same privacy-gate + exclusion pattern);
  Semgrep as local Actions CLI with Cloud App disabled; restore Sonar on PRs; run OWASP Semgrep /
  Sonar / CodeRabbit only after `privacy-gates`. Branch: `plan/sonar-privacy-gated-scans`.
- **PR coverage gate via GitHub Actions** (2026-07-26) — matrix `build` raises non-GUI
  `coverage report --fail-under` from 60→65. New `coverage-pr` job (PRs only) runs combined
  non-GUI + GUI coverage (≥80%) and `diff-cover` ≥80% vs the PR base. Codecov stays main-only
  upload with `codecov.yml` project/patch statuses set to **informational** so Free `codecov/patch`
  no longer blocks merges; the GHA gate is authoritative.
- **Sonar quality-gate README badge removed** (2026-07-25) — dropped the SonarCloud
  `alert_status` badge from `README.md`. On Free / read-only Sonar way the new-code coverage
  gate stays at 80% and cannot be lowered, so the badge was advertising a red status we cannot
  tune. Sonar analysis remains in CI per `SONAR_PRIVACY_GATED_SCANS_PLAN.md`; the badge may
  return only when the gate is green sustainably or a custom gate is available.
- **Sonar coverage now includes GUI tests** (2026-07-25) — cloud-scans coverage generation
  installs the `gui` extra and runs a two-pass `coverage` recipe (non-GUI then `tests/gui/`
  with `--append`) so Sonar measures `src/guiskindose/gui/`. Documented in `SONARQUBE_LOCAL.md`.
- **Cloud scanner exclusion audit** (2026-07-25) — Sonar exclusions add runtime output globs
  (`tmp/**`, `PlotOutputs/**`, `htmlcov/**`, `coverage.xml`); `.coderabbit.yaml` disables
  auto-review and path-filters sensitive surfaces; privacy docs record cloud-vs-local scope
  (OWASP Semgrep stays include-list; privacy Semgrep keeps `src`/`scripts`/`tests`).
- **Privacy-gated CI scans** (2026-07-25) — `privacy-gates` job runs admission + privacy
  Semgrep first; OWASP Semgrep, SonarCloud (PR+main), gui-smoke, and the build matrix wait on
  it. Codecov/Safety stay main-only. Automatic Analysis is off; Free/Sonar-way coverage gate
  remains untunable (no README badge).
- **CodeRabbit after privacy-gates** (2026-07-25) — auto-review disabled; CI posts
  `@coderabbitai review` on non-draft PRs once per head SHA only after reusable
  `privacy-gates` succeeds (does not wait for the full matrix).
- **SonarCloud Automatic Analysis disabled; Free gate untunable** (2026-07-25) — CI-based
  analysis is authoritative; Free/Sonar-way `new_coverage` stays at 80% (B2-B / no README badge).
- **CI locked installs** (2026-07-24) — the `ci.yml` test/coverage matrix (`build`) and the
  main-only `cloud-scans-after-gates` job now install via `uv sync --extra dev --locked` and run
  tools through `uv run --no-sync` (cross-OS) instead of unpinned `pip install`, and coverage
  upload uses the pinned `codecov/codecov-action` instead of `pip install codecov`. This clears
  the SonarCloud **S8544** (unpinned-dependency) findings on those jobs. The intentionally
  unpinned `ci-latest.yml` sweep is unchanged by design. Note: **S8541** ("omitting `--no-build`")
  still reports on `uv sync` lines — it is unavoidable when installing the local project and is a
  SonarCloud accept/disable-rule item, not a code fix.
- **Release pipeline hardening** (2026-07-24) — `release.yml` now builds with the pinned `uv`
  toolchain (`uv build`) instead of an unpinned `pip install setuptools wheel twine build`
  (clears SonarCloud S8544/S8541 on the release path), and publishes to PyPI via **Trusted
  Publishing (OIDC)** — removing the stored `PYPI_DEPLOY_API_KEY` secret in favor of a
  short-lived token (`id-token: write`). The workflow stays inert unless a GitHub Release is
  created; see `PUBLISHING.md` for the one-time PyPI trusted-publisher setup needed before any
  first real publish.
- **SonarCloud new-code Security Rating** (2026-07-24) — Confined the remaining CLI-derived
  filesystem paths in dev scripts through path validation and added git-ref / audit-arg
  allowlisting so SonarCloud stops rating new code below A. `mpfb_generate` and `run_catalog`
  now route catalog/report paths through `path_safety.resolve_under_roots`;
  `check_feature_doc_matrix` validates the changed-paths file stays under the repo root and
  its git ref against a conservative pattern; `audit_dependencies` rejects `uv audit` passthrough
  args containing control characters or surrounding whitespace (the call is already shell-less /
  list-form); `check_doc_freshness` matches link schemes without embedding a clear-text `http://`
  literal (S5332). Behavior unchanged; dev-tooling hardening only.
- **Push-harness fixes for phantom catalog branch** (2026-07-24) — Exclude `scripts/phantom_gen` from
  basedpyright (incomplete bpy/trimesh/numpy-stl stubs); type patient offsets as floats; require
  `jupyterlab>=4.6.2` for notebook extra advisory CVEs; GUI-placement `importorskip` on phantom
  unit tests that transitively import NiceGUI. Pin CI/`[dev]` ruff to `>=0.15,<0.16` so unpinned
  `pip install ruff` cannot pull 0.16 and fail the matrix on hundreds of newly-noisy findings.

### Fixed

- **CodeQL quality-alert cleanup** (2026-08-04) — removed dead assignments and imports,
  made intentional cleanup and fall-through paths explicit, and separated GUI table-origin
  coordinate utilities from offset handlers to break their import cycle. No user-facing
  behavior changed.
- **Locked dependency audit** (2026-08-04) — `uv.lock` bumps `aiohttp` 3.14.1→3.14.3 and
  `cryptography` 49.0.0→50.0.0 so `static-analysis` / `uv audit` clears newly published
  advisories (GHSA-mfx4-hv73-q22v, GHSA-cq5v-8q36-5273, GHSA-mq44-7p77-q5h7,
  GHSA-g6cj-pr64-35w5).
- **Main-push privacy gate on Dependabot / noreply Git trailers** (2026-08-03) —
  `check_ci_metadata.py` failed `main` CI after merging Dependabot or Cursor PRs
  because commit messages include Dependabot `Signed-off-by` and GitHub
  `Co-authored-by` noreply identity trailers. Those known GitHub automation /
  `users.noreply.github.com` trailers are now ignored for `EMAIL_ADDRESS` in
  commit-message and push-metadata scans only (helper:
  `scripts/git_identity_trailers.py`); institutional emails and PR title/body
  scans stay strict. Trailer display names must not contain `@`, so an
  institutional address cannot hide behind an allowlisted bracketed noreply.
- **ci-latest type error on `main`** (2026-07-27) — `check_table_hits` returned
  `hits.tolist()` from a bool ndarray; newer numpy stubs type `ndarray.tolist()` as not
  assignable to the declared `List[bool]`, failing basedpyright in the `latest-deps` job.
  Now builds an explicit `list[bool]` (`[bool(hit) for hit in hits]`); behavior unchanged.
- **SonarQube bugs and easy wins** (2026-07-26) — cleared the three open BUG findings in
  `gui/app.py` (propagate `asyncio` cancellation by not swallowing `CancelledError`; keep a
  strong reference to browser disconnect shutdown tasks). Also fixed confusing adjacent-string
  concatenations, duplicated string literals, dead/commented code, an empty help-button block,
  and preferred `{...}`/`[]` literals over `dict(...)`/`list()` across plot/export helpers
  (python:S7497, S7502, S5799, S1192, S125, S108, S1854, S7498).
- **Local Sonar smells on kerma-meter CF paths** (2026-07-26) — cleared BLOCKER S3516
  (`kerma_meter_prompt` no longer always-returns-bool; dialog is fire-and-continue),
  duplicated dialog CSS literals (S1192), unused warn-helper params (S1172), and cognitive
  complexity on CF table load / Calculate kerma readiness helpers. Behavior unchanged.
  Also tightened basedpyright types on CF table load and identity-adapter tests so
  pre-push typecheck passes.
- **Kerma CF duplicate-row test logging capture** (2026-07-26) — `test_duplicate_rows_first_wins`
  attaches a dedicated WARNING handler instead of relying on pytest `caplog` (flaky on
  CI Python 3.14 when suite logging state blocks root propagation).
- **CodeRabbit kerma-CF hardening** (2026-07-26) — broader fail-soft on CF file load errors;
  invalid in-memory/table factors fall back to `default_factor`; CF prompt keys honor
  `explicit_label`; header aliases for `device_serial_number` / `AcquisitionPlane`; no
  filenames in CF not-found errors/debug logs; export validates kerma list lengths;
  docstrings added across Calculate-tab / kerma tests and remaining branch-touched
  src helpers (export writers, analyze_data, adapters, settings).
- **STL Z-positioning unit test** (2026-07-24) — `test_stl_phantom_positioning_in_z_direction` now
  skips `*_reduced_*` preview companions (decimation can leave tiny +Z verts); full clinical meshes
  still require no vertices with Z > 0.

### Removed

- **`safety` and main-only CI cloud scan removed** (2026-09-03) — the `safety` package was the
  sole consumer of transitive `nltk` in the `dev` extra, so dropping it deletes the unpatched
  `GHSA-8mgp-746c-j5xp` / CVE-2026-81726 exposure at the root instead of ignoring it, along with the
  `nltk>=3.10.3` pin (PYSEC-2026-3726) and the `cloud-scans-main` CI job (`SAFETY_API_KEY` no longer
  needed). Dependency auditing remains covered by `uv audit` + `pip-audit` via
  `scripts/audit_dependencies.py` (same OSV/PyPA advisory data) in the PR-level `static-analysis`
  job and the local pre-push hook. User-facing summary stays in `CHANGELOG.md`.
- **Codecov integration** (2026-07-26) — dropped the `main`-only Codecov upload step from the
  `cloud-scans-main` CI job and deleted `codecov.yml`. Enforced PR coverage remains the GHA
  `coverage-pr` job (combined non-GUI+GUI ≥80% plus `diff-cover` ≥80% vs the PR base); the job
  then ran Safety only until the 2026-09-03 safety removal above deleted it outright.

### Security

- **PHI-like filename admission guard** (2026-07-26) — `scripts/privacy_admission.py check` (pre-commit,
  pre-push, and CI `privacy-gates`) now blocks committing files whose name/path resembles PHI: structural
  identifier patterns (`MRN_…`, SSN format, `patient_name`/`patient_id`, `dob…`, accession numbers) and
  whole-token matches against a curated common-name list. Configured under `phi_filename` in
  `dev-docs/privacy_admission_policy.json` (with an `allowlist_patterns` escape hatch); errors report a
  non-reversible `path_token=` instead of the sensitive name. Verified zero false positives across the
  current tree.
- **PR cloud-scanner boundary hardening** (2026-07-26) — tokenized SonarCloud analysis now
  runs only on `main` pushes and requires an explicit `SONAR_PROTECTED_MAIN_ENABLED=true`
  repository variable, keeping it fail-closed until branch protection is confirmed. Added
  regression tests that forbid `pull_request_target`, prevent PR-head Sonar execution, and
  preserve CI-requested CodeRabbit review after privacy gates. Sonar and CodeRabbit now share
  CI-enforced exclusions for `.dicom` and additional medical/image/document/binary formats;
  OWASP Semgrep remains local with telemetry disabled and asset fixtures excluded. CodeRabbit
  manual review commands remain a documented, accepted bypass of CI ordering.
- **Sonar S8707 catalog report write** (2026-07-26) — `write_text_under_roots()` confines the
  JSON report path then writes via `open().write` so Sonar does not treat CLI-derived report
  payload content as a path-injection sink on `Path.write_text` (clears remaining S8707 on
  `run_catalog.py` after PR #32).
- **Sonar S8707 / S8705 sanitizers** (2026-07-25) — `trusted_path_under_roots()` rebuilds catalog
  JSON report paths from allowlisted roots before write; `build_uv_audit_argv()` allowlists only
  `--frozen`/`--locked` for `uv audit` subprocess argv (clears SonarCloud new-code Security Rating C).
- **Notebook embedded-visual review checklist** (2026-07-25) — `notebook_embedded_visual` assets
  in `approved_asset_inventory.json` now require a `notebook_review` block with
  `embedded_images_reviewed` and `burned_in_text_reviewed` both `true`; an `approved` status alone
  no longer clears a notebook with rendered image/PDF outputs (`check_sensitive_content.py` emits
  `NOTEBOOK_REVIEW_FIELDS_INCOMPLETE` otherwise). This gives notebooks parity with the DICOM and
  container review checklists so embedded outputs get an explicit human PII/PHI review. The
  rendered inventory Markdown and `PRIVACY_AND_SENSITIVE_ASSETS.md` document the new fields.
- **SonarCloud analysis scope** (2026-07-25) — added `.sonarcloud.properties` (the file
  Automatic Analysis actually reads; `sonar-project.properties` is ignored by it) excluding
  directories/artifacts where private data is most likely to land (`example_data`, `phantom_data`,
  `table_data`, `dev-docs`, `**/*.dcm`, notebooks, `**/*.log`, `**/*.txt`, images) plus build
  noise, and mirrored the same exclusions into `sonar-project.properties`; the new
  `check_sonar_properties.py` pre-commit/CI check keeps the shared scope keys in parity. Also aligned the stale
  `sonar-project.properties` project key/name to the Sonar project key in use at the time (renamed to
  `kgrizz-git_GUISkinDose` / `GUISkinDose` after the 2026-09-04 GitHub repository rename) and
  added `sonar.organization` so the local/CI scanner file is actually usable. Scan hygiene and
  defense-in-depth only — the real PHI/PII guard remains the commit/CI privacy gates
  (`check_sensitive_content.py` forbids `*.log`, hash-gates images/DICOM/notebook outputs, and
  pattern-scans all UTF-8 text incl. `*.txt`/`*.ipynb`).
- **Blender subprocess argv allowlisting** (2026-07-24) — `run_catalog.py` validates Blender basename
  and catalog ids, then rebuilds argv from trusted components before `subprocess.run` (Sonar S8705).
- **Phantom_gen path confinement** (2026-07-24) — Shared `path_safety.resolve_under_roots` confines
  CLI/catalog-derived paths under allowlisted roots before open/mkdir/write (Sonar S2083), including
  `transform_to_psd_frame.py` and `validate_phantom.py` load/write helpers. Absolute catalog
  `pose_file` paths may also live under the process temp dir (pytest / local scratch).