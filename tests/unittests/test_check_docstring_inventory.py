"""Unit tests for scripts/check_docstring_inventory.py."""

import ast
from pathlib import Path

import pytest

from scripts.check_docstring_inventory import (
    collect_missing,
    inventory_file,
    iter_module_scope,
    iter_source_files,
    main,
    plural,
)


def test_plural_singular_and_plural() -> None:
    assert plural(1, "file", "files") == "1 file"
    assert plural(2, "file", "files") == "2 files"
    assert plural(0, "file", "files") == "0 files"


def test_collect_missing_clean_module() -> None:
    tree = ast.parse('"""Doc."""\n\n\nclass Foo:\n    """Doc."""\n\n    def method(self):\n        """Doc."""\n')
    missing, totals = collect_missing(tree)
    assert missing == []
    assert totals == {"module": 1, "class": 1, "function": 0, "method": 1}


def test_collect_missing_reports_all_kinds() -> None:
    tree = ast.parse("import os\n\n\nclass Undoc:\n    def method(self):\n        pass\n\n\ndef func():\n    pass\n")
    missing, totals = collect_missing(tree)
    assert missing == ["<module>", "Undoc", "Undoc.method", "func"]
    assert totals["class"] == 1
    assert totals["function"] == 1
    assert totals["method"] == 1


def test_collect_missing_skips_private_and_dunder() -> None:
    tree = ast.parse(
        '"""Doc."""\n\n\ndef _hidden():\n    pass\n\n\nclass Foo:\n    """Doc."""\n\n'
        "    def _priv(self):\n        pass\n\n    def __init__(self):\n        pass\n"
    )
    missing, totals = collect_missing(tree)
    assert missing == []
    assert totals == {"module": 1, "class": 1, "function": 0, "method": 0}


def test_collect_missing_counts_async_and_nested_classes() -> None:
    tree = ast.parse(
        '"""Doc."""\n\n\nasync def afoo():\n    pass\n\n\nclass Outer:\n    """Doc."""\n\n'
        "    class Inner:\n        pass\n"
    )
    missing, totals = collect_missing(tree)
    assert missing == ["afoo", "Outer.Inner"]
    assert totals["function"] == 1
    assert totals["class"] == 2


def test_iter_module_scope_descends_into_guards() -> None:
    tree = ast.parse(
        "if True:\n    def guarded():\n        pass\n\ntry:\n    class Guarded:\n        pass\nexcept ImportError:\n"
        "    def fallback():\n        pass\n"
    )
    names = [node.name for node in iter_module_scope(tree.body)]
    assert names == ["guarded", "Guarded", "fallback"]


def test_inventory_file_marks_unparsable_skipped(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "broken.py"
    path.write_text("def broken(:\n", encoding="utf-8")
    inventory = inventory_file(path)
    assert inventory.skipped is True
    assert inventory.missing == []
    assert "skipped" in capsys.readouterr().err


def _write_src(root: Path, files: dict[str, str]) -> Path:
    src_dir = root / "src" / "guiskindose"
    src_dir.mkdir(parents=True)
    for name, content in files.items():
        (src_dir / name).write_text(content, encoding="utf-8")
    return root


def test_main_advisory_with_gaps(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_src(tmp_path, {"a.py": '"""Doc."""\n', "b.py": "def undoc():\n    pass\n"})
    assert main(["--repo-root", str(tmp_path)]) == 0
    out = capsys.readouterr()
    assert "missing src/guiskindose/b.py" in out.err
    assert "2 missing docstrings in 1 file" in out.out


def test_main_strict_fails_on_gaps(tmp_path: Path) -> None:
    _write_src(tmp_path, {"b.py": "def undoc():\n    pass\n"})
    assert main(["--repo-root", str(tmp_path), "--strict"]) == 1


def test_main_clean_tree_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_src(tmp_path, {"a.py": '"""Doc."""\n'})
    assert main(["--repo-root", str(tmp_path)]) == 0
    assert "Docstring inventory OK." in capsys.readouterr().out


def test_main_missing_src_dir_errors(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--repo-root", str(tmp_path)])


def test_main_external_absolute_src_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    ext_dir = tmp_path / "ext"
    ext_dir.mkdir()
    ext_file = ext_dir / "b.py"
    ext_file.write_text("def undoc():\n    pass\n", encoding="utf-8")

    assert main(["--repo-root", str(repo_dir), "--src-dir", str(ext_dir.resolve()), "--strict"]) == 1
    out = capsys.readouterr()
    assert f"missing {ext_file.resolve().as_posix()}: <module>, undoc" in out.err


def test_iter_source_files_excludes_private_modules(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "public.py").touch()
    (src_dir / "_private.py").touch()
    (src_dir / "__init__.py").touch()
    (src_dir / "__main__.py").touch()

    files = iter_source_files(src_dir)
    names = [f.name for f in files]
    assert names == ["__init__.py", "__main__.py", "public.py"]
