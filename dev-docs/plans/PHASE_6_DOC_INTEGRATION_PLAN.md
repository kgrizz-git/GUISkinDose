# Phase 6: Integration with Main Docs (Option 1)

## Objective
Implement Option 1 from `POSITIONING_HELP_PLAN.md`: "Single source of truth: Help content lives in `docs/source/` and is bundled into the package." This ensures the online documentation and the in-app NiceGUI help dialogs use the exact same markdown files, preventing divergence.

## Rationale
By making `docs/source/gui_help/` the single source of truth, documentation authors can write standard Sphinx/MyST markdown. We then use a pre-commit sync script to mirror these files into the python package directory (`src/mypyskindose/gui/help/`). This approach keeps the source of truth in `docs/` while avoiding complex setuptools configurations or runtime package-data lookup changes.

## Implementation Steps (Ordered)

### 1. Relocate and Merge Help Content
- Create directory: `docs/source/gui_help/`.
- Move the three GUI help files (`positioning_offsets.md`, `geometry_workflow.md`, `below_floor_kvp.md`) from `src/mypyskindose/gui/help/` to `docs/source/gui_help/`.
- **Merge Conflict Resolution:** A longer `positioning_offsets.md` already exists at `docs/source/user_guide/positioning_offsets.md`. Merge the concise GUI version and the detailed Sphinx version into a single unified file at `docs/source/gui_help/positioning_offsets.md`. Remove the old `user_guide` version.
- Ensure any relative markdown links within the merged files (e.g., links to `dev-docs/`) are correct relative to `docs/source/gui_help/`.

### 2. Implement the Sync Mechanism
- Create a sync script `scripts/sync_gui_help.py` that copies `docs/source/gui_help/*.md` to `src/mypyskindose/gui/help/`.
- Run the script so the files exist in `src/mypyskindose/gui/help/` and ensure they are **tracked in git**. 
- Because the files remain in `src/` and are tracked, `pyproject.toml`'s existing `include-package-data = true` will automatically include them in the `.whl` package. No changes to `pyproject.toml` or `MANIFEST.in` are required.
- Because the files are mirrored into `src/`, `src/mypyskindose/gui/components/help_button.py` can continue using `Path(__file__).parent / "help"` exactly as it does now. No code changes to the runtime pathing are needed.

### 3. Add Pre-commit Hook
- Update `.pre-commit-config.yaml` to run `scripts/sync_gui_help.py` automatically before commits, ensuring the `src/` copies are never out of sync with the `docs/` source of truth.

### 4. Update Sphinx `index.rst`
- Modify `docs/source/index.rst` to add the three new files to the `toctree` so they render in the online documentation:
  - `gui_help/positioning_offsets`
  - `gui_help/geometry_workflow`
  - `gui_help/below_floor_kvp`

### 5. Update Harness Checks
- Modify `scripts/check_doc_freshness.py` to scan `docs/source/gui_help/*.md`.
- Note: expanding the scan scope to `docs/source/` may require ensuring that inter-doc references from these Sphinx files resolve correctly in the custom regex checker.

## Acceptance Criteria
- [ ] The files `positioning_offsets.md`, `geometry_workflow.md`, and `below_floor_kvp.md` exist as the single source of truth in `docs/source/gui_help/`.
- [ ] `docs/source/index.rst` includes the three files in its toctree.
- [ ] Running `python scripts/sync_gui_help.py` copies changes from `docs/source/gui_help/` to `src/mypyskindose/gui/help/` successfully.
- [ ] Modifying a file in `docs/source/gui_help/` and running `git commit` triggers the pre-commit hook and auto-syncs the changes to `src/`.
- [ ] The Sphinx documentation builds successfully without warnings.
- [ ] `scripts/check_doc_freshness.py` scans the new files without throwing false positive link errors.
