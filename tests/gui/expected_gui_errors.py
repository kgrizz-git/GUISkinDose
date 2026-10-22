"""ERROR logs the GUI user fixture may see after pytest 9.1 captures non-propagating loggers.

Allowlist entries are stable message codes. A path or a sentence must be fixed at the
call site, not added here. ``drop_allowed_gui_errors`` edits the call-phase record list
in place because that is the list ``caplog.get_records('call')`` returns during teardown.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

# Same alphabet as guiskindose.privacy._CODE_RE. Duplicated so this test helper
# does not import privacy (and so a privacy-rule change fails this module's tests
# only when the two patterns are compared in test_expected_gui_errors.py).
_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")


@dataclass(frozen=True, slots=True)
class ExpectedGuiError:
    """One ERROR the GUI harness accepts: exact logger name plus an operation code."""

    logger: str
    code: str

    def __post_init__(self) -> None:
        if _CODE.fullmatch(self.code) is None:
            raise ValueError("gui_error_code_not_stable")


# Synthetic code emitted by tests/gui/test_user_fixture_expected_errors.py.
# Task 4 appends codes from tmp/pytest91-gui-report.txt. Do not put FREE_TEXT here.
ALLOWED_GUI_ERRORS: tuple[ExpectedGuiError, ...] = (
    ExpectedGuiError("guiskindose.gui.helpers", "gui_test_expected_error"),
    # Run-config import rollback paths exercised in test_run_state_roundtrip.py.
    ExpectedGuiError("guiskindose.gui.tabs._run_config", "run_config_apply"),
    ExpectedGuiError("guiskindose.gui.tabs._run_config", "run_config_apply_unexpected"),
    ExpectedGuiError("guiskindose.gui.tabs._run_config", "run_config_reapply"),
)


def _operation_code(record: logging.LogRecord) -> str:
    """Return the first token, which ``safe_error_event`` uses as the operation code."""
    parts = record.getMessage().split()
    return parts[0] if parts else ""


def _matches(record: logging.LogRecord) -> bool:
    if record.levelno < logging.ERROR:
        return False
    code = _operation_code(record)
    return any(record.name == entry.logger and code == entry.code for entry in ALLOWED_GUI_ERRORS)


def drop_allowed_gui_errors(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    """Remove allowlisted ERROR records from ``records`` and return those removed."""
    removed = [record for record in records if _matches(record)]
    records[:] = [record for record in records if record not in removed]
    return removed
