# Phase D Execution Plan — Correction-Data Distribution Proof

Status: Complete — implemented (2026-09-19), distribution proof PASS locally. Archived.
Created: 2026-09-19
Parent (master) plan: [CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md](../CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md)
 (§5 only; §§1–4 shipped as Phases A–C)
Depends on: Phase A (manifest + validators, PR #101), Phase B (provider swap, PR #102),
 Phase C (guides, PR #103)
Branch: `fix/correction-data-phase-d`

## Objective

Prove the packaged-correction-data behavior holds from a real installed
distribution, not just the source checkout: the wheel/sdist ship every
runtime lookup table and the manifest, and a clean-env install reproduces
checkout-numerical results with no working-directory writes, no ignored-DB
resurrection, and no absolute paths in exports.

## Verified Current State (Phase D coverage map)

Master §5 has nine bullets. Five are already pinned at unit level and are
**not** re-implemented here — Phase D re-asserts them only where installation
can change the outcome (resource loading from a wheel, CWD behavior, export
payloads). Pure-logic items stay unit-tested:

| Master §5 bullet | Status | Evidence (no change in Phase D) |
|---|---|---|
| Explicit custom SQLite parity with source CSVs | Covered | `test_correction_data_provider.py:105` `test_explicit_parity_with_packaged` |
| Malformed / schema-drift DBs fail closed pre-calculation | Covered | `test_correction_validation.py` schema-drift group (`test_explicit_db_bad_version_fails`, `test_explicit_db_missing_version_table_fails`, `test_explicit_db_missing_table_and_column_fail`, out-of-range/duplicate/malicious-name cases) + `test_correction_data_provider.py:112` `test_explicit_malformed_fails_value_free` |
| No absolute path in exports, both modes | Covered (settings serialization) | `test_correction_data_provider.py:166` `test_export_descriptor_has_no_paths` covers `serialize_settings` snapshots only, not full post-`analyze_data` payloads — hence Step 3 item 5 re-asserts full dict/JSON exports from the install |
| Default lookup creates no CWD files | Covered (checkout) | `test_default_lookup_creates_no_cwd_files` — re-asserted from installed wheel in Step 3 |
| Seeded root/CWD DB ignored, packaged golden returned | Covered (checkout) | `test_sentinel_db_ignored_and_untouched` — re-asserted from installed wheel in Step 3 |

Genuinely new work (this plan):

| Master §5 bullet | Gap |
|---|---|
| Wheel asserts for all required CSVs + manifest | `test_packaging.py` checks the package tree + GUI help only; no correction-data content assertions |
| Build wheel, clean-env install under gitignored tmp | No script or test does this today |
| HVL / `k_med` / `k_tab` + golden dose from the install, no root DB | Never executed outside the checkout |
| No `corrections.db`/artifact in CWD from the install | Only asserted for checkout lookups |
| Wheel/sdist contents + numerical parity vs checkout | Never compared |

## Locked Decisions (2026-09-19)

1. **No new hardcoded goldens.** Parity is direct comparison: run the same
   calculation from the installed wheel and from the checkout, assert equal
   outputs (PSD, dose-map checksum, correction tables). A hardcoded golden
   would duplicate the existing golden suites and rot independently.
2. **Bundled fixtures only.** The proof runs the shipped Siemens example RDSR
   (`src/guiskindose/example_data/RDSR/`, already approved inventory) — never
   private DICOM. No PHI/PII enters the proof by construction.
3. **Repo-local scratch.** Build + venv + runs live under gitignored `tmp/`
   (`tmp/dist-proof/`), per the scratch-directory rule. Runtime dependencies
   come from the lockfile/network (CI) or local cache — see D4.
4. **Hermetic proof venv + import-path guard (revised post-review).** The
   draft's `--system-site-packages` default is withdrawn: the dev checkout
   resolves `guiskindose.__file__` to `src/` (verified on this machine), so
   an inheriting venv can silently import the checkout and report a false
   PASS. The proof venv is hermetic (no `--system-site-packages`);
   `uv pip install dist/guiskindose-*.whl` resolves runtime deps from the
   index in CI or the local `uv` cache offline. Mandatory hard fail
   when `Path(guiskindose.__file__).resolve()` is under the repo `src/`
   (run before any assertion). A `--quick` shortcut keeps
   `--system-site-packages` for offline local iteration behind the same
   `__file__` guard; `--quick` is never the canonical §5 evidence.
   Base-environment precondition (fail fast with a clear message when
   `pandas`/`numpy`/`pydicom`/etc. cannot be installed) is documented in the
   script's `--help` and Step 2.
5. **Fast tests stay fast.** Wheel-content assertions follow the existing
   `dist/`-skip pattern (`pytest.skip` when no wheel built); the
   build-and-install proof is a script invoked from CI, not a pytest test
   that shells out to `uv build` (slow/flaky cross-platform; repo precedent
   treats `uv build` as a runbook step, not a pytest precondition).

## Resolved Design Decisions (post dual review, 2026-09-19)

Reviewers: kilo `stepfun/step-3.7-flash:free` + cursor `composer-2.5`, both
REQUEST CHANGES on the draft. Resolutions below; conflicts reconciled
explicitly.

- **Q1 (proof shape) — resolved: standalone script + automatic content
  assertions + optional CI step.** `scripts/verify_distribution.py` is the
  canonical proof (manual per release, PASS log attached to the PR). No
  pytest test shells out to `uv build` (slow/flaky cross-platform; both
  reviewers accept this half). CI enforcement (kilo's concern) comes from
  two automatic pieces: the Step 1 `test_packaging.py` assertions, which run
  in the `build` job that already executes `uv build` before pytest
  (`ci.yml:159,286`) and skip elsewhere, plus an optional Ubuntu-only CI
  step invoking the script with `--skip-build` after the existing build.
  (Reconciliation: sides with cursor against pytest-shellout, adopts kilo's
  CI-enforcement via the CI step rather than a test.)
- **Q2 (venv isolation) — resolved: hermetic default (D4, both reviewers
  converge).** Cursor required the `__file__` guard + hermetic default;
  kilo required the documented base precondition + import-check guard. The
  plan takes both: hermetic venv, locked-cache/offline install path,
  mandatory `__file__` guard, fail-fast precondition, `--quick` shortcut
  for offline iteration only.
- **Q3 (calculation scope) — resolved: full `main()` with default settings.**
  Both reviewers converge: the settings default phantom is `cylinder`
  (cursor verified `settings_example.json`; the draft's "human-mesh cost"
  framing is withdrawn), so full `main()` on the bundled Siemens example
  is both the strongest and a cheap proof. Assertions: PSD + dose-map
  checksum + packaged hash equal the checkout run; targeted HVL/`k_med`/
  `k_tab` parity rides along inside the run (no separate lightweight leg).
  Human mesh and plotting stay out unless a perf budget is approved.
- **Q4 (sdist depth) — resolved: file-list parity only (unanimous).** Assert
  the `guiskindose-*.tar.gz` file list covers the Step 1 set; no
  build-and-install from sdist (needs network build deps, low marginal
  value once the wheel install is proven).

## Scope

**In scope (master §5):**

- Step 1 — wheel/sdist content assertions in `tests/unittests/test_packaging.py`:
  every manifest-declared `runtime_lookup` CSV (3 files, verified roles in
  `correction_data_manifest.json`) + the manifest JSON present in the wheel;
  sdist file list covers the same set. Deliberate narrowing note: "required"
  means runtime lookups + manifest, not the build-input HVL CSVs or the
  provenance-only `device_info.csv` that `MANIFEST.in` also ships. Skip (with
  reason) when no `dist/` artifact exists, matching the existing test pattern.
- Step 2 — `scripts/verify_distribution.py`: `uv build` (wheel + sdist),
  hermetic venv under `tmp/dist-proof/`, locked/cache wheel install, then
  the Step 3 matrix. Prints a PASS/FAIL report; exits nonzero on any failure.
  Decisions 2–5 apply. Implementation constraints (both reviews): proof runs
  execute **only** in proof-venv `python` subprocesses, never in-process
  from the checkout; `PYTHONPATH` is cleared in the proof environment
  (`pyproject.toml` sets `pythonpath = ["tests"]` for pytest, which must not
  leak in); checkout baseline runs in a separate subprocess against the
  checkout interpreter. The script passes the standard `scripts/` harness
  gates (`ruff`, `basedpyright`, `bandit`) and stays under 800 lines.
- Step 3 — installed-wheel run matrix (each against a fresh CWD with no DB,
  then with a sentinel-seeded `corrections.db`):
  1. HVL / `k_med` / `k_tab` lookups return the packaged values (compare
     against checkout provider output, not hardcoded numbers).
  2. Full `main()` on the bundled Siemens example (default cylinder
     settings); PSD + dose-map checksum equal the checkout run.
  3. CWD contains no `corrections.db` or other new artifact after each run.
  4. Sentinel-seeded CWD DB is ignored (untouched bytes) and results equal
     the packaged-CSV run.
  5. Full `analyze_data` dict + JSON export payloads (not just
     `serialize_settings` snapshots) contain no absolute path, in both
     packaged and explicit-SQLite modes.
- Step 4 — docs: `CHANGELOG.md` (Fixed bullet), `dev-docs/MAINTENANCE_LOG.md`,
  `dev-docs/index.md` row flip to Complete **plus add the missing
  `MAINTENANCE_LOG.md` catalog row** (kilo verified it is absent; required
  by `check_doc_freshness.py`), archive this plan to
  `dev-docs/plans/archive/`, clear the Phase D marker in `dev-docs/TO_DO.md`
  (same-PR cleanup rule).

**Out of scope:** custom equipment profiles, support-transmission geometry,
fixture-DICOM scrub (tracked TO_DO deferral), `db_connect.py` removal
(explicit-adapter path stays), §5 bullet re-implementation for already-covered
unit items (table above).

## Validation

- `python -m pytest tests/unittests/test_packaging.py -q` (with and without a
  fresh `uv build` artifact in `dist/`).
- `python scripts/verify_distribution.py` end-to-end on this machine; attach
  the PASS report in the PR. Optional Ubuntu-only CI step runs it with
  `--skip-build` after the existing `uv build`.
- `python scripts/privacy_admission.py run --mode staged` when adding
  `scripts/verify_distribution.py` (new `scripts/` surface).
- Full suite + `ruff` / `basedpyright` / `bandit` / privacy gates per the
  Definition of Done; `check_doc_freshness.py` for the new index/archive links.
