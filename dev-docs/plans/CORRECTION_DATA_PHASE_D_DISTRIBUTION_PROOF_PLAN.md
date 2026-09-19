# Phase D Execution Plan — Correction-Data Distribution Proof

Status: Draft — pending dual review (kilo `stepfun/step-3.7-flash:free` + cursor `composer-2.5`).
Created: 2026-09-19
Parent (master) plan: [CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md](CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md)
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
| Malformed / schema-drift DBs fail closed pre-calculation | Covered | `test_correction_validation.py` schema-drift matrix + `test_explicit_malformed_fails_value_free` |
| No absolute path in exports, both modes | Covered | `test_export_descriptor_has_no_paths` (packaged + explicit, `.db`-free payloads) |
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
   (`tmp/dist-proof/`), per the scratch-directory rule. Nothing outside the
   repo except the venv itself.
4. **venv reuses installed deps.** `--system-site-packages` (Q2 asks reviewers
   to confirm this is strong enough for "clean environment"). Rationale for
   the default: no network, cross-OS reproducible, and the variable under
   test is *data-file resolution from an installed wheel*, not dependency
   isolation. The proof installs with `--no-deps` so only `guiskindose`
   itself comes from the wheel.
5. **Fast tests stay fast.** Wheel-content assertions follow the existing
   `dist/`-skip pattern (`pytest.skip` when no wheel built); the
   build-and-install proof is a script, not a pytest test (Q1 asks reviewers
   to challenge this).

## Open Design Questions (for reviewers — recommendations wanted)

- **Q1 (proof shape):** runbook script (`scripts/verify_distribution.py`,
  manual per release + optional CI job) vs pytest test that shells out to
  `uv build` vs CI-only job. Weigh CI runtime cost, no-network developer
  machines, and Windows/macOS/Linux portability (`pathlib` only, no symlink
  or shell assumptions). Which shape, and should CI run it or is manual +
   logged evidence enough?
- **Q2 (venv isolation):** is `--system-site-packages` + `--no-deps` a
  credible "clean environment" for §5, or must the proof build a hermetic
  venv (deps from a local wheel cache, `--no-index`)? If hermetic, who
  maintains the cache and how is it refreshed?
- **Q3 (calculation scope):** full `main()` on the bundled Siemens example
  (strongest proof, but human-mesh runtime + plotting deps) vs targeted
  HVL/`k_med`/`k_tab` lookups plus a lightweight plane-phantom dose run
  (fast, deterministic, but exercises less of the pipeline). Minimum scope
  that still proves the distribution claim?
- **Q4 (sdist depth):** is asserting the sdist file list (CSVs + manifest +
  `MANIFEST.in` parity with the wheel) sufficient, or must the proof also
  build-and-install from the sdist? Note sdist install needs network for
  build deps unless cached.

## Scope

**In scope (master §5):**

- Step 1 — wheel/sdist content assertions in `tests/unittests/test_packaging.py`:
  every manifest-declared `runtime_lookup` CSV + the manifest JSON present in
  the wheel; sdist file list covers the same set. Skip (with reason) when no
  `dist/` artifact exists, matching the existing test pattern.
- Step 2 — `scripts/verify_distribution.py`: `uv build` (wheel + sdist),
  venv under `tmp/dist-proof/`, `pip install --no-deps` the wheel, then the
  Step 3 matrix. Prints a PASS/FAIL report; exits nonzero on any failure.
  Decisions 2–4 apply. Q1–Q4 resolutions shape the final form.
- Step 3 — installed-wheel run matrix (each against a fresh CWD with no DB,
  then with a sentinel-seeded `corrections.db`):
  1. HVL / `k_med` / `k_tab` lookups return the packaged values (compare
     against checkout provider output, not hardcoded numbers).
  2. Dose calculation per Q3 scope; PSD + outputs equal the checkout run.
  3. CWD contains no `corrections.db` or other new artifact after each run.
  4. Sentinel-seeded CWD DB is ignored (untouched bytes) and results equal
     the packaged-CSV run.
  5. Export payloads (dict/JSON) contain no absolute path in either mode.
- Step 4 — docs: `CHANGELOG.md` (Fixed bullet), `dev-docs/MAINTENANCE_LOG.md`,
  `dev-docs/index.md` row flip to Complete, archive this plan to
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
  the PASS report in the PR.
- Full suite + `ruff` / `basedpyright` / privacy gates per the Definition of
  Done; `check_doc_freshness.py` for the new index/archive links.
