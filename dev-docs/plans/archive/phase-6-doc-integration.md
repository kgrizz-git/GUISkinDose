# Phase 6: Integration with Main Docs (Option 1)

## Objective
Implement Option 1 from `POSITIONING_HELP_PLAN.md`: "Single source of truth: Help content lives in `docs/source/` and is bundled into the package." This ensures the online documentation and the in-app NiceGUI help dialogs use the exact same markdown files.

## Rationale
By making `docs/source/gui_help/` the single source of truth, authors write standard Sphinx markdown. A local pre-commit hook (and CI step) verifies these files are mirrored into `src/mypyskindose/gui/help/` where they are tracked in git and bundled. Post-migration, `src/mypyskindose/gui/help/` is read-only for developers.

## Implementation Steps (Ordered)

### 1. Relocate and Merge Help Content
Execute in this exact order:
1. **Create directory:** `docs/source/gui_help/`
2. **Merge `positioning_offsets.md`:** 
   - *Copy Base:* Copy `docs/source/user_guide/positioning_offsets.md` to `docs/source/gui_help/positioning_offsets.md`.
   - *Overview:* **Replace** the Overview section in the merged file (from the base copy) with the GUI version's `## Overview` section (including its trailing "Note:" paragraph about RDSR offsets) verbatim.
   - *Verify preserved:* The "Troubleshooting" section and the "Getting More Help" section are already in the merged file from Copy Base. **Fix the relative paths to `VENDOR_COORDINATE_SYSTEMS.md` in BOTH the "Coordinate System" section and the "Getting More Help" section.** The current `../../dev-docs/...` is broken in both locations. The correct path from the new location is `../../../dev-docs/VENDOR_COORDINATE_SYSTEMS.md`. (The bare filename in backticks in the Troubleshooting section is not a link and may be left as-is for stylistic consistency).
   - *Parameters:* Rewrite the Quick Reference table to have **four rows** matching the GUI parameter names in this order: Lateral, Longitudinal, Vertical, Rotation. The "Direction" and "Effect of Positive Values" columns should describe each parameter's behavior in the same prose style as the original. After the table, add a MyST footnote: `[^coord]: X→Lateral, Y→Longitudinal, Z→Vertical.` referenced from the table caption or a sentence above it.
   - *Replace:* Swap the `## Iterative Positioning Workflow` section (lines 23–62 of the source) for the GUI version's `## Iterative Workflow` section (lines 24–38), preserving all sub-headings and bulleted lists.
   - *Tips:* Replace the Copy Base's `## Tips` section (lines 90–95) with the GUI version's `## Tips` section (lines 40–45), in order.
   - *Remove:* The "Future Improvements" section.
   - *Delete Old:* Delete `docs/source/user_guide/positioning_offsets.md`. Verify the `docs/source/user_guide/` directory is now empty, then delete the directory itself (do not confuse this directory with the completely separate file `docs/source/user/user_guide.md`, which must remain).
3. **Move files:** Use `git mv` (to cleanly preserve history): `git mv src/mypyskindose/gui/help/geometry_workflow.md docs/source/gui_help/` and similarly for `below_floor_kvp.md`.

### 2. Implement the Sync Mechanism (`sync_gui_help.py`)
- **Script Spec:** Write an idempotent `scripts/sync_gui_help.py` using only the standard library. Read files using `encoding="utf-8-sig"` (to strip any existing BOM) and write files using `encoding="utf-8"` (to write cleanly without a BOM, since `utf-8-sig` writes *with* a BOM). This avoids `\ufeff` appearing in rendered markdown. The script should normalize line endings to LF to ensure cross-platform consistency. It must:
  1. Support a `--check` flag.
  2. Refuse to run (exit non-zero with a clear error) if `docs/source/gui_help/` does not exist, is not a directory, or is empty.
  3. Enforce a **flat directory**: iterate `Path.iterdir()` on `docs/source/gui_help/` and exit non-zero if any entry is a directory. Match files using `Path.glob("*.md")`. Non-`.md` files are silently ignored (intended behavior to drop scratch files).
  4. Create the target directory `src/mypyskindose/gui/help/` with `mkdir(parents=True, exist_ok=True)` if it does not exist (guards against CI sparse-checkouts).
  5. Mirror `.md` files to `src/mypyskindose/gui/help/` (copying new files, overwriting changes).
  6. Delete any `.md` files in `src/mypyskindose/gui/help/` that no longer exist in `docs/source/gui_help/`.
  7. If `--check` is passed, do *not* write/delete files; exit `1` if any file is out of sync, else exit `0`. The target directory must also exist in `--check` mode; if missing, exit non-zero.
- **Order warning:** **Do not run the sync script until all of Step 1 is complete.** Running it after 1.2 but before 1.3 will pass the empty-source safety check and silently delete `geometry_workflow.md` and `below_floor_kvp.md` from `src/`, breaking the GUI.
- **Run Once:** After all of Step 1 is complete, run `python scripts/sync_gui_help.py` (no `--check`) to mirror the files, then `git add src/mypyskindose/gui/help/` to stage the mirrored copies for the first commit.
- **Help Button Verification:** Confirm (via `grep -rn 'content_path=' src/`) that the three call sites reference the files by basename, meaning the sync script must preserve these exact basenames. 
- **Tests:** Add unit tests in `tests/unittests/test_sync_gui_help.py` covering: sync (create/update/delete/unchanged), `--check` exit code, missing/empty source prevention, LF normalization, symlink handling (followed or rejected, by design), non-UTF-8 input (fail cleanly), and flat-source enforcement.

### 3. Add Pre-commit Hook & Workflow
- **Configuration:** Add this block to the `repo: local` `hooks:` list in `.pre-commit-config.yaml`:
  ```yaml
      - id: sync-gui-help
        name: GUI help sync (docs/source/gui_help -> src/mypyskindose/gui/help)
        entry: python scripts/sync_gui_help.py --check
        language: system
        pass_filenames: false
        always_run: true
  ```
- **Overhead Note:** Two `always_run: true` hooks will run on every commit (`doc-freshness` and `sync_gui_help`).
- **Developer Workflow:** Developers edit files in `docs/source/gui_help/` and manually run the sync script. 
- **Drift Resolution:** If a developer accidentally edits `src/mypyskindose/gui/help/`, the `--check` hook will fail the commit. The developer must discard their local edits to `src/`, apply them to `docs/source/gui_help/`, re-run the sync script, and re-stage.

### 4. Update Sphinx `index.rst` & `conf.py`
- Modify `docs/source/index.rst` to insert the new files into the `toctree` between `user/user_guide.md` and `getting_started/getting_started`. Indent to match the existing toctree entries (currently 3 spaces):
  ```rst
     user/user_guide.md
     gui_help/positioning_offsets.md
     gui_help/geometry_workflow.md
     gui_help/below_floor_kvp.md
     getting_started/getting_started
  ```
- **MyST Check:** Verify that `myst_parser` supports the footnote syntax used in the merged file (`[^coord]: …` and inline `[^coord]`). If not, add the `footnote` extension to a new `myst_enable_extensions = ["footnote"]` list in `conf.py`.
- **Version Note:** No version bump in `docs/source/conf.py` `release` is required.
- **Local Sphinx Check:** After updating `index.rst`, run `sphinx-build -b html docs/source docs/build` locally to verify the merged `positioning_offsets.md` renders correctly, all three toctree entries resolve, and there are no broken-link or MyST warnings. Address warnings before proceeding. (`docs/build/` is gitignored by `**/build/` in `.gitignore`. Clean up with `rm -rf docs/build/` after verification.)

### 5. Update Meta-Docs, CI, & Checks
- **CI Integration:** In `.github/workflows/ci.yml`, add a step `Check GUI help sync` to the `static-analysis` job, immediately after the "Check documentation freshness" step. The step has no `if:` guard, matching the documentation freshness step — it runs on every push to `main` and every pull request. The step should run `python scripts/sync_gui_help.py --check` and fail the build on non-zero exit.
- **CI GUI Smoke Verification:** The existing `gui-smoke` job in `.github/workflows/ci.yml` should be verified to exercise the merged `positioning_offsets.md` (e.g., by clicking the help button in the Settings tab during the headless smoke test). If the existing smoke test doesn't cover this, extend it.
- **doc-freshness:** In `scripts/check_doc_freshness.py::collect_markdown_files()`, add a block **after** the existing `dev_docs` block that calls `rglob("*.md")` on `repo_root / "docs" / "source" / "gui_help"` (mirroring the existing `dev_docs.rglob` pattern; equivalent to `glob` for a flat directory, but consistent with the surrounding code).
- **AGENTS.md & dev-docs/index.md:** Add this to the **Conventions** section of `AGENTS.md` (immediately after the existing plan-lifecycle bullet):
  > **GUI help files:** The canonical source for in-app help markdown is `docs/source/gui_help/`. These files are mirrored to `src/mypyskindose/gui/help/` by `scripts/sync_gui_help.py` (enforced by pre-commit + CI). Edit the source under `docs/`, never the mirrored copies under `src/`.

  In `dev-docs/index.md`, add this to the **Harness** section table:
  ```markdown
  | Link to the sync script (`scripts/sync_gui_help.py`) | Mirrors `docs/source/gui_help/*.md` -> `src/mypyskindose/gui/help/*.md`; enforced by pre-commit + CI (`ci.yml` `static-analysis` job). |
  ```
- **CHANGELOG:** Add a `CHANGELOG.md` entry describing the new documentation sync mechanism.
- **Parent Plan Update & Archival:** Mark Phase 6 as "Complete" in `POSITIONING_HELP_PLAN.md` and replace its "File Structure After Implementation" section (lines 106–122) with:
  ```
  docs/source/gui_help/
  ├── positioning_offsets.md    # Merged help content (single source of truth)
  ├── geometry_workflow.md      # Geometry tab workflow
  └── below_floor_kvp.md        # Below-floor kVp policy explanation

  src/mypyskindose/gui/help/
  ├── positioning_offsets.md    # Mirrored from docs/source/gui_help/
  ├── geometry_workflow.md      # Mirrored from docs/source/gui_help/
  └── below_floor_kvp.md        # Mirrored from docs/source/gui_help/
  ```
  Move both files in a **single commit** (to avoid breaking the relative path reference in `PHASE_6_DOC_INTEGRATION_PLAN.md`) to `dev-docs/plans/archive/`. In `dev-docs/index.md`, remove `POSITIONING_HELP_PLAN.md` from "Master plans" and add two new rows to "Archived plans" using the `**Completed** — <summary>` format.

## Acceptance Criteria
- [ ] `positioning_offsets.md`, `geometry_workflow.md`, and `below_floor_kvp.md` exist as the single source of truth in `docs/source/gui_help/`.
- [ ] `docs/source/index.rst` includes the correctly 3-space indented `toctree` lines.
- [ ] `scripts/sync_gui_help.py` has tests in `tests/unittests/test_sync_gui_help.py` covering: sync (create/update/delete/unchanged), `--check` exit code, missing/empty source prevention, LF normalization, symlink handling (followed or rejected, by design), non-UTF-8 input (fail cleanly).
- [ ] **Flat-source enforcement test:** when `docs/source/gui_help/subdir/foo.md` exists, the script exits non-zero with a clear error. The test creates a subdirectory under a temp source dir and asserts the exit code is non-zero.
- [ ] Running `scripts/sync_gui_help.py --check` exits non-zero if (a) any file is out of sync, OR (b) `docs/source/gui_help/` does not exist, is not a directory, or is empty.
- [ ] The local pre-commit hook and `ci.yml` `static-analysis` job both enforce the sync check.
- [ ] `scripts/check_doc_freshness.py` explicitly scans the new path via `rglob`.
- [ ] **Sphinx Verification:** Local `sphinx-build` renders the merged file and footnotes without warnings.
- [ ] **GUI Verification (local + CI):** The NiceGUI app loads and displays the correct help content when run via `python -m mypyskindose --mode gui` on a developer's machine, AND the `gui-smoke` job in `.github/workflows/ci.yml` passes (it exercises the help_button call sites headlessly).
- [ ] **Package Verification:** Help files are included in the source distribution and work after `pip install -e .`.
- [ ] **Archival:** Both plans are moved to `archive/` in a single commit and `dev-docs/index.md` is updated.
- [ ] **Future workflow (Renames/Adds):** When renaming a help file, perform all four edits in the same commit, in this order: (1) rename in `docs/source/gui_help/`, (2) update the `content_path=` reference in the tab module, (3) update the toctree entry, (4) run `python scripts/sync_gui_help.py`. The sync must be last. When adding a file, follow the same order (create, `content_path=`, toctree, sync).
