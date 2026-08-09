"""Unit tests for scripts/check_file_sizes.py."""
from pathlib import Path

from scripts.check_file_sizes import MAX_LINES, check_file_sizes


def test_check_file_sizes_under_limit(tmp_path: Path):
    # Setup folders
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    
    # Write a file under limit
    test_file = src_dir / "short.py"
    test_file.write_text("\n" * (MAX_LINES - 10), encoding="utf-8")
    
    assert check_file_sizes(repo_root=tmp_path) is True

def test_check_file_sizes_exceeds_limit(tmp_path: Path):
    # Setup folders
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    
    # Write a file exceeding limit
    test_file = src_dir / "long.py"
    test_file.write_text("\n" * (MAX_LINES + 10), encoding="utf-8")
    
    assert check_file_sizes(repo_root=tmp_path) is False

def test_check_file_sizes_ignores_unsupported_extensions(tmp_path: Path):
    # Setup folders
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    
    # Write an ignored file extension (e.g. .txt) exceeding the limit
    test_file = src_dir / "long.txt"
    test_file.write_text("\n" * (MAX_LINES + 10), encoding="utf-8")
    
    assert check_file_sizes(repo_root=tmp_path) is True

def test_check_file_sizes_no_whitelist_exceptions(tmp_path: Path):
    """No file-size outliers are whitelisted — every scanned file must respect MAX_LINES."""
    app_path = tmp_path / "src" / "mypyskindose" / "gui" / "app.py"
    app_path.parent.mkdir(parents=True)
    app_path.write_text("\n" * (MAX_LINES + 50), encoding="utf-8")
    assert check_file_sizes(repo_root=tmp_path) is False
