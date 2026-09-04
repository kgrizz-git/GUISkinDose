"""Unit tests for scripts/check_stale_brand.py."""

from pathlib import Path

from scripts.check_stale_brand import LIVE_PACKAGE_NAME, check_file, is_path_allowed


def test_live_package_name_is_not_noop() -> None:
    """PR 1: leftover pre-rename tokens fail the live-tree gate."""
    source = Path(__file__).resolve().parents[2] / "scripts" / "check_stale_brand.py"
    text = source.read_text(encoding="utf-8")
    assert "TODO(PR1)" not in text
    assert LIVE_PACKAGE_NAME in ("guiskindose", None)
    assert LIVE_PACKAGE_NAME != "mypyskindose"


def test_stale_brand_live_package_allowance(tmp_path: Path):
    """When LIVE_PACKAGE_NAME is mypyskindose, live imports are allowed."""
    repo_root = tmp_path
    file_path = repo_root / "src" / "mypyskindose" / "foo.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("import mypyskindose\nfrom MyPySkinDose import MYPYSKINDOSE_VAR\n")

    # Check with live package name allowed (PR 0 mode)
    errors = check_file(file_path, repo_root, live_package_name="mypyskindose")
    assert not errors


def test_stale_brand_fails_closed(tmp_path: Path):
    """When LIVE_PACKAGE_NAME is guiskindose, stray strings fail."""
    repo_root = tmp_path
    file_path = repo_root / "src" / "guiskindose" / "foo.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("import mypyskindose\nprint('MyPySkinDose')\n")

    errors = check_file(file_path, repo_root, live_package_name="guiskindose")
    assert len(errors) == 2
    assert "import mypyskindose" in errors[0]
    assert "print('MyPySkinDose')" in errors[1]


def test_stale_brand_permanent_allowlist(tmp_path: Path):
    """Even when LIVE_PACKAGE_NAME is guiskindose, permanent allowlist rules apply."""
    repo_root = tmp_path
    file_path = repo_root / "src" / "guiskindose" / "foo.py"
    file_path.parent.mkdir(parents=True)

    file_content = (
        "# nosemgrep: mypyskindose-some-rule\n"
        "rule = 'mypyskindose-unsafe-gui-export-write'\n"
        "url = 'github.com/kgrizz-git/GUISkinDose'\n"
        "key = 'kgrizz-git_GUISkinDose'\n"
    )
    file_path.write_text(file_content)

    errors = check_file(file_path, repo_root, live_package_name="guiskindose")
    assert not errors


def test_stale_brand_rejects_live_old_github_urls_and_sonar_key(tmp_path: Path) -> None:
    """Since the 2026-09-04 GitHub/Sonar rename, the old live URL and Sonar key are
    stale brand strings, not allowlisted leftovers."""
    repo_root = tmp_path
    file_path = repo_root / "docs" / "foo.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_text(
        "url = 'https://github.com/kgrizz-git/MyPySkinDose'\n"
        "key = 'kgrizz-git_MyPySkinDose'\n"
        "sonar.projectName=MyPySkinDose\n",
        encoding="utf-8",
    )
    errors = check_file(file_path, repo_root, live_package_name="guiskindose")
    assert len(errors) == 3


def test_stale_brand_excludes_paths(tmp_path: Path):
    """Entire paths on the allowlist are skipped."""
    repo_root = tmp_path
    file_path = repo_root / "dev-docs" / "plans" / "GUISKINDOSE_RENAME_PLAN.md"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("This mentions MyPySkinDose and mypyskindose freely.\n")

    errors = check_file(file_path, repo_root, live_package_name="guiskindose")
    assert not errors


def test_stale_brand_allowlist_matches_files_exactly() -> None:
    """File allowlist entries must not match a suffix variant of the same name."""
    assert is_path_allowed("CHANGELOG.md") is False
    assert is_path_allowed("CHANGELOG.md.bak") is False
    assert is_path_allowed("dev-docs/plans/GUISKINDOSE_RENAME_PLAN.md") is True
    assert is_path_allowed("scripts/check_stale_brand.py") is True
    assert is_path_allowed("scripts/check_stale_brand.py.backup") is False
    assert is_path_allowed("dev-docs/plans/archive/old.md") is True
    assert is_path_allowed("dev-docs/plans/archive_extra/old.md") is False


def test_stale_brand_changelog_unreleased_stray_import(tmp_path: Path) -> None:
    """Unreleased CHANGELOG must not hide an unquoted import of the old package."""
    repo_root = tmp_path
    file_path = repo_root / "CHANGELOG.md"
    file_path.write_text(
        "## [Unreleased]\n\n- leftover live docs still say import mypyskindose\n\n"
        "## [25.2.0] - 2026-07-21\n\n- MyPySkinDose history\n",
        encoding="utf-8",
    )
    errors = check_file(file_path, repo_root, live_package_name="guiskindose")
    assert len(errors) == 1
    assert "import mypyskindose" in errors[0]


def test_stale_brand_changelog_skips_historical_25_sections(tmp_path: Path) -> None:
    """Keep a Changelog sections from ``## [25.`` onward are not scanned."""
    repo_root = tmp_path
    file_path = repo_root / "CHANGELOG.md"
    file_path.write_text(
        "## [Unreleased]\n\n- GUISkinDose 1.0.0\n\n## [25.2.0] - 2026-07-21\n\n- import mypyskindose\n- MyPySkinDose\n",
        encoding="utf-8",
    )
    errors = check_file(file_path, repo_root, live_package_name="guiskindose")
    assert errors == []


def test_stale_brand_changelog_allows_rename_prose(tmp_path: Path) -> None:
    """Unreleased rename notes may mention the old path and dual-read leftovers."""
    repo_root = tmp_path
    file_path = repo_root / "CHANGELOG.md"
    file_path.write_text(
        "\n".join(
            [
                "## [Unreleased]",
                "",
                "- `git mv src/mypyskindose src/guiskindose`",
                "- legacy mypyskindose paths; (`mypyskindose` → `guiskindose`)",
                "- rule IDs stay `mypyskindose-*`; LIVE_PACKAGE_NAME must not remain",
                '  `"mypyskindose"`',
                "- not MyPySkinDose `26.0.0`; remain MyPySkinDose history",
                "- python -m mypyskindose --mode gui (historical CLI)",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    errors = check_file(file_path, repo_root, live_package_name="guiskindose")
    assert errors == []


def test_stale_brand_temp_prefixes_not_allowed(tmp_path: Path):
    """Temp prefixes like mypyskindose-uploads should fail closed after PR 1."""
    repo_root = tmp_path
    file_path = repo_root / "src" / "guiskindose" / "foo.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("prefix = 'mypyskindose-uploads'\n")

    errors = check_file(file_path, repo_root, live_package_name="guiskindose")
    assert len(errors) == 1
    assert "mypyskindose-uploads" in errors[0]


def test_stale_brand_skips_nul_files(tmp_path: Path) -> None:
    repo_root = tmp_path
    file_path = repo_root / "src" / "guiskindose" / "data.bin"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"mypyskindose\x00rest")
    assert check_file(file_path, repo_root, live_package_name="guiskindose") == []


def test_stale_brand_allows_dual_read_and_historical_identity(tmp_path: Path) -> None:
    """Config/env fallbacks and 'formerly MyPySkinDose 25.2.0' remain allowed."""
    repo_root = tmp_path
    file_path = repo_root / "src" / "guiskindose" / "window_prefs.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text(
        "\n".join(
            [
                'SHOW = "MYPYSKINDOSE_SHOW_DEMO_PHANTOMS"',
                'path = Path.home() / ".mypyskindose" / "gui.json"',
                'rules = ".semgrep/mypyskindose-privacy.yml"',
                "The package name in code is guiskindose (formerly `mypyskindose`).",
                "formerly MyPySkinDose, a fork of PySkinDose.",
                "not a continuation of MyPySkinDose `25.2.0`.",
                'for package_name in ("guiskindose", "mypyskindose"):',
                "legacy ``mypyskindose/`` traceback frames",
                "",
            ]
        ),
        encoding="utf-8",
    )
    errors = check_file(file_path, repo_root, live_package_name="guiskindose")
    assert errors == []


def test_stale_brand_still_rejects_import_of_old_package(tmp_path: Path) -> None:
    """Quoted dual-read names are allowed; an unquoted import is not."""
    repo_root = tmp_path
    file_path = repo_root / "src" / "guiskindose" / "oops.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("import mypyskindose\n", encoding="utf-8")
    errors = check_file(file_path, repo_root, live_package_name="guiskindose")
    assert len(errors) == 1
    assert "import mypyskindose" in errors[0]


def test_stale_brand_rejects_relative_import_of_old_package(tmp_path: Path) -> None:
    """A live ``from .mypyskindose import x`` must fail; the dual-read config
    allowlist is scoped to real path/env leftovers, not any ``.mypyskindose``."""
    repo_root = tmp_path
    file_path = repo_root / "src" / "guiskindose" / "oops.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("from .mypyskindose import analyze_data\n", encoding="utf-8")
    errors = check_file(file_path, repo_root, live_package_name="guiskindose")
    assert len(errors) == 1
    assert "from .mypyskindose import analyze_data" in errors[0]


def test_stale_brand_rejects_bare_dotted_reference(tmp_path: Path) -> None:
    """Bare dotted leftovers like ``pkg.mypyskindose`` in live code must fail."""
    repo_root = tmp_path
    file_path = repo_root / "src" / "guiskindose" / "oops.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text(
        "value = pkg.mypyskindose\nOLD = getattr(pkg, 'mypyskindose')\n",
        encoding="utf-8",
    )
    errors = check_file(file_path, repo_root, live_package_name="guiskindose")
    assert len(errors) == 2
    assert "pkg.mypyskindose" in errors[0]
    assert "'mypyskindose'" in errors[1]


def test_stale_brand_changelog_rejects_dotted_import(tmp_path: Path) -> None:
    """``import mypyskindose.gui`` in Unreleased must fail; dotted references in
    historical ``## [25.`` sections are unreachable, so no changelog allowance
    weakens the 'unquoted import fails' guarantee."""
    repo_root = tmp_path
    file_path = repo_root / "CHANGELOG.md"
    file_path.write_text(
        "## [Unreleased]\n\n- fix: still calls import mypyskindose.gui\n\n"
        "## [25.2.0] - 2026-07-21\n\n- ``import of mypyskindose.gui`` is history\n",
        encoding="utf-8",
    )
    errors = check_file(file_path, repo_root, live_package_name="guiskindose")
    assert len(errors) == 1
    assert "import mypyskindose.gui" in errors[0]
