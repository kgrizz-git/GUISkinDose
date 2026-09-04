"""Tests for atomic, private, Git-aware export writes."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from guiskindose.safe_output import UnsafeOutputPathError, atomic_write_private


def test_atomic_write_is_private_and_requires_force_to_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "report.bin"
    atomic_write_private(target, b"first")
    assert target.read_bytes() == b"first"
    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o600

    with pytest.raises(UnsafeOutputPathError, match="export_destination_exists"):
        atomic_write_private(target, b"second")
    atomic_write_private(target, b"second", force=True)
    assert target.read_bytes() == b"second"


def test_checkout_writes_require_an_explicit_ignored_root(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("private-output/\n", encoding="utf-8")
    ignored = tmp_path / "private-output"
    ignored.mkdir()
    target = ignored / "report.json"

    with pytest.raises(UnsafeOutputPathError, match="export_checkout_path_forbidden"):
        atomic_write_private(target, b"{}")
    atomic_write_private(target, b"{}", allow_ignored_checkout=True)
    assert target.read_bytes() == b"{}"


def test_rejection_message_never_echoes_sensitive_destination(tmp_path: Path) -> None:
    sentinel = "PATIENT-SENTINEL-12345.json"
    target = tmp_path / sentinel
    target.write_bytes(b"existing")
    with pytest.raises(UnsafeOutputPathError) as caught:
        atomic_write_private(target, b"replacement")
    assert sentinel not in str(caught.value)
