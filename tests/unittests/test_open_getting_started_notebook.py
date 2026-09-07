"""Tests for the ignored getting-started notebook launcher."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import open_getting_started_notebook as notebook_launcher
from scripts.open_getting_started_notebook import prepare_local_notebook


def test_prepare_local_notebook_creates_a_copy(tmp_path: Path):
    source = tmp_path / "source.ipynb"
    target = tmp_path / "tmp" / "notebooks" / "getting_started.local.ipynb"
    source.write_text('{"cells": []}\n', encoding="utf-8")

    assert prepare_local_notebook(source, target) is True
    assert target.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_prepare_local_notebook_preserves_existing_local_work(tmp_path: Path):
    source = tmp_path / "source.ipynb"
    target = tmp_path / "tmp" / "notebooks" / "getting_started.local.ipynb"
    source.write_text('{"cells": []}\n', encoding="utf-8")
    target.parent.mkdir(parents=True)
    target.write_text('{"local": true}\n', encoding="utf-8")

    assert prepare_local_notebook(source, target) is False
    assert target.read_text(encoding="utf-8") == '{"local": true}\n'


def test_prepare_local_notebook_reset_replaces_existing_local_work(tmp_path: Path):
    source = tmp_path / "source.ipynb"
    target = tmp_path / "tmp" / "notebooks" / "getting_started.local.ipynb"
    source.write_text('{"cells": []}\n', encoding="utf-8")
    target.parent.mkdir(parents=True)
    target.write_text('{"local": true}\n', encoding="utf-8")

    assert prepare_local_notebook(source, target, reset=True) is True
    assert target.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_prepare_local_notebook_requires_canonical_source(tmp_path: Path):
    missing_source = tmp_path / "missing.ipynb"
    target = tmp_path / "tmp" / "notebooks" / "getting_started.local.ipynb"

    with pytest.raises(FileNotFoundError, match="Canonical getting-started notebook is missing") as error:
        prepare_local_notebook(missing_source, target)

    assert str(missing_source) not in str(error.value)


def configure_launcher_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "docs" / "source" / "getting_started" / "getting_started.ipynb"
    target = tmp_path / "tmp" / "notebooks" / "getting_started.local.ipynb"
    source.parent.mkdir(parents=True)
    source.write_text('{"cells": []}\n', encoding="utf-8")
    monkeypatch.setattr(notebook_launcher, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(notebook_launcher, "CANONICAL_NOTEBOOK", source)
    monkeypatch.setattr(notebook_launcher, "LOCAL_NOTEBOOK", target)
    return source, target


def test_launcher_main_no_launch_preserves_then_resets_local_copy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source, target = configure_launcher_paths(monkeypatch, tmp_path)

    assert notebook_launcher.main(["--no-launch"]) == 0
    target.write_text('{"local": true}\n', encoding="utf-8")
    assert notebook_launcher.main(["--no-launch"]) == 0
    assert target.read_text(encoding="utf-8") == '{"local": true}\n'

    assert notebook_launcher.main(["--reset", "--no-launch"]) == 0
    assert target.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_launcher_main_starts_jupyterlab_with_local_copy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    _, target = configure_launcher_paths(monkeypatch, tmp_path)
    calls: list[tuple[list[str], Path, bool]] = []

    def fake_run(command: list[str], *, cwd: Path, check: bool) -> SimpleNamespace:
        calls.append((command, cwd, check))
        return SimpleNamespace(returncode=17)

    monkeypatch.setattr(notebook_launcher.subprocess, "run", fake_run)

    assert notebook_launcher.main([]) == 17
    assert calls == [([sys.executable, "-m", "jupyter", "lab", str(target)], tmp_path, False)]
