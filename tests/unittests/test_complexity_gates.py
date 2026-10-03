"""Unit tests for scripts/check_complexity.py."""

import subprocess
from pathlib import Path

import pytest

from scripts.check_complexity import (
    THRESHOLD,
    bootstrap,
    canonical_document,
    canonicalize,
    check,
    collect_findings,
    main,
    measurement_errors,
    parse_findings,
    qualified_names_by_row,
    ruff_version,
    synthesize_findings,
    validate_caps_file,
)

COMPLEX = """
def complex_fn():
    a = 1
    if a: a += 1
    if a: a += 1
    if a: a += 1
    if a: a += 1
    if a: a += 1
    if a: a += 1
    if a: a += 1
    if a: a += 1
    if a: a += 1
    if a: a += 1
    if a: a += 1
    return a
"""


def _make_tree(root: Path, sources: dict[str, str]) -> None:
    """Write synthetic Python sources under ``src/`` in ``root``."""
    src = root / "src"
    src.mkdir(parents=True, exist_ok=True)
    for name, text in sources.items():
        (src / name).write_text(text, encoding="utf-8")


def _git_init(root: Path) -> None:
    """Give ``root`` a valid HEAD so the bootstrap guard's ref checks work."""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "init"],
        cwd=root,
        check=True,
    )
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=root, check=True)


def _caps_file(root: Path, document: dict) -> Path:
    path = root / "dev-docs" / "complexity_caps.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonicalize(document))
    return path


def _measured_document(root: Path) -> dict:
    return canonical_document(ruff_version(root), collect_findings(root))


def test_qualifies_methods_nested_async_and_decorated(tmp_path: Path) -> None:
    source = """
class Foo:
    def method(self):
        return 1
    def outer(self):
        def nested():
            return 1
        return nested
async def afunc():
    return 1
import functools
def dec(f):
    return f
@dec
def decorated():
    return 1
"""
    _make_tree(tmp_path, {"probe.py": source})
    rows = qualified_names_by_row(tmp_path / "src" / "probe.py")
    names = set(rows.values())
    assert {"Foo.method", "Foo.outer", "Foo.outer.nested", "afunc", "decorated"} <= names


def test_collect_findings_keys_qualified_names(tmp_path: Path) -> None:
    source = (
        "class Widget:\n"
        "    def run(self):\n"
        "        a = 1\n"
        + "\n".join(["        if a: a += 1"] * 10)
        + "\n        return a\n"
    )
    _make_tree(tmp_path, {"probe.py": source})
    findings = collect_findings(tmp_path)
    assert findings
    assert all(f.function == "Widget.run" for f in findings)
    assert all(f.score > THRESHOLD for f in findings)
    assert findings[0].path == "src/probe.py"


def test_synthesize_rejects_missing_join(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    with pytest.raises(ValueError, match="no def at row"):
        synthesize_findings(tmp_path, [(tmp_path / "src" / "probe.py", 9999, "complex_fn", 11)])


def test_synthesize_rejects_name_mismatch(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    import scripts.check_complexity as cc

    row = next(iter(cc.qualified_names_by_row(tmp_path / "src" / "probe.py")))
    with pytest.raises(ValueError, match="name mismatch"):
        synthesize_findings(tmp_path, [(tmp_path / "src" / "probe.py", row, "wrong_name", 11)])


def test_parse_findings_rejects_unexpected_shapes() -> None:
    with pytest.raises(ValueError, match="unexpected ruff diagnostic shape"):
        parse_findings([{"code": "E501", "filename": "a.py", "location": {"row": 1}, "message": "x"}])
    with pytest.raises(ValueError, match="ruff reported threshold"):
        parse_findings(
            [
                {
                    "code": "C901",
                    "name": "complex-structure",
                    "filename": "a.py",
                    "location": {"row": 1},
                    "message": "`f` is too complex (11 > 8)",
                }
            ]
        )


def test_check_passes_with_exact_measured_caps(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    _caps_file(tmp_path, _measured_document(tmp_path))
    assert check(tmp_path) == []


def test_check_reports_unlisted_over_limit(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    _caps_file(tmp_path, canonical_document(ruff_version(tmp_path), []))
    assert any("unlisted over-limit" in e for e in check(tmp_path))


def test_check_reports_over_cap(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    document = canonical_document(ruff_version(tmp_path), [])
    document["caps"].append({"path": "src/probe.py", "function": "complex_fn", "cap": 1})
    document["caps"] = sorted(document["caps"], key=lambda e: (e["path"], e["function"]))
    _caps_file(tmp_path, document)
    assert any("over cap" in e for e in check(tmp_path))


def test_check_reports_cap_above_measured_score(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    document = _measured_document(tmp_path)
    for entry in document["caps"]:
        entry["cap"] += 5
    _caps_file(tmp_path, document)
    assert any("cap above measured score" in e for e in check(tmp_path))


def test_check_reports_stale_cap(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": "def simple():\n    return 1\n"})
    document = {
        "schema_version": 1,
        "metric": "ruff-c901",
        "tool_version": ruff_version(tmp_path),
        "threshold": THRESHOLD,
        "caps": [{"path": "src/probe.py", "function": "simple", "cap": 12}],
        "migrations": [],
    }
    _caps_file(tmp_path, document)
    assert any("stale cap entry" in e for e in check(tmp_path))


def test_check_reports_tool_version_drift(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    document = _measured_document(tmp_path)
    document["tool_version"] = "0.0.0"
    _caps_file(tmp_path, document)
    assert any("does not match locked ruff" in e for e in check(tmp_path))


def test_check_rejects_noncanonical_file(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    path = tmp_path / "dev-docs" / "complexity_caps.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{ "schema_version": 1   }', encoding="utf-8")
    assert any("canonical" in e for e in check(tmp_path))


def test_validate_caps_file_rejects_duplicate_entries(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    document = _measured_document(tmp_path)
    document["caps"].append(dict(document["caps"][0]))
    _caps_file(tmp_path, document)
    _, errors = validate_caps_file(tmp_path / "dev-docs" / "complexity_caps.json", ruff_version(tmp_path))
    assert any("duplicate" in e for e in errors)


def test_check_missing_caps_file(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    assert any("caps file missing" in e for e in check(tmp_path))


def test_measurement_errors_clean_tree(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": "def simple():\n    return 1\n"})
    assert measurement_errors([], canonical_document(ruff_version(tmp_path), [])) == []


def test_main_update_and_migrate_are_deferred(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--update"]) == 2
    assert main(["--migrate", "a:b", "c:d"]) == 2
    assert "chunk 2" in capsys.readouterr().err


def test_bootstrap_creates_validates_and_refuses_rerun(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    _git_init(tmp_path)
    assert bootstrap(tmp_path) == []
    path = tmp_path / "dev-docs" / "complexity_caps.json"
    document, errors = validate_caps_file(path, ruff_version(tmp_path))
    assert errors == [] and document is not None
    assert {e["function"] for e in document["caps"]} == {"complex_fn"}
    assert bootstrap(tmp_path) != []


def test_bootstrap_fails_closed_without_origin_main(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "init"],
        cwd=tmp_path,
        check=True,
    )
    errors = bootstrap(tmp_path)
    assert any("origin/main" in e for e in errors)
    assert not (tmp_path / "dev-docs" / "complexity_caps.json").exists()


def test_bootstrap_output_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _make_tree(first, {"probe.py": COMPLEX})
    _make_tree(second, {"probe.py": COMPLEX})
    _git_init(first)
    _git_init(second)
    bootstrap(first)
    bootstrap(second)
    assert (first / "dev-docs" / "complexity_caps.json").read_bytes() == (
        second / "dev-docs" / "complexity_caps.json"
    ).read_bytes()
