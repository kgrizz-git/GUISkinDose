"""Unit tests for scripts/check_todo_cleanup.py."""

import subprocess

import pytest

from scripts import check_todo_cleanup
from scripts.check_todo_cleanup import OpenItem, evaluate, extract_paths, match_items, parse_open_items


def test_parse_open_items_collects_only_open_with_continuations():
    text = (
        "# Backlog\n\n"
        "- [ ] **DSfloat leak** — pydicom `DSfloat` values reach\n"
        "  `gui/tabs/data.py:126` and crash the socket emit.\n"
        "- [x] **Done thing** — already finished, touches `src/a.py`.\n"
        "- [ ] **Plain item** — no file references here.\n"
    )
    items = parse_open_items(text)
    assert [item.title for item in items] == ["**DSfloat leak** — pydicom `DSfloat` values reach", "**Plain item** — no file references here."]
    assert "gui/tabs/data.py:126" in items[0].text


def test_parse_open_items_stops_at_headings():
    text = "## Next Up\n\n- [ ] **A** — touches `src/a.py`.\n\n## Later\n\nSome prose.\n"
    items = parse_open_items(text)
    assert len(items) == 1


def test_extract_paths_backticked_and_bare():
    text = "See `gui/tabs/data.py:126`, `dataframe.to_dict`, src/guiskindose/gui/helpers.py and `CHANGELOG.md`."
    paths = extract_paths(text)
    assert "gui/tabs/data.py" in paths
    assert "src/guiskindose/gui/helpers.py" in paths
    assert "CHANGELOG.md" in paths
    assert "dataframe.to_dict" not in paths


def test_extract_paths_strips_line_numbers():
    assert extract_paths("see `gui/tabs/data.py:126` fixed") == {"gui/tabs/data.py"}
    assert extract_paths("see `plans/X.md:10-20` fixed") == {"plans/X.md"}


def test_match_items_suffix_and_exact():
    items = [
        OpenItem(title="short form", text="touches gui/tabs/data.py"),
        OpenItem(title="exact", text="touches src/guiskindose/gui/helpers.py"),
        OpenItem(title="unrelated", text="touches docs/other.md"),
    ]
    changed = ["src/guiskindose/gui/tabs/data.py", "src/guiskindose/gui/helpers.py"]
    hits = match_items(items, changed)
    assert [item.title for item, _ in hits] == ["short form", "exact"]


def test_match_items_no_false_positive_on_prose():
    items = [OpenItem(title="plain", text="Just words, no file references.")]
    assert match_items(items, ["src/guiskindose/gui/helpers.py"]) == []


def test_match_items_rejects_partial_filename_suffixes():
    items = [
        OpenItem(title="partial", text="touches `a.py`"),
        OpenItem(title="reverse", text="touches `src/a.py`"),
    ]
    # a.py must not match src/data.py (partial filename);
    # src/a.py must not match changed bare b.py (reverse).
    assert match_items(items, ["src/data.py", "b.py"]) == []


def test_clean_candidate_rejects_non_paths():
    assert extract_paths("see `dataframe.to_dict` soon") == set()
    assert extract_paths("see `` soon") == set()
    assert extract_paths("see `a b` soon") == set()


def test_git_passthrough() -> None:
    result = check_todo_cleanup._git("--version")
    assert result.returncode == 0
    assert "git version" in result.stdout


def test_evaluate_reports_matches_and_exit_codes():
    todo = "- [ ] **A** — touches `src/a.py`.\n"
    code, report = evaluate(todo, ["src/a.py"], strict=False)
    assert code == 0
    assert "src/a.py" in report and "**A**" in report
    code, _ = evaluate(todo, ["src/a.py"], strict=True)
    assert code == 1


def test_evaluate_quiet_without_matches():
    assert evaluate("- [ ] **A** — no files.\n", ["src/a.py"], strict=True) == (0, "")
    assert evaluate("", ["src/a.py"], strict=True) == (0, "")


def test_resolve_base_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    assert check_todo_cleanup.resolve_base() == "origin/main"


def _completed(args: list[str], returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr="")


def test_resolve_base_merge_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.setattr(check_todo_cleanup, "_git", lambda *a: _completed(list(a), stdout="abc123\n"))
    assert check_todo_cleanup.resolve_base() == "abc123"


def test_resolve_base_none_when_undetermined(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.setattr(check_todo_cleanup, "_git", lambda *a: _completed(list(a), returncode=1))
    assert check_todo_cleanup.resolve_base() is None
    monkeypatch.setattr(check_todo_cleanup, "_git", lambda *a: _completed(list(a), stdout="  \n"))
    assert check_todo_cleanup.resolve_base() is None


def test_changed_files_ok_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        check_todo_cleanup, "_git", lambda *a: _completed(list(a), stdout="a.py\n\nb.py\n")
    )
    assert check_todo_cleanup.changed_files("base") == ["a.py", "b.py"]
    monkeypatch.setattr(check_todo_cleanup, "_git", lambda *a: _completed(list(a), returncode=1))
    assert check_todo_cleanup.changed_files("base") == []


def test_main_no_base_exits_zero(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(check_todo_cleanup, "resolve_base", lambda: None)
    assert check_todo_cleanup.main([]) == 0
    assert "undetermined" in capsys.readouterr().err


def test_main_missing_todo_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(check_todo_cleanup, "resolve_base", lambda: "base")
    monkeypatch.setattr(check_todo_cleanup, "TODO_PATH", tmp_path / "TO_DO.md")
    assert check_todo_cleanup.main([]) == 0


def test_main_reports_hits(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    todo = tmp_path / "TO_DO.md"
    todo.write_text("- [ ] **A** — touches `src/a.py`.\n", encoding="utf-8")
    monkeypatch.setattr(check_todo_cleanup, "resolve_base", lambda: "base")
    monkeypatch.setattr(check_todo_cleanup, "TODO_PATH", todo)
    monkeypatch.setattr(check_todo_cleanup, "changed_files", lambda base: ["src/a.py"])
    assert check_todo_cleanup.main([]) == 0
    assert "src/a.py" in capsys.readouterr().out
    assert check_todo_cleanup.main(["--strict"]) == 1
