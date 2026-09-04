"""Unit tests for scripts/sync_gui_help.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.sync_gui_help import (
    diff_files,
    sync,
    validate_source,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "sync_gui_help.py"


@pytest.fixture()
def mirror_dirs(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "docs" / "source" / "gui_help"
    target = tmp_path / "src" / "guiskindose" / "gui" / "help"
    source.mkdir(parents=True)
    target.mkdir(parents=True)
    return source, target


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--repo-root", str(cwd)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_sync_creates_target_file_from_new_source(mirror_dirs: tuple[Path, Path]) -> None:
    source, target = mirror_dirs
    (source / "topic.md").write_text("hello", encoding="utf-8")

    rc = sync(source, target, check=False)

    assert rc == 0
    assert (target / "topic.md").read_text(encoding="utf-8") == "hello"


def test_sync_overwrites_modified_source(mirror_dirs: tuple[Path, Path]) -> None:
    source, target = mirror_dirs
    (source / "topic.md").write_text("new", encoding="utf-8")
    (target / "topic.md").write_text("old", encoding="utf-8")

    sync(source, target, check=False)

    assert (target / "topic.md").read_text(encoding="utf-8") == "new"


def test_sync_leaves_unchanged_target_alone(
    mirror_dirs: tuple[Path, Path],
) -> None:
    source, target = mirror_dirs
    (source / "topic.md").write_text("same", encoding="utf-8")
    target_file = target / "topic.md"
    target_file.write_text("same", encoding="utf-8")
    mtime_before = target_file.stat().st_mtime_ns

    sync(source, target, check=False)

    assert target_file.read_text(encoding="utf-8") == "same"
    assert target_file.stat().st_mtime_ns == mtime_before


def test_sync_deletes_stale_target_files(
    mirror_dirs: tuple[Path, Path],
) -> None:
    source, target = mirror_dirs
    (source / "topic.md").write_text("keep", encoding="utf-8")
    (target / "stale.md").write_text("drop", encoding="utf-8")

    sync(source, target, check=False)

    assert (target / "topic.md").exists()
    assert not (target / "stale.md").exists()


def test_check_mode_exits_zero_when_in_sync(
    mirror_dirs: tuple[Path, Path],
) -> None:
    source, target = mirror_dirs
    (source / "topic.md").write_text("same", encoding="utf-8")
    (target / "topic.md").write_text("same", encoding="utf-8")

    assert sync(source, target, check=True) == 0


def test_check_mode_exits_one_when_target_missing(
    mirror_dirs: tuple[Path, Path],
) -> None:
    source, target = mirror_dirs
    (source / "topic.md").write_text("new", encoding="utf-8")

    assert sync(source, target, check=True) == 1


def test_check_mode_exits_one_when_target_stale(
    mirror_dirs: tuple[Path, Path],
) -> None:
    source, target = mirror_dirs
    (source / "topic.md").write_text("keep", encoding="utf-8")
    (target / "stale.md").write_text("drop", encoding="utf-8")

    assert sync(source, target, check=True) == 1


def test_check_mode_does_not_modify_files(
    mirror_dirs: tuple[Path, Path],
) -> None:
    source, target = mirror_dirs
    (source / "topic.md").write_text("new", encoding="utf-8")
    stale = target / "stale.md"
    stale.write_text("drop", encoding="utf-8")
    stale_mtime = stale.stat().st_mtime_ns

    sync(source, target, check=True)

    assert not (target / "topic.md").exists()
    assert stale.read_text(encoding="utf-8") == "drop"
    assert stale.stat().st_mtime_ns == stale_mtime


def test_validate_source_refuses_missing(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        validate_source(tmp_path / "missing")
    assert exc.value.code == 1


def test_validate_source_refuses_file_not_dir(tmp_path: Path) -> None:
    f = tmp_path / "not-a-dir"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        validate_source(f)
    assert exc.value.code == 1


def test_validate_source_refuses_empty(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(SystemExit) as exc:
        validate_source(empty)
    assert exc.value.code == 1


def test_validate_source_refuses_subdirectory(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "topic.md").write_text("a", encoding="utf-8")
    (src / "subdir").mkdir()
    with pytest.raises(SystemExit) as exc:
        validate_source(src)
    assert exc.value.code == 1


def test_validate_source_ignores_non_md_files(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "topic.md").write_text("a", encoding="utf-8")
    (src / "scratch.txt").write_text("ignore", encoding="utf-8")
    files = validate_source(src)
    assert [p.name for p in files] == ["topic.md"]


def test_sync_normalizes_crlf_to_lf(mirror_dirs: tuple[Path, Path]) -> None:
    source, target = mirror_dirs
    (source / "topic.md").write_bytes(b"line1\r\nline2\r\n")

    sync(source, target, check=False)

    out = (target / "topic.md").read_bytes()
    assert out == b"line1\nline2\n"


def test_sync_strips_utf8_bom_on_read_and_writes_without_bom(
    mirror_dirs: tuple[Path, Path],
) -> None:
    source, target = mirror_dirs
    (source / "topic.md").write_bytes(b"\xef\xbb\xbf# heading\nbody\n")

    sync(source, target, check=False)

    out = (target / "topic.md").read_bytes()
    assert out == b"# heading\nbody\n"


def test_sync_target_created_when_missing(mirror_dirs: tuple[Path, Path]) -> None:
    source, _ = mirror_dirs
    target = source.parent / "does-not-exist" / "help"
    (source / "topic.md").write_text("a", encoding="utf-8")

    sync(source, target, check=False)

    assert (target / "topic.md").exists()


def test_check_mode_target_missing_exits_one(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "topic.md").write_text("a", encoding="utf-8")
    target = tmp_path / "absent" / "help"

    with pytest.raises(SystemExit) as exc:
        sync(source, target, check=True)
    assert exc.value.code == 1


def test_diff_files_detects_difference(tmp_path: Path) -> None:
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("same", encoding="utf-8")
    b.write_text("diff", encoding="utf-8")
    assert diff_files(a, b) is True


def test_diff_files_detects_match(tmp_path: Path) -> None:
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("same", encoding="utf-8")
    b.write_text("same", encoding="utf-8")
    assert diff_files(a, b) is False


def test_diff_files_target_missing(tmp_path: Path) -> None:
    a = tmp_path / "a.md"
    b = tmp_path / "missing.md"
    a.write_text("x", encoding="utf-8")
    assert diff_files(a, b) is True


def test_non_utf8_input_exits_cleanly(mirror_dirs: tuple[Path, Path]) -> None:
    source, target = mirror_dirs
    (source / "topic.md").write_bytes(b"\xff\xfe\x00bad-bytes")

    with pytest.raises(UnicodeDecodeError):
        sync(source, target, check=False)


def test_cli_check_in_sync(tmp_path: Path) -> None:
    source = tmp_path / "docs" / "source" / "gui_help"
    target = tmp_path / "src" / "guiskindose" / "gui" / "help"
    source.mkdir(parents=True)
    target.mkdir(parents=True)
    (source / "a.md").write_text("x", encoding="utf-8")
    (target / "a.md").write_text("x", encoding="utf-8")
    result = _run_cli("--check", cwd=tmp_path)
    assert result.returncode == 0


def test_cli_check_out_of_sync(tmp_path: Path) -> None:
    source = tmp_path / "docs" / "source" / "gui_help"
    target = tmp_path / "src" / "guiskindose" / "gui" / "help"
    source.mkdir(parents=True)
    target.mkdir(parents=True)
    (source / "a.md").write_text("x", encoding="utf-8")
    (target / "a.md").write_text("y", encoding="utf-8")
    result = _run_cli("--check", cwd=tmp_path)
    assert result.returncode == 1
    assert "out of sync" in result.stderr


def test_cli_missing_source_dir(tmp_path: Path) -> None:
    result = _run_cli("--check", cwd=tmp_path)
    assert result.returncode == 1
    assert "does not exist" in result.stderr


def test_cli_empty_source_dir(tmp_path: Path) -> None:
    (tmp_path / "docs" / "source" / "gui_help").mkdir(parents=True)
    result = _run_cli("--check", cwd=tmp_path)
    assert result.returncode == 1
    assert "empty" in result.stderr
