"""Cross-platform command construction for the native "Open file / Open folder"
success actions (export tab). Subprocess is mocked so nothing actually launches."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("nicegui")

from mypyskindose.gui.tabs.export import _open_path


def _capture(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(list(args))

        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr("subprocess.run", fake_run)
    return calls


def test_open_file_macos(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    calls = _capture(monkeypatch)
    assert _open_path(Path("/tmp/report.pdf")) is True
    assert calls == [["open", "/tmp/report.pdf"]]


def test_reveal_folder_macos(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    calls = _capture(monkeypatch)
    assert _open_path(Path("/tmp/report.pdf"), reveal=True) is True
    assert calls == [["open", "-R", "/tmp/report.pdf"]]


def test_open_file_linux(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    calls = _capture(monkeypatch)
    assert _open_path(Path("/tmp/report.pdf")) is True
    assert calls == [["xdg-open", "/tmp/report.pdf"]]


def test_reveal_linux_opens_parent(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    calls = _capture(monkeypatch)
    assert _open_path(Path("/tmp/sub/report.pdf"), reveal=True) is True
    assert calls == [["xdg-open", "/tmp/sub"]]


def test_open_file_windows(monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    calls = _capture(monkeypatch)
    # os.startfile only exists on Windows; provide a stub.
    import os

    started: list[str] = []
    monkeypatch.setattr(os, "startfile", started.append, raising=False)
    assert _open_path(Path(r"C:\reports\report.pdf")) is True
    assert started == [r"C:\reports\report.pdf"]
    assert calls == []  # startfile, not subprocess


def test_failure_returns_false(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")

    def boom(*a, **k):
        raise OSError("no launcher")

    monkeypatch.setattr("subprocess.run", boom)
    assert _open_path(Path("/tmp/report.pdf")) is False
