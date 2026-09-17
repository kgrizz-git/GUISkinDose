# Issue #60 Fix Plan — Phantom-Preview `monkeypatch` vs NiceGUI `sys.modules` Purge

Status: Active — DeepSeek plan review returned 4× APPROVE-WITH-NITS + 1× BLOCK
(Step 5 dispatch); BLOCK + nits addressed below. Ready to implement.
Created: 2026-09-17
Issue: [#60](https://github.com/kgrizz-git/GUISkinDose/issues/60) (`ci-latest` pytest probe failed)
Branch: `fix/issue-60-phantom-preview-monkeypatch`

## Objective

Fix the single deterministically failing test behind issue #60 with a test-only,
version-agnostic change, then prove it via a mixed-suite repro and a green
`ci-latest` run (which auto-closes the issue). No production, dependency, or
lockfile changes.

## Root Cause (verified, not hypothesized)

Cross-suite `sys.modules` pollution — NOT a pytest 9.1.1 regression, NOT a
nicegui 3.16 regression, NOT dependency drift:

1. GUI tests use NiceGUI's `user` fixture (`tests/conftest.py:22-27`), whose
   teardown runs `nicegui_reset_globals()` (`nicegui/testing/general.py:86`,
   byte-identical in local 3.14.0 and canary 3.16.0). It pops every
   `Client.page_routes` module **and all its parents** from `sys.modules`.
2. `src/guiskindose/gui/app.py:150` defines `@ui.page("/")`, so teardown purges
   `guiskindose`, `guiskindose.gui`, `guiskindose.gui.app` — but **not**
   `guiskindose.gui.phantom_preview` (not a prefix of `guiskindose.gui.app`).
3. `tests/unittests/test_gui_phantom_preview.py:17-23` imports the submodule at
   collection (cached); after the purge, pytest's string-path resolver
   re-imports a **fresh parent with no `phantom_preview` binding** while the
   cached child returns without re-binding. Hence at `:61-68`:
   `AttributeError: 'module' object at guiskindose.gui.phantom_preview has no
   attribute 'phantom_preview'`.
4. Pinned `ci` masks this by splitting suites (`ci.yml:290`
   `pytest --ignore=tests/gui` vs separate `tests/gui/` jobs at `:223,331,378`);
   `ci-latest` is the only job running everything in one process
   (`ci-latest.yml:62` `python -m pytest -q`).

Proven locally on **pinned** deps (3.5 s):
`pytest tests/gui/test_gui_smoke.py::test_index_page_renders
tests/unittests/test_gui_phantom_preview.py::test_resolve_preview_mesh_returns_stem_when_reduced_absent`
fails with the exact CI signature. "Canary-only" is a workflow-topology
artifact; the pytest-version hypothesis is dropped (the failure reproduces on
pinned pytest 9.0.3, so no pytest upgrade/downgrade is implicated — do not
cite `resolve()` internals as fact in the #60 closeout comment).

## Scope

**In scope (fix = R1 only):**

- `tests/unittests/test_gui_phantom_preview.py:61-68` — convert string-path
  `monkeypatch.setattr("guiskindose.gui.phantom_preview._PHANTOM_DATA_DIR", …)`
  to object-form patching on the already-imported module
  (`from guiskindose.gui import phantom_preview as mod`, then
  `monkeypatch.setattr(mod, "_PHANTOM_DATA_DIR", tmp_path)`). Matches the
  existing idiom at `tests/gui/test_gui_helpers.py:22`. Patching by object
  identity bypasses `sys.modules` and parent attrs entirely.
- `dev-docs/MAINTENANCE_LOG.md` entry (tests-only + maintenance-log touch →
  PR98 `check_changelog.py` process exemption applies; no `CHANGELOG.md`).

**Out of scope (explicitly deferred, with reasons):**

- `scripts.*` string-path siblings
  (`test_check_sensitive_content.py:466,497`,
  `test_rewrite_package_paths.py:339`) — `scripts.*` is never purged (only
  `guiskindose.*` prefixes are). Optional style hygiene, not a fix.
- `tests/unittests/test_gui_offset_reset.py:225,252,399`
  (`patch("guiskindose.gui.…")`) — NOT at risk: those use `unittest.mock.patch`
  (resolves via `pkgutil.resolve_name`, which returns the cached submodule from
  `sys.modules` directly and never depends on the parent attribute), while the
  failing test uses pytest's `monkeypatch.resolve` (re-getattrs the parent).
  Verified green post-purge by probe (4 passed). No action, no watch note.
- `uv lock --upgrade`, new pins, pytest/nicegui downgrades — would change
  nothing (reproduces under pins when suites mix).
- `raising=False` — not viable: `resolve()` raises unconditionally and takes no
  `raising` param; it would still raise the same error.
- Do NOT "fix" by adding `--ignore=tests/gui` to the canary — it is correctly
  flagging a latent bug; keep the whole-suite run.

## Global Constraints

- Test-only change; no `src/`, no `pyproject.toml`, no `uv.lock`.
- No PHI/PII, paths, or identifiers in logs or the #60 comment (value-free).
- Keep files under ~800 lines (this plan is small; no new source files).
- Update `dev-docs/index.md` catalog in the same PR (harness rule); archive
  this plan to `plans/archive/` once `ci-latest` is green and #60 closes.
- Same-PR TO_DO rule (PR98): this work is not a `TO_DO.md` item, so no backlog
  removal applies.

## File Map

| File | Role in this plan |
|------|-------------------|
| `tests/unittests/test_gui_phantom_preview.py` | The one-line fix (`:61-68`) |
| `tests/gui/test_gui_smoke.py:28` | Repro partner (triggers the purge) |
| `dev-docs/MAINTENANCE_LOG.md` | Process log entry (no CHANGELOG) |
| `dev-docs/index.md` | Catalog this plan (same PR) |

## Tasks

- [ ] **Step 1: Pre-fix repro on pinned env (already done once — re-run to lock evidence)**
  `python -m pytest tests/gui/test_gui_smoke.py::test_index_page_renders
  tests/unittests/test_gui_phantom_preview.py::test_resolve_preview_mesh_returns_stem_when_reduced_absent -q`
  Expect: the exact `AttributeError` signature. If it passes, STOP — the
  ordering assumption changed and the root-cause section must be rewritten
  before touching the test.
- [ ] **Step 2: Apply the object-form fix**
  Add `from guiskindose.gui import phantom_preview as mod` alongside the
  existing import block (`:17-23`), keeping `pytest.importorskip("nicegui")`
  at `:14` ABOVE the new import (core-CI collection breaks otherwise — the
  `check_gui_test_placement` gate enforces this); replace the string target
  at `:63-66` with `monkeypatch.setattr(mod, "_PHANTOM_DATA_DIR", tmp_path)`.
  Nothing else in the test changes (assertion, tmp STL fixture stay).
- [ ] **Step 3: Post-fix verification, in order**
  1. Mixed repro from Step 1 → green.
  2. `python -m pytest tests/unittests/test_gui_phantom_preview.py -q` → 12/12.
  3. Full `python -m pytest -q` (pinned; both suites, one process) → green.
  4. `ruff check` on the touched test file.
  5. `basedpyright` (canary close gate at `ci-latest.yml:177-179` requires it
     green; `pyproject.toml:183` covers `tests/`).
  6. `python scripts/check_doc_freshness.py` (harness-required; docs touched).
  7. `python scripts/check_gui_test_placement.py` (canary `gui_placement` gate).
- [ ] **Step 4: Maintenance log + docs**
  `MAINTENANCE_LOG.md` Fixed entry (tests-only; cite the purge mechanism +
  object-form fix). No `CHANGELOG.md` (PR98 exemption: tests-only +
  maintenance-log touch). (`index.md` row already added with the plan commit;
  it gets updated to the archive path in Step 6, not here.) Implementation
  commits go through the normal pre-commit path (privacy receipts as required).
- [ ] **Step 5: Push branch, open PR, dispatch canary against the branch**
  `gh workflow run ci-latest.yml --ref fix/issue-60-phantom-preview-monkeypatch`
  (dispatch enabled, `ci-latest.yml:20`). NOTE: a bare `gh workflow run`
  without `--ref` checks out `main` (no `ref` on `actions/checkout`,
  `ci-latest.yml:34`) and would red herring on the old code — always pass
  `--ref`. A green branch run auto-closes #60 pre-merge
  (`ci-latest.yml:173-213`); that is acceptable (the fix is in this PR), then
  archive in Step 6 and merge. If red with the SAME signature → fix
  incomplete, reopen Step 2. If red with a NEW failure → separate triage, not
  scope expansion here.
- [ ] **Step 6: Closeout comment + archive**
  Post a value-free comment on #60 stating the mechanism (purge + fresh
  parent, no binding) and the fix (object-form patch), with file:line cites.
  Flip this plan's `Status:` line to Completed, move it to
  `dev-docs/plans/archive/`, and update the `index.md` row to the archive
  path — all in ONE commit to keep `check_doc_freshness` clean.

## Acceptance Criteria

- Mixed repro fails pre-fix / passes post-fix on pinned env.
- Full `pytest -q` green locally; `ci-latest` green; #60 auto-closed.
- Diff is the test fix + maintenance-log entry + plan/index docs. No src,
  dep, lock, or changelog changes.
