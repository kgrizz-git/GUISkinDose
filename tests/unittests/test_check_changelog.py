"""Unit tests for scripts/check_changelog.py (base resolution + exemptions)."""

import subprocess

import pytest

from scripts import check_changelog


def _completed(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_resolve_base_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_BASE_REF", "main")
    assert check_changelog.resolve_base() == "origin/main"


def test_resolve_base_merge_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.setattr(check_changelog, "_git", lambda *a: _completed(stdout="abc123\n"))
    assert check_changelog.resolve_base() == "abc123"


def test_resolve_base_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    monkeypatch.setattr(check_changelog, "_git", lambda *a: _completed(returncode=1))
    assert check_changelog.resolve_base() is None


def _main_with_changed(monkeypatch: pytest.MonkeyPatch, changed: list[str]) -> int:
    monkeypatch.setattr(check_changelog, "resolve_base", lambda: "base")
    monkeypatch.setattr(check_changelog, "changed_files", lambda base: changed)
    return check_changelog.main()


def test_src_change_without_changelog_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _main_with_changed(monkeypatch, ["src/a.py"]) == 1


def test_changelog_touched_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _main_with_changed(monkeypatch, ["src/a.py", "CHANGELOG.md"]) == 0


def test_tests_only_without_changelog_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _main_with_changed(monkeypatch, ["tests/test_a.py"]) == 1


def test_maintenance_log_exemption_for_tests_only_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    """Process-only exemption: tests + maintenance log, no user-facing entry."""
    changed = ["tests/unittests/test_check_todo_cleanup.py", "dev-docs/MAINTENANCE_LOG.md"]
    assert _main_with_changed(monkeypatch, changed) == 0


def test_maintenance_log_does_not_exempt_src_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    changed = ["src/a.py", "dev-docs/MAINTENANCE_LOG.md"]
    assert _main_with_changed(monkeypatch, changed) == 1


def _main_with_sources(
    monkeypatch: pytest.MonkeyPatch,
    changed: list[str],
    before: dict[str, str],
    after: dict[str, str],
) -> int:
    """Drive main() through real lexing, stubbing only git's file reads.

    Deliberately stubs `_file_at` and not `is_comment_only`: two earlier versions of this
    check were wrong inside the classifier, and tests that stubbed the layer above it passed
    anyway. Everything below this seam is the production code path.
    """
    monkeypatch.setattr(check_changelog, "resolve_base", lambda: "base")
    monkeypatch.setattr(check_changelog, "changed_files", lambda base: changed)
    monkeypatch.setattr(
        check_changelog,
        "_file_at",
        lambda ref, path: (before if ref == "base" else after).get(path),
    )
    return check_changelog.main()


_LOG = "dev-docs/MAINTENANCE_LOG.md"


def test_a_comment_only_change_is_satisfied_by_the_maintenance_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """CHANGELOG.md documents itself as user-facing; a comment has no honest entry there."""
    rc = _main_with_sources(
        monkeypatch, ["src/a.py", _LOG], {"src/a.py": "x = 1\n"}, {"src/a.py": "# why x is 1\nx = 1\n"}
    )
    assert rc == 0


def test_comment_only_still_needs_the_maintenance_log(monkeypatch: pytest.MonkeyPatch) -> None:
    rc = _main_with_sources(monkeypatch, ["src/a.py"], {"src/a.py": "x = 1\n"}, {"src/a.py": "# note\nx = 1\n"})
    assert rc == 1


def test_commenting_code_out_is_not_comment_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """The everyday "comment out the code" edit changes behaviour and must be announced."""
    rc = _main_with_sources(
        monkeypatch, ["src/a.py", _LOG], {"src/a.py": "x = compute()\n"}, {"src/a.py": "# disabled\n"}
    )
    assert rc == 1


def test_a_statement_beside_an_added_comment_is_not_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression for the retired diff parser.

    `++i` reached it as `+++i`, was mistaken for a `+++ b/path` file header, and vanished —
    so a real statement counted as comment-only when it arrived next to an added comment.
    Token comparison has no line classification left to get wrong.
    """
    rc = _main_with_sources(
        monkeypatch, ["src/a.py", _LOG], {"src/a.py": "i = 0\n"}, {"src/a.py": "# a note\ni = 0\n++i\n"}
    )
    assert rc == 1


def test_a_hash_inside_a_string_literal_is_not_a_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    """A `#` line inside a triple-quoted string is a value, and changing it changes behaviour."""
    rc = _main_with_sources(
        monkeypatch,
        ["src/a.py", _LOG],
        {"src/a.py": 's = """\n# original\n"""\n'},
        {"src/a.py": 's = """\n# altered\n"""\n'},
    )
    assert rc == 1


def test_a_docstring_edit_is_not_comment_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Docstrings are STRING tokens, so the safe direction is to demand the entry."""
    rc = _main_with_sources(
        monkeypatch,
        ["src/a.py", _LOG],
        {"src/a.py": 'def f():\n    """a"""\n'},
        {"src/a.py": 'def f():\n    """b"""\n'},
    )
    assert rc == 1


def test_an_unlexable_file_is_never_exempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lexical classification failing must not grant the exemption by default."""
    rc = _main_with_sources(monkeypatch, ["src/a.py", _LOG], {"src/a.py": "x = 1\n"}, {"src/a.py": "x = (\n"})
    assert rc == 1


def test_a_new_file_is_never_comment_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """`git show base:path` fails for a file that did not exist; that is not an exemption."""
    rc = _main_with_sources(monkeypatch, ["src/a.py", _LOG], {}, {"src/a.py": "# only a comment\n"})
    assert rc == 1


def test_a_non_python_src_change_is_never_comment_only(monkeypatch: pytest.MonkeyPatch) -> None:
    rc = _main_with_sources(
        monkeypatch,
        ["src/guiskindose/gui/ui_copy.json", _LOG],
        {"src/guiskindose/gui/ui_copy.json": "{}\n"},
        {"src/guiskindose/gui/ui_copy.json": '{"a": 1}\n'},
    )
    assert rc == 1


def test_a_mixed_diff_still_demands_the_changelog(monkeypatch: pytest.MonkeyPatch) -> None:
    """A comment in one file does not excuse a code change in another."""
    rc = _main_with_sources(
        monkeypatch,
        ["src/a.py", "src/b.py", _LOG],
        {"src/a.py": "x = 1\n", "src/b.py": "y = 1\n"},
        {"src/a.py": "# note\nx = 1\n", "src/b.py": "y = 2\n"},
    )
    assert rc == 1


def test_a_deleted_file_is_never_comment_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """`git show HEAD:path` fails for a file this branch removed; deletion is behavioural."""
    rc = _main_with_sources(monkeypatch, ["src/a.py", _LOG], {"src/a.py": "# only a comment\n"}, {})
    assert rc == 1


def test_identical_content_is_never_comment_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """A file listed as changed whose content matches — a mode change, say — is not exempt."""
    rc = _main_with_sources(monkeypatch, ["src/a.py", _LOG], {"src/a.py": "x = 1\n"}, {"src/a.py": "x = 1\n"})
    assert rc == 1


def test_a_tool_directive_comment_stays_exempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pins a judgement call rather than an accident.

    `# type: ignore`, `# noqa` and friends are COMMENT tokens, so they are exempt. They
    change linter and type-checker outcomes, not what the program computes, and the
    MAINTENANCE_LOG entry the exemption still requires records them. If the team ever decides
    static-analysis suppressions belong in CHANGELOG.md, this test is the one to flip.
    """
    rc = _main_with_sources(
        monkeypatch, ["src/a.py", _LOG], {"src/a.py": "x = f()\n"}, {"src/a.py": "x = f()  # type: ignore\n"}
    )
    assert rc == 0


def test_an_encoding_cookie_change_stays_exempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Also a COMMENT token. It matters only for non-UTF-8 source, which this repo has none of."""
    rc = _main_with_sources(
        monkeypatch,
        ["src/a.py", _LOG],
        {"src/a.py": "x = 1\n"},
        {"src/a.py": "# -*- coding: utf-8 -*-\nx = 1\n"},
    )
    assert rc == 0


def test_an_undecodable_file_is_refused_not_crashed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The decode happens in subprocess.run, outside the lexer's try, so guard it there."""

    def explode(*_args: str) -> subprocess.CompletedProcess[str]:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(check_changelog, "_git", explode)
    assert check_changelog._file_at("base", "src/a.py") is None
    assert check_changelog.is_comment_only("base", "src/a.py") is False


def test_a_spacing_only_reformat_is_exempt_but_a_real_one_is_not(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pins exactly which reformats the exemption covers.

    The maintenance log first claimed "a pure reformat" was exempt, which was too broad.
    Spacing is invisible to the token stream, but quote normalisation changes the STRING
    spelling and reindentation changes the INDENT token, so those still demand an entry —
    which is why a real `ruff format` diff would probably still trip the gate.
    """
    spacing = _main_with_sources(monkeypatch, ["src/a.py", _LOG], {"src/a.py": "x=1\n"}, {"src/a.py": "x = 1\n"})
    assert spacing == 0

    quotes = _main_with_sources(monkeypatch, ["src/a.py", _LOG], {"src/a.py": "s = 'a'\n"}, {"src/a.py": 's = "a"\n'})
    assert quotes == 1

    reindent = _main_with_sources(
        monkeypatch, ["src/a.py", _LOG], {"src/a.py": "if x:\n\ty = 1\n"}, {"src/a.py": "if x:\n    y = 1\n"}
    )
    assert reindent == 1

    parens = _main_with_sources(monkeypatch, ["src/a.py", _LOG], {"src/a.py": "x = 1\n"}, {"src/a.py": "x = (1)\n"})
    assert parens == 1
