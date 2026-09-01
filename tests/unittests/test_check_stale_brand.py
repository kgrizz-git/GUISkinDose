"""Unit tests for scripts/check_stale_brand.py."""

from pathlib import Path

from scripts.check_stale_brand import LIVE_PACKAGE_NAME, check_file


def test_live_package_name_pr1_todo_is_present() -> None:
    """PR 0 gate is a no-op until LIVE_PACKAGE_NAME is tightened; keep the marker."""
    source = Path(__file__).resolve().parents[2] / "scripts" / "check_stale_brand.py"
    text = source.read_text(encoding="utf-8")
    assert "TODO(PR1)" in text
    assert LIVE_PACKAGE_NAME == "mypyskindose"


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
        "url = 'github.com/kgrizz-git/MyPySkinDose'\n"
        "sonar.projectName=MyPySkinDose\n"
        "key = 'kgrizz-git_MyPySkinDose'\n"
    )
    file_path.write_text(file_content)
    
    errors = check_file(file_path, repo_root, live_package_name="guiskindose")
    assert not errors

def test_stale_brand_excludes_paths(tmp_path: Path):
    """Entire paths on the allowlist are skipped."""
    repo_root = tmp_path
    file_path = repo_root / "CHANGELOG.md"
    file_path.write_text("This mentions MyPySkinDose and mypyskindose freely.\n")
    
    errors = check_file(file_path, repo_root, live_package_name="guiskindose")
    assert not errors

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
