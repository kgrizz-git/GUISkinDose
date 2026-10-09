"""Unit tests for the ``guiskindose.__main__:cli`` entry point.

These guard the GUISkinDose console script:
``[project.scripts] guiskindose = "guiskindose.__main__:cli"``.
``cli()`` must exist, be callable, and reach the same argument parser as
``python -m guiskindose``.
"""

from __future__ import annotations

import inspect
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest

from guiskindose.__main__ import cli


@pytest.fixture(autouse=True)
def restore_excepthook() -> Iterator[None]:
    """``cli()`` installs a process-global ``sys.excepthook``; restore it after each test."""
    original = sys.excepthook
    yield
    sys.excepthook = original


def test_cli_is_callable_with_no_arguments():
    """``cli()`` is the zero-arg entry point a console script will call."""
    assert callable(cli)
    assert inspect.signature(cli).parameters == {}


def test_cli_invokes_argument_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    """``cli()`` parses ``sys.argv`` through ``get_argument_parser``.

    The parser is monkeypatched to a stub that records the args it received and
    raises ``SystemExit`` so we never reach GUI/export/dose paths. This proves
    ``cli()`` forwards ``sys.argv[1:]`` to the same parser as ``python -m
    guiskindose`` without depending on the real argparse machinery.
    """
    from guiskindose import __main__ as cli_module

    seen: dict[str, object] = {}

    def fake_parser(argv: list[str]) -> object:
        seen["argv"] = list(argv)
        raise SystemExit(0)

    monkeypatch.setattr(cli_module, "get_argument_parser", fake_parser)
    monkeypatch.setattr(sys, "argv", ["guiskindose", "--help"])

    with pytest.raises(SystemExit):
        cli()

    assert seen["argv"] == ["--help"]


def test_cli_help_path_does_not_require_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    """``python -m guiskindose --help`` works without the GUI extra.

    Driving the real parser through ``cli()`` exercises the same code path as a
    future ``guiskindose --help`` console-script invocation and stays free of
    any NiceGUI import.
    """
    from guiskindose.__main__ import cli

    monkeypatch.setattr(sys, "argv", ["guiskindose", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 0


def test_project_scripts_points_at_cli() -> None:
    """``[project.scripts] guiskindose`` must invoke ``guiskindose.__main__:cli``."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    scripts = data["project"]["scripts"]
    assert scripts["guiskindose"] == "guiskindose.__main__:cli"


@pytest.mark.parametrize("argv", [
    ["--mode", "gui", "--host", "0.0.0.0"],
    ["--mode", "gui", "--allow-network"],
])
def test_gui_network_flags_are_removed(argv: list[str]) -> None:
    """`--host` / `--allow-network` are rejected: the GUI is loopback-only.

    The refusal must hold at the CLI surface too, so the flags cannot be
    silently reintroduced without breaking this test.
    """
    from guiskindose.cli_args import get_argument_parser

    with pytest.raises(SystemExit) as excinfo:
        get_argument_parser(argv)
    assert excinfo.value.code == 2


@pytest.mark.parametrize("argv,expected", [
    (["--mode", "gui"], None),
    (["--mode", "gui", "--port", "9999"], 9999),
    (["--mode", "gui", "--port", "0"], 0),
])
def test_gui_port_flag_parses(argv: list[str], expected: int | None) -> None:
    """`--port` selects the loopback port (0 = OS-assigned)."""
    from guiskindose.cli_args import get_argument_parser

    assert get_argument_parser(argv).port == expected


@pytest.mark.parametrize("argv", [
    ["--mode", "gui", "--port", "70000"],
    ["--mode", "gui", "--port", "-1"],
    ["--mode", "gui", "--port", "notaport"],
])
def test_gui_port_flag_rejects_bad_values(argv: list[str]) -> None:
    """Out-of-range/non-integer ports fail as usage errors, not tracebacks."""
    from guiskindose.cli_args import get_argument_parser

    with pytest.raises(SystemExit) as excinfo:
        get_argument_parser(argv)
    assert excinfo.value.code == 2


def test_resolve_file_paths_expands_missing_glob(tmp_path: Path) -> None:
    from guiskindose.__main__ import _resolve_file_paths

    (tmp_path / "a.csv").write_text("x\n", encoding="utf-8")
    (tmp_path / "b.csv").write_text("y\n", encoding="utf-8")
    resolved = _resolve_file_paths([str(tmp_path / "*.csv")])
    assert len(resolved) == 2
    assert {Path(name).name for name in resolved} == {"a.csv", "b.csv"}


def test_cli_preview_expands_globs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from guiskindose import __main__ as cli_module

    seen: list[str] = []

    def fake_preview(path, **_kwargs) -> None:
        seen.append(str(path))

    (tmp_path / "a.csv").write_text("x\n", encoding="utf-8")
    (tmp_path / "b.csv").write_text("y\n", encoding="utf-8")
    monkeypatch.setattr(cli_module, "preview_input_file", fake_preview)
    monkeypatch.setattr(
        sys,
        "argv",
        ["guiskindose", "--input-preview-only", "--file-path", str(tmp_path / "*.csv")],
    )
    cli()
    assert {Path(p).name for p in seen} == {"a.csv", "b.csv"}


def test_cli_preview_rejects_mixed_tabular_and_dicom(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from guiskindose.input_adapters.import_options import PREVIEW_NON_TABULAR_MESSAGE

    monkeypatch.setattr(
        sys,
        "argv",
        ["guiskindose", "--input-preview-only", "--file-path", "events.csv", "scan.dcm"],
    )
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert PREVIEW_NON_TABULAR_MESSAGE in err
    assert "scan.dcm" not in err
    assert "events.csv" not in err


def test_cli_gui_with_export_format_still_launches_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    gui_app = pytest.importorskip("guiskindose.gui.app")
    called: list[tuple[bool, int | None]] = []

    def fake_run_gui(*, native: bool = False, port: int | None = None) -> None:
        called.append((native, port))

    monkeypatch.setattr(gui_app, "run_gui", fake_run_gui)
    monkeypatch.setattr(
        sys,
        "argv",
        ["guiskindose", "--mode", "gui", "--export-format", "pdf"],
    )
    cli()
    assert called == [(False, None)]


def test_cli_preview_rejects_non_tabular(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from guiskindose.input_adapters.import_options import PREVIEW_NON_TABULAR_MESSAGE

    monkeypatch.setattr(sys, "argv", ["guiskindose", "--input-preview-only", "--file-path", "scan.dcm"])
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert PREVIEW_NON_TABULAR_MESSAGE in err
    assert "scan.dcm" not in err


def test_cli_preview_rejects_aggregate(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from guiskindose.input_adapters.import_options import PREVIEW_AGGREGATE_MESSAGE

    monkeypatch.setattr(
        sys,
        "argv",
        ["guiskindose", "--input-preview-only", "--aggregate", "--file-path", "events.csv"],
    )
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert PREVIEW_AGGREGATE_MESSAGE in err
    assert "events.csv" not in err


def test_cli_rejects_coordinate_flags_with_gui(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from guiskindose.input_adapters.import_options import GUI_IMPORT_OPTIONS_MESSAGE

    monkeypatch.setattr(sys, "argv", ["guiskindose", "--mode", "gui", "--swap-lat-lon"])
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert GUI_IMPORT_OPTIONS_MESSAGE in err


def test_cli_export_rejects_coordinate_flag_on_dicom(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from guiskindose.input_adapters.import_options import IMPORT_OPTIONS_NON_TABULAR_MESSAGE

    out = tmp_path / "report.xlsx"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "guiskindose",
            "--export-format",
            "xlsx",
            "--export-path",
            str(out),
            "--swap-lat-lon",
            "--file-path",
            "scan.dcm",
        ],
    )
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert IMPORT_OPTIONS_NON_TABULAR_MESSAGE in err
    assert "scan.dcm" not in err
    assert not out.exists()


def test_python_module_main_delegates_to_cli() -> None:
    import subprocess

    proc = subprocess.run(
        [sys.executable, "-m", "guiskindose.main", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "--swap-lat-lon" in proc.stdout
    assert "--flip-ap1" in proc.stdout
    assert "--flip-ap2" in proc.stdout
