# Assessment: PHASE_6_DOC_INTEGRATION_PLAN.md

## Overall Verdict

The plan is structurally sound in its goal (single source of truth for help content) but contains **one error** and **several gaps** that would cause implementation problems.

---

## Errors

### 1. Missing file: `below_floor_kvp.md` is never mentioned

The plan references only `positioning_offsets.md` and `geometry_workflow.md` throughout — in the relocation step, the sync script, the Sphinx toctree, and the acceptance criteria. However, `src/mypyskindose/gui/help/` contains **three** files:

- `positioning_offsets.md`
- `geometry_workflow.md`
- `below_floor_kvp.md`

`below_floor_kvp.md` is a complete 22-line help file covering below-floor kVp handling. It is referenced nowhere in the plan. The acceptance criteria only list two files.

**Impact:** If implemented as written, `below_floor_kvp.md` would be orphaned — left in `src/` without a docs/ source of truth, or silently dropped.

---

## Gaps

### 2. Merge strategy for `positioning_offsets.md` is underspecified

The plan says to "merge the concise GUI version and the detailed Sphinx version into a single unified file." The two files are substantively different:

| Aspect | GUI version (`src/`) | Sphinx version (`docs/source/user_guide/`) |
|--------|---------------------|-------------------------------------------|
| Lines | 45 | 109 |
| Parameters | Longitudinal, Vertical, Lateral | Latitude (X), Longitude (Y), Rotation |
| Sections | Overview, Parameters, Iterative Workflow, Tips | Overview, Coordinate System, Iterative Workflow (5 steps), Troubleshooting, Tips, Getting More Help, Future Improvements |
| Links | None | References `VENDOR_COORDINATE_SYSTEMS.md`, `normalization_settings.json` |
| Terminology | "patient offsets" on top of "automatic table offsets" | "offset parameters" with vendor normalization note |

The plan does not specify **how** to merge them — which sections to keep, how to reconcile the parameter naming differences, or what to do with the troubleshooting section that only exists in the Sphinx version.

### 3. Sphinx `index.rst` changes are vague

Step 4 says to "modify `docs/source/index.rst` to add the three new files to the `toctree`." The current `index.rst` has a single toctree with entries like `user/background.md`, `getting_started/getting_started`, etc. The plan should specify the exact lines to add, e.g.:

```rst
    gui_help/positioning_offsets
    gui_help/geometry_workflow
    gui_help/below_floor_kvp
```

and where in the toctree they should appear (after `user/user_guide.md`? as a new section?).

### 4. No sync script implementation details

Step 2 says to create `scripts/sync_gui_help.py` but provides no implementation guidance. Key questions:

- Should it use `shutil.copy` or `pathlib.Path.write_bytes`?
- Should it overwrite or skip if the destination is newer?
- Should it remove files from `src/` that no longer exist in `docs/`?
- Should it print a summary of what was synced?
- Should it exit non-zero if files are out of sync (for pre-commit failure)?

### 5. `check_doc_freshness.py` scope expansion risk

Step 5 says to "scan `docs/source/gui_help/*.md`" but the current `collect_markdown_files()` (line 85-97) only scans `AGENTS.md`, `README.md`, `CHANGELOG.md`, `DESIGN.md`, and `dev-docs/**/*.md`. Adding `docs/source/` would change the scan scope significantly.

The existing `docs/source/user_guide/positioning_offsets.md` contains links like `../../dev-docs/VENDOR_COORDINATE_SYSTEMS.md` which resolve correctly from `docs/source/user_guide/`. If help files are placed at `docs/source/gui_help/`, those same relative links would break (wrong depth). The plan should either:
- Pre-fix all relative links before adding to the freshness checker, or
- Exclude `docs/source/` from the freshness checker and handle help files separately.

### 6. Pre-commit hook placement not specified

Step 3 says to add a pre-commit hook but doesn't specify whether it should be a **local hook** (like `doc-freshness`) or a **separate repo hook**. Given the project's existing pattern of using local hooks for custom scripts, the plan should recommend adding it as a local hook alongside `doc-freshness`, with `always_run: true` since it operates on a fixed file set.

### 7. No consideration for `git blame` or merge conflicts

The plan says the `src/` copies should be "tracked in git." But tracking mirrored files creates a maintenance burden:
- A commit to `docs/source/gui_help/` would need a follow-up commit to `src/mypyskindose/gui/help/` (or the pre-commit hook handles it)
- If the pre-commit hook auto-commits, it creates its own commit, which could confuse `git blame`
- The plan should clarify whether the pre-commit hook auto-commits or just fails the commit if files are out of sync

The safer approach: the pre-commit hook should **fail** if `docs/source/gui_help/` and `src/mypyskindose/gui/help/` are not in sync, requiring the developer to run the sync script manually before committing. This avoids auto-commits and keeps `git blame` clean.

### 8. No mention of `.gitignore` implications

The plan says to track `src/` copies in git. This is fine as-is. But if anyone later tries to `.gitignore` them (e.g., to avoid duplication), the entire approach breaks. The plan should explicitly state that `src/mypyskindose/gui/help/*.md` should **not** be added to `.gitignore`.

### 9. No mention of updating `help_button.py`

The plan says in Step 2 that `help_button.py` "can continue using `Path(__file__).parent / 'help'` exactly as it does now." This is correct — since the files are mirrored into `src/`, the existing path resolution works. However, the plan should **explicitly confirm** that no code changes to `help_button.py` are needed, so implementers don't waste time refactoring it.

---

## Minor Issues

### 10. Directory name `gui_help` vs existing `user_guide`

The plan proposes `docs/source/gui_help/` as the new directory. This is a flat path under `docs/source/`, which is consistent with how other docs are organized (`getting_started/`, `user/`). However, it creates a naming inconsistency: the existing `user_guide/` directory vs the new `gui_help/` directory. Consider whether `docs/source/gui/` would be more consistent, or whether the existing `user_guide/positioning_offsets.md` should be moved into `gui_help/` (which would clean up the directory structure).

### 11. Acceptance criteria missing verification of GUI functionality

The acceptance criteria verify file existence, sync behavior, and doc build success, but do not include a criterion that the **GUI actually loads the help content** after the changes. This should be added, e.g.:
- [ ] The NiceGUI help buttons display the correct content from the synced files.

### 12. No mention of testing with `pip install -e .`

Since the whole point is that `include-package-data = true` picks up the mirrored files, the acceptance criteria should include verifying the package works after `pip install -e .`, not just from the source tree.

---

## Recommended Fixes

1. **Add `below_floor_kvp.md`** to all steps: relocation, sync script, toctree, acceptance criteria.
2. **Specify the merge strategy** for `positioning_offsets.md` — recommend keeping the detailed Sphinx version as the unified file, incorporating the GUI version's parameter descriptions and workflow steps.
3. **Provide the exact `index.rst` toctree lines** to add.
4. **Clarify pre-commit behavior** — should it auto-commit or just fail? Recommend failing (not auto-committing) to keep git history clean.
5. **Explicitly state**: no code changes to `help_button.py` are needed.
6. **Add GUI verification** and `pip install -e .` verification to acceptance criteria.
7. **Address the `check_doc_freshness.py` scope issue** — either pre-fix relative links in the merged files, or exclude `docs/source/` from the checker.
