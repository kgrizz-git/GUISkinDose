"""Unit tests for scripts/check_file_sizes.py."""
from pathlib import Path

from scripts.check_file_sizes import APPEND_ONLY_HISTORY, MAX_LINES, check_file_sizes


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
    app_path = tmp_path / "src" / "guiskindose" / "gui" / "app.py"
    app_path.parent.mkdir(parents=True)
    app_path.write_text("\n" * (MAX_LINES + 50), encoding="utf-8")
    assert check_file_sizes(repo_root=tmp_path) is False


def test_append_only_history_may_exceed_the_limit(tmp_path: Path):
    """A chronological log is read newest-first or grepped, never front-to-back.

    Holding it to the cap once forced prose out of three existing, accurate entries to make
    room for a new one — the gate degrading the record it exists to protect.
    """
    log_path = tmp_path / "dev-docs" / "MAINTENANCE_LOG.md"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("\n" * (MAX_LINES + 200), encoding="utf-8")

    assert check_file_sizes(repo_root=tmp_path) is True


def test_the_exemption_is_named_not_a_blanket_for_dev_docs(tmp_path: Path):
    """Only the listed history files are exempt; a normal dev-doc is still capped."""
    other = tmp_path / "dev-docs" / "SOME_GUIDE.md"
    other.parent.mkdir(parents=True)
    other.write_text("\n" * (MAX_LINES + 10), encoding="utf-8")

    assert check_file_sizes(repo_root=tmp_path) is False


def test_append_only_history_covers_the_real_log_path(tmp_path: Path):
    """Pins the exact repo-relative path, so moving the log re-imposes the cap visibly."""
    assert "dev-docs/MAINTENANCE_LOG.md" in APPEND_ONLY_HISTORY
    assert (Path(__file__).resolve().parents[2] / "dev-docs" / "MAINTENANCE_LOG.md").is_file()
