"""Unit tests for scripts/check_complexity.py."""

import json
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


def test_update_lowers_and_removes_caps(tmp_path: Path) -> None:
    from scripts.check_complexity import update

    _make_tree(tmp_path, {"probe.py": COMPLEX})
    _git_init(tmp_path)
    document = canonical_document(ruff_version(tmp_path), collect_findings(tmp_path))
    for entry in document["caps"]:
        entry["cap"] += 20
    stale = {"path": "src/probe.py", "function": "gone", "cap": 12}
    document["caps"].append(stale)
    _caps_file(tmp_path, document)
    assert update(tmp_path) == []
    rewritten = json.loads((tmp_path / "dev-docs" / "complexity_caps.json").read_bytes())
    assert rewritten["caps"] == canonical_document(ruff_version(tmp_path), collect_findings(tmp_path))["caps"]
    assert rewritten["tool_version"] == document["tool_version"]


def test_update_never_adds_caps(tmp_path: Path) -> None:
    from scripts.check_complexity import update

    _make_tree(tmp_path, {"probe.py": COMPLEX})
    document = canonical_document(ruff_version(tmp_path), [])
    _caps_file(tmp_path, document)
    assert update(tmp_path) == []
    rewritten = json.loads((tmp_path / "dev-docs" / "complexity_caps.json").read_bytes())
    assert rewritten["caps"] == []
    assert any("unlisted over-limit" in e for e in check(tmp_path))


def test_migrate_records_nonincreasing_rename(tmp_path: Path) -> None:
    from scripts.check_complexity import migrate

    _make_tree(tmp_path, {"probe.py": COMPLEX})
    _git_init(tmp_path)
    document = canonical_document(ruff_version(tmp_path), collect_findings(tmp_path))
    for entry in document["caps"]:
        entry["function"] = "complex_fn_renamed_old" if entry["function"] == "complex_fn" else entry["function"]
    _caps_file(tmp_path, document)
    # Source now defines complex_fn; caps hold the old name. A rename back to the real name:
    errors = migrate(tmp_path, "src/probe.py:complex_fn_renamed_old", "src/probe.py:complex_fn")
    assert errors == []
    rewritten = json.loads((tmp_path / "dev-docs" / "complexity_caps.json").read_bytes())
    assert rewritten["caps"][0]["function"] == "complex_fn"
    assert rewritten["caps"][0]["cap"] <= rewritten["migrations"][0]["old_cap"]  # nonincreasing
    record = rewritten["migrations"][0]
    assert record["old_function"] == "complex_fn_renamed_old"
    assert record["new_function"] == "complex_fn"
    assert record["new_cap"] <= record["old_cap"]


def test_migrate_rejects_missing_old_key(tmp_path: Path) -> None:
    from scripts.check_complexity import migrate

    _make_tree(tmp_path, {"probe.py": COMPLEX})
    _caps_file(tmp_path, canonical_document(ruff_version(tmp_path), collect_findings(tmp_path)))
    assert migrate(tmp_path, "src/probe.py:nope", "src/probe.py:complex_fn") != []


def test_migrate_rejects_new_key_already_capped(tmp_path: Path) -> None:
    from scripts.check_complexity import migrate

    _make_tree(tmp_path, {"probe.py": COMPLEX})
    _caps_file(tmp_path, canonical_document(ruff_version(tmp_path), collect_findings(tmp_path)))
    assert migrate(tmp_path, "src/probe.py:complex_fn", "src/probe.py:complex_fn") != []


def test_migrate_rejects_new_score_above_old_cap_without_writing(tmp_path: Path) -> None:
    from scripts.check_complexity import migrate

    _make_tree(tmp_path, {"probe.py": COMPLEX})
    document = canonical_document(ruff_version(tmp_path), collect_findings(tmp_path))
    document["caps"][0]["function"] = "old_name"
    document["caps"][0]["cap"] -= 1
    path = _caps_file(tmp_path, document)
    before = path.read_bytes()
    assert any("exceeds old cap" in error for error in migrate(tmp_path, "src/probe.py:old_name", "src/probe.py:complex_fn"))
    assert path.read_bytes() == before


def test_compare_caps_history_rejects_raised_and_unexplained_adds() -> None:
    from scripts.check_complexity import compare_caps_history

    base = {
        "schema_version": 1,
        "metric": "ruff-c901",
        "tool_version": "0.16.2",
        "threshold": 10,
        "caps": [{"path": "src/a.py", "function": "f", "cap": 12}],
        "migrations": [],
    }
    raised = json.loads(json.dumps(base))
    raised["caps"][0]["cap"] = 15
    assert any("raised cap" in e for e in compare_caps_history(base, raised))
    added = json.loads(json.dumps(base))
    added["caps"].append({"path": "src/a.py", "function": "g", "cap": 11})
    assert any("unexplained added cap" in e for e in compare_caps_history(base, added))
    metric = json.loads(json.dumps(base))
    metric["metric"] = "lizard"
    assert any("metric" in e for e in compare_caps_history(base, metric))
    threshold = json.loads(json.dumps(base))
    threshold["threshold"] = 8
    assert any("threshold" in e for e in compare_caps_history(base, threshold))


def test_compare_caps_history_validates_migration_one_to_one() -> None:
    from scripts.check_complexity import compare_caps_history

    base = {
        "schema_version": 1,
        "metric": "ruff-c901",
        "tool_version": "0.16.2",
        "threshold": 10,
        "caps": [{"path": "src/a.py", "function": "f", "cap": 12}],
        "migrations": [],
    }
    good = json.loads(json.dumps(base))
    good["caps"] = [{"path": "src/a.py", "function": "f2", "cap": 12}]
    good["migrations"] = [
        {"old_path": "src/a.py", "old_function": "f", "new_path": "src/a.py", "new_function": "f2", "old_cap": 12, "new_cap": 12}
    ]
    assert compare_caps_history(base, good) == []
    dup = json.loads(json.dumps(good))
    dup["migrations"].append(dict(good["migrations"][0]))
    assert any("at most once" in e for e in compare_caps_history(base, dup))
    old_still_there = json.loads(json.dumps(good))
    old_still_there["caps"].append({"path": "src/a.py", "function": "f", "cap": 12})
    assert any("still present" in e for e in compare_caps_history(base, old_still_there))
    raised_migration = json.loads(json.dumps(good))
    raised_migration["migrations"][0]["new_cap"] = 13
    assert any("migration raised cap" in e for e in compare_caps_history(base, raised_migration))


def test_check_base_history_against_origin_main(tmp_path: Path) -> None:
    from scripts.check_complexity import bootstrap

    repo = tmp_path / "repo"
    _make_tree(repo, {"probe.py": COMPLEX})
    _git_init(repo)
    assert bootstrap(repo) == []
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "add caps"], cwd=repo, check=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=repo, check=True)
    from scripts.check_complexity import check as _check

    # WT caps raised vs base -> fail
    document = json.loads((repo / "dev-docs" / "complexity_caps.json").read_bytes())
    for entry in document["caps"]:
        entry["cap"] += 5
    (repo / "dev-docs" / "complexity_caps.json").write_bytes(canonicalize(document))
    assert any("raised cap" in e or "cap above measured" in e for e in _check(repo))


def test_check_history_rejects_live_valid_unexplained_add(tmp_path: Path) -> None:
    _make_tree(
        tmp_path,
        {
            "probe.py": COMPLEX
            + "\n"
            + COMPLEX.replace("complex_fn", "complex_fn_b"),
        },
    )
    _git_init(tmp_path)
    findings = collect_findings(tmp_path)
    first_only = [f for f in findings if f.function == "complex_fn"]
    from scripts.check_complexity import bootstrap

    assert bootstrap(tmp_path) == []
    document = canonical_document(ruff_version(tmp_path), first_only)
    _caps_file(tmp_path, document)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "caps"], cwd=tmp_path, check=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=tmp_path, check=True)
    # WT now lists both functions with measured-exact caps (live-valid); history sees added B -> reject
    _caps_file(tmp_path, canonical_document(ruff_version(tmp_path), findings))
    assert any("unexplained added cap" in e for e in check(tmp_path))


def test_check_fails_closed_with_garbage_base_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    _git_init(tmp_path)
    from scripts.check_complexity import bootstrap

    bootstrap(tmp_path)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "caps"], cwd=tmp_path, check=True)
    monkeypatch.setenv("GITHUB_BASE_REF", "does-not-exist")
    assert any("not available" in e or "merge-base" in e for e in check(tmp_path))
    monkeypatch.delenv("GITHUB_BASE_REF")
    monkeypatch.setenv("COMPLEXITY_BEFORE_SHA", "0" * 40)
    assert any("not available" in e for e in check(tmp_path))


def test_check_fails_closed_when_origin_main_unavailable_and_caps_differ(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"], cwd=tmp_path, check=True)
    from scripts.check_complexity import bootstrap

    assert any("origin/main" in e for e in bootstrap(tmp_path))
    _caps_file(tmp_path, canonical_document(ruff_version(tmp_path), collect_findings(tmp_path)))
    # caps file differs from HEAD (untracked) and origin/main missing -> fail closed
    assert any("origin/main" in e for e in check(tmp_path))


def test_compare_caps_history_with_interleaved_sorted_migrations() -> None:
    from scripts.check_complexity import compare_caps_history

    r1 = {"old_path": "b.py", "old_function": "f", "new_path": "b.py", "new_function": "g", "old_cap": 15, "new_cap": 15}
    r2 = {"old_path": "a.py", "old_function": "f2", "new_path": "a.py", "new_function": "f3", "old_cap": 12, "new_cap": 12}
    old = {
        "schema_version": 1,
        "metric": "ruff-c901",
        "tool_version": "0.16.2",
        "threshold": 10,
        "caps": [
            {"path": "a.py", "function": "f2", "cap": 12},
            {"path": "b.py", "function": "g", "cap": 15},
        ],
        "migrations": [r1],
    }
    new = json.loads(json.dumps(old))
    new["caps"] = [
        {"path": "a.py", "function": "f3", "cap": 12},
        {"path": "b.py", "function": "g", "cap": 15},
    ]
    new["migrations"] = [r2, r1]  # r2 sorts earlier than r1
    assert new["migrations"][0]["old_path"] == "a.py"
    assert compare_caps_history(old, new) == []


def test_migration_record_must_match_base_old_cap() -> None:
    from scripts.check_complexity import compare_caps_history

    r = {"old_path": "a.py", "old_function": "f", "new_path": "a.py", "new_function": "g", "old_cap": 10, "new_cap": 10}
    old = {
        "schema_version": 1,
        "metric": "ruff-c901",
        "tool_version": "0.16.2",
        "threshold": 10,
        "caps": [{"path": "a.py", "function": "f", "cap": 12}],
        "migrations": [],
    }
    new = json.loads(json.dumps(old))
    new["caps"] = [{"path": "a.py", "function": "g", "cap": 10}]
    new["migrations"] = [r]
    assert any("old_cap mismatch" in e for e in compare_caps_history(old, new))


def test_check_fails_closed_when_origin_main_missing_even_if_unchanged(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"], cwd=tmp_path, check=True)
    _caps_file(tmp_path, canonical_document(ruff_version(tmp_path), collect_findings(tmp_path)))
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "caps"], cwd=tmp_path, check=True)
    assert any("origin/main unavailable" in e for e in check(tmp_path))


def test_committed_cap_raise_detected_on_branch(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    _git_init(tmp_path)
    from scripts.check_complexity import bootstrap

    bootstrap(tmp_path)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "caps v1"], cwd=tmp_path, check=True)
    base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    # Branch makes the function more complex AND raises its cap (live-valid, but a raise historically).
    source = (tmp_path / "src" / "probe.py").read_text(encoding="utf-8")
    expanded = source.replace("    return a", "    if a: a += 1\n" * 5 + "    return a", 1)
    (tmp_path / "src" / "probe.py").write_text(expanded, encoding="utf-8")
    _caps_file(tmp_path, canonical_document(ruff_version(tmp_path), collect_findings(tmp_path)))
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "raise"], cwd=tmp_path, check=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", base_sha], cwd=tmp_path, check=True)
    # WT matches HEAD (raised cap committed on the branch); local check must fail vs base.
    assert any("raised cap" in e for e in check(tmp_path))


def test_bootstrap_branch_later_cap_add_detected(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base"], cwd=tmp_path, check=True)
    base_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", base_sha], cwd=tmp_path, check=True)
    from scripts.check_complexity import bootstrap

    assert bootstrap(tmp_path) == []
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "caps introduced"], cwd=tmp_path, check=True)
    # Second commit adds a new over-limit function and a cap entry
    source = (tmp_path / "src" / "probe.py").read_text(encoding="utf-8")
    (tmp_path / "src" / "probe.py").write_text(source + "\n" + COMPLEX.replace("complex_fn", "complex_fn_b"), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    findings = collect_findings(tmp_path)
    _caps_file(tmp_path, canonical_document(ruff_version(tmp_path), findings))
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "add fn_b + cap"], cwd=tmp_path, check=True)
    assert any("unexplained added cap" in e for e in check(tmp_path))


def test_compare_caps_history_requires_old_records_preserved() -> None:
    from scripts.check_complexity import compare_caps_history

    old = {
        "schema_version": 1,
        "metric": "ruff-c901",
        "tool_version": "0.16.2",
        "threshold": 10,
        "caps": [],
        "migrations": [
            {"old_path": "a.py", "old_function": "f", "new_path": "a.py", "new_function": "g", "old_cap": 12, "new_cap": 12}
        ],
    }
    new = json.loads(json.dumps(old))
    assert compare_caps_history(old, new) == []
    tampered = json.loads(json.dumps(old))
    tampered["migrations"][0]["new_cap"] = 11
    assert any("preserved unchanged" in e for e in compare_caps_history(old, tampered))
    schema = json.loads(json.dumps(old))
    schema["schema_version"] = 2
    assert any("schema_version" in e for e in compare_caps_history(old, schema))


def test_check_passes_offline_when_caps_unchanged(tmp_path: Path) -> None:
    _make_tree(tmp_path, {"probe.py": COMPLEX})
    _git_init(tmp_path)
    from scripts.check_complexity import bootstrap

    bootstrap(tmp_path)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "caps"], cwd=tmp_path, check=True)
    subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=tmp_path, check=True)
    assert check(tmp_path) == []


def test_migrate_output_deterministic(tmp_path: Path) -> None:
    from scripts.check_complexity import migrate

    results = []
    for name in ("first", "second"):
        repo = tmp_path / name
        _make_tree(repo, {"probe.py": COMPLEX})
        _git_init(repo)
        _caps_file(repo, canonical_document(ruff_version(repo), collect_findings(repo)))
        document = json.loads((repo / "dev-docs" / "complexity_caps.json").read_bytes())
        for entry in document["caps"]:
            entry["function"] = "old_" + entry["function"] if entry["function"] == "complex_fn" else entry["function"]
        (repo / "dev-docs" / "complexity_caps.json").write_bytes(canonicalize(document))
        migrate(repo, "src/probe.py:old_complex_fn", "src/probe.py:complex_fn")
        results.append((repo / "dev-docs" / "complexity_caps.json").read_bytes())
    assert results[0] == results[1]


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
