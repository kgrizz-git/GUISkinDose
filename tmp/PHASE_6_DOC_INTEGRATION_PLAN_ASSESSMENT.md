# Assessment: PHASE_6_DOC_INTEGRATION_PLAN.md

## Summary

The plan is well-intentioned but has several gaps, contradictions, and missing details that would cause problems during implementation.

---

## Errors

### 1. File count mismatch — `below_floor_kvp.md` is missing

The plan references moving `positioning_offsets.md` and `geometry_workflow.md` from `src/mypyskindose/gui/help/` to `docs/source/user_guide/gui_help/`. However, there are **three** help files in that directory:

- `positioning_offsets.md`
- `geometry_workflow.md`
- `below_floor_kvp.md`

The third file (`below_floor_kvp.md`) is not mentioned anywhere in the plan. Acceptance criteria also only list two files. This is a clear omission — either `below_floor_kvp.md` should be included or the plan should explicitly exclude it with a rationale.

### 2. `docs/source/user_guide/` already contains `positioning_offsets.md`

The plan says to "Move existing markdown files ... to a new directory `docs/source/user_guide/gui_help/`". But `docs/source/user_guide/positioning_offsets.md` already exists at that level. This file is **different** from the GUI help file — it is 109 lines with more detail (troubleshooting section, tips section, coordinate system quick-reference table). The GUI version is 45 lines and more concise.

The plan does not address this existing file. It should clarify whether:
- The existing file will be moved into `gui_help/` and replaced, or
- The two files will be merged, or
- The existing file will be kept as-is and the GUI help will be a separate copy.

### 3. Sphinx `index.rst` has no `user_guide/` toctree entry

Step 1 says to "Ensure these files are linked in the main Sphinx `index.rst`". However, the current `docs/source/index.rst` has no toctree entry for `user_guide/` at all. The only `user_guide` reference is `user/user_guide.md` (a different file under a different path). The plan should include the specific Sphinx `index.rst` changes needed, not just say "ensure these files are linked".

---

## Gaps

### 4. No code changes specified for `help_button.py`

The plan says "Verify `help_button.py` or the help button instantiations load the markdown files from the correct bundled location" but this is too vague. The current `help_button.py` uses `Path(__file__).parent / "help"` to resolve file paths at runtime. This works when running from source, but when the package is installed via `pip install .`, `__file__` still resolves correctly because setuptools includes package data by default (if `include-package-data = true`, which it is).

However, the plan mentions `importlib.resources` in the rationale but never specifies that `help_button.py` needs to be updated to use it. If the sync approach copies files back into `src/`, the current code may work as-is (no changes needed). But if the plan ever shifts to `importlib.resources` for installed packages, the code changes need to be documented.

### 5. Conflicting sync approaches in Step 2

Step 2 proposes two mutually exclusive approaches without committing to one:

- **Approach A:** Pre-build sync script copies `docs/` → `src/`, track copies in git, use pre-commit hook
- **Approach B:** `.gitignore` the `src/` copies, run sync script in CI before building wheel

The text says "Alternatively" between them, but then the acceptance criteria say "A sync mechanism or script is documented and active" without specifying which. This ambiguity means an implementer wouldn't know which path to take.

The plan should pick one approach. Given the project's existing convention of tracking mirrored files in git (as evidenced by `.gitignore` not excluding `src/mypyskindose/gui/help/*.md`), Approach A is more consistent. But this should be explicit.

### 6. `MANIFEST.in` or `package_data` not addressed

The plan says "Running `pip install .` correctly packages the help files so the GUI can read them at runtime." But this is only true if the files are present in `src/` (which they are, currently). If Approach B is taken (`.gitignore` + CI sync), the build would fail because setuptools wouldn't find the files. The plan should either:
- Confirm that `src/` copies stay in git (no `.gitignore` needed), or
- Add `package_data` or `MANIFEST.in` configuration to `pyproject.toml` to include the synced files.

### 7. No mention of updating `check_doc_freshness.py`

Step 4 says to add a sync verification step to `check_doc_freshness.py`, but the current script scans `AGENTS.md`, `README.md`, `CHANGELOG.md`, `DESIGN.md`, and `dev-docs/**/*.md`. It does **not** scan files under `docs/source/` (only docs under `dev-docs/`). Adding the sync check would require expanding the scan scope, which could introduce new broken-link warnings for inter-doc references. This should be noted.

### 8. No consideration of `pyproject.toml` `[tool.setuptools.package-data]`

The `pyproject.toml` uses `include-package-data = true` but doesn't specify `package-data` explicitly. If the sync approach puts files in `src/mypyskindose/gui/help/`, setuptools should pick them up automatically since they're inside the package directory. But if the plan ever shifts to `importlib.resources` with files outside `src/`, explicit `package-data` configuration would be needed.

### 9. Missing consideration: relative markdown links within help files

Step 1 says to "Update internal markdown links or image references to work in the Sphinx environment." The current help files don't have internal links, but the existing `docs/source/user_guide/positioning_offsets.md` has links like `../../dev-docs/VENDOR_COORDINATE_SYSTEMS.md`. If help files are moved to `docs/source/user_guide/gui_help/`, these relative paths would change. The plan should note this.

### 10. No timeline or implementation order

The plan lists 4 steps but doesn't specify an implementation order or dependencies between them. For example, Step 3 (update GUI pathing) depends on completing Step 2 (bundling mechanism). This is implicit but worth making explicit for an implementer.

---

## Minor Issues

### 11. "gui_help" subdirectory naming

The plan proposes `docs/source/user_guide/gui_help/` as the destination. This is a deeper nesting than the current `docs/source/user_guide/positioning_offsets.md` (which is at the top level of `user_guide/`). The naming is also slightly inconsistent — `gui_help` vs `user_guide`. Consider `docs/source/user_guide/gui/` or `docs/source/gui_help/` for consistency.

### 12. Acceptance criterion 5 is unverifiable

"Modifying the file in `docs/` correctly updates the GUI help text after a sync/build" — this is a process outcome, not a testable criterion. It should be paired with a concrete verification step, e.g., "Running `python scripts/sync_gui_help.py` copies changes from `docs/` to `src/` within 1 second."

---

## Recommendations

1. **Pick one sync approach** (A or B) and remove the alternative. Approach A (track in git + pre-commit) is more consistent with existing project conventions.

2. **Address all three help files** — include `below_floor_kvp.md` or explicitly exclude it.

3. **Resolve the existing `positioning_offsets.md` conflict** — merge, replace, or document why both exist.

4. **Specify the exact `index.rst` changes** needed for Sphinx integration.

5. **Clarify `help_button.py` changes** — if the current `Path(__file__)` approach works, say so; if `importlib.resources` is needed, show the code changes.

6. **Add `check_doc_freshness.py` scope update** to Step 4, noting the need to scan `docs/source/` files.
