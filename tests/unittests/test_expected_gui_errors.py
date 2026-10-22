"""Allowlisted GUI ERROR records are removed in place; everything else stays."""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "gui" / "expected_gui_errors.py"
_SPEC = importlib.util.spec_from_file_location("expected_gui_errors", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
drop_allowed_gui_errors = _MODULE.drop_allowed_gui_errors
ALLOWED_GUI_ERRORS = _MODULE.ALLOWED_GUI_ERRORS
ExpectedGuiError = _MODULE.ExpectedGuiError


def _record(name: str, level: int, message: str) -> logging.LogRecord:
    return logging.LogRecord(name, level, __file__, 1, message, (), None)


def test_drop_removes_only_matching_error_codes() -> None:
    allowed = ExpectedGuiError("guiskindose.gui.helpers", "gui_test_expected_error")
    assert allowed in ALLOWED_GUI_ERRORS
    keep_warning = _record("guiskindose.gui.helpers", logging.WARNING, "gui_test_expected_error")
    keep_other = _record("guiskindose.gui.helpers", logging.ERROR, "unlisted_code")
    keep_other_logger = _record("guiskindose.gui.app", logging.ERROR, "gui_test_expected_error")
    drop_me = _record("guiskindose.gui.helpers", logging.ERROR, "gui_test_expected_error")
    shaped = _record(
        "guiskindose.gui.helpers",
        logging.ERROR,
        "gui_test_expected_error failed (error_type=ValueError at guiskindose/gui/helpers.py:1 in fn)",
    )
    records = [keep_warning, keep_other, keep_other_logger, drop_me, shaped]
    removed = drop_allowed_gui_errors(records)
    assert removed == [drop_me, shaped]
    assert records == [keep_warning, keep_other, keep_other_logger]


def test_allowlist_codes_match_the_privacy_code_pattern() -> None:
    code_re = __import__("re").compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
    for entry in ALLOWED_GUI_ERRORS:
        assert code_re.fullmatch(entry.code)
        assert " " not in entry.code
        assert "/" not in entry.code
        assert "\\" not in entry.code
