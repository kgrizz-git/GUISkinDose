"""Unit tests for the ``guiskindose.__main__:cli`` entry point.

These guard PR 0 of the GUISkinDose rename: a future
``[project.scripts] guiskindose = "guiskindose.__main__:cli"`` line reuses this
function, so it must exist, be callable, and reach the same argument parser as
``python -m guiskindose``.
"""

from __future__ import annotations

import inspect
import sys
from collections.abc import Iterator

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
