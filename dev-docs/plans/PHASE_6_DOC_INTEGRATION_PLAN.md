# Phase 6: Integration with Main Docs (Option 1)

## Objective
Implement Option 1 from `POSITIONING_HELP_PLAN.md`: "Single source of truth: Help content lives in `docs/source/` and is bundled into the package." This ensures that the online documentation (via Sphinx/ReadTheDocs) and the in-app NiceGUI help dialogs use the exact same markdown files, preventing divergence.

## Rationale
By making `docs/source/user_guide/` the single source of truth, documentation authors can write standard Sphinx/MyST markdown without needing to know about the GUI package structure. We then bundle these specific help files into the python wheel so the GUI can access them at runtime via `importlib.resources` (or `pathlib`).

## Step-by-Step Plan

### 1. Relocate Help Content to `docs/`
- Move existing markdown files from `src/mypyskindose/gui/help/` to a new directory `docs/source/user_guide/gui_help/`.
- Ensure these files are linked in the main Sphinx `index.rst` (or `user_guide/index.rst`) so they appear in the web documentation.
- Update internal markdown links or image references to work in the Sphinx environment.

### 2. Implement the Bundling Mechanism
Since `pyproject.toml` uses `setuptools` with `src/` as the package directory, files outside `src/` are not automatically included in the wheel.
- **Approach:** Create a pre-build sync script (e.g., `scripts/sync_gui_help.py`) that copies the markdown files from `docs/source/user_guide/gui_help/` into `src/mypyskindose/gui/help/`.
- **Git integration:** Use a pre-commit hook (e.g., via `pre-commit`) to ensure the files in `src/` are always perfectly mirrored from `docs/` and tracked in version control. Tracking them is often easier for local development without requiring a build step, and ensures the code works immediately after a `git clone`.
- **Build integration:** Alternatively, add `src/mypyskindose/gui/help/*.md` to `.gitignore` and run the sync script as part of the CI/CD release workflow before building the wheel.

### 3. Update the GUI Pathing
- Verify `src/mypyskindose/gui/app.py` or the help button instantiations load the markdown files from the correct bundled location.
- Since we are mirroring them into `src/mypyskindose/gui/help/`, the runtime path logic in the GUI (`Path(__file__).parent / "help" / "positioning_offsets.md"`) will largely remain the same, but we should verify it resolves correctly when installed via `pip install .`.

### 4. Update the Harness Checks
- Add a step to the repository harness (`dev-docs/HARNESS_ENGINEERING.md`) or the existing `check_doc_freshness.py` script to verify that the files in `docs/source/user_guide/gui_help/` match the copies in `src/mypyskindose/gui/help/`.

## Acceptance Criteria
- [ ] `positioning_offsets.md` and `geometry_workflow.md` source files exist in `docs/source/user_guide/gui_help/`.
- [ ] The Sphinx documentation builds successfully and includes the help content.
- [ ] Running `pip install .` correctly packages the help files so the GUI can read them at runtime.
- [ ] A sync mechanism or script is documented and active.
- [ ] Modifying the file in `docs/` correctly updates the GUI help text after a sync/build.
