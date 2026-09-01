"""Unit tests for the ``mypyskindose.__main__:cli`` entry point.

These guard PR 0 of the GUISkinDose rename: a future
``[project.scripts] guiskindose = "guiskindose.__main__:cli"`` line reuses this
function, so it must exist, be callable, and reach the same argument parser as
``python -m mypyskindose``.
"""

from __future__ import annotations

import inspect
import sys

import pytest

from mypyskindose.__main__ import cli


def test_cli_is_callable_with_no_arguments():
    """``cli()`` is the zero-arg entry point a console script will call."""
    assert callable(cli)
    assert inspect.signature(cli).parameters == {}


def test_cli_invokes_argument_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    """``cli()`` parses ``sys.argv`` through ``get_argument_parser``.

    The parser is monkeypatched to a stub that records the args it received and
    raises ``SystemExit`` so we never reach GUI/export/dose paths. This proves
    ``cli()`` forwards ``sys.argv[1:]`` to the same parser as ``python -m
    mypyskindose`` without depending on the real argparse machinery.
    """
    from mypyskindose import __main__ as cli_module

    seen: dict[str, object] = {}

    def fake_parser(argv: list[str]) -> object:
        seen["argv"] = list(argv)
        raise SystemExit(0)

    monkeypatch.setattr(cli_module, "get_argument_parser", fake_parser)
    monkeypatch.setattr(sys, "argv", ["mypyskindose", "--help"])

    with pytest.raises(SystemExit):
        cli()

    assert seen["argv"] == ["--help"]


def test_cli_help_path_does_not_require_gui(monkeypatch: pytest.MonkeyPatch) -> None:
    """``python -m mypyskindose --help`` works without the GUI extra.

    Driving the real parser through ``cli()`` exercises the same code path as a
    future ``guiskindose --help`` console-script invocation and stays free of
    any NiceGUI import.
    """
    from mypyskindose.__main__ import cli

    monkeypatch.setattr(sys, "argv", ["mypyskindose", "--help"])
    with pytest.raises(SystemExit) as excinfo:
        cli()
    assert excinfo.value.code == 0
