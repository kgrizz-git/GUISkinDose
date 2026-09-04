"""Tests for scripts/rewrite_package_paths.py (PR 0 GUISkinDose rename helper)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.rewrite_package_paths import (
    _is_line_allowlisted,
    rewrite_inventory_paths,
    rewrite_path_prefix,
    scan_leftover_brand,
)

# ---------------------------------------------------------------------------
# rewrite_path_prefix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("src/mypyskindose/gui/app.py", "src/guiskindose/gui/app.py"),
        ("src/mypyskindose/example_data/RDSR/x.dcm", "src/guiskindose/example_data/RDSR/x.dcm"),
    ],
)
def test_rewrite_path_prefix_rewrites_src_package(old: str, new: str) -> None:
    assert rewrite_path_prefix(old) == new


@pytest.mark.parametrize(
    "path",
    [
        "src/mypyskindose",  # no trailing slash — not a prefix match
        "docs/source/user/figures/beam/beam_ap1.svg",
        "github.com/kgrizz-git/MyPySkinDose",  # URL, not a src path
        "mypyskindose-privacy",  # Semgrep rule ID fragment
        "src/guiskindose/gui/app.py",  # already renamed
    ],
)
def test_rewrite_path_prefix_leaves_others_untouched(path: str) -> None:
    assert rewrite_path_prefix(path) == path


# ---------------------------------------------------------------------------
# rewrite_inventory_paths (pure function)
# ---------------------------------------------------------------------------


def _make_inventory() -> dict[str, Any]:
    return {
        "version": 1,
        "assets": [
            {
                "path": "src/mypyskindose/gui/app.py",
                "sha256": "a" * 64,
                "kind": "image",
                "purpose": "GUI entry",
                "review": {"status": "approved", "reviewer": "KG", "reviewed_on": "2026-07-13"},
            },
            {
                "path": "docs/source/user/figures/beam/beam_ap1.svg",
                "sha256": "b" * 64,
                "kind": "image",
                "purpose": "Doc figure",
                "review": {"status": "approved", "reviewer": "KG", "reviewed_on": "2026-07-13"},
            },
        ],
    }


def test_rewrite_inventory_paths_rewrites_only_src_package() -> None:
    data = _make_inventory()
    rewritten, changes = rewrite_inventory_paths(data)

    assert changes == [("src/mypyskindose/gui/app.py", "src/guiskindose/gui/app.py")]
    assets = rewritten["assets"]
    assert assets[0]["path"] == "src/guiskindose/gui/app.py"
    assert assets[1]["path"] == "docs/source/user/figures/beam/beam_ap1.svg"


def test_rewrite_inventory_paths_preserves_metadata() -> None:
    data = _make_inventory()
    rewritten, _ = rewrite_inventory_paths(data)

    original_first = data["assets"][0]
    rewritten_first = rewritten["assets"][0]
    for key in ("sha256", "kind", "purpose", "review"):
        assert rewritten_first[key] == original_first[key]
    # Original input must not be mutated.
    assert original_first["path"] == "src/mypyskindose/gui/app.py"


def test_rewrite_inventory_paths_returns_new_structure() -> None:
    data = _make_inventory()
    rewritten, _ = rewrite_inventory_paths(data)
    assert rewritten is not data
    assert rewritten["assets"] is not data["assets"]


def test_rewrite_inventory_paths_no_changes_returns_empty() -> None:
    data = {
        "version": 1,
        "assets": [
            {"path": "docs/foo.svg", "sha256": "c" * 64, "kind": "image", "purpose": "x", "review": {}},
        ],
    }
    _, changes = rewrite_inventory_paths(data)
    assert changes == []


def test_rewrite_inventory_paths_recurses_into_nested_structures() -> None:
    data = {
        "version": 1,
        "assets": [
            {
                "path": "src/mypyskindose/gui/app.py",
                "sha256": "d" * 64,
                "kind": "image",
                "purpose": "x",
                "review": {},
                "alternatives": [
                    {"path": "src/mypyskindose/gui/alt.py"},
                    {"path": "docs/other.md"},
                ],
            }
        ],
    }
    rewritten, changes = rewrite_inventory_paths(data)

    assert ("src/mypyskindose/gui/app.py", "src/guiskindose/gui/app.py") in changes
    assert ("src/mypyskindose/gui/alt.py", "src/guiskindose/gui/alt.py") in changes
    alts = rewritten["assets"][0]["alternatives"]
    assert alts[0]["path"] == "src/guiskindose/gui/alt.py"
    assert alts[1]["path"] == "docs/other.md"


# ---------------------------------------------------------------------------
# CLI: rewrite subcommand (dry-run vs apply)
# ---------------------------------------------------------------------------


def test_cli_rewrite_dry_run_does_not_write(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    inventory = _make_inventory()
    inv_path = tmp_path / "approved_asset_inventory.json"
    inv_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    original_text = inv_path.read_text(encoding="utf-8")

    from scripts.rewrite_package_paths import main

    ret = main(["rewrite", "--inventory", str(inv_path)])
    assert ret == 0
    assert inv_path.read_text(encoding="utf-8") == original_text
    captured = capsys.readouterr()
    assert "DRY RUN" in captured.out
    assert "src/mypyskindose/gui/app.py" in captured.out
    assert "src/guiskindose/gui/app.py" in captured.out


def test_cli_rewrite_apply_writes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    inventory = _make_inventory()
    inv_path = tmp_path / "approved_asset_inventory.json"
    inv_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    from scripts.rewrite_package_paths import main

    ret = main(["rewrite", "--inventory", str(inv_path), "--apply"])
    assert ret == 0
    rewritten = json.loads(inv_path.read_text(encoding="utf-8"))
    assert rewritten["assets"][0]["path"] == "src/guiskindose/gui/app.py"
    # Trailing newline preserved.
    assert inv_path.read_text(encoding="utf-8").endswith("\n")
    # Metadata preserved.
    assert rewritten["assets"][0]["sha256"] == "a" * 64
    assert rewritten["assets"][0]["review"]["reviewer"] == "KG"
    captured = capsys.readouterr()
    assert "Rewrote" in captured.out
    assert "render_asset_inventory.py --write" in captured.out


def test_cli_rewrite_no_changes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    inventory = {
        "version": 1,
        "assets": [
            {"path": "docs/foo.svg", "sha256": "e" * 64, "kind": "image", "purpose": "x", "review": {}},
        ],
    }
    inv_path = tmp_path / "approved_asset_inventory.json"
    inv_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    from scripts.rewrite_package_paths import main

    ret = main(["rewrite", "--inventory", str(inv_path)])
    assert ret == 0
    captured = capsys.readouterr()
    assert "No" in captured.out and "paths to rewrite" in captured.out


# ---------------------------------------------------------------------------
# scan_leftover_brand + allowlist
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, rel: str, contents: str) -> Path:
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


def test_scan_leftover_brand_reports_hits(tmp_path: Path) -> None:
    _write(tmp_path, "src/mypyskindose/gui/app.py", "import mypyskindose\nx = 1\n")
    hits = scan_leftover_brand(tmp_path, [Path("src")])
    assert len(hits) == 1
    assert hits[0][1] == 1
    assert "mypyskindose" in hits[0][2]


def test_scan_leftover_brand_allowlists_nosemgrep(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/mypyskindose/gui/export.py",
        "x = 1  # nosemgrep: mypyskindose-log\ny = mypyskindose\n",
    )
    hits = scan_leftover_brand(tmp_path, [Path("src")])
    # The nosemgrep line is allowlisted; the bare reference is not.
    assert len(hits) == 1
    assert hits[0][1] == 2


def test_scan_leftover_brand_allowlists_rule_ids(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/mypyskindose/gui/export.py",
        "id: mypyskindose-log\nrules:\n  - mypyskindose-export\n",
    )
    hits = scan_leftover_brand(tmp_path, [Path("src")])
    # The "id:" line is allowlisted as a YAML rule ID; the bare list item is not.
    assert len(hits) == 1
    assert hits[0][1] == 3


def test_scan_leftover_brand_allowlists_archive_and_plan_paths(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "dev-docs/plans/archive/old_plan.md",
        "This still says mypyskindose in an archived plan.\n",
    )
    _write(
        tmp_path,
        "dev-docs/assessments/old.md",
        "Assessment mentions mypyskindose.\n",
    )
    _write(
        tmp_path,
        "dev-docs/plans/GUISKINDOSE_RENAME_PLAN.md",
        "mypyskindose -> guiskindose\n",
    )
    hits = scan_leftover_brand(tmp_path, [Path("dev-docs")])
    assert hits == []


def test_scan_leftover_brand_allowlists_github_url(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "docs/foo.md",
        "See https://github.com/kgrizz-git/MyPySkinDose for details.\n",
    )
    hits = scan_leftover_brand(tmp_path, [Path("docs")])
    assert hits == []


def test_scan_leftover_brand_skips_changelog(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "CHANGELOG.md",
        "## 25.1.0\n- Renamed from mypyskindose.\n",
    )
    hits = scan_leftover_brand(tmp_path, [Path("CHANGELOG.md")])
    assert hits == []


def test_scan_leftover_brand_skips_binary_files(tmp_path: Path) -> None:
    path = tmp_path / "src" / "mypyskindose" / "data.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x01\x02" + b"mypyskindose" + b"\xff\xfe")
    hits = scan_leftover_brand(tmp_path, [Path("src")])
    assert hits == []


def test_scan_leftover_brand_reports_brand_and_env_prefix(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "src/foo.py",
        'APP_NAME = "MyPySkinDose"\nos.environ["MYPYSKINDOSE_SHOW"]\n',
    )
    hits = scan_leftover_brand(tmp_path, [Path("src")])
    assert len(hits) == 2
    assert "MyPySkinDose" in hits[0][2]
    assert "MYPYSKINDOSE_" in hits[1][2]


def test_scan_leftover_brand_exit_zero_even_with_hits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write(tmp_path, "src/foo.py", "import mypyskindose\n")
    from scripts.rewrite_package_paths import main

    monkeypatch.setattr("scripts.rewrite_package_paths.repo_root_from_script", lambda: tmp_path)

    ret = main(["scan", "--roots", "src"])
    # The helper is report-only: exit 0 even when hits exist.
    assert ret == 0
    assert "Leftover brand hits: 1" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# _is_line_allowlisted unit coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "  - mypyskindose-log  # nosemgrep: mypyskindose-log",
        "id: mypyskindose-privacy",
        "https://github.com/kgrizz-git/MyPySkinDose fork",
    ],
)
def test_is_line_allowlisted_matches(line: str) -> None:
    assert _is_line_allowlisted(line) is True


@pytest.mark.parametrize(
    "repo_rel",
    [
        "dev-docs/plans/archive/old_plan.md",
        "dev-docs/assessments/old.md",
        "dev-docs/plans/GUISKINDOSE_RENAME_PLAN.md",
        "dev-docs/plans/GUISKINDOSE_GITHUB_RENAME_PLAN.md",
        "dev-docs/plans/GUISKINDOSE_PRIVACY_REPUBLICATION_PLAN.md",
        "dev-docs/COORD_TRANSFORM_COMPARISON.md",
    ],
)
def test_is_file_allowlisted_matches(repo_rel: str) -> None:
    from scripts.rewrite_package_paths import _is_file_allowlisted

    assert _is_file_allowlisted(repo_rel) is True


def test_is_file_allowlisted_matches_files_exactly() -> None:
    from scripts.rewrite_package_paths import _is_file_allowlisted

    assert _is_file_allowlisted("CHANGELOG.md") is True
    assert _is_file_allowlisted("CHANGELOG.md.bak") is False
    assert _is_file_allowlisted("scripts/rewrite_package_paths.py") is True
    assert _is_file_allowlisted("scripts/rewrite_package_paths.py.backup") is False
    assert _is_file_allowlisted("dev-docs/plans/archive/old.md") is True
    assert _is_file_allowlisted("dev-docs/plans/archive_extra/old.md") is False


def test_is_line_allowlisted_rejects_bare_reference() -> None:
    assert _is_line_allowlisted("import mypyskindose") is False


def test_scan_allowlist_covers_stale_brand_gate_paths() -> None:
    """Keep rewrite scan and the CI gate allowlisting the same helper files."""
    from scripts.check_stale_brand import ALLOWED_PATHS
    from scripts.rewrite_package_paths import _is_file_allowlisted

    for allowed in ALLOWED_PATHS:
        assert _is_file_allowlisted(allowed), allowed
