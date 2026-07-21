# PR 22 Nitpicks and Worktree-Aware Git Hooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up the 3 unaddressed review nitpicks from PR #22 and resolve the git `commit-msg` hook containment error in linked git worktrees.

**Architecture:** Update `scripts/check_commit_message.py` to inspect git's active repository directory (`git rev-parse --git-dir`) and common repository directory (`git rev-parse --git-common-dir`) when resolving `allowed_roots`, so commit-message files created in worktree git directories (`.git/worktrees/<name>/COMMIT_EDITMSG`) are properly recognized as contained within the repository. Also fix markdown code block formatting in assessment docs and reuse test fixtures.

**Tech Stack:** Python 3.11+, `pathlib.Path`, `subprocess`, `pytest`

## Global Constraints

- Preserve all existing privacy containment and path security checks in `scripts/check_commit_message.py`.
- Do not allow arbitrary external paths to escape repository containment.
- Run `pytest` and pre-commit checks to verify clean execution.

---

### Task 1: Clean Up PR #22 Review Nitpicks

**Files:**
- Modify: `dev-docs/assessments/HTML_EXPORT_BACKGROUND_TASK_ERROR_20260719T123241.md:24-30,142-144`
- Modify: `tests/unittests/test_gui_figures.py:12-61`

**Interfaces:**
- Consumes: `_PATIENT_FOR_EXPORT_TESTS` from `tests/unittests/test_gui_figures.py`
- Produces: Formatted assessment markdown and streamlined test fixture usage

- [ ] **Step 1: Verify current nitpick states**

Check that in `dev-docs/assessments/HTML_EXPORT_BACKGROUND_TASK_ERROR_20260719T123241.md` lines 24 and 142 lack language tags. In `tests/unittests/test_gui_figures.py`, confirm both `test_make_dosemap_fig_includes_coordinate_frame_annotation` (line 15) and `test_make_dosemap_html_returns_html_bytes` (line 50) define local `patient` dicts identical to `_PATIENT_FOR_EXPORT_TESTS`.

- [ ] **Step 2: Update fenced code blocks in HTML export assessment doc**

In `dev-docs/assessments/HTML_EXPORT_BACKGROUND_TASK_ERROR_20260719T123241.md`:
Replace untagged code blocks at lines 24-30 and 142-144 with ```text fences.

- [ ] **Step 3: Update `tests/unittests/test_gui_figures.py` to reuse `_PATIENT_FOR_EXPORT_TESTS`**

In `tests/unittests/test_gui_figures.py`:
Move `_PATIENT_FOR_EXPORT_TESTS` to top of file (above line 12, right after imports). Replace local `patient` dict definitions in both `test_make_dosemap_fig_includes_coordinate_frame_annotation` and `test_make_dosemap_html_returns_html_bytes` with `explicit_patient=_PATIENT_FOR_EXPORT_TESTS`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unittests/test_gui_figures.py -v`
Expected: PASS

- [ ] **Step 5: Commit Task 1**

```bash
git add dev-docs/assessments/HTML_EXPORT_BACKGROUND_TASK_ERROR_20260719T123241.md tests/unittests/test_gui_figures.py
git commit -m "style(docs,tests): fix PR 22 review nitpicks (codeblock tags & fixture reuse)"
```

---

### Task 2: Make `check_commit_message.py` Worktree-Aware

**Files:**
- Modify: `scripts/check_commit_message.py:22-50`
- Modify: `tests/unittests/test_check_sensitive_content.py` (append after existing `resolve_*` tests, ~line 401)
- Modify: `dev-docs/TO_DO.md:117-124`

**Interfaces:**
- Consumes: `subprocess.run(["git", "rev-parse", ...])`
- Produces: Worktree-aware `resolve_commit_message_path(path)` resolution

- [ ] **Step 1: Write failing unit tests for worktree git directory resolution and security containment**

Add tests to `tests/unittests/test_check_sensitive_content.py`:
```python
def test_resolve_commit_message_path_supports_worktree_git_dir(tmp_path: Path, monkeypatch) -> None:
    import tempfile
    from scripts.check_commit_message import resolve_commit_message_path

    # Simulate a linked worktree COMMIT_EDITMSG path located inside .git/worktrees/branch_name/
    git_dir = tmp_path / ".git" / "worktrees" / "feature-branch"
    git_dir.mkdir(parents=True)
    msg_file = git_dir / "COMMIT_EDITMSG"
    msg_file.write_text("feat: worktree commit\n", encoding="utf-8")

    # Isolate tempfile.gettempdir so tmp_path is not automatically allowed as tempdir
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "fake_temp"))

    def mock_run(cmd, **kwargs):
        class Result:
            returncode = 0
            stdout = str(git_dir) if "--git-dir" in cmd else str(tmp_path / ".git")
        return Result()

    monkeypatch.setattr("scripts.check_commit_message.subprocess.run", mock_run)
    worktree_cwd = tmp_path / ".worktrees" / "feature-branch"
    worktree_cwd.mkdir(parents=True)
    monkeypatch.chdir(worktree_cwd)

    resolved = resolve_commit_message_path(msg_file)
    assert resolved == msg_file.resolve()


def test_resolve_worktree_roots_do_not_widen_to_arbitrary_paths(tmp_path: Path, monkeypatch) -> None:
    """Ensure _git_dir_roots() doesn't accidentally allow paths outside the repo."""
    import tempfile

    import pytest
    from scripts.check_commit_message import resolve_commit_message_path

    # Path strictly outside cwd, tempdir, and any git dir
    outside_dir = Path("/nonexistent_test_root_12345")
    msg_file = outside_dir / "COMMIT_EDITMSG"

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    monkeypatch.chdir(repo_dir)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path / "fake_temp"))

    # Mock git returning real-looking roots that still shouldn't allow outside_dir
    def mock_run(cmd, **kwargs):
        class Result:
            returncode = 0
            stdout = str(repo_dir / ".git")
        return Result()

    monkeypatch.setattr("scripts.check_commit_message.subprocess.run", mock_run)

    with pytest.raises(ValueError, match="commit-message path escapes repository"):
        resolve_commit_message_path(msg_file)
```

- [ ] **Step 2: Run tests to verify worktree test fails**

Run: `pytest tests/unittests/test_check_sensitive_content.py -k "test_resolve_commit_message_path" -v`
Expected: `test_resolve_commit_message_path_supports_worktree_git_dir` FAILS with `ValueError: commit-message path escapes repository`.

- [ ] **Step 3: Implement worktree-aware root resolution in `scripts/check_commit_message.py`**

In `scripts/check_commit_message.py`:
Add `import subprocess` and hardened `_git_dir_roots()` helper:
```python
import subprocess


def _git_dir_roots() -> list[Path]:
    roots: list[Path] = []
    for flag in ("--git-dir", "--git-common-dir"):
        try:
            res = subprocess.run(
                ["git", "rev-parse", flag],
                capture_output=True,
                text=True,
                check=False,
                timeout=2.0,
            )
            if res.returncode == 0 and res.stdout.strip():
                p = Path(res.stdout.strip()).resolve()
                if p not in roots:
                    roots.append(p)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return roots
```
And inside `resolve_commit_message_path`:
```python
    roots = (
        [root.resolve() for root in allowed_roots]
        if allowed_roots is not None
        else [
            Path.cwd().resolve(),
            (Path.cwd() / ".git").resolve(),
            Path(tempfile.gettempdir()).resolve(),
            *_git_dir_roots(),
        ]
    )
```

- [ ] **Step 4: Run tests to verify all resolve_commit_message_path tests pass**

Run: `pytest tests/unittests/test_check_sensitive_content.py -k "test_resolve_commit_message_path" -v`
Expected: PASS

- [ ] **Step 5: Run full test suite and pre-commit checks**

Run: `pytest tests/unittests/ -v`
Expected: All tests pass.

- [ ] **Step 6: Update `dev-docs/TO_DO.md` item**

In `dev-docs/TO_DO.md`:
Update item 117 to clarify that `commit-msg` hook containment is resolved, while pre-push hook `PATH` tracking in worktrees remains active:
```markdown
- [ ] **Worktree hook environment tracking** — `commit-msg` hook path resolution is worktree-aware (`resolve_commit_message_path` checks `--git-common-dir`/`--git-dir`). Pre-push hooks (basedpyright, gui-test-placement) still resolve `mypyskindose` from whichever editable install is on `PATH` — document or detect venv resolution when running pre-push hooks from linked worktrees.
```

- [ ] **Step 7: Commit Task 2**

```bash
git add scripts/check_commit_message.py tests/unittests/test_check_sensitive_content.py dev-docs/TO_DO.md
git commit -m "fix(hooks): make check_commit_message worktree-aware and update TO_DO"
```
